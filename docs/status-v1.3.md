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
- MinIO 接入 `internal/blob`(bestfunc-minio,sentinel bucket)

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

### P4 AI 升级(部分)
- ★ 背景调查(#9b):`internal/investigate` DeepSeek→HTML→MinIO→详情「背景调查」tab + 重新背调

## 剩余(P4 未完)
1. **#2 AI 讲解升级为 HTML**:当前讲解是纯文本段落(清晰可用);可改为 DeepSeek 生成富 HTML(配图/图表)存 MinIO,详情页 iframe 展示。参考 investigate 的实现。
2. **MCP server + skill**:建 Sentinel MCP(无认证,参考 Tinia `_shared/local-mcp`)暴露策略数据工具,让 agentic AI(背调/财报)能自己拉数据做更深调研。当前背调是 DeepSeek 塞 prompt(方案A);MCP 是方案 B。
3. **#9c 财报解读**:用户选季度 → SEC EDGAR 取 10-Q/10-K(已有 fp 基建可扩)→ AI 解读 → HTML → MinIO → 详情「财报解读」tab(用户触发)。

## 已知增强点
- P3 走势:某股只在被选中日有档位(gappy);连续任意股走势需 per-day focus 计算(可加 `engine/trend.py`)。
- 前端 bundle 偏大(echarts 1.2MB),可 code-split。
- 实时数据(yfinance 每日刷新)未接——定时任务目前跑现有静态数据;接入后才拿新交易日。
- 选股范围决策:动量 98 大盘 / SY 1393 含中小盘(保持现状,已记 `architecture-v1.3.md` + 帮助页)。

## 安全
- 所有密钥(DB/DeepSeek/MinIO)只在 `server/.env`(gitignore)。
- ⚠️ DeepSeek key 曾在排查时误露一次,建议轮换。
