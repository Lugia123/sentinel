// cmd/server — Sentinel 后端入口。
// 职责:读快照 / 触发 Python 引擎 / 持仓盈亏 / 供 API 给 React 仪表盘。
// 运行:cd server && go run ./cmd/server   (默认 :8787)
package main

import (
	"log"
	"net/http"

	"sentinel/internal/api"
	"sentinel/internal/config"
	"sentinel/internal/engine"
	"sentinel/internal/portfolio"
	"sentinel/internal/store"
	"sentinel/internal/version"
)

func main() {
	cfg := config.Load()
	ver := version.Compute(cfg.Root)
	st := store.New(cfg.DataDir)
	rn := engine.New(cfg.PythonBin, cfg.EngineDir)
	pf := portfolio.New(cfg.DataDir)
	a := api.New(st, rn, pf, cfg.DataDir, ver)

	log.Printf("Sentinel %s 后端启动 :%s (%s)", ver.Version, cfg.Port, ver.Branch)
	log.Printf("  快照/价格/持仓目录 %s", cfg.DataDir)
	log.Printf("  API: /api/snapshot · /api/run · /api/positions · /api/datastatus · /api/version")
	if err := http.ListenAndServe(":"+cfg.Port, a.Routes()); err != nil {
		log.Fatal(err)
	}
}
