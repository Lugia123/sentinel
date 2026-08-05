#!/usr/bin/env python3
"""A股【未来20日收益范围】逐日历史序列 —— 详情页价格图下方两张图(收益% / 价格锥)的数据源。

对过去 N 个交易日的每一天 t,用"截至 t 的数据"重算当天的 h20 收益带(严格无前视):
复用 focus_cn.vol_scaled_prob(与实时概率带、cn_engine 完全同口径)→ 保证序列最后一点 == 详情页概率带表。
每个历史日的带只依赖 ≤t 的数据,故其值永久不变(明天重算结果一致,只会追加新日),因此现算即可、无需落库。

输出(单行 JSON):
  {"ticker","asof","points":[{"date","close","lo","hi","mid"}...]}
  lo/hi = 70%区间下/上沿(收益,如 -0.08/0.12);mid = 中位收益。价格锥由前端 close*(1+lo/hi/mid) 换算。
用法: python bandhist_cn.py sh.600000 [--asof latest] [--n 120]
"""
import os, sys, json, argparse
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from focus_cn import _load, vol_scaled_prob  # 同口径复用:_load 单票CSV(含断档保护)、vol_scaled_prob h20带


def band_series(code, asof, n=120):
    df, _ = _load(code, asof)
    if df is None:
        return None, None
    C = df["close"]
    idx = C.index
    L = len(C)
    if L < 120:
        return [], str(idx[-1].date())
    start = max(120, L - n)  # 需 ≥120 天才能算 vol_scaled_prob;取最后 n 天
    pts = []
    for t in range(start, L):
        sub = C.iloc[:t + 1]                 # 截至第 t 天(无前视:vol_scaled_prob 内部对末尾前瞻收益 dropna)
        p = vol_scaled_prob(sub)
        if not p:
            continue
        lo, hi = p["band70"]
        pts.append({
            "date": idx[t].strftime("%Y-%m-%d"),
            "close": round(float(sub.iloc[-1]), 2),
            "lo": lo, "hi": hi, "mid": p["median"],
        })
    return pts, str(idx[-1].date())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--asof", default="latest")
    ap.add_argument("--n", type=int, default=120)
    args = ap.parse_args()
    code = args.ticker.strip().lower()
    pts, asof = band_series(code, args.asof, max(20, min(args.n, 500)))
    if pts is None:
        print(json.dumps({"error": f"{code} 不在A股数据池"}, ensure_ascii=False))
        return
    print(json.dumps({"ticker": code, "asof": asof, "points": pts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
