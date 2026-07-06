package api

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"sync"
)

var (
	metaOnce  sync.Once
	metaCache json.RawMessage
)

// meta 返回 ticker → {cn, sector} 映射(engine/ticker_meta.json),前端查中文名+板块。
func (a *API) meta(w http.ResponseWriter, r *http.Request) {
	metaOnce.Do(func() {
		b, err := os.ReadFile(filepath.Join(a.engineDir, "ticker_meta.json"))
		if err == nil && json.Valid(b) {
			metaCache = b
		} else {
			metaCache = json.RawMessage("{}")
		}
	})
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_, _ = w.Write(metaCache)
}

// universe 返回全部【可分析】股票(数据池里有价格的,约1393只),带中文名/板块(有则填)。
// 供「添加自定义股票」搜索——不再只限98只大盘股。
func (a *API) universe(w http.ResponseWriter, r *http.Request) {
	var tickers []string
	a.gdb.Raw(`SELECT DISTINCT ticker FROM prices ORDER BY ticker`).Scan(&tickers)
	// 读中文名映射(有的才填)
	var m map[string]struct {
		CN     string `json:"cn"`
		Sector string `json:"sector"`
	}
	if b, err := os.ReadFile(filepath.Join(a.engineDir, "ticker_meta.json")); err == nil {
		_ = json.Unmarshal(b, &m)
	}
	out := make([]map[string]any, 0, len(tickers))
	for _, tk := range tickers {
		item := map[string]any{"ticker": tk}
		if v, ok := m[tk]; ok {
			item["cn"] = v.CN
			item["sector"] = v.Sector
		}
		out = append(out, item)
	}
	writeJSON(w, http.StatusOK, map[string]any{"universe": out})
}
