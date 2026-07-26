#!/usr/bin/env python3
"""下载业绩预告(全市场,按报告期)→ data/alt/yjyg.parquet。用于 PEAD/盈利惊喜。
stock_yjyg_em(date=报告期) 返回该季全市场预告,含【公告日期】(PIT 披露日)+【业绩变动幅度】(惊喜代理)。
survivorship LOW:按报告期拉,含当时已退市股。用法:python lib/dl_yjyg.py"""
import os, sys, time
import akshare as ak, pandas as pd, warnings
warnings.filterwarnings("ignore")
DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
OUT = os.path.join(DATA_DIR, "alt"); os.makedirs(OUT, exist_ok=True)

def periods(y0=2008, y1=2026):
    ps = []
    for y in range(y0, y1 + 1):
        for q in ("0331", "0630", "0930", "1231"):
            ps.append(f"{y}{q}")
    return ps

def main():
    rows = []
    for p in periods():
        for attempt in range(3):
            try:
                df = ak.stock_yjyg_em(date=p)
                if df is not None and len(df):
                    df = df.copy(); df["报告期"] = p
                    rows.append(df)
                print(f"{p}: {0 if df is None else len(df)}", flush=True)
                break
            except Exception as e:
                print(f"{p}: retry{attempt} {type(e).__name__}", flush=True)
                time.sleep(2)
    if not rows:
        print("NO DATA"); return
    all_df = pd.concat(rows, ignore_index=True)
    # 精简列
    keep = ["股票代码", "预测指标", "业绩变动幅度", "预告类型", "预测数值", "上年同期值", "公告日期", "报告期"]
    keep = [c for c in keep if c in all_df.columns]
    all_df = all_df[keep]
    fp = os.path.join(OUT, "yjyg.parquet")
    all_df.to_parquet(fp, index=False)
    print(f"\nSAVED {fp}  rows={len(all_df)}  最早公告={all_df['公告日期'].min()}  最晚={all_df['公告日期'].max()}")

if __name__ == "__main__":
    main()
