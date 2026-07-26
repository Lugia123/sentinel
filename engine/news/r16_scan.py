#!/usr/bin/env python3
"""R16 系统性事件类型 alpha 扫描:各 alt 事件类型(带方向拆分)→ size中性事件研究。
PIT:一律用【公开披露日】(公告日/上榜日/交易日/解禁日),T+1 起算。找 rev+PEAD 之外的存活信号。"""
import pandas as pd, numpy as np, os
from eventstudy import Panel, event_study
ALT = os.path.join(os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")), "alt")

M = Panel.load(start="2014-01-01")
KS = (1, 5, 10)


def ev(df, code_col, date_col):
    d = df[[code_col, date_col]].dropna().copy()
    d.columns = ["code", "date"]
    d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.date
    return d.dropna()


print("\n########## R16 事件类型扫描(size中性)##########")

# ── 增减持 ggcg:方向=增持/减持,PIT=公告日 ──
g = pd.read_parquet(f"{ALT}/ggcg.parquet")
g["dir"] = g["持股变动信息-增减"].astype(str)
for name, mask in [("增持", g["dir"].str.contains("增", na=False)), ("减持", g["dir"].str.contains("减", na=False))]:
    event_study(M, ev(g[mask], "代码", "公告日"), ks=KS, label=f"高管增减持·{name}", size_neutral=True)

# ── 回购 repurchase:全部利多,PIT=最新公告日期 ──
rp = pd.read_parquet(f"{ALT}/repurchase.parquet")
event_study(M, ev(rp, "股票代码", "最新公告日期"), ks=KS, label="回购公告", size_neutral=True)

# ── 解禁 jiejin:利空(供给增),PIT=解禁日(提前已知);按占流通市值比例分大小 ──
jj = pd.read_parquet(f"{ALT}/jiejin.parquet")
jj["ratio"] = pd.to_numeric(jj["占解禁前流通市值比例"], errors="coerce")
event_study(M, ev(jj, "股票代码", "解禁时间"), ks=KS, label="解禁(全部)", size_neutral=True)
big = jj[jj["ratio"] > jj["ratio"].quantile(0.8)]
event_study(M, ev(big, "股票代码", "解禁时间"), ks=KS, label="解禁(大额>P80)", size_neutral=True)

# ── 龙虎榜 lhb:方向=净买额符号,PIT=上榜日(盘后披露→T+1) ──
lhb = pd.read_parquet(f"{ALT}/lhb.parquet")
lhb["net"] = pd.to_numeric(lhb["龙虎榜净买额"], errors="coerce")
for name, mask in [("净买入", lhb["net"] > 0), ("净卖出", lhb["net"] < 0)]:
    event_study(M, ev(lhb[mask], "代码", "上榜日"), ks=KS, label=f"龙虎榜·{name}", size_neutral=True)

# ── 大宗交易 dzjy:方向=折溢率符号,PIT=交易日 ──
dz = pd.read_parquet(f"{ALT}/dzjy.parquet")
dz["prem"] = pd.to_numeric(dz["折溢率"], errors="coerce")
for name, mask in [("溢价", dz["prem"] > 0), ("折价", dz["prem"] < 0)]:
    event_study(M, ev(dz[mask], "证券代码", "交易日期"), ks=KS, label=f"大宗·{name}", size_neutral=True)

# ── 股东户数 gdhs:户数减少=筹码集中(利多),增加=分散(利空),PIT=公告日 ──
gh = pd.read_parquet(f"{ALT}/gdhs.parquet")
gh["chg"] = pd.to_numeric(gh["股东户数-增减比例"], errors="coerce")
for name, mask in [("户数减少(集中)", gh["chg"] < -0.05), ("户数增加(分散)", gh["chg"] > 0.05)]:
    event_study(M, ev(gh[mask], "代码", "公告日期"), ks=KS, label=f"股东户数·{name}", size_neutral=True)
