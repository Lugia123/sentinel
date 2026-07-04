// Package db — PostgreSQL 连接(gorm)+ 编号 SQL 迁移运行器(对齐 Tinia)。
package db

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

// Connect 打开 gorm 连接(静默日志)。
func Connect(dsn string) (*gorm.DB, error) {
	return gorm.Open(postgres.Open(dsn), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
}

// Migrate 应用 migrationsDir 下未执行的 *.up.sql(按文件名排序),记录进 schema_migrations。
func Migrate(gdb *gorm.DB, migrationsDir string) error {
	if err := gdb.Exec(`CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())`).Error; err != nil {
		return err
	}
	applied := map[string]bool{}
	var rows []struct{ Version string }
	gdb.Raw(`SELECT version FROM schema_migrations`).Scan(&rows)
	for _, r := range rows {
		applied[r.Version] = true
	}
	entries, err := os.ReadDir(migrationsDir)
	if err != nil {
		return fmt.Errorf("读迁移目录 %s: %w", migrationsDir, err)
	}
	var ups []string
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".up.sql") {
			ups = append(ups, e.Name())
		}
	}
	sort.Strings(ups)
	for _, name := range ups {
		ver := strings.TrimSuffix(name, ".up.sql")
		if applied[ver] {
			continue
		}
		sqlBytes, err := os.ReadFile(filepath.Join(migrationsDir, name))
		if err != nil {
			return err
		}
		if err := gdb.Exec(string(sqlBytes)).Error; err != nil {
			return fmt.Errorf("迁移 %s 失败: %w", name, err)
		}
		if err := gdb.Exec(`INSERT INTO schema_migrations(version) VALUES (?)`, ver).Error; err != nil {
			return err
		}
	}
	return nil
}
