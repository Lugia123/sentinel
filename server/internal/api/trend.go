package api

import (
	"net/http"
	"strings"
)

// trend 历史分析走势(从回填快照的 raw JSONB 里挖多维序列):
//   ?ticker=X 或 ?tickers=X,Y,Z  → {series:{TK:[{date,grade,median20,mom21,vol,pct_from_high,bandwidth,price,sy}]}}
//   兼容旧单股:?ticker=X 也返回 points(= series[X])。
//   可选 ?from=&to=(YYYY-MM-DD)
func (a *API) trend(w http.ResponseWriter, r *http.Request) {
	from := q(r, "from", "2000-01-01")
	to := q(r, "to", "2100-01-01")
	market := mktParam(r)

	var tickers []string
	if multi := r.URL.Query().Get("tickers"); multi != "" {
		for _, tk := range strings.Split(multi, ",") {
			if tk = normTicker(market, tk); tk != "" {
				tickers = append(tickers, tk)
			}
		}
	} else if tk := normTicker(market, r.URL.Query().Get("ticker")); tk != "" {
		tickers = append(tickers, tk)
	}
	if len(tickers) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker 或 tickers"})
		return
	}

	series := map[string]any{}
	for _, tk := range tickers {
		series[tk] = a.richSeries(market, tk, from, to)
	}
	out := map[string]any{"series": series}
	if len(tickers) == 1 { // 兼容旧单股调用
		out["ticker"] = tickers[0]
		out["points"] = series[tickers[0]]
	}
	writeJSON(w, http.StatusOK, out)
}

// richSeries 从 snapshots.raw 的 holdings 数组里,按 ticker 抽取每个交易日的多维指标。
func (a *API) richSeries(market, tk, from, to string) []map[string]any {
	type row struct {
		Date        string   `json:"date"`
		Grade       *int     `json:"grade"`
		Median20    *float64 `json:"median20"`
		Mom21       *float64 `json:"mom21"`
		Mom126      *float64 `json:"mom126"`
		Vol         *float64 `json:"vol"`
		PctFromHigh *float64 `json:"pct_from_high"`
		Bandwidth   *float64 `json:"bandwidth"`
		Price       *float64 `json:"price"`
		Sma20       *float64 `json:"sma20"`
		Sma50       *float64 `json:"sma50"`
		Sy          *float64 `json:"sy"`
	}
	var rows []row
	a.gdb.Raw(`
		SELECT s.asof::text AS date,
		       (elem->>'grade')::int                                   AS grade,
		       (elem->'prob'->'h20'->>'median')::float                 AS median20,
		       (elem->'indicators'->>'mom21')::float                   AS mom21,
		       (elem->'indicators'->>'mom126')::float                  AS mom126,
		       (elem->'indicators'->>'vol_annual')::float              AS vol,
		       (elem->'indicators'->>'pct_from_high')::float           AS pct_from_high,
		       ((elem->'prob'->'h20'->'band70'->>1)::float
		        - (elem->'prob'->'h20'->'band70'->>0)::float)          AS bandwidth,
		       (elem->>'price')::float                                 AS price,
		       (elem->'indicators'->>'sma20')::float                   AS sma20,
		       (elem->'indicators'->>'sma50')::float                   AS sma50,
		       (elem->'indicators'->>'sy_yield')::float                AS sy
		FROM snapshots s, jsonb_array_elements(s.raw->'holdings') elem
		WHERE s.market = ? AND elem->>'ticker' = ? AND s.asof BETWEEN ?::date AND ?::date
		ORDER BY s.asof`, market, tk, from, to).Scan(&rows)
	out := make([]map[string]any, len(rows))
	for i, r := range rows {
		out[i] = map[string]any{
			"date": r.Date, "grade": r.Grade, "median20": r.Median20,
			"mom21": r.Mom21, "mom126": r.Mom126, "vol": r.Vol,
			"pct_from_high": r.PctFromHigh, "bandwidth": r.Bandwidth,
			"price": r.Price, "sma20": r.Sma20, "sma50": r.Sma50, "sy": r.Sy,
		}
	}
	return out
}

// trendTickers 列出当前市场所有【有档位历史】的股票(供走势页多选下拉),带中文名+样本数。
// A股中文名从 universe.csv 取(name 字段);美股前端自查 ticker_meta 映射。
func (a *API) trendTickers(w http.ResponseWriter, r *http.Request) {
	market := mktParam(r)
	type trow struct {
		Ticker string `json:"ticker"`
		N      int    `json:"n"`
	}
	var rows []trow
	a.gdb.Raw(`
		SELECT ticker, COUNT(*) AS n FROM holdings WHERE market = ?
		GROUP BY ticker ORDER BY n DESC, ticker`, market).Scan(&rows)
	var names map[string]string
	if market == "cn" {
		names = a.cnNameMap()
	}
	out := make([]map[string]any, len(rows))
	for i, r := range rows {
		item := map[string]any{"ticker": r.Ticker, "n": r.N}
		if nm := names[r.Ticker]; nm != "" {
			item["name"] = nm
		}
		out[i] = item
	}
	writeJSON(w, http.StatusOK, map[string]any{"tickers": out})
}
