# 每日快照数据契约(engine → server → client 唯一接口)

`run_daily.py` 产出 `data/snapshot_<asof>.json`。改字段必须三端同步。

```jsonc
{
  "asof": "2026-06-25",              // 数据截至收盘日(非运行日)
  "generated_at": "2026-07-04",     // 运行日历日
  "capital": 4000.0,
  "disclaimer": "研究工具,非投资建议",
  "risk_light": {
    "level": "green|amber|red",     // 波动目标体制闸
    "spy_vol": 0.14,                // SPY 年化已实现波动
    "exposure": 1.0,                // 建议总仓位(min(1,0.15/vol))
    "note": "波动正常,可满仓"
  },
  "holdings": [{
    "ticker": "AAPL",
    "sleeve": "momentum|SY|both",   // 来自哪条腿
    "price": 210.5,
    "base_weight": 0.06,            // 风险平价基础权重
    "target_shares": 1.14,         // 按资金池定仓(可碎股)
    "target_value": 240.0,
    "grade": 2,                     // 7档趋势状态 -3..+3
    "grade_label": "偏强",
    "action": "持有|减一档|减半|减至1/4|清仓",  // 松·只减跟法
    "action_weight": 1.0,          // 档位乘数(只减不加)
    "prob": {                       // 到价概率(波动缩放经验分布,R33)
      "h20": {
        "median": 0.01, "band70": [-0.04, 0.05],
        "stop": 200.0, "target": 225.0,
        "p_hit_target": 0.31, "p_hit_stop": 0.18
      }
    },
    "reason": "动量腿 · 相对SPY强度 +12.3%(池内第3强)",  // 为什么入选(透明)
    "signals": [                    // 档位7子信号明细(透明化怎么算出档位)
      {"name": "站上20日线", "detail": "现价 210.5 vs 20日线 205.3", "verdict": "多"}
    ],
    "indicators": {                 // 关键指标原值(不藏)
      "mom126": 0.15, "mom21": 0.042, "vol_annual": 0.24,
      "sma20": 205.3, "sma50": 198.1, "sma200": 180.5,
      "pct_from_high": -0.08, "sy_yield": null
    }
  }],
  // AI 讲解不在快照里,走 GET /api/explain?ticker=X(DeepSeek,缓存于 explanations 表)
  "portfolio": {
    "n_holdings": 20, "gross_exposure": 0.95, "cash_pct": 0.05,
    "next_rebalance": "2026-12-xx"
  }
}
```
