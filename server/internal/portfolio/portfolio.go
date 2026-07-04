// Package portfolio — 用户实际持仓录入 + 按 as-of 收盘价算浮盈亏。
// 持仓存 data/positions.json;价格取 engine 产出的 prices_<date>.json(as-of 一致)。
package portfolio

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// Position 用户录入的一笔持仓。
type Position struct {
	Ticker string  `json:"ticker"`
	Shares float64 `json:"shares"`
	Cost   float64 `json:"cost"` // 每股成本
}

// PnL 计算后的持仓盈亏。
type PnL struct {
	Position
	Price       float64 `json:"price"`        // as-of 收盘价(无则 0 + priced=false)
	Priced      bool    `json:"priced"`       // 是否取到价格
	MarketValue float64 `json:"market_value"`
	CostValue   float64 `json:"cost_value"`
	PnL         float64 `json:"pnl"`
	PnLPct      float64 `json:"pnl_pct"`
}

type Store struct{ dataDir string }

func New(dataDir string) *Store { return &Store{dataDir: dataDir} }

func (s *Store) file() string { return filepath.Join(s.dataDir, "positions.json") }

// Get 读持仓(无文件返回空)。
func (s *Store) Get() ([]Position, error) {
	b, err := os.ReadFile(s.file())
	if os.IsNotExist(err) {
		return []Position{}, nil
	}
	if err != nil {
		return nil, err
	}
	var ps []Position
	if err := json.Unmarshal(b, &ps); err != nil {
		return nil, err
	}
	return ps, nil
}

// Save 整体替换持仓。
func (s *Store) Save(ps []Position) error {
	b, _ := json.MarshalIndent(ps, "", "  ")
	return os.WriteFile(s.file(), b, 0644)
}

// priceMap 读 as-of 价格表(date 空=latest)。
func (s *Store) priceMap(date string) (string, map[string]float64, error) {
	name := "prices_latest.json"
	if date != "" && date != "latest" {
		name = fmt.Sprintf("prices_%s.json", date)
	}
	b, err := os.ReadFile(filepath.Join(s.dataDir, name))
	if err != nil {
		return "", nil, err
	}
	var pd struct {
		Asof   string             `json:"asof"`
		Prices map[string]float64 `json:"prices"`
	}
	if err := json.Unmarshal(b, &pd); err != nil {
		return "", nil, err
	}
	return pd.Asof, pd.Prices, nil
}

// Compute 按 as-of 价格算每笔盈亏 + 组合汇总。
func (s *Store) Compute(date string) (map[string]any, error) {
	ps, err := s.Get()
	if err != nil {
		return nil, err
	}
	asof, prices, err := s.priceMap(date)
	if err != nil {
		return nil, fmt.Errorf("无价格表(先 POST /api/run 生成 as-of=%s): %w", date, err)
	}
	var rows []PnL
	var totMV, totCost float64
	for _, p := range ps {
		px, ok := prices[p.Ticker]
		mv := p.Shares * px
		cv := p.Shares * p.Cost
		pnl := mv - cv
		pct := 0.0
		if cv > 0 {
			pct = pnl / cv
		}
		rows = append(rows, PnL{Position: p, Price: px, Priced: ok,
			MarketValue: round2(mv), CostValue: round2(cv), PnL: round2(pnl), PnLPct: round4(pct)})
		if ok {
			totMV += mv
			totCost += cv
		}
	}
	totPnL := totMV - totCost
	totPct := 0.0
	if totCost > 0 {
		totPct = totPnL / totCost
	}
	return map[string]any{
		"asof":      asof,
		"positions": rows,
		"summary": map[string]any{
			"market_value": round2(totMV), "cost_value": round2(totCost),
			"pnl": round2(totPnL), "pnl_pct": round4(totPct),
		},
	}, nil
}

func round2(x float64) float64 { return float64(int(x*100+sign(x)*0.5)) / 100 }
func round4(x float64) float64 { return float64(int(x*10000+sign(x)*0.5)) / 10000 }
func sign(x float64) float64 {
	if x < 0 {
		return -1
	}
	return 1
}
