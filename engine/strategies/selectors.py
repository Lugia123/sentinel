"""selectors.py — 选股策略。新增一条腿:仿此写个类 + @register(SELECTORS,'名字')。"""
import os
import pandas as pd
from .base import register, SELECTORS, Pick

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, os.path.join(_HERE, "lib"))
from champion import DATA_DIR_98  # noqa
NARROW = set(f[:-4] for f in os.listdir(DATA_DIR_98) if f.endswith(".csv"))
N = 10  # 每腿票数


@register(SELECTORS, "momentum")
class MomentumSelector:
    """动量哨兵:98大盘窄池,趋势门(>SMA200/上行/>SMA50/近高) + 相对SPY强度 top10。"""
    label = "动量"
    universe = "98 大盘窄池"

    def select(self, ctx):
        elig = []
        for tk in NARROW:
            if tk not in ctx.uni:
                continue
            r = ctx.row(tk)
            if r is None or pd.isna(r["close"]) or pd.isna(r["sma200"]) or pd.isna(r["mom126"]):
                continue
            if r["close"] > r["sma200"] and r["sma200_slope"] > 0 and r["close"] > r["sma50"] \
               and r["pct_from_high"] > -0.25:
                elig.append((tk, r["mom126"] - ctx.spy_mom))
        elig.sort(key=lambda kv: -kv[1])
        picks = []
        for i, (tk, rs) in enumerate(elig[:N]):
            picks.append(Pick(tk, rs, f"动量腿 · 相对SPY强度 {rs:+.1%}(池内第{i+1}强)", "momentum", rank=i + 1))
        return picks


@register(SELECTORS, "shareholder_yield")
class ShareholderYieldSelector:
    """股东收益率:1393宽池(含中小盘),净回购率+股息率 top10。SEC EDGAR PIT。"""
    label = "股东回报"
    universe = "1393 S&P1500(含中小盘)"

    _scored = {}  # 缓存全池评分(供 contribute_indicators)

    def contribute_indicators(self, ctx):
        """向持仓 indicators 贡献全池 sy_yield(不只被选中的股)。"""
        return {tk: {"sy_yield": round(float(v), 4)} for tk, v in self._scored.items()}

    def select(self, ctx):
        self._scored = {}
        if not ctx.with_sy or ctx.fp is None:
            return []
        fp = ctx.fp
        avail = [tk for tk in ctx.uni if (r := ctx.row(tk)) and not pd.isna(r["close"]) and r["close"] >= 5]
        scored = {}
        for tk in avail:
            if tk not in fp.available_tickers():
                continue
            sh = fp.get_latest(tk, "CommonStockSharesOutstanding", ctx.asof, lag_days=45)
            px = ctx.row(tk)["close"]
            if not sh or sh <= 0:
                continue
            mcap = sh * px
            bb = fp.get_quarterly_series(tk, "PaymentsForRepurchaseOfCommonStock", ctx.asof, n_quarters=4, lag_days=45)
            iss = fp.get_quarterly_series(tk, "ProceedsFromIssuanceOfCommonStock", ctx.asof, n_quarters=4, lag_days=45)
            tb = sum(abs(v) for _, v in bb if v is not None)
            ti = sum(v for _, v in iss if v is not None)
            dv = fp.get_dividend_ttm(tk, ctx.asof, lag_days=45) or 0.0
            scored[tk] = (tb - ti) / mcap + dv / mcap
        self._scored = scored
        sy_sorted = sorted(scored.items(), key=lambda kv: -kv[1])
        picks = []
        for i, (tk, sc) in enumerate(sy_sorted[:N]):
            picks.append(Pick(tk, sc, f"股东回报腿 · 股东收益率 {sc:.1%}(池内第{i+1})", "SY", rank=i + 1))
        return picks
