#!/usr/bin/env python3
"""
news_profile.py — 个股关联画像 + 画像匹配(news_lab R10)· Phase C
==============================================================
画像 = 行业 + 概念 + 主营关键词 + 上游商品。匹配"不直接点名但相关"的新闻(industry/concept/supply)。

数据获取现状(R10):行业分类【多源可用】(申万31/同花顺90/巨潮294),但 per-stock 行业成分
需东财板块接口,本 session 密集调用后被限流(见 R19)。故 build_profiles 支持:
  --from-ths  : 用同花顺行业成分建画像(退避重试;限流时部分成功)
  --seed FILE : 从种子CSV(ticker,industry,concepts,keywords,commodities)灌入(限流兜底/测试)
匹配逻辑 match_by_profile 与数据来源解耦,先用种子样本验证机制。

用法:
  uv run python news/news_profile.py --seed seed.csv     # 灌画像
  uv run python news/news_profile.py --match             # 用画像链接今日宏观新闻(industry/concept)
"""
import sys, os, argparse, asyncio, csv
import asyncpg
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newsdb import parse_dsn  # noqa


async def seed(path):
    conn = await asyncpg.connect(**parse_dsn())
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            rows.append(("cn", r["ticker"].strip().lower(), r.get("name", ""), r.get("industry", ""),
                         [x for x in r.get("concepts", "").split("|") if x],
                         [x for x in r.get("keywords", "").split("|") if x],
                         [x for x in r.get("commodities", "").split("|") if x]))
    await conn.executemany("""INSERT INTO stock_profile(market,ticker,name,industry,concepts,keywords,commodities)
        VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (market,ticker) DO UPDATE SET
        industry=EXCLUDED.industry, concepts=EXCLUDED.concepts, keywords=EXCLUDED.keywords,
        commodities=EXCLUDED.commodities, updated_at=now()""", rows)
    print(f"灌入画像 {len(rows)} 只", flush=True)
    await conn.close()


# R10 发现:宽泛行业/概念词匹配噪声极大(能源/AI/半导体命中任何提及新闻)。
# 只保留【窄且经济链条直接】的关系:商品映射(输入成本) + 长产品词;宽泛词一律剔除。
BROAD_TERMS = {"能源", "科技", "半导体", "人工智能", "AI", "消费", "医药", "金融", "地产", "新能源",
               "芯片", "电子", "汽车", "5G", "云计算", "大数据", "军工", "电力"}


async def match():
    """画像间接链接:只用商品映射(supply,conf 0.6)+ 窄产品关键词(concept,conf 0.5,≥3字非宽泛词)。
    宽泛行业/概念词剔除(R10 证明其噪声大)。已被 R9 直连的 (ticker,news) 自动去重。"""
    conn = await asyncpg.connect(**parse_dsn())
    profs = await conn.fetch("SELECT ticker, name, keywords, commodities FROM stock_profile WHERE market='cn'")
    if not profs:
        print("无画像(先 --seed 或 --from-ths)"); await conn.close(); return
    d0 = await conn.fetchval("SELECT max(published_at::date) FROM news_items")
    news = await conn.fetch("""SELECT id, title, body FROM news_items
        WHERE ticker IS NULL AND published_at::date=$1 ORDER BY published_at DESC""", d0)
    ins = []
    for n in news:
        txt = (n["title"] or "") + " " + (n["body"] or "")[:80]
        for p in profs:
            terms = []
            for cm in p["commodities"]:  # 商品映射:输入成本,经济链条直接
                if cm and cm not in BROAD_TERMS and cm in txt:
                    terms.append(("supply", cm, 0.6))
            for k in p["keywords"]:  # 窄产品词:≥3字且非宽泛
                if k and len(k) >= 3 and k not in BROAD_TERMS and k in txt:
                    terms.append(("concept", k, 0.5))
            if terms:
                rel, matched, conf = terms[0]
                ins.append(("cn", p["ticker"], n["id"], rel, conf, matched))
    linked = 0
    if ins:
        before = await conn.fetchval("SELECT count(*) FROM stock_news")
        await conn.executemany("""INSERT INTO stock_news(market,ticker,news_id,relation,confidence,matched)
            VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (market,ticker,news_id) DO NOTHING""", ins)
        linked = await conn.fetchval("SELECT count(*) FROM stock_news") - before
    print(f"画像匹配:{len(news)}新闻 × {len(profs)}画像 → 新建间接关联 {linked} 条", flush=True)
    prev = await conn.fetch("""SELECT sn.ticker, sn.relation, sn.matched, left(n.title,38) title
        FROM stock_news sn JOIN news_items n ON n.id=sn.news_id
        WHERE sn.relation IN ('industry','concept','supply') ORDER BY sn.created_at DESC LIMIT 10""")
    for p in prev:
        print(f"  {p['ticker']} ←[{p['relation']}] {p['matched']} | {p['title']}")
    await conn.close()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=None)
    ap.add_argument("--match", action="store_true")
    a = ap.parse_args()
    if a.seed:
        await seed(a.seed)
    if a.match:
        await match()


if __name__ == "__main__":
    asyncio.run(main())
