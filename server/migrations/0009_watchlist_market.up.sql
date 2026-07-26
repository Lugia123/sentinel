-- 0009_watchlist_market — watchlist/focus_cache 加 market 维度(修复:美股自定义股/关注混进 A股列表)
-- A股 ticker 为 sh./sz. 前缀,存量行按前缀回填。

ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS market TEXT NOT NULL DEFAULT 'us';
UPDATE watchlist SET market='cn' WHERE lower(ticker) LIKE 'sh.%' OR lower(ticker) LIKE 'sz.%' OR lower(ticker) LIKE 'bj.%';
ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS watchlist_pkey;
ALTER TABLE watchlist ADD PRIMARY KEY (user_id, market, ticker);

ALTER TABLE focus_cache ADD COLUMN IF NOT EXISTS market TEXT NOT NULL DEFAULT 'us';
UPDATE focus_cache SET market='cn' WHERE lower(ticker) LIKE 'sh.%' OR lower(ticker) LIKE 'sz.%' OR lower(ticker) LIKE 'bj.%';
ALTER TABLE focus_cache DROP CONSTRAINT IF EXISTS focus_cache_pkey;
ALTER TABLE focus_cache ADD PRIMARY KEY (user_id, market, ticker, asof);
