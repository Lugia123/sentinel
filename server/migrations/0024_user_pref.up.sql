-- 0024_user_pref — 每用户通用偏好 KV（用户隔离）。首个用途:color_up 涨跌配色。
-- 空/无记录 → 代码层默认 color_up='red'（A股习惯:红涨绿跌)。'green'=绿涨红跌(西式)。
CREATE TABLE IF NOT EXISTS user_pref (
  user_id    BIGINT NOT NULL,
  key        TEXT   NOT NULL,
  value      TEXT   NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, key)
);
