#!/usr/bin/env python3
"""A股【板块资金热力】展示数据源(纯展示,不进策略)—— 资金流页「板块」区。

tushare moneyflow_ind_dc(东财行业板块资金流,content_type='行业',~86个):
  今日各行业主力净流入(元→亿)、板块涨跌%、净额占比、代表股;并累计近5日主力净流入(重累计原则)。
输出(单行 JSON):
  {"asof","industries":[{name,net,net5,pct,rate,lead}...] 按今日 net 降序}
  net/net5 单位亿元。前端:今日排行(net) + 持续吸金榜(net5) + 全景 treemap。token死→{"error":...}。
用法: python moneyflow_sector_cn.py [--days 5]
"""
import os, sys, json, argparse
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ts_refresh import ts, trade_dates
from sw_levels import name_to_level


def _amount_yi(net_yi, rate):
    """成交额(盘子总额,亿)= 主力净额 / 主力净额占比。rate=占成交额百分比。"""
    try:
        if rate and abs(rate) > 1e-6:
            return round(net_yi / (rate / 100.0), 0)
    except Exception:
        pass
    return None


def pull_day(dt):
    df = ts("moneyflow_ind_dc", {"trade_date": dt},
            "trade_date,content_type,name,pct_change,net_amount,net_amount_rate,buy_sm_amount_stock")
    if df is None or df.empty:
        return None
    df = df[df["content_type"] == "行业"].copy()
    for c in ("pct_change", "net_amount", "net_amount_rate"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def build(days=5):
    dates = trade_dates("20260101")
    if not dates:
        return {"error": "取不到交易日历(检查凭证)"}
    # 从最新交易日往回找有数据的日(当日数据可能盘中未出),收集最近 days 个有效日
    collected = []  # (dt, df) 新→旧
    for dt in reversed(dates[-15:]):
        d = pull_day(dt)
        if d is not None and not d.empty:
            collected.append((dt, d))
        if len(collected) >= days:
            break
    if not collected:
        return {"error": "行业资金流暂不可用"}
    today, dtoday = collected[0]

    # 近 N 日累计主力净流入(按行业名求和)
    cum = {}
    for _, d in collected:
        for _, r in d.iterrows():
            cum[r["name"]] = cum.get(r["name"], 0.0) + (r["net_amount"] or 0.0)

    lv = name_to_level()  # 行业名 → 申万层级(1/2/3);未命中默认 3(细分)
    out = []
    for _, r in dtoday.iterrows():
        nm = r["name"]
        net = round(float(r["net_amount"] or 0.0) / 1e8, 2)
        rate = None if pd.isna(r["net_amount_rate"]) else round(float(r["net_amount_rate"]), 2)
        out.append({
            "name": nm,
            "level": lv.get(nm, 3),                                       # 层级
            "net": net,                                                   # 今日主力净流入(亿)
            "net5": round(float(cum.get(nm, 0.0)) / 1e8, 2),             # 近N日累计(亿)
            "pct": None if pd.isna(r["pct_change"]) else round(float(r["pct_change"]), 2),
            "rate": rate,                                                 # 主力净额占成交额%
            "amount": _amount_yi(net, rate),                             # 成交额(盘子总额,亿)
            "lead": str(r.get("buy_sm_amount_stock") or "").strip(),
        })
    out.sort(key=lambda x: x["net"], reverse=True)
    asof = f"{today[:4]}-{today[4:6]}-{today[6:]}"
    return {"asof": asof, "days": len(collected), "industries": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=5)
    args = ap.parse_args()
    print(json.dumps(build(max(1, min(args.days, 20))), ensure_ascii=False))


if __name__ == "__main__":
    main()
