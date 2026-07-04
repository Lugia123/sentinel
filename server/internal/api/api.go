// Package api — Sentinel HTTP 路由与处理器(stdlib net/http,零外部依赖)。
package api

import (
	"encoding/json"
	"net/http"

	"sentinel/internal/engine"
	"sentinel/internal/store"
)

type API struct {
	store  *store.Store
	runner *engine.Runner
}

func New(st *store.Store, rn *engine.Runner) *API {
	return &API{store: st, runner: rn}
}

// Routes 注册所有路由(带 dev CORS)。
func (a *API) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/health", a.health)
	mux.HandleFunc("/api/snapshot", a.snapshot)     // ?date=YYYY-MM-DD 可选,默认 latest
	mux.HandleFunc("/api/snapshot/dates", a.dates)   // 所有快照日
	mux.HandleFunc("/api/run", a.run)                // POST 触发引擎
	return cors(mux)
}

func (a *API) health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "service": "sentinel"})
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
	asof := r.URL.Query().Get("asof")
	if asof == "" {
		asof = "latest"
	}
	capital := r.URL.Query().Get("capital")
	if capital == "" {
		capital = "4000"
	}
	withSY := r.URL.Query().Get("sy") != "0"
	out, err := a.runner.RunDaily(asof, capital, withSY)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error(), "log": out})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "done", "log": out})
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
