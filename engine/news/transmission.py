"""
transmission.py — 全球事件→A股传导映射(news_lab R12)
====================================================
把"海外/全球主题 → A股受影响板块 + 提前/滞后 + 机制"显式编码。领域知识 seed,可 AI/回测迭代。
lead_lag: 相对 A股的时序(天)。负=海外先行(A股滞后 N 天反应);0≈同步;正=A股先行/海外滞后。
  例:美联储决议海外隔夜公布 → A股次日经北向反应 → lead_lag=-1(海外先行1天)。
每个主题带 GDELT 查询词(英文一手)+ A股板块 + 方向倾向 + 机制说明。
"""

# theme: {query(GDELT英文查询), cn_sectors, lead_lag, mechanism, tone_hint}
TRANSMISSION = [
    # ── 政治性 ──
    dict(theme="芯片出口管制", query="semiconductor export control China",
         cn_sectors=["半导体", "国产替代", "集成电路"], lead_lag=-1,
         mechanism="美对华芯片/设备管制→被管制环节利空,但强化国产替代逻辑(利好本土设备/材料/EDA)",
         tone_hint="mixed"),
    dict(theme="中美关税贸易", query="US China tariff trade",
         cn_sectors=["出口链", "跨境电商", "航运", "纺织"], lead_lag=-1,
         mechanism="关税/贸易摩擦→出口导向行业利空;转口贸易国(越南/墨西哥)受益转移",
         tone_hint="利空"),
    dict(theme="地缘冲突中东", query="Middle East conflict Iran Israel oil",
         cn_sectors=["石油石化", "军工", "黄金"], lead_lag=-1,
         mechanism="中东冲突隔夜升级→次日 A股石油/军工/黄金避险受益,整体风险偏好承压",
         tone_hint="mixed"),
    # ── 宏观×政治 ──
    dict(theme="美联储货币政策", query="Federal Reserve interest rate decision",
         cn_sectors=["大盘", "外资重仓", "黄金", "券商"], lead_lag=-1,
         mechanism="美联储隔夜决议→次日经北向资金/美元汇率传导A股;降息利好外资回流/黄金",
         tone_hint="mixed"),
    dict(theme="美国通胀数据", query="US CPI inflation data",
         cn_sectors=["大盘", "外资重仓"], lead_lag=-1,
         mechanism="美CPI隔夜公布→影响美联储路径预期→次日经风险偏好/汇率传导",
         tone_hint="mixed"),
    # ── 行业性(全球产业链)──
    dict(theme="锂电新能源车海外", query="lithium battery EV sales global",
         cn_sectors=["锂电池", "新能源车", "储能"], lead_lag=0,
         mechanism="海外EV销量/电池技术/政策→A股锂电产业链(宁德/比亚迪链)近同步反应",
         tone_hint="mixed"),
    dict(theme="AI算力芯片", query="AI chip Nvidia data center",
         cn_sectors=["算力", "AI", "光模块", "服务器"], lead_lag=-1,
         mechanism="英伟达/海外算力需求→A股算力链(光模块/服务器/PCB)次日跟随",
         tone_hint="利好"),
    dict(theme="光伏海外需求", query="solar photovoltaic demand policy",
         cn_sectors=["光伏"], lead_lag=0,
         mechanism="海外装机/贸易政策→A股光伏(组件出口占比高)",
         tone_hint="mixed"),
    dict(theme="创新药出海", query="China biotech drug FDA license deal",
         cn_sectors=["创新药", "CXO"], lead_lag=0,
         mechanism="海外授权/FDA/BD交易→A股创新药+CXO",
         tone_hint="利好"),
    # ── 大宗商品(近同步/A股滞后)──
    dict(theme="原油价格", query="crude oil price OPEC",
         cn_sectors=["石油石化", "油服"], lead_lag=0,
         mechanism="国际油价→A股石油链近同步;成本端影响航空/化工",
         tone_hint="mixed"),
    dict(theme="铜价有色", query="copper price supply demand",
         cn_sectors=["有色金属", "铜"], lead_lag=0,
         mechanism="LME铜价→A股有色近同步",
         tone_hint="mixed"),
    dict(theme="黄金", query="gold price safe haven",
         cn_sectors=["黄金", "贵金属"], lead_lag=0,
         mechanism="国际金价→A股黄金股近同步",
         tone_hint="mixed"),
    dict(theme="铁矿石钢铁", query="iron ore steel price China demand",
         cn_sectors=["钢铁", "铁矿"], lead_lag=0,
         mechanism="铁矿石价格→A股钢铁成本/利润",
         tone_hint="mixed"),
    dict(theme="稀土磁材", query="rare earth China export quota",
         cn_sectors=["稀土", "磁材"], lead_lag=1,
         mechanism="中国是稀土主产→常A股/国内政策先行,海外报道滞后(lead_lag=+1)",
         tone_hint="利好"),
    # ── 气候性(滞后,经作物/能源传导)──
    dict(theme="干旱农业", query="drought crop harvest agriculture",
         cn_sectors=["种业", "农业", "食品"], lead_lag=-14,
         mechanism="海外/国内旱情→作物减产预期→数周内农产品价格→种业/农业(滞后约2周)",
         tone_hint="利好"),
    dict(theme="极端天气能源", query="cold wave heatwave energy demand",
         cn_sectors=["电力", "煤炭", "天然气"], lead_lag=-3,
         mechanism="寒潮/热浪→用电用气激增→数日内能源价格/电力板块",
         tone_hint="利好"),
    dict(theme="厄尔尼诺气候", query="El Nino La Nina weather commodity",
         cn_sectors=["农业", "种业", "白糖"], lead_lag=-30,
         mechanism="厄尔尼诺→全球农业气候异常→软商品价格(滞后约1月+)",
         tone_hint="mixed"),
]


def lead_lag_label(d):
    if d < -1:
        return f"海外先行约{-d}天(A股滞后反应)"
    if d == -1:
        return "海外隔夜先行(A股次日反应)"
    if d == 0:
        return "近同步"
    return f"A股/国内先行约{d}天(海外报道滞后)"
