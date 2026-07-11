// Package scheduler — 每 N 小时自动:刷新数据 + 跑双市场引擎 + ingest。
// 间隔可由管理员在系统设置里维护(settings.schedule_interval_hours);EOD 数据每天更一次,
// 多跑=兜底重试(确保可靠抓到当天收盘)。ingest 幂等(upsert),多次执行安全。
package scheduler

import (
	"log"
	"strconv"
	"time"

	"sentinel/internal/engine"
	"sentinel/internal/pipeline"
	"sentinel/internal/store"
)

// MARKETS 每周期跑的市场(各自 EOD 刷新+重算)。
var MARKETS = []string{"us", "cn"}

// SettingKey 管理员可维护的调度间隔(小时)。
const SettingKey = "schedule_interval_hours"

type Scheduler struct {
	rn       *engine.Runner
	st       *store.Store
	dataDir  string
	capital  string
	defHours int // 设置缺失时的默认间隔(小时)
}

// New defHours=默认间隔小时(设置表无值时用);解析历史 "HH:MM" 兼容为默认 4h。
func New(rn *engine.Runner, st *store.Store, dataDir, capital, schedule string) *Scheduler {
	def := 4
	if n, err := strconv.Atoi(schedule); err == nil && n >= 1 && n <= 24 {
		def = n // 支持 SENTINEL_SCHEDULE="4"(小时)
	}
	return &Scheduler{rn: rn, st: st, dataDir: dataDir, capital: capital, defHours: def}
}

// intervalHours 实时读设置(管理员改后下个周期生效),clamp [1,24]。
func (s *Scheduler) intervalHours() int {
	if v := s.st.GetSetting(SettingKey); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n >= 1 && n <= 24 {
			return n
		}
	}
	return s.defHours
}

// Start 启动后台调度(非阻塞)。
func (s *Scheduler) Start() {
	go func() {
		// 启动自愈:任一市场无快照则补跑一次
		need := false
		for _, m := range MARKETS {
			if _, err := s.st.Latest(m); err != nil {
				need = true
			}
		}
		if need {
			log.Printf("[scheduler] 库中缺快照,启动补跑…")
			s.run()
		}
		for {
			h := s.intervalHours()
			d := time.Duration(h) * time.Hour
			log.Printf("[scheduler] 下次自动运行:%dh 后(每 %dh 跑一次,双市场 %v)", h, h, MARKETS)
			time.Sleep(d)
			s.run()
		}
	}()
}

// run 每周期:逐市场 刷新数据(S3 接) + 跑引擎 + ingest(幂等 upsert)。
func (s *Scheduler) run() {
	for _, m := range MARKETS {
		s.refreshData(m) // 增量刷新(新交易日才拉;S2/S3 实现)
		res, err := pipeline.RunAndIngest(s.rn, s.st, s.dataDir, m, "latest", s.capital, true, nil)
		if err != nil {
			log.Printf("[scheduler] [%s] 运行失败:%v", m, err)
			continue
		}
		log.Printf("[scheduler] [%s] 完成:snapshot_id=%d 价格%d 条", m, res.SnapshotID, res.NPrices)
	}
}
