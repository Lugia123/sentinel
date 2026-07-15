#!/usr/bin/env python3
"""
news_daily.py — 每日金融要闻日报(news_lab R6)· Phase B
=====================================================
流水:L0 规则粗筛+碎片聚合 → L1 批量分级(复用 R5)→ 取 major/watch → L2 生成结构化日报 → 入库。
两级漏斗 L2 段:只把粗筛后的要闻喂给 AI 合成,不读全量(R4 吞吐/成本)。

用法:
  uv run python news/news_daily.py --gen               # 生成今日日报
  uv run python news/news_daily.py --gen --date 2026-07-14
"""
import sys, os, argparse, asyncio, json, re
import datetime as dt
import asyncpg
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newsdb import parse_dsn  # noqa
import newsai  # noqa
from news_classify import classify_batch  # noqa
from transmission import lead_lag_label  # noqa

# L0 碎片聚合:同源+标题前缀相同(如"沃什：…"发言人前缀)视为一个主题簇,只留代表条 + 计数
SPEAKER_PREFIX = re.compile(r"^([一-龥A-Za-z·]{2,6})[:：]")


def prefilter(rows):
    """L0:去重(库层已做)+ 讲话碎片聚合 + 明显噪声词剔除。返回精简后的新闻列表。"""
    seen_topic = {}
    out = []
    for r in rows:
        title = r["title"]
        m = SPEAKER_PREFIX.match(title)
        if m:  # 发言人碎片:同发言人聚成一簇
            key = (r["source"], m.group(1))
            if key in seen_topic:
                seen_topic[key]["_frag"] += 1
                continue
            r = dict(r); r["_frag"] = 1
            seen_topic[key] = r
            out.append(r)
        else:
            out.append(dict(r, _frag=1))
    return out


DIGEST_SYS = """你是资深财经编辑,为中国A股投资者写【每日金融要闻日报】。给你今日已分级的要闻(每条带 level/dims/tone),
以及【全球事件+传导标注】(每条带对A股的板块传导和提前/滞后时序)。提炼成结构化日报。
只输出JSON,不编造未给出的事实,不预测涨跌幅。
{
 "overview": "一段today综述(80字内,今天市场最该关注什么)",
 "world": [{"title":"世界大事标题","impact":"对A股的可能影响(一句)","tone":"利好/利空/中性"}],
 "domestic": [{"title":"国内大事","impact":"...","tone":"..."}],
 "market_impact": [{"sector":"受影响板块/主题","reason":"为什么","tone":"..."}],
 "global_transmission": [{"event":"全球事件","cn_sectors":"传导到的A股板块","timing":"提前/滞后特征(如'海外隔夜先行,A股次日反应')","tone":"..."}]
}
world/domestic 各取最重要 3-5 条(major优先),market_impact 取 2-4 板块。
global_transmission 从【全球事件】里挑 2-4 个对A股传导明确的,必须写清 timing(提前还是滞后)。宁缺勿凑,没有空数组。"""


def build_digest_user(items):
    lines = []
    for n in items:
        tag = ""
        try:
            k = json.loads(n["keywords"]) if n["keywords"] else {}
            tag = f'[{k.get("level","")}/{",".join(k.get("dims",[]))}/{k.get("tone","")}]'
        except Exception:
            pass
        frag = f'(+{n["_frag"]-1}条相关)' if n.get("_frag", 1) > 1 else ""
        lines.append(f'{tag} {n["title"]} {frag} {(n["body"] or "")[:50]}')
    return "今日要闻(%d条):\n%s" % (len(items), "\n".join(lines))


async def gen(date=None):
    conn = await asyncpg.connect(**parse_dsn())
    # 目标日期:显式指定,否则取库中宏观新闻的最新日
    if date:
        d = dt.date.fromisoformat(date)
    else:
        d = await conn.fetchval("SELECT max(published_at::date) FROM news_items WHERE ticker IS NULL")
    if d is None:
        print("无新闻可生成日报"); await conn.close(); return
    rows = [dict(r) for r in await conn.fetch("""SELECT id,source,title,body,keywords FROM news_items
        WHERE published_at::date=$1 AND ticker IS NULL ORDER BY published_at DESC""", d)]
    if not rows:
        print(f"{d}: 无宏观新闻"); await conn.close(); return

    # L0 粗筛+聚合
    items = prefilter(rows)
    # L1 分级(未分级的补分级;分批25)
    unclassified = [n for n in items if not n["keywords"]]
    for i in range(0, len(unclassified), 25):
        batch = unclassified[i:i+25]
        res = classify_batch(batch, temperature=0.0)
        for j, n in enumerate(batch, 1):
            if j in res:
                lvl, dims, tone = res[j]
                n["keywords"] = json.dumps({"level": lvl, "dims": list(dims), "tone": tone}, ensure_ascii=False)
                await conn.execute("UPDATE news_items SET keywords=$1 WHERE id=$2", n["keywords"], n["id"])
    # 取 major/watch 喂 L2
    def lvl(n):
        try: return json.loads(n["keywords"]).get("level", "noise")
        except: return "noise"
    top = [n for n in items if lvl(n) in ("major", "watch")]
    top.sort(key=lambda n: 0 if lvl(n) == "major" else 1)
    top = top[:40]

    # 全球新闻(GDELT)+ 传导标注:近3天(海外先行,窗口放宽)
    grows = await conn.fetch("""SELECT title, keywords FROM news_items
        WHERE source='gdelt' AND published_at::date > $1::date - 3 ORDER BY published_at DESC LIMIT 60""", d)
    gblock = ""
    if grows:
        lines = []
        for r in grows:
            try:
                k = json.loads(r["keywords"])
                lines.append(f'[{k.get("theme","")}|{lead_lag_label(k.get("lead_lag",0))}|板块:{"/".join(k.get("cn_sectors",[]))}] {r["title"][:70]}')
            except Exception:
                continue
        gblock = "\n\n【全球事件+传导标注】(每条已标 A股板块传导 + 提前/滞后时序):\n" + "\n".join(lines[:40])
    print(f"{d}: 原始{len(rows)}→聚合{len(items)}→要闻{len(top)} + 全球{len(grows)}(喂AI)", flush=True)

    date_hdr = f"【报告日期】{d.strftime('%Y年%m月%d日')}(所有时间判断以此为准,新闻均为近日,勿臆断年份如'2024年')\n\n"
    out = newsai.chat(DIGEST_SYS, date_hdr + build_digest_user(top) + gblock, temperature=0.3, json_mode=True)
    digest = newsai.extract_json(out)
    await conn.execute("""INSERT INTO news_digest(market,digest_date,digest,n_source)
        VALUES('cn',$1,$2::jsonb,$3) ON CONFLICT(market,digest_date) DO UPDATE SET digest=EXCLUDED.digest, n_source=EXCLUDED.n_source, generated_at=now()""",
        d, json.dumps(digest, ensure_ascii=False), len(top))
    await conn.close()
    # 打印预览
    print("\n=== 日报预览 ===")
    print("综述:", digest.get("overview", ""))
    for sec in ("world", "domestic", "market_impact", "global_transmission"):
        arr = digest.get(sec, [])
        print(f"\n[{sec}] {len(arr)}条")
        for x in arr[:5]:
            print("  ·", {k: v for k, v in x.items()})


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", action="store_true")
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    if a.gen:
        await gen(a.date)


if __name__ == "__main__":
    asyncio.run(main())
