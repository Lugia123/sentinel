#!/usr/bin/env python3
"""
news_link.py — 实体链接 v1(news_lab R9)· Phase C
================================================
把宏观流里的新闻认领到个股(relation=company)。重点:R7 发现的业绩预告(公司名开头、无ticker)。
匹配策略(高→低置信):
  ① 标题冒号前缀命中简称(如"东亚药业：预计…")→ conf 1.0(A股公告/业绩预告标准格式)
  ② 标题任意位置整词命中简称(≥3字,避免"银行""科技"等泛词误伤)→ conf 0.8
去重:同 (ticker,news_id) 只连一次。R10 再加行业/概念/供应链维度。

用法:
  uv run python news/news_link.py --today          # 链接今日宏观新闻
  uv run python news/news_link.py --backfill-days 3 # 链接近N天
"""
import sys, os, argparse, asyncio, re, csv
import asyncpg
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newsdb import parse_dsn  # noqa

UNIV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_cn_meta", "universe.csv")
PREFIX = re.compile(r"^\s*([一-龥A-Za-z0-9]{2,8})\s*[:：]")
# 泛词黑名单:太常见的行业词单独出现不算个股命中
STOPNAMES = {"银行", "科技", "电力", "证券", "保险", "地产", "医药", "能源", "传媒", "环保", "机场", "高速", "航空"}


def load_names():
    """code_name → 归一化 ticker(sh.600000)。只取活跃股(status_txt=active),名称≥2字。"""
    m = {}
    with open(UNIV) as f:
        for r in csv.DictReader(f):
            nm = (r.get("code_name") or "").strip()
            code = (r.get("code") or "").strip().lower()
            if not nm or not code or len(nm) < 2:
                continue
            if r.get("status_txt") == "delisted":
                continue
            # 去 ST/*ST 前缀便于匹配
            base = re.sub(r"^\*?ST", "", nm)
            m.setdefault(base, code)
            m.setdefault(nm, code)
    return m


def match(title, names):
    """返回 [(ticker, conf, matched_name)]。前缀命中优先。"""
    hits = {}
    m = PREFIX.match(title or "")
    if m:
        nm = m.group(1)
        if nm in names:
            hits[names[nm]] = (1.0, nm)
    # 任意位置整词(≥3字且非泛词)
    for nm, code in names.items():
        if len(nm) < 3 or nm in STOPNAMES:
            continue
        if nm in (title or "") and code not in hits:
            hits[code] = (0.8, nm)
    return [(c, v[0], v[1]) for c, v in hits.items()]


async def link(days=1):
    conn = await asyncpg.connect(**parse_dsn())
    names = load_names()
    print(f"简称表 {len(names)} 项", flush=True)
    d0 = await conn.fetchval("SELECT max(published_at::date) FROM news_items")
    rows = await conn.fetch("""SELECT id, title FROM news_items
        WHERE ticker IS NULL AND published_at::date > $1::date - $2::int
        ORDER BY published_at DESC""", d0, days)
    linked = 0; ins = []
    for r in rows:
        for tk, conf, nm in match(r["title"], names):
            ins.append(("cn", tk, r["id"], "company", conf, nm))
    if ins:
        before = await conn.fetchval("SELECT count(*) FROM stock_news")
        await conn.executemany("""INSERT INTO stock_news(market,ticker,news_id,relation,confidence,matched)
            VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (market,ticker,news_id) DO NOTHING""", ins)
        linked = await conn.fetchval("SELECT count(*) FROM stock_news") - before
    print(f"扫 {len(rows)} 条宏观新闻 → 新建关联 {linked} 条", flush=True)
    # 抽样预览
    prev = await conn.fetch("""SELECT sn.ticker, sn.matched, sn.confidence, left(n.title,40) title
        FROM stock_news sn JOIN news_items n ON n.id=sn.news_id
        WHERE sn.relation='company' ORDER BY sn.created_at DESC LIMIT 10""")
    for p in prev:
        print(f"  {p['ticker']} ←[{p['confidence']}] {p['matched']} | {p['title']}")
    await conn.close()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", action="store_true")
    ap.add_argument("--backfill-days", type=int, default=None)
    a = ap.parse_args()
    await link(a.backfill_days or 1)


if __name__ == "__main__":
    asyncio.run(main())
