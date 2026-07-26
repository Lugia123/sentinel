#!/usr/bin/env python3
"""R0 数据管道:baostock 批量下全A股+退市股日线(survivorship-free)。
字段:date,open,high,low,close,preclose,volume,amount,turn(换手率),tradestatus(停牌),pctChg,isST。
后复权(adjustflag=2)。可续跑(跳过已存)。存 data/daily/{code}.csv。

⚠️ baostock 长会话坑:跑约 120 次查询后 session 会静默失效(error_code 仍=0 但返回空)。
   → 每 RELOGIN_EVERY 只主动重登;遇空再重登重试一次,仍空才判真空(退市早/无数据)。"""
import baostock as bs, pandas as pd, os, time, sys, socket
socket.setdefaulttimeout(30)   # ⚠️ baostock 无内置超时,死连接会无限挂起 → 全局 30s 超时,死读快速失败触发重试
DATA_DIR=os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
OUTD=os.path.join(DATA_DIR, "daily"); os.makedirs(OUTD, exist_ok=True)
FIELDS="date,open,high,low,close,preclose,volume,amount,turn,tradestatus,pctChg,isST"
START="2005-01-01"
RELOGIN_EVERY=80          # 每 80 次成功查询主动重登,避开掉线阈值
uni=pd.read_csv(os.path.join(DATA_DIR, "meta", "universe.csv"), dtype=str)
# 分片并行:argv = NSHARDS RESIDUE → 本进程只处理 行号%NSHARDS==RESIDUE 的股票
NSHARDS = int(sys.argv[1]) if len(sys.argv)>2 else 1
RESIDUE = int(sys.argv[2]) if len(sys.argv)>2 else 0
TAG = f"[{RESIDUE}/{NSHARDS}]"

def relogin():
    try: bs.logout()
    except Exception: pass
    for _ in range(5):
        r=bs.login()
        if r.error_code=='0': return True
        time.sleep(3)
    return False

def fetch(code, end):
    rs=bs.query_history_k_data_plus(code, FIELDS, start_date=START, end_date=end,
                                    frequency="d", adjustflag="2")
    rows=[]
    while (rs.error_code=='0') and rs.next(): rows.append(rs.get_row_data())
    return rows, rs.fields

relogin()
t0=time.time(); done=0; skip=0; empty=0; queries=0
n=len(uni)
for i,r in uni.iterrows():
    if i % NSHARDS != RESIDUE: continue        # 分片:只处理本进程负责的行
    code=r['code']; fn=f"{OUTD}/{code.replace('.','_')}.csv"
    if os.path.exists(fn): skip+=1; continue
    end=r['outDate'] if r['status']=='0' and pd.notna(r['outDate']) and r['outDate'] else "2026-07-06"
    # 定期主动重登
    if queries and queries % RELOGIN_EVERY == 0:
        relogin()
    try:
        rows, fields = fetch(code, end)
        if not rows:                 # 可能是掉线 → 重登重试一次
            relogin()
            rows, fields = fetch(code, end)
        if rows:
            pd.DataFrame(rows, columns=fields).to_csv(fn, index=False); done+=1
        else:
            empty+=1
    except Exception:
        relogin(); empty+=1
    queries+=1
    if done and done%50==0:
        el=time.time()-t0
        print(f"  {TAG} {i+1}/{n} | 新下{done} 跳过{skip} 空{empty} | {el:.0f}s", flush=True)
try: bs.logout()
except Exception: pass
print(f"完成{TAG}:新下{done} 跳过{skip} 空{empty},总{time.time()-t0:.0f}s", flush=True)
