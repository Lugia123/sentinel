-- 0014_event_calendar — 前瞻大事日历(news_lab R7)
-- 可预知事件比突发更有前瞻价值。来源:财报发布(baidu,可靠)+ 新闻流AI抽取的前瞻事件。
CREATE TABLE IF NOT EXISTS event_calendar (
  market      TEXT NOT NULL DEFAULT 'cn',
  event_date  DATE NOT NULL,
  category    TEXT NOT NULL,            -- earnings / macro / policy / meeting
  title       TEXT NOT NULL,
  ticker      TEXT,                     -- 财报类事件挂靠代码
  importance  INT NOT NULL DEFAULT 1,   -- 1-3
  source      TEXT NOT NULL DEFAULT '',
  fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (market, event_date, category, title)
);
CREATE INDEX IF NOT EXISTS idx_evcal_date ON event_calendar(market, event_date);
