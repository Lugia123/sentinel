package store

import (
	"fmt"
	"os"
	"testing"

	"sentinel/internal/db"
)

// TestDroppedStateMachine 集成测试:掉出/回归双 CD 状态机。
// 需本机 Postgres(同 TestMarketIsolation);未配置则跳过。
// 场景(CD_DROP=2, CD_BACK=2):
//   d1(A,B,C) d2(A,B) → C pending(miss=1)
//   d3(A,B)          → C dropped
//   d4(A,B,C)        → C back_streak=1(仍 dropped)
//   d5(A,B,C)        → C 回归,删行
//   闪烁:d1(A,B,C) d2(A,B) d3(A,B,C) → C 观察期闪回,删行(从未判定掉出)
//   幂等:同一 asof 重复 ingest 不推进 streak
func TestDroppedStateMachine(t *testing.T) {
	dsn := os.Getenv("SENTINEL_DB_DSN")
	if dsn == "" {
		dsn = "host=localhost port=5432 user=sentinel password=sentinel dbname=sentinel_test sslmode=disable"
	}
	gdb, err := db.Connect(dsn)
	if err != nil {
		t.Skipf("跳过(无DB): %v", err)
	}
	s := New(gdb)
	cleanup := func() {
		gdb.Exec(`DELETE FROM snapshots WHERE market='us' AND asof BETWEEN '1998-01-01' AND '1998-01-31'`)
		gdb.Exec(`DELETE FROM dropped_stocks WHERE market='us' AND ticker IN ('TSTA','TSTB','TSTC','TSTD')`)
	}
	cleanup()
	defer cleanup()

	snap := func(asof string, tickers ...string) []byte {
		hs := ""
		for i, tk := range tickers {
			if i > 0 {
				hs += ","
			}
			hs += fmt.Sprintf(`{"ticker":"%s","sleeve":"momentum","price":10,"grade":1,"action":"持有"}`, tk)
		}
		return []byte(fmt.Sprintf(`{"market":"us","asof":"%s","capital":4000,"risk_light":{"level":"green","exposure":1},"portfolio":{"gross_exposure":1,"cash_pct":0},"holdings":[%s]}`, asof, hs))
	}
	ingest := func(asof string, tickers ...string) {
		raw := snap(asof, tickers...)
		if _, e := s.IngestSnapshot(raw); e != nil {
			t.Fatalf("ingest %s: %v", asof, e)
		}
		if e := s.UpdateDropped(raw); e != nil {
			t.Fatalf("UpdateDropped %s: %v", asof, e)
		}
	}
	getRow := func(tk string) (status string, miss, back int, ok bool) {
		row := gdb.Raw(`SELECT status, miss_streak, back_streak FROM dropped_stocks WHERE market='us' AND ticker=?`, tk).Row()
		if err := row.Scan(&status, &miss, &back); err != nil {
			return "", 0, 0, false
		}
		return status, miss, back, true
	}

	// ── 主流程:掉出 CD ──
	ingest("1998-01-01", "TSTA", "TSTB", "TSTC")
	ingest("1998-01-02", "TSTA", "TSTB") // C 缺席 1 天 → pending
	if st, miss, _, ok := getRow("TSTC"); !ok || st != "pending" || miss != 1 {
		t.Fatalf("d2 后 TSTC 应 pending/miss=1,got %s/%d ok=%v", st, miss, ok)
	}
	// 幂等:同 asof 重复 ingest 不推进
	ingest("1998-01-02", "TSTA", "TSTB")
	if _, miss, _, _ := getRow("TSTC"); miss != 1 {
		t.Fatalf("同 asof 重复 ingest 后 miss 应仍=1,got %d", miss)
	}
	ingest("1998-01-05", "TSTA", "TSTB") // C 缺席第 2 个快照 → dropped
	if st, _, _, ok := getRow("TSTC"); !ok || st != "dropped" {
		t.Fatalf("d3 后 TSTC 应 dropped,got %s ok=%v", st, ok)
	}
	// ── 回归 CD ──
	ingest("1998-01-06", "TSTA", "TSTB", "TSTC") // 回归第 1 天:back=1,仍在掉出列表
	if st, _, back, ok := getRow("TSTC"); !ok || st != "dropped" || back != 1 {
		t.Fatalf("回归1天后应 dropped/back=1,got %s/%d ok=%v", st, back, ok)
	}
	ingest("1998-01-07", "TSTA", "TSTB", "TSTC") // 回归第 2 天:删行
	if _, _, _, ok := getRow("TSTC"); ok {
		t.Fatalf("回归满 CD 后应删行,但仍存在")
	}
	// ── 回归中断:back 清零 ──
	ingest("1998-01-08", "TSTA", "TSTB")         // C 又缺席 → pending
	ingest("1998-01-09", "TSTA", "TSTB")         // → dropped
	ingest("1998-01-12", "TSTA", "TSTB", "TSTC") // back=1
	ingest("1998-01-13", "TSTA", "TSTB")         // 中断 → back=0
	if st, _, back, ok := getRow("TSTC"); !ok || st != "dropped" || back != 0 {
		t.Fatalf("回归中断后应 dropped/back=0,got %s/%d ok=%v", st, back, ok)
	}
	gdb.Exec(`DELETE FROM dropped_stocks WHERE market='us' AND ticker='TSTC'`)
	// ── 闪烁:观察期内回来 → 撤销,不算掉出 ──
	ingest("1998-01-14", "TSTA", "TSTB", "TSTC")
	ingest("1998-01-15", "TSTA", "TSTB") // pending
	ingest("1998-01-16", "TSTA", "TSTB", "TSTC")
	if _, _, _, ok := getRow("TSTC"); ok {
		t.Fatalf("观察期闪回后应删行(不判掉出),但仍存在")
	}
	// ── 自定义股不参与:TSTD 只以 custom 身份出现过,消失后不进掉出表 ──
	rawD1 := []byte(`{"market":"us","asof":"1998-01-19","capital":4000,"risk_light":{"level":"green","exposure":1},"portfolio":{"gross_exposure":1,"cash_pct":0},"holdings":[{"ticker":"TSTA","sleeve":"momentum","price":10,"grade":1,"action":"持有"},{"ticker":"TSTD","sleeve":"custom","price":10,"grade":1,"action":"持有"}]}`)
	if _, e := s.IngestSnapshot(rawD1); e != nil {
		t.Fatal(e)
	}
	_ = s.UpdateDropped(rawD1)
	ingest("1998-01-20", "TSTA") // TSTD(custom) 消失,但不该进掉出表
	if _, _, _, ok := getRow("TSTD"); ok {
		t.Fatalf("custom 股不应进入掉出状态机")
	}
}
