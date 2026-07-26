DROP TABLE IF EXISTS user_column_digest;
CREATE TABLE user_column_digest (
  user_id BIGINT NOT NULL, market TEXT NOT NULL DEFAULT 'cn', digest_date DATE NOT NULL,
  digest JSONB NOT NULL, generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, market, digest_date)
);
