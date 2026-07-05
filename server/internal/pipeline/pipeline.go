// Package pipeline — 跑引擎 + ingest 入库的共享流程(/api/run 与 定时任务 共用)。
package pipeline

import (
	"fmt"
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
func RunAndIngest(rn *engine.Runner, st *store.Store, dataDir, asof, capital string, withSY bool, track []string) (Result, error) {
	out, err := rn.RunDaily(asof, capital, withSY, track)
	if err != nil {
		return Result{Log: out}, err
	}
	snapRaw, e1 := os.ReadFile(filepath.Join(dataDir, "snapshot_latest.json"))
	priceRaw, e2 := os.ReadFile(filepath.Join(dataDir, "prices_latest.json"))
	if e1 != nil || e2 != nil {
		return Result{Log: out}, fmt.Errorf("引擎产出读取失败")
	}
	sid, e3 := st.IngestSnapshot(snapRaw)
	if e3 != nil {
		return Result{Log: out}, fmt.Errorf("ingest 快照: %w", e3)
	}
	n, e4 := st.IngestPrices(priceRaw)
	if e4 != nil {
		return Result{Log: out}, fmt.Errorf("ingest 价格: %w", e4)
	}
	return Result{SnapshotID: sid, NPrices: n, Log: out}, nil
}
