package api

import (
	"net/http"
	"strings"
	"time"
)

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
		Title     string `json:"title"`
		Source    string `json:"source"`
		URL       string `json:"url"`
		Published string `json:"published"`
		Relation  string `json:"relation"`
	}
	var news []newsRow
	a.gdb.Raw(`
		SELECT title, source, url, published_at::text AS published, 'company' AS relation
		FROM news_items WHERE ticker=$1
		UNION ALL
		SELECT n.title, n.source, n.url, n.published_at::text, sn.relation
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

func trunc(s string, n int) string {
	r := []rune(s)
	if len(r) > n {
		return string(r[:n]) + "…"
	}
	return s
}
