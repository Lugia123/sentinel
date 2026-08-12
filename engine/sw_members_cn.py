#!/usr/bin/env python3
"""A股 code → 申万行业(tushare `index_member_all`)—— 全站统一数据源。

统一口径:板块分类与 sw_levels(资金流页分级)同走 **tushare 申万(SW2021)**,不再依赖 akshare 静态
`sw_industry.csv`(当期快照/需手动重抓)。一次调用即得全市场每股的 L1/L2/L3 行业名 + 进出日(PIT)。
带 7 天文件缓存(避免每次多打一次 tushare)。ts_code(600000.SH)→ 项目 canonical(sh.600000)。

用法:python sw_members_cn.py   → 打印层级/覆盖统计。
"""
import os, json, time

HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE = os.path.join(HERE, "data_cn_meta", "sw_members.json")
_LEGACY = os.path.join(HERE, "data_cn_meta", "sw_industry.csv")  # akshare 静态,仅 tushare 不可用时回退


def _norm(ts_code):
    """600000.SH → sh.600000 / 000001.SZ → sz.000001 / 830799.BJ → bj.830799。"""
    s = str(ts_code).strip()
    if "." not in s:
        return s
    num, suf = s.split(".", 1)
    return f"{suf.lower()}.{num}"


def _from_tushare():
    from ts_refresh import ts
    df = ts("index_member_all", {"is_new": "Y"}, "l1_name,ts_code,out_date")
    if df is None or df.empty:
        return {}
    m = {}
    for _, r in df.iterrows():
        # is_new=Y 为最新在册;out_date 为空 = 当前归属(双保险)
        if r.get("out_date"):
            continue
        nm = str(r.get("l1_name") or "").strip()
        if nm:
            m[_norm(r["ts_code"])] = nm
    return m


def _from_legacy():
    """tushare 失败时回退 akshare 静态 sw_industry.csv(若存在)。"""
    try:
        import pandas as pd
        d = pd.read_csv(_LEGACY, dtype=str)
        return dict(zip(d["code"], d["sw_name"]))
    except Exception:
        return {}


def code_to_l1():
    """返回 {code: 申万一级行业名}。tushare(缓存7天)→ 失败回退静态 → 再失败空 dict(前端记「其他」)。"""
    try:
        if os.path.exists(_CACHE) and time.time() - os.path.getmtime(_CACHE) < 7 * 86400:
            return json.load(open(_CACHE, encoding="utf-8"))
    except Exception:
        pass
    m = {}
    try:
        m = _from_tushare()
    except Exception:
        m = {}
    if not m:
        return _from_legacy()   # tushare 挂了 → 用静态兜底,不缓存(下次再试 tushare)
    try:
        os.makedirs(os.path.dirname(_CACHE), exist_ok=True)
        json.dump(m, open(_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass
    return m


if __name__ == "__main__":
    m = code_to_l1()
    from collections import Counter
    c = Counter(m.values())
    print(f"申万一级 {len(c)} 个行业,覆盖 {len(m)} 只")
    print("样例:", list(m.items())[:3])
