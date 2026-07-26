#!/usr/bin/env python3
"""R22 事件腿合成回测:long-only(A股现实),按业绩惊喜因子选股 + 龙虎榜共振加权,定期调仓,
对比等权市场基线。用 safna_jr_a metrics 算 Sharpe/回撤。含真摩擦(印花税0.05%单边卖+佣金)。"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from eventstudy import Panel, load_yjyg
import engine as E
ALT = os.path.join(os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")), "alt")

M = Panel.load(start="2014-01-01")
C = M["close"]; dates = C.index; cols = C.columns; ret = M["ret1"]
M["mktret"] = ret.mean(axis=1)
CARRY, HOLD, TOPN = 20, 5, 40
TYPE_SIGN = {"预增": 1, "略增": 0.5, "扭亏": 0.7, "续盈": 0.2, "预盈": 0.5,
             "续亏": -0.5, "略减": -0.3, "预减": -1, "首亏": -0.8, "增亏": -0.7, "不确定": 0}


def to_col(c):
    c = str(c).zfill(6); return ("sh." if c[0] == "6" else "bj." if c[0] in ("4", "8") else "sz.") + c


# 因子矩阵(同 R21,修正版)
y = load_yjyg(); y = y[y["type"].isin(TYPE_SIGN)].copy()
y["score"] = y["type"].map(TYPE_SIGN) * np.log1p(y["chg"].clip(-95, 5000).abs().fillna(0))
y["col"] = y["code"].map(to_col); y = y[y["col"].isin(set(cols))]
y["pos"] = dates.searchsorted(pd.to_datetime(y["date"])); y = y[y["pos"] < len(dates)]
fac = pd.DataFrame(index=range(len(dates)), columns=cols, dtype=float)
for col, g in y.groupby("col"):
    s = pd.Series(np.nan, index=range(len(dates)))
    for _, r in g.iterrows():
        s.iloc[r["pos"]] = max(s.iloc[r["pos"]] if pd.notna(s.iloc[r["pos"]]) else -9, r["score"])
    fac[col] = s.ffill(limit=CARRY).values

# 龙虎榜净买入集合(用于共振加权):col×pos 命中
lhb = pd.read_parquet(f"{ALT}/lhb.parquet"); lhb["net"] = pd.to_numeric(lhb["龙虎榜净买额"], errors="coerce")
lb = lhb[lhb["net"] > 0][["代码", "上榜日"]].dropna()
lb["col"] = lb["代码"].map(to_col); lb["pos"] = dates.searchsorted(pd.to_datetime(lb["上榜日"]))
lbset = set(zip(lb["col"], lb["pos"].clip(0, len(dates) - 1)))
lb_recent = pd.DataFrame(0, index=range(len(dates)), columns=cols)  # ±5日内有龙虎榜净买
for col, pos in lbset:
    if col in cols:
        lo, hi = max(0, pos - 5), min(len(dates), pos + 1)
        lb_recent.iloc[lo:hi, lb_recent.columns.get_loc(col)] = 1


can_buy = M["can_buy"]; sizeq = M["fmc"].rank(axis=1, pct=True)


def backtest(use_resonance=False, only_pos=True, realistic=True):
    """每 HOLD 日调仓,选因子最强 TOPN,等权持有 HOLD 日,含卖出摩擦。
    realistic:①T+1 一字涨停不可买(can_buy)②剔小市值下 30%(流动性/容量)。"""
    fee = 0.0007
    rets = []
    for i in range(250, len(dates) - HOLD - 1, HOLD):
        f = fac.iloc[i].copy()
        if only_pos:
            f = f[f > 0]
        if use_resonance:
            f = f * (1 + 0.5 * lb_recent.iloc[i].reindex(f.index).fillna(0))
        cand = f.dropna()
        if realistic:
            # T+1 可买(次日非一字涨停不停牌)+ 市值下限(剔最小30%)
            cb = can_buy.iloc[i + 1].reindex(cand.index).fillna(False)
            sz = sizeq.iloc[i].reindex(cand.index).fillna(0)
            cand = cand[cb.values & (sz.values > 0.3)]
        picks = cand.nlargest(TOPN).index
        if len(picks) < 5:
            rets.extend([M["mktret"].iloc[i + j] for j in range(1, HOLD + 1)]); continue
        for j in range(1, HOLD + 1):
            rr = ret[picks].iloc[i + j]
            if realistic:
                rr = rr.clip(-0.11, 0.11)  # 单日涨跌停裁剪(去极端小盘假收益)
            rets.append(rr.mean() if np.isfinite(rr.mean()) else 0)
        rets[-HOLD] -= fee  # 调仓摩擦计入首日
    r = pd.Series(rets).fillna(0)
    equity = (1 + r).cumprod()
    ann = equity.iloc[-1] ** (252 / len(r)) - 1
    vol = r.std() * np.sqrt(252)
    return dict(ann=ann * 100, vol=vol * 100, sharpe=ann / vol if vol > 0 else 0,
                mdd=(equity / equity.cummax() - 1).min() * 100, n=len(r))


print("\n##### R22 事件腿回测(long-only, 含卖出摩擦)#####")
mkt = M["mktret"].iloc[250:].fillna(0)
meq = (1 + mkt).cumprod(); mann = meq.iloc[-1] ** (252 / len(mkt)) - 1
print(f"  等权市场基线 : 年化{mann*100:+.1f}%  波动{mkt.std()*np.sqrt(252)*100:.1f}%  "
      f"Sharpe{mann/(mkt.std()*np.sqrt(252)):.2f}  MDD{(meq/meq.cummax()-1).min()*100:.1f}%")
for name, kw in [("惊喜因子腿(朴素)", dict(use_resonance=False, realistic=False)),
                 ("惊喜因子腿(真实约束)", dict(use_resonance=False, realistic=True)),
                 ("惊喜+共振腿(真实约束)", dict(use_resonance=True, realistic=True))]:
    r = backtest(**kw)
    print(f"  {name:22s}: 年化{r['ann']:+.1f}%  波动{r['vol']:.1f}%  Sharpe{r['sharpe']:.2f}  MDD{r['mdd']:.1f}%  N={r['n']}")
