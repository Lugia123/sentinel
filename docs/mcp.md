# Sentinel MCP server

把每个页面的用户操作都包成 MCP 工具,让 agentic AI / Claude 直接驱动、测试整个 app。
薄封装后端 HTTP API(`SENTINEL_API`,默认 `http://localhost:8787`)。源码 `server/cmd/mcp/main.go`。

## 启用(让 Claude Code 能调用)
1. 先起后端:`./scripts/run-dev.sh`(或 `cd server && go run ./cmd/server`)。
2. MCP 配置已在 `.mcp.json`(用 `go run ./cmd/mcp`)。在本项目目录打开 Claude Code 会自动连;
   若在别的目录用,把 `.mcp.json` 的 `sentinel` 块加进那个会话的 MCP 配置,然后重开会话。
3. 无认证(本地开发用)。

## 工具清单(= 页面按钮)
| 工具 | 对应按钮/页面 |
|---|---|
| `sentinel_snapshot` / `sentinel_snapshot_dates` | 策略信号页 / 历史日期 |
| `sentinel_run` | 【重算】 |
| `sentinel_watchlist` / `sentinel_watch_add` / `sentinel_watch_remove` | 【★关注/取消】 |
| `sentinel_focus` | 【自选股分析】 |
| `sentinel_positions` | 我的持仓页 |
| `sentinel_trend` / `sentinel_trend_multi` | 【单股走势】/【多股对比】 |
| `sentinel_explain` | 【AI讲解/重新讲解】 |
| `sentinel_investigate` | 【背景调查/重新背调】(自动返回 HTML) |
| `sentinel_earnings_quarters` / `sentinel_earnings` | 【财报解读:季度/解读这一季】(自动返回 HTML) |
| `sentinel_meta` / `sentinel_strategies` / `sentinel_history` / `sentinel_datastatus` / `sentinel_version` | 元数据 / 策略 / 历史 / 状态 / 版本 |

## 自测
`SENTINEL_API=http://localhost:8787 python3 <stdio 测试脚本>` 驱动全部工具(见开发记录)。
实测 18 工具全通、0 报错。
