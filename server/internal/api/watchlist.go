package api

import (
	"net/http"

	"sentinel/internal/auth"
)

// watchlist(按用户隔离): GET 列表 / POST ?ticker=&source= 加 / DELETE ?ticker= 删。
func (a *API) watchlist(w http.ResponseWriter, r *http.Request) {
	uid := auth.UserID(r)
	switch r.Method {
	case http.MethodGet:
		type row struct {
			Ticker string `json:"ticker"`
			Source string `json:"source"`
		}
		var rows []row
		a.gdb.Raw(`SELECT ticker, source FROM watchlist WHERE user_id=? ORDER BY added_at DESC`, uid).Scan(&rows)
		writeJSON(w, http.StatusOK, map[string]any{"watchlist": rows})
	case http.MethodPost:
		tk := r.URL.Query().Get("ticker")
		if tk == "" {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker"})
			return
		}
		src := r.URL.Query().Get("source")
		if src == "" {
			src = "ai"
		}
		a.gdb.Exec(`INSERT INTO watchlist(user_id,ticker,source) VALUES (?,?,?) ON CONFLICT (user_id,ticker) DO NOTHING`, uid, tk, src)
		writeJSON(w, http.StatusOK, map[string]string{"status": "added", "ticker": tk})
	case http.MethodDelete:
		tk := r.URL.Query().Get("ticker")
		a.gdb.Exec(`DELETE FROM watchlist WHERE user_id=? AND ticker=?`, uid, tk)
		writeJSON(w, http.StatusOK, map[string]string{"status": "removed", "ticker": tk})
	default:
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "GET/POST/DELETE"})
	}
}
