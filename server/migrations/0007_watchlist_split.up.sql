-- 0007_watchlist_split — 分离「关注(★)」与「自定义追踪股」(原来挤在一张表导致取消关注就删掉自定义股)
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS starred BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS custom  BOOLEAN NOT NULL DEFAULT false;
-- 迁移旧语义:source='user'=用户自定义股(不默认关注);source='ai'=用户手动关注的
UPDATE watchlist SET custom = true  WHERE source = 'user';
UPDATE watchlist SET starred = true WHERE source = 'ai';
