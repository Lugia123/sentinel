// Package datasource — 外部数据源凭证(host + api key)的集中管理。
// 目前只有 tushare 一个需凭证的源(A股 事件/红利/资金流腿;月卡 token 会过期)。
// 真源 = DB settings 表(管理员在「系统管理 · 数据源」里维护);server/.env 仅作回退,
// 便于老部署平滑迁移(库里没配 → 仍用 .env 跑;配过一次后以库为准)。
// 保存后立即注入进程 env,Python 引擎子进程(RunPython 继承父进程环境)即刻用上,无需重启后端。
package datasource

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"
)

// settings 表键 / 引擎读的环境变量名(见 engine/ts_refresh.py)。
const (
	KeyTSURL   = "ts_url"
	KeyTSToken = "ts_token"
	EnvTSURL   = "SENTINEL_TS_URL"
	EnvTSToken = "SENTINEL_TS_TOKEN"

	DefaultTSURL = "http://api.tushare.pro"
)

// Store 只需 settings 读写(store.Store 满足)。
type Store interface {
	GetSetting(key string) string
	SetSetting(key, value string) error
}

// Tushare 一个数据源的凭证:接口地址 + api key。
type Tushare struct {
	URL   string `json:"url"`
	Token string `json:"token"`
}

func (c Tushare) Enabled() bool { return c.URL != "" && c.Token != "" }

// Load 读当前生效凭证:DB 优先,逐字段回退 .env。
func Load(st Store) Tushare {
	return Tushare{
		URL:   firstNonEmpty(st.GetSetting(KeyTSURL), os.Getenv(EnvTSURL)),
		Token: firstNonEmpty(st.GetSetting(KeyTSToken), os.Getenv(EnvTSToken)),
	}
}

// Source 标注每个字段当前取自哪儿("db" / "env" / ""),供前端提示配置来源。
func Source(st Store) (urlSrc, tokenSrc string) {
	return srcOf(st.GetSetting(KeyTSURL), os.Getenv(EnvTSURL)), srcOf(st.GetSetting(KeyTSToken), os.Getenv(EnvTSToken))
}

// Save 写入 DB 并立即注入进程 env。Token 留空 = 保留原值(前端不回显密钥,同 SMTP 口径)。
func Save(st Store, c Tushare) error {
	if err := st.SetSetting(KeyTSURL, strings.TrimSpace(c.URL)); err != nil {
		return err
	}
	if t := strings.TrimSpace(c.Token); t != "" {
		if err := st.SetSetting(KeyTSToken, t); err != nil {
			return err
		}
	}
	Apply(st)
	return nil
}

// Apply 把当前生效凭证注入进程环境变量,供 Python 引擎子进程继承。
// 后端启动时调一次;管理员保存后再调一次(热生效)。
func Apply(st Store) Tushare {
	c := Load(st)
	if c.URL != "" {
		os.Setenv(EnvTSURL, c.URL)
	}
	if c.Token != "" {
		os.Setenv(EnvTSToken, c.Token)
	}
	return c
}

// Test 用给定凭证真打一次 tushare(trade_cal,权限门槛最低的接口),验证 host 可达 + token 有效。
// 成功返回一句人话摘要;失败返回 tushare 的原始 msg(如 token 无效/积分不足),便于管理员对症。
func Test(c Tushare) (string, error) {
	if !c.Enabled() {
		return "", fmt.Errorf("接口地址与 token 都要填")
	}
	day := time.Now().Format("20060102")
	body, _ := json.Marshal(map[string]any{
		"api_name": "trade_cal",
		"token":    c.Token,
		"params":   map[string]string{"exchange": "SSE", "start_date": day, "end_date": day},
		"fields":   "cal_date,is_open",
	})
	req, err := http.NewRequest(http.MethodPost, c.URL, bytes.NewReader(body))
	if err != nil {
		return "", fmt.Errorf("接口地址无效: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := (&http.Client{Timeout: 20 * time.Second}).Do(req)
	if err != nil {
		return "", fmt.Errorf("连不上数据源: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("数据源返回 HTTP %d", resp.StatusCode)
	}
	var out struct {
		Code int    `json:"code"`
		Msg  string `json:"msg"`
		Data struct {
			Items [][]any `json:"items"`
		} `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "", fmt.Errorf("响应不是预期的 tushare 格式(检查接口地址): %v", err)
	}
	if out.Code != 0 {
		return "", fmt.Errorf("token 校验失败: %s", strings.TrimSpace(out.Msg))
	}
	return fmt.Sprintf("连接正常 — trade_cal 返回 %d 行(host 可达、token 有效)", len(out.Data.Items)), nil
}

// Mask 打码回显:保留首4尾4,中间星号。空则返回空。
func Mask(s string) string {
	if s == "" {
		return ""
	}
	if len(s) <= 8 {
		return strings.Repeat("*", len(s))
	}
	return s[:4] + strings.Repeat("*", 6) + s[len(s)-4:]
}

func firstNonEmpty(a, b string) string {
	if strings.TrimSpace(a) != "" {
		return strings.TrimSpace(a)
	}
	return strings.TrimSpace(b)
}

func srcOf(dbv, envv string) string {
	switch {
	case strings.TrimSpace(dbv) != "":
		return "db"
	case strings.TrimSpace(envv) != "":
		return "env"
	}
	return ""
}
