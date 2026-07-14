#!/usr/bin/env python3
"""R18 全球传导 lead/lag 回测:全球触发序列(yfinance)× A股板块篮子(自建)→ 测同步/滞后相关。
验 R12 传导映射:原油→石油、黄金→黄金股、铜→有色、标普→大盘的 lead/lag 是否真实。
时区:美股/大宗收于 A股之后 → 全球 T 日的动作,A股 T+1 才能反应(LEAD)。"""
import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
import yfinance as yf
from eventstudy import Panel

M = Panel.load(start="2018-01-01")
C = M["close"]

# A股板块篮子(代表股,归一码匹配面板列)
BASKETS = {
    "石油石化": ["601857", "600028", "601808", "600583", "000059"],
    "黄金": ["600547", "601899", "600489", "000975", "600988"],
    "有色铜": ["000630", "000878", "600362", "601600", "000060"],
    "大盘": None,  # 全市场等权
}
GLOBAL = {"原油": "CL=F", "黄金": "GC=F", "铜": "HG=F", "标普": "^GSPC", "美元": "DX-Y.NYB"}


def basket_ret(codes):
    if codes is None:
        return M["ret1"].mean(axis=1)
    cols = []
    for c in codes:
        for pre in ("sh.", "sz."):
            if pre + c in C.columns:
                cols.append(pre + c)
    if not cols:
        return None
    return M["ret1"][cols].mean(axis=1)


# 全球日收益(按 A股交易日对齐:全球 T 日 → 映射到 A股下一个交易日)
adates = C.index
grets = {}
for name, sym in GLOBAL.items():
    h = yf.Ticker(sym).history(start="2018-01-01")
    r = h["Close"].pct_change()
    r.index = r.index.tz_localize(None)
    grets[name] = r

print("\n##### R18 全球→A股板块 传导 lead/lag(相关系数 × 100)#####")
print("(行=全球触发, 列=A股板块; lag0=同A股日, lag1=A股次日反应=海外先行)")
for gname, gr in grets.items():
    # 把全球收益对齐到 A股交易日(reindex ffill 到最近全球日)
    g_on_a = gr.reindex(adates, method="ffill")
    line = []
    for bname, codes in BASKETS.items():
        br = basket_ret(codes)
        if br is None:
            line.append(f"{bname}:NA"); continue
        # lag0:同日相关;lag1:A股次日 vs 全球今日(海外先行1天)
        c0 = g_on_a.corr(br)
        c1 = g_on_a.corr(br.shift(-1))  # br 次日
        line.append(f"{bname}[同步{c0*100:+.0f}/次日{c1*100:+.0f}]")
    print(f"  {gname:5s} → " + "  ".join(line), flush=True)
