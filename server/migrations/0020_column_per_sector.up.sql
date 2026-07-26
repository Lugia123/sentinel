-- 0020_column_per_sector — 专栏改为每板块一份完整 digest(tab 式)
DROP TABLE IF EXISTS user_column_digest;
CREATE TABLE user_column_digest (
  user_id      BIGINT NOT NULL,
  market       TEXT NOT NULL DEFAULT 'cn',
  sector       TEXT NOT NULL,
  digest_date  DATE NOT NULL,
  digest       JSONB NOT NULL,          -- {overview, world[], domestic[], stock_impact[], global_transmission[]}
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, market, sector, digest_date)
);
