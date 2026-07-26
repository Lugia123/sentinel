#!/usr/bin/env python3
"""R21 新闻事件因子:把稀疏事件惊喜分向前携带成截面因子,测 rank-IC / 分组单调 / size 正交性。
factor[date,stock] = 最近一次业绩预告惊喜分(类型符号×log(1+|幅度|)),事件后携带 CARRY 日。"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eventstudy import Panel, load_yjyg

M = Panel.load(start="2014-01-01")
C = M["close"]; dates = C.index; cols = C.columns
fwd = M["fwd"]; grpfwd = M["grpfwd"]
CARRY = 20   # 事件后携带交易日(PEAD 漂移窗)
TYPE_SIGN = {"预增": 1, "略增": 0.5, "扭亏": 0.7, "续盈": 0.2, "预盈": 0.5,
             "续亏": -0.5, "略减": -0.3, "预减": -1, "首亏": -0.8, "增亏": -0.7, "不确定": 0}


def to_col(c):
    c = str(c).zfill(6)
    return ("sh." if c[0] == "6" else "bj." if c[0] in ("4", "8") else "sz.") + c


# 构造事件惊喜分
y = load_yjyg()
y = y[y["type"].isin(TYPE_SIGN)].copy()
# 惊喜分 = 类型符号(方向) × log(1+|幅度|)(强度)。修:去掉多余的 sign 抵消导致丢方向的 bug。
y["score"] = y["type"].map(TYPE_SIGN) * np.log1p(y["chg"].clip(-95, 5000).abs().fillna(0))
y["col"] = y["code"].map(to_col)
y = y[y["col"].isin(set(cols))]
y["dt"] = pd.to_datetime(y["date"])

# 因子矩阵:事件当日置分,向前 ffill CARRY 日(用 reindex+limit)
fac = pd.DataFrame(index=dates, columns=cols, dtype=float)
y["pos"] = dates.searchsorted(y["dt"])
y = y[y["pos"] < len(dates)]
for col, grp in y.groupby("col"):
    s = pd.Series(np.nan, index=range(len(dates)))
    for _, r in grp.iterrows():
        s.iloc[r["pos"]] = r["score"]
    s = s.ffill(limit=CARRY)
    fac[col] = s.values
print(f"因子非空覆盖:日均 {fac.notna().sum(axis=1).mean():.0f} 只", flush=True)

# rank-IC:每日截面 factor vs 前向k日超额(size中性用 grpfwd)
def rank_ic(k, size_neutral=True):
    f = fac
    excess = fwd[k] - (grpfwd[k] if size_neutral else 0)
    ics = []
    for i in range(len(dates)):
        fi = f.iloc[i]; ei = excess.iloc[i]
        m = fi.notna() & ei.notna()
        if m.sum() < 20:
            continue
        ics.append(fi[m].rank().corr(ei[m].rank()))
    ics = np.array(ics)
    return ics.mean(), ics.mean() / ics.std() * np.sqrt(len(ics)) if ics.std() > 0 else 0, len(ics)


print("\n##### R21 因子 rank-IC(size中性)#####")
for k in (5, 10, 20):
    ic, icir_t, n = rank_ic(k, size_neutral=True)
    print(f"  T+{k:<2}: 平均rank-IC={ic:+.4f}  IC_t≈{icir_t:+.1f}  有效日={n}")

# 分组单调:因子五分位 → 前向10日超额
print("\n##### 因子五分位 → 前向10日 size中性超额(%)#####")
k = 10
excess = fwd[k] - grpfwd[k]
buckets = {q: [] for q in range(5)}
for i in range(len(dates)):
    fi = fac.iloc[i]; ei = excess.iloc[i]
    m = fi.notna() & ei.notna()
    if m.sum() < 25:
        continue
    q = pd.qcut(fi[m].rank(method="first"), 5, labels=False)
    for qq in range(5):
        buckets[qq].extend(ei[m][q == qq].values)
for qq in range(5):
    a = np.array(buckets[qq])
    print(f"  Q{qq} (低→高惊喜): 均值{a.mean()*100:+.2f}%  中位{np.median(a)*100:+.2f}%  N={len(a)}")

# size 正交性:因子 vs 流通市值分位 相关
sizeq = M["fmc"].rank(axis=1, pct=True)
corrs = []
for i in range(0, len(dates), 5):
    fi = fac.iloc[i]; si = sizeq.iloc[i]
    m = fi.notna() & si.notna()
    if m.sum() > 20:
        corrs.append(fi[m].corr(si[m], method="spearman"))
print(f"\n因子 vs size 分位 平均相关: {np.nanmean(corrs):+.3f}  (≈0=正交,不是size伪装)")
