#!/usr/bin/env python3
"""P2 回测:事件腿/红利腿在 akshare-alt(生产)vs tushare-alt(迁移)上的 honest 回测对比。
低选股重叠不代表更差(同类票互换);决定性看 Calmar/收益相关。复用 cn_engine 的信号构造。
用法:SENTINEL_TS_STAGE=<暂存alt> python engine/ds_compare_alt.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import cn_engine as ce
E, L, A_ = ce.E, ce.L, ce.A_

PROD = ce.ALT_DIR
STAGE = os.environ["SENTINEL_TS_STAGE"]


def dividend_sig(alt, M):
    C = M["close"]; idx = C.index
    ev = pd.read_parquet(os.path.join(alt, "div_events.parquet"))
    dps = ev.pivot_table(index="ann_date", columns="code", values="dps", aggfunc="sum").reindex(index=idx, columns=C.columns).fillna(0.0)
    ttm = dps.rolling(252, min_periods=1).sum()
    yld = (ttm / C).replace([np.inf, -np.inf], np.nan)
    vol60 = C.pct_change(fill_method=None).rolling(60).std()
    mk = L.masks(M); tr = mk["tr"] & mk["st"]
    comp = yld.rank(axis=1, pct=True) + (-vol60).rank(axis=1, pct=True)
    return L.size_neutral(comp.where(tr), M["fmc"])


def event_sig(alt, M):
    fmc = M["fmc"]; mk = L.masks(M)
    an = pd.read_parquet(os.path.join(alt, "analyst.parquet")); chg = an["评级变化"].astype(str)
    an["rv"] = np.where(chg.str.contains("调高|上调", na=False), 1.0, np.where(chg.str.contains("调低|下调", na=False), -1.0, 0.0))
    zr = L.size_neutral(A_.events_to_matrix(an, M, code_col="证券代码", date_col="发布日期", val_col="rv", lag=1, max_ffill=90, agg="sum"), fmc)
    yj = pd.read_parquet(os.path.join(alt, "yjyg.parquet")); yj = yj[yj["预测指标"].astype(str).str.contains("净利润", na=False)].copy()
    TS = {"预增": 2, "扭亏": 2, "略增": 1, "续盈": 1, "减亏": 0.5, "预减": -1, "略减": -1, "首亏": -2, "续亏": -2, "增亏": -2, "不确定": 0}
    yj["s"] = yj["预告类型"].map(TS).fillna(0.0)
    zp = L.size_neutral(A_.events_to_matrix(yj, M, code_col="股票代码", date_col="公告日期", val_col="s", lag=1, max_ffill=60, agg="last"), fmc)
    comp = pd.concat([zr.stack(), zp.stack()], axis=1).mean(axis=1).unstack().reindex(index=M["close"].index, columns=M["close"].columns)
    return comp.where(mk["tr"])


def bt(sig, M, n):
    eq = E.backtest(sig.where(M["in_market"]), M, n_hold=n, rebalance="M", weight="equal")["equity"]
    e = eq.dropna(); return e / e.iloc[0]


def show(name, eqa, eqb):
    ma, mb = E.metrics(eqa), E.metrics(eqb)
    corr = eqa.pct_change().corr(eqb.reindex(eqa.index).pct_change())
    print(f"\n{name}")
    print(f"  A akshare: CAGR{ma['CAGR']*100:5.1f}% Sharpe{ma['Sharpe']:.2f} maxDD{ma['maxDD']*100:6.1f}% Calmar{ma['Calmar']:.3f}")
    print(f"  B tushare: CAGR{mb['CAGR']*100:5.1f}% Sharpe{mb['Sharpe']:.2f} maxDD{mb['maxDD']*100:6.1f}% Calmar{mb['Calmar']:.3f}")
    print(f"  日收益相关: {corr:.4f}   ΔCalmar(B-A): {mb['Calmar']-ma['Calmar']:+.3f}")


def main():
    print("加载 baostock M …", flush=True)
    M = E.load_matrices(start="2016-01-01")
    print(f"末日 {M['close'].index[-1].date()}", flush=True)
    print("回测红利腿 …", flush=True)
    show("红利低波(top50 月频)", bt(dividend_sig(PROD, M), M, 50), bt(dividend_sig(STAGE, M), M, 50))
    print("回测事件腿 …", flush=True)
    show("事件腿 rev+PEAD(top20 月频)", bt(event_sig(PROD, M), M, 20), bt(event_sig(STAGE, M), M, 20))
    print("\n判据:ΔCalmar≥-0.05 且 收益相关>0.9 → tushare腿等价可迁;否则需查信号构造", flush=True)


if __name__ == "__main__":
    main()
