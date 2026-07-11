// Package scheduler — 每日定点自动跑引擎+ingest;启动时若库中无当日快照则自愈补跑。
// 让策略后台自动运行,用户平时不用手动点(仅当天缺失时用「重算」按钮)。
package scheduler

import (
	"log"
	"time"

	"sentinel/internal/engine"
	"sentinel/internal/pipeline"
	"sentinel/internal/store"
)

type Scheduler struct {
	rn      *engine.Runner
	st      *store.Store
	dataDir string
	capital string
	hh, mm  int // 每日运行时刻(本地时间)
}

// New at="HH:MM"(本地时间,默认 05:30 = 美股收盘后)。解析失败用默认。
func New(rn *engine.Runner, st *store.Store, dataDir, capital, at string) *Scheduler {
	hh, mm := 5, 30
	if len(at) == 5 && at[2] == ':' {
		if h, m := int(at[0]-'0')*10+int(at[1]-'0'), int(at[3]-'0')*10+int(at[4]-'0'); h < 24 && m < 60 {
			hh, mm = h, m
		}
	}
	return &Scheduler{rn: rn, st: st, dataDir: dataDir, capital: capital, hh: hh, mm: mm}
}

// Start 启动后台调度(非阻塞)。
func (s *Scheduler) Start() {
	go func() {
		// 启动自愈:库中无快照则补跑一次
		if _, err := s.st.Latest("us"); err != nil {
			log.Printf("[scheduler] 库中无快照,启动补跑…")
			s.run()
		}
		for {
			d := s.until()
			log.Printf("[scheduler] 下次自动运行:%s 后(每日 %02d:%02d)", d.Truncate(time.Second), s.hh, s.mm)
			time.Sleep(d)
			s.run()
		}
	}()
}

func (s *Scheduler) until() time.Duration {
	now := time.Now()
	next := time.Date(now.Year(), now.Month(), now.Day(), s.hh, s.mm, 0, 0, now.Location())
	if !next.After(now) {
		next = next.Add(24 * time.Hour)
	}
	return time.Until(next)
}

func (s *Scheduler) run() {
	log.Printf("[scheduler] 自动运行引擎 …")
	// TODO(live-data): 此处先跑现有数据;接入 yfinance 每日刷新后才会拿到新交易日。
	// 共享快照=策略持仓(不含任何用户的自定义股;自定义股按用户在读取时合并)
	res, err := pipeline.RunAndIngest(s.rn, s.st, s.dataDir, "us", "latest", s.capital, true, nil)
	if err != nil {
		log.Printf("[scheduler] 运行失败:%v", err)
		return
	}
	log.Printf("[scheduler] 完成:snapshot_id=%d 价格%d 条", res.SnapshotID, res.NPrices)
}
