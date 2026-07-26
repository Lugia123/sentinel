#!/usr/bin/env python3
"""
news_calendar.py — 前瞻大事日历(news_lab R7)
============================================
两类来源:
  ① 财报发布日历:news_report_time_baidu(可靠,A股按交易所过滤)
  ② 前瞻事件抽取:从已采集新闻里 AI 抽"未来将发生"的可预知事件(FOMC/数据发布/会议)——
     因经济日历免费源(news_economic_baidu)已 403 死,用新闻流兜底。
日报头部可展示"未来一周日历"。

用法:
  uv run python news/news_calendar.py --earnings      # 拉财报发布日历(A股)
  uv run python news/news_calendar.py --extract       # 从今日新闻抽前瞻事件
"""
import sys, os, argparse, asyncio, json, datetime as dt, warnings, signal
import asyncpg
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newsdb import parse_dsn  # noqa
import newsai  # noqa
warnings.filterwarnings("ignore")

CN_EXCH = {"SH", "SZ", "BJ", "上海", "深圳", "北京"}


def _call(sec, fn, *a, **k):
    def h(s, f): raise TimeoutError()
    old = signal.signal(signal.SIGALRM, h); signal.alarm(sec)
    try:
        return fn(*a, **k)
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, old)


async def _ins(conn, rows):
    if not rows:
        return 0
    before = await conn.fetchval("SELECT count(*) FROM event_calendar")
    await conn.executemany("""INSERT INTO event_calendar(market,event_date,category,title,ticker,importance,source)
        VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (market,event_date,category,title) DO NOTHING""", rows)
    return await conn.fetchval("SELECT count(*) FROM event_calendar") - before


async def earnings(days=14):
    """未来 days 天的 A股财报发布日历。"""
    import akshare as ak
    conn = await asyncpg.connect(**parse_dsn())
    tot = 0
    for i in range(days):
        d = dt.date.today() + dt.timedelta(days=i)
        try:
            df = _call(20, ak.news_report_time_baidu, date=d.strftime("%Y%m%d"))
        except Exception:
            continue
        rows = []
        for _, r in df.iterrows():
            if str(r.get("交易所", "")).upper() not in CN_EXCH:
                continue  # 只要 A股
            try:
                ed = dt.date.fromisoformat(str(r.get("发布日期", d))[:10])
            except (ValueError, TypeError):
                ed = d
            rows.append(("cn", ed, "earnings", f'{r["股票简称"]}({r["股票代码"]}) {r.get("财报类型","财报")}',
                         str(r["股票代码"]), 1, "baidu_report"))
        tot += await _ins(conn, rows)
    print(f"earnings: 新增 {tot} 条(未来{days}天)", flush=True)
    await conn.close()


EXTRACT_SYS = """从给定新闻里抽取【明确提到将在未来发生的可预知事件】(如"下周将公布CPI""美联储议息会议定于X日"
"X日召开发布会""下月实施新规")。只输出JSON,不推测没写明日期的事件。
{"events":[{"date":"YYYY-MM-DD","category":"macro/policy/meeting","title":"事件","importance":1到3}]}
date 必须是新闻里明确或可推算的日期(相对日期如"下周三"按新闻发布日推算);无明确日期的不要抽。没有则空数组。"""


async def extract():
    """从今日新闻抽前瞻事件。"""
    conn = await asyncpg.connect(**parse_dsn())
    d = await conn.fetchval("SELECT max(published_at::date) FROM news_items")
    rows = await conn.fetch("""SELECT title, body, published_at::date::text AS pd FROM news_items
        WHERE published_at::date=$1 AND ticker IS NULL ORDER BY published_at DESC LIMIT 80""", d)
    if not rows:
        print("无新闻"); await conn.close(); return
    user = f"新闻发布日={d}。新闻:\n" + "\n".join(f'{i+1}. {r["title"]} {(r["body"] or "")[:40]}' for i, r in enumerate(rows))
    out = newsai.chat(EXTRACT_SYS, user, temperature=0.0, json_mode=True)
    j = newsai.extract_json(out)
    evs = j.get("events", [])
    ins = []
    for e in evs:
        try:
            ed = dt.date.fromisoformat(e["date"][:10])
            if ed < d:  # 只要未来
                continue
            ins.append(("cn", ed, e.get("category", "macro"), e["title"][:120], None, int(e.get("importance", 1)), "news_extract"))
        except (ValueError, KeyError, TypeError):
            continue
    n = await _ins(conn, ins)
    print(f"extract: 抽出 {len(evs)} 事件,新增 {n} 条", flush=True)
    for e in ins[:8]:
        print(f"  · {e[1]} [{e[2]}] {e[3]}")
    await conn.close()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--earnings", action="store_true")
    ap.add_argument("--extract", action="store_true")
    a = ap.parse_args()
    if a.earnings:
        await earnings()
    if a.extract:
        await extract()


if __name__ == "__main__":
    asyncio.run(main())
