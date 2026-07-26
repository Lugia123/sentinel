#!/usr/bin/env python3
"""R19 事件量异动 → 风险信号:聚合所有事件流成每股每日事件计数,测密度突变后的前向【已实现波动】。
非方向:检验"有事发生"能否预警波动/回撤上升(SAFNA-A:情绪不独立,但风险提示对人有用)。"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, os
from eventstudy import Panel
ALT = os.path.join(os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")), "alt")
M = Panel.load(start="2014-01-01")
C = M["close"]; ret = M["ret1"]
dates = C.index

# 前向已实现波动(T+1..T+10 日收益年化std)+ 前向最大回撤
fwd_vol = ret.shift(-1).rolling(10).std().shift(-9) * np.sqrt(252)
# 前向10日累计最低点相对进入价(近似最大回撤)
fwd_min = (1 + ret.shift(-1)).rolling(10).apply(lambda x: np.cumprod(x).min() - 1, raw=True).shift(-9)

# 聚合事件流 → 每股每日事件计数
def load_ev(f, ccol, dcol):
    d = pd.read_parquet(f"{ALT}/{f}.parquet")[[ccol, dcol]].dropna()
    d.columns = ["code", "date"]
    d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.normalize()
    d["code"] = d["code"].astype(str).str.zfill(6)
    return d.dropna()

streams = [("yjyg", "股票代码", "公告日期"), ("lhb", "代码", "上榜日"), ("dzjy", "证券代码", "交易日期"),
           ("ggcg", "代码", "公告日"), ("jiejin", "股票代码", "解禁时间"), ("gdhs", "代码", "公告日期"),
           ("repurchase", "股票代码", "最新公告日期")]
allev = pd.concat([load_ev(*s) for s in streams], ignore_index=True)
cnt = allev.groupby(["date", "code"]).size().rename("n").reset_index()
print(f"事件总 {len(allev)},(股,日)计数 {len(cnt)}", flush=True)

# 面板列前缀映射
def to_col(c):
    return ("sh." if c[0] == "6" else "bj." if c[0] in ("4", "8") else "sz.") + c
cnt["col"] = cnt["code"].map(to_col)
cnt = cnt[cnt["col"].isin(set(C.columns))]
dpos = pd.Series(range(len(dates)), index=dates.normalize())

# 高密度事件日(单日≥N个事件)vs 单事件日,比较前向波动/回撤
def stat(sub, label):
    vols, mins = [], []
    for d, col in zip(sub["date"].values, sub["col"].values):
        pos = dpos.get(pd.Timestamp(d))
        if pos is None or pos >= len(dates):
            continue
        v = fwd_vol.iat[pos, fwd_vol.columns.get_loc(col)] if col in fwd_vol.columns else np.nan
        m = fwd_min.iat[pos, fwd_min.columns.get_loc(col)] if col in fwd_min.columns else np.nan
        if np.isfinite(v): vols.append(v)
        if np.isfinite(m): mins.append(m)
    if len(vols) < 50:
        print(f"[{label}] N不足"); return
    print(f"[{label}] N={len(vols)}  前向10日年化波动 中位={np.median(vols)*100:.1f}%  "
          f"前向10日回撤 中位={np.median(mins)*100:.2f}%  P10回撤={np.percentile(mins,10)*100:.1f}%", flush=True)

print("\n##### R19 事件密度 → 前向风险 #####")
stat(cnt[cnt["n"] == 1], "单事件日")
stat(cnt[cnt["n"] == 2], "2事件日")
stat(cnt[cnt["n"] >= 3], "≥3事件日(密度突变)")
stat(cnt[cnt["n"] >= 5], "≥5事件日(极端)")
# 基线:随机(股,日)
np.random.seed(0)
rc = pd.DataFrame({"date": np.random.choice(dates.normalize(), 20000), "col": np.random.choice(list(C.columns), 20000)})
stat(rc, "随机基线")
