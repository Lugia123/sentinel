-- 0012_news — 新闻系统(news_lab R3)采集落库
-- 两张主表:通用新闻流 news_items(宏观/大事/个股新闻) + 深历史公告 stock_announcements。
-- 冷启动:除公告(25年)/央视(可回补)外,快讯类只能从采集日起积累,故尽早上线跑。

-- 通用新闻(东财全球快讯/新浪/同花顺/央视/财新/个股新闻)
CREATE TABLE IF NOT EXISTS news_items (
  id           BIGSERIAL PRIMARY KEY,
  source       TEXT NOT NULL,                 -- em_global / sina_global / ths_global / cctv / caixin / stock_em
  fingerprint  TEXT NOT NULL,                 -- 去重指纹(source+标题+发布时刻的hash)
  title        TEXT NOT NULL DEFAULT '',
  body         TEXT NOT NULL DEFAULT '',
  url          TEXT NOT NULL DEFAULT '',
  keywords     TEXT NOT NULL DEFAULT '',      -- 源自带关键词(个股新闻有)/后续AI填
  ticker       TEXT,                          -- 个股新闻挂靠的代码(宏观新闻为 NULL)
  published_at TIMESTAMPTZ,                    -- 源声明的发布时刻(PIT基准)
  fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  market       TEXT NOT NULL DEFAULT 'cn',
  raw          JSONB,
  UNIQUE (fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_news_pub ON news_items(market, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_ticker ON news_items(ticker, published_at DESC) WHERE ticker IS NOT NULL;

-- 个股公告(深历史 25年,结构化公告类型,PIT完美)——单独表,主键含类型便于回测过滤
CREATE TABLE IF NOT EXISTS stock_announcements (
  ticker       TEXT NOT NULL,
  ann_date     DATE NOT NULL,
  title        TEXT NOT NULL,
  ann_type     TEXT NOT NULL DEFAULT '',      -- 公告类型(分配方案/回购/质押/业绩...)
  url          TEXT NOT NULL DEFAULT '',
  is_signal    BOOLEAN NOT NULL DEFAULT false, -- 是否命中白名单(R2)=对金融有影响
  market       TEXT NOT NULL DEFAULT 'cn',
  fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (market, ticker, ann_date, title)
);
CREATE INDEX IF NOT EXISTS idx_ann_ticker ON stock_announcements(market, ticker, ann_date DESC);
CREATE INDEX IF NOT EXISTS idx_ann_signal ON stock_announcements(market, ann_date DESC) WHERE is_signal;
