// dropped — 「掉出推荐」状态机:策略每天重选,掉出的股票进入观察/掉出列表(带双向 CD 防抖)。
package store

import (
	"encoding/json"
	"fmt"

	"gorm.io/gorm"
)

const (
	CDDrop   = 2  // 连续缺席满 N 个快照日才判定「掉出」(防选股边缘股一天闪出)
	CDBack   = 2  // 掉出后连续回归满 N 个快照日才移出掉出列表(防一天闪回)
	KeepDays = 30 // 掉出后保留天数,超过自动清理
)

// strategySleeve 是否策略选中的腿(自定义/单股观察不参与掉出逻辑)。
func strategySleeve(sleeve string) bool { return sleeve != "custom" && sleeve != "focus" }

type droppedRow struct {
	Ticker     string
	Status     string
	MissStreak int
	BackStreak int
	AsofSeen   string
}

// UpdateDropped 在新快照 ingest 后调用:对比上一快照,推进掉出状态机。
// 幂等:每行记 asof_seen,同一 asof 重复 ingest 不重复推进。
func (s *Store) UpdateDropped(raw []byte) error {
	var p snapProbe
	if err := json.Unmarshal(raw, &p); err != nil {
		return fmt.Errorf("解析快照: %w", err)
	}
	if p.Asof == "" {
		return fmt.Errorf("快照缺 asof")
	}
	market := mkt(p.Market)
	cur := map[string]bool{}
	names := map[string]string{}
	for _, h := range p.Holdings {
		if strategySleeve(h.Sleeve) {
			cur[h.Ticker] = true
		}
	}

	// 上一快照(严格早于当前 asof)的策略持仓,含原始 holding JSON(掉出时的 context)
	var prevRaw, prevAsof string
	s.gdb.Raw(`SELECT raw::text, asof::text FROM snapshots WHERE market=? AND asof<? ORDER BY asof DESC LIMIT 1`,
		market, p.Asof).Row().Scan(&prevRaw, &prevAsof)
	prevHoldings := map[string]json.RawMessage{}
	if prevRaw != "" {
		var prev struct {
			Holdings []json.RawMessage `json:"holdings"`
		}
		if json.Unmarshal([]byte(prevRaw), &prev) == nil {
			for _, hr := range prev.Holdings {
				var h snapProbeHolding
				var nm struct {
					Name string `json:"name"`
				}
				if json.Unmarshal(hr, &h) == nil && strategySleeve(h.Sleeve) {
					_ = json.Unmarshal(hr, &nm)
					names[h.Ticker] = nm.Name
					prevHoldings[h.Ticker] = hr
				}
			}
		}
	}

	return s.gdb.Transaction(func(tx *gorm.DB) error {
		var rows []droppedRow
		if e := tx.Raw(`SELECT ticker, status, miss_streak, back_streak, asof_seen::text AS asof_seen
			FROM dropped_stocks WHERE market=?`, market).Scan(&rows).Error; e != nil {
			return e
		}
		inTable := map[string]bool{}
		for _, r := range rows {
			inTable[r.Ticker] = true
			if r.AsofSeen >= p.Asof { // 同日重复 ingest → 幂等跳过
				continue
			}
			if cur[r.Ticker] { // 重新出现在推荐中
				if r.Status == "pending" { // 观察期闪回 → 撤销
					if e := tx.Exec(`DELETE FROM dropped_stocks WHERE market=? AND ticker=?`, market, r.Ticker).Error; e != nil {
						return e
					}
				} else { // 已掉出:回归 CD 计数
					if r.BackStreak+1 >= CDBack {
						if e := tx.Exec(`DELETE FROM dropped_stocks WHERE market=? AND ticker=?`, market, r.Ticker).Error; e != nil {
							return e
						}
					} else if e := tx.Exec(`UPDATE dropped_stocks SET back_streak=?, asof_seen=?, updated_at=now()
						WHERE market=? AND ticker=?`, r.BackStreak+1, p.Asof, market, r.Ticker).Error; e != nil {
						return e
					}
				}
			} else { // 继续缺席
				if r.Status == "pending" {
					if r.MissStreak+1 >= CDDrop { // 观察期满 → 正式掉出
						if e := tx.Exec(`UPDATE dropped_stocks SET status='dropped', dropped_at=?, miss_streak=?, asof_seen=?, updated_at=now()
							WHERE market=? AND ticker=?`, p.Asof, r.MissStreak+1, p.Asof, market, r.Ticker).Error; e != nil {
							return e
						}
					} else if e := tx.Exec(`UPDATE dropped_stocks SET miss_streak=?, asof_seen=?, updated_at=now()
						WHERE market=? AND ticker=?`, r.MissStreak+1, p.Asof, market, r.Ticker).Error; e != nil {
						return e
					}
				} else { // dropped 且未回归:回归计数清零
					if e := tx.Exec(`UPDATE dropped_stocks SET back_streak=0, asof_seen=?, updated_at=now()
						WHERE market=? AND ticker=?`, p.Asof, market, r.Ticker).Error; e != nil {
						return e
					}
				}
			}
		}
		// 新缺席:上一快照在、当前不在、表里也没有 → 进入观察期
		for tk, hr := range prevHoldings {
			if cur[tk] || inTable[tk] {
				continue
			}
			var h snapProbeHolding
			_ = json.Unmarshal(hr, &h)
			if e := tx.Exec(`INSERT INTO dropped_stocks(market,ticker,name,status,last_seen,last_price,last_grade,context,miss_streak,back_streak,asof_seen)
				VALUES (?,?,?,'pending',?,?,?,?::jsonb,1,0,?)`,
				market, tk, names[tk], prevAsof, h.Price, h.Grade, string(hr), p.Asof).Error; e != nil {
				return e
			}
		}
		// 过期清理
		return tx.Exec(`DELETE FROM dropped_stocks WHERE market=? AND status='dropped' AND dropped_at < ?::date - ?::int`,
			market, p.Asof, KeepDays).Error
	})
}

// DroppedItem 掉出列表条目(price_now 为该市场最新价,可能为 0=无价)。
type DroppedItem struct {
	Ticker    string  `json:"ticker"`
	Name      string  `json:"name"`
	LastSeen  string  `json:"last_seen"`
	DroppedAt string  `json:"dropped_at"`
	LastPrice float64 `json:"last_price"`
	LastGrade int     `json:"last_grade"`
	PriceNow  float64 `json:"price_now"`
	Context   string  `json:"context"`
}

// Dropped 某市场已判定掉出的列表(新→旧),带最新现价。
func (s *Store) Dropped(market string) ([]DroppedItem, error) {
	var items []DroppedItem
	err := s.gdb.Raw(`
		SELECT d.ticker, d.name, d.last_seen::text AS last_seen, d.dropped_at::text AS dropped_at,
		       d.last_price, d.last_grade, COALESCE(p.close, 0) AS price_now, d.context::text AS context
		FROM dropped_stocks d
		LEFT JOIN LATERAL (
			SELECT close FROM prices WHERE market=d.market AND ticker=d.ticker ORDER BY date DESC LIMIT 1
		) p ON true
		WHERE d.market=? AND d.status='dropped'
		ORDER BY d.dropped_at DESC, d.ticker`, mkt(market)).Scan(&items).Error
	return items, err
}

// DroppedInfo 单只股票的掉出记录(不在掉出列表返回 nil)。explain 判断用。
func (s *Store) DroppedInfo(market, ticker string) *DroppedItem {
	var it DroppedItem
	row := s.gdb.Raw(`SELECT ticker, name, last_seen::text AS last_seen, dropped_at::text AS dropped_at,
		last_price, last_grade, 0 AS price_now, context::text AS context
		FROM dropped_stocks WHERE market=? AND ticker=? AND status='dropped'`, mkt(market), ticker).Scan(&it)
	if row.Error != nil || it.Ticker == "" {
		return nil
	}
	return &it
}
