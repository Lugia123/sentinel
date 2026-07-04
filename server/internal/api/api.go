// Package api — Sentinel HTTP 路由与处理器(stdlib net/http,零外部依赖)。
package api

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"

	"sentinel/internal/engine"
	"sentinel/internal/portfolio"
	"sentinel/internal/store"
	"sentinel/internal/version"
)

type API struct {
	store   *store.Store
	runner  *engine.Runner
	port    *portfolio.Store
	dataDir string
	ver     version.Info
}

func New(st *store.Store, rn *engine.Runner, pf *portfolio.Store, dataDir string, ver version.Info) *API {
	return &API{store: st, runner: rn, port: pf, dataDir: dataDir, ver: ver}
}

// Routes 注册所有路由(带 dev CORS)。
func (a *API) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/health", a.health)
	mux.HandleFunc("/api/version", a.version)
	mux.HandleFunc("/api/datastatus", a.dataStatus)     // 数据源完整性
	mux.HandleFunc("/api/snapshot", a.snapshot)         // ?date=YYYY-MM-DD 可选,默认 latest
	mux.HandleFunc("/api/snapshot/dates", a.dates)
	mux.HandleFunc("/api/run", a.run)                   // POST ?asof=&capital=&sy= 触发引擎
	mux.HandleFunc("/api/positions", a.positions)       // GET 算盈亏 / POST 录入
	return cors(mux)
}

func (a *API) health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "service": "sentinel", "version": a.ver.Version})
}

func (a *API) version(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, a.ver)
}

// dataStatus 汇报数据源完整性:快照/价格表/universe 覆盖。
func (a *API) dataStatus(w http.ResponseWriter, r *http.Request) {
	dates, _ := a.store.Dates()
	status := map[string]any{
		"snapshot_dates": dates,
		"n_snapshots":    len(dates),
	}
	// 最新快照的覆盖情况
	if raw, err := a.store.Latest(); err == nil {
		var snap map[string]any
		_ = json.Unmarshal(raw, &snap)
		status["latest_asof"] = snap["asof"]
		if hs, ok := snap["holdings"].([]any); ok {
			status["n_holdings"] = len(hs)
		}
		status["risk_light"] = snap["risk_light"]
	}
	// 价格表覆盖(universe 大小)
	if b, err := os.ReadFile(filepath.Join(a.dataDir, "prices_latest.json")); err == nil {
		var pd struct {
			Asof   string             `json:"asof"`
			Prices map[string]float64 `json:"prices"`
		}
		if json.Unmarshal(b, &pd) == nil {
			status["price_table"] = map[string]any{"asof": pd.Asof, "n_tickers": len(pd.Prices)}
		}
	}
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

func (a *API) run(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "用 POST"})
		return
	}
	asof := q(r, "asof", "latest")
	capital := q(r, "capital", "4000")
	withSY := r.URL.Query().Get("sy") != "0"
	out, err := a.runner.RunDaily(asof, capital, withSY)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error(), "log": out})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "done", "log": out})
}

// positions: GET 返回持仓盈亏(?date= as-of);POST 录入持仓(body=[]Position)。
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
		var ps []portfolio.Position
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

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

// cors — 开发期放开跨域(前端 vite 5173 → 后端 8787)。
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
