// Package api — Sentinel HTTP 路由与处理器(stdlib net/http,零外部 web 依赖)。
package api

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"

	"gorm.io/gorm"

	"sentinel/internal/engine"
	"sentinel/internal/explain"
	"sentinel/internal/portfolio"
	"sentinel/internal/store"
	"sentinel/internal/version"
)

type API struct {
	store   *store.Store
	runner  *engine.Runner
	port    *portfolio.Store
	explain *explain.Service
	gdb     *gorm.DB
	dataDir string
	ver     version.Info
}

func New(st *store.Store, rn *engine.Runner, pf *portfolio.Store, ex *explain.Service, gdb *gorm.DB, dataDir string, ver version.Info) *API {
	return &API{store: st, runner: rn, port: pf, explain: ex, gdb: gdb, dataDir: dataDir, ver: ver}
}

func (a *API) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/health", a.health)
	mux.HandleFunc("/api/version", a.version)
	mux.HandleFunc("/api/datastatus", a.dataStatus)
	mux.HandleFunc("/api/snapshot", a.snapshot)
	mux.HandleFunc("/api/snapshot/dates", a.dates)
	mux.HandleFunc("/api/run", a.run)
	mux.HandleFunc("/api/positions", a.positions)
	mux.HandleFunc("/api/explain", a.explainHandler)
	return cors(mux)
}

// explainHandler AI 白话讲解某股:?ticker=X&date=&force=1
func (a *API) explainHandler(w http.ResponseWriter, r *http.Request) {
	ticker := r.URL.Query().Get("ticker")
	if ticker == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker"})
		return
	}
	res, err := a.explain.Explain(r.Context(), ticker, r.URL.Query().Get("date"), r.URL.Query().Get("force") == "1")
	if err != nil {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, res)
}

func (a *API) health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "service": "sentinel", "version": a.ver.Version})
}

func (a *API) version(w http.ResponseWriter, r *http.Request) { writeJSON(w, http.StatusOK, a.ver) }

// dataStatus 数据源完整性:快照(DB)+ 价格覆盖(DB)+ 数据源清单。
func (a *API) dataStatus(w http.ResponseWriter, r *http.Request) {
	dates, _ := a.store.Dates()
	status := map[string]any{"snapshot_dates": dates, "n_snapshots": len(dates), "storage": "PostgreSQL"}
	if raw, err := a.store.Latest(); err == nil {
		var snap map[string]any
		_ = json.Unmarshal(raw, &snap)
		status["latest_asof"] = snap["asof"]
		if hs, ok := snap["holdings"].([]any); ok {
			status["n_holdings"] = len(hs)
		}
		status["risk_light"] = snap["risk_light"]
	}
	var nPrices int64
	var priceAsof string
	a.gdb.Raw(`SELECT count(*) FROM prices WHERE date = (SELECT max(date) FROM prices)`).Row().Scan(&nPrices)
	a.gdb.Raw(`SELECT max(date)::text FROM prices`).Row().Scan(&priceAsof)
	status["price_table"] = map[string]any{"asof": priceAsof, "n_tickers": nPrices}
	status["sources"] = map[string]string{
		"prices":       "safna_jr/round20/data_broad(1393只 OHLCV+指标)→ 选股/档位/概率/盈亏",
		"fundamentals": "SEC EDGAR PIT(SY 股东收益率)→ 选股SY腿",
		"note":         "历史至2026-06-25;实时刷新(yfinance)待接",
	}
	writeJSON(w, http.StatusOK, status)
}

func (a *API) snapshot(w http.ResponseWriter, r *http.Request) {
	date := r.URL.Query().Get("date")
	var (
		raw json.RawMessage
		err error
	)
	if date == "" || date == "latest" {
		raw, err = a.store.Latest()
	} else {
		raw, err = a.store.ByDate(date)
	}
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "无快照,请先 POST /api/run 生成", "detail": err.Error()})
		return
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(raw)
}

func (a *API) dates(w http.ResponseWriter, r *http.Request) {
	ds, err := a.store.Dates()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"dates": ds})
}

// run 触发引擎(产 JSON)→ ingest 快照+价格入 PostgreSQL。
func (a *API) run(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "用 POST"})
		return
	}
	asof := q(r, "asof", "latest")
	out, err := a.runner.RunDaily(asof, q(r, "capital", "4000"), r.URL.Query().Get("sy") != "0")
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error(), "log": out})
		return
	}
	// ingest 引擎产出的 latest 快照 + 价格
	snapRaw, e1 := os.ReadFile(filepath.Join(a.dataDir, "snapshot_latest.json"))
	priceRaw, e2 := os.ReadFile(filepath.Join(a.dataDir, "prices_latest.json"))
	if e1 != nil || e2 != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "引擎产出读取失败", "log": out})
		return
	}
	sid, e3 := a.store.IngestSnapshot(snapRaw)
	nPx, e4 := a.store.IngestPrices(priceRaw)
	if e3 != nil || e4 != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": errStr(e3, e4), "log": out})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "done", "snapshot_id": sid, "n_prices": nPx, "log": out})
}

func (a *API) positions(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		res, err := a.port.Compute(r.URL.Query().Get("date"))
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, res)
	case http.MethodPost:
		var ps []portfolio.Input
		if err := json.NewDecoder(r.Body).Decode(&ps); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "body 应为持仓数组: " + err.Error()})
			return
		}
		if err := a.port.Save(ps); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"status": "saved", "n": len(ps)})
	default:
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "GET 或 POST"})
	}
}

func q(r *http.Request, k, d string) string {
	if v := r.URL.Query().Get(k); v != "" {
		return v
	}
	return d
}

func errStr(errs ...error) string {
	for _, e := range errs {
		if e != nil {
			return e.Error()
		}
	}
	return ""
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func cors(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}
