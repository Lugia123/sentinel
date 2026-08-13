package datasource

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

// fakeStore 内存 settings,替代 PG。
type fakeStore struct{ m map[string]string }

func newFake() *fakeStore                         { return &fakeStore{m: map[string]string{}} }
func (f *fakeStore) GetSetting(k string) string   { return f.m[k] }
func (f *fakeStore) SetSetting(k, v string) error { f.m[k] = v; return nil }

// DB 空 → 回退 .env;DB 有值 → 覆盖 .env(管理员配置优先)。
func TestLoadPrefersDBOverEnv(t *testing.T) {
	os.Setenv(EnvTSURL, "http://env.example")
	os.Setenv(EnvTSToken, "envtoken")
	defer func() { os.Unsetenv(EnvTSURL); os.Unsetenv(EnvTSToken) }()

	st := newFake()
	if c := Load(st); c.URL != "http://env.example" || c.Token != "envtoken" {
		t.Fatalf("库空应回退 env,得到 %+v", c)
	}
	if u, tk := Source(st); u != "env" || tk != "env" {
		t.Fatalf("来源应为 env,得到 %s/%s", u, tk)
	}

	if err := Save(st, Tushare{URL: "http://db.example", Token: "dbtoken"}); err != nil {
		t.Fatal(err)
	}
	c := Load(st)
	if c.URL != "http://db.example" || c.Token != "dbtoken" {
		t.Fatalf("库有值应覆盖 env,得到 %+v", c)
	}
	if u, tk := Source(st); u != "db" || tk != "db" {
		t.Fatalf("来源应为 db,得到 %s/%s", u, tk)
	}
	// Save 已注入进程 env,Python 子进程(继承环境)即刻用上新凭证
	if os.Getenv(EnvTSURL) != "http://db.example" || os.Getenv(EnvTSToken) != "dbtoken" {
		t.Fatalf("保存后应注入进程 env,得到 %s/%s", os.Getenv(EnvTSURL), os.Getenv(EnvTSToken))
	}
}

// token 留空 = 保留原值(前端不回显密钥);URL 可被改空(回落 env)。
func TestSaveEmptyTokenKeepsOld(t *testing.T) {
	os.Unsetenv(EnvTSURL)
	os.Unsetenv(EnvTSToken)
	st := newFake()
	_ = Save(st, Tushare{URL: "http://a", Token: "secret1"})
	_ = Save(st, Tushare{URL: "http://b", Token: "  "}) // 空白 token 视为不改
	c := Load(st)
	if c.Token != "secret1" {
		t.Fatalf("空 token 应保留原值,得到 %q", c.Token)
	}
	if c.URL != "http://b" {
		t.Fatalf("URL 应更新为 http://b,得到 %q", c.URL)
	}
}

func TestMask(t *testing.T) {
	for _, tc := range []struct{ in, want string }{
		{"", ""},
		{"abc", "***"},
		{"abcdefghijkl", "abcd******ijkl"},
	} {
		if got := Mask(tc.in); got != tc.want {
			t.Fatalf("Mask(%q)=%q 期望 %q", tc.in, got, tc.want)
		}
	}
	if strings.Contains(Mask("supersecrettoken"), "secret") {
		t.Fatal("打码后不应残留密钥中段")
	}
}

// Test():tushare code==0 视为通过;code!=0 把 msg 原样带回(如 token 过期)。
func TestTestConnection(t *testing.T) {
	ok := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]any
		_ = json.NewDecoder(r.Body).Decode(&body)
		if body["api_name"] != "trade_cal" || body["token"] != "tk" {
			t.Errorf("请求体不符: %+v", body)
		}
		_, _ = w.Write([]byte(`{"code":0,"msg":"","data":{"fields":["cal_date"],"items":[["20260813"]]}}`))
	}))
	defer ok.Close()
	if msg, err := Test(Tushare{URL: ok.URL, Token: "tk"}); err != nil || !strings.Contains(msg, "1 行") {
		t.Fatalf("应通过,得到 msg=%q err=%v", msg, err)
	}

	bad := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"code":40203,"msg":"token不正确或已过期","data":null}`))
	}))
	defer bad.Close()
	_, err := Test(Tushare{URL: bad.URL, Token: "tk"})
	if err == nil || !strings.Contains(err.Error(), "已过期") {
		t.Fatalf("应带回 tushare 原始 msg,得到 %v", err)
	}

	if _, err := Test(Tushare{URL: "", Token: "tk"}); err == nil {
		t.Fatal("缺 host 应报错")
	}
}
