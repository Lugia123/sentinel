#!/usr/bin/env python3
"""跨轮共享的对照腿:头号腿(小市值×低换手·剔ST)+ 同池EW。
另类数据轮次统一 import 这里,保证与 R1-R9 口径完全一致,corr/超额可跨轮比较。"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E, benchmark as BM


def tradable(M):
    """可交易过滤(与 R7-R9 一致):20日均换手>0.1% + 正常状态 + 近20日≥18日有效收益。
    滤掉停牌冻结/僵尸股(见 R5 教训:冻结股会伪装低波/低换手)。"""
    ret = M["close"].pct_change(fill_method=None)
    return (M["turn"].rolling(20).mean() > 0.1) & (M["status"] == 1) & (ret.notna().rolling(20).sum() >= 18)


def masks(M, small_q=0.20):
    """返回常用掩码:tradable / 非ST / 小市值层(流通市值分位<=small_q)。"""
    tr = tradable(M)
    st = (M["st"].fillna(0) == 0)
    rnk = M["fmc"].rank(axis=1, pct=True)
    small = rnk <= small_q
    return dict(tr=tr, st=st, rnk=rnk, small=small)


def run_sig(M, sig, mask=None, n_hold=50):
    s = sig.where(M["in_market"])
    if mask is not None:
        s = s.where(mask)
    return E.backtest(s, M, n_hold=n_hold, rebalance="M", weight="equal")["equity"]


def headline_leg(M, n_hold=50):
    """头号腿 = 小市值层内按低换手(-20日均换手)选前 N,剔ST。OOS 12.3%/0.59/-50%。"""
    m = masks(M)
    turn20 = M["turn"].rolling(20).mean()
    return run_sig(M, -turn20, mask=(m["tr"] & m["st"] & m["small"]), n_hold=n_hold)


def ew(M):
    return BM.ew_survivorship_free(M)["equity"]


def size_neutral(sig, fmc, nq=5):
    """market-cap 中性化:每个交易日按 fmc 分 nq 层,层内对信号做 z-score。
    去掉信号的 size 倾斜(层内比较)。返回同形状 date×code。"""
    q = fmc.rank(axis=1, pct=True)
    bucket = (q * nq).clip(upper=nq - 1e-9).apply(np.floor)  # 0..nq-1
    out = pd.DataFrame(np.nan, index=sig.index, columns=sig.columns)
    for b in range(nq):
        mask = (bucket == b)
        s = sig.where(mask)
        mu = s.mean(axis=1); sd = s.std(axis=1).replace(0, np.nan)
        z = s.sub(mu, axis=0).div(sd, axis=0)
        out = out.where(~mask, z)
    return out


# ---- 四门评测复用(EXPLORE_ALT.md:G1超EW / G2 corr<0.6 / G3大盘存活 / G4组合Calmar) ----
def _line(l, eq):
    import altdata as A
    m = E.metrics(eq.dropna())
    print(f"{l:<30}{m['CAGR']*100:>7.1f}%  Sh{m['Sharpe']:>6}  DD{m['maxDD']*100:>7.1f}%  Cal{m['Calmar']:>6}")
    return m


def run_gates(M, sig, start, precomp=None, pos_only=True, n_hold=50, tag="因子"):
    """对一个 date×code 信号跑完整四门。sig 越大越优。start=同期对照起点。
    precomp: 可传 dict(ew=,head=,masks=) 复用已算好的基准(省时)。返回各腿 metrics。"""
    import altdata as A
    m = precomp["masks"] if precomp else masks(M)
    ew_eq = precomp["ew"] if precomp else ew(M)
    head = precomp["head"] if precomp else headline_leg(M)
    C = M["close"]
    sel = (sig > 0) if pos_only else sig.notna()
    def era(l, eq): return _line(l, A.in_era(eq, start))
    print(f"\n== 基准(同期 {start}+)==")
    era("同期EW", ew_eq); h = era("同期头号腿", head)
    print(f"\n== G1 {tag}前{n_hold}(全池)==")
    leg = run_sig(M, sig, mask=(m["tr"] & sel), n_hold=n_hold); era(f"{tag}·全池", leg)
    print("\n== G3 大盘子池(rnk>0.5)==")
    big = m["rnk"] > 0.5
    ones = pd.DataFrame(1.0, index=C.index, columns=C.columns)
    ewb = run_sig(M, ones, mask=(m["tr"] & big)); era("大盘子池EW", ewb)
    legb = run_sig(M, sig, mask=(m["tr"] & big & sel), n_hold=n_hold); era(f"{tag}·大盘子池", legb)
    print("\n== 参照小盘层 ==")
    legs_sm = run_sig(M, sig, mask=(m["tr"] & m["small"] & sel), n_hold=n_hold); era(f"{tag}·小盘层", legs_sm)
    print("\n== G2 正交 + G4 组合 ==")
    c_all = A.corr(leg, head, start); c_big = A.corr(legb, head, start)
    print(f"  {tag}全池 vs 头号腿 corr {c_all} | 大盘版 corr {c_big}")
    r1 = A.in_era(leg, start).pct_change(fill_method=None)
    r2 = A.in_era(head, start).pct_change(fill_method=None)
    j = pd.concat([r1, r2], axis=1, join="inner").dropna()
    comb = (1 + j.mean(axis=1)).cumprod(); cm = _line("  头号+因子 组合", comb)
    print(f"\n  判定门:G1 {'✓' if E.metrics(A.in_era(leg,start))['CAGR']>E.metrics(A.in_era(ew_eq,start))['CAGR'] else '✗'}"
          f" | G2 {'✓正交' if (c_all is not None and abs(c_all)<0.6) else '✗共线'}(corr {c_all})"
          f" | G4 {'✓改善' if cm['Calmar']>h['Calmar'] else '✗拖累'}(组合Cal {cm['Calmar']} vs 头号 {h['Calmar']})")
    return dict(leg=leg, legb=legb, head=head, ew=ew_eq, corr=c_all, corr_big=c_big, comb=comb)
