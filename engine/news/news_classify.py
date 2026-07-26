#!/usr/bin/env python3
"""
news_classify.py — 金融影响分级器(news_lab R5)
==============================================
L1 批量分级层:一次 prompt 塞 N 条新闻,统一分级(重大/关注/噪声 + 影响方向标签)。
两级漏斗的中段——规则粗筛(L0)之后、深度合成(L2)之前的公共分级。批量=控吞吐(R4)。

用法(研究/自测):
  uv run python news/news_classify.py --consistency   # 同批重复3次测自洽率(R5验证)
  uv run python news/news_classify.py --today          # 分级今日库中未分级新闻(落库 tags)
"""
import sys, os, argparse, asyncio, json
import asyncpg
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newsdb import parse_dsn  # noqa
import newsai  # noqa

SYSTEM = """你是资深金融新闻分析师。给你一批新闻(编号列表),对每条判断它对【中国A股市场】的影响,只输出JSON。
【分级 level】
  major = 重大:可能显著影响大盘/板块/多股(货币财政政策、重大监管、地缘冲突、大盘级资金面、行业性政策)
  watch = 值得关注:影响特定板块或个股(公司公告、行业动态、局部政策、商品价格)
  noise = 噪声:对投资决策无信息量(重复、程序性、软文、纯宣传、旧闻)
【影响维度 dims】(多选,数组;无则空数组)从固定集合选:
  货币政策/财政政策/监管/地缘/汇率/利率/大宗商品/行业政策/资金面/风险偏好/个股事件/宏观数据
【方向 tone】仅从 {利好, 利空, 中性} 三选一(对相关标的的方向;不确定填中性)
【严格要求】不预测涨跌幅,不编造;只依据给定文本判断"影响类别",不是"会涨会跌"。
输出格式(严格JSON,数组,每条对应输入编号):
{"items":[{"id":1,"level":"major","dims":["货币政策","利率"],"tone":"利好"},...]}"""


def build_user(batch):
    lines = [f'{i+1}. [{n["source"]}] {n["title"]} {(n["body"] or "")[:60]}' for i, n in enumerate(batch)]
    return "新闻批次(共%d条):\n%s\n\n对每条输出 level/dims/tone。" % (len(batch), "\n".join(lines))


def classify_batch(batch, temperature=0.2):
    out = newsai.chat(SYSTEM, build_user(batch), temperature=temperature, json_mode=True)
    j = newsai.extract_json(out)
    items = j.get("items", j if isinstance(j, list) else [])
    res = {}
    for it in items:
        try:
            res[int(it["id"])] = (it.get("level", "noise"), tuple(it.get("dims", [])), it.get("tone", "中性"))
        except (KeyError, ValueError, TypeError):
            continue
    return res


async def fetch_batch(conn, n=25):
    rows = await conn.fetch("""
        SELECT id, source, title, body FROM news_items
        WHERE published_at::date = (SELECT max(published_at::date) FROM news_items)
        ORDER BY published_at DESC LIMIT $1""", n)
    return [dict(r) for r in rows]


async def consistency():
    """同一批新闻重复分级3次,测 level 自洽率(R5 验证:目标>85%)。"""
    conn = await asyncpg.connect(**parse_dsn())
    batch = await fetch_batch(conn, 25)
    await conn.close()
    print(f"取 {len(batch)} 条,重复分级 3 次(temp=0)…", flush=True)
    runs = [classify_batch(batch, temperature=0.0) for _ in range(3)]
    ids = set(runs[0]) & set(runs[1]) & set(runs[2])
    rank = {"noise": 0, "watch": 1, "major": 2}
    agree_level = sum(1 for i in ids if runs[0][i][0] == runs[1][i][0] == runs[2][i][0])
    # 决策相关指标:①相邻档容差(±1算一致)②major 识别一致性(是否都判/都不判 major)
    adj = sum(1 for i in ids if max(rank[runs[k][i][0]] for k in range(3)) - min(rank[runs[k][i][0]] for k in range(3)) <= 1)
    major_consist = sum(1 for i in ids if len({runs[k][i][0] == "major" for k in range(3)}) == 1)
    agree_tone = sum(1 for i in ids if runs[0][i][2] == runs[1][i][2] == runs[2][i][2])
    print(f"3次都覆盖 {len(ids)} 条")
    print(f"  level 三档全一致: {agree_level}/{len(ids)} = {agree_level/max(1,len(ids))*100:.0f}%")
    print(f"  level ±1档容差:  {adj}/{len(ids)} = {adj/max(1,len(ids))*100:.0f}%")
    print(f"  major 识别一致:  {major_consist}/{len(ids)} = {major_consist/max(1,len(ids))*100:.0f}% (决策最关键)")
    print(f"  tone  三次全一致: {agree_tone}/{len(ids)} = {agree_tone/max(1,len(ids))*100:.0f}%")
    # 分布 + 分歧样例
    from collections import Counter
    print("  level 分布(run1):", dict(Counter(v[0] for v in runs[0].values())))
    for i in list(ids)[:20]:
        ls = [runs[k][i][0] for k in range(3)]
        if len(set(ls)) > 1:
            print(f"    分歧 #{i}: {ls} | {batch[i-1]['title'][:30]}")


async def classify_today():
    conn = await asyncpg.connect(**parse_dsn())
    batch = await fetch_batch(conn, 50)
    res = classify_batch(batch)
    for i, n in enumerate(batch, 1):
        if i in res:
            lvl, dims, tone = res[i]
            await conn.execute("UPDATE news_items SET keywords=$1 WHERE id=$2",
                               json.dumps({"level": lvl, "dims": list(dims), "tone": tone}, ensure_ascii=False), n["id"])
    from collections import Counter
    print("今日分级:", dict(Counter(v[0] for v in res.values())), flush=True)
    await conn.close()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--consistency", action="store_true")
    ap.add_argument("--today", action="store_true")
    a = ap.parse_args()
    if a.consistency:
        await consistency()
    if a.today:
        await classify_today()


if __name__ == "__main__":
    asyncio.run(main())
