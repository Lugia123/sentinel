#!/usr/bin/env python3
"""A股个股【资金流 · 量能】展示卡数据源(纯展示,不进任何策略/档位/风险灯)。

两条腿合成:
  ① 资金流(额度)← tushare moneyflow:主力(大+特大单)/散户(中+小单)净流入、四单结构、全单净额。万元→亿。
  ② 量能(volume)← data_cn CSV(不用tushare):量比(量/20日均量)、换手、涨跌%、量价配合。
输出(单行 JSON):
  {"ticker","asof","summary":{...},"points":[{date,main,retail,net,elg,lg,md,sm,vol_ratio,turn,pct,close}...]}
  单位亿元(主力=超大+大净;散户=中+小净;net=全单净额)。token死→{"error":...}前端优雅降级(量能仍可另算)。
用法: python moneyflow_cn.py sh.600000 [--days 40]
"""
import os, sys, json, argparse
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from focus_cn import _load          # 单票CSV(含断档保护),index=date
from ts_refresh import ts           # tushare 调用(带重试;读 SENTINEL_TS_URL/TOKEN)


def _tscode(code):
    """sh.600000 → 600000.SH(tushare 口径)。"""
    if "." in code:
        mk, num = code.split(".")
        return f"{num}.{mk.upper()}"
    return code


def _state(pct, vr, main5):
    """量价配合 + 资金合成的一句话状态标签 + 色调(in/out/flat)。"""
    heavy = vr >= 1.2 if np.isfinite(vr) else False
    light = vr <= 0.8 if np.isfinite(vr) else False
    vp = ("放量" if heavy else "缩量" if light else "平量") + ("上涨" if pct > 0 else "下跌" if pct < 0 else "横盘")
    if main5 > 0 and heavy and pct > 0:
        return vp + " · 主力进场", "in"
    if main5 < 0 and heavy and pct > 0:
        return vp + " · 主力流出(价涨钱撤,谨慎)", "out"
    if main5 < 0:
        return vp + " · 主力流出", "out"
    if main5 > 0:
        return vp + " · 主力净流入", "in"
    return vp + " · 资金观望", "flat"


def _consec(vals):
    """今日起往前,主力净额同号连续天数:正=连续流入N日,负=连续流出N日。"""
    xs = [v for v in vals if v is not None]
    if not xs:
        return 0
    sign = 1 if xs[-1] > 0 else -1 if xs[-1] < 0 else 0
    if sign == 0:
        return 0
    n = 0
    for v in reversed(xs):
        if (v > 0 and sign > 0) or (v < 0 and sign < 0):
            n += 1
        else:
            break
    return n * sign


def series(code, days=40):
    df, _ = _load(code, "latest")
    if df is None:
        return {"error": f"{code} 不在A股数据池"}
    C = df.copy()
    vol = pd.to_numeric(C.get("volume"), errors="coerce")
    vr = vol / vol.rolling(20).mean()
    turn = pd.to_numeric(C.get("turn"), errors="coerce")
    pct = pd.to_numeric(C.get("pctChg"), errors="coerce")
    close = pd.to_numeric(C.get("close"), errors="coerce")
    tail = C.tail(days).index
    if len(tail) == 0:
        return {"error": f"{code} 无行情"}
    d0, d1 = tail[0].strftime("%Y%m%d"), tail[-1].strftime("%Y%m%d")

    # 资金流:tushare moneyflow(区间一次拉回)
    mf = ts("moneyflow", {"ts_code": _tscode(code), "start_date": d0, "end_date": d1},
            "trade_date,buy_lg_amount,sell_lg_amount,buy_elg_amount,sell_elg_amount,"
            "buy_md_amount,sell_md_amount,buy_sm_amount,sell_sm_amount,net_mf_amount")
    mfmap = {}
    if mf is not None and len(mf):
        for c in mf.columns:
            if c != "trade_date":
                mf[c] = pd.to_numeric(mf[c], errors="coerce")
        for _, r in mf.iterrows():
            elg = (r["buy_elg_amount"] - r["sell_elg_amount"]) / 1e4     # 特大单净额(亿)
            lg = (r["buy_lg_amount"] - r["sell_lg_amount"]) / 1e4        # 大单
            md = (r["buy_md_amount"] - r["sell_md_amount"]) / 1e4        # 中单
            sm = (r["buy_sm_amount"] - r["sell_sm_amount"]) / 1e4        # 小单
            mfmap[str(r["trade_date"])] = dict(
                elg=elg, lg=lg, md=md, sm=sm,
                main=elg + lg, retail=md + sm, net=r["net_mf_amount"] / 1e4)

    def rnd(x):
        return None if x is None or not np.isfinite(x) else round(float(x), 4)

    def v2(sr, i):
        return None if not np.isfinite(sr.get(i, np.nan)) else round(float(sr[i]), 2)

    pts = []
    for ti in tail:
        key = ti.strftime("%Y%m%d")
        m = mfmap.get(key)
        pts.append({
            "date": ti.strftime("%Y-%m-%d"),
            "main": rnd(m["main"]) if m else None, "retail": rnd(m["retail"]) if m else None,
            "net": rnd(m["net"]) if m else None,
            "elg": rnd(m["elg"]) if m else None, "lg": rnd(m["lg"]) if m else None,
            "md": rnd(m["md"]) if m else None, "sm": rnd(m["sm"]) if m else None,
            "vol_ratio": v2(vr, ti), "turn": v2(turn, ti), "pct": v2(pct, ti),
            "close": v2(close, ti),
        })

    def sumn(k, n):
        vals = [p[k] for p in pts[-n:] if p[k] is not None]
        return round(sum(vals), 4) if vals else None

    last = pts[-1]
    main5 = sumn("main", 5) or 0.0
    has_mf = any(p["main"] is not None for p in pts)
    state, tone = _state(last["pct"] or 0.0, last["vol_ratio"] if last["vol_ratio"] is not None else np.nan, main5)

    # 背离:近5日价格趋势 vs 主力5日净额
    closes5 = [p["close"] for p in pts[-6:] if p["close"] is not None]
    divergence = ""
    if len(closes5) >= 2 and has_mf:
        p_up = closes5[-1] > closes5[0]
        if p_up and main5 < 0:
            divergence = "top"       # 价升钱出:顶背离
        elif (not p_up) and main5 > 0:
            divergence = "bottom"    # 价跌钱进:或吸筹

    summary = {
        "main_5d": sumn("main", 5), "main_20d": sumn("main", 20), "retail_5d": sumn("retail", 5),
        "consec": _consec([p["main"] for p in pts]),
        "vol_ratio": last["vol_ratio"], "turn": last["turn"], "pct": last["pct"],
        "buckets_today": {k: last[k] for k in ("elg", "lg", "md", "sm")},
        "state": state, "tone": tone, "divergence": divergence, "has_moneyflow": has_mf,
    }
    return {"ticker": code, "asof": last["date"], "summary": summary, "points": pts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--days", type=int, default=40)
    args = ap.parse_args()
    code = args.ticker.strip().lower()
    out = series(code, max(10, min(args.days, 120)))
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
