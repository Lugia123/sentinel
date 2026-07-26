-- 0011_dropped — 掉出推荐列表(v2.1)
-- 策略每天重选,掉出的股票原来悄无声息消失;现在进入「掉出推荐」列表并可 AI 分析原因。
-- 状态机(带双向 CD 防抖):
--   推荐中缺席 → INSERT status=pending(观察期);连续缺席满 CD_DROP 个快照日 → status=dropped
--   pending 期间重新出现 → 直接删行(闪烁,当无事发生)
--   dropped 后重新出现:back_streak 连续满 CD_BACK 个快照日 → 删行(回归推荐);中断则清零
--   dropped 超过保留天数 → 自动清理
CREATE TABLE IF NOT EXISTS dropped_stocks (
  market      TEXT NOT NULL,
  ticker      TEXT NOT NULL,
  name        TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'pending',  -- pending=缺席观察期 / dropped=已判定掉出
  last_seen   DATE NOT NULL,                    -- 最后一次出现在推荐中的快照日
  dropped_at  DATE,                             -- 判定掉出的快照日
  last_price  NUMERIC,                          -- last_seen 当天价格
  last_grade  INT,
  context     JSONB,                            -- 掉出前最后一天的完整 holding(AI 分析原料)
  miss_streak INT NOT NULL DEFAULT 1,           -- 连续缺席快照数
  back_streak INT NOT NULL DEFAULT 0,           -- 掉出后连续回归快照数
  asof_seen   DATE NOT NULL,                    -- 状态机最后处理的快照日(同日重跑幂等)
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (market, ticker)
);
CREATE INDEX IF NOT EXISTS idx_dropped_market_status ON dropped_stocks(market, status, dropped_at DESC);
