# Sentinel MCP server

把每个页面的用户操作都包成 MCP 工具,让 agentic AI / Claude 直接驱动、测试整个 app。
薄封装后端 HTTP API(`SENTINEL_API`,默认 `http://localhost:8787`)。源码 `server/cmd/mcp/main.go`。

## 启用(让 Claude Code 能调用)
1. 先起后端:`./scripts/run-dev.sh`(或 `cd server && go run ./cmd/server`)。
2. MCP 配置已在 `.mcp.json`(用 `go run ./cmd/mcp`)。在本项目目录打开 Claude Code 会自动连;
   若在别的目录用,把 `.mcp.json` 的 `sentinel` 块加进那个会话的 MCP 配置,然后重开会话。
3. **鉴权**:全 app 需登录,MCP 启动时用管理员凭据(`SENTINEL_ADMIN_EMAIL`/`PASSWORD`,由 env 设置,无默认)登录拿 JWT,所有调用带上。以管理员身份驱动(可用重算等)。

## 工具清单(= 页面按钮,共 24)
| 工具 | 对应按钮/页面 |
|---|---|
| `sentinel_snapshot` / `sentinel_snapshot_dates` | 策略信号页 / 历史日期 |
| `sentinel_run` | 【重算】(仅管理员) |
| `sentinel_watchlist` | 查关注★+自定义追踪(带 starred/custom) |
| `sentinel_star` | 【★关注/取消】(on=true/false) |
| `sentinel_track_add` / `sentinel_track_remove` | 【添加/移除 自定义追踪股】 |
| `sentinel_capital` | 【我的资金池】(set=金额则改) |
| `sentinel_focus` | 单股 focus 分析 |
| `sentinel_positions` | 我的持仓页 |
| `sentinel_trend` / `sentinel_trend_multi` / `sentinel_trend_tickers` | 走势(单/多股/可选清单) |
| `sentinel_explain` | 【AI讲解/重新讲解】 |
| `sentinel_investigate` | 【背景调查】(自动返回 HTML) |
| `sentinel_earnings_quarters` / `sentinel_earnings` | 【财报:季度/解读】(自动返回 HTML) |
| `sentinel_allocate` | 【AI 分配】 |
| `sentinel_universe` | 添加自定义股搜索源(1393只) |
| `sentinel_meta` / `sentinel_strategies` / `sentinel_history` / `sentinel_datastatus` / `sentinel_version` | 元数据 / 策略 / 历史 / 状态 / 版本 |

## 自测
`python3 tmp/mcp_full_test.py` 驱动全部工具。实测 **24 工具 / 29 项全通、0 报错**
(含资金池读写、关注/自定义分离、per-user 隔离验证)。
