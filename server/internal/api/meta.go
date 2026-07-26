package api

import (
	"encoding/csv"
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"sync"
)

var (
	metaOnce  sync.Once
	metaCache json.RawMessage

	cnNameOnce sync.Once
	cnNames    map[string]string
)

// meta 返回 ticker → {cn, sector} 映射(engine/ticker_meta.json),前端查中文名+板块(美股)。
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

// cnNameMap A股 code → 中文名(engine/data_cn_meta/universe.csv,含退市股,一次加载)。
func (a *API) cnNameMap() map[string]string {
	cnNameOnce.Do(func() {
		cnNames = map[string]string{}
		f, err := os.Open(filepath.Join(a.engineDir, "data_cn_meta", "universe.csv"))
		if err != nil {
			return
		}
		defer f.Close()
		rows, err := csv.NewReader(f).ReadAll()
		if err != nil || len(rows) < 2 {
			return
		}
		ci, ni := -1, -1
		for i, name := range rows[0] {
			switch name {
			case "code":
				ci = i
			case "code_name":
				ni = i
			}
		}
		if ci < 0 || ni < 0 {
			return
		}
		for _, row := range rows[1:] {
			if ci < len(row) && ni < len(row) {
				cnNames[row[ci]] = row[ni]
			}
		}
	})
	return cnNames
}

// universe 返回当前市场全部【可分析】股票(prices 表里有价格的),带中文名/板块(有则填)。
// 供「添加自定义股票」搜索。?market=cn 时只列 A股,中文名从 universe.csv 取。
func (a *API) universe(w http.ResponseWriter, r *http.Request) {
	market := mktParam(r)
	var tickers []string
	a.gdb.Raw(`SELECT DISTINCT ticker FROM prices WHERE market=? ORDER BY ticker`, market).Scan(&tickers)
	out := make([]map[string]any, 0, len(tickers))
	if market == "cn" {
		names := a.cnNameMap()
		for _, tk := range tickers {
			item := map[string]any{"ticker": tk}
			if nm, ok := names[tk]; ok && nm != "" {
				item["cn"] = nm
			}
			out = append(out, item)
		}
	} else {
		var m map[string]struct {
			CN     string `json:"cn"`
			Sector string `json:"sector"`
		}
		if b, err := os.ReadFile(filepath.Join(a.engineDir, "ticker_meta.json")); err == nil {
			_ = json.Unmarshal(b, &m)
		}
		for _, tk := range tickers {
			item := map[string]any{"ticker": tk}
			if v, ok := m[tk]; ok {
				item["cn"] = v.CN
				item["sector"] = v.Sector
			}
			out = append(out, item)
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"universe": out})
}
