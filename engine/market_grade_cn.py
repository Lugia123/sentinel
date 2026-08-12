#!/usr/bin/env python3
"""A股【全市场档位表】—— 建议持仓列表「板块」tab 的数据源(纯展示,不进策略)。

给**全市场每一只**活跃股都算:
  行业(申万一级) · 基础行情(现价/涨跌%/换手/成交额/ST) · 趋势档位 · 未来20日概率区间。
档位/区间复用 cn_engine 的 trend_grade_cn / vol_scaled_prob(与推荐列表同口径)。

内存友好:**逐股流式**——每只读自己的日频 CSV、算完只留标量结果、丢弃序列,峰值内存仅几十 MB
(不建全市场大矩阵;生产 4GB 无 swap 机上与快照并发也不会 OOM)。无 LLM/API/token。

与 /api/snapshot(推荐~120,逐用户个性化)分离:本表全用户共享、缓存,前端做 filter/排序/搜索/分页。
输出(单行 JSON):
  {"asof","count","stocks":[{code,name,sector,price,pct,turn,amount,st,grade,gl,h20{median,lo,hi}}...]}
  amount 单位亿元;h20 缺失(数据不足)记 null;停牌/退市久(距最新>10日)剔除。取不到数据→{"error":...}。
用法: python market_grade_cn.py
"""
import os, sys, json, glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pandas as pd
from cn_engine import E, vol_scaled_prob, trend_grade_cn, _names
from sw_members_cn import code_to_l1   # 统一:tushare 申万成分(替代 akshare 静态 sw_industry.csv)

START = "2021-01-01"      # 与快照同窗口(足够 vol_scaled_prob 的 500 日经验分布)
MIN_DAYS = 250            # 与 load_matrices 同门槛:窗口内不足 250 日的剔除
USECOLS = ["date", "close", "turn", "amount", "pctChg", "isST"]


def _last_num(df, col, nd=2):
    """df[col] 最后一个有效数值(round nd),无则 None。"""
    try:
        v = pd.to_numeric(df[col], errors="coerce").dropna()
        return round(float(v.iloc[-1]), nd) if len(v) else None
    except Exception:
        return None


def build():
    files = sorted(glob.glob(os.path.join(E.DAILY, "*.csv")))
    if not files:
        return {"error": "取不到日频数据目录(检查 data_cn 软链)"}
    names = _names()
    sect = code_to_l1()   # 统一 tushare 申万一级(缓存7天,失败回退静态)
    start_ts = pd.Timestamp(START)

    rows = []
    for f in files:
        code = os.path.basename(f)[:-4].replace("_", ".", 1)
        try:
            df = pd.read_csv(f, usecols=lambda c: c in USECOLS)
        except Exception:
            continue
        if len(df) < MIN_DAYS:
            continue
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"] >= start_ts]
        if len(df) < MIN_DAYS:
            continue
        df = df.set_index("date")
        close = df["close"].astype(float)
        if close.dropna().empty:
            continue
        last_dt = close.index[-1]
        price = float(close.dropna().iloc[-1])
        M = {"close": pd.DataFrame({code: close})}   # 单股迷你 M,复用同口径 grade/prob
        try:
            g = trend_grade_cn(M, code, None)
            grade, gl = int(g[0]), str(g[1])
        except Exception:
            grade, gl = 0, "—"
        h20 = None
        try:
            p = vol_scaled_prob(M, code, None)
            if p:
                b = p["band70"]
                h20 = {"median": p["median"], "lo": b[0], "hi": b[1]}
        except Exception:
            pass
        st_v = _last_num(df, "isST", 0)
        amt = _last_num(df, "amount", 2)
        rows.append({
            "code": code,
            "name": names.get(code, ""),
            "sector": sect.get(code, "其他"),
            "price": round(price, 2),
            "pct": _last_num(df, "pctChg", 2),
            "turn": _last_num(df, "turn", 2),
            "amount": round(amt / 1e8, 2) if amt is not None else None,   # 成交额(亿)
            "st": bool(st_v) if st_v is not None else False,
            "grade": grade,
            "gl": gl,
            "h20": h20,
            "_dt": last_dt,
        })
    if not rows:
        return {"error": "全市场档位暂不可用"}
    asof_ts = max(r["_dt"] for r in rows)
    out = []
    for r in rows:
        if (asof_ts - r["_dt"]).days <= 10:   # 停牌/退市久的(距市场最新>10日)剔除
            r.pop("_dt")
            out.append(r)
    # 默认按档位高→低、再成交额高→低(前端会按 tab 再排:推荐置顶)
    out.sort(key=lambda x: (-x["grade"], -(x["amount"] or 0)))
    return {"asof": str(asof_ts.date()), "count": len(out), "stocks": out}


def main():
    print(json.dumps(build(), ensure_ascii=False))


if __name__ == "__main__":
    main()
