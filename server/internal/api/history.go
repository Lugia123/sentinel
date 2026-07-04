package api

import (
	"encoding/csv"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
)

// history 返回某 ticker 最近 N 日 {date,close,sma20,sma50,sma200}(均线由收盘价算,原CSV只有OHLCV)。
func (a *API) history(w http.ResponseWriter, r *http.Request) {
	ticker := r.URL.Query().Get("ticker")
	if ticker == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "缺 ticker"})
		return
	}
	n := 120
	if v := r.URL.Query().Get("n"); v != "" {
		if x, err := strconv.Atoi(v); err == nil && x > 0 && x <= 500 {
			n = x
		}
	}
	f, err := os.Open(filepath.Join(a.engineDir, "data", ticker+".csv"))
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": ticker + " 无历史数据"})
		return
	}
	defer f.Close()
	rows, err := csv.NewReader(f).ReadAll()
	if err != nil || len(rows) < 2 {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": "读取失败"})
		return
	}
	col := map[string]int{}
	for i, name := range rows[0] {
		col[name] = i
	}
	di, ci := col["date"], col["close"]
	dates := make([]string, 0, len(rows)-1)
	closes := make([]float64, 0, len(rows)-1)
	for _, row := range rows[1:] {
		if ci >= len(row) {
			continue
		}
		c, err := strconv.ParseFloat(row[ci], 64)
		if err != nil {
			continue
		}
		dates = append(dates, row[di])
		closes = append(closes, c)
	}
	sma := func(i, k int) *float64 { // i 处 trailing k 日均线
		if i+1 < k {
			return nil
		}
		var s float64
		for j := i - k + 1; j <= i; j++ {
			s += closes[j]
		}
		v := s / float64(k)
		return &v
	}
	type pt struct {
		Date   string   `json:"date"`
		Close  float64  `json:"close"`
		Sma20  *float64 `json:"sma20"`
		Sma50  *float64 `json:"sma50"`
		Sma200 *float64 `json:"sma200"`
	}
	start := 0
	if len(closes)-n > 0 {
		start = len(closes) - n
	}
	var out []pt
	for i := start; i < len(closes); i++ {
		out = append(out, pt{Date: dates[i], Close: closes[i], Sma20: sma(i, 20), Sma50: sma(i, 50), Sma200: sma(i, 200)})
	}
	writeJSON(w, http.StatusOK, map[string]any{"ticker": ticker, "history": out})
}
