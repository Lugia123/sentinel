package api

import "net/http"

// watchlist: GET 列表 / POST ?ticker=&source= 加 / DELETE ?ticker= 删。
func (a *API) watchlist(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		type row struct {
			Ticker string `json:"ticker"`
			Source string `json:"source"`
		}
		var rows []row
		a.gdb.Raw(`SELECT ticker, source FROM watchlist ORDER BY added_at DESC`).Scan(&rows)
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
		a.gdb.Exec(`INSERT INTO watchlist(ticker,source) VALUES (?,?) ON CONFLICT (ticker) DO NOTHING`, tk, src)
		writeJSON(w, http.StatusOK, map[string]string{"status": "added", "ticker": tk})
	case http.MethodDelete:
		tk := r.URL.Query().Get("ticker")
		a.gdb.Exec(`DELETE FROM watchlist WHERE ticker=?`, tk)
		writeJSON(w, http.StatusOK, map[string]string{"status": "removed", "ticker": tk})
	default:
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "GET/POST/DELETE"})
	}
}
