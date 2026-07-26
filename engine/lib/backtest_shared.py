"""
backtest_shared.py —— R22 B队共享回测框架
==========================================
基于 round12/lib/backtest_lib2.py 和 champion.py，
提供宽池数据加载、回测入口、相关性计算等共享功能。
"""

import os
import sys
import json
import math
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_lib2 as bl2
from champion import run_champion

# 路径常量
DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
BROAD_DIR = os.path.join(DATA_DIR, "broad")
NARROW_DIR = os.path.join(DATA_DIR, "narrow")
SPY_PATH = os.path.join(DATA_DIR, "SPY.csv")
OUTPUT_DIR = os.path.join(DATA_DIR, "r22")

# 共享参数
SHARED_PARAMS = dict(
    capital=4000.0,
    slippage=0.0005,
    ltcg_rate=0.15,
    stcg_rate=0.25,
    ltcg_days=365,
    min_history=252,
    seed=42,
    risk_pct=0.02,
)


def load_broad_data():
    """加载宽池 (1393 只) + SPY"""
    print("[backtest_shared] Loading broad pool from", BROAD_DIR)
    uni, spy, master = bl2.load_universe(BROAD_DIR, spy_path=SPY_PATH)
    print(f"[backtest_shared]   uni={len(uni)} tickers, master={len(master)} days")
    return uni, spy, master


def load_narrow_data():
    """加载窄池 (98 只) + SPY"""
    print("[backtest_shared] Loading narrow pool from", NARROW_DIR)
    uni, spy, master = bl2.load_universe(NARROW_DIR, spy_path=SPY_PATH)
    print(f"[backtest_shared]   uni={len(uni)} tickers, master={len(master)} days")
    return uni, spy, master


def run_champion_broad(uni=None, spy=None, master=None, drop_top_n=0):
    """在宽池跑动量冠军对照"""
    if uni is None:
        uni, spy, master = load_broad_data()
    print("[backtest_shared] Running champion (broad)...")
    res = run_champion(uni=uni, spy=spy, master=master, drop_top_n=drop_top_n)
    m = res["metrics"]
    print(f"[backtest_shared]   champion: CAGR={m.get('CAGR'):.4f}  "
          f"Sharpe={m.get('Sharpe'):.2f}  maxDD={m.get('maxDD'):.4f}")
    return res


def monthly_returns_from_equity(equity_curve):
    """从日 equity_curve [(date_str, equity), ...] 计算月收益序列"""
    if not equity_curve:
        return pd.Series(dtype=float)
    eq = pd.DataFrame(equity_curve, columns=["date", "equity"])
    eq["date"] = pd.to_datetime(eq["date"])
    eq = eq.set_index("date").sort_index()
    monthly = eq["equity"].resample("ME").last().dropna()
    if len(monthly) < 2:
        return pd.Series(dtype=float)
    monthly_rets = monthly.pct_change().dropna()
    monthly_rets.index = monthly_rets.index.to_period("M")
    return monthly_rets


def calc_correlation(my_monthly, champion_monthly, clean_window=True):
    """计算两组月收益 Pearson 相关系数。

    clean_window=True: 剔除 2010-10 前 (动量趴现金假零期)
    """
    if isinstance(my_monthly, (list, tuple)):
        my_monthly = pd.Series(my_monthly)
    if isinstance(champion_monthly, (list, tuple)):
        champion_monthly = pd.Series(champion_monthly)

    if isinstance(my_monthly, pd.Series) and isinstance(champion_monthly, pd.Series):
        combined = pd.concat(
            [my_monthly.rename("my"), champion_monthly.rename("champion")],
            axis=1, join="inner"
        )
    else:
        n = min(len(my_monthly), len(champion_monthly))
        combined = pd.DataFrame({"my": my_monthly[:n], "champion": champion_monthly[:n]})

    if clean_window and len(combined) > 0:
        # 剔除 2010-10 之前
        if isinstance(combined.index, pd.PeriodIndex):
            mask = combined.index >= pd.Period("2010-11", "M")
        else:
            mask = pd.to_datetime(combined.index) >= pd.Timestamp("2010-11-01")
        combined = combined[mask]

    if len(combined) < 6:
        return dict(corr=float("nan"), aligned_len=len(combined),
                   years=0.0, note="too few overlapping months")

    corr = combined["my"].corr(combined["champion"])
    return dict(
        corr=round(float(corr), 4),
        aligned_len=len(combined),
        years=round(len(combined) / 12, 1),
        note="clean window (>=2010-11)" if clean_window else "full window"
    )


def run_backtest(rank_fn, params, posmgmt=None, uni=None, spy=None, master=None,
                 drop_top_n=0):
    """统一回测入口"""
    if uni is None:
        uni, spy, master = load_broad_data()
    P = dict(SHARED_PARAMS)
    P.update(params)

    res = bl2.backtest_portfolio(
        rank_fn, P,
        posmgmt=posmgmt,
        uni=uni, spy=spy, master=master,
        drop_top_n_expost=drop_top_n,
        audit=True,
    )

    # 附加月收益
    monthly_rets = monthly_returns_from_equity(res.get("equity", []))
    res["monthly_returns"] = monthly_rets.tolist() if len(monthly_rets) else []
    res["monthly_returns_index"] = [str(p) for p in monthly_rets.index] if len(monthly_rets) else []

    # 年收益
    if len(monthly_rets) > 0:
        ann = {}
        for period, ret in monthly_rets.items():
            year = str(period.year)
            ann[year] = ann.get(year, 0.0) + ret
        res["annual_returns"] = ann
    else:
        res["annual_returns"] = {}

    # 基准月收益
    ew_monthly = monthly_returns_from_equity(res.get("benchmark_ew", []))
    spy_monthly = monthly_returns_from_equity(res.get("benchmark_spy", []))
    res["ew_monthly_returns"] = ew_monthly.tolist() if len(ew_monthly) else []
    res["spy_monthly_returns"] = spy_monthly.tolist() if len(spy_monthly) else []

    return res


class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, pd.Timestamp):
            return str(obj)
        if isinstance(obj, pd.Period):
            return str(obj)
        return super().default(obj)


def save_result(res, filename):
    """保存结果 JSON"""
    path = os.path.join(OUTPUT_DIR, filename)
    # 只保留核心指标 (避免 trades 等大数组)
    out = {
        "metrics": res.get("metrics", {}),
        "spy_metrics": res.get("spy_metrics", {}),
        "ew_metrics": res.get("ew_metrics", {}),
        "annual_returns": res.get("annual_returns", {}),
        "audit_violation": res.get("audit_violation"),
        "params": res.get("params", {}),
        "n_trades": res["metrics"].get("n_trades", 0),
        "monthly_returns": res.get("monthly_returns", []),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, cls=NpEncoder, indent=2, ensure_ascii=False)
    print(f"[backtest_shared] Saved to {path}")
    return path


# ---- 自测 ----
if __name__ == "__main__":
    print("=== backtest_shared self-test ===")
    uni, spy, master = load_broad_data()
    print(f"  uni={len(uni)} spy_cols={list(spy.columns)[:5]} master={len(master)}")

    # 简单动量测试
    def rank_mom(view, P):
        scored = []
        for t in view.available_tickers():
            row = view.last_row(t)
            if row is None or pd.isna(row.get("mom126", None)):
                continue
            scored.append((t, row["mom126"]))
        scored.sort(key=lambda kv: -kv[1])
        return [t for t, _ in scored]

    test_res = run_backtest(
        rank_mom,
        dict(n_slots=6, rebalance="M", weight_mode="invvol", max_weight=0.25),
        uni=uni, spy=spy, master=master,
    )
    m = test_res["metrics"]
    print(f"  test: CAGR={m.get('CAGR'):.4f} Sharpe={m.get('Sharpe'):.2f} "
          f"maxDD={m.get('maxDD'):.4f} audit={test_res.get('audit_violation')}")
    print("=== self-test done ===")
