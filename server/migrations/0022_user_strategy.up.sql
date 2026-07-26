-- 0022_user_strategy — 每个用户×市场的策略偏好(A股「头号腿/红利低波」二选一)
-- 空/无记录 → 代码层默认 'headline'(头号腿·微盘)。'dividend' = 红利低波(大资金替代腿)。
CREATE TABLE IF NOT EXISTS user_strategy (
  user_id    BIGINT NOT NULL,
  market     TEXT   NOT NULL,
  strategy   TEXT   NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, market)
);
