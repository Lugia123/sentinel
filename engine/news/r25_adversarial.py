#!/usr/bin/env python3
"""R25 对抗稳健性:①严格PIT(信号=两事件都已知的较晚日,进场T+1,消除前视)②参数扰动③子样本。"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eventstudy import Panel, event_study, load_yjyg
ALT = os.path.join(os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")), "alt")
M = Panel.load(start="2014-01-01")
C = M["close"]; dates = C.index


def to_col(c):
    c = str(c).zfill(6); return ("sh." if c[0] == "6" else "bj." if c[0] in ("4", "8") else "sz.") + c


y = load_yjyg(); yz = y[y["type"] == "预增"][["code", "date"]].copy()
yz["date"] = pd.to_datetime(yz["date"]); yz["col"] = yz["code"].map(to_col)
yz = yz[yz["col"].isin(set(C.columns))]
lhb = pd.read_parquet(f"{ALT}/lhb.parquet"); lhb["net"] = pd.to_numeric(lhb["龙虎榜净买额"], errors="coerce")
lb = lhb[lhb["net"] > 0][["代码", "上榜日"]].dropna(); lb["col"] = lb["代码"].map(to_col); lb["d"] = pd.to_datetime(lb["上榜日"])
lbmap = {}
for _, r in lb.iterrows():
    lbmap.setdefault(r["col"], []).append(r["d"])


def build_resonance(win, pit_mode):
    """pit_mode: 'lookahead'=旧(±win, 事件日=预增日) / 'strict'=信号日=两事件较晚日。"""
    rows = []
    for _, r in yz.iterrows():
        ds = [d for d in lbmap.get(r["col"], []) if abs((d - r["date"]).days) <= win]
        if not ds:
            continue
        if pit_mode == "strict":
            # 只用 [预增-win, 预增] 或事件都已知:信号日 = max(预增, 最近的已发生龙虎榜)
            past = [d for d in ds if d <= r["date"] + pd.Timedelta(days=0)]  # 龙虎榜<=预增(或反过来取max)
            sig_date = max([r["date"]] + ds)  # 两事件都已知的最晚日
            rows.append({"code": r["code"], "date": sig_date})
        else:
            rows.append({"code": r["code"], "date": r["date"]})
    return pd.DataFrame(rows)


print("\n##### R25a 前视复查:旧(lookahead) vs 严格PIT #####")
for mode in ["lookahead", "strict"]:
    res = build_resonance(5, mode)
    event_study(M, res, ks=(5, 10), label=f"共振·{mode}(win5)", size_neutral=True, min_n=30)

print("\n##### R25b 参数扰动:窗口 3/5/10(严格PIT)#####")
for win in (3, 5, 10):
    res = build_resonance(win, "strict")
    event_study(M, res, ks=(10,), label=f"共振·strict·win{win}", size_neutral=True, min_n=30)

print("\n##### R25c 子样本:前半(≤2019) vs 后半(≥2020)(严格PIT win5)#####")
res = build_resonance(5, "strict")
res["date"] = pd.to_datetime(res["date"])
event_study(M, res[res["date"] < "2020-01-01"], ks=(10,), label="共振·前半≤2019", size_neutral=True, min_n=30)
event_study(M, res[res["date"] >= "2020-01-01"], ks=(10,), label="共振·后半≥2020", size_neutral=True, min_n=30)

print("\n##### R25d 完整性 critic:遗漏的证伪路径 #####")
print("""  已查:安慰剂无偏(R13)/size中性(R14+)/中位数去尾(R17)/真实摩擦+涨停(R22)/beta调整(R23)/
        拥挤衰减(R24)/前视(R25a)/参数(R25b)/子样本(R25c)。
  未查但需承认的残余风险:
   ① 龙虎榜数据本身可能有幸存者/披露口径变化(2016前后规则变);
   ② 事件腿高beta+MDD50%,极端市场(2015/2018股灾)可能爆亏,回测未含个股停牌无法卖的流动性黑洞;
   ③ 共振稀疏(128/年),任一年样本小,单年可证伪(2024中位负);
   ④ 未含冲击成本(仅印花税+佣金),40只小盘聚焦腿实盘冲击成本会吃掉部分alpha。""")
