package api

import (
	"encoding/json"
	"net/http"

	"sentinel/internal/auth"
)

// allocateHandler AI 分配建议股数。POST body: {tickers:[...], capital?:number}
// (均分/风险平价为确定性,前端直接算;此接口只做 AI 模式。)
func (a *API) allocateHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "用 POST"})
		return
	}
	var body struct {
		Tickers []string `json:"tickers"`
		Capital float64  `json:"capital"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	res, err := a.alloc.AIAllocate(r.Context(), auth.UserID(r), mktParam(r), body.Tickers, body.Capital)
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, res)
}
