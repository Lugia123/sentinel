# 建议持仓列表重构:Tab 分组 + 全市场板块浏览 + 分页 + 搜索(v2.5)

> 状态:设计 / 待评审 · 分支 `feature/v2.5`
> 目标页:`client/src/pages/Dashboard.tsx`(「建议持仓」表)

## 1. 需求

当前「建议持仓」是**一张表**,靠 `sleeve` 字段把「策略推荐股」和「用户自选股」混在一起(分组头分隔)。要改成:

- **Tab 1 推荐股票** —— 现在 `sleeve !== 'custom'` 那批(策略推荐)。
- **Tab 2 用户自选** —— 现在 `sleeve === 'custom'` 那批(watchlist)。
- **Tab 3+ 各板块** —— 申万一级 **31 个行业**,每个 tab = 该行业**全部股票**;推荐股置顶(带完整档位),其余按行情排,**也算出档位/区间**供直观对比。
- **分页组件** —— 参考 el-pagination:`N 条 · 第 x/y 页` + 上一页 + 页码 + 下一页 + `20 条/页` + 跳至。全 tab 通用。
- **全局搜索** —— 列表扩到全市场后加搜索框,**跨板块**(不限当前 tab),按代码/名称找股票。

## 2. 关键决策(已定)

| 决策 | 选择 | 依据 |
|---|---|---|
| 非推荐股展示深度 | **B:每只都算完整档位+20日区间** | 用户要"看没进推荐的实际算出来啥样",做直观对比 |
| Tab 形态 | 固定 `[推荐][自选]` + 板块**横向滚动条**(31 个一级行业) | 贴合"每板块一个 tab",31 个太长 → 横向滚动 |
| 分级 | 仅申万**一级(L1)**,31 个 | `sw_industry.csv` 的 `sw_name` 即 L1;L2/L3 会让 tab 数爆炸,本期不做 |

## 3. 性能结论(已实测,含生产 4GB 机)

档位=均线多空打分,区间=滚动波动率×经验分布分位,**纯 numpy 确定性计算,无 LLM/API/token**。

**内存是关键**:生产机 4GB **无 swap**,快照(cn_engine)本身峰值 ~2GB;若 market_grade 也用 `load_matrices` 建全市场大矩阵(实测本机 21s/2GB、生产 140s/2GB),两者并发 = 4GB > 可用 3.1GB → **OOM**(可能连累 postgres)。

故最终实现走**逐股流式**(§4.1):每只读自己的日频 CSV、算完只留标量、丢弃序列,**不建大矩阵**。实测:

| | 本机 | 生产(4GB) |
|---|---|---|
| 耗时 | 21s | **204s**(读 5507 CSV,IO 单核) |
| 峰值内存 | 190MB | **115MB** |
| 输出 | 5120 只 | 5121 只(剔停牌/退市久的) |

204s 慢但**后台预热 + 30min 缓存**,用户走缓存不受影响;runner 超时 5min。115MB 与快照并发也绝不 OOM。

## 4. 架构:主快照不膨胀(核心)

**红线:5300 只带档位不能塞进 `/api/snapshot`**(每次页面加载都传、且逐用户 personalize → 1MB+ × 每次)。拆成两条链路:

```
        推荐股(~120) + 用户自选        全市场行情+档位(~5300)
              │                              │
        /api/snapshot (原样,个性化)     /api/market (新增,全用户共享,缓存)
              │                              │
              └──────────── 前端合并 ────────┘
        Tab1/2 用 snapshot ; Tab板块 用 market,推荐股 join snapshot 取富数据
```

### 4.1 引擎:`market_grade_cn.py`(逐股流式,内存友好)

独立脚本,**不复用快照的 `M` 大矩阵**(那会 2GB → OOM)。逐个 CSV:读 `close/turn/amount/pctChg/isST` →
构造单股迷你 `M={"close":df1}` 复用 `trend_grade_cn`/`vol_scaled_prob` → 取末行行情 → 存标量、丢弃序列。
峰值仅 ~115MB。停牌/退市久(末交易日距市场最新 >10 日)剔除。`sector` 来自 `sw_industry.csv`(code→申万一级)。
输出**紧凑** JSON(前端一次拉全,做 filter/排序/搜索/分页):

```jsonc
{
  "asof": "2026-08-12",
  "stocks": [
    { "code":"sh.600000", "name":"浦发银行", "sector":"银行",
      "price":9.01, "pct":-1.2, "turn":0.8, "amount":3.2e8, "fmc":2600, "st":false,
      "grade":-1, "grade_label":"转弱",
      "h20":{ "median":0.0045, "band70":[-0.058,0.072], "target":9.37, "stop":8.37,
              "p_target":0.196, "p_stop":0.158 } }
    // …约 5300 行
  ]
}
```

- 字段全部来自 `M`:`close`(price)、`pct`、`turn`、`amount`(成交额)、`fmc`(流通市值)、`st`;`sector` 来自 `sw_industry.csv`(`code→sw_name` L1);`grade/h20` 复用 `trend_grade_cn`/`vol_scaled_prob`。
- **不含** `signals/indicators/reason`(那些重字段只推荐股才需要,点股详情时走现有 `/api/focus` 按需取)。
- 体积:~5300 行 × ~150B ≈ **0.8MB raw / gzip ~150KB**,可接受。
- 新脚本 `engine/market_grade_cn.py`(独立可跑),或在 `run_daily.py` 快照后追加一步。倾向**独立脚本 + run_daily 调用**,便于单测。

### 4.2 后端:新增缓存端点

- `GET /api/market?market=cn` → 返回整张 `market_cn.json`(全用户共享)。
- 缓存:仿 `sectorCache` 模式(内存 + TTL,快照刷新时失效),`Runner.RunMarketGrade` 触发引擎。
- **不做服务端分页/搜索** —— 数据小(<1MB),一次性返回,前端做 filter/sort/search/分页,页面切换零延迟(贴合截图那种即点即翻)。
- 推荐标记:前端把 market 行与已在内存的 snapshot holdings 求交,命中即"推荐"。

### 4.3 前端:Dashboard 重构

- **Tab 栏**:`[推荐] [自选]` 固定 + 31 行业**横向滚动** chip;右侧/上方**全局搜索框**。
- **Tab 推荐/自选**:沿用现有 `mainRows`/`customRows`,套分页。
- **Tab 板块 X**:从 market 表 filter `sector===X`;排序 = 推荐股置顶 → 档位高→低 → 成交额高→低;推荐股用 snapshot 富数据渲染(选股依据/动作),非推荐股用 market 行渲染(档位/区间/行情)。套分页。
- **搜索**:输入即切到「搜索结果」视图,`q` 对**全市场** filter(代码含 `q` 或名称含 `q`),跨板块;清空回到当前 tab。
- **`<Pagination>` 新组件**(通用):`N 条 · 第 x/y 页` · 上一页 · 页码(首尾+当前邻近,省略号)· 下一页 · `每页 N 条`(10/20/50)· 跳至。受控:`total/page/size/onChange`。样式并入 `index.css`,配色走现有 token(涨跌用 `--rise/--fall`,不新造)。

### 4.4 列(板块 tab)

星标(自选) · 标的(code+中文名) · 板块 · 现价 · 涨跌% · 换手 · 成交额 · 档位(GradeBadge) · 20日区间 · [推荐股额外] 选股依据/动作。非推荐股这些"额外"列留空或 `—`。

## 5. 改动清单

**引擎**
- `engine/market_grade_cn.py`(新)—— 全市场档位+行情+板块 → JSON。
- `engine/run_daily.py` —— 快照后调用产出 `market_cn.json`。

**后端**
- `server/internal/api/api.go` —— `/api/market` handler + `marketCache` + warm。
- `server/internal/engine/runner.go` —— `RunMarketGrade`。
- (scheduler 复用现有快照刷新节奏)。

**前端**
- `client/src/components/Pagination.tsx`(新)。
- `client/src/pages/Dashboard.tsx` —— tab 栏 + 搜索 + 分页,渲染分流。
- `client/src/api.ts` —— `fetchMarket()` + 类型 `MarketStock`。
- `client/src/index.css` —— `.pagination`、tab 栏、搜索框样式。

## 6. 非目标(本期不做)

- L2/L3 分级 tab(仅 L1)。
- 给非推荐股产出 `reason/signals`(点详情按需)。
- LLM 板块解读(独立功能,后续单议)。
- 服务端分页/搜索(数据量不需要)。

## 6.5 部署注记

- **`sw_industry.csv` 生产缺失**:`engine/data_cn_meta` 是软链 → `safna_jr_a/data/meta`,生产只镜像了部分文件(sector flow 用 `sw_levels.json`,从没用过 `sw_industry.csv`)。已手动 `scp engine/data_cn_meta/sw_industry.csv → 服务器 safna_jr_a/data/meta/`。**重建服务器数据镜像时勿漏此文件**,否则板块列全「其他」。
- runner `RunMarketGrade` 超时 5min(生产 204s + 余量);warmMarket 并入 `StartSectorWarmer`(启动 + 每 25min)。

## 7. 风险 / 待验

- `market_cn.json` 与 snapshot 的 `asof` 一致性(同一次快照产出,天然对齐)。
- 横向滚动 tab 条在窄屏的可用性(加左右渐隐 + 可拖动)。
- 搜索 debounce,避免每键 filter 5300 行卡顿(实测 5300 行 filter 应 <5ms,基本无需 debounce,仍加 120ms 稳妥)。
