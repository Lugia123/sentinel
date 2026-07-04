// cmd/server — Sentinel 后端入口。
// 职责:读快照 / 触发 Python 引擎 / 供 API 给 React 仪表盘。
// 运行:cd server && go run ./cmd/server   (默认 :8787)
package main

import (
	"log"
	"net/http"

	"sentinel/internal/api"
	"sentinel/internal/config"
	"sentinel/internal/engine"
	"sentinel/internal/store"
)

func main() {
	cfg := config.Load()
	st := store.New(cfg.DataDir)
	rn := engine.New(cfg.PythonBin, cfg.EngineDir)
	a := api.New(st, rn)

	log.Printf("Sentinel 后端启动 :%s", cfg.Port)
	log.Printf("  快照目录 %s", cfg.DataDir)
	log.Printf("  引擎目录 %s", cfg.EngineDir)
	log.Printf("  API: GET /api/snapshot  |  POST /api/run  |  GET /api/snapshot/dates")
	if err := http.ListenAndServe(":"+cfg.Port, a.Routes()); err != nil {
		log.Fatal(err)
	}
}
