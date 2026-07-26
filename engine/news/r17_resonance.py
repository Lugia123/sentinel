#!/usr/bin/env python3
"""R17 事件共振 + 龙虎榜右尾稳健性:①龙虎榜均值/中位/去尾对比 ②预增×其他信号同窗叠加。"""
import pandas as pd, numpy as np, os
from eventstudy import Panel, event_study, load_yjyg
ALT = os.path.join(os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")), "alt")
M = Panel.load(start="2014-01-01")
KS = (1, 5, 10)


def ev(df, c, d):
    x = df[[c, d]].dropna().copy(); x.columns = ["code", "date"]
    x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.date
    return x.dropna()


print("\n##### R17a 龙虎榜右尾稳健性(均值 vs 中位 vs 去尾)#####")
lhb = pd.read_parquet(f"{ALT}/lhb.parquet"); lhb["net"] = pd.to_numeric(lhb["龙虎榜净买额"], errors="coerce")
event_study(M, ev(lhb[lhb["net"] > 0], "代码", "上榜日"), ks=KS, label="龙虎榜净买入", size_neutral=True)
event_study(M, ev(lhb[lhb["net"] < 0], "代码", "上榜日"), ks=KS, label="龙虎榜净卖出", size_neutral=True)

print("\n##### R17b 事件共振:预增 × 其他信号同窗(±5日)叠加 #####")
y = load_yjyg(); yz = y[y["type"] == "预增"][["code", "date"]].copy()
yz["date"] = pd.to_datetime(yz["date"]).dt.date
yz["code"] = yz["code"].astype(str)
# 基线
event_study(M, yz, ks=KS, label="预增(基线)", size_neutral=True)

# 龙虎榜净买入事件集(code,date)
lb = ev(lhb[lhb["net"] > 0], "代码", "上榜日"); lb["code"] = lb["code"].astype(str)
# 股东户数集中
gh = pd.read_parquet(f"{ALT}/gdhs.parquet"); gh["chg"] = pd.to_numeric(gh["股东户数-增减比例"], errors="coerce")
gc = ev(gh[gh["chg"] < -0.05], "代码", "公告日期"); gc["code"] = gc["code"].astype(str)


def resonate(base, other, win=5, label=""):
    """base 事件里,±win 日内该股也有 other 事件的子集。"""
    om = {}
    for _, r in other.iterrows():
        om.setdefault(str(r["code"]).zfill(6) if str(r["code"]).isdigit() else str(r["code"]), []).append(r["date"])
    keep = []
    for _, r in base.iterrows():
        c = str(r["code"]).zfill(6) if str(r["code"]).isdigit() else str(r["code"])
        ds = om.get(c, [])
        if any(abs((d - r["date"]).days) <= win for d in ds):
            keep.append(r)
    sub = pd.DataFrame(keep)
    if len(sub) >= 30:
        event_study(M, sub[["code", "date"]], ks=KS, label=label, size_neutral=True)
    else:
        print(f"[{label}] 共振样本不足 N={len(sub)}")


resonate(yz, lb, win=5, label="预增 ∩ 龙虎榜净买入(±5日)")
resonate(yz, gc, win=10, label="预增 ∩ 股东户数集中(±10日)")
