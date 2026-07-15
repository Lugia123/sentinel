// Package allocate — 建议股数分配:在用户选定的候选股上分配资金池。
// AI 模式用 DeepSeek 给购买比例(做取舍,不必全买);权重服务端归一化、
// 股数按价确定性计算(金融计算不信 AI 算术,交叉校验)。
package allocate

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"gorm.io/gorm"

	"sentinel/internal/ai"
	"sentinel/internal/store"
)

const SYSTEM = `你是严谨的组合配置助手,面向资金有限的散户。给你一个资金池和一组候选股(用户选定的,可能含策略推荐股 + 用户自定义追踪股),请分配【购买比例】。
原则:①不必全买——资金有限要做取舍,优先档位高、趋势好(action=持有优于减仓)、概率中位为正、波动适中的;②单只权重不超过 25%,避免过度集中;③可以保留现金(总权重可小于100%),尤其风险偏高时;④被你排除的股票要在 note 里说明为什么舍弃。
【只输出 JSON,不要任何多余文字/代码围栏】格式:
{"allocations":[{"ticker":"AAPL","weight_pct":18.5,"reason":"档位+3趋势强,波动适中"}],"cash_pct":10,"note":"舍弃了ADBE/CRM(档位-3趋势走弱);整体因风险灯偏黄留了现金"}
weight_pct 是占资金池的百分比(0-100),所有 allocations 的 weight_pct 加 cash_pct 应≈100。reason/note 用简洁中文。`

type Service struct {
	ai  *ai.Client
	st  *store.Store
	gdb *gorm.DB
}

func New(aic *ai.Client, st *store.Store, gdb *gorm.DB) *Service { return &Service{ai: aic, st: st, gdb: gdb} }

type holding struct {
	Ticker     string          `json:"ticker"`
	Price      float64         `json:"price"`
	Grade      int             `json:"grade"`
	GradeLabel string          `json:"grade_label"`
	Action     string          `json:"action"`
	Reason     string          `json:"reason"`
	Prob       json.RawMessage `json:"prob"`
	Indicators struct {
		Vol *float64 `json:"vol_annual"`
		Sy  *float64 `json:"sy_yield"`
	} `json:"indicators"`
}

type Alloc struct {
	Ticker string  `json:"ticker"`
	Weight float64 `json:"weight"` // 0-1
	Shares float64 `json:"shares"`
	Value  float64 `json:"value"`
	Reason string  `json:"reason"`
}

// AIAllocate 让 DeepSeek 在候选股上分配比例。tickers 为空则用全部持仓。含用户自定义追踪股(从 focus 缓存补)。
// market: us/cn(取对应市场快照;A股股数按一手=100股取整、¥ 计价)。
func (s *Service) AIAllocate(ctx context.Context, userID int64, market string, tickers []string, capital float64) (map[string]any, error) {
	if !s.ai.Enabled() {
		return nil, fmt.Errorf("未配置 DeepSeek,AI 分配不可用(可用均分/风险平价)")
	}
	if market != "cn" {
		market = "us"
	}
	raw, err := s.st.Latest(market)
	if err != nil {
		return nil, err
	}
	var snap struct {
		Asof      string    `json:"asof"`
		Capital   float64   `json:"capital"`
		RiskLight struct{ Note, Level string } `json:"risk_light"`
		Holdings  []holding `json:"holdings"`
	}
	if err := json.Unmarshal(raw, &snap); err != nil {
		return nil, err
	}
	if capital <= 0 {
		capital = snap.Capital
	}
	want := map[string]bool{}
	for _, t := range tickers {
		want[strings.ToUpper(t)] = true
	}
	var cands []holding
	inCand := map[string]bool{}
	for _, h := range snap.Holdings {
		if len(want) == 0 || want[strings.ToUpper(h.Ticker)] {
			cands = append(cands, h)
			inCand[strings.ToUpper(h.Ticker)] = true
		}
	}
	// 补上不在共享快照里、但被选中的用户自定义追踪股(从 focus 缓存取档位/价)
	if s.gdb != nil {
		for tk := range want {
			if inCand[tk] {
				continue
			}
			qtk := tk
			if market == "cn" {
				qtk = strings.ToLower(tk) // A股代码存小写(sh.600000)
			}
			var raw2 string
			s.gdb.Raw(`SELECT holding::text FROM focus_cache WHERE user_id=? AND market=? AND ticker=? AND asof=?`, userID, market, qtk, snap.Asof).Row().Scan(&raw2)
			if raw2 != "" {
				var ch holding
				if json.Unmarshal([]byte(raw2), &ch) == nil && ch.Ticker != "" {
					cands = append(cands, ch)
					inCand[tk] = true
				}
			}
		}
	}
	if len(cands) == 0 {
		return nil, fmt.Errorf("没有候选股")
	}

	// 候选清单喂给 AI(带决策相关信息)
	cur := "$"
	if market == "cn" {
		cur = "¥"
	}
	var b strings.Builder
	fmt.Fprintf(&b, "【当前日期】%s\n资金池:%s%.0f\n风险灯:%s(%s)\n候选股(%d只):\n", ai.TodayCN(), cur, capital, snap.RiskLight.Note, snap.RiskLight.Level, len(cands))
	priceOf := map[string]float64{}
	nameOf := map[string]string{}
	for _, h := range cands {
		priceOf[strings.ToUpper(h.Ticker)] = h.Price
		nameOf[strings.ToUpper(h.Ticker)] = h.Ticker
		vol := "—"
		if h.Indicators.Vol != nil {
			vol = fmt.Sprintf("%.0f%%", *h.Indicators.Vol*100)
		}
		var med float64
		var pp struct {
			H20 struct{ Median float64 `json:"median"` } `json:"h20"`
		}
		_ = json.Unmarshal(h.Prob, &pp)
		med = pp.H20.Median
		fmt.Fprintf(&b, "- %s 档位%d(%s) 动作:%s 现价%s%.2f 年化波动%s 未来20日中位%.1f%% | %s\n",
			h.Ticker, h.Grade, h.GradeLabel, h.Action, cur, h.Price, vol, med*100, h.Reason)
	}
	if market == "cn" {
		b.WriteString("\n请分配购买比例(做取舍,不必全买)。注意这是A股:买入以一手=100股为单位。")
	} else {
		b.WriteString("\n请分配购买比例(做取舍,不必全买)。")
	}

	content, err := s.ai.Chat(ctx, SYSTEM, b.String())
	if err != nil {
		return nil, err
	}
	content = stripFence(content)
	var parsed struct {
		Allocations []struct {
			Ticker    string  `json:"ticker"`
			WeightPct float64 `json:"weight_pct"`
			Reason    string  `json:"reason"`
		} `json:"allocations"`
		CashPct float64 `json:"cash_pct"`
		Note    string  `json:"note"`
	}
	if err := json.Unmarshal([]byte(content), &parsed); err != nil {
		return nil, fmt.Errorf("解析 AI 分配失败:%v(原文:%.200s)", err, content)
	}

	// 交叉校验:权重求和归一(总权重≤1,超了按比例缩);股数按价确定性算(不信 AI 算术)
	sum := 0.0
	for _, a := range parsed.Allocations {
		if a.WeightPct > 0 {
			sum += a.WeightPct
		}
	}
	scale := 1.0
	if sum > 100 {
		scale = 100 / sum
	}
	out := []Alloc{}
	invested := 0.0
	for _, a := range parsed.Allocations {
		key := strings.ToUpper(a.Ticker)
		px := priceOf[key]
		if px <= 0 || a.WeightPct <= 0 {
			continue
		}
		w := a.WeightPct * scale / 100
		val := capital * w
		shares := round3(val / px)
		if market == "cn" { // A股一手=100股,向下取整手;金额随实际股数重算
			shares = float64(int(val/px/100)) * 100
			if shares <= 0 {
				continue
			}
			val = shares * px
			w = val / capital
		}
		out = append(out, Alloc{
			Ticker: nameOf[key], Weight: round4(w), Shares: shares, Value: round2(val), Reason: a.Reason,
		})
		invested += val
	}
	return map[string]any{
		"mode": "ai", "capital": capital, "asof": snap.Asof,
		"allocations": out,
		"cash_pct":    round4((capital - invested) / capital),
		"note":        parsed.Note,
	}, nil
}

func stripFence(s string) string {
	t := strings.TrimSpace(s)
	if strings.HasPrefix(t, "```") {
		if i := strings.IndexByte(t, '\n'); i >= 0 {
			t = t[i+1:]
		}
		t = strings.TrimSuffix(strings.TrimSpace(t), "```")
	}
	// 容错:截取第一个 { 到最后一个 }
	if i, j := strings.IndexByte(t, '{'), strings.LastIndexByte(t, '}'); i >= 0 && j > i {
		t = t[i : j+1]
	}
	return strings.TrimSpace(t)
}

func round2(f float64) float64 { return float64(int(f*100+0.5)) / 100 }
func round3(f float64) float64 { return float64(int(f*1000+0.5)) / 1000 }
func round4(f float64) float64 { return float64(int(f*10000+0.5)) / 10000 }
