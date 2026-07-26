-- 用户关注列表(关注的股票在列表置顶)
CREATE TABLE IF NOT EXISTS watchlist (
  ticker   TEXT        NOT NULL PRIMARY KEY,
  source   TEXT        NOT NULL DEFAULT 'ai',   -- ai=AI选中的; user=用户手动加的(可能不在AI持仓里)
  added_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
