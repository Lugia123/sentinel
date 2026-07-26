# Sentinel — 开发约定(给 Claude / 协作者)

## 是什么
A股 + 美股 双市场**策略决策支持**仪表盘(量化研究的产品化)。**非投资建议、非自动交易**——给信号 + 概率 + 市场风险灯,人工执行。策略引擎逻辑已 vendor 进 `engine/lib/`(自包含,无外部研究库依赖)。

## 架构与目录
- `engine/` **Python 策略引擎(核心)**:`cn_engine.py`(A股)/`run_daily.py`(美股)产出每日快照 JSON(选股/定仓/档位/到价概率/风险灯)。策略库在 `engine/lib/`;数据在 `SENTINEL_DATA_DIR`(默认 `engine/data`,含 `daily/meta/alt`),用 `engine/lib/dl_*.py`、`refresh_data.py`、`ts_refresh.py` 生成(**数据不入库,用户自行拉取**)。
- `server/` **Go 后端**(net/http + gorm):module `sentinel`,`cmd/server/main.go` 入口,`internal/{api,engine,store,portfolio,db,config,version}` + `migrations/`(编号 SQL)。职责=连 PG + 迁移、触发引擎、ingest 入库、供 API。
- `client/` **React + Vite + TS + ECharts** 暗色仪表盘:`src/{api,components,pages,types}` + App.tsx。
- 数据流:`engine/` 产 JSON → Go ingest → **真源 PostgreSQL** → API → 前端。DB 密码等只在 `server/.env`(gitignore,见 `server/.env.example`)。
- **gorm 坑**:标量单值查询用 `.Raw(...).Row().Scan(&x)`,别用 `.Scan(&x)`(后者只对 struct/slice 生效,标量静默不填充)。

## 数据契约(引擎→后端→前端唯一接口)
每日快照 JSON = `engine/schema.md` 定义。字段:asof、holdings[]、risk_light、portfolio。改字段必须三端同步 + 更新 schema.md。

## 铁律
- 只做多、手动可执行、真摩擦分档税、**无前视(PIT)**、幸存者偏差下界标注。
- **数值极易错必多重交叉核验**。
- 诚实定位:不吹自动 alpha;档位=趋势状态(A股逐票只展示、风控归市场级风险灯);概率=校准分布,非方向预言。
- 不写密钥(只在 `.env`);commit 前先本地验证。

## 开发命令
- 引擎:`cd engine && python cn_engine.py --asof latest`(A股)
- 后端:`cd server && go run ./cmd/server`
- 前端:`cd client && npm run dev`
- 一键 dev:`scripts/run-dev.sh`
