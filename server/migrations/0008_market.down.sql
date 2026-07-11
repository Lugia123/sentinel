-- 0008_market 回滚
ALTER TABLE prices DROP CONSTRAINT IF EXISTS prices_pkey;
ALTER TABLE prices ADD PRIMARY KEY (ticker, date);
ALTER TABLE prices DROP COLUMN IF EXISTS market;

ALTER TABLE snapshots DROP CONSTRAINT IF EXISTS snapshots_market_asof_key;
ALTER TABLE snapshots ADD CONSTRAINT snapshots_asof_key UNIQUE (asof);
ALTER TABLE snapshots DROP COLUMN IF EXISTS market;

DROP INDEX IF EXISTS idx_holdings_market_ticker;
ALTER TABLE holdings  DROP COLUMN IF EXISTS market;
ALTER TABLE positions DROP COLUMN IF EXISTS market;
ALTER TABLE runs      DROP COLUMN IF EXISTS market;
