package portfolio

import (
	"testing"

	"sentinel/internal/db"
)

func TestComputePnL(t *testing.T) {
	ps := []db.Position{{Ticker: "UNH", Shares: 1, Cost: 400}, {Ticker: "MO", Shares: 10, Cost: 60}}
	prices := map[string]float64{"UNH": 415.53, "MO": 73.21}
	rows, sum := ComputePnL(ps, prices)
	if len(rows) != 2 {
		t.Fatalf("行数 %d, want 2", len(rows))
	}
	// UNH: 415.53-400=15.53 ; MO: 732.1-600=132.1 ; 合计 147.63 / 成本1000 = 14.76%
	if sum["pnl"] != 147.63 {
		t.Errorf("总盈亏 = %v, want 147.63", sum["pnl"])
	}
	if sum["cost_value"] != 1000 {
		t.Errorf("总成本 = %v, want 1000", sum["cost_value"])
	}
	if sum["pnl_pct"] < 0.147 || sum["pnl_pct"] > 0.148 {
		t.Errorf("盈亏%% = %v, want ~0.1476", sum["pnl_pct"])
	}
}

func TestComputeUnpriced(t *testing.T) {
	ps := []db.Position{{Ticker: "ZZZZ", Shares: 5, Cost: 10}}
	rows, sum := ComputePnL(ps, map[string]float64{"AAPL": 200})
	if rows[0].Priced {
		t.Error("无价 ticker 应 priced=false")
	}
	if sum["market_value"] != 0 {
		t.Errorf("无价持仓不应计入市值,got %v", sum["market_value"])
	}
}
