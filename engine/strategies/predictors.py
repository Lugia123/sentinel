"""predictors.py — 到价概率预测策略。"""
import numpy as np
from .base import register, PREDICTORS

HORIZONS = [5, 20, 60]


@register(PREDICTORS, "vol_scaled")
class VolScaledPredictor:
    """波动缩放经验分布:未来 5/20/60 日收益分布(校准),输出概率带 + 到价概率。"""
    label = "波动缩放经验分布"

    def predict(self, ticker, ctx):
        r = ctx.row(ticker)
        px = float(r["close"])
        v63 = ctx.vol63(ticker)
        prob = {}
        for h in HORIZONS:
            zq, zsort = ctx.z_quantiles(h)
            sig_h = (v63 * np.sqrt(h)) if v63 and v63 > 0 else 0.0
            prob[f"h{h}"] = _prob_bands(px, sig_h, zq, zsort)
        return prob


def _prob_bands(price, sig_h, zq, zsort):
    q = {k: price * (1 + sig_h * v) for k, v in zq.items()}
    stop = q[0.10]; target = q[0.90]
    def p_ge(px):
        z = (px / price - 1) / sig_h if sig_h > 0 else 0
        return float(1 - np.searchsorted(zsort, z) / len(zsort))
    return dict(median=round(q[0.50] / price - 1, 4),
                band70=[round(q[0.15] / price - 1, 4), round(q[0.85] / price - 1, 4)],
                stop=round(stop, 2), target=round(target, 2),
                p_hit_target=round(p_ge(target), 3), p_hit_stop=round(1 - p_ge(stop), 3))
