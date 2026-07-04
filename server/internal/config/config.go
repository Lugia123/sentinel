// Package config — Sentinel 后端配置(路径 / 端口 / 引擎命令)。
package config

import (
	"os"
	"path/filepath"
)

type Config struct {
	Port      string // HTTP 端口
	Root      string // 项目根(算版本 + 持仓文件)
	DataDir   string // 每日快照 JSON 目录(engine 产出)
	EngineDir string // Python 引擎目录
	PythonBin string // python 解释器(默认复用 safna_jr 的 uv venv)
}

// Load 从环境变量读配置,给出合理默认值(本地开发即用)。
func Load() Config {
	// 项目根 = 可执行文件上溯;开发期用 CWD 上溯到含 engine/ 的目录
	root := findRoot()
	return Config{
		Port:      envOr("SENTINEL_PORT", "8787"),
		Root:      root,
		DataDir:   envOr("SENTINEL_DATA", filepath.Join(root, "data")),
		EngineDir: envOr("SENTINEL_ENGINE", filepath.Join(root, "engine")),
		PythonBin: envOr("SENTINEL_PYTHON", "/Users/lugia/lugia_fc/TradingAgents/.venv/bin/python"),
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
