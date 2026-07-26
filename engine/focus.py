#!/usr/bin/env python3
"""
focus.py — 单股观察:对任意 ticker(即便非AI选中)用【同一套档位/预测规则】分析,
资金池全给这一只(看它自己的趋势/概率)。复用可插拔框架(Context+Grader+Predictor)。
不跑选股/SY(focus 无需选股)。输出单持仓 JSON 到 stdout,供后端 /api/focus。

用法:uv run python focus.py TICKER [--asof latest] [--capital 4000]
"""
import sys, os, json, argparse
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_daily as R
from strategies import Context, GRADERS, PREDICTORS, GATES, STRATEGY_CONFIG


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--asof", default="latest")
    ap.add_argument("--capital", type=float, default=4000.0)
    args = ap.parse_args()
    tk = args.ticker.upper()

    # 只加载这一只 + SPY(不再全池 1393 加载),内存从 ~2.7GB 降到 ~50MB
    uni, spy, master, _ = R.load_all(with_sy=False, tickers=[tk], recent=300)
    if tk not in uni:
        print(json.dumps({"error": f"{tk} 不在数据池(暂无该股数据,实时源接入后可支持)"}, ensure_ascii=False))
        return
    asof = R.resolve_asof(uni, args.asof)
    ctx = Context(uni, spy, master, None, asof, args.capital, with_sy=False)
    r = ctx.row(tk)
    if r is None or pd.isna(r["close"]):
        print(json.dumps({"error": f"{tk} 在 {asof.date()} 无收盘数据"}, ensure_ascii=False))
        return

    grader = GRADERS[STRATEGY_CONFIG["grader"]]
    predictor = PREDICTORS[STRATEGY_CONFIG["predictor"]]
    gate = GATES[STRATEGY_CONFIG["gate"]].evaluate(ctx)
    gd = grader.grade(tk, ctx)
    px = float(r["close"]); v63 = ctx.vol63(tk)
    exposure = gate.pop("exposure_raw", gate["exposure"])
    holding = dict(
        ticker=tk, sleeve="focus", price=round(px, 2), base_weight=1.0,
        target_shares=round(args.capital * exposure / px, 3), target_value=round(args.capital * exposure, 2),
        grade=gd["grade"], grade_label=gd["grade_label"], action=gd["action"], action_weight=gd["action_weight"],
        prob=predictor.predict(tk, ctx),
        reason="用户自定义 · 单股观察(资金池全押这一只,同样的档位/概率规则)",
        signals=gd["signals"],
        indicators=dict(
            mom126=round(float(r["mom126"]), 4) if not pd.isna(r["mom126"]) else None,
            mom21=round(float(r["mom21"]), 4) if not pd.isna(r["mom21"]) else None,
            vol_annual=round(float(v63 * np.sqrt(252)), 4) if v63 else None,
            sma20=round(float(r["sma20"]), 2), sma50=round(float(r["sma50"]), 2), sma200=round(float(r["sma200"]), 2),
            pct_from_high=round(float(r["pct_from_high"]), 4), sy_yield=None,
        ))
    print(json.dumps(dict(asof=str(asof.date()), ticker=tk, risk_light=gate, holding=holding),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
