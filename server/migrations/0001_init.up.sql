-- 0001_init — Sentinel 初始 schema
-- 混合范式:关键列规范化(便于查询/聚合)+ raw/prob 用 JSONB(保留完整数据契约)

-- ① 日度收盘价(喂 P&L + 准确率回测;由引擎产出后 ingest)
CREATE TABLE IF NOT EXISTS prices (
  ticker TEXT          NOT NULL,
  date   DATE          NOT NULL,
  close  NUMERIC(14,4) NOT NULL,
  PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(date);

-- ② 每日策略快照(asof 唯一 → 幂等重跑 upsert)
CREATE TABLE IF NOT EXISTS snapshots (
  id             BIGSERIAL PRIMARY KEY,
  asof           DATE          NOT NULL UNIQUE,
  generated_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
  capital        NUMERIC(14,2) NOT NULL,
  risk_level     TEXT          NOT NULL,
  spy_vol        NUMERIC(8,4),
  exposure       NUMERIC(6,4),
  gross_exposure NUMERIC(6,4),
  cash_pct       NUMERIC(6,4),
  raw            JSONB         NOT NULL
);

-- ③ 快照内持仓(规范化,便于按 ticker/时间查历史 + 做准确率)
CREATE TABLE IF NOT EXISTS holdings (
  id            BIGSERIAL PRIMARY KEY,
  snapshot_id   BIGINT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
  ticker        TEXT   NOT NULL,
  sleeve        TEXT   NOT NULL,
  price         NUMERIC(14,4),
  base_weight   NUMERIC(8,6),
  target_shares NUMERIC(14,4),
  target_value  NUMERIC(14,2),
  grade         SMALLINT,
  action        TEXT,
  prob          JSONB,
  UNIQUE (snapshot_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_holdings_ticker ON holdings(ticker);

-- ④ 用户实际持仓(可变;opened_at 供持有期/税档)
CREATE TABLE IF NOT EXISTS positions (
  id         BIGSERIAL PRIMARY KEY,
  ticker     TEXT          NOT NULL,
  shares     NUMERIC(14,4) NOT NULL,
  cost       NUMERIC(14,4) NOT NULL,
  opened_at  DATE,
  note       TEXT,
  created_at TIMESTAMPTZ   NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- ⑤ 引擎运行日志(可观测)
CREATE TABLE IF NOT EXISTS runs (
  id          BIGSERIAL PRIMARY KEY,
  asof        DATE,
  status      TEXT NOT NULL,
  duration_ms INTEGER,
  log         TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
