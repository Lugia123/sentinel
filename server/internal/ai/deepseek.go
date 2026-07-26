// Package ai — DeepSeek(OpenAI 兼容)客户端,用于对策略结果做白话讲解。
// key 只从 config(server/.env)注入,绝不硬编码/回显。
package ai

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type Client struct {
	key, base, model string
	http             *http.Client
}

func New(key, base, model string) *Client {
	return &Client{key: key, base: base, model: model, http: &http.Client{Timeout: 90 * time.Second}}
}

// Enabled 是否配了 key(未配则 AI 讲解功能优雅降级)。
func (c *Client) Enabled() bool { return c.key != "" }

// TodayCN 当前北京日期(如 2026年07月16日)。注入 AI prompt 作时间基准,
// 否则 DeepSeek 无当前时间概念,会按训练期臆断年份(如把近期数据写成"2024年")。
func TodayCN() string {
	return time.Now().In(time.FixedZone("CST", 8*3600)).Format("2006年01月02日")
}

type msg struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// Chat 调用 /chat/completions,返回首条回复文本。
func (c *Client) Chat(ctx context.Context, system, user string) (string, error) {
	if !c.Enabled() {
		return "", fmt.Errorf("未配置 DeepSeek key(server/.env 的 SENTINEL_DEEPSEEK_KEY)")
	}
	body, _ := json.Marshal(map[string]any{
		"model":       c.model,
		"messages":    []msg{{Role: "system", Content: system}, {Role: "user", Content: user}},
		"temperature": 0.4,
		"stream":      false,
	})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, c.base+"/chat/completions", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.key)
	resp, err := c.http.Do(req)
	if err != nil {
		return "", fmt.Errorf("调用 DeepSeek 失败: %w", err)
	}
	defer resp.Body.Close()
	var out struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
		Error *struct {
			Message string `json:"message"`
		} `json:"error"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "", fmt.Errorf("解析 DeepSeek 响应: %w", err)
	}
	if out.Error != nil {
		return "", fmt.Errorf("DeepSeek: %s", out.Error.Message)
	}
	if len(out.Choices) == 0 {
		return "", fmt.Errorf("DeepSeek 返回空(HTTP %d)", resp.StatusCode)
	}
	return out.Choices[0].Message.Content, nil
}
