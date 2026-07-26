// cmd/server — Sentinel 后端入口。
// 职责:连 PostgreSQL / 跑迁移 / 触发引擎并 ingest / 供 API 给 React 仪表盘。
// 运行:cd server && go run ./cmd/server   (默认 :8787,DB DSN 在 server/.env)
package main

import (
	"log"
	"os"
	"net/http"
	"path/filepath"

	"sentinel/internal/ai"
	"sentinel/internal/allocate"
	"sentinel/internal/api"
	"sentinel/internal/auth"
	"sentinel/internal/blob"
	"sentinel/internal/config"
	"sentinel/internal/db"
	"sentinel/internal/earnings"
	"sentinel/internal/engine"
	"sentinel/internal/explain"
	"sentinel/internal/investigate"
	"sentinel/internal/portfolio"
	"sentinel/internal/scheduler"
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
	bs, berr := blob.New(cfg.Minio.Endpoint, cfg.Minio.Key, cfg.Minio.Secret, cfg.Minio.Bucket)
	if berr != nil {
		log.Printf("MinIO 连接失败(大HTML存储降级): %v", berr)
	}
	ex := explain.New(st, aic, gdb)
	inv := investigate.New(aic, bs, cfg.EngineDir)
	earn := earnings.New(rn, aic, bs)
	al := allocate.New(aic, st, gdb)
	au := auth.New(gdb, env("SENTINEL_JWT_SECRET", ""))
	// 初始管理员:必须由环境变量提供邮箱+密码(不设弱默认密码)。都缺则跳过,可稍后手动建。
	adminEmail := env("SENTINEL_ADMIN_EMAIL", "")
	adminPass := env("SENTINEL_ADMIN_PASSWORD", "")
	if adminEmail != "" && adminPass != "" {
		if err := au.EnsureAdmin(adminEmail, adminPass); err != nil {
			log.Printf("种子管理员失败: %v", err)
		} else {
			log.Printf("初始管理员已就绪: %s", adminEmail)
		}
	} else {
		log.Printf("未建初始管理员(设 SENTINEL_ADMIN_EMAIL + SENTINEL_ADMIN_PASSWORD 后重启即可)")
	}
	a := api.New(st, rn, pf, ex, inv, earn, al, au, bs, gdb, aic, cfg.DataDir, cfg.EngineDir, ver)

	// 后台定时任务:每日定点自动跑引擎+ingest;启动时若库中无快照则自愈补跑
	scheduler.New(rn, st, cfg.DataDir, cfg.Capital, cfg.Schedule).Start()

	aiState := "已启用"
	if !aic.Enabled() {
		aiState = "未配置(讲解功能降级,其余不受影响)"
	}
	log.Printf("Sentinel %s 后端启动 :%s (%s)", ver.Version, cfg.Port, ver.Branch)
	minioState := "未配置"
	if bs != nil && bs.Enabled() {
		minioState = "已连接(" + cfg.Minio.Bucket + ")"
	}
	log.Printf("  PostgreSQL 已连接 + 迁移完成 | DeepSeek AI: %s | MinIO: %s", aiState, minioState)
	log.Printf("  API: /api/snapshot · /api/run · /api/positions · /api/explain · /api/datastatus")
	if err := http.ListenAndServe(":"+cfg.Port, a.Routes()); err != nil {
		log.Fatal(err)
	}
}

func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}
