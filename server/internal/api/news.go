package api

import (
	"context"
	"crypto/md5"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

const newsInterpretSys = `你是资深财经分析师,面向A股投资者解读一条新闻。给你标题+摘要(可能很短),用你的常识把这条新闻【展开解读】。输出一段 HTML 片段(不要 <html>/<body>/代码围栏)。
分区(用 <h4> 小标题):
① 发生了什么 —— 把这条新闻讲清楚(标题若太简,用你掌握的背景补全来龙去脉;不确定的地方标注"(需核实)",绝不编造具体数字)。
② 对A股意味着什么 —— 涉及哪些板块/主题?利好还是利空?是否有提前/滞后的传导(如海外隔夜事件A股次日反应)?
③ 需要关注什么 —— 后续要盯的点。
【时间基准】新闻均为近日发生。用户消息会给出【当前日期】,一切时间判断以它为准;绝不臆断为往年(如不要写"2024年"),涉及年份直接用当前日期的年份。
【硬要求】<h4>+<p>/<ul><li>,关键处 <b>,不写 CSS,中文,250字内。结尾 <p class="disc">AI 依常识解读,非实时核实,非投资建议。</p>
另外:在解读之外,单独一行输出 <!--SECTORS:板块1,板块2--> (涉及的A股板块,逗号分隔,2-5个),供系统标注。`

// news.go — 新闻模块只读 API(独立 overlay,绝不碰策略端点)。
// 读写分工:Python engine/news 写表,Go 只读展示。全部 market-scoped。

// newsDigest 今日金融要闻日报。GET /api/news/digest?market=cn
func (a *API) newsDigest(w http.ResponseWriter, r *http.Request) {
	market := mktParam(r)
	var digestDate, digest string
	var nSource int
	err := a.gdb.Raw(`SELECT digest_date::text, digest::text, n_source
		FROM news_digest WHERE market=? ORDER BY digest_date DESC LIMIT 1`, market).Row().
		Scan(&digestDate, &digest, &nSource)
	if err != nil || digest == "" {
		writeJSON(w, http.StatusOK, map[string]any{"digest": nil, "note": "暂无日报(采集/生成后可见)"})
		return
	}
	// digest 是 JSON 文本,前端 JSON.parse;这里原样字符串返回
	writeJSON(w, http.StatusOK, map[string]any{
		"digest_date": digestDate, "digest": digest, "n_source": nSource,
	})
}

// newsStock 个股相关新闻 + 叙事关键词 + 信号旗。GET /api/news/stock?ticker=&market=cn&refresh=1
// 只 A股(新闻源为 akshare/中文);refresh=1 时先触发采集+关联+关键词(懒加载,类似 investigate)。
func (a *API) newsStock(w http.ResponseWriter, r *http.Request) {
	market := mktParam(r)
	tk := normTicker(market, r.URL.Query().Get("ticker"))
	if tk == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker"})
		return
	}
	if market != "cn" {
		writeJSON(w, http.StatusOK, map[string]any{"ticker": tk, "news": []any{}, "keywords": nil,
			"note": "个股新闻目前仅 A股(数据源为中文财经)"})
		return
	}
	code := strings.TrimPrefix(strings.TrimPrefix(strings.TrimPrefix(tk, "sh."), "sz."), "bj.")

	// refresh:同步触发采集(个股新闻+公告)+ 关联 + 关键词(~10-30s)
	if r.URL.Query().Get("refresh") == "1" {
		_, _ = a.runner.RunPython("news/news_collector.py", []string{"--stocks", code}, 60*time.Second)
		_, _ = a.runner.RunPython("news/news_link.py", []string{"--backfill-days", "3"}, 60*time.Second)
		_, _ = a.runner.RunPython("news/news_keywords.py", []string{"--ticker", tk, "--days", "60"}, 90*time.Second)
	}

	// 关联新闻(个股新闻 + 命中的宏观关联),按时间倒序
	type newsRow struct {
		ID        int64  `json:"id"`
		Title     string `json:"title"`
		Source    string `json:"source"`
		URL       string `json:"url"`
		Published string `json:"published"`
		Relation  string `json:"relation"`
	}
	var news []newsRow
	a.gdb.Raw(`
		SELECT id, title, source, url, to_char(published_at AT TIME ZONE 'Asia/Shanghai','YYYY-MM-DD HH24:MI') AS published, 'company' AS relation
		FROM news_items WHERE ticker=$1
		UNION ALL
		SELECT n.id, n.title, n.source, n.url, to_char(n.published_at AT TIME ZONE 'Asia/Shanghai','YYYY-MM-DD HH24:MI'), sn.relation
		FROM stock_news sn JOIN news_items n ON n.id=sn.news_id
		WHERE sn.market=$2 AND sn.ticker=$1
		ORDER BY published DESC NULLS LAST LIMIT 30`, tk, market).Scan(&news)

	// 叙事关键词(最新一期)
	var kwJSON, summary string
	a.gdb.Raw(`SELECT keywords::text, summary FROM stock_keywords WHERE market=? AND ticker=? ORDER BY asof DESC LIMIT 1`,
		market, tk).Row().Scan(&kwJSON, &summary)

	// 信号旗(SQL 复刻 news_signals:近30天公告)——诚实定位,非 alpha
	flags := a.newsStockFlags(market, tk)

	writeJSON(w, http.StatusOK, map[string]any{
		"ticker": tk, "news": news, "keywords_json": kwJSON, "summary": summary, "flags": flags,
		"disclaimer": "资讯/关注/风险提示,非买入卖出建议,非收益预测(新闻对A股无强可交易alpha)",
	})
}

// newsStockFlags 诚实信号旗(近30天公告标题匹配):attention/avoid_risk/vol_warn。
func (a *API) newsStockFlags(market, tk string) []map[string]string {
	flags := []map[string]string{}
	type annRow struct {
		Title   string
		AnnDate string
	}
	var pos, neg []annRow
	a.gdb.Raw(`SELECT title, ann_date::text AS ann_date FROM stock_announcements
		WHERE market=? AND ticker=? AND ann_date >= current_date - 30
		  AND (title LIKE '%预增%' OR title LIKE '%扭亏%' OR (title LIKE '%业绩预告%' AND title LIKE '%增%'))
		ORDER BY ann_date DESC LIMIT 2`, market, tk).Scan(&pos)
	for _, p := range pos {
		flags = append(flags, map[string]string{"type": "attention", "level": "info",
			"text": "业绩正惊喜(关注):" + trunc(p.Title, 34), "basis": p.AnnDate + " 公告",
			"note": "rev+PEAD 温和正漂移(size中性);非买入建议"})
	}
	a.gdb.Raw(`SELECT title, ann_date::text AS ann_date FROM stock_announcements
		WHERE market=? AND ticker=? AND ann_date >= current_date - 30
		  AND (title LIKE '%减持%' OR title LIKE '%预减%' OR title LIKE '%首亏%' OR title LIKE '%风险警示%'
		       OR title LIKE '%立案%' OR title LIKE '%处罚%')
		ORDER BY ann_date DESC LIMIT 2`, market, tk).Scan(&neg)
	for _, n := range neg {
		flags = append(flags, map[string]string{"type": "avoid_risk", "level": "warn",
			"text": "利空/风险事件(回避):" + trunc(n.Title, 34), "basis": n.AnnDate + " 公告",
			"note": "负惊喜/资金流出稳健负漂移;持有者关注回避"})
	}
	var nEvt int
	a.gdb.Raw(`SELECT count(*) FROM stock_announcements WHERE market=? AND ticker=? AND ann_date >= current_date - 20 AND is_signal`,
		market, tk).Row().Scan(&nEvt)
	if nEvt > 0 {
		flags = append(flags, map[string]string{"type": "vol_warn", "level": "info",
			"text": "近期有信号事件 → 波动可能加大", "basis": "近20天", "note": "有事件的股前向波动约45% vs 无事件35%"})
	}
	return flags
}

// newsCalendar 未来事件日历(财报/宏观)。GET /api/news/calendar?market=cn
func (a *API) newsCalendar(w http.ResponseWriter, r *http.Request) {
	market := mktParam(r)
	type evRow struct {
		EventDate  string `json:"event_date"`
		Category   string `json:"category"`
		Title      string `json:"title"`
		Importance int    `json:"importance"`
	}
	var evs []evRow
	a.gdb.Raw(`SELECT event_date::text AS event_date, category, title, importance
		FROM event_calendar WHERE market=? AND event_date >= current_date
		ORDER BY event_date, importance DESC LIMIT 60`, market).Scan(&evs)
	writeJSON(w, http.StatusOK, map[string]any{"calendar": evs})
}

// newsItem 单条新闻详情 + AI 解读。GET /api/news/item?id=&force=1
func (a *API) newsItem(w http.ResponseWriter, r *http.Request) {
	id := r.URL.Query().Get("id")
	if id == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 id"})
		return
	}
	var title, body, url, source, published, interpret string
	err := a.gdb.Raw(`SELECT title, body, url, source, to_char(published_at AT TIME ZONE 'Asia/Shanghai','YYYY-MM-DD HH24:MI'), COALESCE(ai_interpret,'')
		FROM news_items WHERE id=?`, id).Row().Scan(&title, &body, &url, &source, &published, &interpret)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "无此新闻"})
		return
	}
	// 懒生成解读(缓存;force 重生成)
	if (interpret == "" || r.URL.Query().Get("force") == "1") && a.aiClient != nil && a.aiClient.Enabled() {
		user := fmt.Sprintf("【当前日期】%s\n标题:%s\n摘要:%s\n来源:%s", todayCN(), title, body, source)
		ctx, cancel := context.WithTimeout(r.Context(), 60*time.Second)
		defer cancel()
		out, e := a.aiClient.Chat(ctx, newsInterpretSys, user)
		if e != nil {
			// AI 失败(如余额不足)→ 优雅降级:仍返回新闻+来源,不阻断
			writeJSON(w, http.StatusOK, map[string]any{
				"title": title, "body": body, "url": url, "source": source, "published": published,
				"interpret": "", "sectors": []string{}, "ai_error": e.Error(),
			})
			return
		}
		if out != "" {
			out = stripFence(out)
			secStr := strings.Join(extractSectors(out), ",")
			out = stripSectorMarker(out)
			interpret = out
			a.gdb.Exec(`UPDATE news_items SET ai_interpret=?, ai_sectors=string_to_array(?, ',') WHERE id=?`, out, secStr, id)
		}
	}
	var secStr string
	a.gdb.Raw(`SELECT COALESCE(array_to_string(ai_sectors, ','),'') FROM news_items WHERE id=?`, id).Row().Scan(&secStr)
	sectors := []string{}
	if secStr != "" {
		sectors = strings.Split(secStr, ",")
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"title": title, "body": body, "url": url, "source": source, "published": published,
		"interpret": interpret, "sectors": sectors,
	})
}

const eventInterpretSys = `你是资深财经分析师,面向A股投资者【深度解读】一则宏观/时政大事。给你【事件标题】和【初步影响判断】,用你的常识把它展开。输出一段 HTML 片段(不要 <html>/<body>/代码围栏)。
分区(用 <h4> 小标题):
① 事件是什么 —— 讲清来龙去脉、背景与关键事实(标题若太简,用你掌握的背景补全;不确定处标"(需核实)",绝不编造具体数字)。
② 对A股意味着什么 —— 传导路径:涉及哪些板块/主题?利好还是利空?海外事件对A股是否有提前/滞后反应(如隔夜事件次日反应)?哪些行业弹性最大?
③ 需要关注什么 —— 后续要盯的信号、关键时间节点、风险点。
【时间基准】事件均为近日发生。用户消息会给出【当前日期】,一切时间判断以它为准;绝不臆断为往年(如不要写"2024年"),涉及年份直接用当前日期的年份。
【硬要求】<h4>+<p>/<ul><li>,关键处 <b>,不写 CSS,中文,300字内。结尾 <p class="disc">AI 依常识解读,非实时核实,非投资建议。</p>
另外:单独一行输出 <!--SECTORS:板块1,板块2--> (涉及的A股板块,逗号分隔,2-5个),供系统标注。`

// newsEventInterpret 宏观「世界大事/国内大事」条目的按需 AI 深度解读(缓存)。POST /api/news/event-interpret
func (a *API) newsEventInterpret(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Title   string `json:"title"`
		Context string `json:"context"`
		Market  string `json:"market"`
		Force   bool   `json:"force"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || strings.TrimSpace(req.Title) == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 title"})
		return
	}
	market := req.Market
	if market == "" {
		market = "cn"
	}
	key := fmt.Sprintf("%x", md5.Sum([]byte(req.Title)))
	var interpret, secStr string
	a.gdb.Raw(`SELECT interpret, sectors FROM event_interpret WHERE market=? AND event_key=?`, market, key).Row().Scan(&interpret, &secStr)
	if (interpret == "" || req.Force) && a.aiClient != nil && a.aiClient.Enabled() {
		user := fmt.Sprintf("【当前日期】%s\n事件标题:%s\n初步影响判断:%s", todayCN(), req.Title, req.Context)
		ctx, cancel := context.WithTimeout(r.Context(), 60*time.Second)
		defer cancel()
		out, e := a.aiClient.Chat(ctx, eventInterpretSys, user)
		if e != nil {
			writeJSON(w, http.StatusOK, map[string]any{"interpret": "", "sectors": []string{}, "ai_error": e.Error()})
			return
		}
		if out != "" {
			out = stripFence(out)
			secStr = strings.Join(extractSectors(out), ",")
			out = stripSectorMarker(out)
			interpret = out
			a.gdb.Exec(`INSERT INTO event_interpret (market, event_key, interpret, sectors) VALUES (?,?,?,?)
				ON CONFLICT (market, event_key) DO UPDATE SET interpret=EXCLUDED.interpret, sectors=EXCLUDED.sectors, created_at=now()`,
				market, key, interpret, secStr)
		}
	}
	sectors := []string{}
	if secStr != "" {
		sectors = strings.Split(secStr, ",")
	}
	writeJSON(w, http.StatusOK, map[string]any{"interpret": interpret, "sectors": sectors})
}

func stripFence(s string) string {
	s = strings.TrimSpace(s)
	if strings.HasPrefix(s, "```") {
		if i := strings.IndexByte(s, '\n'); i >= 0 {
			s = s[i+1:]
		}
		s = strings.TrimSuffix(strings.TrimSpace(s), "```")
	}
	return strings.TrimSpace(s)
}

func extractSectors(s string) []string {
	i := strings.Index(s, "<!--SECTORS:")
	if i < 0 {
		return nil
	}
	rest := s[i+len("<!--SECTORS:"):]
	j := strings.Index(rest, "-->")
	if j < 0 {
		return nil
	}
	var out []string
	for _, x := range strings.Split(rest[:j], ",") {
		if x = strings.TrimSpace(x); x != "" {
			out = append(out, x)
		}
	}
	return out
}

func stripSectorMarker(s string) string {
	i := strings.Index(s, "<!--SECTORS:")
	if i < 0 {
		return s
	}
	j := strings.Index(s[i:], "-->")
	if j < 0 {
		return s[:i]
	}
	return strings.TrimSpace(s[:i] + s[i+j+3:])
}

// 当前北京日期,注入 AI 解读 prompt 作时间基准(否则 DeepSeek 会臆断为训练期年份如2024)
func todayCN() string {
	return time.Now().In(time.FixedZone("CST", 8*3600)).Format("2006年01月02日")
}

func trunc(s string, n int) string {
	r := []rune(s)
	if len(r) > n {
		return string(r[:n]) + "…"
	}
	return s
}
