#!/usr/bin/env python3
"""R23 体制/交互:共振信号(预增×龙虎榜)的边际是否集中在特定市值/牛熊,是否只是 size/beta 伪装。"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eventstudy import Panel, event_study, load_yjyg
ALT = os.path.join(os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")), "alt")
M = Panel.load(start="2014-01-01")
C = M["close"]; dates = C.index; ret = M["ret1"]
sizeq = M["fmc"].rank(axis=1, pct=True)
mkt = ret.mean(axis=1)
mkt60 = mkt.rolling(60).mean()  # 牛熊代理


def to_col(c):
    c = str(c).zfill(6); return ("sh." if c[0] == "6" else "bj." if c[0] in ("4", "8") else "sz.") + c


# 构造共振事件集:预增 ∩ ±5日龙虎榜净买入
y = load_yjyg(); yz = y[y["type"] == "预增"][["code", "date"]].copy()
yz["date"] = pd.to_datetime(yz["date"]); yz["col"] = yz["code"].map(to_col)
yz = yz[yz["col"].isin(set(C.columns))]
lhb = pd.read_parquet(f"{ALT}/lhb.parquet"); lhb["net"] = pd.to_numeric(lhb["龙虎榜净买额"], errors="coerce")
lb = lhb[lhb["net"] > 0][["代码", "上榜日"]].dropna(); lb["col"] = lb["代码"].map(to_col)
lb["d"] = pd.to_datetime(lb["上榜日"])
lbmap = {}
for _, r in lb.iterrows():
    lbmap.setdefault(r["col"], []).append(r["d"])
res = []
for _, r in yz.iterrows():
    ds = lbmap.get(r["col"], [])
    if any(abs((d - r["date"]).days) <= 5 for d in ds):
        res.append(r)
res = pd.DataFrame(res)
res["pos"] = dates.searchsorted(res["date"]); res = res[res["pos"] < len(dates)]
print(f"共振事件 {len(res)} 个")

# 事件日的 size 分位 + 市场体制
res["sz"] = [sizeq.iat[p, sizeq.columns.get_loc(c)] if c in sizeq.columns else np.nan
             for p, c in zip(res["pos"], res["col"])]
res["reg"] = [mkt60.iloc[p] for p in res["pos"]]

print("\n##### 共振 × 市值三分层(size中性 T+10)#####")
res2 = res.dropna(subset=["sz"])
for lab, m in [("小市值(<0.4)", res2["sz"] < 0.4), ("中(0.4-0.7)", (res2["sz"] >= 0.4) & (res2["sz"] < 0.7)), ("大(≥0.7)", res2["sz"] >= 0.7)]:
    event_study(M, res2[m][["code", "date"]], ks=(5, 10), label=f"共振·{lab}", size_neutral=True, min_n=20)

print("\n##### 共振 × 牛熊体制(size中性 T+10)#####")
for lab, m in [("牛(60日市场>0)", res["reg"] > 0), ("熊(60日市场≤0)", res["reg"] <= 0)]:
    event_study(M, res[m][["code", "date"]], ks=(5, 10), label=f"共振·{lab}", size_neutral=True, min_n=20)

# 共振腿 vs 市场 alpha/beta(用共振事件后10日等权收益构造月度序列近似)
print("\n##### 共振信号的 alpha/beta(月度)#####")
# 每月:该月发生的共振事件,持有10日的平均超额,近似月度策略收益
res["ym"] = res["date"].dt.to_period("M")
fwd10 = M["fwd"][10]; mkt10 = M["mktfwd"][10]
res["fx"] = [fwd10.iat[p, fwd10.columns.get_loc(c)] if c in fwd10.columns else np.nan for p, c in zip(res["pos"], res["col"])]
res["mk"] = [mkt10.iloc[p] for p in res["pos"]]
mon = res.dropna(subset=["fx"]).groupby("ym").agg(strat=("fx", "mean"), mret=("mk", "mean")).dropna()
if len(mon) > 24:
    b, a = np.polyfit(mon["mret"], mon["strat"], 1)
    resid = mon["strat"] - (a + b * mon["mret"])
    talpha = a / (resid.std() / np.sqrt(len(mon)))
    print(f"  月度回归 strat = alpha + beta*mkt: beta={b:.2f}  alpha={a*100:+.2f}%/10日  t(alpha)={talpha:+.1f}  月数={len(mon)}")
    print(f"  → beta{'高(≈市场)' if b>0.7 else '中低'},alpha{'显著' if abs(talpha)>2 else '不显著'}")
