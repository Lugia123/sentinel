-- AI 讲解缓存(DeepSeek 生成的白话解读,按 ticker+asof 缓存,避免重复调用)
CREATE TABLE IF NOT EXISTS explanations (
  ticker     TEXT        NOT NULL,
  asof       DATE        NOT NULL,
  kind       TEXT        NOT NULL DEFAULT 'holding',
  content    TEXT        NOT NULL,
  model      TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (ticker, asof, kind)
);
