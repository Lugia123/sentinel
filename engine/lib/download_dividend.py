#!/usr/bin/env python3
"""R2b 数据:akshare 东财 stock_fhps_detail_em 下每股全部分红历史(一次调用/股)。
含 现金分红比例(每10股派X元) + 股息率 + 业绩披露日期(PIT,无前视关键)。存 data/div/{code}.csv。
东财反爬 → 重试+小延时+分片。用法:python lib/download_dividend.py NSHARDS RESIDUE"""
import akshare as ak, pandas as pd, os, time, sys
DATA_DIR=os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
OUTD=os.path.join(DATA_DIR, "div"); os.makedirs(OUTD, exist_ok=True)
uni=pd.read_csv(os.path.join(DATA_DIR, "meta", "universe.csv"), dtype=str)
NSHARDS=int(sys.argv[1]) if len(sys.argv)>2 else 1
RESIDUE=int(sys.argv[2]) if len(sys.argv)>2 else 0
TAG=f"[{RESIDUE}/{NSHARDS}]"
KEEP=["报告期","业绩披露日期","现金分红-现金分红比例","现金分红-股息率","除权除息日","最新公告日期"]

def fetch(sym):
    for _ in range(3):
        try:
            df=ak.stock_fhps_detail_em(symbol=sym)
            return df
        except Exception:
            time.sleep(1.5)
    return None

t0=time.time(); done=skip=empty=0; n=len(uni)
for i,r in uni.iterrows():
    if i%NSHARDS!=RESIDUE: continue
    code=r['code']; sym=code.split(".")[-1]; fn=f"{OUTD}/{code.replace('.','_')}.csv"
    if os.path.exists(fn): skip+=1; continue
    df=fetch(sym)
    if df is None or len(df)==0:
        empty+=1; pd.DataFrame(columns=KEEP).to_csv(fn,index=False)  # 占位防重下
    else:
        cols=[c for c in KEEP if c in df.columns]
        df[cols].to_csv(fn,index=False); done+=1
    time.sleep(0.15)
    if done and done%100==0:
        print(f"  {TAG} {i+1}/{n} | 新下{done} 跳过{skip} 空{empty} | {time.time()-t0:.0f}s", flush=True)
print(f"完成{TAG}:新下{done} 跳过{skip} 空{empty},总{time.time()-t0:.0f}s", flush=True)
