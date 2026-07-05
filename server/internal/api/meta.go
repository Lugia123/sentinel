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
