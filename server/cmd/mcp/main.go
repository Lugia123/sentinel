// Sentinel MCP server(stdio / JSON-RPC 2.0)——把每个页面的用户操作包成 MCP 工具,
// 薄封装后端 HTTP API(默认 http://localhost:8787,可用 SENTINEL_API 覆盖)。
// 让 agentic AI / Claude 能直接驱动、测试整个 app 的所有按钮。
package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

var api = env("SENTINEL_API", "http://localhost:8787")
var httpc = &http.Client{Timeout: 90 * time.Second}

func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

// ── 工具定义 ──
type tool struct {
	Name    string
	Desc    string
	Schema  map[string]any
	Handler func(args map[string]any) (string, error)
}

func obj(props map[string]any, required ...string) map[string]any {
	m := map[string]any{"type": "object", "properties": props}
	if len(required) > 0 {
		m["required"] = required
	}
	return m
}
func str(desc string) map[string]any { return map[string]any{"type": "string", "description": desc} }
func boolean(desc string) map[string]any {
	return map[string]any{"type": "boolean", "description": desc}
}

// httpCall 调后端;GET 用 query,POST 用 body(json)。返回响应体文本。
func httpCall(method, path string, query url.Values, body any) (string, error) {
	u := api + path
	if len(query) > 0 {
		u += "?" + query.Encode()
	}
	var br io.Reader
	if body != nil {
		b, _ := json.Marshal(body)
		br = bytes.NewReader(b)
	}
	req, err := http.NewRequest(method, u, br)
	if err != nil {
		return "", err
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := httpc.Do(req)
	if err != nil {
		return "", fmt.Errorf("连不上后端(%s):%v。请先启动 sentinel 服务(./scripts/run-dev.sh 或 go run ./cmd/server)", api, err)
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	if resp.StatusCode >= 400 {
		return "", fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(b))
	}
	return string(b), nil
}

func qs(args map[string]any, keys ...string) url.Values {
	q := url.Values{}
	for _, k := range keys {
		if v, ok := args[k]; ok && v != nil {
			q.Set(k, fmt.Sprint(v))
		}
	}
	return q
}

// 背调/财报:拿到 key 后顺带取回 HTML 内容,方便一次调用就看到结果。
func withBlob(raw string, err error) (string, error) {
	if err != nil {
		return "", err
	}
	var r struct {
		Key string `json:"key"`
	}
	if json.Unmarshal([]byte(raw), &r) == nil && r.Key != "" {
		if html, e := httpCall("GET", "/api/blob", qs(map[string]any{"key": r.Key}, "key"), nil); e == nil {
			return raw + "\n\n<!-- HTML 内容 -->\n" + html, nil
		}
	}
	return raw, nil
}

func tools() []tool {
	return []tool{
		{"sentinel_snapshot", "获取当前策略快照(建议持仓列表/风险灯/组合)。可选 date=YYYY-MM-DD",
			obj(map[string]any{"date": str("快照日期,省略取最新")}),
			func(a map[string]any) (string, error) { return httpCall("GET", "/api/snapshot", qs(a, "date"), nil) }},
		{"sentinel_snapshot_dates", "列出所有有快照的历史日期(回填的)。", obj(nil),
			func(a map[string]any) (string, error) { return httpCall("GET", "/api/snapshot/dates", nil, nil) }},
		{"sentinel_run", "【重算按钮】重跑今天的策略引擎(约30秒)。sy=是否含股东回报腿(默认true)。",
			obj(map[string]any{"sy": boolean("是否含SY腿,默认true")}),
			func(a map[string]any) (string, error) {
				q := url.Values{"sy": {"1"}}
				if v, ok := a["sy"].(bool); ok && !v {
					q.Set("sy", "0")
				}
				return httpCall("POST", "/api/run", q, nil)
			}},
		{"sentinel_watchlist", "查看关注列表。", obj(nil),
			func(a map[string]any) (string, error) { return httpCall("GET", "/api/watchlist", nil, nil) }},
		{"sentinel_watch_add", "【★关注按钮】把某股加入关注(会在列表置顶)。source=ai/user。",
			obj(map[string]any{"ticker": str("代码"), "source": str("ai或user,默认ai")}, "ticker"),
			func(a map[string]any) (string, error) { return httpCall("POST", "/api/watchlist", qs(a, "ticker", "source"), nil) }},
		{"sentinel_watch_remove", "【★取消关注】把某股移出关注。",
			obj(map[string]any{"ticker": str("代码")}, "ticker"),
			func(a map[string]any) (string, error) { return httpCall("DELETE", "/api/watchlist", qs(a, "ticker"), nil) }},
		{"sentinel_focus", "【自选股分析按钮】对任意股用同一套档位/概率规则分析(资金池假设全押这一只)。",
			obj(map[string]any{"ticker": str("代码")}, "ticker"),
			func(a map[string]any) (string, error) { return httpCall("GET", "/api/focus", qs(a, "ticker"), nil) }},
		{"sentinel_positions", "【我的持仓页】查持仓盈亏(as-of 一致定价)。可选 date。",
			obj(map[string]any{"date": str("日期,省略取最新")}),
			func(a map[string]any) (string, error) { return httpCall("GET", "/api/positions", qs(a, "date"), nil) }},
		{"sentinel_trend", "【单股走势】某股历史档位/价/20日中位序列。可选 from/to(YYYY-MM-DD)。",
			obj(map[string]any{"ticker": str("代码"), "from": str("起"), "to": str("止")}, "ticker"),
			func(a map[string]any) (string, error) { return httpCall("GET", "/api/trend", qs(a, "ticker", "from", "to"), nil) }},
		{"sentinel_trend_multi", "【多股对比】多只股的档位走势对比。tickers 逗号分隔,如 AMD,INTC,MO。",
			obj(map[string]any{"tickers": str("逗号分隔代码")}, "tickers"),
			func(a map[string]any) (string, error) { return httpCall("GET", "/api/trend", qs(a, "tickers", "from", "to"), nil) }},
		{"sentinel_explain", "【AI讲解按钮】按策略规则白话解读某股(HTML)。force=1 重新生成。",
			obj(map[string]any{"ticker": str("代码"), "force": boolean("重新生成")}, "ticker"),
			func(a map[string]any) (string, error) {
				return httpCall("GET", "/api/explain", forceQS(a, "ticker"), nil)
			}},
		{"sentinel_investigate", "【背景调查按钮】AI 调研公司背景→HTML(自动返回内容)。force=1 重新调研。",
			obj(map[string]any{"ticker": str("代码"), "force": boolean("重新调研")}, "ticker"),
			func(a map[string]any) (string, error) {
				return withBlob(httpCall("GET", "/api/investigate", forceQS(a, "ticker"), nil))
			}},
		{"sentinel_earnings_quarters", "【财报解读页】列出某股可解读的季度(SEC 官方数据)。",
			obj(map[string]any{"ticker": str("代码")}, "ticker"),
			func(a map[string]any) (string, error) { return httpCall("GET", "/api/earnings/quarters", qs(a, "ticker"), nil) }},
		{"sentinel_earnings", "【解读这一季按钮】AI 解读某股某季财报→HTML(自动返回内容)。period=YYYY-MM-DD。force=1 重解读。",
			obj(map[string]any{"ticker": str("代码"), "period": str("季度末日期"), "force": boolean("重新解读")}, "ticker", "period"),
			func(a map[string]any) (string, error) {
				return withBlob(httpCall("GET", "/api/earnings", forceQS(a, "ticker", "period"), nil))
			}},
		{"sentinel_meta", "全部股票的中文名+板块映射。", obj(nil),
			func(a map[string]any) (string, error) { return httpCall("GET", "/api/meta", nil, nil) }},
		{"sentinel_strategies", "当前启用的策略组件(选股/定仓/趋势/预测/风险闸)+ 可用清单。", obj(nil),
			func(a map[string]any) (string, error) { return httpCall("GET", "/api/strategies", nil, nil) }},
		{"sentinel_history", "个股价格+均线历史(近 n 日,默认120)。",
			obj(map[string]any{"ticker": str("代码"), "n": str("天数")}, "ticker"),
			func(a map[string]any) (string, error) { return httpCall("GET", "/api/history", qs(a, "ticker", "n"), nil) }},
		{"sentinel_datastatus", "数据状态(数据日/条数等)。", obj(nil),
			func(a map[string]any) (string, error) { return httpCall("GET", "/api/datastatus", nil, nil) }},
		{"sentinel_version", "版本信息。", obj(nil),
			func(a map[string]any) (string, error) { return httpCall("GET", "/api/version", nil, nil) }},
	}
}

// forceQS: 普通 query + force(bool→1)。
func forceQS(a map[string]any, keys ...string) url.Values {
	q := qs(a, keys...)
	if v, ok := a["force"].(bool); ok && v {
		q.Set("force", "1")
	}
	return q
}

// ── JSON-RPC / MCP stdio 循环 ──
type rpcReq struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params"`
}

func main() {
	reg := map[string]tool{}
	var list []map[string]any
	for _, t := range tools() {
		reg[t.Name] = t
		list = append(list, map[string]any{"name": t.Name, "description": t.Desc, "inputSchema": t.Schema})
	}
	in := bufio.NewScanner(os.Stdin)
	in.Buffer(make([]byte, 1024*1024), 8*1024*1024)
	out := bufio.NewWriter(os.Stdout)
	send := func(id json.RawMessage, result any, errObj map[string]any) {
		msg := map[string]any{"jsonrpc": "2.0", "id": json.RawMessage(id)}
		if errObj != nil {
			msg["error"] = errObj
		} else {
			msg["result"] = result
		}
		b, _ := json.Marshal(msg)
		out.Write(b)
		out.WriteByte('\n')
		out.Flush()
	}
	for in.Scan() {
		line := strings.TrimSpace(in.Text())
		if line == "" {
			continue
		}
		var req rpcReq
		if json.Unmarshal([]byte(line), &req) != nil {
			continue
		}
		switch req.Method {
		case "initialize":
			send(req.ID, map[string]any{
				"protocolVersion": "2024-11-05",
				"capabilities":    map[string]any{"tools": map[string]any{}},
				"serverInfo":      map[string]any{"name": "sentinel", "version": "1.3"},
			}, nil)
		case "notifications/initialized":
			// 通知,无响应
		case "ping":
			send(req.ID, map[string]any{}, nil)
		case "tools/list":
			send(req.ID, map[string]any{"tools": list}, nil)
		case "tools/call":
			var p struct {
				Name string         `json:"name"`
				Args map[string]any `json:"arguments"`
			}
			json.Unmarshal(req.Params, &p)
			t, ok := reg[p.Name]
			if !ok {
				send(req.ID, nil, map[string]any{"code": -32602, "message": "未知工具: " + p.Name})
				continue
			}
			text, err := t.Handler(p.Args)
			if err != nil {
				send(req.ID, map[string]any{
					"content": []map[string]any{{"type": "text", "text": "错误: " + err.Error()}},
					"isError": true,
				}, nil)
				continue
			}
			send(req.ID, map[string]any{
				"content": []map[string]any{{"type": "text", "text": text}},
			}, nil)
		default:
			if len(req.ID) > 0 {
				send(req.ID, nil, map[string]any{"code": -32601, "message": "method not found: " + req.Method})
			}
		}
	}
}
