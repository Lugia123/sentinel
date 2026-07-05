"""gates.py — 风险闸(总仓位)策略。"""
import numpy as np
import pandas as pd
from .base import register, GATES

VOL_TARGET = 0.15


@register(GATES, "vol_target")
class VolTargetGate:
    """波动目标闸:按 SPY 已实现波动缩放总仓位(波动高→降仓)。"""
    label = "波动目标体制闸"

    def evaluate(self, ctx):
        spy_ret = pd.Series(ctx.spy_c[:ctx.sp + 1]).pct_change()
        spyvol = float(spy_ret.tail(21).std() * np.sqrt(252))
        exposure = float(min(1.0, VOL_TARGET / spyvol)) if spyvol > 0 else 1.0
        level = "green" if exposure >= 0.95 else ("amber" if exposure >= 0.7 else "red")
        note = {"green": "波动正常,可满仓", "amber": "波动偏高,建议降仓", "red": "波动极高,大幅降仓"}[level]
        # exposure_raw = 未舍入(供 sizing,与重构前一致);exposure = 舍入(供显示)
        return dict(level=level, spy_vol=round(spyvol, 3), exposure=round(exposure, 3), note=note, exposure_raw=exposure)
