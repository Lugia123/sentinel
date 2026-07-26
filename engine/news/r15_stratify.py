#!/usr/bin/env python3
"""R15 业绩预告惊喜分层:类型 × 幅度 → 漂移是否单调/对称。"""
import pandas as pd, numpy as np
from eventstudy import Panel, event_study, load_yjyg

M = Panel.load(start="2014-01-01")
y = load_yjyg()
print(f"\n业绩预告总 {len(y)} 条,类型分布:", y["type"].value_counts().head(10).to_dict())

print("\n===== 按预告类型(size中性,看 T+5)=====")
order = ["预增", "略增", "扭亏", "续盈", "预盈", "续亏", "略减", "预减", "首亏", "增亏", "不确定"]
for t in order:
    sub = y[y["type"] == t][["code", "date"]]
    if len(sub) < 200:
        continue
    r = event_study(M, sub, ks=(1, 5, 10), label=f"预告={t}", size_neutral=True)

print("\n===== 预增:按业绩变动幅度五分位(size中性)=====")
yz = y[y["type"] == "预增"].copy()
yz = yz[yz["chg"].notna()]
yz["q"] = pd.qcut(yz["chg"].clip(-100, 2000), 5, labels=False, duplicates="drop")
for q in sorted(yz["q"].dropna().unique()):
    sub = yz[yz["q"] == q]
    rng = f"[{sub['chg'].min():.0f}%~{sub['chg'].max():.0f}%]"
    event_study(M, sub[["code", "date"]], ks=(1, 5, 10), label=f"预增Q{int(q)}{rng}", size_neutral=True)
