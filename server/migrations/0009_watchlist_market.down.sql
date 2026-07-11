ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS watchlist_pkey;
ALTER TABLE watchlist DROP COLUMN IF EXISTS market;
ALTER TABLE watchlist ADD PRIMARY KEY (user_id, ticker);

ALTER TABLE focus_cache DROP CONSTRAINT IF EXISTS focus_cache_pkey;
ALTER TABLE focus_cache DROP COLUMN IF EXISTS market;
ALTER TABLE focus_cache ADD PRIMARY KEY (user_id, ticker, asof);
