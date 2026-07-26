#!/usr/bin/env python3
"""另类/事件数据 → date×code 信号矩阵(PIT 无前视)。数据源无关的通用管道。

核心问题:另类数据(龙虎榜/北向/两融/股东户数/解禁/业绩预告/分析师…)是"事件型长表"
(每行 = 某股某披露日的一个值),要变成引擎能吃的 date×code 矩阵,且严禁前视——
只能在【公开可得日】之后使用该值。本模块统一处理三件事:
  1. 列名对齐到 M 的日历(reindex 到交易日)与代码(baostock 风格 sh.600000)。
  2. PIT 滞后:信号在【披露日/可得日 + lag 个交易日】才生效(默认 lag=1,次日才用)。
  3. 前向填充:低频事件(季度/不定期)在下次更新前保持最近值(可设 max_ffill 上限,过期作废)。

用法:
    import altdata as A
    sig = A.events_to_matrix(df, M, code_col="code", date_col="pub_date",
                             val_col="value", lag=1, max_ffill=None)
    # sig 与 M["close"] 同 index/columns,可直接 .where(mask) 后喂 E.backtest
"""
import numpy as np, pandas as pd


def _norm_code_safe(s):
    s = str(s).strip().upper()
    for suf in (".SH", ".SZ", ".BJ"):
        s = s.replace(suf, "")
    for pre in ("SH", "SZ", "BJ"):
        if s.startswith(pre):
            s = s[len(pre):]
    s = s.replace(".", "").strip().zfill(6)
    if s[0] == "6":
        return "sh." + s
    if s[0] in ("0", "3"):
        return "sz." + s
    if s[0] in ("4", "8"):
        return "bj." + s
    return "sz." + s


def events_to_matrix(df, M, code_col="code", date_col="pub_date", val_col="value",
                     lag=1, max_ffill=None, agg="last", already_norm=False):
    """事件长表 → date×code 信号矩阵(与 M 对齐,PIT)。
    df: 含 [code, 披露日, 值] 的长表。date_col 必须是【公开可得日】(披露日),不是报告期!
    lag: 信号在可得日之后第 lag 个交易日才生效(默认 1,次日才用,防同日前视)。
    max_ffill: 前向填充的最大交易日数(None=无限,保持到下次更新;设值则过期作废)。
    agg: 同一 (code, 交易日) 多条时的聚合('last'/'sum'/'mean'/'max'/'min')。
    返回:date×code DataFrame,index=M 交易日,columns=M 代码。缺失=NaN(不参与选股)。"""
    cal = M["close"].index                       # 交易日日历
    cols = M["close"].columns                    # 全池代码
    d = df[[code_col, date_col, val_col]].copy()
    d.columns = ["code", "date", "val"]
    d = d.dropna(subset=["code", "date"])
    if not already_norm:
        d["code"] = d["code"].map(_norm_code_safe)
    d = d[d["code"].isin(cols)]
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.dropna(subset=["date"])
    d["val"] = pd.to_numeric(d["val"], errors="coerce")
    # 把披露日对齐到 >= 该日的第 lag 个交易日(searchsorted 保证无前视)
    pos = cal.searchsorted(d["date"].values, side="left")  # 首个 >= 披露日的交易日下标
    pos = pos + int(lag)                                     # 再滞后 lag 个交易日
    ok = pos < len(cal)
    d = d[ok.values if hasattr(ok, "values") else ok].copy()
    d["eff"] = cal[pos[ok.values if hasattr(ok, "values") else ok]]
    # 聚合同一 (code, 生效日)
    g = d.groupby(["eff", "code"])["val"]
    d2 = getattr(g, agg)().reset_index() if agg != "last" else g.last().reset_index()
    sig = d2.pivot(index="eff", columns="code", values="val")
    sig = sig.reindex(index=cal, columns=cols)
    sig = sig.ffill(limit=max_ffill)
    return sig


def in_era(eq, start):
    """把权益曲线截到 start 之后并归一(同期对照用)。"""
    e = eq.dropna()
    e = e[e.index >= pd.Timestamp(start)]
    return e / e.iloc[0] if len(e) else e


def mret(eq):
    return eq.dropna().resample("ME").last().pct_change(fill_method=None).dropna()


def corr(e1, e2, start=None):
    a, b = mret(e1), mret(e2)
    if start:
        a = a[a.index >= pd.Timestamp(start)]
        b = b[b.index >= pd.Timestamp(start)]
    j = pd.concat([a, b], axis=1, join="inner").dropna()
    return round(j.iloc[:, 0].corr(j.iloc[:, 1]), 2) if len(j) > 5 else np.nan
