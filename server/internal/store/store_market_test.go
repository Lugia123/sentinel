package store

import (
	"encoding/json"
	"os"
	"testing"

	"sentinel/internal/db"
)

// TestMarketIsolation 集成测试:ingest us+cn 双市场快照 → 按市场查询隔离。
// 需 SENTINEL_DB_DSN(本机 Postgres);未配置则跳过。
func TestMarketIsolation(t *testing.T) {
	dsn := os.Getenv("SENTINEL_DB_DSN")
	if dsn == "" {
		dsn = "host=localhost port=5432 user=sentinel password=sentinel dbname=sentinel_test sslmode=disable"
	}
	gdb, err := db.Connect(dsn)
	if err != nil {
		t.Skipf("跳过(无DB): %v", err)
	}
	s := New(gdb)
	// 清理测试残留
	cleanup := func() {
		gdb.Exec(`DELETE FROM snapshots WHERE asof IN ('1999-01-01','1999-01-02')`)
	}
	cleanup()
	defer cleanup()

	usSnap := `{"market":"us","asof":"1999-01-01","capital":4000,"risk_light":{"level":"green","exposure":1.0},"portfolio":{"gross_exposure":1.0,"cash_pct":0},"holdings":[{"ticker":"AAPL","sleeve":"momentum","price":100,"grade":2,"action":"持有"}]}`
	cnSnap := `{"market":"cn","asof":"1999-01-02","capital":100000,"risk_light":{"level":"red","exposure":0.0},"portfolio":{"gross_exposure":0.0,"cash_pct":1.0},"holdings":[{"ticker":"sh.688060","sleeve":"smallcap","price":33.5,"grade":-3,"action":"持有"},{"ticker":"sh.603301","sleeve":"event","price":20,"grade":0,"action":"持有"}]}`

	if _, err := s.IngestSnapshot([]byte(usSnap)); err != nil {
		t.Fatalf("ingest us: %v", err)
	}
	if _, err := s.IngestSnapshot([]byte(cnSnap)); err != nil {
		t.Fatalf("ingest cn: %v", err)
	}

	// 按市场查最新,验证隔离
	check := func(market, wantAsof, wantLevel string, wantHoldings int) {
		raw, err := s.Latest(market)
		if err != nil {
			t.Fatalf("Latest(%s): %v", market, err)
		}
		var snap struct {
			Market    string `json:"market"`
			Asof      string `json:"asof"`
			RiskLight struct{ Level string } `json:"risk_light"`
			Holdings  []any  `json:"holdings"`
		}
		json.Unmarshal(raw, &snap)
		if snap.Market != market {
			t.Errorf("[%s] market=%s, want %s", market, snap.Market, market)
		}
		if snap.Asof != wantAsof {
			t.Errorf("[%s] asof=%s, want %s(市场隔离失败?)", market, snap.Asof, wantAsof)
		}
		if snap.RiskLight.Level != wantLevel {
			t.Errorf("[%s] risk=%s, want %s", market, snap.RiskLight.Level, wantLevel)
		}
		if len(snap.Holdings) != wantHoldings {
			t.Errorf("[%s] holdings=%d, want %d", market, len(snap.Holdings), wantHoldings)
		}
	}
	// 注:1999 测试日是历史最早,不会被真实数据的 latest 覆盖——用 ByDate 更稳
	checkByDate := func(market, asof, wantLevel string, wantHoldings int) {
		raw, err := s.ByDate(market, asof)
		if err != nil {
			t.Fatalf("ByDate(%s,%s): %v", market, asof, err)
		}
		var snap struct {
			Market    string `json:"market"`
			RiskLight struct{ Level string } `json:"risk_light"`
			Holdings  []any  `json:"holdings"`
		}
		json.Unmarshal(raw, &snap)
		if snap.Market != market {
			t.Errorf("[%s] market=%s, want %s", market, snap.Market, market)
		}
		if snap.RiskLight.Level != wantLevel {
			t.Errorf("[%s@%s] risk=%s, want %s", market, asof, snap.RiskLight.Level, wantLevel)
		}
		if len(snap.Holdings) != wantHoldings {
			t.Errorf("[%s@%s] holdings=%d, want %d", market, asof, len(snap.Holdings), wantHoldings)
		}
	}
	_ = check
	checkByDate("us", "1999-01-01", "green", 1)
	checkByDate("cn", "1999-01-02", "red", 2)

	// 交叉验证:cn 市场查不到 us 的 asof(隔离)
	if _, err := s.ByDate("cn", "1999-01-01"); err == nil {
		t.Error("隔离失败:cn 市场查到了 us 的 1999-01-01 快照")
	}
	// holdings 表带 market
	var nCn int64
	gdb.Raw(`SELECT count(*) FROM holdings WHERE market='cn' AND ticker LIKE 'sh.%'`).Row().Scan(&nCn)
	if nCn < 2 {
		t.Errorf("holdings market=cn 计数 %d, want>=2", nCn)
	}
}
