DROP TABLE IF EXISTS focus_cache;
ALTER TABLE positions    DROP COLUMN IF EXISTS user_id;
ALTER TABLE watchlist    DROP COLUMN IF EXISTS user_id;
ALTER TABLE explanations DROP COLUMN IF EXISTS user_id;
