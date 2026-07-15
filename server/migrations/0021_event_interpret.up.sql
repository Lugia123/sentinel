-- 宏观「世界大事/国内大事」条目的按需 AI 解读缓存(digest 事件无 news_item id,按标题哈希缓存)
CREATE TABLE IF NOT EXISTS event_interpret (
  market     TEXT NOT NULL DEFAULT 'cn',
  event_key  TEXT NOT NULL,            -- md5(事件标题)
  interpret  TEXT NOT NULL DEFAULT '',
  sectors    TEXT NOT NULL DEFAULT '', -- 逗号分隔
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (market, event_key)
);
