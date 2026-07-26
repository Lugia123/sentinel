// ingest_risklight — 把 backfill_risklight.py 产出的风险灯历史 JSON 灌进 risk_light_history(upsert)。
// 用法:SENTINEL_DB_DSN="..." ingest_risklight <rl_hist.json>
package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"

	"sentinel/internal/db"
)

type rec struct {
	Market    string   `json:"market"`
	Asof      string   `json:"asof"`
	Level     string   `json:"level"`
	Exposure  float64  `json:"exposure"`
	Breadth   *float64 `json:"breadth"`
	BreadthMA *float64 `json:"breadth_ma"`
	Crowd     *float64 `json:"crowd"`
	AmountRat *float64 `json:"amount_ratio"`
	SpyVol    *float64 `json:"spy_vol"`
	Diverge   *bool    `json:"diverge"`
}

func main() {
	if len(os.Args) < 2 {
		log.Fatal("用法: ingest_risklight <rl_hist.json>")
	}
	raw, err := os.ReadFile(os.Args[1])
	if err != nil {
		log.Fatal(err)
	}
	var rows []rec
	if err := json.Unmarshal(raw, &rows); err != nil {
		log.Fatal(err)
	}
	gdb, err := db.Connect(os.Getenv("SENTINEL_DB_DSN"))
	if err != nil {
		log.Fatal(err)
	}
	n := 0
	for _, r := range rows {
		if e := gdb.Exec(`INSERT INTO risk_light_history
			(market,asof,level,exposure,breadth,breadth_ma,crowd,amount_ratio,spy_vol,diverge)
			VALUES (?,?,?,?,?,?,?,?,?,?)
			ON CONFLICT (market,asof) DO UPDATE SET level=EXCLUDED.level, exposure=EXCLUDED.exposure,
			  breadth=EXCLUDED.breadth, breadth_ma=EXCLUDED.breadth_ma, crowd=EXCLUDED.crowd,
			  amount_ratio=EXCLUDED.amount_ratio, spy_vol=EXCLUDED.spy_vol, diverge=EXCLUDED.diverge`,
			r.Market, r.Asof, r.Level, r.Exposure, r.Breadth, r.BreadthMA, r.Crowd, r.AmountRat, r.SpyVol, r.Diverge).Error; e != nil {
			log.Fatalf("upsert %s %s: %v", r.Market, r.Asof, e)
		}
		n++
	}
	fmt.Printf("灌入 risk_light_history: %d 行\n", n)
}
