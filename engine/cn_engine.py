#!/usr/bin/env python3
"""
cn_engine.py — Sentinel A股 每日快照引擎(v2.0 双市场)
=====================================================
复用 safna_jr_a(R1-R47)已验证逻辑,产出与 schema.md 对齐的 A股 snapshot(market="cn"):
  选股 = 头号腿(小市值×低换手·剔ST·双周)[R7/R45]  (+ rev+PEAD 事件腿,可选 [R19])
  趋势分档 = 市场级优化分档 GATE(宽度∧拥挤∧成交额未枯竭∧非小盘背离,WF Cal0.66)[阶段G R41]
  逐票档 = 只展示趋势状态,不减仓(A股反转,美股式逐票减仓是灾难 R36)
  到价概率 = 波动缩放经验分布·滚动窗(区间校准良好 R46)
诚实定位:决策支持,非自动交易。研究推演,非投资建议。
用法:python cn_engine.py [--asof latest|YYYY-MM-DD] [--capital 100000]
数据:engine/data_cn(软链 safna_jr_a/data/daily)。
"""
import sys, os, json, argparse
import numpy as np
import pandas as pd

SAFNA_A = "/Users/lugia/lugia_fc/safna_jr_a"
sys.path.insert(0, os.path.join(SAFNA_A, "lib"))
import engine as E          # noqa  A股回测引擎(load_matrices/metrics)
import legs as L            # noqa  头号腿+masks
import timing as T          # noqa  择时/分档信号

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "data")
UNIV = os.path.join(SAFNA_A, "data", "meta", "universe.csv")
N_HOLD = 50
DISCLAIMER = "研究工具,非投资建议"


def _names():
    try:
        u = pd.read_csv(UNIV).set_index("code")["code_name"]
        return u.to_dict()
    except Exception:
        return {}


def vol_scaled_prob(M, code, ci, h=20, win=500):
    """到价概率:该股 vol 缩放经验分布(滚动win日,区间预测)。返回 h20 dict。"""
    C = M["close"][code].dropna()
    if len(C) < 120:
        return None
    r = C.pct_change()
    vol = r.rolling(63).std().iloc[-1]
    if not np.isfinite(vol) or vol <= 0:
        return None
    px = float(C.iloc[-1]); hv = vol * np.sqrt(h)
    # 该股历史标准化前瞻收益(滚动win,无前视)
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


def trend_grade_cn(M, code, ci):
    """逐票趋势状态(仅展示,不减仓)。A股反转市,美式减仓有害(R36)→ action恒'持有'。"""
    C = M["close"][code].dropna()
    if len(C) < 200:
        return 0, "数据不足", [], 1.0
    c = float(C.iloc[-1]); s20 = C.tail(20).mean(); s50 = C.tail(50).mean(); s200 = C.tail(200).mean()
    sigs = []
    def add(name, ok, detail): sigs.append(dict(name=name, detail=detail, verdict="多" if ok else "空"))
    add("站上20日线", c > s20, f"现价{c:.2f} vs 20日线{s20:.2f}")
    add("站上60日线", c > C.tail(60).mean(), f"现价{c:.2f} vs 60日线{C.tail(60).mean():.2f}")
    add("站上200日线", c > s200, f"现价{c:.2f} vs 200日线{s200:.2f}")
    score = sum(1 if x["verdict"] == "多" else -1 for x in sigs)
    grade = int(np.clip(round(score * 3 / 3), -3, 3))
    label = {3: "偏强", 2: "偏强", 1: "中性", 0: "中性", -1: "转弱", -2: "走弱", -3: "弱势"}.get(grade, "中性")
    # ★A股:逐票不减仓,action恒持有,乘数1.0(市场级Gate管风险)
    return grade, label, sigs, 1.0


def compute_gate_cn(M):
    """市场级优化分档(阶段G R41):宽度∧拥挤∧成交额未枯竭∧非小盘背离 → 3档exposure+风险灯。"""
    br = T.breadth(M, 60); brma = br.rolling(40).mean()
    cr = T.crowding(M, 0.30, 500)["index"]
    amt = T.amount_regime(M, 5, 60)
    sbr = T.layer_breadth(M, 0.0, 0.20, 60); sbrma = sbr.rolling(40).mean()
    bbr = T.layer_breadth(M, 0.80, 1.0, 60)
    b_now = float(br.iloc[-1]); bma_now = float(brma.iloc[-1])
    c_now = float(cr.iloc[-1]); a_now = float(amt.iloc[-1])
    diverge = bool((bbr.iloc[-1] > 0.4) and (sbr.iloc[-1] < sbrma.iloc[-1]) and ((sbr.iloc[-1] - bbr.iloc[-1]) < 0))
    wide_on = b_now > bma_now
    not_crowd = c_now <= 0.85
    liq_ok = a_now > 0.85
    # 3档:满(全过)/半(宽度on但成交额或背离警示)/空(宽度off或拥挤)
    if wide_on and not_crowd and liq_ok and not diverge:
        expo, level, note = 1.0, "green", "宽度强+流动性足+无背离 → 满仓"
    elif wide_on and not_crowd:
        expo, level, note = 0.5, "amber", "宽度on但成交额枯竭或小盘背离警示 → 半仓"
    else:
        expo, level, note = 0.0, "red", ("宽度弱(risk-off)" if not wide_on else "微盘拥挤") + " → 空仓观望"
    return dict(level=level, bench_breadth=round(b_now, 3), breadth_ma=round(bma_now, 3),
                crowd_pct=round(c_now, 3), amount_ratio=round(a_now, 3), diverge=diverge,
                exposure=expo, note=note)


def headline_pick(M):
    """头号腿选股:tradable∧剔ST∧小市值分位≤20% 内按20日均换手升序取前N。返回 [(code,turn,fmc)]。"""
    m = L.masks(M); turn20 = M["turn"].rolling(20).mean()
    sig = (-turn20).where(m["tr"] & m["st"] & m["small"] & M["in_market"])
    row = sig.iloc[-1].dropna().sort_values(ascending=False)
    codes = row.head(N_HOLD).index.tolist()
    fmc = M["fmc"].iloc[-1]; tn = turn20.iloc[-1]
    return [(c, float(tn[c]), float(fmc[c]) / 1e8) for c in codes]


def compute_snapshot_cn(asof=None, capital=100000.0):
    # 载入近~4年面板(足够 rolling500 拥挤 + 指标),到 asof
    end = None if (asof in (None, "latest")) else asof
    start = "2021-01-01" if end is None else str((pd.Timestamp(end) - pd.Timedelta(days=1500)).date())
    M = E.load_matrices(start=start, end=end, min_days=250)
    C = M["close"]; last = C.index[-1]
    names = _names()
    gate = compute_gate_cn(M)
    picks = headline_pick(M)
    px = C.iloc[-1]
    holds = []
    w = 1.0 / max(1, len(picks))
    for rank, (code, turn, fmc_yi) in enumerate(picks, 1):
        grade, glabel, sigs, aw = trend_grade_cn(M, code, None)
        prob = vol_scaled_prob(M, code, None)
        price = float(px[code]) if code in px.index and np.isfinite(px[code]) else None
        holds.append(dict(
            ticker=code, name=names.get(code, ""), sleeve="smallcap", price=price,
            base_weight=round(w, 4), target_shares=round(capital * w * gate["exposure"] / price, 1) if price else 0,
            target_value=round(capital * w * gate["exposure"], 1),
            grade=grade, grade_label=glabel, action="持有", action_weight=aw,
            prob=dict(h20=prob) if prob else {},
            reason=f"头号腿·小市值×低换手(池内低换手第{rank}) 流通{fmc_yi:.1f}亿/20日换手{turn:.2f}%",
            signals=sigs,
            indicators=dict(float_mktcap_yi=round(fmc_yi, 1), turn20=round(turn, 2)),
        ))
    snap = dict(
        market="cn", asof=str(last.date()), generated_at=str(pd.Timestamp("today").date()),
        capital=capital, disclaimer=DISCLAIMER,
        risk_light=dict(level=gate["level"], exposure=gate["exposure"], note=gate["note"],
                        bench_breadth=gate["bench_breadth"], crowd_pct=gate["crowd_pct"],
                        amount_ratio=gate["amount_ratio"], diverge=gate["diverge"]),
        holdings=holds,
        portfolio=dict(n_holdings=len(holds), gross_exposure=gate["exposure"],
                       cash_pct=round(1 - gate["exposure"], 2), rebalance="双周", next_rebalance=""),
        strategy_config=dict(market="cn", selector="cn_smallcap_lowturn", gate="cn_breadth_crowding_optimized",
                             grader="cn_display_only", predictor="vol_scaled_rolling"),
    )
    return snap, M


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default="latest")
    ap.add_argument("--capital", type=float, default=100000.0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    snap, _ = compute_snapshot_cn(a.asof, a.capital)
    os.makedirs(OUT_DIR, exist_ok=True)
    fps = [os.path.join(OUT_DIR, f"snapshot_cn_{snap['asof']}.json"),
           os.path.join(OUT_DIR, "snapshot_cn_latest.json")]
    for fp in fps:
        json.dump(snap, open(fp, "w"), ensure_ascii=False, indent=2)
    print(f"SAVED {fps[0]}")
    print(f"  market={snap['market']} asof={snap['asof']} 风险灯={snap['risk_light']['level']} "
          f"exposure={snap['risk_light']['exposure']} 持仓={snap['portfolio']['n_holdings']}")
    print(f"  {snap['risk_light']['note']}")
    print(f"  样例持仓: {[(h['ticker'], h['name'], h['grade_label']) for h in snap['holdings'][:3]]}")


if __name__ == "__main__":
    main()
