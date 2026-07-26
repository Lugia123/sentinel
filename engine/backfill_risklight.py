#!/usr/bin/env python3
"""向量化回算 A股风险灯(市场级Gate)历史 → JSON,供灌入 risk_light_history 表。
compute_gate_cn 的宽度/拥挤/成交额/背离都是完整时间序列(当天只取 .iloc[-1]),
这里对每个交易日套同一套阈值逻辑,产出整条历史。与生产快照口径一致。
用法:python backfill_risklight.py [--year 2026] [--out /tmp/rl_hist.json]
     (需 baostock data_cn;算 rolling500 拥挤需更早warmup,故 load 从 2016 起)
"""
import os, sys, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import cn_engine as ce
E, T = ce.E, ce.T


def gate_history(M):
    """返回 DataFrame(index=交易日):level/exposure/breadth/breadth_ma/crowd/amount_ratio/diverge。"""
    br = T.breadth(M, 60); brma = br.rolling(40).mean()
    cr = T.crowding(M, 0.30, 500)["index"]
    amt = T.amount_regime(M, 5, 60)
    sbr = T.layer_breadth(M, 0.0, 0.20, 60); sbrma = sbr.rolling(40).mean()
    bbr = T.layer_breadth(M, 0.80, 1.0, 60)
    idx = br.index
    wide_on = br > brma
    not_crowd = cr <= 0.85
    liq_ok = amt > 0.85
    diverge = (bbr > 0.4) & (sbr < sbrma) & ((sbr - bbr) < 0)
    green = wide_on & not_crowd & liq_ok & (~diverge)
    amber = wide_on & not_crowd & (~green)
    level = np.where(green, "green", np.where(amber, "amber", "red"))
    expo = np.where(green, 1.0, np.where(amber, 0.5, 0.0))
    return pd.DataFrame({
        "asof": idx.strftime("%Y-%m-%d"),
        "level": level, "exposure": expo,
        "breadth": br.round(4).values, "breadth_ma": brma.round(4).values,
        "crowd": cr.round(4).values, "amount_ratio": amt.round(4).values,
        "diverge": diverge.values,
    }, index=idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--out", default="/tmp/rl_hist_cn.json")
    a = ap.parse_args()
    print("加载 A股 M(2016+ warmup)…", flush=True)
    M = E.load_matrices(start=f"{a.year-3}-01-01")   # 仅需~2年warmup(crowding rolling500),轻4倍
    g = gate_history(M)
    # 只保留目标年、且已成熟(brma 需40日、crowd 需500日 warmup → dropna)
    g = g[g["breadth_ma"].notna() & g["crowd"].notna()]
    sel = g[g.index.year == a.year].copy()
    rows = [dict(market="cn", **{k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in r.items()})
            for r in sel.to_dict("records")]
    json.dump(rows, open(a.out, "w"), ensure_ascii=False)
    # 分布 + 抽样(校验用)
    from collections import Counter
    print(f"{a.year} A股: {len(rows)}天 分布={dict(Counter(r['level'] for r in rows))}", flush=True)
    print("近端抽样(校验对齐现有快照 07-24=0.083/07-23=0.12):", flush=True)
    for r in rows[-6:]:
        print(f"  {r['asof']} {r['level']} 宽度{r['breadth']} vs MA{r['breadth_ma']} 拥挤{r['crowd']} 暴露{r['exposure']}", flush=True)
    print(f"→ {a.out}", flush=True)


if __name__ == "__main__":
    main()
