#!/usr/bin/env python3
"""R24 容量/衰减:共振信号的①长窗漂移(半衰期/反转)②事件频率(容量)③逐年 CAAR(拥挤衰减)。"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eventstudy import Panel, event_study, load_yjyg
ALT = os.path.join(os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")), "alt")
M = Panel.load(start="2014-01-01", ks=(1, 5, 10, 20, 40, 60))
C = M["close"]; dates = C.index


def to_col(c):
    c = str(c).zfill(6); return ("sh." if c[0] == "6" else "bj." if c[0] in ("4", "8") else "sz.") + c


y = load_yjyg(); yz = y[y["type"] == "预增"][["code", "date"]].copy()
yz["date"] = pd.to_datetime(yz["date"]); yz["col"] = yz["code"].map(to_col)
yz = yz[yz["col"].isin(set(C.columns))]
lhb = pd.read_parquet(f"{ALT}/lhb.parquet"); lhb["net"] = pd.to_numeric(lhb["龙虎榜净买额"], errors="coerce")
lb = lhb[lhb["net"] > 0][["代码", "上榜日"]].dropna(); lb["col"] = lb["代码"].map(to_col); lb["d"] = pd.to_datetime(lb["上榜日"])
lbmap = {}
for _, r in lb.iterrows():
    lbmap.setdefault(r["col"], []).append(r["d"])
res = pd.DataFrame([r for _, r in yz.iterrows() if any(abs((d - r["date"]).days) <= 5 for d in lbmap.get(r["col"], []))])
print(f"共振事件 {len(res)}")

print("\n##### R24a 长窗漂移(半衰期/反转)#####")
event_study(M, res[["code", "date"]], ks=(1, 5, 10, 20, 40, 60), label="共振长窗", size_neutral=True)

print("\n##### R24b 容量:逐年事件数 #####")
res["yr"] = res["date"].dt.year
vc = res["yr"].value_counts().sort_index()
print("  每年共振事件:", vc.to_dict())
print(f"  年均 {vc.mean():.0f} 个 → 组合可行性:每年约{vc.mean():.0f}个信号,足够构建持续调仓的聚焦腿")

print("\n##### R24c 拥挤衰减:逐年 CAAR(size中性 T+10)#####")
for yr in sorted(res["yr"].unique()):
    sub = res[res["yr"] == yr]
    if len(sub) >= 40:
        r = event_study(M, sub[["code", "date"]], ks=(10,), label=f"{yr}", size_neutral=True, min_n=30)
