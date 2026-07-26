#!/usr/bin/env python3
"""通用 tushare 按【交易日】拉全市场数据下载器(囤本地,回测不依赖三方端点)。
token/url 从环境变量读(TS_TOKEN/TS_URL),不硬编码。断点续跑。
用法:TS_TOKEN=... TS_URL=... python lib/dl_tushare.py <api_name> <fields逗号分隔> <out_name> [start=20160101]
例:python lib/dl_tushare.py daily_basic ts_code,trade_date,turnover_rate_f,volume_ratio,pe_ttm,pb,total_mv,circ_mv daily_basic
产出:data/alt/<out_name>.parquet(long表,date列由trade_date转,code列由ts_code转 sh.600000 格式)
"""
import os, sys, glob, time
import pandas as pd, requests

DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
TOKEN = os.environ["TS_TOKEN"]; URL = os.environ["TS_URL"]
API = sys.argv[1]; FIELDS = sys.argv[2]; OUT_NAME = sys.argv[3]
START = sys.argv[4] if len(sys.argv) > 4 else "20160101"
OUT = os.path.join(DATA_DIR, "alt", f"{OUT_NAME}.parquet"); PART = OUT + ".partial"

def trade_dates():
    for cand in ("sh_600000.csv", "sz_000001.csv"):
        f = os.path.join(DATA_DIR, "daily", cand)
        if os.path.exists(f):
            ds = pd.to_datetime(pd.read_csv(f)["date"]).dt.strftime("%Y%m%d")
            return sorted(ds[ds >= START].tolist())
    raise SystemExit("找不到交易日")

def ts2code(ts):
    try:
        num, mk = ts.split("."); return f"{mk.lower()}.{num}"
    except Exception:
        return ts

def main():
    dates = trade_dates()
    print(f"[{API}] {len(dates)}天 {dates[0]}~{dates[-1]} → {OUT}", flush=True)
    done = set(); frames = []
    if os.path.exists(PART):
        old = pd.read_parquet(PART); done = set(old["_dt"].unique()) if "_dt" in old else set(old["date"].dt.strftime("%Y%m%d").unique()); frames = [old]
        print(f"续跑:已有 {len(done)} 天", flush=True)
    sess = requests.Session(); ok = fail = 0
    for i, dt in enumerate(dates):
        if dt in done:
            continue
        try:
            r = sess.post(URL, json={"api_name": API, "token": TOKEN, "params": {"trade_date": dt}, "fields": FIELDS},
                          headers={"Accept-Encoding": "gzip"}, timeout=30)
            j = r.json()
            if j.get("code") != 0:
                fail += 1; time.sleep(1); continue
            d = j["data"]
            if not d["items"]:
                continue
            df = pd.DataFrame(d["items"], columns=d["fields"])
            df["_dt"] = dt
            if "trade_date" in df: df["date"] = pd.to_datetime(df["trade_date"])
            if "ts_code" in df: df["code"] = df["ts_code"].map(ts2code)
            frames.append(df); ok += 1
        except Exception:
            fail += 1; time.sleep(1)
        if (i + 1) % 100 == 0:
            pd.concat(frames, ignore_index=True).to_parquet(PART)
            print(f"  {i+1}/{len(dates)} ok{ok} fail{fail}", flush=True)
        time.sleep(0.42)
    all_df = pd.concat(frames, ignore_index=True)
    all_df.to_parquet(OUT)
    if os.path.exists(PART): os.remove(PART)
    n = all_df["code"].nunique() if "code" in all_df else "?"
    print(f"[{API}] 完成:{n}只 × {all_df['_dt'].min()}~{all_df['_dt'].max()} ok{ok} fail{fail}", flush=True)

if __name__ == "__main__":
    main()
