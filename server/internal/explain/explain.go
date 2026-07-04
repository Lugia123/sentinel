// Package explain — 用 DeepSeek 把某只持仓的策略计算结果讲成白话(带 DB 缓存)。
package explain

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"gorm.io/gorm"

	"sentinel/internal/ai"
	"sentinel/internal/store"
)

// 策略规则全文(注入 prompt,让 AI 严格据此解释,不编造)。
const RULES = `Sentinel 策略规则(严格据此解释,不得编造额外理由):
【选股】两条腿各选10只,各占一半仓位:
  - 动量腿:在98只大盘股里,先过"趋势门"(现价>200日线 且 200日线上行 且 现价>50日线 且 距52周高不超过25%),再按"相对SPY强度(近半年涨幅减SPY)"从高到低取前10。
  - 股东回报腿(SY):全市场按"股东收益率=净回购率+股息率"从高到低取前10。
【定仓】风险平价:波动越低给越多仓位(逆波动加权),各腿内部再分配。
【档位】-3到+3七档,由7个趋势子信号(站上20/50/200日线、200日线上行、21日动量为正、均线多头排列、接近52周高)求和映射而来。档位只用于"防御性减仓"(松·只减):+1及以上=持有,0=减一档,-1=减半,-2=减到1/4,-3=清仓。绝不追涨加仓(回测证追涨=负期望)。
【概率带】未来N日收益分布,用"波动缩放经验分布"算(把历史收益按波动标准化后取分位再还原)。70%区间=15%到85%分位。这是【离散度/波动范围】的校准估计,不是方向预测。
【风险灯】按SPY已实现波动做仓位闸(波动高=降总仓)。
【诚实边界】方向不可预测(已被严格回测证实);本系统是决策支持,不预测涨跌,只给趋势状态+校准的概率范围+风险提示。`

const SYSTEM = `你是严谨的量化策略助手,面向完全不懂量化的小白用户。任务:严格根据给定的【策略规则】和【这只股票的计算结果】,用通俗中文解释:①为什么这只股票会被策略选中 ②它的档位是怎么由子信号算出来的 ③概率带/风险该怎么理解 ④用户该关注什么信号变化。
要求:通俗、准确、不夸张、不预测涨跌、不编造规则里没有的东西。控制在300字内,分点讲。结尾提醒"研究工具非投资建议"。`

type Service struct {
	store *store.Store
	ai    *ai.Client
	gdb   *gorm.DB
}

func New(st *store.Store, aic *ai.Client, gdb *gorm.DB) *Service {
	return &Service{store: st, ai: aic, gdb: gdb}
}

type holding struct {
	Ticker     string          `json:"ticker"`
	Sleeve     string          `json:"sleeve"`
	Price      float64         `json:"price"`
	Grade      int             `json:"grade"`
	GradeLabel string          `json:"grade_label"`
	Action     string          `json:"action"`
	Reason     string          `json:"reason"`
	Signals    json.RawMessage `json:"signals"`
	Indicators json.RawMessage `json:"indicators"`
	Prob       json.RawMessage `json:"prob"`
}

// Explain 返回某股白话讲解(优先缓存;force=true 强制重算)。
func (s *Service) Explain(ctx context.Context, ticker, date string, force bool) (map[string]any, error) {
	raw, err := s.snapshot(date)
	if err != nil {
		return nil, err
	}
	var snap struct {
		Asof     string    `json:"asof"`
		Holdings []holding `json:"holdings"`
	}
	if err := json.Unmarshal(raw, &snap); err != nil {
		return nil, err
	}
	var h *holding
	for i := range snap.Holdings {
		if strings.EqualFold(snap.Holdings[i].Ticker, ticker) {
			h = &snap.Holdings[i]
			break
		}
	}
	if h == nil {
		return nil, fmt.Errorf("%s 不在 %s 的持仓里", ticker, snap.Asof)
	}

	if !force {
		var cached string
		if s.gdb.Raw(`SELECT content FROM explanations WHERE ticker=? AND asof=? AND kind='holding'`,
			h.Ticker, snap.Asof).Row().Scan(&cached) == nil && cached != "" {
			return map[string]any{"ticker": h.Ticker, "asof": snap.Asof, "content": cached, "cached": true}, nil
		}
	}
	if !s.ai.Enabled() {
		return nil, fmt.Errorf("未配置 DeepSeek(server/.env 的 SENTINEL_DEEPSEEK_KEY);其余功能不受影响")
	}

	user := fmt.Sprintf("%s\n\n【这只股票 %s 的计算结果】\n档位:%d(%s)→ 动作:%s\n选股理由:%s\n档位子信号:%s\n关键指标:%s\n概率带:%s",
		RULES, h.Ticker, h.Grade, h.GradeLabel, h.Action, h.Reason, string(h.Signals), string(h.Indicators), string(h.Prob))
	content, err := s.ai.Chat(ctx, SYSTEM, user)
	if err != nil {
		return nil, err
	}
	s.gdb.Exec(`INSERT INTO explanations(ticker,asof,kind,content,model) VALUES (?,?,'holding',?,?)
		ON CONFLICT (ticker,asof,kind) DO UPDATE SET content=EXCLUDED.content, model=EXCLUDED.model, created_at=now()`,
		h.Ticker, snap.Asof, content, "deepseek")
	return map[string]any{"ticker": h.Ticker, "asof": snap.Asof, "content": content, "cached": false}, nil
}

func (s *Service) snapshot(date string) ([]byte, error) {
	if date == "" || date == "latest" {
		return s.store.Latest()
	}
	return s.store.ByDate(date)
}
