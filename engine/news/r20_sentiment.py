#!/usr/bin/env python3
"""R20 AI 情绪 → 方向:AI 读业绩预告文本打连续情绪分,回测其 IC,对比机械类型符号 baseline。
检验"AI 情绪是否比硬事件多出独立方向信息"(预期:只复现类型,不独立 → 印证 SAFNA-A)。
数据约束:历史规模化新闻文本无 → 用 yjyg 结构字段拼文本作代理;抽样控成本。"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eventstudy import Panel, load_yjyg
import newsai

M = Panel.load(start="2014-01-01")
C = M["close"]; dates = C.index
fwd5 = M["fwd"][5]; mkt5 = M["mktfwd"][5]

TYPE_SIGN = {"预增": 1, "略增": 0.5, "扭亏": 0.7, "续盈": 0.2, "预盈": 0.5,
             "续亏": -0.5, "略减": -0.3, "预减": -1, "首亏": -0.8, "增亏": -0.7, "不确定": 0}

y = load_yjyg()
y = y[y["type"].isin(TYPE_SIGN)].copy()
y["date"] = pd.to_datetime(y["date"])
# 抽样(分层,控成本):每类型抽~110
np.random.seed(0)
samp = y.groupby("type", group_keys=False).apply(lambda g: g.sample(min(len(g), 110), random_state=0))
print(f"抽样 {len(samp)} 条 AI 打分…", flush=True)

SYS = """给你一批A股业绩预告,对每条判断【市场情绪方向强度】,-1(极度利空)到+1(极度利好)连续值。
只看文本传达的惊喜方向与力度,输出JSON:{"items":[{"id":1,"s":0.8},...]}。不预测涨跌幅。"""


def blurb(r):
    return f'{r["type"]}, 净利润变动{r["chg"]:.0f}%' if pd.notna(r["chg"]) else str(r["type"])


rows = samp.reset_index(drop=True)
ai_scores = {}
for i in range(0, len(rows), 25):
    b = rows.iloc[i:i+25]
    user = "预告批次:\n" + "\n".join(f'{j+1}. {blurb(r)}' for j, (_, r) in enumerate(b.iterrows()))
    try:
        out = newsai.chat(SYS, user, temperature=0.0, json_mode=True)
        for it in newsai.extract_json(out).get("items", []):
            ai_scores[i + int(it["id"]) - 1] = float(it["s"])
    except Exception as e:
        print(f"  batch {i} fail {e}")

# 前向5日超额
def fwd_excess(code, dt):
    col = ("sh." if str(code).zfill(6)[0] == "6" else "bj." if str(code).zfill(6)[0] in ("4", "8") else "sz.") + str(code).zfill(6)
    if col not in fwd5.columns:
        return np.nan
    pos = dates.searchsorted(dt)
    if pos >= len(dates):
        return np.nan
    v = fwd5.iat[pos, fwd5.columns.get_loc(col)]
    return v - mkt5.iat[pos] if np.isfinite(v) else np.nan

rows["ai"] = [ai_scores.get(i, np.nan) for i in range(len(rows))]
rows["typesign"] = rows["type"].map(TYPE_SIGN)
rows["fx"] = [fwd_excess(r["code"], r["date"]) for _, r in rows.iterrows()]
d = rows.dropna(subset=["ai", "fx"])
print(f"\n有效 {len(d)} 条")
ic_ai = d["ai"].corr(d["fx"], method="spearman")
ic_type = d["typesign"].corr(d["fx"], method="spearman")
ic_mag = d["chg"].clip(-100, 2000).corr(d["fx"], method="spearman") if d["chg"].notna().sum() > 30 else np.nan
# AI 与类型符号的相关(是否只是复现)
ai_vs_type = d["ai"].corr(d["typesign"], method="spearman")
# 偏相关:控制类型符号后 AI 残差还有 IC 吗
from numpy.polynomial import polynomial as P
res_ai = d["ai"] - np.poly1d(np.polyfit(d["typesign"], d["ai"], 1))(d["typesign"])
ic_ai_resid = pd.Series(res_ai.values).corr(pd.Series(d["fx"].values), method="spearman")
print(f"rank-IC(vs 前向5日超额):")
print(f"  AI情绪分      : {ic_ai:+.4f}")
print(f"  机械类型符号  : {ic_type:+.4f}")
print(f"  变动幅度      : {ic_mag:+.4f}")
print(f"  AI vs 类型符号相关: {ai_vs_type:+.4f}  (高=AI只复现类型)")
print(f"  控类型后AI残差IC : {ic_ai_resid:+.4f}  (≈0=AI无独立信息)")
