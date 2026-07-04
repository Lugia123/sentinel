// Package engine — 调度 Python 策略引擎(subprocess)产出每日快照。
package engine

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"path/filepath"
	"time"
)

type Runner struct {
	pythonBin string
	engineDir string
}

func New(pythonBin, engineDir string) *Runner {
	return &Runner{pythonBin: pythonBin, engineDir: engineDir}
}

// RunDaily 跑 run_daily.py 产出/刷新快照。asof="latest" 或 YYYY-MM-DD。
// 返回引擎 stdout(便于前端显示日志);超时 10 分钟(SY 腿较慢)。
func (r *Runner) RunDaily(asof string, capital string, withSY bool) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()

	args := []string{filepath.Join(r.engineDir, "run_daily.py"), "--asof", asof, "--capital", capital}
	if !withSY {
		args = append(args, "--no-sy")
	}
	cmd := exec.CommandContext(ctx, r.pythonBin, args...)
	cmd.Dir = r.engineDir
	var out, errb bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &errb
	if err := cmd.Run(); err != nil {
		return out.String(), fmt.Errorf("引擎运行失败: %v | stderr: %s", err, errb.String())
	}
	return out.String(), nil
}
