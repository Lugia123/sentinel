# Sentinel — 开发约定(给 Claude / 协作者)

## 是什么
`safna_jr` 研究(R1–R35)的**产品化**:美股 $4000 账户策略**决策支持**仪表盘。**非投资建议、非自动交易**——给信号+概率,人工执行。

## 架构与目录
- `engine/` **Python 策略引擎(核心,复用 safna_jr 已验证逻辑)**:`run_daily.py` 产出每日快照 JSON(选股/定仓/7档/到价概率/风险灯)。数据源 `engine/data/`(软链到 safna_jr/round20/data_broad,live 用 yfinance 刷)。
- `server/` **Go 后端**(net/http + gorm):module `sentinel`,`cmd/server/main.go` 入口,`internal/{api,engine,store,portfolio,db,config,version}` + `migrations/`(编号 SQL)。职责=连 PG+迁移、触发引擎、ingest 入库、供 API。
- `client/` **React+Vite+TS+ECharts** 暗色仪表盘:`src/{api,components,types}` + App.tsx(tabs:策略信号/我的持仓)。
- `engine/` 产 JSON;`data/` 是 ingest 源(gitignore);**真源是 PostgreSQL**(容器 bestfunc-postgres:5433 库 sentinel)。DB 密码只在 `server/.env`。
- **gorm 坑**:标量单值查询用 `.Raw(...).Row().Scan(&x)`,别用 `.Scan(&x)`(后者只对 struct/slice 生效,标量静默不填充)。

## 数据契约(引擎→后端→前端唯一接口)
每日快照 JSON = `engine/schema.md` 定义。字段:asof、holdings[]、risk_light、portfolio。改字段必须三端同步 + 更新 schema.md。

## 铁律(承接 safna_jr)
- 只做多、手动可执行、真摩擦分档税(LTCG15/STCG25)、**无前视(PIT)**、vs SPY、幸存者下界标注。
- **数值极易错必多重交叉核验**(引擎产数须能对上 safna_jr 已验证口径)。
- 诚实定位:不吹自动 alpha;档位=松·只减防御减仓;概率=校准分布非方向预言。
- 不写密钥(只在 `.env`);本地 git 管理;commit 前先本地验证。

## 研究溯源
每个部件的验证结论见 `docs/research-provenance.md`,对应 `safna_jr/PROGRESS.md` 的轮次。改策略逻辑前先读溯源,别推翻已证伪的方向(如:找正交第三腿=死路、日频自动择时不加Sharpe)。

## 开发命令
- 引擎:`cd engine && python run_daily.py --asof latest`
- 后端:`cd server && go run ./cmd/server`
- 前端:`cd client && npm run dev`
- 一键 dev:`scripts/run-dev.sh`
