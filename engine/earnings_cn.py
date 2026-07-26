#!/usr/bin/env python3
"""
earnings_cn.py — A股季度财报关键数(营收/净利/营业利润/毛利/EPS),输出与 earnings.py 同构 JSON。
数据源:新浪财经利润表(akshare stock_financial_report_sina,免费)。
注意:A股财报为【年内累计值】,本脚本差分成【单季值】再输出(Q1 原值;Q2=半年报-Q1;依此类推)。
用法:python earnings_cn.py sh.600000   → {"ticker":..., "quarters":[近8个单季,新→旧]}
"""
import sys, json


def _num(v):
    try:
        f = float(v)
        return f if f == f else None  # NaN → None
    except (TypeError, ValueError):
        return None


def pick(row, *names):
    for nm in names:
        if nm in row:
            v = _num(row[nm])
            if v is not None:
                return v
    return None


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "用法: earnings_cn.py sh.600000"}, ensure_ascii=False))
        return
    code = sys.argv[1].strip().lower()          # sh.600000
    sina = code.replace(".", "")                # sh600000
    try:
        import akshare as ak
        df = ak.stock_financial_report_sina(stock=sina, symbol="利润表")
    except Exception as e:
        print(json.dumps({"error": f"拉取A股财报失败: {type(e).__name__} {str(e)[:80]}"}, ensure_ascii=False))
        return
    if df is None or len(df) == 0 or "报告日" not in df.columns:
        print(json.dumps({"error": f"{code} 无财报数据"}, ensure_ascii=False))
        return

    # 累计值按报告日升序排,便于年内差分
    df = df.sort_values("报告日").reset_index(drop=True)
    cum = []
    for _, r in df.iterrows():
        d = str(r["报告日"])  # YYYYMMDD
        if len(d) != 8:
            continue
        cum.append(dict(
            ymd=d, year=d[:4], month=d[4:6],
            revenue=pick(r, "营业总收入", "营业收入"),
            net_income=pick(r, "归属于母公司所有者的净利润", "净利润"),
            operating_income=pick(r, "营业利润"),
            cost=pick(r, "营业总成本"),
            eps=pick(r, "基本每股收益"),
        ))
    # 差分:同年内减去上一报告期累计
    sub = lambda a, b: (a - b) if (a is not None and b is not None) else (a if b is None else None)
    quarters = []
    prev = None
    for q in cum:
        if prev is not None and prev["year"] == q["year"]:
            single = {k: sub(q[k], prev[k]) for k in ("revenue", "net_income", "operating_income", "cost", "eps")}
        else:  # Q1(或该年首个报告期)直接用累计值
            single = {k: q[k] for k in ("revenue", "net_income", "operating_income", "cost", "eps")}
        gp = None
        if single["revenue"] is not None and single["cost"] is not None:
            gp = single["revenue"] - single["cost"]
        quarters.append(dict(
            period=f"{q['year']}-{q['month']}-{q['ymd'][6:]}",
            revenue=single["revenue"], net_income=single["net_income"],
            operating_income=single["operating_income"], gross_profit=gp,
            eps=round(single["eps"], 4) if single["eps"] is not None else None,
        ))
        prev = q
    quarters = quarters[::-1][:8]  # 新→旧,近8季
    print(json.dumps({"ticker": code, "quarters": quarters}, ensure_ascii=False))


if __name__ == "__main__":
    main()
