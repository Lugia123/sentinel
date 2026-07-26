#!/usr/bin/env python3
"""个股资金流(主力/超大单)tushare moneyflow 下载器 · 按交易日拉全市场(每日一次调用)。
token/url 从环境变量读(TS_TOKEN/TS_URL),不硬编码、不落配置文件。研究验证用。
用法:TS_TOKEN=... TS_URL=... python lib/dl_moneyflow_ts.py [start_date=20160101]
产出:data/alt/moneyflow_ts.parquet(long: date, code, main_net(主力净额万元), elg_net(超大单净额), lg_net(大单净额))
"""
import os, sys, glob, time
import pandas as pd, requests

DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
OUT = os.path.join(DATA_DIR, "alt", "moneyflow_ts.parquet")
PART = OUT + ".partial"
TOKEN = os.environ["TS_TOKEN"]; URL = os.environ["TS_URL"]
START = sys.argv[1] if len(sys.argv) > 1 else "20160101"

def trade_dates():
    """从本地一只长历史股的日线取交易日(>=START)。"""
    for cand in ("sh_600000.csv", "sz_000001.csv", "sh_600519.csv"):
        f = os.path.join(DATA_DIR, "daily", cand)
        if os.path.exists(f):
            d = pd.read_csv(f)
            ds = pd.to_datetime(d["date"]).dt.strftime("%Y%m%d")
            return sorted(ds[ds >= START].tolist())
    raise SystemExit("找不到日线取交易日")

def ts2code(ts):  # '002060.SZ' -> 'sz.002060'
    num, mk = ts.split(".")
    return f"{mk.lower()}.{num}"

def main():
    dates = trade_dates()
    print(f"交易日 {len(dates)} 天 ({dates[0]}~{dates[-1]}) → {OUT}", flush=True)
    done = set(); frames = []
    if os.path.exists(PART):
        old = pd.read_parquet(PART); done = set(old["date"].unique()); frames = [old]
        print(f"续跑:已有 {len(done)} 天", flush=True)
    sess = requests.Session()
    ok = fail = 0
    for i, dt in enumerate(dates):
        if dt in done:
            continue
        try:
            r = sess.post(URL, json={"api_name": "moneyflow", "token": TOKEN,
                "params": {"trade_date": dt},
                "fields": "ts_code,trade_date,net_mf_amount,buy_elg_amount,sell_elg_amount,buy_lg_amount,sell_lg_amount"},
                headers={"Accept-Encoding": "gzip"}, timeout=30)
            j = r.json()
            if j.get("code") != 0:
                fail += 1; time.sleep(1); continue
            d = j["data"]; cols = d["fields"]; items = d["items"]
            if not items:
                continue
            df = pd.DataFrame(items, columns=cols)
            g = pd.DataFrame({
                "date": pd.to_datetime(df["trade_date"]),
                "code": df["ts_code"].map(ts2code),
                "main_net": pd.to_numeric(df["net_mf_amount"], errors="coerce"),
                "elg_net": pd.to_numeric(df["buy_elg_amount"], errors="coerce") - pd.to_numeric(df["sell_elg_amount"], errors="coerce"),
                "lg_net": pd.to_numeric(df["buy_lg_amount"], errors="coerce") - pd.to_numeric(df["sell_lg_amount"], errors="coerce"),
            })
            frames.append(g); ok += 1
        except Exception:
            fail += 1; time.sleep(1)
        if (i + 1) % 100 == 0:
            pd.concat(frames, ignore_index=True).to_parquet(PART)
            print(f"  {i+1}/{len(dates)} | ok{ok} fail{fail}", flush=True)
        time.sleep(0.42)   # ~140/min < 150 限速
    all_df = pd.concat(frames, ignore_index=True)
    all_df.to_parquet(OUT)
    if os.path.exists(PART):
        os.remove(PART)
    print(f"完成:{all_df['code'].nunique()}只 × {all_df['date'].min().date()}~{all_df['date'].max().date()} | ok{ok} fail{fail}", flush=True)

if __name__ == "__main__":
    main()
