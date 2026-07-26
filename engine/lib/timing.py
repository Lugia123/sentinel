#!/usr/bin/env python3
"""择时/regime 引擎:市场级信号(从已有面板算)+ 择时叠加器(T+1+切换成本)。
用于给小盘多头腿降回撤(不做空,只减仓/空仓避险)。判定:择时后 Calmar↑ 且 maxDD↓ 且 OOS 不靠牺牲全部收益。"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E


# ---- 市场级信号(daily,只用当日及之前信息)----
def breadth(M, n=60):
    """市场宽度:可交易股中 收盘>n日均线 的比例(0..1)。低=弱势。"""
    C = M["close"].ffill()
    ma = C.rolling(n).mean()
    above = (C > ma) & M["in_market"]
    valid = M["in_market"]
    return (above.sum(axis=1) / valid.sum(axis=1).replace(0, np.nan))


def limit_sentiment(M, n=10):
    """涨停情绪:(涨停家数−跌停家数)/可交易数 的 n 日均。>0 情绪热。"""
    pct = M["pct"]
    up = (pct >= 9.5) & M["in_market"]     # 近似涨停(主板10%,留缓冲)
    dn = (pct <= -9.5) & M["in_market"]
    net = (up.sum(axis=1) - dn.sum(axis=1)) / M["in_market"].sum(axis=1).replace(0, np.nan)
    return net.rolling(n).mean()


def eq_trend(eq, n=100):
    """腿/指数自身趋势:净值 > n日均线 = 上行(risk-on)。返回 bool Series。"""
    e = eq.dropna()
    return (e > e.rolling(n).mean())


def vol_regime(eq, n=20, win=750, q=0.8):
    """波动率 regime:近n日已实现波动率的滚动分位 > q = 高波(risk-off)。返回 bool(高波=True)。"""
    r = eq.dropna().pct_change()
    rv = r.rolling(n).std()
    rank = rv.rolling(win, min_periods=120).apply(lambda x: (x[-1] > x).mean(), raw=True)
    return (rank > q)


def crowding(M, small_q=0.30, win=500):
    """★微盘拥挤度(自研):小盘成交额占比 + 小盘/全市场换手倍数,滚动分位。
    高=资源向微盘极端集中=易崩(2024初微盘危机)。返回 dict(share,turn_mult,index=0..1分位)。"""
    amt = M["amount"]; turn = M["turn"]; inm = M["in_market"]
    rnk = M["fmc"].rank(axis=1, pct=True)
    small = (rnk <= small_q) & inm
    tr = inm
    share = amt.where(small).sum(axis=1) / amt.where(tr).sum(axis=1).replace(0, np.nan)
    tmult = turn.where(small).mean(axis=1) / turn.where(tr).mean(axis=1).replace(0, np.nan)
    # 各自滚动分位(PIT,只用过去)再平均成拥挤指数
    def rpct(s): return s.rolling(win, min_periods=120).apply(lambda x: (x[-1] > x).mean(), raw=True)
    idx = (rpct(share) + rpct(tmult)) / 2.0
    return dict(share=share, turn_mult=tmult, index=idx)


def dispersion(M, n=5):
    """横截面收益离散度:每日全市场个股收益的横截面std,再n日均。高=分化/风险。"""
    r = M["close"].pct_change(fill_method=None).where(M["in_market"])
    return r.std(axis=1).rolling(n).mean()


def small_breadth(M, small_q=0.20, ma=60, smooth=40):
    """小盘专属宽度:小市值层内 收盘>ma日线 的比例(小盘腿用自身regime)。"""
    C = M["close"].ffill(); rnk = M["fmc"].rank(axis=1, pct=True)
    small = (rnk <= small_q) & M["in_market"]
    above = (C > C.rolling(ma).mean()) & small
    return (above.sum(axis=1) / small.sum(axis=1).replace(0, np.nan))


def amihud_illiq(M, small_q=0.20, win=500):
    """微盘流动性枯竭(A队#3):小盘层 Amihud=mean(|pctChg%|/成交额) 的滚动分位。
    高分位=枯竭=risk-off。补 crowding 盲区(崩中换手枯竭→crowding失灵回落,Amihud上升符号正确)。"""
    rnk = M["fmc"].rank(axis=1, pct=True); small = (rnk <= small_q) & M["in_market"]
    illiq = (M["pct"].abs() / (M["amount"] / 1e8).replace(0, np.nan)).where(small)
    series = illiq.mean(axis=1)
    return series.rolling(win, min_periods=120).apply(lambda x: (x[-1] > x).mean(), raw=True)


def layer_breadth(M, lo, hi, ma=60, smooth=40):
    """任意市值层 [lo,hi] 分位内的宽度(站上ma线比例)。小盘lo=0,hi=0.2;大盘lo=0.8,hi=1。"""
    C = M["close"].ffill(); rnk = M["fmc"].rank(axis=1, pct=True)
    layer = (rnk > lo) & (rnk <= hi) & M["in_market"]
    above = (C > C.rolling(ma).mean()) & layer
    br = above.sum(axis=1) / layer.sum(axis=1).replace(0, np.nan)
    return br


def drawdown_state(eq, win=250):
    """指数/EW 当前回撤(距win日高点)。深回撤=risk-off。返回<=0的Series。"""
    e = eq.dropna(); peak = e.rolling(win, min_periods=20).max()
    return e / peak - 1.0


def amount_regime(M, short=5, long=60):
    """全市场成交额 短/长均比(枯竭<1=危险,放大>1)。"""
    tot = M["amount"].where(M["in_market"]).sum(axis=1)
    return tot.rolling(short).mean() / tot.rolling(long).mean().replace(0, np.nan)


def new_high_low(M, win=244, n=10):
    """52周新高家数−新低家数,占比,n日均。ADL式宽度。"""
    C = M["close"].ffill()
    hi = (C >= C.rolling(win).max() * 0.999) & M["in_market"]
    lo = (C <= C.rolling(win).min() * 1.001) & M["in_market"]
    net = (hi.sum(axis=1) - lo.sum(axis=1)) / M["in_market"].sum(axis=1).replace(0, np.nan)
    return net.rolling(n).mean()


def breadth_accel(M, ma=60, chg=20):
    """宽度动量/加速:宽度的chg日变化。宽度掉头向下=早预警。"""
    br = breadth(M, ma)
    return br - br.shift(chg)


def downside_semivol(eq, n=20, win=750, q=0.8):
    """下行半波动 regime(novel vol变体):只用负收益的波动率滚动分位>q=下行风险高(risk-off)。
    区别于总波动(R22证否)——只对'跌得剧烈'避险,不因'涨得剧烈'空仓。返回 bool(高下行波=True)。"""
    r = eq.dropna().pct_change()
    dn = r.clip(upper=0.0)                       # 只留负收益
    sv = dn.rolling(n).std()
    rank = sv.rolling(win, min_periods=120).apply(lambda x: (x[-1] > x).mean(), raw=True)
    return (rank > q)


def month_of(idx):
    """返回 index 各日的月份 Series(季节择时用)。"""
    return pd.Series(idx.month, index=idx)


def beixiang_trend(M, path, n=20):
    """北向累计净买 > n日均线 = 资金流入(risk-on)。对齐到 M 日历。返回 bool Series。"""
    df = pd.read_parquet(path)
    df = df[df["类型"] == "北向资金"].copy()
    df["d"] = pd.to_datetime(df["日期"], errors="coerce")
    df = df.dropna(subset=["d"]).set_index("d").sort_index()
    cum = pd.to_numeric(df["历史累计净买额"], errors="coerce")
    sig = (cum > cum.rolling(n).mean())
    return sig.reindex(M["close"].index).ffill()


# ---- 择时叠加器 ----
def apply_timing(leg_eq, expo, cost=0.001):
    """把日频目标暴露 expo(0..1,t 日已知)T+1 施于腿。切换暴露时扣 cost。返回择时后净值。"""
    r = leg_eq.dropna().pct_change().fillna(0.0)
    e = expo.reindex(r.index).ffill().shift(1).fillna(1.0).clip(0, 1)
    switch = e.diff().abs().fillna(0.0)
    tr = r * e - switch * cost
    return (1 + tr).cumprod()


def confirm_entry(raw_on, n=3):
    """非对称快出慢进(B队①):出场即时(raw_on转False立即0),进场需连续n日True才1。
    raw_on=bool Series。返回确认后的暴露(0/1)。"""
    v = raw_on.fillna(False).astype(bool).values
    out = np.zeros(len(v)); state = 0; run = 0
    for i in range(len(v)):
        if v[i]:
            run += 1
        else:
            run = 0; state = 0        # 出场即时
        if state == 0 and run >= n:
            state = 1                  # 连续n日确认才进
        out[i] = state
    return pd.Series(out, index=raw_on.index)


def hysteresis(sig, ref, k=0.03):
    """滞回带(B队②):sig>ref*(1+k)进场、sig<ref*(1-k)出场、带内维持前态。减whipsaw。"""
    up = (sig > ref * (1 + k)).values; dn = (sig < ref * (1 - k)).values
    out = np.zeros(len(up)); state = 0
    for i in range(len(up)):
        if up[i]: state = 1
        elif dn[i]: state = 0
        out[i] = state
    return pd.Series(out, index=sig.index)


def cooldown(expo, m=15):
    """出场后冷却m日(B队③):任一次1→0后强制0持续m日。"""
    v = expo.fillna(0).values; out = v.copy(); cd = 0
    for i in range(1, len(v)):
        if v[i-1] > 0 and v[i] == 0: cd = m
        if cd > 0: out[i] = 0.0; cd -= 1
    return pd.Series(out, index=expo.index)


def walk_forward(leg, expo_dict, y0=2017, y1=2026, warmup="2011-01-01", cost=0.001):
    """walk-forward:每年只用<当年数据挑Calmar最优的候选暴露,应用于当年,拼成诚实WF净值。
    leg=腿净值;expo_dict={label: 日频暴露Series(0..1)}。返回(WF净值, 逐年选用label)。"""
    import engine as E
    idx = leg.dropna().index
    timed = {k: apply_timing(leg, v, cost=cost) for k, v in expo_dict.items()}
    wf_expo = pd.Series(np.nan, index=idx); choices = {}
    for y in range(y0, y1 + 1):
        best, bcal = None, -1e9
        for k, e in timed.items():
            past = e.dropna(); past = past[(past.index >= pd.Timestamp(warmup)) & (past.index <= pd.Timestamp(f"{y-1}-12-31"))]
            if len(past) > 150:
                past = past / past.iloc[0]; c = E.metrics(past)["Calmar"]
                if c > bcal: bcal, best = c, k
        if best is None: best = list(expo_dict.keys())[0]
        choices[y] = best
        yr = (idx >= pd.Timestamp(f"{y}-01-01")) & (idx <= pd.Timestamp(f"{y}-12-31"))
        wf_expo.loc[idx[yr]] = expo_dict[best].reindex(idx).ffill().reindex(idx[yr]).values
    wf = apply_timing(leg, wf_expo.ffill().fillna(1.0), cost=cost)
    return wf, choices


def to_expo(sig_bool, off=0.0):
    """bool risk-on 信号 → 暴露(True=1 满仓,False=off 减仓/空仓)。"""
    return sig_bool.astype(float).replace(0.0, off) if off else sig_bool.astype(float)
