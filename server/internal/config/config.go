// Package config — Sentinel 后端配置(路径 / 端口 / 引擎 / 数据库)。
package config

import (
	"bufio"
	"os"
	"path/filepath"
	"strings"
)

type Config struct {
	Port      string // HTTP 端口
	Root      string // 项目根(算版本)
	DataDir   string // 引擎产出的快照/价格 JSON 目录(ingest 源)
	EngineDir string // Python 引擎目录
	PythonBin string // python 解释器(默认复用 safna_jr 的 uv venv)
	DBDSN     string // PostgreSQL DSN(密码在 server/.env,不入库)
	Capital   string // 默认资金池
	Schedule  string // 每日自动运行时刻 HH:MM(本地时间,默认美股收盘后)
	DeepSeek  DeepSeekConfig
	Minio     MinioConfig
}

type MinioConfig struct {
	Endpoint, Key, Secret, Bucket string
}

type DeepSeekConfig struct {
	Key   string // API key(只在 server/.env)
	Base  string // https://api.deepseek.com
	Model string // deepseek-chat / deepseek-reasoner
}

// Load 从环境变量 / server/.env 读配置,给出合理默认值(本地开发即用)。
func Load() Config {
	root := findRoot()
	loadDotenv(filepath.Join(root, "server", ".env")) // 开发期自动加载 .env(含 DB 密码)
	return Config{
		Port:      envOr("SENTINEL_PORT", "8787"),
		Root:      root,
		DataDir:   envOr("SENTINEL_DATA", filepath.Join(root, "data")),
		EngineDir: envOr("SENTINEL_ENGINE", filepath.Join(root, "engine")),
		PythonBin: envOr("SENTINEL_PYTHON", "python3"),
		DBDSN:     envOr("SENTINEL_DB_DSN", "host=localhost port=5432 user=sentinel dbname=sentinel sslmode=disable"),
		Capital:   envOr("SENTINEL_CAPITAL", "4000"),
		Schedule:  envOr("SENTINEL_SCHEDULE", "4"), // 默认间隔小时(每4h跑双市场;管理员可在设置里改,存 settings.schedule_interval_hours)
		DeepSeek: DeepSeekConfig{
			Key:   os.Getenv("SENTINEL_DEEPSEEK_KEY"),
			Base:  envOr("SENTINEL_DEEPSEEK_BASE", "https://api.deepseek.com"),
			Model: envOr("SENTINEL_DEEPSEEK_MODEL", "deepseek-chat"),
		},
		Minio: MinioConfig{
			Endpoint: os.Getenv("SENTINEL_MINIO_ENDPOINT"),
			Key:      os.Getenv("SENTINEL_MINIO_KEY"),
			Secret:   os.Getenv("SENTINEL_MINIO_SECRET"),
			Bucket:   envOr("SENTINEL_MINIO_BUCKET", "sentinel"),
		},
	}
}

// loadDotenv 极简 .env 解析(KEY=VALUE),只设未存在的环境变量;文件缺失静默。
func loadDotenv(path string) {
	f, err := os.Open(path)
	if err != nil {
		return
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		k, v, ok := strings.Cut(line, "=")
		if ok && os.Getenv(strings.TrimSpace(k)) == "" {
			os.Setenv(strings.TrimSpace(k), strings.TrimSpace(v))
		}
	}
}

func envOr(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

// findRoot 从 CWD 向上找含 engine/ 与 data/ 的项目根;找不到用 CWD。
func findRoot() string {
	cwd, _ := os.Getwd()
	dir := cwd
	for i := 0; i < 6; i++ {
		if fi, err := os.Stat(filepath.Join(dir, "engine")); err == nil && fi.IsDir() {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	return cwd
}
