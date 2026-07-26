"""
round10/lib/champion.py
=======================
R9 冠军「综合发明系统·税后长持·集中趋势」抽成可复用模块(红队对抗的统一被攻对象)。

来源 = round9/invent/test.py 的 rank_fn_invent + posmgmt_invent + BASE params。
引擎 = round9/lib/backtest_lib2.py(禁改;只 import)。

核心 API:
    run_champion(data_dir=, pool_tickers=None, exclude=None, period=None,
                 param_overrides=None, drop_top_n=0, uni=/spy=/master=) -> 引擎结果 dict

基线复现:run_champion(DATA_DIR_98) 应得 CAGR≈0.1599 / Sharpe≈0.88 / maxDD≈-0.341。
研究推演,非投资建议。
"""
import os, sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_lib2 as bl2  # noqa: E402

DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
DATA_DIR_98 = os.path.join(DATA_DIR, "narrow98")
DATA_DIR_FADED = os.path.join(DATA_DIR, "faded")
SPY_PATH = os.path.join(DATA_DIR, "SPY.csv")

# ---- 冠军参数(与 round9/invent/test.py BASE 完全一致)----
CHAMPION_PARAMS = dict(
    capital=4000.0, n_slots=4, rebalance="M", rebalance_threshold=0.10,
    max_weight=0.35, weight_mode="invvol",
    ltcg_rate=0.15, stcg_rate=0.25, ltcg_days=365, min_history=252,
    keep_band_mult=2.0, pct_from_high_min=-0.25, use_regime=True,
    exit_mode="trend_only",
)


# ============================================================================
# 选股层(逐字搬自 round9/invent/test.py:rank_fn_invent)
# ============================================================================
def rank_fn_champion(view, P):
    spy_hist = view.spy_history(n=260)
    if spy_hist is None or len(spy_hist) < 130:
        return []
    spy_mom = spy_hist["close"].iloc[-1] / spy_hist["close"].iloc[-127] - 1.0
    pfh_min = P.get("pct_from_high_min", -0.25)
    scored = []
    for tkr in view.available_tickers():
        row = view.last_row(tkr)
        if row is None:
            continue
        bad = False
        for f in ("sma200", "sma50", "mom126", "sma200_slope", "hi252"):
            if pd.isna(row[f]):
                bad = True
                break
        if bad:
            continue
        c = row["close"]
        if c <= row["sma200"]:
            continue
        if row["sma200_slope"] <= 0:
            continue
        if c <= row["sma50"]:
            continue
        if row["pct_from_high"] < pfh_min:
            continue
        rs = row["mom126"] - spy_mom
        scored.append((tkr, rs))
    scored.sort(key=lambda kv: -kv[1])
    return [t for t, _ in scored]


def _broad_rank(view):
    out = []
    for t in view.available_tickers():
        row = view.last_row(t)
        if row is None or pd.isna(row["mom126"]):
            continue
        out.append((t, row["mom126"]))
    out.sort(key=lambda kv: -kv[1])
    return [t for t, _ in out]


# ============================================================================
# 仓位层(逐字搬自 round9/invent/test.py:posmgmt_invent)
# ============================================================================
def posmgmt_champion(view, P, positions, eq, ranked):
    N = int(P["n_slots"])
    keep_band = int(round(P.get("keep_band_mult", 2.0) * N))
    max_w = P["max_weight"]
    thr = P["rebalance_threshold"]
    use_regime = P.get("use_regime", True)
    wmode = P.get("weight_mode", "invvol")
    exit_mode = P.get("exit_mode", "trend_only")

    regime_on = True
    if use_regime:
        spc = view.spy_last("close")
        ssma = view.spy_last("sma200")
        if spc is not None and ssma is not None and not pd.isna(ssma):
            regime_on = bool(spc >= ssma)

    brank = None
    if exit_mode == "broad_rank":
        brank = {t: i for i, t in enumerate(_broad_rank(view))}

    survivors = []
    exits = []
    for t in list(positions.keys()):
        row = view.last_row(t)
        if row is None or pd.isna(row["sma200"]) or row["close"] < row["sma200"]:
            exits.append((t, "trend_break"))
            continue
        if exit_mode == "broad_rank" and brank.get(t, 10**9) >= keep_band:
            exits.append((t, "rank_exit"))
            continue
        survivors.append(t)
    exit_set = {t for t, _ in exits}

    n_open = N - len(survivors)
    new_names = []
    if regime_on and n_open > 0:
        held = set(positions.keys())
        for t in ranked:
            if t in held or t in exit_set:
                continue
            new_names.append(t)
            if len(new_names) >= n_open:
                break

    book = survivors + new_names
    orders = []
    for t, r in exits:
        orders.append(dict(act="sell", tkr=t, frac=1.0, reason=r))
    if not book:
        return orders

    if wmode == "invvol":
        inv = {}
        for t in book:
            row = view.last_row(t)
            px = row["close"] if row is not None else None
            atr = row["atr14"] if row is not None else None
            inv[t] = (px / atr) if (px and atr and atr > 0) else 0.0
        s = sum(inv.values()) or 1.0
        w = {t: inv[t] / s for t in book}
    else:
        w = {t: 1.0 / len(book) for t in book}
    w = {t: min(v, max_w) for t, v in w.items()}

    buys = []
    for t in book:
        row = view.last_row(t)
        if row is None:
            continue
        close = row["close"]
        atr = row["atr14"]
        target = w[t] * eq
        if t in positions and t not in exit_set:
            cur = close * positions[t].shares
            drift = abs(target - cur) / max(1.0, eq)
            if drift > thr:
                if target > cur:
                    buys.append(dict(act="buy", tkr=t, dollars=target - cur, atr=atr))
                else:
                    frac = (cur - target) / cur if cur > 0 else 0.0
                    if frac > 0.02:
                        orders.append(dict(act="sell", tkr=t, frac=frac, reason="rebal_trim"))
        else:
            buys.append(dict(act="buy", tkr=t, dollars=target, atr=atr))
    orders.extend(buys)
    return orders


# ============================================================================
# 工具:period 切片(切已含指标的 uni/spy/master,保 warmup → 段内可第一日交易)
# ============================================================================
def slice_period(uni, spy, master, period):
    """period=(start,end) 字符串/Timestamp。返回切片后的 (uni,spy,master)。
    指标已在 load_universe 预算,切片后段首仍带完整历史指标(无 warmup 损失)。"""
    if period is None:
        return uni, spy, master
    start = pd.Timestamp(period[0]); end = pd.Timestamp(period[1])
    uni2 = {}
    for t, df in uni.items():
        sub = df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)
        if len(sub) >= 30:
            uni2[t] = sub
    spy2 = spy[(spy["date"] >= start) & (spy["date"] <= end)].reset_index(drop=True)
    master2 = [d for d in master if start <= pd.Timestamp(d) <= end]
    return uni2, spy2, master2


def load_pool(data_dir=DATA_DIR_98, extra_dirs=None, pool_tickers=None, exclude=None):
    """加载 universe;可合并多目录(沦落股扩池);可只取 pool_tickers 子集。"""
    uni, spy, master = bl2.load_universe(data_dir, spy_path=SPY_PATH, exclude=exclude)
    for d in (extra_dirs or []):
        u2, _, m2 = bl2.load_universe(d, spy_path=SPY_PATH, exclude=exclude)
        uni.update(u2)
        master = sorted(set(master) | set(m2))
    if pool_tickers is not None:
        keep = set(pool_tickers)
        uni = {t: df for t, df in uni.items() if t in keep}
    return uni, spy, master


# ============================================================================
# 主 API
# ============================================================================
def run_champion(data_dir=DATA_DIR_98, pool_tickers=None, exclude=None, period=None,
                 param_overrides=None, drop_top_n=0,
                 uni=None, spy=None, master=None, extra_dirs=None):
    """跑冠军策略。返回引擎结果 dict(metrics/spy_metrics/ew_metrics/audit_violation/...)。
    - pool_tickers: 只用这些票(随机子池 / de-winnered 用)。
    - extra_dirs:  额外数据目录列表(沦落股扩池:extra_dirs=[DATA_DIR_FADED])。
    - period:      (start,end) 只回测该段,双基准同段重算。
    - param_overrides: 覆盖 CHAMPION_PARAMS(参数扰动用)。
    - drop_top_n:  剔全期最强 N 票(幸存者下界)。
    """
    if uni is None:
        uni, spy, master = load_pool(data_dir, extra_dirs=extra_dirs,
                                     pool_tickers=pool_tickers, exclude=exclude)
    else:
        uni = dict(uni)
        if pool_tickers is not None:
            keep = set(pool_tickers)
            uni = {t: df for t, df in uni.items() if t in keep}
    if period is not None:
        uni, spy, master = slice_period(uni, spy, master, period)

    P = dict(CHAMPION_PARAMS)
    if param_overrides:
        P.update(param_overrides)

    res = bl2.backtest_portfolio(
        rank_fn_champion, P, posmgmt=posmgmt_champion,
        uni=uni, spy=spy, master=master, drop_top_n_expost=drop_top_n, audit=True)
    return res


if __name__ == "__main__":
    res = run_champion()
    m = res["metrics"]
    print("=== CHAMPION baseline (98-pool, full period) ===")
    print({k: m[k] for k in ("CAGR", "Sharpe", "maxDD", "Sortino", "Calmar",
                              "avg_hold", "pct_long_term", "final_equity")})
    print("SPY-BH :", {k: res["spy_metrics"][k] for k in ("CAGR", "Sharpe", "maxDD")})
    print("EW-BH  :", {k: res["ew_metrics"][k] for k in ("CAGR", "Sharpe", "maxDD")})
    print("audit_violation (must be None):", res["audit_violation"])
    print("n_tickers:", len(res["params"]) and "ok")
