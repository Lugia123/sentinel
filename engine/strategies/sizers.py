"""sizers.py — 定仓策略。"""
from .base import register, SIZERS


@register(SIZERS, "risk_parity")
class RiskParitySizer:
    """风险平价:各腿等分总仓,腿内逆波动加权(波动低给多)。"""
    label = "风险平价(逆波动)"

    def size(self, picks, ctx):
        by_sleeve = {}
        for p in picks:
            by_sleeve.setdefault(p.sleeve, []).append(p.ticker)
        sleeves = [s for s, ts in by_sleeve.items() if ts]
        if not sleeves:
            return {}
        frac = 1.0 / len(sleeves)
        base = {}
        for s in sleeves:
            iv = {tk: 1.0 / v for tk in by_sleeve[s] if (v := ctx.vol63(tk)) and v > 0}
            tot = sum(iv.values())
            if tot <= 0:
                continue
            for tk in by_sleeve[s]:
                base[tk] = base.get(tk, 0) + frac * iv.get(tk, 0) / tot
        return base
