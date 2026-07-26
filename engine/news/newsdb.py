"""news 域共享:PG 连接(复用 server/.env 的 SENTINEL_DB_DSN)+ 公告白名单(R2)。"""
import os, re, hashlib

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "server", ".env")


def parse_dsn():
    dsn = ""
    with open(ENV) as f:
        for line in f:
            if line.startswith("SENTINEL_DB_DSN="):
                dsn = line.split("=", 1)[1].strip()
    kv = dict(re.findall(r"(\w+)=(\S+)", dsn))
    return dict(host=kv.get("host", "localhost"), port=int(kv.get("port", 5432)),
                user=kv.get("user"), password=kv.get("password"), database=kv.get("dbname"))


def fp(*parts):
    """去重指纹:source+标题+发布时刻。"""
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8", "ignore")).hexdigest()


def norm_ticker(code):
    """裸码 → 归一化(sh.600000/sz.000021/bj.830799),与 Sentinel 其余部分一致。
    已带前缀的原样返回(小写)。6→sh,0/3→sz,4/8→bj。"""
    c = str(code).strip().lower()
    if c[:3] in ("sh.", "sz.", "bj."):
        return c
    c = c.zfill(6)
    if c[0] == "6":
        return "sh." + c
    if c[0] in ("0", "3"):
        return "sz." + c
    if c[0] in ("4", "8"):
        return "bj." + c
    return c


# 公告类型白名单(R2):对金融有影响 → is_signal=true。
ANN_WHITELIST = {
    "分配预案", "分配方案实施", "分配方案决议公告", "回购进展情况", "股权激励进展公告",
    "关联交易", "股份质押、冻结", "提供/对外担保公告", "月度经营情况", "限售股份上市流通",
    "股本变动", "高管人员任职变动", "年度报告全文", "年度报告摘要", "半年度报告全文",
    "半年度报告摘要", "三季度报告全文", "一季度报告全文", "募集资金使用情况报告",
}
# 标题关键词补识别(高价值但类型常归入"其他"/程序性类型)。R3 抽查迭代:补产能/异常波动等。
ANN_TITLE_KW = re.compile(
    r"中标|重大合同|框架协议|订单|资产重组|重大资产|收购|出售|剥离|诉讼|仲裁|处罚|问询函|关注函|"
    r"业绩预告|业绩快报|预增|预减|扭亏|首亏|减持|增持|回购|停牌|复牌|立案|调查|风险警示|退市|破产|重整|"
    r"异常波动|扩产|产能|投产|扩建|募投|中止|终止|解除|违规|担保|计提|减值|商誉")


def ann_is_signal(ann_type, title):
    """公告是否对金融有影响(白名单类型 或 标题命中关键词)。"""
    if ann_type in ANN_WHITELIST:
        return True
    return bool(ANN_TITLE_KW.search(title or ""))
