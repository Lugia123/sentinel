-- 0010_capital_market — 资金池按【用户×市场】隔离(美股$与A股¥不该共用一个数字)
-- 存量 users.capital 迁移为该用户的 us 资金池;A股无记录时代码层默认 ¥100000。
CREATE TABLE IF NOT EXISTS user_capital (
  user_id    BIGINT NOT NULL,
  market     TEXT   NOT NULL,
  capital    NUMERIC(14,2) NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, market)
);
INSERT INTO user_capital(user_id, market, capital)
SELECT id, 'us', capital FROM users
ON CONFLICT (user_id, market) DO NOTHING;
