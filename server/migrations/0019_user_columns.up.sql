-- 0019_user_columns — 用户自定义行业/板块专栏(用户隔离)
CREATE TABLE IF NOT EXISTS user_columns (
  user_id     BIGINT NOT NULL,
  market      TEXT NOT NULL DEFAULT 'cn',
  sectors     TEXT[] NOT NULL DEFAULT '{}',  -- 关注的行业/板块/关键词
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, market)
);
-- 专栏生成缓存(每用户每市场每日一份)
CREATE TABLE IF NOT EXISTS user_column_digest (
  user_id      BIGINT NOT NULL,
  market       TEXT NOT NULL DEFAULT 'cn',
  digest_date  DATE NOT NULL,
  digest       JSONB NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, market, digest_date)
);
