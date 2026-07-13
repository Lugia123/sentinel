// Package pipeline — 跑引擎 + ingest 入库的共享流程(/api/run 与 定时任务 共用)。
package pipeline

import (
	"fmt"
	"log"
	"os"
	"path/filepath"

	"sentinel/internal/engine"
	"sentinel/internal/store"
)

type Result struct {
	SnapshotID int64
	NPrices    int
	Log        string
}

// RunAndIngest 跑 run_daily.py 产 JSON → ingest snapshots/holdings/prices 入 PG。
// market: us(snapshot_latest.json)/ cn(snapshot_cn_latest.json)。
func RunAndIngest(rn *engine.Runner, st *store.Store, dataDir, market, asof, capital string, withSY bool, track []string) (Result, error) {
	out, err := rn.RunDaily(market, asof, capital, withSY, track)
	if err != nil {
		return Result{Log: out}, err
	}
	suffix := ""
	if market == "cn" {
		suffix = "_cn"
	}
	snapRaw, e1 := os.ReadFile(filepath.Join(dataDir, "snapshot"+suffix+"_latest.json"))
	priceRaw, e2 := os.ReadFile(filepath.Join(dataDir, "prices"+suffix+"_latest.json"))
	if e1 != nil || e2 != nil {
		return Result{Log: out}, fmt.Errorf("引擎产出读取失败")
	}
	sid, e3 := st.IngestSnapshot(snapRaw)
	if e3 != nil {
		return Result{Log: out}, fmt.Errorf("ingest 快照: %w", e3)
	}
	if e := st.UpdateDropped(snapRaw); e != nil { // 掉出状态机(失败不阻断快照入库)
		log.Printf("[pipeline] 掉出状态机失败(快照不受影响): %v", e)
	}
	n, e4 := st.IngestPrices(priceRaw)
	if e4 != nil {
		return Result{Log: out}, fmt.Errorf("ingest 价格: %w", e4)
	}
	return Result{SnapshotID: sid, NPrices: n, Log: out}, nil
}
