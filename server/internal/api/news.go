package api

import (
	"net/http"
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
