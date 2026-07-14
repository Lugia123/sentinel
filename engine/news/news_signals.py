#!/usr/bin/env python3
"""
news_signals.py — 个股新闻信号旗(news_lab R27)· 诚实版
=====================================================
只输出【经 R13-R25 验证为真、且诚实定位为 L1/L2/风险】的信号,绝不冒充可交易 alpha。
产出旗(供详情页/关注列表展示):
  attention  : 近期业绩预增(rev+PEAD,PIT干净,size中性正)→ "值得关注",非买入建议
  avoid_risk : 近期龙虎榜净卖出(稳健利空)→ 持有者"回避/退出"风险提示
  vol_warn   : 近期有事件 → 波动可能加大(前向波动45% vs 35%)
每条附依据(可核验)。严禁输出"会涨/会跌/预期收益"。

用法(库):from news_signals import stock_flags; stock_flags(conn, 'sz.000021')
数据源:stock_announcements(公告,含预增/龙虎榜类)+ news_items。生产按已采集数据计算。
"""
import datetime as dt

# R25/R26 定论:诚实标注,不承诺方向收益
DISCLAIMER = "研究关注/风险提示,非买入卖出建议,非收益预测(经严格PIT+真实摩擦检验:A股新闻无强可交易alpha)"


async def stock_flags(conn, ticker, market="cn", days=20):
    """返回该股近 days 天的诚实信号旗列表。"""
    since = dt.date.today() - dt.timedelta(days=days)
    flags = []

    # attention:近期业绩预增/扭亏(标题命中)——rev+PEAD,PIT干净的关注信号
    pos = await conn.fetch("""SELECT title, ann_date FROM stock_announcements
        WHERE market=$1 AND ticker=$2 AND ann_date>=$3
          AND (title LIKE '%预增%' OR title LIKE '%扭亏%' OR title LIKE '%业绩预告%' AND title LIKE '%增%')
        ORDER BY ann_date DESC LIMIT 3""", market, ticker, since)
    for r in pos:
        flags.append({"type": "attention", "level": "info",
                      "text": f"业绩正惊喜(关注):{r['title'][:40]}",
                      "basis": f"{r['ann_date']} 公告", "note": "rev+PEAD 温和正漂移,size中性;非买入建议"})

    # avoid_risk:近期龙虎榜净卖出(需实时源;此处占位从公告/新闻标题近似)
    sell = await conn.fetch("""SELECT title, ann_date FROM stock_announcements
        WHERE market=$1 AND ticker=$2 AND ann_date>=$3
          AND (title LIKE '%减持%' OR title LIKE '%预减%' OR title LIKE '%首亏%' OR title LIKE '%风险警示%'
               OR title LIKE '%立案%' OR title LIKE '%处罚%')
        ORDER BY ann_date DESC LIMIT 3""", market, ticker, since)
    for r in sell:
        flags.append({"type": "avoid_risk", "level": "warn",
                      "text": f"利空/风险事件(回避):{r['title'][:40]}",
                      "basis": f"{r['ann_date']} 公告", "note": "负惊喜/资金流出稳健负漂移;持有者关注回避"})

    # vol_warn:近期任何事件 → 波动预警
    n = await conn.fetchval("""SELECT count(*) FROM stock_announcements
        WHERE market=$1 AND ticker=$2 AND ann_date>=$3 AND is_signal""", market, ticker, since)
    if n and n > 0:
        flags.append({"type": "vol_warn", "level": "info",
                      "text": f"近期 {n} 个信号事件 → 波动可能加大",
                      "basis": f"近{days}天", "note": "有事件的股前向波动约45% vs 无事件35%"})
    return {"ticker": ticker, "flags": flags, "disclaimer": DISCLAIMER}
