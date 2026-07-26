# Sentinel 进度状态(feature/v1.3,截至 v1.3.18)

## 已完成(全部测试 + 提交)
### P0 视觉地基
- 黑金设计规范 `docs/design-system.md` + CSS tokens
- 顶部 Header 导航(品牌/菜单/重算)
- tooltip 层级/偏移修复(createPortal 到 body)
- 收益范围图颜色统一 + 图例说明(颜色=档位,长度=波动)

### P1 数据主干
- Go 定时任务(每日 05:30 自动跑 + 启动自愈)`internal/scheduler`
- 历史回填 `engine/backfill.py`(装一次循环,3.8s/日;已回填 2026 全年 120 日)
- MinIO 接入 `internal/blob`(MinIO 容器,sentinel bucket)

### ★ 架构重构(可插拔策略框架)
- `engine/strategies/`:5 类可注册组件(Selector/Sizer/Grader/Predictor/RiskGate)+ Context + 流水线
- 新增任意策略 = 写类 + @register + config,不改核心
- **回归:与重构前逐字节一致;as-of 5/5 通过**
- `/api/strategies` 暴露启用+可用组件;snapshot 带 strategy_config

### P2 元数据 + 交互
- 中文名 + 板块(`engine/ticker_meta.json` 98 覆盖)`/api/meta`,列表/详情显示
- 关注 watchlist(`/api/watchlist`,星标置顶)
- 自定义股分析(`engine/focus.py` + `/api/focus`,任意股同规则、资金池=这一只)

### P3 分析走势
- `/api/trend`(单股全指标序列 + 多股档位对比)
- 前端「分析走势」页(单股档位/中位双轴 + 多股档位对比)

### P4 AI 升级(基本完成)
- ★ 背景调查(#9b):`internal/investigate` DeepSeek→HTML片段→MinIO→详情「背景调查」tab + 重新背调
- #2 AI 讲解升级为 HTML:explain 输出结构化 HTML 片段(4 小标题),详情页注入渲染
- #9c 财报解读:`engine/earnings.py` 拉 SEC EDGAR 真实季度财务 → `internal/earnings` DeepSeek 解读(含 QoQ/YoY)→ MinIO → 详情「财报解读」tab(季度下拉选)
- ★ 背调/财报 HTML 改【片段注入渲染】(dangerouslySetInnerHTML),不用 iframe——无内嵌滚动,随整页滚(按用户要求)

## 剩余(P4 只剩 MCP)
1. **MCP server + skill**:建 Sentinel MCP(无认证,参考 Tinia `_shared/local-mcp`)暴露策略数据工具(snapshot/holding/history/trend/strategies),让 agentic AI 能自己拉数据做更深调研。当前背调/财报是 DeepSeek 塞 prompt(方案A);MCP 是方案 B(agentic)。当前 AI 功能不依赖它也完整可用。

## 已知增强点
- P3 走势:某股只在被选中日有档位(gappy);连续任意股走势需 per-day focus 计算(可加 `engine/trend.py`)。
- 前端 bundle 偏大(echarts 1.2MB),可 code-split。
- 实时数据(yfinance 每日刷新)未接——定时任务目前跑现有静态数据;接入后才拿新交易日。
- 选股范围决策:动量 98 大盘 / SY 1393 含中小盘(保持现状,已记 `architecture-v1.3.md` + 帮助页)。

## 安全
- 所有密钥(DB/DeepSeek/MinIO)只在 `server/.env`(gitignore)。
- ⚠️ DeepSeek key 曾在排查时误露一次,建议轮换。
