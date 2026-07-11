#!/usr/bin/env python3
"""
focus_cn.py — A股单股观察:对任意 A股代码(即便非策略选中)用【与 cn_engine 同一套】
趋势档位(20/60/200 三信号,仅展示不减仓)+ 到价概率(波动缩放经验分布 h20)分析。
轻量实现:直接读 engine/data_cn/<sh_600000>.csv 单只数据,不加载全市场面板(秒级)。
输出单持仓 JSON 到 stdout,供后端 warmFocus / /api/focus?market=cn。

用法:python focus_cn.py sh.600000 [--asof latest] [--capital 100000]
"""
import os, json, argparse
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_CN = os.path.join(HERE, "data_cn")
UNIV = os.path.join(HERE, "data_cn_meta", "universe.csv")


def _name_of(code):
    try:
        u = pd.read_csv(UNIV).set_index("code")["code_name"]
        return str(u.get(code, ""))
    except Exception:
        return ""


def _load(code, asof):
    fp = os.path.join(DATA_CN, code.replace(".", "_") + ".csv")
    if not os.path.exists(fp):
        return None
    df = pd.read_csv(fp, parse_dates=["date"]).set_index("date").sort_index()
    if asof not in (None, "latest"):
        df = df.loc[:pd.Timestamp(asof)]
    df = df[np.isfinite(df["close"])]
    return df if len(df) else None


def trend_grade_cn(C):
    """与 cn_engine.trend_grade_cn 同口径:站上 20/60/200 日线,3 信号求和;A股逐票不减仓,action 恒'持有'。"""
    if len(C) < 200:
        return 0, "数据不足", [], 1.0
    c = float(C.iloc[-1]); s20 = C.tail(20).mean(); s60 = C.tail(60).mean(); s200 = C.tail(200).mean()
    sigs = []
    def add(name, ok, detail): sigs.append(dict(name=name, detail=detail, verdict="多" if ok else "空"))
    add("站上20日线", c > s20, f"现价{c:.2f} vs 20日线{s20:.2f}")
    add("站上60日线", c > s60, f"现价{c:.2f} vs 60日线{s60:.2f}")
    add("站上200日线", c > s200, f"现价{c:.2f} vs 200日线{s200:.2f}")
    score = sum(1 if x["verdict"] == "多" else -1 for x in sigs)
    grade = int(np.clip(score, -3, 3))
    label = {3: "偏强", 2: "偏强", 1: "中性", 0: "中性", -1: "转弱", -2: "走弱", -3: "弱势"}.get(grade, "中性")
    return grade, label, sigs, 1.0


def vol_scaled_prob(C, h=20, win=500):
    """与 cn_engine.vol_scaled_prob 同口径:该股 vol 缩放经验分布(滚动 win 日,区间预测)。"""
    if len(C) < 120:
        return None
    r = C.pct_change()
    vol = r.rolling(63).std().iloc[-1]
    if not np.isfinite(vol) or vol <= 0:
        return None
    px = float(C.iloc[-1]); hv = vol * np.sqrt(h)
    fwd = C.shift(-h) / C - 1.0
    z = (fwd / (r.rolling(63).std() * np.sqrt(h))).dropna()
    z = z[np.abs(z) < 10].tail(win)
    if len(z) < 60:
        return None
    med = float(z.median()); b70 = [float(z.quantile(.15)), float(z.quantile(.85))]
    tgt_z, stop_z = 1.0, -1.0
    return dict(
        median=round(med * hv, 4),
        band70=[round(b70[0] * hv, 4), round(b70[1] * hv, 4)],
        target=round(px * (1 + tgt_z * hv), 2), stop=round(px * (1 + stop_z * hv), 2),
        p_hit_target=round(float((z >= tgt_z).mean()), 3),
        p_hit_stop=round(float((z <= stop_z).mean()), 3),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--asof", default="latest")
    ap.add_argument("--capital", type=float, default=100000.0)
    args = ap.parse_args()
    code = args.ticker.strip().lower()

    df = _load(code, args.asof)
    if df is None:
        print(json.dumps({"error": f"{code} 不在A股数据池(确认代码形如 sh.600000 / sz.000001)"}, ensure_ascii=False))
        return
    C = df["close"]
    asof = C.index[-1]
    grade, glabel, sigs, aw = trend_grade_cn(C)
    prob = vol_scaled_prob(C)
    px = float(C.iloc[-1])
    # 指标:20日均换手;流通市值 ≈ 成交额/换手率(近似,亿)
    turn20 = None
    fmc_yi = None
    if "turn" in df.columns:
        t = df["turn"].tail(20)
        t = t[np.isfinite(t) & (t > 0)]
        if len(t):
            turn20 = round(float(t.mean()), 2)
        last = df[np.isfinite(df.get("turn", np.nan)) & (df.get("turn", 0) > 0)].tail(1)
        if len(last) and "amount" in df.columns and np.isfinite(last["amount"].iloc[0]):
            fmc_yi = round(float(last["amount"].iloc[0] / (last["turn"].iloc[0] / 100.0)) / 1e8, 1)

    holding = dict(
        ticker=code, name=_name_of(code), sleeve="focus", price=round(px, 2), base_weight=1.0,
        target_shares=round(args.capital / px, 1) if px > 0 else 0, target_value=round(args.capital, 2),
        grade=grade, grade_label=glabel, action="持有", action_weight=aw,
        prob=dict(h20=prob) if prob else {},
        reason="用户自定义 · 单股观察(A股同口径:20/60/200趋势档位仅展示,逐票不减仓,风险由市场级风险灯统一管)",
        signals=sigs,
        indicators=dict(float_mktcap_yi=fmc_yi, turn20=turn20),
    )
    print(json.dumps(dict(asof=str(asof.date()), ticker=code, holding=holding), ensure_ascii=False))


if __name__ == "__main__":
    main()
