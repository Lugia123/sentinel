#!/usr/bin/env python3
"""
earnings.py — 从 SEC EDGAR 拉某股季度财报关键数(营收/净利/营业利润/毛利/EPS),
供财报解读页(用户选季度 → AI 解读)。输出 JSON 到 stdout。

用法:uv run python earnings.py TICKER          → 列出近8个季度关键财务(JSON)
数据源:SEC data.sec.gov companyconcept API(免费,需 UA 带联系邮箱)。
"""
import sys, os, json, argparse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data_cache")
os.makedirs(CACHE, exist_ok=True)
UA = {"User-Agent": "sentinel research lugia123@me.com"}
REV = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"]


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=25))


def cik_of(ticker):
    p = os.path.join(CACHE, "cik_map.json")
    if not os.path.exists(p):
        data = _get("https://www.sec.gov/files/company_tickers.json")
        m = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in data.values()}
        json.dump(m, open(p, "w"))
    m = json.load(open(p))
    return m.get(ticker.upper())


def quarterly(cik, names):
    """取季度值(form 10-Q/10-K,期间≈3个月)→ {end: val}。多候选概念名取第一个有数据的。"""
    for nm in names:
        try:
            d = _get(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{nm}.json")
        except Exception:
            continue
        out = {}
        for x in d.get("units", {}).get("USD", []) + d.get("units", {}).get("USD/shares", []):
            if x.get("form") not in ("10-Q", "10-K"):
                continue
            s, e = x.get("start"), x.get("end")
            if not s or not e:
                continue
            days = (_d(e) - _d(s))
            if 80 <= days <= 100:  # 季度
                out[e] = x["val"]
        if out:
            return out
    return {}


def _d(s):
    from datetime import date
    y, m, dd = map(int, s.split("-"))
    return date(y, m, dd).toordinal()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    args = ap.parse_args()
    tk = args.ticker.upper()
    cik = cik_of(tk)
    if not cik:
        print(json.dumps({"error": f"{tk} 找不到 SEC CIK(可能非美股或代码不符)"}, ensure_ascii=False))
        return
    rev = quarterly(cik, REV)
    ni = quarterly(cik, ["NetIncomeLoss"])
    oi = quarterly(cik, ["OperatingIncomeLoss"])
    gp = quarterly(cik, ["GrossProfit"])
    eps = quarterly(cik, ["EarningsPerShareDiluted"])
    ends = sorted(set(rev) | set(ni) | set(oi), reverse=True)[:8]
    quarters = []
    for e in ends:
        quarters.append(dict(period=e, revenue=rev.get(e), net_income=ni.get(e),
                             operating_income=oi.get(e), gross_profit=gp.get(e), eps=eps.get(e)))
    print(json.dumps({"ticker": tk, "cik": cik, "quarters": quarters}, ensure_ascii=False))


if __name__ == "__main__":
    main()
