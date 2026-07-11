#!/usr/bin/env python3
"""
refresh_data.py — 每日 EOD 数据增量刷新(供调度器每周期调用)
============================================================
检测本地最新日 vs 数据源最新交易日:已最新则秒退(skip),有新日才增量拉取并追加到 CSV。
  --market cn : A股 baostock 后复权(engine/data_cn → safna_jr_a/data/daily),格式
                date,open,high,low,close,preclose,volume,amount,turn,tradestatus,pctChg,isST
  --market us : 美股 yfinance(engine/data → safna_jr_a/round20/data_broad),格式
                date,open,high,low,close,volume
幂等:重复跑同一天 → 已最新 → skip。只追加严格晚于本地最新日的行。
用法:python refresh_data.py --market cn|us [--limit N] [--dry]
"""
import sys, os, glob, argparse, csv
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))


def _local_max_date(data_dir, probe="sh_600000.csv"):
    """本地最新日 = 探针股(或任一股)CSV 的最后一行日期。"""
    p = os.path.join(data_dir, probe)
    files = [p] if os.path.exists(p) else sorted(glob.glob(os.path.join(data_dir, "*.csv")))[:1]
    if not files:
        return None
    with open(files[0]) as f:
        last = None
        for row in csv.reader(f):
            if row and row[0][:2].isdigit():
                last = row[0]
    return last


def _last_date(fp):
    """高效读单只 CSV 最后一行日期(尾部 seek,避免读全文件)——per-file 断点续传/去重用。"""
    try:
        with open(fp, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 400))
            tail = f.read().decode(errors="ignore").splitlines()
        for l in reversed(tail):
            c = l.split(",", 1)[0]
            if len(c) >= 8 and c[:4].isdigit():
                return c
    except Exception:
        pass
    return None


# ────────────────────────── A股(baostock 后复权)──────────────────────────
def refresh_cn(data_dir, limit=None, dry=False):
    import baostock as bs
    lmax = _local_max_date(data_dir)
    if not lmax:
        print("cn: 本地无数据,需先全量下载(refresh 只做增量)"); return 1
    bs.login()
    # 探针取数据源最新交易日
    rs = bs.query_history_k_data_plus("sh.600000", "date", start_date=lmax, frequency="d", adjustflag="2")
    dates = []
    while rs.error_code == '0' and rs.next():
        dates.append(rs.get_row_data()[0])
    src_max = dates[-1] if dates else lmax
    files = sorted(glob.glob(os.path.join(data_dir, "*.csv")))
    if limit:
        files = files[:limit]
    # 落后超 ~20 日历天的按退市/长期停牌处理,不追(否则会拉全历史)
    cutoff = (datetime.strptime(lmax, "%Y-%m-%d") - timedelta(days=20)).strftime("%Y-%m-%d")
    # 不做基于单一探针的整体 skip:改为逐只 per-file 判断(已最新的秒过 continue),
    # 这样上次跑到一半被中断也能自愈续传(探针股已更新≠全体已更新)。
    print(f"cn: 探针{lmax} → 数据源{src_max}({len(files)}只,per-file 断点续传;各只已最新则跳过)", flush=True)
    updated = 0
    for i, fp in enumerate(files):
        flast = _last_date(fp)  # 该只自身最后日期(断点)
        if not flast or flast >= src_max or flast < cutoff:
            continue  # 已最新 / 退市停牌太久 → 跳过
        start_i = (datetime.strptime(flast, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        code = os.path.basename(fp)[:-4].replace("_", ".", 1)
        for attempt in range(2):
            try:
                rs = bs.query_history_k_data_plus(
                    code, "date,open,high,low,close,preclose,volume,amount,turn,tradestatus,pctChg,isST",
                    start_date=start_i, end_date=src_max, frequency="d", adjustflag="2")
                rows = []
                while rs.error_code == '0' and rs.next():
                    r = rs.get_row_data()
                    if r[0] > flast:  # 严格晚于该只最后日期(防重复)
                        rows.append(r)
                if rows and not dry:
                    with open(fp, "a", newline="") as f:
                        csv.writer(f).writerows(rows)
                if rows:
                    updated += 1
                break
            except Exception:
                bs.login()  # 会话失效重登重试
        if i % 80 == 79:
            bs.logout(); bs.login()  # 长会话防静默失效
        if i % 500 == 0:
            print(f"  {i}/{len(files)} 已更新{updated}只", flush=True)
    bs.logout()
    print(f"cn: {'DRY ' if dry else ''}done 更新{updated}只 → {src_max}")
    return 0


# ────────────────────────── 美股(yfinance)──────────────────────────
def refresh_us(data_dir, limit=None, dry=False):
    import yfinance as yf
    import pandas as pd
    lmax = _local_max_date(data_dir, probe="AAPL.csv")
    if not lmax:
        print("us: 本地无数据,需先全量下载"); return 1
    # 探针取最新交易日:多候选轮询(yfinance 对个别 ticker 偶发 delisted 误报,取第一个成功的)
    src_max = None
    for pb in ["AAPL", "MSFT", "SPY", "QQQ", "JPM"]:
        try:
            h = yf.Ticker(pb).history(period="7d")
            if not h.empty:
                src_max = h.index[-1].strftime("%Y-%m-%d"); break
        except Exception:
            continue
    if not src_max:
        print("us: yfinance 无响应(所有探针失败)"); return 1
    if src_max <= lmax:
        print(f"us: skip(已最新 {lmax})"); return 0
    start = (datetime.strptime(lmax, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    files = sorted(glob.glob(os.path.join(data_dir, "*.csv")))
    if limit:
        files = files[:limit]
    tickers = [os.path.basename(f)[:-4] for f in files]
    print(f"us: 本地{lmax} → 数据源{src_max},增量拉 {start}~({len(tickers)}只)", flush=True)
    updated = 0
    for i in range(0, len(tickers), 50):  # 分批批量下载
        batch = tickers[i:i + 50]
        try:
            df = yf.download(batch, start=start, auto_adjust=True, progress=False, group_by="ticker", threads=True)
        except Exception:
            continue
        for tk in batch:
            try:
                fp = os.path.join(data_dir, tk + ".csv")
                flast = _last_date(fp) or lmax  # 该只自身最后日期(per-file 去重,防部分更新后重复)
                sub = df[tk] if len(batch) > 1 else df
                sub = sub.dropna()
                rows = [[d.strftime("%Y-%m-%d"), round(r.Open, 4), round(r.High, 4), round(r.Low, 4),
                         round(r.Close, 4), int(r.Volume)] for d, r in sub.iterrows() if d.strftime("%Y-%m-%d") > flast]
                if rows and not dry:
                    with open(fp, "a", newline="") as f:
                        csv.writer(f).writerows(rows)
                if rows:
                    updated += 1
            except Exception:
                continue
        print(f"  {i+len(batch)}/{len(tickers)} 已更新{updated}只", flush=True)
    print(f"us: {'DRY ' if dry else ''}done 更新{updated}只 → {src_max}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True, choices=["us", "cn"])
    ap.add_argument("--limit", type=int, default=None, help="只刷前N只(测试)")
    ap.add_argument("--dry", action="store_true", help="只检测不写入")
    a = ap.parse_args()
    data_dir = os.path.join(HERE, "data_cn" if a.market == "cn" else "data")
    rc = (refresh_cn if a.market == "cn" else refresh_us)(data_dir, a.limit, a.dry)
    sys.exit(rc)


if __name__ == "__main__":
    main()
