#!/usr/bin/env python3
"""
news_collector.py — A股新闻采集(news_lab R3)
============================================
按 R1 源清单抓取 → 去重指纹 → upsert 入 PG(asyncpg,与 backfill.py 一致)。
幂等:重复跑同批新闻靠 fingerprint 去重。
  宏观/大事:东财全球快讯 / 新浪 / 同花顺 / 央视(可回补)
  个股:stock_news_em(近期,带关键词)/ stock_individual_notice_report(公告,深历史)
公告命中白名单(R2)标 is_signal。

用法:
  uv run python news/news_collector.py --macro                 # 抓宏观快讯+央视(当天)
  uv run python news/news_collector.py --stocks 600000,000021  # 抓指定个股新闻+公告
  uv run python news/news_collector.py --cctv-date 20260713    # 回补某天央视
  uv run python news/news_collector.py --ann-backfill 600519   # 回补单股全部公告历史
"""
import sys, os, argparse, asyncio, datetime as dt, warnings, signal
import asyncpg
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newsdb import parse_dsn, fp, ann_is_signal, norm_ticker  # noqa
warnings.filterwarnings("ignore")


def _call(sec, fn, *a, **k):
    """带 SIGALRM 超时的同步调用(akshare 反爬源可能卡死)。"""
    def h(s, f): raise TimeoutError()
    old = signal.signal(signal.SIGALRM, h); signal.alarm(sec)
    try:
        return fn(*a, **k)
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, old)


def _parse_ts(s):
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return dt.datetime.strptime(str(s)[:19], f)
        except ValueError:
            continue
    return None


async def _ins_news(conn, rows):
    """rows: [(source,fp,title,body,url,keywords,ticker,published_at)]。返回新增数。"""
    if not rows:
        return 0
    before = await conn.fetchval("SELECT count(*) FROM news_items")
    await conn.executemany("""
        INSERT INTO news_items(source,fingerprint,title,body,url,keywords,ticker,published_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT (fingerprint) DO NOTHING
    """, rows)
    return await conn.fetchval("SELECT count(*) FROM news_items") - before


async def _ins_ann(conn, rows):
    """rows: [(ticker,ann_date,title,ann_type,url,is_signal)]。返回新增数。"""
    if not rows:
        return 0
    before = await conn.fetchval("SELECT count(*) FROM stock_announcements")
    await conn.executemany("""
        INSERT INTO stock_announcements(ticker,ann_date,title,ann_type,url,is_signal)
        VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (market,ticker,ann_date,title) DO UPDATE SET is_signal=EXCLUDED.is_signal
    """, rows)
    return await conn.fetchval("SELECT count(*) FROM stock_announcements") - before


# ── 宏观/大事 ──
async def collect_macro(conn):
    import akshare as ak
    total = 0
    for src, fn, tcol, titlef, bodyf, urlf in [
        ("em_global", ak.stock_info_global_em, "发布时间", "标题", "摘要", "链接"),
        ("ths_global", ak.stock_info_global_ths, "发布时间", "标题", "内容", "链接"),
    ]:
        try:
            df = _call(30, fn)
            rows = [(src, fp(src, r[titlef], r[tcol]), str(r[titlef]), str(r.get(bodyf, "")),
                     str(r.get(urlf, "")), "", None, _parse_ts(r[tcol])) for _, r in df.iterrows()]
            total += await _ins_news(conn, rows)
        except Exception as e:
            print(f"  [warn] {src}: {type(e).__name__}", flush=True)
    try:  # 新浪只有 时间/内容
        df = _call(20, ak.stock_info_global_sina)
        rows = [("sina_global", fp("sina_global", str(r["内容"])[:40], r["时间"]), str(r["内容"])[:80],
                 str(r["内容"]), "", "", None, _parse_ts(r["时间"])) for _, r in df.iterrows()]
        total += await _ins_news(conn, rows)
    except Exception as e:
        print(f"  [warn] sina_global: {type(e).__name__}", flush=True)
    return total


async def collect_cctv(conn, date):
    import akshare as ak
    df = _call(25, ak.news_cctv, date=date)
    pub = _parse_ts(f"{date[:4]}-{date[4:6]}-{date[6:]} 19:00:00")  # 19:00 播出
    rows = [("cctv", fp("cctv", r["title"], date), str(r["title"]), str(r.get("content", "")),
             "", "", None, pub) for _, r in df.iterrows()]
    return await _ins_news(conn, rows)


# ── 个股 ──
async def collect_stock_news(conn, code):
    import akshare as ak
    df = _call(20, ak.stock_news_em, symbol=code)
    rows = [("stock_em", fp("stock_em", code, r["新闻标题"], r["发布时间"]), str(r["新闻标题"]),
             str(r.get("新闻内容", "")), str(r.get("新闻链接", "")), str(r.get("关键词", "")),
             norm_ticker(code), _parse_ts(r["发布时间"])) for _, r in df.iterrows()]
    return await _ins_news(conn, rows)


async def collect_announcements(conn, code, recent_only=True):
    import akshare as ak
    df = _call(30, ak.stock_individual_notice_report, security=code)
    if recent_only:
        cutoff = (dt.date.today() - dt.timedelta(days=90)).strftime("%Y-%m-%d")
        df = df[df["公告日期"].astype(str) >= cutoff]
    rows = []
    for _, r in df.iterrows():
        typ, title = str(r.get("公告类型", "")), str(r["公告标题"])
        try:
            d = dt.date.fromisoformat(str(r["公告日期"])[:10])
        except ValueError:
            continue
        rows.append((norm_ticker(code), d, title, typ, str(r.get("网址", "")), ann_is_signal(typ, title)))
    return await _ins_ann(conn, rows)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--macro", action="store_true")
    ap.add_argument("--cctv-date", default=None)
    ap.add_argument("--stocks", default=None, help="逗号分隔纯数字代码")
    ap.add_argument("--ann-backfill", default=None)
    a = ap.parse_args()
    conn = await asyncpg.connect(**parse_dsn())
    try:
        if a.macro:
            n = await collect_macro(conn)
            try:
                n += await collect_cctv(conn, dt.date.today().strftime("%Y%m%d"))
            except Exception:
                print("  [info] 今日央视暂无(未到播出时间)", flush=True)
            print(f"macro: 新增 {n} 条", flush=True)
        if a.cctv_date:
            print(f"cctv {a.cctv_date}: 新增 {await collect_cctv(conn, a.cctv_date)} 条", flush=True)
        if a.stocks:
            tn = ta = 0
            for code in a.stocks.split(","):
                code = code.strip()
                try:
                    tn += await collect_stock_news(conn, code)
                except Exception as e:
                    print(f"  [warn] news {code}: {type(e).__name__}", flush=True)
                try:
                    ta += await collect_announcements(conn, code, recent_only=True)
                except Exception as e:
                    print(f"  [warn] ann {code}: {type(e).__name__}", flush=True)
            print(f"stocks: 新增新闻 {tn} 条 / 公告 {ta} 条", flush=True)
        if a.ann_backfill:
            print(f"ann-backfill {a.ann_backfill}: 新增 {await collect_announcements(conn, a.ann_backfill, recent_only=False)} 条", flush=True)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
