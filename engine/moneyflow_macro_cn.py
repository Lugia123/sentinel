#!/usr/bin/env python3
"""A股【大盘 + 北向】资金流展示数据源(纯展示,不进策略)—— 资金流页顶部 + 策略信号首屏 ribbon。

  ① 北向资金 moneyflow_hsgt:north_money(沪股通+深股通净流入,万元→亿)——"聪明钱"。
  ② 大盘资金 moneyflow_mkt_dc:net_amount(两市主力净流入,元→亿)+ 沪/深涨跌%。
两接口均支持日期区间(各一次调用,快)。输出(单行 JSON):
  {"asof","north":[{date,north,south}...],"market":[{date,net,pct_sh,pct_sz}...],"summary":{...}}
  单位亿元。token死→{"error":...}。
用法: python moneyflow_macro_cn.py [--days 20]
"""
import os, sys, json, argparse
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ts_refresh import ts


def build(days=20):
    end = pd.Timestamp.today().strftime("%Y%m%d")
    start = (pd.Timestamp.today() - pd.Timedelta(days=days * 2 + 20)).strftime("%Y%m%d")

    hs = ts("moneyflow_hsgt", {"start_date": start, "end_date": end},
            "trade_date,hgt,sgt,north_money,south_money")
    mk = ts("moneyflow_mkt_dc", {"start_date": start, "end_date": end},
            "trade_date,close_sh,pct_change_sh,pct_change_sz,net_amount")
    if (hs is None or hs.empty) and (mk is None or mk.empty):
        return {"error": "大盘/北向资金流暂不可用"}

    north = []
    if hs is not None and not hs.empty:
        hs = hs.sort_values("trade_date")
        for _, r in hs.iterrows():
            def f(x):
                try:
                    return round(float(x) / 1e4, 2)   # 万元→亿
                except Exception:
                    return None
            north.append({"date": _fmt(r["trade_date"]), "north": f(r["north_money"]), "south": f(r["south_money"])})
        north = north[-days:]

    market = []
    if mk is not None and not mk.empty:
        for c in ("pct_change_sh", "pct_change_sz", "net_amount"):
            mk[c] = pd.to_numeric(mk[c], errors="coerce")
        mk = mk.sort_values("trade_date")
        for _, r in mk.iterrows():
            market.append({"date": _fmt(r["trade_date"]),
                           "net": None if pd.isna(r["net_amount"]) else round(float(r["net_amount"]) / 1e8, 2),  # 元→亿
                           "pct_sh": None if pd.isna(r["pct_change_sh"]) else round(float(r["pct_change_sh"]), 2),
                           "pct_sz": None if pd.isna(r["pct_change_sz"]) else round(float(r["pct_change_sz"]), 2)})
        market = market[-days:]

    def s5(rows, k):
        vals = [x[k] for x in rows[-5:] if x.get(k) is not None]
        return round(sum(vals), 2) if vals else None

    asof = (north[-1]["date"] if north else market[-1]["date"] if market else None)
    summary = {
        "north_today": north[-1]["north"] if north else None,
        "north_5d": s5(north, "north"),
        "market_today": market[-1]["net"] if market else None,
        "market_5d": s5(market, "net"),
        "pct_sh": market[-1]["pct_sh"] if market else None,
    }
    return {"asof": asof, "north": north, "market": market, "summary": summary}


def _fmt(d):
    d = str(d)
    return f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=20)
    args = ap.parse_args()
    print(json.dumps(build(max(5, min(args.days, 60))), ensure_ascii=False))


if __name__ == "__main__":
    main()
