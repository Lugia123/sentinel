#!/usr/bin/env python3
"""A股【板块资金 · 历史矩阵】—— 资金流页板块分析卡的历史/累计/RRG 三视图共用数据源(纯展示)。

逐日循环 tushare moneyflow_ind_dc(content_type='行业'),构建「日期 × 行业」主力净流入矩阵(元→亿)+ 逐行业累计。
返回**全部行业**(热力图全展示;累计线/RRG 由前端取 top)。按最终累计降序。
输出(单行 JSON):
  {"asof","dates":[...],"industries":[{name, net:[逐日], cum:[逐日累计]}...]}
  net/cum 单位亿元;某行业某日缺失记 0。token死→{"error":...}。
用法: python moneyflow_sector_history_cn.py [--days 60]
"""
import os, sys, json, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ts_refresh import trade_dates
from moneyflow_sector_cn import pull_day   # 同口径:content_type='行业',数值已转 float


def build(days=60):
    cal = trade_dates("20260101")
    if not cal:
        return {"error": "取不到交易日历(检查凭证)"}
    # 从最新往回收集有数据的交易日(当日盘中未出则跳过),最多 days 个
    collected = []  # (dt, df) 新→旧
    for dt in reversed(cal[-(days + 15):]):
        d = pull_day(dt)
        if d is not None and not d.empty:
            collected.append((dt, d))
        if len(collected) >= days:
            break
    if not collected:
        return {"error": "行业资金流暂不可用"}
    collected.reverse()  # 旧→新
    n = len(collected)
    dates = [f"{dt[:4]}-{dt[4:6]}-{dt[6:]}" for dt, _ in collected]

    sect = {}  # name -> [逐日净额(亿)]
    for di, (_, df) in enumerate(collected):
        for _, r in df.iterrows():
            nm = r["name"]
            if nm not in sect:
                sect[nm] = [0.0] * n
            v = r["net_amount"]
            sect[nm][di] = round(float(v) / 1e8, 2) if v == v else 0.0  # NaN→0

    out = []
    for nm, nets in sect.items():
        cum, c = [], 0.0
        for v in nets:
            c += (v or 0.0)
            cum.append(round(c, 2))
        out.append({"name": nm, "net": nets, "cum": cum})
    out.sort(key=lambda o: o["cum"][-1], reverse=True)
    return {"asof": dates[-1], "dates": dates, "industries": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    args = ap.parse_args()
    print(json.dumps(build(max(10, min(args.days, 90))), ensure_ascii=False))


if __name__ == "__main__":
    main()
