// Package engine — 调度 Python 策略引擎(subprocess)产出每日快照。
package engine

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

type Runner struct {
	pythonBin string
	engineDir string
}

func New(pythonBin, engineDir string) *Runner {
	return &Runner{pythonBin: pythonBin, engineDir: engineDir}
}

// EngineDir 引擎目录(供调度器定位 refresh_data.py 等)。
func (r *Runner) EngineDir() string { return r.engineDir }

// RunPython 跑任意引擎脚本(供数据刷新);返回 stdout,超时 timeout。
func (r *Runner) RunPython(script string, args []string, timeout time.Duration) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	full := append([]string{script}, args...)
	cmd := exec.CommandContext(ctx, r.pythonBin, full...)
	cmd.Dir = r.engineDir
	var out, errb bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &errb
	if err := cmd.Run(); err != nil {
		return out.String(), fmt.Errorf("%v | stderr: %s", err, errb.String())
	}
	return out.String(), nil
}

// RunDaily 跑 run_daily.py 产出/刷新快照。asof="latest" 或 YYYY-MM-DD。
// 返回引擎 stdout(便于前端显示日志);超时 10 分钟(SY 腿较慢)。
func (r *Runner) RunDaily(market string, asof string, capital string, withSY bool, track []string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()

	if market != "cn" {
		market = "us"
	}
	args := []string{filepath.Join(r.engineDir, "run_daily.py"), "--market", market, "--asof", asof, "--capital", capital}
	if !withSY {
		args = append(args, "--no-sy")
	}
	if len(track) > 0 {
		args = append(args, "--track", strings.Join(track, ","))
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

// RunFocus 单股观察:按市场跑 focus.py / focus_cn.py TICKER,返回 stdout 最后一行 JSON。
func (r *Runner) RunFocus(market, ticker, asof, capital string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()
	script := "focus.py"
	if market == "cn" {
		script = "focus_cn.py"
	}
	cmd := exec.CommandContext(ctx, r.pythonBin, filepath.Join(r.engineDir, script),
		ticker, "--asof", asof, "--capital", capital)
	cmd.Dir = r.engineDir
	var out, errb bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &errb
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("focus 运行失败: %v | %s", err, errb.String())
	}
	return lastJSON(out.String(), "focus")
}

// RunBandHist 跑 bandhist_cn.py TICKER —— A股【未来20日收益范围】逐日历史序列(详情页两图数据源)。
// 单票 CSV 重算,~0.5s;返回单行 JSON {ticker,asof,points}。当前仅 A股(cn),其余市场返回空。
func (r *Runner) RunBandHist(market, ticker, asof string, n int) (string, error) {
	if market != "cn" {
		return "", fmt.Errorf("bandhist 暂仅支持 A股")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, r.pythonBin, filepath.Join(r.engineDir, "bandhist_cn.py"),
		ticker, "--asof", asof, "--n", strconv.Itoa(n))
	cmd.Dir = r.engineDir
	var out, errb bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &errb
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("bandhist 运行失败: %v | %s", err, errb.String())
	}
	return lastJSON(out.String(), "bandhist")
}

// RunMoneyflow 跑 moneyflow_cn.py TICKER —— A股【资金流·量能】展示卡数据(仅 cn,纯展示)。
// tushare moneyflow(主力/散户/四单)+ 本地量能;单票 ~1s;返回单行 JSON。
func (r *Runner) RunMoneyflow(market, ticker string, days int) (string, error) {
	if market != "cn" {
		return "", fmt.Errorf("moneyflow 暂仅支持 A股")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, r.pythonBin, filepath.Join(r.engineDir, "moneyflow_cn.py"),
		ticker, "--days", strconv.Itoa(days))
	cmd.Dir = r.engineDir
	var out, errb bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &errb
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("moneyflow 运行失败: %v | %s", err, errb.String())
	}
	return lastJSON(out.String(), "moneyflow")
}

// RunSectorFlow 跑 moneyflow_sector_cn.py —— A股【板块资金热力】(行业净流入排行/近N日累计,纯展示)。
// 多次 tushare 调用 ~5s,故上层缓存;返回单行 JSON {asof,industries}。
func (r *Runner) RunSectorFlow(days int) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, r.pythonBin, filepath.Join(r.engineDir, "moneyflow_sector_cn.py"),
		"--days", strconv.Itoa(days))
	cmd.Dir = r.engineDir
	var out, errb bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &errb
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("sector flow 运行失败: %v | %s", err, errb.String())
	}
	return lastJSON(out.String(), "sectorflow")
}

// RunEarnings 按市场跑 earnings.py(美股 SEC)/ earnings_cn.py(A股新浪)TICKER,返回季度财报 JSON。
func (r *Runner) RunEarnings(market, ticker string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	script := "earnings.py"
	if market == "cn" {
		script = "earnings_cn.py"
	}
	cmd := exec.CommandContext(ctx, r.pythonBin, filepath.Join(r.engineDir, script), ticker)
	cmd.Dir = r.engineDir
	var out, errb bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &errb
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("earnings 运行失败: %v | %s", err, errb.String())
	}
	return lastJSON(out.String(), "earnings")
}

func lastJSON(s, name string) (string, error) {
	lines := strings.Split(strings.TrimSpace(s), "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		if strings.HasPrefix(strings.TrimSpace(lines[i]), "{") {
			return strings.TrimSpace(lines[i]), nil
		}
	}
	return "", fmt.Errorf("%s 无有效输出", name)
}
