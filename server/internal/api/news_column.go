package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"sentinel/internal/auth"
)

// news_column.go — 用户自定义行业/板块专栏(用户隔离,与策略无关)。
// 用户设关注板块 → 按板块筛选新闻 → AI 合成聚焦专栏。每用户每日缓存一份。

const columnSys = `你是财经编辑,为关注特定板块的A股投资者写一份【板块专栏日报】。给你用户关注的板块 + 与这些板块相关的今日新闻。
提炼成聚焦这些板块的结构化专栏。只输出JSON,不编造,不预测涨跌幅。
{
 "overview": "一段综述(60字内:今天这些板块最该关注什么)",
 "items": [{"sector":"板块","points":["要点1","要点2"],"tone":"利好/利空/中性","impact":"对该板块的影响一句"}]
}
items 每个关注板块一条(有相关新闻才给),按重要性排序。宁缺勿凑。`

// newsColumn 用户专栏。
//   GET  /api/news/column?market=cn        → 该用户的关注板块 + 最新专栏
//   PUT  /api/news/column  body:{sectors:[]} → 设置关注板块
//   POST /api/news/column?refresh=1        → 立即生成今日专栏
func (a *API) newsColumn(w http.ResponseWriter, r *http.Request) {
	uid := auth.UserID(r)
	market := mktParam(r)
	switch r.Method {
	case http.MethodPut:
		var b struct {
			Sectors []string `json:"sectors"`
		}
		_ = json.NewDecoder(r.Body).Decode(&b)
		clean := make([]string, 0, len(b.Sectors))
		for _, s := range b.Sectors {
			if s = strings.TrimSpace(s); s != "" && len([]rune(s)) <= 12 {
				clean = append(clean, s)
			}
		}
		a.gdb.Exec(`INSERT INTO user_columns(user_id,market,sectors,updated_at) VALUES(?,?,string_to_array(?, ','),now())
			ON CONFLICT(user_id,market) DO UPDATE SET sectors=string_to_array(?, ','), updated_at=now()`,
			uid, market, strings.Join(clean, ","), strings.Join(clean, ","))
		writeJSON(w, http.StatusOK, map[string]any{"sectors": clean})
		return
	case http.MethodPost:
		a.generateColumn(r.Context(), uid, market)
		fallthrough
	case http.MethodGet:
		var secStr string
		a.gdb.Raw(`SELECT COALESCE(array_to_string(sectors,','),'') FROM user_columns WHERE user_id=? AND market=?`, uid, market).Row().Scan(&secStr)
		sectors := []string{}
		if secStr != "" {
			sectors = strings.Split(secStr, ",")
		}
		var digestDate, digest string
		a.gdb.Raw(`SELECT digest_date::text, digest::text FROM user_column_digest WHERE user_id=? AND market=? ORDER BY digest_date DESC LIMIT 1`,
			uid, market).Row().Scan(&digestDate, &digest)
		out := map[string]any{"sectors": sectors, "digest_date": digestDate}
		if digest != "" {
			out["digest"] = digest
		}
		writeJSON(w, http.StatusOK, out)
		return
	default:
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "GET/PUT/POST"})
	}
}

// generateColumn 按用户关注板块,筛选相关新闻 → AI 合成专栏 → 存(用户隔离)。
func (a *API) generateColumn(ctx context.Context, uid int64, market string) {
	var secStr string
	a.gdb.Raw(`SELECT COALESCE(array_to_string(sectors,','),'') FROM user_columns WHERE user_id=? AND market=?`, uid, market).Row().Scan(&secStr)
	if secStr == "" || a.aiClient == nil || !a.aiClient.Enabled() {
		return
	}
	sectors := strings.Split(secStr, ",")
	// 按板块关键词筛今日相关新闻(标题/正文命中任一板块词)
	like := make([]string, 0, len(sectors))
	args := []any{market, market} // 外层 market + 子查询 market
	for _, s := range sectors {
		like = append(like, "(title LIKE ? OR body LIKE ?)")
		args = append(args, "%"+s+"%", "%"+s+"%")
	}
	q := `SELECT title, COALESCE(body,'') AS body FROM news_items
		WHERE market=? AND published_at::date = (SELECT max(published_at::date) FROM news_items WHERE market=?)
		AND (` + strings.Join(like, " OR ") + `) ORDER BY published_at DESC LIMIT 40`
	type row struct{ Title, Body string }
	var rows []row
	a.gdb.Raw(q, args...).Scan(&rows)
	if len(rows) == 0 {
		return
	}
	var sb strings.Builder
	fmt.Fprintf(&sb, "关注板块:%s\n相关新闻(%d条):\n", strings.Join(sectors, "、"), len(rows))
	for _, r := range rows {
		fmt.Fprintf(&sb, "· %s %s\n", r.Title, trunc(r.Body, 40))
	}
	cctx, cancel := context.WithTimeout(ctx, 90*time.Second)
	defer cancel()
	out, err := a.aiClient.Chat(cctx, columnSys, sb.String())
	if err != nil {
		return
	}
	out = stripFence(out)
	// 提取 JSON
	if i, j := strings.Index(out, "{"), strings.LastIndex(out, "}"); i >= 0 && j > i {
		out = out[i : j+1]
	}
	if !json.Valid([]byte(out)) {
		return
	}
	a.gdb.Exec(`INSERT INTO user_column_digest(user_id,market,digest_date,digest,generated_at)
		VALUES(?,?,current_date,?::jsonb,now())
		ON CONFLICT(user_id,market,digest_date) DO UPDATE SET digest=EXCLUDED.digest, generated_at=now()`,
		uid, market, out)
}
