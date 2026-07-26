#!/usr/bin/env python3
"""
eventstudy.py — 事件研究引擎(news_lab R13)· L3 价值发现地基【向量化版】
====================================================================
复用 safna_jr_a 价格面板(20年)+ alt 事件流。对"某类事件在公告日 T 发生"→
测事件后 T+1..T+k 的【相对市场】与【size中性】超额收益(CAAR)。
严格 PIT:公告日 T 已知 → T+1 起可执行(lag=1),无前视。

性能:预计算前向 k 日累计收益矩阵 + 市场/size组基准 → 事件查表 O(N)。
指标:CAAR(累计平均超额)、t 值、hit%(超额>0占比)、N。size中性=减同市值五分组当日均值。
"""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import engine as E  # noqa
DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
ALT = os.path.join(DATA_DIR, "alt")
KS = (1, 3, 5, 10, 20)


class Panel:
    _M = None

    @classmethod
    def load(cls, start="2014-01-01", end=None, ks=KS):
        if cls._M is not None:
            return cls._M
        print(f"装载价格面板 {start}~{end or 'latest'} …", flush=True)
        M = E.load_matrices(start=start, end=end, min_days=250)
        C = M["close"]
        ret1 = C.pct_change(fill_method=None)
        logr = np.log1p(ret1)
        # 前向 k 日累计收益(T+1..T+k):用 log 收益滚动和后 shift(-1) 对齐到"事件日 T"行
        # fwd_k[t] = sum(logr[t+1 .. t+k]) → exp-1
        M["fwd"] = {}
        M["mktfwd"] = {}
        M["grpfwd"] = {}
        sizeq = M["fmc"].rank(axis=1, pct=True)
        grp = (sizeq / 0.2001).apply(np.floor).clip(0, 4)  # 0..4 五分组
        M["grp"] = grp
        for k in ks:
            fsum = logr.shift(-1).rolling(k, min_periods=k).sum().shift(-(k - 1))  # T+1..T+k
            fwd = np.expm1(fsum)
            M["fwd"][k] = fwd
            M["mktfwd"][k] = fwd.mean(axis=1)
            # size 组当日均值:按 grp 分组求每组均值,再 map 回每只
            gf = pd.DataFrame(index=fwd.index, columns=fwd.columns, dtype=float)
            for g in range(5):
                mask = (grp == g)
                grp_mean = fwd.where(mask).mean(axis=1)
                gf = gf.where(~mask, grp_mean, axis=0)
            M["grpfwd"][k] = gf
        M["ret1"] = ret1
        M["_ks"] = tuple(ks)
        cls._M = M
        print(f"面板:{C.shape[1]}只 × {C.shape[0]}日 ({C.index[0].date()}~{C.index[-1].date()}),预计算 k={ks}", flush=True)
        return M

    @classmethod
    def reset(cls):
        cls._M = None


def _col_mapper(cols):
    sample = str(cols[0])
    pref = sample[:3] in ("sh.", "sz.", "bj.")
    def to_col(code):
        c = str(code).strip().lower()
        if pref:
            if "." in c:
                return c
            c = c.zfill(6)
            return ("sh." if c[0] == "6" else "bj." if c[0] in ("4", "8") else "sz.") + c
        return c.replace("sh.", "").replace("sz.", "").replace("bj.", "").zfill(6)
    return to_col


def event_study(M, events, ks=KS, size_neutral=False, label="", min_n=30):
    """events: DataFrame[code, date]. 返回 {k: {CAAR,t,hit,N}}。"""
    C = M["close"]
    dates = C.index
    dpos = pd.Series(range(len(dates)), index=dates)
    to_col = _col_mapper(C.columns)
    colset = set(C.columns)

    # 事件日 → 面板行(公告落到 >= 当日的首个交易日)
    ev = events.copy()
    ev["dt"] = pd.to_datetime(ev["date"], errors="coerce")
    ev = ev.dropna(subset=["dt"])
    ev["col"] = ev["code"].map(to_col)
    ev = ev[ev["col"].isin(colset)]
    # searchsorted 对齐
    idx = dates.searchsorted(ev["dt"].values)  # 首个 >= dt 的位置
    ev = ev.assign(pos=idx)
    ev = ev[(ev["pos"] >= 0) & (ev["pos"] < len(dates))]

    out = {}
    used = None
    for k in ks:
        fwd = M["fwd"][k]
        base = M["grpfwd"][k] if size_neutral else None
        mkt = M["mktfwd"][k]
        vals = []
        for pos, col in zip(ev["pos"].values, ev["col"].values):
            v = fwd.iat[pos, fwd.columns.get_loc(col)] if col in fwd.columns else np.nan
            if not np.isfinite(v):
                continue
            if size_neutral:
                b = base.iat[pos, base.columns.get_loc(col)]
                b = b if np.isfinite(b) else mkt.iat[pos]
            else:
                b = mkt.iat[pos]
            if np.isfinite(b):
                vals.append(v - b)
        a = np.array(vals)
        if used is None:
            used = len(a)
        if len(a) < min_n:
            out[k] = dict(CAAR=None, t=None, hit=None, N=len(a), med=None, wins=None); continue
        caar = a.mean(); t = caar / (a.std(ddof=1) / np.sqrt(len(a))) if a.std() > 0 else 0
        med = np.median(a)
        lo, hi = np.percentile(a, [2.5, 97.5])  # 去尾均值(2.5%双侧)判右尾驱动
        wins = a[(a >= lo) & (a <= hi)].mean()
        out[k] = dict(CAAR=round(caar * 100, 3), t=round(t, 2), hit=round((a > 0).mean() * 100, 1),
                      N=len(a), med=round(med * 100, 3), wins=round(wins * 100, 3))
    tag = f"[{label}] " if label else ""
    print(f"{tag}{'size中性' if size_neutral else 'vs市场'} (事件≈{used}):", flush=True)
    for k in ks:
        o = out[k]
        if o["CAAR"] is not None:
            print(f"   T+{k:<2}: 均值{o['CAAR']:+.2f}%(t{o['t']:+.1f}) 中位{o['med']:+.2f}% 去尾{o['wins']:+.2f}% hit{o['hit']}% N={o['N']}", flush=True)
        else:
            print(f"   T+{k:<2}: N={o['N']}(不足)", flush=True)
    return out


def load_yjyg():
    """业绩预告(净利润),带类型与幅度。"""
    d = pd.read_parquet(os.path.join(ALT, "yjyg.parquet"))
    d = d[d["预测指标"].astype(str).str.contains("净利润", na=False)].copy()
    d["date"] = pd.to_datetime(d["公告日期"]).dt.date
    d = d.rename(columns={"股票代码": "code", "预告类型": "type", "业绩变动幅度": "chg"})
    return d[["code", "date", "type", "chg"]]
