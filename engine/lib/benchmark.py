#!/usr/bin/env python3
"""R0 基准标杆(survivorship-free)。
- 指数买入持有:沪深300 / 中证800 / 中证500(baostock 指数收益)。
- 同池等权 EW:每月等权持有当时"在市"的全部股票(含后来退市的,survivorship-free),扣摩擦。
  ⚠️ EW-持有全池不用逐股撮合引擎(会 O(天×5000持仓) 极慢);用向量化月度再平衡+换手成本,秒级、标准做法。
  R1+ 有信号选股时才用 engine.backtest(需 T+1/涨跌停/停牌撮合精度)。
运行:python lib/benchmark.py → 打印表(供 策略排行榜.md 对照)。"""
import os, sys, time
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E

DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
META = os.path.join(DATA_DIR, "meta")
# 摩擦(单边):印花税(仅卖)+佣金(双边)+滑点(双边)
STAMP, COMM, SLIP = E.STAMP, E.COMM, E.SLIP


def index_bh(name):
    df = pd.read_csv(os.path.join(META, f"index_{name}.csv"))
    df["date"] = pd.to_datetime(df["date"])
    s = df.set_index("date")["close"].astype(float)
    return s / s.iloc[0]


def ew_survivorship_free(M):
    """向量化 月度再平衡 等权持有全池(survivorship-free)。
    每月末重置为当时在市股等权;月内按各股日收益漂移;退市股在最后交易日后自动退出。
    换手成本:每次再平衡按 权重变动的换手额 收 (SLIP+COMM) + 卖出部分 STAMP。"""
    C = M["close"]
    r = C.pct_change(fill_method=None)          # 日简单收益,停牌/未上市为 NaN
    inm = M["in_market"]
    dates = C.index
    rb = pd.Series(dates).groupby([dates.year, dates.month]).last().values
    rb = set(pd.DatetimeIndex(rb))

    w = pd.Series(0.0, index=C.columns)         # 当前权重(占组合净值比)
    nav = 1.0
    navs = []
    turnover_sum = 0.0
    prev_avail = None
    for i, day in enumerate(dates):
        rt = r.loc[day].fillna(0.0)             # 当日收益(缺失=停牌,按0漂移)
        # 组合当日收益 = 上期末权重 · 当日收益
        port_r = float((w * rt).sum())
        nav *= (1.0 + port_r)
        # 权重漂移
        if w.sum() > 0:
            w = w * (1.0 + rt)
            w = w / w.sum()
        navs.append((day, nav))
        # 月末再平衡到"次日在市股"等权(信号只用当日,次日执行→用当日在市近似,EW无前视问题)
        if day in rb:
            avail = C.columns[inm.loc[day].values]
            if len(avail) == 0:
                continue
            w_new = pd.Series(0.0, index=C.columns)
            w_new[avail] = 1.0 / len(avail)
            # 换手额(单边)= 0.5*Σ|Δw|;成本:买卖都收 SLIP+COMM,卖侧另收 STAMP
            dwe = (w_new - w).abs().sum() * 0.5
            cost = dwe * (2 * (SLIP + COMM) + STAMP)   # 一次换手含买+卖两侧
            nav *= (1.0 - cost)
            turnover_sum += dwe
            w = w_new
    eq = pd.Series(dict(navs)).sort_index()
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    return dict(equity=eq, turnover=turnover_sum / max(years, 0.1))


def main():
    t0 = time.time()
    M = E.load_matrices(start="2007-01-01", min_days=250)
    C = M["close"]
    print(f"池:{C.shape[1]} 只 × {C.shape[0]} 日 | {C.index[0].date()}~{C.index[-1].date()} | load {time.time()-t0:.0f}s", flush=True)

    rows = []
    for name, label in [("hs300", "沪深300 BH"), ("zz800", "中证800 BH"), ("zz500", "中证500 BH")]:
        try:
            s = index_bh(name).reindex(C.index).ffill().dropna()
            rows.append((label, E.metrics(s)))
        except Exception as e:
            print(f"  {label} 跳过: {e}")

    ew = ew_survivorship_free(M)
    rows.append((f"同池等权EW(含退市,{C.shape[1]}只)", E.metrics(ew["equity"])))

    print(f"\n{'基准':<30}{'CAGR':>9}{'Sharpe':>9}{'maxDD':>9}{'Calmar':>8}{'vol':>8}")
    for label, m in rows:
        print(f"{label:<30}{m['CAGR']*100:>8.1f}%{m['Sharpe']:>9}{m['maxDD']*100:>8.1f}%{m['Calmar']:>8}{m['vol']*100:>7.1f}%")
    print(f"\n同池EW 年换手 {ew['turnover']:.2f}× | 总耗时 {time.time()-t0:.0f}s")
    return rows


if __name__ == "__main__":
    main()
