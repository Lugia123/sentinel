-- 0018_news_interpret — 新闻 AI 解读缓存 + 板块标注
ALTER TABLE news_items ADD COLUMN IF NOT EXISTS ai_interpret TEXT;      -- AI 解读 HTML(懒生成缓存)
ALTER TABLE news_items ADD COLUMN IF NOT EXISTS ai_sectors  TEXT[] NOT NULL DEFAULT '{}'; -- 涉及A股板块
