-- 0005_isolation — 用户数据隔离(持仓/关注/AI讲解 按用户;策略快照仍共享)
ALTER TABLE positions    ADD COLUMN IF NOT EXISTS user_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE watchlist    ADD COLUMN IF NOT EXISTS user_id BIGINT NOT NULL DEFAULT 1;
ALTER TABLE explanations ADD COLUMN IF NOT EXISTS user_id BIGINT NOT NULL DEFAULT 1;

-- 关注:主键 ticker → (user_id, ticker)
ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS watchlist_pkey;
ALTER TABLE watchlist ADD PRIMARY KEY (user_id, ticker);

-- AI讲解缓存:主键含 user_id(每个用户独立缓存)
ALTER TABLE explanations DROP CONSTRAINT IF EXISTS explanations_pkey;
ALTER TABLE explanations ADD PRIMARY KEY (user_id, ticker, asof, kind);

CREATE INDEX IF NOT EXISTS idx_positions_user ON positions(user_id);

-- 自定义股每日档位缓存(按用户+股+数据日;快照读取时合并自定义股,避免重复跑focus)
CREATE TABLE IF NOT EXISTS focus_cache (
  user_id    BIGINT NOT NULL,
  ticker     TEXT   NOT NULL,
  asof       DATE   NOT NULL,
  holding    JSONB  NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, ticker, asof)
);
