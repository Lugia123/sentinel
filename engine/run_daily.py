#!/usr/bin/env python3
"""
run_daily.py — Sentinel 每日快照引擎
=====================================
复用 safna_jr(R1–R35)已验证逻辑,产出 data/snapshot_<asof>.json:
  选股 = 动量哨兵(窄98趋势门)50 / SY 股东收益率(宽池)50     [R24/R28]
  定仓 = 风险平价(逆波动)按资金池                          [R35]
  档位 = 7档趋势状态(-3..+3),松·只减跟法(只减不追涨)      [R35 v4]
  概率 = 波动缩放经验分布 5/20/60日(校准)                  [R33]
  风险灯 = 波动目标体制闸                                    [R30]

诚实定位:决策支持,非自动交易;方向不可预测,概率=离散度校准非方向预言。
用法:python run_daily.py [--asof latest|YYYY-MM-DD] [--capital 4000] [--no-sy]
数据:engine/data(软链 safna_jr/round20/data_broad);SY 走 SEC EDGAR PIT(round24 fp)。
"""
import sys, os, json, argparse
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import backtest_lib2 as bl2                    # noqa
from champion import DATA_DIR_98               # noqa

DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(HERE, "data"))
OUT_DIR = os.path.join(os.path.dirname(HERE), "data")   # 快照产出目录(Go 后端按 SENTINEL_DATA 读,勿动)
SPY_PATH = os.path.join(DATA_DIR, "SPY.csv")
NARROW = set(f[:-4] for f in os.listdir(DATA_DIR_98) if f.endswith(".csv"))

sys.path.insert(0, HERE)
from strategies import (  # noqa 可插拔策略框架
    Context, SELECTORS, SIZERS, GRADERS, PREDICTORS, GATES, STRATEGY_CONFIG, active_manifest,
)


def _load_lite(tickers=None, min_date=None, recent=300):
    """轻量加载(省内存):只读 tickers(None=全部)的 CSV;每只算完指标后只留
    min_date 之后 或 近 recent 行,再存进字典——避免把 22 年 × 1393 只全驻留内存。
    指标在完整历史上算好再裁,近端值与全量加载完全一致。"""
    import glob
    import backtest_lib as bl  # 复用同一套指标计算 _add_indicators
    uni, all_dates = {}, set()
    if tickers:
        paths = [os.path.join(DATA_DIR, f"{t}.csv") for t in tickers]
        paths = [p for p in paths if os.path.exists(p)]
    else:
        paths = sorted(glob.glob(os.path.join(DATA_DIR, "*.csv")))

    def trim(df):
        if min_date is not None:
            return df[df["date"] >= pd.Timestamp(min_date)].reset_index(drop=True)
        if recent:
            return df.tail(recent).reset_index(drop=True)
        return df

    for path in paths:
        tkr = os.path.splitext(os.path.basename(path))[0]
        df = pd.read_csv(path)
        df["date"] = pd.to_datetime(df["date"])
        df = trim(bl._add_indicators(df))  # 先算指标(全历史)再裁,近端值不变
        if len(df):
            uni[tkr] = df
            all_dates.update(df["date"].tolist())
    spy = pd.read_csv(SPY_PATH)
    spy["date"] = pd.to_datetime(spy["date"])
    spy = spy.sort_values("date").reset_index(drop=True)
    spy["sma200"] = spy["close"].rolling(200).mean()
    spy["sma200_slope"] = spy["sma200"] - spy["sma200"].shift(10)
    spy = trim(spy)
    all_dates.update(spy["date"].tolist())
    return uni, spy, sorted(all_dates)


def load_all(with_sy=True, tickers=None, min_date=None, recent=300):
    """装一次数据 + fp。默认走轻量加载(recent=300 行,省内存);
    backfill 传 min_date(保留回填区间+回看窗口);focus 传 tickers=[单只]。"""
    uni, spy, master = _load_lite(tickers=tickers, min_date=min_date, recent=recent)
    fp = None
    if with_sy:
        from backtest_r24 import FundamentalsPITExtended
        fp = FundamentalsPITExtended(verbose=False)
    return uni, spy, master, fp


def resolve_asof(uni, target):
    """把目标日(latest 或 YYYY-MM-DD)解析成 <=目标 的最后一个交易日 Timestamp。"""
    a0 = next(iter(uni.values()))
    all_dates = pd.to_datetime(a0["date"]).tolist()
    if target == "latest":
        return all_dates[-1]
    t = pd.Timestamp(target)
    cand = [d for d in all_dates if d <= t]
    return max(cand) if cand else None


def compute_snapshot(uni, spy, master, fp, asof, capital=4000.0, with_sy=True, track=None):
    """纯计算:给定预载数据 + fp + asof(Timestamp),返回 (snap_dict, prices_out)。不写文件。
    track:用户"添加自定义股票"的代码列表,每天也算档位/概率(sleeve=custom,不占仓位)。"""
    # 流水线:Context → 选股 → 定仓 → 风险闸 → 每票档位/预测/指标(全走可插拔框架)
    ctx = Context(uni, spy, master, fp, asof, capital, with_sy)

    # 1) 各启用 Selector 选股
    all_picks = []
    for name in STRATEGY_CONFIG["selectors"]:
        sel = SELECTORS.get(name)
        if sel is None:
            continue
        try:
            all_picks.extend(sel.select(ctx))
        except Exception as e:
            print(f"选股 {name} 跳过({e})", flush=True)

    # 合并:每票 sleeve 集合 + 理由(按选股腿顺序)+ 各腿贡献的全池指标
    sleeves_of, reason_of, ind_contrib = {}, {}, {}
    for p in all_picks:
        sleeves_of.setdefault(p.ticker, []).append(p.sleeve)
        reason_of.setdefault(p.ticker, []).append(p.reason)
    for name in STRATEGY_CONFIG["selectors"]:
        sel = SELECTORS.get(name)
        if sel and hasattr(sel, "contribute_indicators"):
            for tk, d in sel.contribute_indicators(ctx).items():
                ind_contrib.setdefault(tk, {}).update(d)

    # 2) 定仓  3) 风险闸
    base = SIZERS[STRATEGY_CONFIG["sizer"]].size(all_picks, ctx)
    gate = GATES[STRATEGY_CONFIG["gate"]].evaluate(ctx)
    exposure = gate.pop("exposure_raw", gate["exposure"])  # sizing 用未舍入值(与重构前一致)
    grader = GRADERS[STRATEGY_CONFIG["grader"]]
    predictor = PREDICTORS[STRATEGY_CONFIG["predictor"]]

    # 4) 组装 holdings(每票 档位 + 预测 + 指标)
    holdings = []
    for tk in sorted(base, key=lambda t: -base[t]):
        r = ctx.row(tk)
        px = float(r["close"]); v63 = ctx.vol63(tk)
        gd = grader.grade(tk, ctx)
        sl = list(dict.fromkeys(sleeves_of.get(tk, [])))
        sleeve = "both" if len(sl) > 1 else (sl[0] if sl else "")
        tv = base[tk] * capital * exposure
        holdings.append(dict(
            ticker=tk, sleeve=sleeve, price=round(px, 2),
            base_weight=round(base[tk], 4),
            target_shares=round(tv / px, 3), target_value=round(tv, 2),
            grade=gd["grade"], grade_label=gd["grade_label"], action=gd["action"],
            action_weight=gd["action_weight"], prob=predictor.predict(tk, ctx),
            reason="；".join(reason_of.get(tk, [])),
            signals=gd["signals"],
            indicators=dict(
                mom126=round(float(r["mom126"]), 4) if not pd.isna(r["mom126"]) else None,
                mom21=round(float(r["mom21"]), 4) if not pd.isna(r["mom21"]) else None,
                vol_annual=round(float(v63 * np.sqrt(252)), 4) if v63 else None,
                sma20=round(float(r["sma20"]), 2), sma50=round(float(r["sma50"]), 2),
                sma200=round(float(r["sma200"]), 2),
                pct_from_high=round(float(r["pct_from_high"]), 4),
                sy_yield=ind_contrib.get(tk, {}).get("sy_yield"),
            )))
    POS = ctx.POS
    light = gate["level"]

    snap = dict(
        asof=str(asof.date()), generated_at=str(pd.Timestamp("today").date()),
        capital=capital, disclaimer="研究工具,非投资建议",
        risk_light=gate,
        strategy_config=active_manifest(),   # 当天启用了哪些策略(可追溯/可扩展)
        holdings=holdings,
        portfolio=dict(n_holdings=len(holdings),
                       gross_exposure=round(sum(h["target_value"] for h in holdings) / capital, 3),
                       cash_pct=round(1 - sum(h["target_value"] for h in holdings) / capital, 3)),
    )
    # 自定义追踪股:用户"添加自定义股票"的、不在策略选中里的,也每天算档位/概率,
    # 以 sleeve="custom"、目标股数0 追加(纳入每日追踪+走势历史,不占策略仓位)。
    # 空 track 时完全不变(保底:portfolio 已按策略持仓算好)。
    if track:
        held = {h["ticker"] for h in holdings}
        for tk in track:
            tk = str(tk).strip().upper()
            if not tk or tk in held or tk not in uni:
                continue
            r = ctx.row(tk)
            if r is None or pd.isna(r["close"]):
                continue
            px = float(r["close"]); v63 = ctx.vol63(tk); gd = grader.grade(tk, ctx)
            holdings.append(dict(
                ticker=tk, sleeve="custom", price=round(px, 2), base_weight=0.0,
                target_shares=0.0, target_value=0.0,
                grade=gd["grade"], grade_label=gd["grade_label"], action=gd["action"],
                action_weight=gd["action_weight"], prob=predictor.predict(tk, ctx),
                reason="用户自定义 · 每日追踪(不占策略仓位)",
                signals=gd["signals"],
                indicators=dict(
                    mom126=round(float(r["mom126"]), 4) if not pd.isna(r["mom126"]) else None,
                    mom21=round(float(r["mom21"]), 4) if not pd.isna(r["mom21"]) else None,
                    vol_annual=round(float(v63 * np.sqrt(252)), 4) if v63 else None,
                    sma20=round(float(r["sma20"]), 2), sma50=round(float(r["sma50"]), 2),
                    sma200=round(float(r["sma200"]), 2),
                    pct_from_high=round(float(r["pct_from_high"]), 4),
                    sy_yield=ind_contrib.get(tk, {}).get("sy_yield"),
                )))
            held.add(tk)
    # 价格表(全池 asof 收盘价)——供后端算用户持仓盈亏,as-of 一致
    prices = {}
    for tk, df in uni.items():
        p = POS.get(tk)
        if p is not None:
            c = df["close"].iloc[p]
            if not pd.isna(c):
                prices[tk] = round(float(c), 4)
    pd_out = dict(asof=str(asof.date()), prices=prices)
    return snap, pd_out


def write_snapshot(snap, pd_out, asof, also_latest=True):
    """把 compute 结果写成 JSON 文件(main 用;backfill 直连DB不用这个)。"""
    os.makedirs(OUT_DIR, exist_ok=True)
    names = [f"snapshot_{asof.date()}.json"] + (["snapshot_latest.json"] if also_latest else [])
    for name in names:
        with open(os.path.join(OUT_DIR, name), "w") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
    pnames = [f"prices_{asof.date()}.json"] + (["prices_latest.json"] if also_latest else [])
    for name in pnames:
        with open(os.path.join(OUT_DIR, name), "w") as f:
            json.dump(pd_out, f, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="us", choices=["us", "cn"], help="市场:us(美股)/cn(A股)")
    ap.add_argument("--asof", default="latest")
    ap.add_argument("--capital", type=float, default=4000.0)
    ap.add_argument("--no-sy", action="store_true", help="跳过SY腿(快速demo)")
    ap.add_argument("--track", default="", help="自定义追踪股(逗号分隔),每天也算档位/概率")
    args = ap.parse_args()
    # ── v2.0 双市场:A股走 cn_engine(复用 safna_jr_a 逻辑),美股走原路径 ──
    if args.market == "cn":
        import cn_engine
        cap = args.capital if args.capital != 4000.0 else 100000.0   # A股默认10万
        snap, M = cn_engine.compute_snapshot_cn(args.asof, cap)
        os.makedirs(OUT_DIR, exist_ok=True)
        for fp in (os.path.join(OUT_DIR, f"snapshot_cn_{snap['asof']}.json"),
                   os.path.join(OUT_DIR, "snapshot_cn_latest.json")):
            json.dump(snap, open(fp, "w"), ensure_ascii=False, indent=2)
        px = M["close"].iloc[-1].dropna()
        prices = {c: round(float(v), 4) for c, v in px.items() if np.isfinite(v)}
        json.dump(dict(market="cn", asof=snap["asof"], prices=prices),
                  open(os.path.join(OUT_DIR, "prices_cn_latest.json"), "w"), ensure_ascii=False)
        rl = snap["risk_light"]
        print(f"[cn] 快照写入 snapshot_cn_{snap['asof']}.json (+prices {len(prices)}只) | 持仓{len(snap['holdings'])} "
              f"风险灯{rl['level']} exposure{rl['exposure']} | {rl['note']}", flush=True)
        return
    print("装载数据 ...", flush=True)
    uni, spy, master, fp = load_all(with_sy=not args.no_sy)
    asof = resolve_asof(uni, args.asof)
    print(f"as-of(收盘日): {asof.date()}", flush=True)
    track = [t.strip() for t in args.track.split(",") if t.strip()]
    snap, pd_out = compute_snapshot(uni, spy, master, fp, asof, args.capital, with_sy=not args.no_sy, track=track)
    write_snapshot(snap, pd_out, asof)
    rl = snap["risk_light"]
    print(f"快照写入 snapshot_{asof.date()}.json | 持仓{len(snap['holdings'])} 风险灯{rl['level']} | 价格表{len(pd_out['prices'])}只", flush=True)


if __name__ == "__main__":
    main()
