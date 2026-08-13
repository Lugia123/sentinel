package api

import (
	"encoding/json"
	"net/http"
	"strings"

	"sentinel/internal/datasource"
)

// datasourceCfg 管理员维护数据源凭证(tushare:接口地址 + api key)。
// GET 读当前(token 只回打码,不回显明文);PUT 保存(token 留空=不改)。保存即热生效(注入进程 env)。
func (a *API) datasourceCfg(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPut {
		var body datasource.Tushare
		if json.NewDecoder(r.Body).Decode(&body) != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "请求体格式错误"})
			return
		}
		if u := strings.TrimSpace(body.URL); u != "" && !strings.HasPrefix(u, "http://") && !strings.HasPrefix(u, "https://") {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "接口地址须以 http:// 或 https:// 开头"})
			return
		}
		if err := datasource.Save(a.store, body); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
	}
	cur := datasource.Load(a.store)
	urlSrc, tokenSrc := datasource.Source(a.store)
	writeJSON(w, http.StatusOK, map[string]any{
		"tushare": map[string]any{
			"url":          cur.URL,
			"token_masked": datasource.Mask(cur.Token),
			"has_token":    cur.Token != "",
			"url_source":   urlSrc,
			"token_source": tokenSrc,
		},
		"enabled":     cur.Enabled(),
		"default_url": datasource.DefaultTSURL,
		"note":        "tushare 供 A股 事件/红利/资金流腿;月卡 token 过期后这些腿会停更(顶部红条报警),美股与 A股行情腿不受影响。",
	})
}

// datasourceTest 用页面上的值(token 留空则用已保存的)真打一次 tushare,验证 host+token。
func (a *API) datasourceTest(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "仅支持 POST"})
		return
	}
	var body datasource.Tushare
	if json.NewDecoder(r.Body).Decode(&body) != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "请求体格式错误"})
		return
	}
	cur := datasource.Load(a.store)
	c := datasource.Tushare{URL: strings.TrimSpace(body.URL), Token: strings.TrimSpace(body.Token)}
	if c.URL == "" {
		c.URL = cur.URL
	}
	if c.Token == "" {
		c.Token = cur.Token // 未改动 token 时用已保存的测
	}
	msg, err := datasource.Test(c)
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"ok": false, "error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "note": msg})
}
