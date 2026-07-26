// Package portfolio — 用户实际持仓(PostgreSQL)+ 按 as-of 收盘价算浮盈亏。
package portfolio

import (
	"fmt"

	"gorm.io/gorm"

	"sentinel/internal/db"
)

// Input 前端录入的一笔持仓。
type Input struct {
	Ticker   string  `json:"ticker"`
	Shares   float64 `json:"shares"`
	Cost     float64 `json:"cost"`
	OpenedAt *string `json:"opened_at,omitempty"`
	Note     string  `json:"note,omitempty"`
}

// PnL 计算后的持仓盈亏行。
type PnL struct {
	Ticker      string  `json:"ticker"`
	Shares      float64 `json:"shares"`
	Cost        float64 `json:"cost"`
	Price       float64 `json:"price"`
	Priced      bool    `json:"priced"`
	MarketValue float64 `json:"market_value"`
	CostValue   float64 `json:"cost_value"`
	PnLVal      float64 `json:"pnl"`
	PnLPct      float64 `json:"pnl_pct"`
}

type Store struct{ gdb *gorm.DB }

func New(gdb *gorm.DB) *Store { return &Store{gdb: gdb} }

// Get 读某用户某市场的持仓(用户+市场双隔离)。
func (s *Store) Get(uid int64, market string) ([]db.Position, error) {
	var ps []db.Position
	err := s.gdb.Where("user_id = ? AND market = ?", uid, market).Order("ticker").Find(&ps).Error
	return ps, err
}

// Save 整体替换某用户【当前市场】的持仓(事务:清空该市场 + 批量插;不动另一市场)。
func (s *Store) Save(uid int64, market string, in []Input) error {
	return s.gdb.Transaction(func(tx *gorm.DB) error {
		if err := tx.Exec(`DELETE FROM positions WHERE user_id=? AND market=?`, uid, market).Error; err != nil {
			return err
		}
		for _, p := range in {
			if err := tx.Exec(`INSERT INTO positions(user_id,market,ticker,shares,cost,opened_at,note,created_at,updated_at)
				VALUES (?,?,?,?,?,?,?,now(),now())`, uid, market, p.Ticker, p.Shares, p.Cost, p.OpenedAt, p.Note).Error; err != nil {
				return err
			}
		}
		return nil
	})
}

// Compute 按 as-of 价格(date 空=该市场最新快照日)算某用户每笔盈亏 + 组合汇总。
func (s *Store) Compute(uid int64, market, date string) (map[string]any, error) {
	asof := date
	if asof == "" || asof == "latest" {
		if err := s.gdb.Raw(`SELECT asof::text FROM snapshots WHERE market=? ORDER BY asof DESC LIMIT 1`, market).Row().Scan(&asof); err != nil || asof == "" {
			// 无快照则退到该市场最新价格日
			s.gdb.Raw(`SELECT max(date)::text FROM prices WHERE market=?`, market).Row().Scan(&asof)
		}
	}
	if asof == "" {
		return nil, fmt.Errorf("无价格数据(先 POST /api/run 生成)")
	}
	ps, err := s.Get(uid, market)
	if err != nil {
		return nil, err
	}
	// 该 as-of 的价格
	prices := map[string]float64{}
	var prows []db.Price
	s.gdb.Raw(`SELECT ticker, close FROM prices WHERE market=? AND date = ?`, market, asof).Scan(&prows)
	for _, r := range prows {
		prices[r.Ticker] = r.Close
	}
	rows, summary := ComputePnL(ps, prices)
	return map[string]any{"asof": asof, "positions": rows, "summary": summary}, nil
}

// ComputePnL 纯函数:给持仓 + 价格表,算每笔盈亏 + 组合汇总(无价不计入汇总)。可测。
func ComputePnL(ps []db.Position, prices map[string]float64) ([]PnL, map[string]float64) {
	rows := []PnL{} // 非 nil,空持仓也返回 [] 而非 null(前端 .map 才不会崩)
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
		rows = append(rows, PnL{Ticker: p.Ticker, Shares: p.Shares, Cost: p.Cost, Price: px, Priced: ok,
			MarketValue: round2(mv), CostValue: round2(cv), PnLVal: round2(pnl), PnLPct: round4(pct)})
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
	return rows, map[string]float64{
		"market_value": round2(totMV), "cost_value": round2(totCost),
		"pnl": round2(totPnL), "pnl_pct": round4(totPct),
	}
}

func round2(x float64) float64 { return float64(int(x*100+sign(x)*0.5)) / 100 }
func round4(x float64) float64 { return float64(int(x*10000+sign(x)*0.5)) / 10000 }
func sign(x float64) float64 {
	if x < 0 {
		return -1
	}
	return 1
}
