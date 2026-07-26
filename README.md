# Sentinel

A股 + 美股 **量化策略决策支持仪表盘**。策略引擎每日产出选股 / 定仓 / 趋势档位 / 到价概率 / 市场风险灯,通过 Go 后端 + React 前端呈现。

> ⚠️ **非投资建议、非自动交易。** 本项目是研究与决策支持工具,只给信号、概率和风险提示,不构成任何买卖推荐。市场有风险,盈亏自负,使用者对自己的决策负全部责任。详见 [LICENSE](LICENSE) 末尾声明。

---

## 特性

- **A股策略**(主线,已充分迭代)
  - 头号腿:小市值 × 低换手,周频调仓 + 换手阻尼(诚实 walk-forward 验证)
  - 事件腿:分析师评级上修 + 业绩预告惊喜(size 中性合成,容量友好)
  - 红利低波替代腿:高股息 × 低波动(大资金替代腿,与头号腿二选一)
  - 前端「头号腿 / 红利低波」策略选择器,按资金量级二选一
- **市场级风险灯(Gate)**:宽度 ∧ 非拥挤 ∧ 成交额未枯竭 ∧ 非背离 → 绿/黄/红三档总仓位。A股逐票只展示趋势档位、不逐票减仓(反转市特性),风控统一交给市场闸。
- **风险灯历史 + 灯 vs 走势对照**:制度带、日历热力图、信号分解;价格线叠加制度背景 + 制度收益归因,直接看"灯准不准"。
- **到价概率带**:未来 20 日收益的波动缩放经验分布(区间校准,非方向预测)。
- **美股引擎**:动量哨兵 + 股东收益率两腿(需额外数据,见下)。
- **AI 讲解**(可选):OpenAI 兼容接口(如 DeepSeek)解读每只标的的选中/掉出原因。
- **新闻/研报模块**(可选)、我的持仓盈亏、自选股追踪。

## 架构

```
engine/ (Python)   策略引擎:每日产出快照 JSON(选股/定仓/档位/概率/风险灯)
   ├─ cn_engine.py    A股引擎
   ├─ run_daily.py    美股引擎
   ├─ lib/            回测/因子/择时库(已自包含,无外部依赖)
   ├─ refresh_data.py 增量刷新行情(A股 baostock / 美股 yfinance)
   └─ ts_refresh.py   A股事件/红利另类数据(tushare)
       │  产出 JSON
       ▼
server/ (Go)       net/http + gorm:连 PostgreSQL + 迁移、触发引擎、ingest 入库、供 REST API
       │  REST
       ▼
client/ (React+Vite+TS+ECharts)   暗色仪表盘
```

数据流:引擎产 JSON → Go ingest → **真源 PostgreSQL** → API → 前端。数据契约见 `engine/schema.md`。

## 技术栈

Go(net/http, gorm)· PostgreSQL · Python(pandas/numpy/pyarrow)· React + Vite + TypeScript + ECharts · 数据源 baostock(A股行情,免费)/ akshare / tushare(A股另类)/ yfinance(美股)。

## 快速开始

### 前置
- Go 1.22+ · Node 18+ · PostgreSQL 14+ · Python 3.10+
- Python 依赖:`pip install pandas numpy pyarrow requests baostock akshare`

### 1. 配置
```bash
cp server/.env.example server/.env
# 编辑 server/.env:填 SENTINEL_DB_DSN(数据库)、SENTINEL_JWT_SECRET 等
```

### 2. 数据库
```bash
createdb sentinel                        # 用你 .env 里的用户/库名
# 迁移在后端启动时自动执行(server/migrations/*.up.sql)
```

### 3. 生成数据(⚠️ 数据不随仓库分发,需自行拉取)
数据默认放 `engine/data`(可用环境变量 `SENTINEL_DATA_DIR` 覆盖),子目录 `daily/`(日线)、`meta/`(股票名单/指数)、`alt/`(另类数据)。
```bash
cd engine
# A股日线(baostock,免费无需 token)
python lib/download_daily.py
# A股事件/红利另类数据(tushare,需 token)
export SENTINEL_TS_URL=https://api.tushare.pro SENTINEL_TS_TOKEN=<你的token>
python ts_refresh.py --full
```
> 美股(可选)需 yfinance 行情 + SEC EDGAR 基本面数据,数据准备更重。

### 4. 启动
```bash
# 一键(需 Docker PostgreSQL;可用环境变量覆盖容器/端口/用户)
scripts/run-dev.sh

# 或手动
cd server && go run ./cmd/server        # 后端 :8787(自动迁移)
cd client && npm install && npm run dev # 前端 :5173
```

## 配置(server/.env)

| 变量 | 说明 |
|---|---|
| `SENTINEL_DB_DSN` | PostgreSQL 连接串(必填) |
| `SENTINEL_JWT_SECRET` | 鉴权密钥(`openssl rand -hex 32`) |
| `SENTINEL_PYTHON` | 引擎用的 Python 解释器(默认 `python3`) |
| `SENTINEL_DATA_DIR` | 引擎数据目录(默认 `engine/data`) |
| `SENTINEL_DEEPSEEK_KEY` / `_BASE` / `_MODEL` | AI 讲解(可选,OpenAI 兼容) |
| `SENTINEL_TS_URL` / `_TOKEN` | A股另类数据 tushare(可选) |
| `SENTINEL_MINIO_*` | 对象存储(可选,新闻附件) |

密钥只放 `.env`(已 gitignore),**绝不入库**。

## 部署

生产部署(PostgreSQL + Go 后端 + nginx + React)见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## 免责声明

本软件按「原样」提供,不作任何担保。它**不提供**金融、投资或交易建议,输出的任何内容都不是买卖推荐。请自行判断、自担风险。

## 许可证

[MIT](LICENSE)
