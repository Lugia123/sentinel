#!/usr/bin/env python3
"""
news_keywords.py — 个股累计叙事关键词(news_lab R11)· Phase C 核心(你的第②点)
============================================================================
聚合一只股滚动 N 天的所有新闻源(个股新闻 + 关联宏观新闻 + 信号公告),AI 提炼:
  ① 当前叙事关键词(带权重+依据)——"这只股现在的故事是什么"
  ② 一句话叙事总结
存 stock_keywords。同时可副产 R10 画像(窄主营+商品),替代受限的板块 API。

用法:
  uv run python news/news_keywords.py --ticker sz.000021        # 单股
  uv run python news/news_keywords.py --ticker sz.000021 --days 45
"""
import sys, os, argparse, asyncio, json, datetime as dt
import asyncpg
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newsdb import parse_dsn, norm_ticker  # noqa
import newsai  # noqa

SYSTEM = """你是资深行业分析师。给你一只A股公司最近的新闻+公告(混合),提炼它【当前的市场叙事】。只输出JSON。
{
 "summary": "一句话:这只股现在的核心叙事/市场在讲什么故事(30字内)",
 "keywords": [{"kw":"关键词(2-6字,具体,如'存储涨价''机器人订单',不要'科技''发展'这种空词)",
               "weight":0.0到1.0,"why":"依据哪条新闻(简述)"}],
 "profile": {"industry":"所属细分行业","products":["窄主营产品词"],"commodities":["上游关键商品,无则空"]}
}
keywords 取 3-6 个最能代表当前叙事的,按 weight 排序。严格依据给定新闻,不编造;新闻少就少给。"""


async def gen(ticker, days=30):
    ticker = norm_ticker(ticker)
    conn = await asyncpg.connect(**parse_dsn())
    asof = await conn.fetchval("SELECT max(published_at::date) FROM news_items")
    since = asof - dt.timedelta(days=days)
    # 聚合三源:个股新闻 + 关联宏观(stock_news)+ 信号公告
    own = await conn.fetch("""SELECT title, keywords, published_at::date::text pd FROM news_items
        WHERE ticker=$1 AND published_at::date>=$2 ORDER BY published_at DESC LIMIT 30""", ticker, since)
    linked = await conn.fetch("""SELECT n.title, sn.relation, sn.matched, n.published_at::date::text pd
        FROM stock_news sn JOIN news_items n ON n.id=sn.news_id
        WHERE sn.ticker=$1 AND n.published_at::date>=$2 ORDER BY n.published_at DESC LIMIT 20""", ticker, since)
    anns = await conn.fetch("""SELECT title, ann_type, ann_date::text pd FROM stock_announcements
        WHERE ticker=$1 AND ann_date>=$2 AND is_signal ORDER BY ann_date DESC LIMIT 20""", ticker, since)
    total = len(own) + len(linked) + len(anns)
    if total == 0:
        print(f"{ticker}: 近{days}天无新闻/公告"); await conn.close(); return
    # 构造 AI 输入
    parts = []
    if own:
        parts.append("【个股新闻】\n" + "\n".join(f'· {r["pd"]} {r["title"]}' for r in own))
    if linked:
        parts.append("【关联新闻】\n" + "\n".join(f'· {r["pd"]} [{r["relation"]}:{r["matched"]}] {r["title"]}' for r in linked))
    if anns:
        parts.append("【信号公告】\n" + "\n".join(f'· {r["pd"]} [{r["ann_type"]}] {r["title"]}' for r in anns))
    user = f"公司代码 {ticker},近{days}天({since}~{asof})共{total}条:\n\n" + "\n\n".join(parts)

    out = newsai.chat(SYSTEM, user, temperature=0.2, json_mode=True)
    j = newsai.extract_json(out)
    kws = j.get("keywords", [])
    await conn.execute("""INSERT INTO stock_keywords(market,ticker,asof,keywords,summary,n_news)
        VALUES('cn',$1,$2,$3::jsonb,$4,$5) ON CONFLICT(market,ticker,asof) DO UPDATE SET
        keywords=EXCLUDED.keywords, summary=EXCLUDED.summary, n_news=EXCLUDED.n_news, updated_at=now()""",
        ticker, asof, json.dumps(kws, ensure_ascii=False), j.get("summary", ""), total)
    # 副产:写画像(窄主营+商品)
    prof = j.get("profile", {})
    if prof:
        await conn.execute("""INSERT INTO stock_profile(market,ticker,industry,keywords,commodities)
            VALUES('cn',$1,$2,$3,$4) ON CONFLICT(market,ticker) DO UPDATE SET
            industry=EXCLUDED.industry, keywords=EXCLUDED.keywords, commodities=EXCLUDED.commodities, updated_at=now()""",
            ticker, prof.get("industry", ""), prof.get("products", []), prof.get("commodities", []))
    print(f"{ticker}: 聚合 {total} 条(个股{len(own)}/关联{len(linked)}/公告{len(anns)})", flush=True)
    print(f"  叙事: {j.get('summary','')}")
    for k in kws:
        print(f"    [{k.get('weight',0):.1f}] {k.get('kw','')} — {k.get('why','')[:36]}")
    if prof:
        print(f"  画像: 行业={prof.get('industry','')} 主营={prof.get('products',[])} 商品={prof.get('commodities',[])}")
    await conn.close()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    await gen(a.ticker, a.days)


if __name__ == "__main__":
    asyncio.run(main())
