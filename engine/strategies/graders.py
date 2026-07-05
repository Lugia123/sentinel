"""graders.py — 趋势档位策略。新增档位器:仿此写类 + 注册。"""
import numpy as np
import pandas as pd
from .base import register, GRADERS

# 松·只减 档位→乘数(只减不加,R35 v4 最优跟法)
ACTION = {3: (1.0, "偏强·持有"), 2: (1.0, "偏强·持有"), 1: (1.0, "中性·持有"),
          0: (0.75, "转弱·减一档"), -1: (0.5, "走弱·减半"),
          -2: (0.25, "破位·减至1/4"), -3: (0.0, "跌势·清仓")}


@register(GRADERS, "seven_signal")
class SevenSignalGrader:
    """7 子信号(站上20/50/200线、200线上行、21日动量、均线排列、近52周高)求和→-3..+3。"""
    label = "7子信号趋势共识"

    def grade(self, ticker, ctx):
        r = ctx.row(ticker)
        g = _trend_grade(r)
        mult, label = ACTION[g]
        return dict(grade=g, grade_label=label.split("·")[0], action=label.split("·")[1],
                    action_weight=mult, signals=_grade_signals(r))


def _trend_grade(r):
    c, s200 = r["close"], r["sma200"]
    if pd.isna(c) or pd.isna(s200):
        return 1
    s = 0
    s += 1 if c > r["sma20"] else -1
    s += 1 if c > r["sma50"] else -1
    s += 1 if c > s200 else -1
    s += 1 if r["sma200_slope"] > 0 else -1
    s += 1 if r["mom21"] > 0 else -1
    s += 1 if r["sma20"] > r["sma50"] > s200 else (-1 if r["sma20"] < r["sma50"] < s200 else 0)
    pf = r["pct_from_high"]
    s += 1 if pf > -0.10 else (-1 if pf < -0.25 else 0)
    return int(np.clip(round(s * 3 / 7), -3, 3))


def _grade_signals(r):
    c = r["close"]
    def v(x):
        return "多" if x > 0 else ("空" if x < 0 else "中")
    sig = [
        dict(name="站上20日线", detail=f"现价 {c:.2f} vs 20日线 {r['sma20']:.2f}", verdict=v(c - r["sma20"])),
        dict(name="站上50日线", detail=f"现价 {c:.2f} vs 50日线 {r['sma50']:.2f}", verdict=v(c - r["sma50"])),
        dict(name="站上200日线", detail=f"现价 {c:.2f} vs 200日线 {r['sma200']:.2f}", verdict=v(c - r["sma200"])),
        dict(name="200日线上行", detail=f"斜率 {r['sma200_slope']:+.3f}", verdict=v(r["sma200_slope"])),
        dict(name="21日动量为正", detail=f"近21日 {r['mom21']:+.1%}", verdict=v(r["mom21"])),
    ]
    if r["sma20"] > r["sma50"] > r["sma200"]:
        al, ad = "多", "多头排列 20>50>200"
    elif r["sma20"] < r["sma50"] < r["sma200"]:
        al, ad = "空", "空头排列 20<50<200"
    else:
        al, ad = "中", "均线交织(无排列)"
    sig.append(dict(name="均线排列", detail=ad, verdict=al))
    pf = r["pct_from_high"]
    pv = "多" if pf > -0.10 else ("空" if pf < -0.25 else "中")
    sig.append(dict(name="接近52周高", detail=f"距高点 {pf:+.1%}", verdict=pv))
    return sig
