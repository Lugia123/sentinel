# Sentinel 架构再规划 v1.3 — 可插拔策略框架

## 背景与决策记录
- **选股范围(用户确认保持现状,2026-07-05)**:动量腿=98大盘窄池(回测最优);股东回报(SY)腿=1393只 S&P1500(含中小盘)。**中小盘经 SY 腿被选出**。整体=活到今天的 S&P1500,不含退市股(用户否决退市股方向)。已写入帮助页。
- **用户诉求**:现有 2 选股策略 + 1 定仓 + 1 趋势 + 1 预测 + 1 风险闸,全是**硬编码在 compute_snapshot 里**。以后加任意一种新策略都要改核心。**后端结构必须方便扩展**;前端尽量数据驱动。

## 核心设计:策略即插件(注册表 + 流水线)
把策略拆成 **5 类可注册组件**,每类一个接口 + 注册表。新增策略 = 实现接口 + 注册 + 配置启用,**不改流水线**。

### 组件类型
| 类型 | 接口 | 现有实现 | 未来举例 |
|---|---|---|---|
| **Selector 选股** | `select(ctx) → [Pick(ticker,score,reason,sleeve)]` | momentum(98)、shareholder_yield(1393) | 低波动、质量、反转… |
| **Sizer 定仓** | `size(picks, ctx) → {ticker: weight}` | risk_parity(逆波动) | 等权、凯利、目标波动… |
| **Grader 趋势档位** | `grade(ticker, ctx) → Grade(grade,label,action,signals)` | seven_signal(7子信号) | 均线斜率、MACD、突破… |
| **Predictor 预测** | `predict(ticker, ctx) → prob` | vol_scaled(波动缩放经验分布) | GARCH、分位回归… |
| **RiskGate 风险闸** | `evaluate(ctx) → {level,exposure,note}` | vol_target(SPY波动目标) | VIX体制、回撤闸… |

### 上下文 Context
`ctx` 封装共享数据访问(uni/spy/fp/asof/POS + row()/vol63() 等 helper),所有组件通过它拿数据,**天然无前视**(POS 按日期定位)。

### 流水线(compute_snapshot 变薄,只编排)
```
1. 各启用 Selector.select(ctx) → picks(带 sleeve 标签)
2. 合并 picks(并集,记录每票来自哪些 selector)
3. Sizer.size(picks, ctx) → base_weights
4. RiskGate.evaluate(ctx) → 总仓位闸
5. 每只持仓:Grader.grade + Predictor.predict + 关键指标
6. 组装 snapshot(holdings 带 sleeve/source、grade、signals、prob、reason、indicators)
```

### 配置声明启用哪些组件
```python
STRATEGY_CONFIG = {
  "selectors": ["momentum", "shareholder_yield"],  # 加新腿:追加名字
  "sizer": "risk_parity",
  "grader": "seven_signal",
  "predictor": "vol_scaled",
  "gate": "vol_target",
}
```

## 目录结构(engine)
```
engine/strategies/
  base.py        # 接口 + Context + 注册表(SELECTORS/SIZERS/GRADERS/PREDICTORS/GATES)
  selectors.py   # MomentumSelector, ShareholderYieldSelector
  sizers.py      # RiskParitySizer
  graders.py     # SevenSignalGrader
  predictors.py  # VolScaledPredictor
  gates.py       # VolTargetGate
  __init__.py    # import 各模块触发注册 + STRATEGY_CONFIG
engine/run_daily.py  # compute_snapshot 用注册表+config 编排(流水线)
```

## 后端(Go)扩展点
- `holdings.sleeve` = 选股来源(泛化;多 selector 命中→"both"/列表)。
- snapshot `raw` 里带 `strategy_config`(当天启用了哪些组件)——可追溯、可对比。
- **`/api/strategies`** 端点:列出可用/启用的策略组件(前端据此适配、做策略开关)。
- DB schema 已够灵活(raw JSONB + holdings 规范化);新组件无需改表。

## 前端扩展(尽量数据驱动)
- 持仓的 sleeve 徽章/reason/signals/prob **由数据驱动**——新选股腿自动出徽章、新档位器产出的 signals 通用渲染。
- 复合视图(仪表盘/走势)对新"类型"策略可能要小改;但同类新增(多一条选股腿、多一个档位器)前端零改动。
- SleeveBadge 对未知 sleeve 优雅降级(显示名字)。

## 落地顺序(v1.3)
1. 建 `strategies/` 框架 + 把现有 5 组件迁进去(**回归测试:快照必须与重构前逐字节一致**)。
2. `/api/strategies` + snapshot 带 strategy_config。
3. 之后所有新功能(自定义股分析、走势、新策略)都在此框架上加。

## 用户自定义股分析(#6/#7,契合本框架)
关注的某只股 = 用**同一套流水线 + 同一起点**跑,只是"资金池=这一只"(看它自己的档位/概率/走势)。实现:pipeline 支持 `focus_ticker` 模式——跳过 selector,直接把该票当唯一持仓,跑 grader/predictor,capital 全给它。标记 `source=user`。
