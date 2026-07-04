// Package store — 读取 engine 产出的每日快照 JSON(只读缓存层)。
package store

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type Store struct {
	dataDir string
}

func New(dataDir string) *Store { return &Store{dataDir: dataDir} }

// Latest 读最新快照(snapshot_latest.json)。
func (s *Store) Latest() (json.RawMessage, error) {
	return s.readFile(filepath.Join(s.dataDir, "snapshot_latest.json"))
}

// ByDate 读指定收盘日快照。
func (s *Store) ByDate(date string) (json.RawMessage, error) {
	return s.readFile(filepath.Join(s.dataDir, fmt.Sprintf("snapshot_%s.json", date)))
}

// Dates 列出所有已有快照的收盘日(倒序)。
func (s *Store) Dates() ([]string, error) {
	entries, err := os.ReadDir(s.dataDir)
	if err != nil {
		return nil, err
	}
	var dates []string
	for _, e := range entries {
		n := e.Name()
		if strings.HasPrefix(n, "snapshot_") && strings.HasSuffix(n, ".json") && n != "snapshot_latest.json" {
			dates = append(dates, strings.TrimSuffix(strings.TrimPrefix(n, "snapshot_"), ".json"))
		}
	}
	sort.Sort(sort.Reverse(sort.StringSlice(dates)))
	return dates, nil
}

func (s *Store) readFile(p string) (json.RawMessage, error) {
	b, err := os.ReadFile(p)
	if err != nil {
		return nil, err
	}
	if !json.Valid(b) {
		return nil, fmt.Errorf("快照 %s 非合法 JSON", p)
	}
	return json.RawMessage(b), nil
}
