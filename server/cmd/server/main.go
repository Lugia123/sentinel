// cmd/server — Sentinel 后端入口。
// 职责:连 PostgreSQL / 跑迁移 / 触发引擎并 ingest / 供 API 给 React 仪表盘。
// 运行:cd server && go run ./cmd/server   (默认 :8787,DB DSN 在 server/.env)
package main

import (
	"log"
	"net/http"
	"path/filepath"

	"sentinel/internal/ai"
	"sentinel/internal/api"
	"sentinel/internal/config"
	"sentinel/internal/db"
	"sentinel/internal/engine"
	"sentinel/internal/explain"
	"sentinel/internal/portfolio"
	"sentinel/internal/store"
	"sentinel/internal/version"
)

func main() {
	cfg := config.Load()
	ver := version.Compute(cfg.Root)

	gdb, err := db.Connect(cfg.DBDSN)
	if err != nil {
		log.Fatalf("连接 PostgreSQL 失败(检查 server/.env 的 SENTINEL_DB_DSN): %v", err)
	}
	if err := db.Migrate(gdb, filepath.Join(cfg.Root, "server", "migrations")); err != nil {
		log.Fatalf("数据库迁移失败: %v", err)
	}

	st := store.New(gdb)
	rn := engine.New(cfg.PythonBin, cfg.EngineDir)
	pf := portfolio.New(gdb)
	aic := ai.New(cfg.DeepSeek.Key, cfg.DeepSeek.Base, cfg.DeepSeek.Model)
	ex := explain.New(st, aic, gdb)
	a := api.New(st, rn, pf, ex, gdb, cfg.DataDir, cfg.EngineDir, ver)

	aiState := "已启用"
	if !aic.Enabled() {
		aiState = "未配置(讲解功能降级,其余不受影响)"
	}
	log.Printf("Sentinel %s 后端启动 :%s (%s)", ver.Version, cfg.Port, ver.Branch)
	log.Printf("  PostgreSQL 已连接 + 迁移完成 | DeepSeek AI: %s", aiState)
	log.Printf("  API: /api/snapshot · /api/run · /api/positions · /api/explain · /api/datastatus")
	if err := http.ListenAndServe(":"+cfg.Port, a.Routes()); err != nil {
		log.Fatal(err)
	}
}
