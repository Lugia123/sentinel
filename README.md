# Sentinel — 美股策略决策支持系统

**研究工具,非投资建议。** 把 `safna_jr` 多轮量化研发(R1–R35)沉淀下来的**已验证部件**做成一个每日可用的决策支持仪表盘:选股 → 定仓 → 每日档位 → 到价概率 → 风险灯,供**手动**在券商(老虎)执行。

## 定位(诚实)
经 35 轮研究反复证伪,得到一条硬结论:**本 universe 里方向不可预测、日频自动择时不能稳定提升风险调整收益**。因此 Sentinel **不是自动交易黑箱**,而是**决策支持工具**——它给你信号和概率,由你判断和执行。

## 已验证部件(研究结论,见 `docs/research-provenance.md`)
| 部件 | 结论 | 来源 |
|---|---|---|
| 选股 = 动量哨兵(窄98池趋势门)50 / SY 股东收益率(宽池)50 | 2011+ Sharpe≈1.22/回撤-20% | R24/R28 |
| 定仓 = 风险平价(逆波动)按资金池 | — | R35 |
| 每日档位 = 7 档趋势状态,**松·只减**跟法 | 降回撤(-24%→-20%),不追涨(追涨=负EV) | R35 v4 |
| 到价概率 = 波动缩放经验分布(5/20/60日) | 样本外校准良好(覆盖率贴名义) | R33 |
| 风险灯 = 波动目标体制闸 | 极端波动降仓提示 | R30 |

## 架构
```
client/       React + Vite + TS + ECharts        仪表盘(暗色金融风)
server/       Go (net/http) + gorm               API + 编排 + ingest
  migrations/ 编号 SQL 迁移(对齐 Tinia)
engine/       Python(复用 safna_jr 已验证逻辑)   每日算快照 JSON(选股/定仓/档位/概率/风险)
data/         引擎产出的 JSON(ingest 源,不入库)
PostgreSQL    快照/持仓/价格/运行日志持久化
```
Go 后端触发 Python 引擎算快照(产 JSON)→ ingest 入 PostgreSQL → 经 API 供 React。参考 Tinia 的 Go+Python+PG 模式。

## 数据库(PostgreSQL)
- 连接 Docker 容器 `bestfunc-postgres`(postgres:16,宿主端口 **5433**)里的独立库 **sentinel**。
- 建库:`docker exec bestfunc-postgres createdb -U bestfunc sentinel`
- 配置:复制 `server/.env.example` → `server/.env`,填 DSN(密码不入库);后端启动时**自动跑迁移**。
- 5 张表:`snapshots`(每日快照,asof 唯一)`holdings`(快照内持仓)`prices`(日度收盘)`positions`(用户实际持仓)`runs`(运行日志)。详见 `server/migrations/0001_init.up.sql`。

## 快速开始
```bash
cp server/.env.example server/.env   # 填 DB 密码
./scripts/run-dev.sh                  # 引擎 → 后端(自动迁移)→ 前端:5173
```

## 红线
只做多、手动执行、真摩擦分档税、无前视、必带免责声明、不写密钥(只在 `.env`)。
