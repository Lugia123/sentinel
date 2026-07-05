package api

import (
	"net/http"
	"strings"
)

// trend 历史分析走势(从回填的 holdings 查):
//   ?ticker=X            → 单股全指标序列 [{date,grade,price,median20}]
//   ?tickers=X,Y,Z       → 多股档位序列对比 {ticker:[{date,grade}]}
//   可选 ?from=&to=(YYYY-MM-DD)
func (a *API) trend(w http.ResponseWriter, r *http.Request) {
	from := q(r, "from", "2000-01-01")
	to := q(r, "to", "2100-01-01")

	if multi := r.URL.Query().Get("tickers"); multi != "" {
		out := map[string]any{}
		for _, tk := range strings.Split(multi, ",") {
			tk = strings.TrimSpace(strings.ToUpper(tk))
			if tk == "" {
				continue
			}
			out[tk] = a.gradeSeries(tk, from, to)
		}
		writeJSON(w, http.StatusOK, map[string]any{"series": out})
		return
	}

	tk := strings.ToUpper(r.URL.Query().Get("ticker"))
	if tk == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker 或 tickers"})
		return
	}
	type pt struct {
		Date     string   `json:"date"`
		Grade    int      `json:"grade"`
		Price    float64  `json:"price"`
		Median20 *float64 `json:"median20"`
	}
	var rows []pt
	a.gdb.Raw(`
		SELECT s.asof::text AS date, h.grade, h.price, (h.prob->'h20'->>'median')::float AS median20
		FROM holdings h JOIN snapshots s ON s.id = h.snapshot_id
		WHERE h.ticker = ? AND s.asof BETWEEN ?::date AND ?::date
		ORDER BY s.asof`, tk, from, to).Scan(&rows)
	writeJSON(w, http.StatusOK, map[string]any{"ticker": tk, "points": rows})
}

func (a *API) gradeSeries(tk, from, to string) []map[string]any {
	type gp struct {
		Date  string `json:"date"`
		Grade int    `json:"grade"`
	}
	var rows []gp
	a.gdb.Raw(`
		SELECT s.asof::text AS date, h.grade FROM holdings h JOIN snapshots s ON s.id = h.snapshot_id
		WHERE h.ticker = ? AND s.asof BETWEEN ?::date AND ?::date ORDER BY s.asof`, tk, from, to).Scan(&rows)
	out := make([]map[string]any, len(rows))
	for i, r := range rows {
		out[i] = map[string]any{"date": r.Date, "grade": r.Grade}
	}
	return out
}
