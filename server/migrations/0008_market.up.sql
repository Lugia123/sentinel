-- 0008_market — v2.0 双市场:加 market 维度(默认 'us',向后兼容存量美股数据)
-- A股 ticker 为 sh./sz. 前缀,与美股天然不冲突;market 列用于市场级过滤与快照隔离。

-- ① snapshots:asof 市场无关 → 唯一键改 (market, asof)
ALTER TABLE snapshots ADD COLUMN IF NOT EXISTS market TEXT NOT NULL DEFAULT 'us';
ALTER TABLE snapshots DROP CONSTRAINT IF EXISTS snapshots_asof_key;
ALTER TABLE snapshots ADD CONSTRAINT snapshots_market_asof_key UNIQUE (market, asof);

-- ② holdings:加 market(便于跨快照按市场+ticker查历史)
ALTER TABLE holdings ADD COLUMN IF NOT EXISTS market TEXT NOT NULL DEFAULT 'us';
CREATE INDEX IF NOT EXISTS idx_holdings_market_ticker ON holdings(market, ticker);

-- ③ prices:主键改 (market, ticker, date)
ALTER TABLE prices ADD COLUMN IF NOT EXISTS market TEXT NOT NULL DEFAULT 'us';
ALTER TABLE prices DROP CONSTRAINT IF EXISTS prices_pkey;
ALTER TABLE prices ADD PRIMARY KEY (market, ticker, date);

-- ④ positions / runs:加 market
ALTER TABLE positions ADD COLUMN IF NOT EXISTS market TEXT NOT NULL DEFAULT 'us';
ALTER TABLE runs      ADD COLUMN IF NOT EXISTS market TEXT NOT NULL DEFAULT 'us';
