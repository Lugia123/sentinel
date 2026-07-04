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

SAFNA = "/Users/lugia/lugia_fc/safna_jr"
for p in (f"{SAFNA}/round12/lib", f"{SAFNA}/round24/groupB"):
    sys.path.insert(0, p)
import backtest_lib2 as bl2                    # noqa
from champion import DATA_DIR_98               # noqa

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
OUT_DIR = os.path.join(os.path.dirname(HERE), "data")
SPY_PATH = f"{SAFNA}/动量哨兵研究/round2/data/SPY.csv"
NARROW = set(f[:-4] for f in os.listdir(DATA_DIR_98) if f.endswith(".csv"))

N = 10                        # 每腿票数
HORIZONS = [5, 20, 60]
VOL_TARGET = 0.15             # 风险灯目标年化波动
# 松·只减 档位→乘数(只减不加,R35 v4 最优跟法)
ACTION = {3: (1.0, "偏强·持有"), 2: (1.0, "偏强·持有"), 1: (1.0, "中性·持有"),
          0: (0.75, "转弱·减一档"), -1: (0.5, "走弱·减半"),
          -2: (0.25, "破位·减至1/4"), -3: (0.0, "跌势·清仓")}


def trend_grade(r):
    c, s200 = r["close"], r["sma200"]
    if pd.isna(c) or pd.isna(s200):
        return 1
    s = 0
    s += 1 if c > r["sma20"] else -1
    s += 1 if c > r["sma50"] else -1
    s += 1 if c > s200 else -1
    s += 1 if r["sma200_slope"] > 0 else -1
    s += 1 if r["mom21"] > 0 else -1
    s += 1 if r["sma20"] > r["sma50"] > s200 else (-1 if r["sma20"] < r["sma50"] < s200 else 0)
    pf = r["pct_from_high"]
    s += 1 if pf > -0.10 else (-1 if pf < -0.25 else 0)
    return int(np.clip(round(s * 3 / 7), -3, 3))


def build_z_quantiles(uni, POS, h):
    """全池历史标准化前瞻收益 z=fwd_h/(vol*sqrt(h)) 的经验分位(<=asof,无前视)。"""
    zs = []
    for tk, df in uni.items():
        p = POS.get(tk)
        if p is None:
            continue
        c = df["close"].values[:p + 1]
        if len(c) < 300:
            continue
        r1 = pd.Series(c).pct_change()
        vol = r1.rolling(63).std().values
        fwd = np.concatenate([c[h:] / c[:-h] - 1, [np.nan] * h])
        hv = vol * np.sqrt(h)
        with np.errstate(divide="ignore", invalid="ignore"):
            z = fwd[:len(c)] / hv
        z = z[np.isfinite(z)]
        zs.append(z[np.abs(z) < 10])
    allz = np.concatenate(zs) if zs else np.array([0.0])
    qs = [0.05, 0.10, 0.15, 0.25, 0.50, 0.75, 0.85, 0.90, 0.95]
    return {q: float(np.quantile(allz, q)) for q in qs}, np.sort(allz)


def prob_bands(price, sig_h, zq, zsort):
    """给定当前 h 日波动尺度 sig_h,输出概率带 + 到价概率。"""
    q = {k: price * (1 + sig_h * v) for k, v in zq.items()}
    stop = q[0.10]; target = q[0.90]
    # 到价概率:目标/止损对应的 z 在经验分布的位置
    def p_ge(px):
        z = (px / price - 1) / sig_h if sig_h > 0 else 0
        return float(1 - np.searchsorted(zsort, z) / len(zsort))
    return dict(median=round(q[0.50] / price - 1, 4),
                band70=[round(q[0.15] / price - 1, 4), round(q[0.85] / price - 1, 4)],
                stop=round(stop, 2), target=round(target, 2),
                p_hit_target=round(p_ge(target), 3), p_hit_stop=round(1 - p_ge(stop), 3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default="latest")
    ap.add_argument("--capital", type=float, default=4000.0)
    ap.add_argument("--no-sy", action="store_true", help="跳过SY腿(快速demo)")
    args = ap.parse_args()

    print("装载数据 ...", flush=True)
    uni, spy, master = bl2.load_universe(DATA_DIR, spy_path=SPY_PATH)
    a0 = next(iter(uni.values()))
    all_dates = pd.to_datetime(a0["date"]).tolist()
    if args.asof == "latest":
        asof_i = len(all_dates) - 1
    else:
        target = pd.Timestamp(args.asof)
        asof_i = max(i for i, d in enumerate(all_dates) if d <= target)
    asof = all_dates[asof_i]
    print(f"as-of(收盘日): {asof.date()}", flush=True)

    # ★ 无前视关键:按【日期】per-ticker 定位,不用共享位置索引(各票上市日/行数不同,
    #   位置索引会错位取到未来价)。POS[tk] = 该票 <=asof 的最后一行位置。
    asof64 = np.datetime64(asof)

    def _pos(df):
        d = pd.to_datetime(df["date"]).values
        p = int(np.searchsorted(d, asof64, side="right")) - 1
        return p if p >= 0 else None
    POS = {tk: _pos(df) for tk, df in uni.items()}

    def row(tk):
        i = POS.get(tk)
        if i is None:
            return None
        df = uni[tk]
        return {c: df[c].iloc[i] for c in
                ("close", "sma20", "sma50", "sma200", "sma200_slope", "mom21", "mom126", "pct_from_high")}

    def vol63(tk):
        i = POS.get(tk)
        if i is None or i < 63:
            return np.nan
        c = uni[tk]["close"].values[:i + 1]
        return float(pd.Series(c).pct_change().tail(63).std())

    # ── 选股 ──
    spy_c = spy["close"].values
    spy_dt = pd.to_datetime(spy["date"]).values
    sp = int(np.searchsorted(spy_dt, asof64, side="right")) - 1
    spy_mom = (spy_c[sp] / spy_c[sp - 126] - 1) if sp >= 126 else 0.0
    elig = []
    for tk in NARROW:
        if tk not in uni:
            continue
        r = row(tk)
        if r is None or pd.isna(r["close"]) or pd.isna(r["sma200"]) or pd.isna(r["mom126"]):
            continue
        if r["close"] > r["sma200"] and r["sma200_slope"] > 0 and r["close"] > r["sma50"] \
           and r["pct_from_high"] > -0.25:
            elig.append((tk, r["mom126"] - spy_mom))
    elig.sort(key=lambda kv: -kv[1])
    mom_picks = [tk for tk, _ in elig[:N]]

    sy_picks = []
    if not args.no_sy:
        try:
            from backtest_r24 import FundamentalsPITExtended
            fp = FundamentalsPITExtended(verbose=False)
            avail = [tk for tk in uni if (r := row(tk)) and not pd.isna(r["close"]) and r["close"] >= 5]
            scored = {}
            for tk in avail:
                if tk not in fp.available_tickers():
                    continue
                sh = fp.get_latest(tk, "CommonStockSharesOutstanding", asof, lag_days=45)
                px = row(tk)["close"]
                if not sh or sh <= 0:
                    continue
                mcap = sh * px
                bb = fp.get_quarterly_series(tk, "PaymentsForRepurchaseOfCommonStock", asof, n_quarters=4, lag_days=45)
                iss = fp.get_quarterly_series(tk, "ProceedsFromIssuanceOfCommonStock", asof, n_quarters=4, lag_days=45)
                tb = sum(abs(v) for _, v in bb if v is not None)
                ti = sum(v for _, v in iss if v is not None)
                dv = fp.get_dividend_ttm(tk, asof, lag_days=45) or 0.0
                scored[tk] = (tb - ti) / mcap + dv / mcap
            sy_picks = [tk for tk, _ in sorted(scored.items(), key=lambda kv: -kv[1])[:N]]
        except Exception as e:
            print(f"SY 腿跳过({e})", flush=True)

    # ── 风险平价定仓(逆波动,各腿50%)──
    def ivw(picks, frac):
        iv = {tk: 1.0 / v for tk in picks if (v := vol63(tk)) and v > 0}
        s = sum(iv.values())
        return {tk: frac * iv.get(tk, 0) / s for tk in picks} if s > 0 else {}
    base = {}
    for tk, w in ivw(mom_picks, 0.5 if sy_picks else 1.0).items():
        base[tk] = base.get(tk, 0) + w
    for tk, w in ivw(sy_picks, 0.5).items():
        base[tk] = base.get(tk, 0) + w

    # ── 风险灯(波动目标)──
    spy_ret = pd.Series(spy_c[:sp + 1]).pct_change()
    spyvol = float(spy_ret.tail(21).std() * np.sqrt(252))
    exposure = float(min(1.0, VOL_TARGET / spyvol)) if spyvol > 0 else 1.0
    light = "green" if exposure >= 0.95 else ("amber" if exposure >= 0.7 else "red")

    # ── 概率分位(全池,每 horizon 一次)──
    zqs = {h: build_z_quantiles(uni, POS, h) for h in HORIZONS}

    # ── 组装 holdings ──
    holdings = []
    for tk in sorted(base, key=lambda t: -base[t]):
        r = row(tk)
        px = float(r["close"]); g = trend_grade(r)
        mult, label = ACTION[g]
        v63 = vol63(tk)
        prob = {}
        for h in HORIZONS:
            zq, zsort = zqs[h]
            sig_h = (v63 * np.sqrt(h)) if v63 and v63 > 0 else 0.0
            prob[f"h{h}"] = prob_bands(px, sig_h, zq, zsort)
        sleeve = ("both" if tk in mom_picks and tk in sy_picks
                  else ("momentum" if tk in mom_picks else "SY"))
        tv = base[tk] * args.capital * exposure
        holdings.append(dict(
            ticker=tk, sleeve=sleeve, price=round(px, 2),
            base_weight=round(base[tk], 4),
            target_shares=round(tv / px, 3), target_value=round(tv, 2),
            grade=g, grade_label=label.split("·")[0], action=label.split("·")[1],
            action_weight=mult, prob=prob))

    snap = dict(
        asof=str(asof.date()), generated_at=str(pd.Timestamp("today").date()),
        capital=args.capital, disclaimer="研究工具,非投资建议",
        risk_light=dict(level=light, spy_vol=round(spyvol, 3), exposure=round(exposure, 3),
                        note={"green": "波动正常,可满仓", "amber": "波动偏高,建议降仓",
                              "red": "波动极高,大幅降仓"}[light]),
        holdings=holdings,
        portfolio=dict(n_holdings=len(holdings),
                       gross_exposure=round(sum(h["target_value"] for h in holdings) / args.capital, 3),
                       cash_pct=round(1 - sum(h["target_value"] for h in holdings) / args.capital, 3)),
    )
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"snapshot_{asof.date()}.json")
    with open(out, "w") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    # latest 软链方便后端读
    latest = os.path.join(OUT_DIR, "snapshot_latest.json")
    with open(latest, "w") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    # 价格表(全池 asof 收盘价)——供后端算用户持仓盈亏,as-of 一致
    prices = {}
    for tk, df in uni.items():
        p = POS.get(tk)
        if p is not None:
            c = df["close"].iloc[p]
            if not pd.isna(c):
                prices[tk] = round(float(c), 4)
    pd_out = dict(asof=str(asof.date()), prices=prices)
    for name in (f"prices_{asof.date()}.json", "prices_latest.json"):
        with open(os.path.join(OUT_DIR, name), "w") as f:
            json.dump(pd_out, f, ensure_ascii=False)

    print(f"快照写入 {out}", flush=True)
    print(f"价格表 {len(prices)} 只", flush=True)
    print(f"持仓 {len(holdings)} 只 | 风险灯 {light}(SPYvol {spyvol:.1%},建议仓位 {exposure:.0%})", flush=True)
    print(f"动量腿 {len(mom_picks)} / SY腿 {len(sy_picks)}", flush=True)


if __name__ == "__main__":
    main()
