// Package store — 快照读取 + 从引擎 JSON ingest 入 PostgreSQL。
package store

import (
	"encoding/json"
	"fmt"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"sentinel/internal/db"
)

type Store struct{ gdb *gorm.DB }

func New(gdb *gorm.DB) *Store { return &Store{gdb: gdb} }

// GetSetting 读 settings 表某键(不存在返回空)。
func (s *Store) GetSetting(key string) string {
	var v string
	s.gdb.Raw(`SELECT value FROM settings WHERE key=?`, key).Scan(&v)
	return v
}

// SetSetting 写 settings 表(upsert)。
func (s *Store) SetSetting(key, value string) error {
	return s.gdb.Exec(`INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value`, key, value).Error
}

// TrackedTickers 用户"添加自定义股票"的追踪清单(watchlist source='user'),
// 供每日引擎把它们也算档位/概率(纳入每日分析)。
func (s *Store) TrackedTickers() []string {
	var ts []string
	s.gdb.Raw(`SELECT ticker FROM watchlist WHERE source='user' ORDER BY added_at`).Scan(&ts)
	return ts
}

// mkt 规整市场参数(空→us,向后兼容)。
func mkt(market string) string {
	if market == "cn" {
		return "cn"
	}
	return "us"
}

// Latest 最新快照的完整 raw JSON(按市场)。
func (s *Store) Latest(market string) (json.RawMessage, error) {
	var raw string
	if err := s.gdb.Raw(`SELECT raw::text FROM snapshots WHERE market = ? ORDER BY asof DESC LIMIT 1`, mkt(market)).Row().Scan(&raw); err != nil || raw == "" {
		return nil, fmt.Errorf("无快照(先 POST /api/run?market=%s)", mkt(market))
	}
	return json.RawMessage(raw), nil
}

// ByDate 指定收盘日快照(按市场)。
func (s *Store) ByDate(market, date string) (json.RawMessage, error) {
	var raw string
	if err := s.gdb.Raw(`SELECT raw::text FROM snapshots WHERE market = ? AND asof = ?`, mkt(market), date).Row().Scan(&raw); err != nil || raw == "" {
		return nil, fmt.Errorf("无 %s 快照", date)
	}
	return json.RawMessage(raw), nil
}

// Dates 某市场所有快照收盘日(倒序)。
func (s *Store) Dates(market string) ([]string, error) {
	var dates []string
	err := s.gdb.Raw(`SELECT asof::text FROM snapshots WHERE market = ? ORDER BY asof DESC`, mkt(market)).Scan(&dates).Error
	return dates, err
}

// ── ingest:解析引擎 JSON → upsert snapshots / holdings / prices ──

type snapProbeHolding struct {
	Ticker       string          `json:"ticker"`
	Sleeve       string          `json:"sleeve"`
	Price        float64         `json:"price"`
	BaseWeight   float64         `json:"base_weight"`
	TargetShares float64         `json:"target_shares"`
	TargetValue  float64         `json:"target_value"`
	Grade        int             `json:"grade"`
	Action       string          `json:"action"`
	Prob         json.RawMessage `json:"prob"`
}
type snapProbe struct {
	Market    string `json:"market"`
	Asof      string `json:"asof"`
	Capital   float64
	RiskLight struct {
		Level    string  `json:"level"`
		SpyVol   float64 `json:"spy_vol"`
		Exposure float64 `json:"exposure"`
	} `json:"risk_light"`
	Portfolio struct {
		GrossExposure float64 `json:"gross_exposure"`
		CashPct       float64 `json:"cash_pct"`
	} `json:"portfolio"`
	Holdings []snapProbeHolding `json:"holdings"`
}

// IngestSnapshot 解析快照 JSON,upsert snapshots(按 asof)+ 重建 holdings。
func (s *Store) IngestSnapshot(raw []byte) (int64, error) {
	var p snapProbe
	if err := json.Unmarshal(raw, &p); err != nil {
		return 0, fmt.Errorf("解析快照: %w", err)
	}
	if p.Asof == "" {
		return 0, fmt.Errorf("快照缺 asof")
	}
	market := mkt(p.Market) // 快照缺 market → us(向后兼容)
	var id int64
	err := s.gdb.Transaction(func(tx *gorm.DB) error {
		// upsert snapshot(按 market+asof)
		if e := tx.Exec(`
			INSERT INTO snapshots(market,asof,generated_at,capital,risk_level,spy_vol,exposure,gross_exposure,cash_pct,raw)
			VALUES (?, ?, now(), ?, ?, ?, ?, ?, ?, ?)
			ON CONFLICT (market,asof) DO UPDATE SET generated_at=now(), capital=EXCLUDED.capital,
			  risk_level=EXCLUDED.risk_level, spy_vol=EXCLUDED.spy_vol, exposure=EXCLUDED.exposure,
			  gross_exposure=EXCLUDED.gross_exposure, cash_pct=EXCLUDED.cash_pct, raw=EXCLUDED.raw`,
			market, p.Asof, p.Capital, p.RiskLight.Level, p.RiskLight.SpyVol, p.RiskLight.Exposure,
			p.Portfolio.GrossExposure, p.Portfolio.CashPct, string(raw)).Error; e != nil {
			return e
		}
		if e := tx.Raw(`SELECT id FROM snapshots WHERE market = ? AND asof = ?`, market, p.Asof).Scan(&id).Error; e != nil {
			return e
		}
		// 重建 holdings
		if e := tx.Exec(`DELETE FROM holdings WHERE snapshot_id = ?`, id).Error; e != nil {
			return e
		}
		for _, h := range p.Holdings {
			prob := "null"
			if len(h.Prob) > 0 {
				prob = string(h.Prob)
			}
			if e := tx.Exec(`INSERT INTO holdings(snapshot_id,market,ticker,sleeve,price,base_weight,target_shares,target_value,grade,action,prob)
				VALUES (?,?,?,?,?,?,?,?,?,?,?)`,
				id, market, h.Ticker, h.Sleeve, h.Price, h.BaseWeight, h.TargetShares, h.TargetValue, h.Grade, h.Action, prob).Error; e != nil {
				return e
			}
		}
		return nil
	})
	return id, err
}

// IngestPrices 解析价格 JSON(asof + {ticker:close}),批量 upsert prices。
func (s *Store) IngestPrices(raw []byte) (int, error) {
	var pd struct {
		Market string             `json:"market"`
		Asof   string             `json:"asof"`
		Prices map[string]float64 `json:"prices"`
	}
	if err := json.Unmarshal(raw, &pd); err != nil {
		return 0, err
	}
	market := mkt(pd.Market)
	rows := make([]db.Price, 0, len(pd.Prices))
	for tk, c := range pd.Prices {
		rows = append(rows, db.Price{Market: market, Ticker: tk, Date: pd.Asof, Close: c})
	}
	if len(rows) == 0 {
		return 0, nil
	}
	err := s.gdb.Clauses(clause.OnConflict{
		Columns:   []clause.Column{{Name: "market"}, {Name: "ticker"}, {Name: "date"}},
		DoUpdates: clause.AssignmentColumns([]string{"close"}),
	}).CreateInBatches(rows, 500).Error
	return len(rows), err
}
