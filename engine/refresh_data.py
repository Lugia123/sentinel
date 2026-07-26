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
DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(HERE, "data"))


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


CN_FIELDS = "date,open,high,low,close,preclose,volume,amount,turn,tradestatus,pctChg,isST"
GAP_DAYS = 180  # 相邻行日期差超过此值视为断档(污染:旧历史+新增量拼接)


def _dates_of(fp):
    """读单只 CSV 全部日期列(修复模式全扫用)。"""
    out = []
    try:
        with open(fp) as f:
            for row in csv.reader(f):
                if row and row[0][:4].isdigit():
                    out.append(row[0])
    except Exception:
        pass
    return out


def _max_gap_days(dates):
    """相邻日期最大间隔(天)。"""
    worst = 0
    for a, b in zip(dates, dates[1:]):
        try:
            d = (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days
            worst = max(worst, d)
        except ValueError:
            continue
    return worst


def _full_refetch_cn(bs, code, fp, dry=False):
    """全量重拉一只A股并原子重写 CSV(修复断档/落后太久)。返回重写后的最后日期(失败 None)。"""
    rs = bs.query_history_k_data_plus(code, CN_FIELDS, start_date="1990-01-01",
                                      frequency="d", adjustflag="2")
    rows = []
    while rs.error_code == '0' and rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return None
    if not dry:
        tmp = fp + ".tmp"
        with open(tmp, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(CN_FIELDS.split(","))
            w.writerows(rows)
        os.replace(tmp, fp)
    return rows[-1][0]


def repair_cn(data_dir, limit=None, dry=False):
    """修复模式:全扫每只 CSV 的日期列,发现内部断档(相邻>GAP_DAYS天)→ 全量重拉重写。
    一次性使用(存量污染:历史下载不完整 + 后来增量直接接尾)。"""
    import baostock as bs
    files = sorted(glob.glob(os.path.join(data_dir, "*.csv")))
    if limit:
        files = files[:limit]
    bs.login()
    bad = fixed = 0
    for i, fp in enumerate(files):
        dates = _dates_of(fp)
        if len(dates) < 2 or _max_gap_days(dates) <= GAP_DAYS:
            continue
        bad += 1
        code = os.path.basename(fp)[:-4].replace("_", ".", 1)
        try:
            last = _full_refetch_cn(bs, code, fp, dry)
            if last:
                fixed += 1
                print(f"  修复 {code}: 断档→全量重拉 {len(_dates_of(fp))}行 至{last}" if not dry
                      else f"  [dry] {code} 需重拉", flush=True)
        except Exception as e:
            print(f"  [warn] {code} 重拉失败: {type(e).__name__}", flush=True)
            bs.login()
        if i % 80 == 79:
            bs.logout(); bs.login()
    bs.logout()
    print(f"cn-repair: {'DRY ' if dry else ''}断档{bad}只,修复{fixed}只")
    return 0 if fixed == bad else 1


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
    # 落后超 ~20 日历天的:不再直接追增量(会在文件里拼出断档),改走【全量重拉】;
    # 重拉后仍落后的是真退市/长期停牌 → 记入 .norefetch,后续周期不再反复重拉。
    cutoff = (datetime.strptime(lmax, "%Y-%m-%d") - timedelta(days=20)).strftime("%Y-%m-%d")
    norefetch_fp = os.path.join(data_dir, ".norefetch")
    norefetch = set()
    if os.path.exists(norefetch_fp):
        norefetch = set(open(norefetch_fp).read().split())
    # 不做基于单一探针的整体 skip:改为逐只 per-file 判断(已最新的秒过 continue),
    # 这样上次跑到一半被中断也能自愈续传(探针股已更新≠全体已更新)。
    print(f"cn: 探针{lmax} → 数据源{src_max}({len(files)}只,per-file 断点续传;各只已最新则跳过)", flush=True)
    updated = 0
    for i, fp in enumerate(files):
        flast = _last_date(fp)  # 该只自身最后日期(断点)
        if not flast or flast >= src_max:
            continue  # 已最新
        code = os.path.basename(fp)[:-4].replace("_", ".", 1)
        if flast < cutoff:  # 落后太久:增量追加会造断档 → 全量重拉(退市股缓存跳过)
            if code in norefetch:
                continue
            try:
                last = _full_refetch_cn(bs, code, fp, dry)
            except Exception:
                bs.login(); last = None
            if last and last >= cutoff:
                updated += 1
                print(f"  {code} 落后({flast})→ 全量重拉至{last}", flush=True)
            else:  # 重拉后仍旧 = 真退市/停牌 → 记缓存
                norefetch.add(code)
                if not dry:
                    with open(norefetch_fp, "w") as f:
                        f.write("\n".join(sorted(norefetch)))
            continue
        start_i = (datetime.strptime(flast, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        for attempt in range(2):
            try:
                rs = bs.query_history_k_data_plus(
                    code, CN_FIELDS,
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
    ap.add_argument("--repair", action="store_true", help="cn 修复模式:全扫内部断档并全量重拉(一次性)")
    a = ap.parse_args()
    data_dir = os.path.join(DATA_DIR, "daily") if a.market == "cn" else DATA_DIR
    if a.repair:
        if a.market != "cn":
            print("--repair 目前仅支持 cn"); sys.exit(1)
        sys.exit(repair_cn(data_dir, a.limit, a.dry))
    rc = (refresh_cn if a.market == "cn" else refresh_us)(data_dir, a.limit, a.dry)
    sys.exit(rc)


if __name__ == "__main__":
    main()
