# Sentinel v2.0 双市场(美股 + A股)设计

> 分支 `feature/v2.0-dual-market`(自 feature/v1.6)。目标:在现有美股决策支持仪表盘上,新增 A股 市场,用户可切换查看两个市场各自的选股/趋势档位/到价概率/风险灯。A股 策略来自 `safna_jr_a`(R1-R47)。**研究工具,非投资建议。**

## 一·核心设计决策

### 决策1:加"市场(market)"维度(方案②),不走平行管线(方案①)
- 理由:双市场是**产品特性**(用户同一界面切换看两市场),不是临时脚本。平行管线会导致快照 asof 键冲突、前端无法统一切换、DB 无法区分归属。
- 落地:全链路加 `market ∈ {us, cn}` 维度;默认 `us`(向后兼容,存量数据视为 us)。

### 决策2:最大化复用可插拔框架,A股 只加"腿"和"闸"
- **零改动复用**(市场无关):`base.py`(5类注册表+Context)、`sizers.py`(风险平价)、`predictors.py`(波动缩放经验分布,R46 验证 A股 区间校准良好)、Go 后端流水线骨架、前端图表组件。
- **新增 A股 组件**(插进现有槽):`cn_stock_pick`(选股腿)、`cn_breadth_gate`(市场级优化分档=A股趋势分档的全部)。
- **关键结构差异(已由 safna_jr_a R36 证实)**:**A股 趋势分档在市场级 GATE,不在逐票 GRADER**。美股 7档动量 grader 搬到 A股 是灾难(Cal0.587→0.021,A股反转市)。→ **A股 的 grader 关闭减仓功能,或只作"个股趋势状态展示"**;真正的档位=cn_breadth_gate 输出的 exposure。

### 决策3:每市场独立 STRATEGY_CONFIG
```python
STRATEGY_CONFIG = {
  "us": {"selectors":["momentum","shareholder_yield"], "sizer":"risk_parity",
         "grader":"seven_signal", "predictor":"vol_scaled", "gate":"vol_target"},
  "cn": {"selectors":["cn_smallcap_lowturn","cn_rev_pead"], "sizer":"equal",
         "grader":"cn_display_only", "predictor":"vol_scaled_rolling", "gate":"cn_breadth_crowding"},
}
```

## 二·分层改动清单 + 改动量评估

| 层 | 文件 | 改动 | 量级 |
|---|---|---|---|
| **引擎** | `engine/run_daily.py` | 参数化 `--market`;去 SPY/safna_jr 硬编码(L20-29),改按市场选数据目录+基准+config;快照加 `"market"` 字段 | **中**(~80行) |
| 引擎 | `engine/strategies/cn_selectors.py`(新) | 头号腿(小市值×低换手·双周)+ rev+PEAD 腿,移植 safna_jr_a/lib/legs | **中**(~150行,逻辑已有) |
| 引擎 | `engine/strategies/cn_gates.py`(新) | cn_breadth_crowding 优化分档(宽度∧拥挤∧成交额∧非背离,WF0.66),移植 lib/timing | **中**(~120行,逻辑已有) |
| 引擎 | `engine/strategies/graders.py` | 加 `cn_display_only`(只标趋势状态不减仓);或 config 允许 grader=none | **小**(~30行) |
| 引擎 | `engine/strategies/predictors.py` | 加 `vol_scaled_rolling`(A股用滚动窗,R46:壳改革后分布漂移) | **小**(~30行) |
| 引擎 | `engine/strategies/__init__.py` | STRATEGY_CONFIG 改为按市场嵌套;active_manifest(market) | **小**(~20行) |
| 引擎 | `engine/data_cn/`(新软链) | 指向 `safna_jr_a/data/daily` + 基准(中证全指) | 配置 |
| **契约** | `engine/schema.md` | 加 `"market"` 顶层字段;holdings 加可选 A股字段(涨跌停状态/流通市值);risk_light 泛化(spy_vol→bench_vol,加宽度/拥挤读数) | **小** |
| **DB** | `server/migrations/0008_market.up.sql`(新) | 8表加 `market TEXT NOT NULL DEFAULT 'us'`,重做唯一键:snapshots(market,asof)、prices(market,ticker,date)、positions/holdings/runs/explanations/watchlist/focus_cache 加 market | **中**(一个迁移文件) |
| DB | `server/internal/db/models.go` | 6个模型加 `Market string` 字段 | **小**(~10行) |
| **后端** | `server/internal/pipeline/pipeline.go` | ingest 读快照 `market` 字段,写入各表 | **小** |
| 后端 | `server/internal/api/*.go` | ~15个数据路由加 `?market=` 参数(默认us),查询加 `WHERE market=`;/api/markets 新路由列可用市场 | **中**(~28路由,~15需改,每处几行) |
| 后端 | `server/internal/engine/runner.go` | run 触发 subprocess 传 `--market` | **小** |
| **前端** | `client/src/App.tsx` | Header 加市场切换器(us/cn tab),全局 market state(context/url param) | **中** |
| 前端 | `client/src/api.ts` | 所有 API 调用带 market 参数 | **小**(集中一处) |
| 前端 | `client/src/pages/*.tsx` | Dashboard/Positions/Trends 读当前 market;A股展示适配(涨跌停/¥计价/趋势档位说明"市场级") | **中** |
| 前端 | `client/src/types.ts` | Snapshot/Holding 加 market 字段;A股可选字段 | **小** |

### 总改动量评估:**中等,非重写**
- **改动集中在"加维度"(市场),不动核心算法**;策略框架的可插拔性让 A股 逻辑以"新腿+新闸"插入,不碰流水线。
- 估算:引擎 ~430 行(半数是移植已验证逻辑)、Go 后端 ~200 行(多是加 market 过滤)、前端 ~300 行(市场切换器+适配)、1 个 DB 迁移。
- **风险点**:①DB 迁移的唯一键重做(需 down 迁移可回滚)②ticker 命名空间(A股 sh.600000 vs 美股 AAPL,加 market 前缀天然隔离)③前端计价单位(¥ vs $)与涨跌停展示。
- **不需要**:重写引擎/后端/前端骨架;改数据契约结构(只加字段);动认证/AI讲解核心。

## 三·A股 组件规格(接 safna_jr_a 定稿)
- **选股(cn_selectors)**:①头号腿=tradable∧剔ST∧小市值分位≤20% 内按20日均换手升序前50,**双周调仓**等权(R45免税红利);②rev+PEAD=分析师净上调+业绩预告惊喜 各市值分层z-score合成前50。sleeve=`smallcap`/`event`。
- **趋势分档(cn_breadth_crowding GATE)**:risk-on = 宽度(站上60日线比例>其40日均线)∧ 微盘拥挤度分位≤0.85 ∧ 成交额未枯竭(5/60日均比>0.85)∧ 非小盘-大盘背离。输出 exposure(二值满/空 或 3档满/半/空 UX)。诚实指标 WF Cal0.66/DD−21%。
- **逐票档(cn_display_only GRADER)**:只标个股趋势状态(供人看),**不据此减仓**(A股反转,美股式减仓是灾难)。
- **到价概率(vol_scaled_rolling)**:波动缩放经验分布,**滚动500-750日窗**(A股分布壳改革后漂移),区间预测(R46验证校准优秀);涨跌停截断已隐含。
- **数据**:baostock 日线(EOD刷新)+ akshare 事件(revision T+0/业绩预告季节性);生产建议配 Tushare Pro 兜底。

## 四·分期实施(建议)
1. **P1 引擎双市场**:参数化 run_daily + cn_selectors/cn_gates/graders/predictors + 数据软链 → 产出 A股 snapshot JSON(schema 对齐)。可独立验证(不动后端)。
2. **P2 DB+后端**:0008 迁移 + models + pipeline + API 加 market 参数。
3. **P3 前端**:市场切换器 + 页面适配 + A股 计价/涨跌停展示。
4. **P4 联调**:双市场端到端 + 每日双市场跑批 + 兼容性(存量美股=us)。

## 五·兼容性与回滚
- 存量数据/API 默认 `market=us`,老前端不传 market 仍工作(向后兼容)。
- 每个迁移带 down;分支独立,不影响 v1.6 生产。
- A股 数据源不稳(akshare)时,该市场快照标 stale,不影响美股。

> 依赖:safna_jr_a 的 `有效策略清单.md`/`SENTINEL接入准备.md`/`lib/{legs,timing,altdata}.py`(逻辑源)。研究推演,非投资建议。
