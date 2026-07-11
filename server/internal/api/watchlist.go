package api

import (
	"net/http"
	"strings"

	"sentinel/internal/auth"
)

// normTicker 规范化代码:美股大写(aapl→AAPL);A股保持小写前缀格式(SH.600000→sh.600000)。
func normTicker(market, tk string) string {
	tk = strings.TrimSpace(tk)
	if market == "cn" {
		return strings.ToLower(tk)
	}
	return strings.ToUpper(tk)
}

// watchlist GET:该用户当前市场的关注★ + 自定义追踪股(带 starred/custom 标记,两者独立)。
func (a *API) watchlist(w http.ResponseWriter, r *http.Request) {
	uid := auth.UserID(r)
	type row struct {
		Ticker  string `json:"ticker"`
		Starred bool   `json:"starred"`
		Custom  bool   `json:"custom"`
	}
	var rows []row
	a.gdb.Raw(`SELECT ticker, starred, custom FROM watchlist WHERE user_id=? AND market=? AND (starred OR custom) ORDER BY ticker`,
		uid, mktParam(r)).Scan(&rows)
	writeJSON(w, http.StatusOK, map[string]any{"watchlist": rows})
}

// watchStar POST ?ticker=&on=1|0 — 关注/取消关注(不影响自定义追踪)。
func (a *API) watchStar(w http.ResponseWriter, r *http.Request) {
	uid := auth.UserID(r)
	mkt := mktParam(r)
	tk := normTicker(mkt, r.URL.Query().Get("ticker"))
	if tk == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker"})
		return
	}
	if r.URL.Query().Get("on") != "0" {
		a.gdb.Exec(`INSERT INTO watchlist(user_id,market,ticker,starred) VALUES(?,?,?,true)
			ON CONFLICT(user_id,market,ticker) DO UPDATE SET starred=true`, uid, mkt, tk)
	} else {
		a.gdb.Exec(`UPDATE watchlist SET starred=false WHERE user_id=? AND market=? AND ticker=?`, uid, mkt, tk)
		a.gdb.Exec(`DELETE FROM watchlist WHERE user_id=? AND market=? AND ticker=? AND NOT starred AND NOT custom`, uid, mkt, tk)
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "ticker": tk})
}

// watchCustom POST ?ticker= 加自定义追踪股(不关注;同步预热档位使其可用);DELETE ?ticker= 移除。
func (a *API) watchCustom(w http.ResponseWriter, r *http.Request) {
	uid := auth.UserID(r)
	mkt := mktParam(r)
	tk := normTicker(mkt, r.URL.Query().Get("ticker"))
	if tk == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker"})
		return
	}
	switch r.Method {
	case http.MethodPost:
		// 同步预热 focus(~3秒):跑得出才入库,顺便让快照能立刻显示(不再阻塞后续页面加载)
		if h := a.warmFocus(uid, mkt, tk, a.latestAsof(mkt)); h == nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": tk + " 不在数据池,无法追踪"})
			return
		}
		a.gdb.Exec(`INSERT INTO watchlist(user_id,market,ticker,custom) VALUES(?,?,?,true)
			ON CONFLICT(user_id,market,ticker) DO UPDATE SET custom=true`, uid, mkt, tk)
		writeJSON(w, http.StatusOK, map[string]any{"ok": true, "ticker": tk})
	case http.MethodDelete:
		a.gdb.Exec(`UPDATE watchlist SET custom=false WHERE user_id=? AND market=? AND ticker=?`, uid, mkt, tk)
		a.gdb.Exec(`DELETE FROM watchlist WHERE user_id=? AND market=? AND ticker=? AND NOT starred AND NOT custom`, uid, mkt, tk)
		writeJSON(w, http.StatusOK, map[string]any{"ok": true, "ticker": tk})
	default:
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "POST/DELETE"})
	}
}
