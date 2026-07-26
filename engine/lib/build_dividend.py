#!/usr/bin/env python3
"""把 data/div/ 每股分红 CSV → data/alt/div_events.parquet(紧凑事件表,供生产红利低波腿)。
现金分红-现金分红比例 = 每10股派X元 → 每股 X/10。PIT 用【最新公告日期】(防前视)。
用法:python lib/build_dividend.py
"""
import os, glob
import pandas as pd

DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
DIV = os.path.join(DATA_DIR, "div")
OUT = os.path.join(DATA_DIR, "alt", "div_events.parquet")


def main():
    rows = []
    for f in glob.glob(os.path.join(DIV, "*.csv")):
        b = os.path.basename(f)[:-4]                      # sh_600000
        if "_" not in b:
            continue
        mk, num = b.split("_", 1)
        code = f"{mk}.{num}"
        try:
            d = pd.read_csv(f)
        except Exception:
            continue
        if d.empty or "最新公告日期" not in d.columns:
            continue
        r10 = pd.to_numeric(d.get("现金分红-现金分红比例"), errors="coerce")   # 每10股派元
        ann = pd.to_datetime(d["最新公告日期"], errors="coerce")
        g = pd.DataFrame({"code": code, "ann_date": ann, "dps": r10 / 10.0}).dropna(subset=["ann_date"])
        g = g[g["dps"].fillna(0) > 0]                     # 只留真实派现
        rows.append(g)
    df = pd.concat(rows, ignore_index=True)
    df.to_parquet(OUT)
    print(f"完成:{OUT} | {df['code'].nunique()} 只 × {len(df)} 派现事件 | {df['ann_date'].min().date()}~{df['ann_date'].max().date()}", flush=True)


if __name__ == "__main__":
    main()
