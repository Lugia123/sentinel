package db

import (
	"time"

	"gorm.io/datatypes"
)

// 与 migrations/0001_init 对应的 gorm 模型(查询用;建表由 SQL 迁移负责)。

type Snapshot struct {
	ID            int64          `gorm:"primaryKey" json:"id"`
	Market        string         `gorm:"column:market" json:"market"` // us / cn(v2.0 双市场)
	Asof          string         `gorm:"column:asof" json:"asof"` // DATE 以字符串收发
	GeneratedAt   time.Time      `json:"generated_at"`
	Capital       float64        `json:"capital"`
	RiskLevel     string         `json:"risk_level"`
	SpyVol        float64        `json:"spy_vol"`
	Exposure      float64        `json:"exposure"`
	GrossExposure float64        `json:"gross_exposure"`
	CashPct       float64        `json:"cash_pct"`
	Raw           datatypes.JSON `json:"raw"`
}

func (Snapshot) TableName() string { return "snapshots" }

type Holding struct {
	ID           int64          `gorm:"primaryKey" json:"id"`
	SnapshotID   int64          `json:"snapshot_id"`
	Market       string         `gorm:"column:market" json:"market"`
	Ticker       string         `json:"ticker"`
	Sleeve       string         `json:"sleeve"`
	Price        float64        `json:"price"`
	BaseWeight   float64        `json:"base_weight"`
	TargetShares float64        `json:"target_shares"`
	TargetValue  float64        `json:"target_value"`
	Grade        int            `json:"grade"`
	Action       string         `json:"action"`
	Prob         datatypes.JSON `json:"prob"`
}

func (Holding) TableName() string { return "holdings" }

type Position struct {
	ID        int64     `gorm:"primaryKey" json:"id"`
	Market    string    `gorm:"column:market" json:"market"`
	Ticker    string    `json:"ticker"`
	Shares    float64   `json:"shares"`
	Cost      float64   `json:"cost"`
	OpenedAt  *string   `gorm:"column:opened_at" json:"opened_at,omitempty"`
	Note      string    `json:"note,omitempty"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

func (Position) TableName() string { return "positions" }

type Price struct {
	Market string  `gorm:"primaryKey;column:market" json:"market"`
	Ticker string  `gorm:"primaryKey" json:"ticker"`
	Date   string  `gorm:"primaryKey;column:date" json:"date"`
	Close  float64 `json:"close"`
}

func (Price) TableName() string { return "prices" }

type Run struct {
	ID         int64     `gorm:"primaryKey" json:"id"`
	Asof       *string   `json:"asof,omitempty"`
	Status     string    `json:"status"`
	DurationMs int       `json:"duration_ms"`
	Log        string    `json:"log"`
	CreatedAt  time.Time `json:"created_at"`
}

func (Run) TableName() string { return "runs" }
