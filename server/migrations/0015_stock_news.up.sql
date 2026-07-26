-- 0015_stock_news — 新闻↔个股关联(news_lab R9)。多对多:一条政策新闻可关联多股。
CREATE TABLE IF NOT EXISTS stock_news (
  market      TEXT NOT NULL DEFAULT 'cn',
  ticker      TEXT NOT NULL,           -- 归一化代码(sh.600000)
  news_id     BIGINT NOT NULL REFERENCES news_items(id) ON DELETE CASCADE,
  relation    TEXT NOT NULL DEFAULT 'company',  -- company/industry/concept/supply/macro
  confidence  REAL NOT NULL DEFAULT 1.0,
  matched     TEXT NOT NULL DEFAULT '',         -- 命中的名称/关键词(可核验)
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (market, ticker, news_id)
);
CREATE INDEX IF NOT EXISTS idx_stocknews_ticker ON stock_news(market, ticker);
CREATE INDEX IF NOT EXISTS idx_stocknews_news ON stock_news(news_id);
