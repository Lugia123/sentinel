-- 0017_stock_keywords — 个股滚动叙事关键词(news_lab R11)
CREATE TABLE IF NOT EXISTS stock_keywords (
  market      TEXT NOT NULL DEFAULT 'cn',
  ticker      TEXT NOT NULL,
  asof        DATE NOT NULL,
  keywords    JSONB NOT NULL,          -- [{kw, weight, why}] 当前叙事关键词
  summary     TEXT NOT NULL DEFAULT '',-- 一句话叙事总结
  n_news      INT NOT NULL DEFAULT 0,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (market, ticker, asof)
);
