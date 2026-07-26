package api

import (
	"net/http"
)

// riskHistory 返回某市场近 N 天风险灯历史(asof / 等级 / 暴露 / 宽度 / 拥挤度 / 成交额比 / 背离),
// 供前端画风险灯趋势。数据从 snapshots.raw 的 risk_light 提取(每日一条,天然有历史)。
func (a *API) riskHistory(w http.ResponseWriter, r *http.Request) {
	market := mktParam(r)
	type row struct {
		Asof     string   `json:"asof"`
		Level    string   `json:"level"`
		Exposure float64  `json:"exposure"`
		Breadth  *float64 `json:"breadth"`
		Crowd    *float64 `json:"crowd"`
		AmtRatio *float64 `json:"amount_ratio"`
		SpyVol   *float64 `json:"spy_vol"`
		Diverge  *bool    `json:"diverge"`
	}
	var rows []row
	// A股:宽度/拥挤度/成交额比/背离;美股:spy_vol。都从 raw 取,缺则 null。
	a.gdb.Raw(`
		SELECT asof::text AS asof,
		       risk_level AS level,
		       exposure,
		       (raw::json->'risk_light'->>'bench_breadth')::float8 AS breadth,
		       (raw::json->'risk_light'->>'crowd_pct')::float8     AS crowd,
		       (raw::json->'risk_light'->>'amount_ratio')::float8  AS amt_ratio,
		       (raw::json->'risk_light'->>'spy_vol')::float8       AS spy_vol,
		       (raw::json->'risk_light'->>'diverge')::bool         AS diverge
		FROM snapshots WHERE market=? ORDER BY asof DESC LIMIT 60`, market).Scan(&rows)
	writeJSON(w, http.StatusOK, map[string]any{"market": market, "history": rows})
}
