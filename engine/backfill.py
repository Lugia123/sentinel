#!/usr/bin/env python3
"""
backfill.py — 历史回填:装一次数据,循环每个交易日算快照,直连 PG 入库。
省掉 run_daily 每次重装 1393 CSV+fp 的固定成本(单次24s→回填边际远小)。
upsert SQL 镜像 server/internal/store/store.go(schema 稳定,可接受少量重复)。

用法:cd engine && uv run python backfill.py --from 2026-01-01 [--to latest] [--no-sy]
"""
import sys, os, re, time, json, argparse, asyncio
import pandas as pd
import asyncpg
import run_daily as R

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server", ".env")


def parse_dsn():
    """读 server/.env 的 SENTINEL_DB_DSN(libpq keyword 格式)→ asyncpg 连接参数。"""
    dsn = ""
    with open(ENV) as f:
        for line in f:
            if line.startswith("SENTINEL_DB_DSN="):
                dsn = line.split("=", 1)[1].strip()
    kv = dict(re.findall(r"(\w+)=(\S+)", dsn))
    return dict(host=kv.get("host", "localhost"), port=int(kv.get("port", 5432)),
                user=kv.get("user"), password=kv.get("password"), database=kv.get("dbname"))


async def ingest(conn, snap, prices, asof):
    raw = json.dumps(snap, ensure_ascii=False)
    rl, pf = snap["risk_light"], snap["portfolio"]
    sid = await conn.fetchval("""
        INSERT INTO snapshots(asof,generated_at,capital,risk_level,spy_vol,exposure,gross_exposure,cash_pct,raw)
        VALUES ($1,now(),$2,$3,$4,$5,$6,$7,$8::jsonb)
        ON CONFLICT (asof) DO UPDATE SET generated_at=now(),capital=EXCLUDED.capital,risk_level=EXCLUDED.risk_level,
          spy_vol=EXCLUDED.spy_vol,exposure=EXCLUDED.exposure,gross_exposure=EXCLUDED.gross_exposure,
          cash_pct=EXCLUDED.cash_pct,raw=EXCLUDED.raw RETURNING id
    """, asof, snap["capital"], rl["level"], rl["spy_vol"], rl["exposure"], pf["gross_exposure"], pf["cash_pct"], raw)
    await conn.execute("DELETE FROM holdings WHERE snapshot_id=$1", sid)
    await conn.executemany("""
        INSERT INTO holdings(snapshot_id,ticker,sleeve,price,base_weight,target_shares,target_value,grade,action,prob)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)
    """, [(sid, h["ticker"], h["sleeve"], h["price"], h["base_weight"], h["target_shares"],
           h["target_value"], h["grade"], h["action"], json.dumps(h.get("prob", {}))) for h in snap["holdings"]])
    await conn.executemany("INSERT INTO prices(ticker,date,close) VALUES ($1,$2,$3) ON CONFLICT (ticker,date) DO UPDATE SET close=EXCLUDED.close",
                           [(tk, asof, c) for tk, c in prices["prices"].items()])


async def run(args):
    print("装载数据(一次)...", flush=True)
    t0 = time.time()
    # 回填保留 [起点-400天, 最新] 的历史(400天≈252交易日回看,够算sma200/52周高),省内存
    uni, spy, master, fp = R.load_all(with_sy=not args.no_sy,
                                      min_date=pd.Timestamp(args.frm) - pd.Timedelta(days=400))
    print(f"装载 {time.time()-t0:.1f}s", flush=True)

    a0 = next(iter(uni.values()))
    all_dates = [d for d in pd.to_datetime(a0["date"]).tolist()]
    frm = pd.Timestamp(args.frm)
    to = all_dates[-1] if args.to == "latest" else pd.Timestamp(args.to)
    dates = [d for d in all_dates if frm <= d <= to]
    print(f"回填 {len(dates)} 个交易日:{dates[0].date()} → {dates[-1].date()}", flush=True)

    conn = await asyncpg.connect(**parse_dsn())
    try:
        done = 0; t1 = time.time()
        for d in dates:
            snap, prices = R.compute_snapshot(uni, spy, master, fp, d, args.capital, with_sy=not args.no_sy)
            await ingest(conn, snap, prices, d.date())
            done += 1
            if done % 10 == 0 or done == len(dates):
                el = time.time() - t1
                print(f"  {done}/{len(dates)} | 边际 {el/done:.1f}s/日 | 已 {el:.0f}s | 预计剩 {el/done*(len(dates)-done):.0f}s", flush=True)
    finally:
        await conn.close()
    print(f"回填完成 {len(dates)} 日,总 {time.time()-t1:.0f}s(不含装载)", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", required=True, help="起点 YYYY-MM-DD")
    ap.add_argument("--to", default="latest")
    ap.add_argument("--capital", type=float, default=4000.0)
    ap.add_argument("--no-sy", action="store_true")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
