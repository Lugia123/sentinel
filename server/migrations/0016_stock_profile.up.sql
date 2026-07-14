-- 0016_stock_profile — 个股关联画像(news_lab R10):行业/概念/主营关键词/上游商品映射
CREATE TABLE IF NOT EXISTS stock_profile (
  market      TEXT NOT NULL DEFAULT 'cn',
  ticker      TEXT NOT NULL,
  name        TEXT NOT NULL DEFAULT '',
  industry    TEXT NOT NULL DEFAULT '',       -- 行业(申万/同花顺)
  concepts    TEXT[] NOT NULL DEFAULT '{}',    -- 概念板块
  keywords    TEXT[] NOT NULL DEFAULT '{}',    -- 主营关键词(AI/公告抽取)
  commodities TEXT[] NOT NULL DEFAULT '{}',    -- 上游商品映射(铜/锂/油...)
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (market, ticker)
);
