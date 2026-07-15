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

// news_column.go — 用户自定义板块专栏(tab 式,每板块一份完整 digest;用户隔离,与策略无关)。

const columnSys = `你是财经编辑,为【只关注「%s」这个板块】的A股投资者写一份聚焦该板块的资讯日报。给你与该板块相关的今日新闻,提炼成结构化内容。只输出JSON,不编造,不预测涨跌幅。
{
 "overview": "该板块今日综述(80字内,最该关注什么)",
 "world": [{"title":"与该板块相关的世界大事","impact":"对该板块的影响","tone":"利好/利空/中性"}],
 "domestic": [{"title":"与该板块相关的国内大事","impact":"...","tone":"..."}],
 "stock_impact": [{"stock":"该板块受影响的具体A股个股(名称)","reason":"为什么","tone":"..."}],
 "global_transmission": [{"event":"传导到该板块的全球事件","timing":"提前/滞后特征","tone":"..."}]
}
每节取最相关的 2-5 条,stock_impact 尽量点名该板块的具体上市公司。宁缺勿凑,没有就空数组。全部紧扣「%s」板块。`

// newsColumn 板块列表管理。GET 读关注板块;PUT 设置。
func (a *API) newsColumn(w http.ResponseWriter, r *http.Request) {
	uid := auth.UserID(r)
	market := mktParam(r)
	if r.Method == http.MethodPut {
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
	}
	writeJSON(w, http.StatusOK, map[string]any{"sectors": a.userSectors(uid, market)})
}

func (a *API) userSectors(uid int64, market string) []string {
	var secStr string
	a.gdb.Raw(`SELECT COALESCE(array_to_string(sectors,','),'') FROM user_columns WHERE user_id=? AND market=?`, uid, market).Row().Scan(&secStr)
	if secStr == "" {
		return []string{}
	}
	return strings.Split(secStr, ",")
}

// newsSectorDigest 某板块的完整 digest。GET /api/news/column/digest?market=cn&sector=半导体&refresh=1
func (a *API) newsSectorDigest(w http.ResponseWriter, r *http.Request) {
	uid := auth.UserID(r)
	market := mktParam(r)
	sector := strings.TrimSpace(r.URL.Query().Get("sector"))
	if sector == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 sector"})
		return
	}
	if r.URL.Query().Get("refresh") == "1" {
		a.generateSectorDigest(r.Context(), uid, market, sector)
	}
	var digestDate, digest string
	a.gdb.Raw(`SELECT digest_date::text, digest::text FROM user_column_digest
		WHERE user_id=? AND market=? AND sector=? ORDER BY digest_date DESC LIMIT 1`, uid, market, sector).
		Row().Scan(&digestDate, &digest)
	out := map[string]any{"sector": sector, "digest_date": digestDate}
	if digest != "" {
		out["digest"] = digest
	}
	writeJSON(w, http.StatusOK, out)
}

// generateSectorDigest 按板块筛当日新闻 → AI 合成完整 digest → 存(用户隔离)。
func (a *API) generateSectorDigest(ctx context.Context, uid int64, market, sector string) {
	if a.aiClient == nil || !a.aiClient.Enabled() {
		return
	}
	rows := a.sectorNews(market, sector, 40)
	if len(rows) == 0 {
		return
	}
	var sb strings.Builder
	fmt.Fprintf(&sb, "【当前日期】%s(时间判断以此为准,勿臆断年份)\n板块「%s」相关新闻(%d条):\n", todayCN(), sector, len(rows))
	for _, r := range rows {
		fmt.Fprintf(&sb, "· %s %s\n", r.Title, trunc(r.Body, 40))
	}
	cctx, cancel := context.WithTimeout(ctx, 90*time.Second)
	defer cancel()
	sys := fmt.Sprintf(columnSys, sector, sector)
	out, err := a.aiClient.Chat(cctx, sys, sb.String())
	if err != nil {
		return
	}
	out = stripFence(out)
	if i, j := strings.Index(out, "{"), strings.LastIndex(out, "}"); i >= 0 && j > i {
		out = out[i : j+1]
	}
	if !json.Valid([]byte(out)) {
		return
	}
	a.gdb.Exec(`INSERT INTO user_column_digest(user_id,market,sector,digest_date,digest,generated_at)
		VALUES(?,?,?,current_date,?::jsonb,now())
		ON CONFLICT(user_id,market,sector,digest_date) DO UPDATE SET digest=EXCLUDED.digest, generated_at=now()`,
		uid, market, sector, out)
}

type sectorNewsRow struct {
	ID    int64
	Title string
	Body  string
}

// sectorNews 当日与板块相关的新闻(标题/正文命中板块词)。
func (a *API) sectorNews(market, sector string, limit int) []sectorNewsRow {
	var rows []sectorNewsRow
	a.gdb.Raw(`SELECT id, title, COALESCE(body,'') AS body FROM news_items
		WHERE market=? AND published_at::date = (SELECT max(published_at::date) FROM news_items WHERE market=?)
		AND (title LIKE ? OR body LIKE ?) ORDER BY published_at DESC LIMIT ?`,
		market, market, "%"+sector+"%", "%"+sector+"%", limit).Scan(&rows)
	return rows
}

// newsFeed 可点新闻列表(综合=近期宏观;板块=命中板块词)。GET /api/news/feed?market=cn&sector=半导体
func (a *API) newsFeed(w http.ResponseWriter, r *http.Request) {
	market := mktParam(r)
	sector := strings.TrimSpace(r.URL.Query().Get("sector"))
	type feedRow struct {
		ID        int64  `json:"id"`
		Title     string `json:"title"`
		Source    string `json:"source"`
		URL       string `json:"url"`
		Published string `json:"published"`
	}
	var rows []feedRow
	if sector == "" {
		a.gdb.Raw(`SELECT id, title, source, url, to_char(published_at AT TIME ZONE 'Asia/Shanghai','YYYY-MM-DD HH24:MI') AS published FROM news_items
			WHERE market=? AND ticker IS NULL ORDER BY published_at DESC NULLS LAST LIMIT 40`, market).Scan(&rows)
	} else {
		a.gdb.Raw(`SELECT id, title, source, url, to_char(published_at AT TIME ZONE 'Asia/Shanghai','YYYY-MM-DD HH24:MI') AS published FROM news_items
			WHERE market=? AND (title LIKE ? OR body LIKE ?) ORDER BY published_at DESC NULLS LAST LIMIT 40`,
			market, "%"+sector+"%", "%"+sector+"%").Scan(&rows)
	}
	writeJSON(w, http.StatusOK, map[string]any{"feed": rows})
}
