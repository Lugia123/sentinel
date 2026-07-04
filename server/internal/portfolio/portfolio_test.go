package portfolio

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestComputePnL(t *testing.T) {
	dir := t.TempDir()
	// 价格表
	prices := map[string]any{"asof": "2026-06-25", "prices": map[string]float64{"UNH": 415.53, "MO": 73.21}}
	b, _ := json.Marshal(prices)
	os.WriteFile(filepath.Join(dir, "prices_latest.json"), b, 0644)

	s := New(dir)
	if err := s.Save([]Position{{Ticker: "UNH", Shares: 1, Cost: 400}, {Ticker: "MO", Shares: 10, Cost: 60}}); err != nil {
		t.Fatal(err)
	}
	res, err := s.Compute("")
	if err != nil {
		t.Fatal(err)
	}
	sum := res["summary"].(map[string]any)
	// UNH: 415.53-400=15.53 ; MO: 732.1-600=132.1 ; 合计 147.63 / 成本1000 = 14.76%
	if got := sum["pnl"].(float64); got != 147.63 {
		t.Errorf("总盈亏 = %v, want 147.63", got)
	}
	if got := sum["cost_value"].(float64); got != 1000 {
		t.Errorf("总成本 = %v, want 1000", got)
	}
	pct := sum["pnl_pct"].(float64)
	if pct < 0.147 || pct > 0.148 {
		t.Errorf("盈亏%% = %v, want ~0.1476", pct)
	}
}

func TestComputeUnpriced(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "prices_latest.json"),
		[]byte(`{"asof":"2026-06-25","prices":{"AAPL":200}}`), 0644)
	s := New(dir)
	s.Save([]Position{{Ticker: "ZZZZ", Shares: 5, Cost: 10}}) // 无价 ticker
	res, err := s.Compute("")
	if err != nil {
		t.Fatal(err)
	}
	rows := res["positions"].([]PnL)
	if rows[0].Priced {
		t.Error("无价 ticker 应 priced=false")
	}
	// 无价不计入组合汇总
	if sum := res["summary"].(map[string]any); sum["market_value"].(float64) != 0 {
		t.Errorf("无价持仓不应计入市值,got %v", sum["market_value"])
	}
}
