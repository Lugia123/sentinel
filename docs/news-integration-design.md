# A股新闻模块集成设计(news → sentinel app)

> 现状:`engine/news/` 引擎/数据层已建好并验证(27轮),迁移 0012-0017 已应用。
> **未做**:Go API、React 前端、调度器接入。本文设计这部分。
> 铁律(按 15 轮 L3 结论):**新闻独立,绝不进策略计算**——只做资讯/解释/风险展示。

## 0. 独立性保证(最重要)

新闻是**纯 overlay**,与策略引擎物理隔离:

| | 策略侧(现有,不动) | 新闻侧(新增) |
|---|---|---|
| 引擎 | cn_engine.py / focus_cn.py / run_daily.py | engine/news/*(独立) |
| 数据表 | snapshots/holdings/prices/focus_cache | news_items/stock_announcements/news_digest/… |
| 计算 | 档位/动作/概率/风险灯 = 纯价格+基本面 | 日报/关联/关键词/信号旗 |
| 触发 | 调度器策略任务 | 调度器**独立**新闻任务(错峰) |

**红线**:
- cn_engine/focus_cn/run_daily **永不读新闻表**;快照的 grade/action/prob 计算逻辑一字不改。
- 新闻信号旗(attention/avoid/vol_warn)是**展示层**,绝不改 grade/action。
- 前端新闻区块统一标注"资讯参考,非策略信号,非投资建议"。
- 删除新闻功能 → 策略功能完全不受影响(可独立开关)。

## 1. 读写分工(沿用现有 Python写-Go读 模式)

- **Python(engine)= 写侧**:collector 采集、news_daily 日报、news_link/keywords 关联(调度/触发)。
- **Go(backend)= 读侧**:查新闻表供 API 展示(gorm 直查,不调 Python)。
- 与现有一致:Python 产快照 → Go 读快照。新闻同理。

## 2. Go 后端(internal/news + api)

新增只读 API(全部 market-scoped,与策略端点解耦):
```
GET /api/news/digest?market=cn          → 今日要闻日报(news_digest 最新)
GET /api/news/stock?ticker=&market=cn   → 个股:关联新闻 + 叙事关键词 + 信号旗
GET /api/news/calendar?market=cn        → 未来事件日历(event_calendar)
```
- `internal/news/service.go`:gorm 查表;信号旗逻辑用 SQL(简单 LIKE,复刻 news_signals.py)。
- 挂到现有 mux(api.go),走现有 auth 中间件。**不碰 snapshot/focus/allocate 任何 handler**。

## 3. 调度器(scheduler,独立任务)

现有调度器每 N 小时跑双市场策略。新增**独立新闻任务**(错峰,如策略后 30 分钟):
```
[news] 每日盘后:
  1. news_collector.py --macro                    # 宏观快讯+央视
  2. news_collector.py --stocks <watchlist代码>    # 关注股新闻+公告
  3. news_global.py --collect(主题轮转,防限频)    # 全球一手
  4. news_link.py --today + news_daily.py --gen    # 关联 + 日报
```
- 用现有 `Runner.RunPython`(已有,backfill/refresh 都用)。
- 失败不影响策略任务(独立 goroutine + try/catch);限频退避(R10/R12 教训)。
- 个股 keywords/signals:按需算(详情页打开时触发,类似 investigate/earnings 的懒加载+缓存)。

## 4. React 前端

- **新导航 tab「今日要闻」**:日报页(综述/世界大事/国内大事/板块影响/**全球传导 lead-lag**)。
  纯展示 news_digest,与策略页并列,互不影响。
- **StockDetail 新增「相关新闻」tab**(与现有 背调/财报 tab 并列):
  关联新闻列表(按 relation 分组)+ 叙事关键词云 + **信号旗**(attention/avoid/vol_warn,带依据+免责)。
- **掉出分析(v2.1)引用关联新闻**:掉出原因 AI 分析注入近期关联新闻摘要(已在 v2.1 explain 预留)。
- 全部新闻 UI 底部固定:「资讯参考 · 非策略信号 · 非投资建议」。

## 5. 部署增量

- 迁移 0012-0017 → scp 到服务器 migrations/,重启自动应用(幂等)。
- engine/news/ → rsync(已含 __init__.py)。
- 服务器 venv 补装:collector 需 akshare(已装)、news_global 需 requests(标准)、newsai 需 openai(补装)。
- Go 二进制重编上传(含 news 包)。前端 build。

## 6. 分阶段落地建议(可增量,每阶段独立可用)

1. **Phase 1 只读日报**:Go /api/news/digest + 前端「今日要闻」tab + 调度器日报任务。最快见效,零策略耦合。
2. **Phase 2 个股新闻**:/api/news/stock + StockDetail「相关新闻」tab + 按需关联/关键词。
3. **Phase 3 信号旗 + 掉出引用**:signals 展示 + 掉出分析引用新闻。
4. **Phase 4 全球+日历**:全球传导段 + 事件日历(GDELT 主题轮转)。

## 7. 工作量

- Go:internal/news 包 + 3 端点 + 调度器任务 ≈ 中等。
- 前端:1 新页 + 1 详情 tab ≈ 中等。
- 引擎:已完成(0 增量,仅调度接线)。
- 一天内可完成 Phase 1-2(核心价值),Phase 3-4 增量。
