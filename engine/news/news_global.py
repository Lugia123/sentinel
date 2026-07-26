#!/usr/bin/env python3
"""
news_global.py — 全球新闻采集(GDELT)+ 传导标注(news_lab R12)
=============================================================
按传导映射(transmission.py)的主题查询 GDELT 全球英文新闻(一手,lead-time),
落 news_items(source=gdelt,keywords 存 {theme, cn_sectors, lead_lag})。节流 6s(GDELT 免费层限频)。

用法:
  uv run python news/news_global.py --collect          # 拉全部传导主题(节流,约2min)
  uv run python news/news_global.py --collect --span 3d
"""
import sys, os, argparse, asyncio, json, time, datetime as dt
import requests
import asyncpg
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newsdb import parse_dsn, fp  # noqa
from transmission import TRANSMISSION, lead_lag_label  # noqa

UA = {"User-Agent": "Mozilla/5.0 (SentinelNews/1.0)"}
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"


def _parse_gdelt_ts(s):
    # 20260714T173000Z
    try:
        return dt.datetime.strptime(s, "%Y%m%dT%H%M%SZ")
    except (ValueError, TypeError):
        return None


def query_gdelt(query, span="2d", maxrecords=10, retries=3):
    for i in range(retries):
        try:
            r = requests.get(GDELT, params={"query": query, "mode": "artlist", "maxrecords": maxrecords,
                             "format": "json", "timespan": span, "sort": "datedesc"}, headers=UA, timeout=30)
            if r.status_code == 429:  # 限频退避
                time.sleep(8 * (i + 1)); continue
            if r.status_code == 200 and r.text.strip().startswith("{"):
                return r.json().get("articles", [])
            return []
        except Exception:
            time.sleep(4)
    return []


async def collect(span="2d"):
    conn = await asyncpg.connect(**parse_dsn())
    total = 0
    for t in TRANSMISSION:
        arts = query_gdelt(t["query"], span=span)
        meta = json.dumps({"theme": t["theme"], "cn_sectors": t["cn_sectors"], "lead_lag": t["lead_lag"]}, ensure_ascii=False)
        rows = []
        for a in arts:
            title = a.get("title", "")
            if not title:
                continue
            rows.append(("gdelt", fp("gdelt", title, a.get("seendate", "")), title[:300],
                         f'[{a.get("sourcecountry","")}] {a.get("domain","")}', a.get("url", ""),
                         meta, None, _parse_gdelt_ts(a.get("seendate", ""))))
        if rows:
            before = await conn.fetchval("SELECT count(*) FROM news_items")
            await conn.executemany("""INSERT INTO news_items(source,fingerprint,title,body,url,keywords,ticker,published_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT (fingerprint) DO NOTHING""", rows)
            n = await conn.fetchval("SELECT count(*) FROM news_items") - before
            total += n
            print(f"  [{t['theme']}] {len(arts)}篇→新增{n} | {lead_lag_label(t['lead_lag'])} → {'/'.join(t['cn_sectors'])}", flush=True)
        time.sleep(12)  # GDELT 免费层节流(实测6s仍429,提到12s)
    print(f"gdelt: 共新增 {total} 条全球新闻", flush=True)
    await conn.close()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--span", default="2d")
    a = ap.parse_args()
    if a.collect:
        await collect(a.span)


if __name__ == "__main__":
    asyncio.run(main())
