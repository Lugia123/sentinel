-- 0023_risk_light_history — 风险灯历史(市场级Gate),供「风险灯历史」页。
-- 回补的历史存这里;每日 live 值仍从 snapshots.raw 取,端点 UNION 两者。
CREATE TABLE IF NOT EXISTS risk_light_history (
  market       TEXT NOT NULL,
  asof         DATE NOT NULL,
  level        TEXT NOT NULL,
  exposure     REAL NOT NULL,
  breadth      REAL,
  breadth_ma   REAL,
  crowd        REAL,
  amount_ratio REAL,
  spy_vol      REAL,
  diverge      BOOLEAN,
  PRIMARY KEY (market, asof)
);
