package api

import (
	"net/http"
)

// riskHistory 返回某市场近 N 天风险灯历史(asof / 等级 / 暴露 / 宽度 / 拥挤度 / 成交额比 / 背离),
// 供前端画风险灯趋势。数据从 snapshots.raw 的 risk_light 提取(每日一条,天然有历史)。
func (a *API) riskHistory(w http.ResponseWriter, r *http.Request) {
	market := mktParam(r)
	type row struct {
		Asof      string   `json:"asof"`
		Level     string   `json:"level"`
		Exposure  float64  `json:"exposure"`
		Breadth   *float64 `json:"breadth"`
		BreadthMA *float64 `json:"breadth_ma"`
		Crowd     *float64 `json:"crowd"`
		AmtRatio  *float64 `json:"amount_ratio"`
		SpyVol    *float64 `json:"spy_vol"`
		Diverge   *bool    `json:"diverge"`
	}
	var rows []row
	// UNION:回补历史(risk_light_history)+ 每日live(snapshots.raw);同 asof 取 live(pri高)。
	// A股:宽度/宽度MA/拥挤/成交额比/背离;美股:spy_vol。
	a.gdb.Raw(`
		SELECT asof::text AS asof, level, exposure, breadth, breadth_ma, crowd, amt_ratio, spy_vol, diverge FROM (
		  SELECT DISTINCT ON (asof) asof, level, exposure, breadth, breadth_ma, crowd, amt_ratio, spy_vol, diverge
		  FROM (
		    -- 回补表(字段完整,含breadth_ma;A股值与快照一致)优先;快照补回补未覆盖的近日
		    SELECT asof, level, exposure, breadth, breadth_ma, crowd, amount_ratio AS amt_ratio, spy_vol, diverge, 2 AS pri
		    FROM risk_light_history WHERE market=?
		    UNION ALL
		    SELECT asof, risk_level AS level, exposure,
		           (raw::json->'risk_light'->>'bench_breadth')::float8 AS breadth,
		           (raw::json->'risk_light'->>'breadth_ma')::float8    AS breadth_ma,
		           (raw::json->'risk_light'->>'crowd_pct')::float8     AS crowd,
		           (raw::json->'risk_light'->>'amount_ratio')::float8  AS amt_ratio,
		           (raw::json->'risk_light'->>'spy_vol')::float8       AS spy_vol,
		           (raw::json->'risk_light'->>'diverge')::bool         AS diverge, 1 AS pri
		    FROM snapshots WHERE market=?
		  ) u ORDER BY asof, pri DESC
		) d ORDER BY asof DESC LIMIT 800`, market, market).Scan(&rows)
	writeJSON(w, http.StatusOK, map[string]any{"market": market, "history": rows})
}
