"""
strategies/base.py — 可插拔策略框架:Context(共享数据访问)+ 5 类注册表。
新增策略 = 实现对应方法 + @register(...) + 在 __init__.STRATEGY_CONFIG 启用。不改流水线。
"""
import numpy as np
import pandas as pd

# 5 类组件注册表:name -> 实例
SELECTORS = {}   # Selector.select(ctx) -> [Pick]
SIZERS = {}      # Sizer.size(picks, ctx) -> {ticker: weight}
GRADERS = {}     # Grader.grade(ticker, ctx) -> Grade
PREDICTORS = {}  # Predictor.predict(ticker, ctx) -> prob dict
GATES = {}       # RiskGate.evaluate(ctx) -> {level,exposure,note}


def register(reg, name):
    """类装饰器:实例化并注册。用法 @register(SELECTORS, 'momentum')。"""
    def deco(cls):
        inst = cls()
        inst.name = name
        reg[name] = inst
        return cls
    return deco


class Pick:
    """选股结果:哪只、分数、理由、来自哪条腿。"""
    __slots__ = ("ticker", "score", "reason", "sleeve", "rank", "extra")

    def __init__(self, ticker, score, reason, sleeve, rank=None, extra=None):
        self.ticker, self.score, self.reason, self.sleeve = ticker, score, reason, sleeve
        self.rank, self.extra = rank, extra or {}


class Context:
    """共享数据访问 + PIT helper(按日期定位,无前视)。所有组件通过它拿数据。"""

    def __init__(self, uni, spy, master, fp, asof, capital=4000.0, with_sy=True):
        self.uni, self.spy, self.master, self.fp = uni, spy, master, fp
        self.asof, self.capital, self.with_sy = asof, capital, with_sy
        self.asof64 = np.datetime64(asof)
        self.POS = {tk: self._pos(df) for tk, df in uni.items()}
        self.spy_c = spy["close"].values
        spy_dt = pd.to_datetime(spy["date"]).values
        self.sp = int(np.searchsorted(spy_dt, self.asof64, side="right")) - 1
        self.spy_mom = (self.spy_c[self.sp] / self.spy_c[self.sp - 126] - 1) if self.sp >= 126 else 0.0
        self._zcache = {}

    def _pos(self, df):
        d = pd.to_datetime(df["date"]).values
        p = int(np.searchsorted(d, self.asof64, side="right")) - 1
        return p if p >= 0 else None

    def row(self, tk):
        i = self.POS.get(tk)
        if i is None:
            return None
        df = self.uni[tk]
        return {c: df[c].iloc[i] for c in
                ("close", "sma20", "sma50", "sma200", "sma200_slope", "mom21", "mom126", "pct_from_high")}

    def vol63(self, tk):
        i = self.POS.get(tk)
        if i is None or i < 63:
            return np.nan
        c = self.uni[tk]["close"].values[:i + 1]
        return float(pd.Series(c).pct_change().tail(63).std())

    def z_quantiles(self, h):
        """全池标准化前瞻收益经验分位(缓存,供 Predictor)。"""
        if h not in self._zcache:
            self._zcache[h] = build_z_quantiles(self.uni, self.POS, h)
        return self._zcache[h]


def build_z_quantiles(uni, POS, h):
    """全池历史标准化前瞻收益 z=fwd_h/(vol*sqrt(h)) 的经验分位(<=asof,无前视)。"""
    zs = []
    for tk, df in uni.items():
        p = POS.get(tk)
        if p is None:
            continue
        c = df["close"].values[:p + 1]
        if len(c) < 300:
            continue
        r1 = pd.Series(c).pct_change()
        vol = r1.rolling(63).std().values
        fwd = np.concatenate([c[h:] / c[:-h] - 1, [np.nan] * h])
        hv = vol * np.sqrt(h)
        with np.errstate(divide="ignore", invalid="ignore"):
            z = fwd[:len(c)] / hv
        z = z[np.isfinite(z)]
        zs.append(z[np.abs(z) < 10])
    allz = np.concatenate(zs) if zs else np.array([0.0])
    qs = [0.05, 0.10, 0.15, 0.25, 0.50, 0.75, 0.85, 0.90, 0.95]
    return {q: float(np.quantile(allz, q)) for q in qs}, np.sort(allz)
