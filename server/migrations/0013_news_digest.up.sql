-- 0013_news_digest — 每日金融要闻日报(news_lab R6)
CREATE TABLE IF NOT EXISTS news_digest (
  market      TEXT NOT NULL DEFAULT 'cn',
  digest_date DATE NOT NULL,
  digest      JSONB NOT NULL,          -- {overview, world[], domestic[], market_impact[], calendar[]}
  n_source    INT NOT NULL DEFAULT 0,  -- 生成时用到的新闻条数
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (market, digest_date)
);
