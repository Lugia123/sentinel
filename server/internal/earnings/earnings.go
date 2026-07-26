// Package earnings — 财报解读:SEC季度数(engine/earnings.py)→ DeepSeek解读HTML → MinIO → 详情tab。
package earnings

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"sentinel/internal/ai"
	"sentinel/internal/blob"
	"sentinel/internal/engine"
)

const SYSTEM = `你是面向中国散户的财报解读助手。给你某美股某季度的关键财务数字(营收/净利/营业利润/毛利/EPS)及对比,请解读成一段【HTML 片段】(会被注入到已有暗色页面,随整页滚动)。
分区:①本季概况(营收/利润多少,通俗)②环比/同比变化(增长还是下滑,幅度)③利润率与质量 ④亮点与隐忧。数字换算成"亿美元"更好懂。
【HTML 格式硬要求】只输出片段,绝不要 <!doctype>/<html>/<head>/<body>/<style>/代码围栏。用 <h4> + <p> + <ul><li>,关键词 <b>,不写任何 CSS。中文。结尾 <p class="disc">AI 基于 SEC 公开财报数据解读,仅供参考,非投资建议。</p>。`

// SYSTEM_CN A股版(数据来自新浪财经利润表,已差分成单季;单位换算成亿元)。
const SYSTEM_CN = `你是面向中国散户的财报解读助手。给你某A股上市公司某季度的关键财务数字(营收/净利/营业利润/毛利/EPS,已换算为单季值)及对比,请解读成一段【HTML 片段】(会被注入到已有暗色页面,随整页滚动)。
分区:①本季概况(营收/利润多少,通俗)②环比/同比变化(增长还是下滑,幅度;注意A股季节性,同比比环比更有参考性)③利润率与质量 ④亮点与隐忧。数字换算成"亿元"更好懂。
【HTML 格式硬要求】只输出片段,绝不要 <!doctype>/<html>/<head>/<body>/<style>/代码围栏。用 <h4> + <p> + <ul><li>,关键词 <b>,不写任何 CSS。中文。结尾 <p class="disc">AI 基于公开财报数据(新浪财经利润表)解读,仅供参考,非投资建议;请以巨潮资讯/交易所公告为准核实。</p>。`

type Quarter struct {
	Period          string   `json:"period"`
	Revenue         *float64 `json:"revenue"`
	NetIncome       *float64 `json:"net_income"`
	OperatingIncome *float64 `json:"operating_income"`
	GrossProfit     *float64 `json:"gross_profit"`
	EPS             *float64 `json:"eps"`
	Cached          bool     `json:"cached"` // 该季是否已解读过(MinIO 有缓存)
}

// earnKey 财报解读 HTML 的 MinIO key(按用户隔离)。
func earnKey(userID int64, ticker, period string) string {
	return fmt.Sprintf("earnings/%d/%s_%s.html", userID, ticker, period)
}

type Service struct {
	runner *engine.Runner
	ai     *ai.Client
	blob   *blob.Store
}

func New(rn *engine.Runner, aic *ai.Client, bs *blob.Store) *Service {
	return &Service{runner: rn, ai: aic, blob: bs}
}

// Quarters 返回可解读的季度列表。market: us(SEC)/ cn(新浪,单季差分)。
func (s *Service) Quarters(market, ticker string) ([]Quarter, error) {
	raw, err := s.runner.RunEarnings(market, ticker)
	if err != nil {
		return nil, err
	}
	var d struct {
		Error    string    `json:"error"`
		Quarters []Quarter `json:"quarters"`
	}
	if err := json.Unmarshal([]byte(raw), &d); err != nil {
		return nil, err
	}
	if d.Error != "" {
		return nil, fmt.Errorf("%s", d.Error)
	}
	return d.Quarters, nil
}

// QuartersWithStatus 在季度列表上标注每季是否已解读(下拉框区分已/未解读)。
func (s *Service) QuartersWithStatus(ctx context.Context, userID int64, market, ticker string) ([]Quarter, error) {
	qs, err := s.Quarters(market, ticker)
	if err != nil {
		return nil, err
	}
	if s.blob != nil && s.blob.Enabled() {
		for i := range qs {
			qs[i].Cached = s.blob.Exists(ctx, earnKey(userID, ticker, qs[i].Period))
		}
	}
	return qs, nil
}

// Interpret 解读指定季度(→HTML→MinIO,返回 key)。
func (s *Service) Interpret(ctx context.Context, userID int64, market, ticker, period string, force bool) (map[string]any, error) {
	if s.blob == nil || !s.blob.Enabled() {
		return nil, fmt.Errorf("MinIO 未配置")
	}
	k := earnKey(userID, ticker, period)
	if !force && s.blob.Exists(ctx, k) {
		return map[string]any{"ticker": ticker, "period": period, "key": k, "cached": true}, nil
	}
	if !s.ai.Enabled() {
		return nil, fmt.Errorf("未配置 DeepSeek")
	}
	qs, err := s.Quarters(market, ticker)
	if err != nil {
		return nil, err
	}
	var cur, prev, yoy *Quarter
	for i := range qs {
		if qs[i].Period == period {
			cur = &qs[i]
			if i+1 < len(qs) {
				prev = &qs[i+1]
			}
			if i+4 < len(qs) {
				yoy = &qs[i+4]
			}
		}
	}
	if cur == nil {
		return nil, fmt.Errorf("无 %s 季度数据", period)
	}
	system := SYSTEM
	if market == "cn" {
		system = SYSTEM_CN
	}
	user := fmt.Sprintf("【当前日期】%s(涉及时间以此为准,勿臆断年份;季度以「本季(%s)」标注为准)\n公司:%s\n本季(%s):%s\n上一季:%s\n去年同期:%s\n请解读本季财报。",
		ai.TodayCN(), period, ticker, period, fmtQ(cur), fmtQ(prev), fmtQ(yoy))
	html, err := s.ai.Chat(ctx, system, user)
	if err != nil {
		return nil, err
	}
	html = stripFence(html)
	if err := s.blob.PutHTML(ctx, k, html); err != nil {
		return nil, err
	}
	return map[string]any{"ticker": ticker, "period": period, "key": k, "cached": false}, nil
}

func fmtQ(q *Quarter) string {
	if q == nil {
		return "无"
	}
	f := func(p *float64, div float64, unit string) string {
		if p == nil {
			return "-"
		}
		return fmt.Sprintf("%.1f%s", *p/div, unit)
	}
	return fmt.Sprintf("营收%s 净利%s 营业利润%s 毛利%s EPS%s",
		f(q.Revenue, 1e8, "亿"), f(q.NetIncome, 1e8, "亿"), f(q.OperatingIncome, 1e8, "亿"),
		f(q.GrossProfit, 1e8, "亿"), f(q.EPS, 1, ""))
}

func stripFence(s string) string {
	t := strings.TrimSpace(s)
	if strings.HasPrefix(t, "```") {
		if i := strings.IndexByte(t, '\n'); i >= 0 {
			t = t[i+1:]
		}
		t = strings.TrimSuffix(strings.TrimSpace(t), "```")
	}
	return strings.TrimSpace(t)
}
