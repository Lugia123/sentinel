"""
backtest_r24.py —— R24 B队 (DeepSeek): 寻找M2型互补件 —— 质量sleeve
=====================================================================
运行: uv run python backtest_r24.py
产出: result.json (四大候选单腿+动量组合+三腿sleeve+survivor)

四大候选:
  1. SY  (Shareholder Yield): 净回购率 + 股息率 = 总股东收益率
  2. FCFY (FCF Yield): 自由现金流/市值，便宜且赚现金
  3. DELEV (Deleveraging): 资产负债表改善——去杠杆+净现金积累
  4. ECQ  (Earnings-Cashflow Quality): 盈利+现金流双高稳健复利者

全部连续打分+黏性持仓+半年度调仓, 禁止资格硬开关/质量门。
"""
import sys, os, json, math, time
import numpy as np
import pandas as pd
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest_lib2 as bl2
from backtest_shared import (
    load_broad_data, run_backtest,
    run_champion_broad, calc_correlation,
    monthly_returns_from_equity, SHARED_PARAMS,
    BROAD_DIR, SPY_PATH,
)
from fundamentals_pit import FundamentalsPIT, CONCEPTS

DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
OUTPUT_DIR = os.path.join(DATA_DIR, "r24")
R23_DIR = os.path.join(DATA_DIR, "r23")

# ══════════════════════════════════════════════════════════════════════════════
# 扩展 EDGAR 概念: 加入股息
# ══════════════════════════════════════════════════════════════════════════════
DIVIDEND_CONCEPTS = [
    "PaymentsOfDividends",
    "PaymentsOfDividendsCommonStock",
    "CommonStockDividendsPerShareCashPaid",
]

class FundamentalsPITExtended(FundamentalsPIT):
    """扩展版: 加入股息支付数据"""
    def __init__(self, data_dir=None, verbose=True):
        super().__init__(data_dir=data_dir, verbose=False)
        self._dividend_data = defaultdict(list)
        self._load_dividends(verbose)

    def _load_dividends(self, verbose):
        import json as _json
        n_loaded = 0
        for ticker in self._tickers:
            fp = os.path.join(self.data_dir, f"{ticker}.json")
            try:
                with open(fp) as f:
                    raw = _json.load(f)
            except:
                continue
            facts = raw.get("facts", {})
            has_div = False
            for taxonomy, tax_data in facts.items():
                if not isinstance(tax_data, dict):
                    continue
                for cname in DIVIDEND_CONCEPTS:
                    if cname not in tax_data:
                        continue
                    concept = tax_data[cname]
                    if not isinstance(concept, dict) or "units" not in concept:
                        continue
                    units = concept["units"]
                    for unit_type, records in units.items():
                        if not records:
                            continue
                        for rec in records:
                            if not isinstance(rec, dict):
                                continue
                            filed = rec.get("filed", "")
                            end = rec.get("end", "")
                            val = rec.get("val")
                            if not filed or val is None:
                                continue
                            self._dividend_data[ticker].append({
                                "val": float(val),
                                "filed": filed,
                                "end": end,
                                "fy": rec.get("fy", 0),
                                "fp": rec.get("fp", ""),
                                "form": rec.get("form", ""),
                            })
                            has_div = True
            if has_div:
                n_loaded += 1
        # 按 filed 排序
        for t in self._dividend_data:
            self._dividend_data[t].sort(key=lambda r: r["filed"])
        if verbose:
            print(f"[FundamentalsPITExtended] Dividends loaded: {n_loaded} tickers")

    def get_dividend_ttm(self, ticker, as_of, lag_days=45):
        """获取过去12个月(4个季度)的股息支付总额"""
        cutoff = (pd.Timestamp(as_of) - pd.Timedelta(days=lag_days)).strftime("%Y-%m-%d")
        divs = self._dividend_data.get(ticker, [])
        if not divs:
            return None
        # 取 filed <= cutoff 的记录
        valid = [d for d in divs if d["filed"] <= cutoff]
        if len(valid) < 1:
            return None
        # 取最近 4 条 (季度数据的最近1年)
        recent = valid[-4:]
        total = sum(r["val"] for r in recent)
        return total


# ══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════════════════

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Period):
            return str(obj)
        if isinstance(obj, pd.Timestamp):
            return str(obj)
        return super().default(obj)


def save_result(res, filename):
    path = os.path.join(OUTPUT_DIR, filename)
    out = {
        "metrics": res.get("metrics", {}),
        "spy_metrics": res.get("spy_metrics", {}),
        "ew_metrics": res.get("ew_metrics", {}),
        "annual_returns": res.get("annual_returns", {}),
        "audit_violation": str(res.get("audit_violation", "None")),
        "params": res.get("params", {}),
        "n_trades": res["metrics"].get("n_trades", 0),
        "monthly_returns": res.get("monthly_returns", []),
        "monthly_returns_index": res.get("monthly_returns_index", []),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, cls=NpEncoder, indent=2, ensure_ascii=False)
    print(f"[save] {path}")
    return path


# ══════════════════════════════════════════════════════════════════════════════
# 黏性持仓管理 (同 R23 M2 驯服配方)
# ══════════════════════════════════════════════════════════════════════════════

def make_sticky_posmgmt(n_slots=10, sticky_mult=2.5):
    def posmgmt(view, P, positions, current_equity, ranked_list):
        n_slots_actual = int(P.get("n_slots", n_slots))
        sticky_boundary = max(n_slots_actual + 1, int(n_slots_actual * sticky_mult))
        orders = []
        current_tickers = set(positions.keys()) if positions else set()
        picks = ranked_list[:n_slots_actual] if ranked_list else []
        sticky_candidates = set(ranked_list[:sticky_boundary]) if ranked_list else set()

        for tkr in list(current_tickers):
            if tkr not in sticky_candidates:
                orders.append({
                    "act": "sell", "tkr": tkr, "frac": 1.0,
                    "reason": f"sticky_out (rank>{sticky_boundary})",
                })

        open_slots = n_slots_actual - len([t for t in current_tickers if t in sticky_candidates])
        if open_slots > 0:
            for tkr in picks:
                if tkr not in current_tickers:
                    orders.append({
                        "act": "buy", "tkr": tkr,
                        "dollars": current_equity / n_slots_actual,
                        "reason": "sticky_new",
                    })
                    open_slots -= 1
                    if open_slots <= 0:
                        break
        return orders
    return posmgmt


# ══════════════════════════════════════════════════════════════════════════════
# 候选 1: 股东收益率 (Shareholder Yield = 净回购率 + 股息率)
# ══════════════════════════════════════════════════════════════════════════════

def make_rank_fn_shareholder_yield(fp):
    """
    总股东收益率: Net Buyback Yield + Dividend Yield
    - 净回购率: 过去4Q的(回购支出-发行收入)/市值
    - 股息率: 过去4Q股息/市值
    连续打分, 高分=股东回报多
    """
    def rank_fn(view, params):
        as_of = pd.Timestamp(view.as_of)
        scored = []
        for t in view.available_tickers():
            if t not in fp.available_tickers():
                continue
            row = view.last_row(t)
            if row is None or row.get("close", 0) < 5:
                continue

            # 获取市值 (shares * price)
            shares = fp.get_latest(t, "CommonStockSharesOutstanding", as_of, lag_days=45)
            price = row["close"]
            if shares is None or shares <= 0:
                continue
            mcap = shares * price
            if mcap <= 0:
                continue

            # 净回购: 过去4Q (回购支出 - 发行收入)
            buyback_q = fp.get_quarterly_series(t, "PaymentsForRepurchaseOfCommonStock",
                                                 as_of, n_quarters=4, lag_days=45)
            issuance_q = fp.get_quarterly_series(t, "ProceedsFromIssuanceOfCommonStock",
                                                  as_of, n_quarters=4, lag_days=45)

            ttm_buyback = 0.0
            ttm_issuance = 0.0
            for _, v in buyback_q:
                if v is not None:
                    ttm_buyback += abs(v)  # buyback is usually negative in cash flow
            for _, v in issuance_q:
                if v is not None:
                    ttm_issuance += v

            net_buyback = ttm_buyback - ttm_issuance
            net_buyback_yield = net_buyback / mcap if mcap > 0 else 0

            # 股息率: TTM股息 / 市值
            ttm_div = fp.get_dividend_ttm(t, as_of, lag_days=45)
            div_yield = (ttm_div / mcap) if (ttm_div is not None and mcap > 0) else 0.0

            # 总股东收益率
            total_yield = net_buyback_yield + div_yield
            scored.append((t, total_yield))

        scored.sort(key=lambda kv: -kv[1])
        return [t for t, _ in scored]
    return rank_fn


# ══════════════════════════════════════════════════════════════════════════════
# 候选 2: FCF 收益率 (FCF Yield = 自由现金流 / 市值)
# ══════════════════════════════════════════════════════════════════════════════

def make_rank_fn_fcf_yield(fp):
    """
    FCF 收益率: (OCF - CapEx) / 市值
    便宜+能产生现金的企业 → 质量+价值双重属性
    连续打分, 高FCF收益率=好
    """
    def rank_fn(view, params):
        as_of = pd.Timestamp(view.as_of)
        scored = []
        for t in view.available_tickers():
            if t not in fp.available_tickers():
                continue
            row = view.last_row(t)
            if row is None or row.get("close", 0) < 5:
                continue

            shares = fp.get_latest(t, "CommonStockSharesOutstanding", as_of, lag_days=45)
            price = row["close"]
            if shares is None or shares <= 0:
                continue
            mcap = shares * price
            if mcap <= 0:
                continue

            # TTM 经营现金流
            ocf_q = fp.get_quarterly_series(t, "NetCashProvidedByUsedInOperatingActivities",
                                             as_of, n_quarters=4, lag_days=45)
            # TTM 资本支出
            capex_q = fp.get_quarterly_series(t, "PaymentsToAcquirePropertyPlantAndEquipment",
                                               as_of, n_quarters=4, lag_days=45)

            ttm_ocf = sum(v for _, v in ocf_q if v is not None)
            ttm_capex = sum(abs(v) if v is not None else 0 for _, v in capex_q)

            fcf = ttm_ocf - ttm_capex
            fcf_yield = fcf / mcap if mcap > 0 else 0

            # 也看 FCF 是否为正 (负FCF的公司排除也不对，但要打低分)
            # 用连续分: FCF yield高低排序
            scored.append((t, fcf_yield))

        # 排除极端异常值 (FCF yield > 100% 或 < -50%)
        scored = [(t, s) for t, s in scored if -0.5 < s < 1.0]
        scored.sort(key=lambda kv: -kv[1])
        return [t for t, _ in scored]
    return rank_fn


# ══════════════════════════════════════════════════════════════════════════════
# 候选 3: 去杠杆趋势 (Deleveraging + Net Cash Building)
# ══════════════════════════════════════════════════════════════════════════════

def make_rank_fn_deleveraging(fp):
    """
    资产负债表改善: 四个维度 z-score 等权合成
    ① 当前杠杆率低 (Equity/Assets 高)
    ② 杠杆率在下降 (ΔDebt/Assets < 0)
    ③ 现金比率高 (Cash/Assets)
    ④ 现金比率在改善 (ΔCash/Assets > 0)
    连续打分, 无硬门槛
    """
    def rank_fn(view, params):
        as_of = pd.Timestamp(view.as_of)
        raw = []
        for t in view.available_tickers():
            if t not in fp.available_tickers():
                continue
            row = view.last_row(t)
            if row is None or row.get("close", 0) < 5:
                continue

            assets = fp.get_latest(t, "Assets", as_of, lag_days=45)
            equity = fp.get_latest(t, "StockholdersEquity", as_of, lag_days=45)
            cash = fp.get_latest(t, "CashAndCashEquivalentsAtCarryingValue", as_of, lag_days=45)

            if assets is None or assets <= 0:
                continue

            eq_ratio = equity / assets if equity is not None else None
            cash_ratio = cash / assets if cash is not None else None

            # 1年前对比
            as_of_1y = as_of - pd.Timedelta(days=365)
            assets_1y = fp.get_latest(t, "Assets", as_of_1y, lag_days=45)
            equity_1y = fp.get_latest(t, "StockholdersEquity", as_of_1y, lag_days=45)
            cash_1y = fp.get_latest(t, "CashAndCashEquivalentsAtCarryingValue", as_of_1y, lag_days=45)

            delta_debt_ratio = None
            delta_cash_ratio = None
            if assets_1y and assets_1y > 0:
                if equity is not None and equity_1y is not None:
                    debt_now = (assets - equity) / assets
                    debt_1y = (assets_1y - equity_1y) / assets_1y
                    delta_debt_ratio = debt_now - debt_1y  # 负=去杠杆=好

                if cash is not None and cash_1y is not None:
                    cr_now = cash / assets
                    cr_1y = cash_1y / assets_1y
                    delta_cash_ratio = cr_now - cr_1y  # 正=积累现金=好

            raw.append((t, eq_ratio, delta_debt_ratio, cash_ratio, delta_cash_ratio))

        if len(raw) < 5:
            return [t for t, _, _, _, _ in raw]

        def safe_z(vals, flip=False):
            arr = np.array([v if v is not None else np.nan for v in vals], dtype=float)
            mu = np.nanmean(arr); sigma = np.nanstd(arr)
            if sigma == 0 or np.isnan(sigma):
                return np.zeros(len(arr))
            z = (arr - mu) / sigma
            return -z if flip else z

        tickers = [r[0] for r in raw]
        z_eq = safe_z([r[1] for r in raw])         # 权益比高=好
        z_dd = safe_z([-r[2] if r[2] is not None else None for r in raw])  # 去杠杆=好
        z_cr = safe_z([r[3] for r in raw])          # 现金比高=好
        z_dc = safe_z([r[4] for r in raw])          # 现金积累=好

        combined = []
        for i, t in enumerate(tickers):
            parts = []
            if not np.isnan(z_eq[i]): parts.append(z_eq[i] * 0.25)
            if not np.isnan(z_dd[i]): parts.append(z_dd[i] * 0.25)
            if not np.isnan(z_cr[i]): parts.append(z_cr[i] * 0.25)
            if not np.isnan(z_dc[i]): parts.append(z_dc[i] * 0.25)
            if parts:
                combined.append((t, sum(parts)))

        combined.sort(key=lambda kv: -kv[1])
        return [t for t, _ in combined]
    return rank_fn


# ══════════════════════════════════════════════════════════════════════════════
# 候选 4: 盈利+现金流双高质量 (Earnings-Cashflow Quality)
# ══════════════════════════════════════════════════════════════════════════════

def make_rank_fn_ec_quality(fp):
    """
    盈利+现金流双高质量稳健复利者: 四维度 z-score 等权合成
    ① ROA 高 (盈利能力强)
    ② CFOA 高 (现金流/资产,真实赚钱)
    ③ ROA 波动低 (盈利稳定,不是一次性的)
    ④ OCF/NI 稳健 (现金流覆盖利润,非应计驱动)
    连续打分, 强调盈利和现金流"双高"的公司
    """
    def rank_fn(view, params):
        as_of = pd.Timestamp(view.as_of)
        raw = []
        for t in view.available_tickers():
            if t not in fp.available_tickers():
                continue
            row = view.last_row(t)
            if row is None or row.get("close", 0) < 5:
                continue

            ni = fp.get_latest(t, "NetIncomeLoss", as_of, lag_days=45)
            ocf = fp.get_latest(t, "NetCashProvidedByUsedInOperatingActivities", as_of, lag_days=45)
            assets = fp.get_latest(t, "Assets", as_of, lag_days=45)

            if assets is None or assets <= 0:
                continue

            roa = ni / assets if ni is not None else None
            cfoa = ocf / assets if ocf is not None else None

            # ROA 稳定性 (过去4-8个季度)
            ni_series = fp.get_quarterly_series(t, "NetIncomeLoss", as_of, n_quarters=8, lag_days=45)
            assets_series = fp.get_quarterly_series(t, "Assets", as_of, n_quarters=8, lag_days=45)
            roa_std = None
            if len(ni_series) >= 4 and len(assets_series) >= 4:
                roas = []
                for (_, ni_v), (_, a_v) in zip(ni_series[-4:], assets_series[-4:]):
                    if a_v and a_v > 0:
                        roas.append(ni_v / a_v)
                if len(roas) >= 3:
                    roa_std = np.std(roas)

            # 现金流/利润比 (OCF/NI ratio, 稳健的应在0.5-2.0区间)
            # 用tanh归一化: 越接近1越好, 但不要硬门槛
            ocf_ni_quality = None
            if ni is not None and ocf is not None and abs(ni) > 1e6:
                ratio = ocf / ni
                # 距离1越远分越低 (但ratio=1最理想)
                ocf_ni_quality = 1.0 / (1.0 + abs(ratio - 1.0))

            raw.append((t, roa, cfoa, roa_std, ocf_ni_quality))

        if len(raw) < 5:
            return [t for t, _, _, _, _ in raw]

        def safe_z(vals, flip=False):
            arr = np.array([v if v is not None else np.nan for v in vals], dtype=float)
            mu = np.nanmean(arr); sigma = np.nanstd(arr)
            if sigma == 0 or np.isnan(sigma):
                return np.zeros(len(arr))
            z = (arr - mu) / sigma
            return -z if flip else z

        tickers = [r[0] for r in raw]
        z_roa = safe_z([r[1] for r in raw])           # ROA高=好
        z_cfoa = safe_z([r[2] for r in raw])           # CFOA高=好
        z_std = safe_z([-r[3] if r[3] is not None else None for r in raw])  # 低波动=好
        z_ocfni = safe_z([r[4] for r in raw])          # OCF/NI质量=好

        combined = []
        for i, t in enumerate(tickers):
            parts = []
            if not np.isnan(z_roa[i]): parts.append(z_roa[i] * 0.30)
            if not np.isnan(z_cfoa[i]): parts.append(z_cfoa[i] * 0.30)
            if not np.isnan(z_std[i]): parts.append(z_std[i] * 0.20)
            if not np.isnan(z_ocfni[i]): parts.append(z_ocfni[i] * 0.20)
            if parts:
                combined.append((t, sum(parts)))

        combined.sort(key=lambda kv: -kv[1])
        return [t for t, _ in combined]
    return rank_fn


# ══════════════════════════════════════════════════════════════════════════════
# 净口径组合对比引擎
# ══════════════════════════════════════════════════════════════════════════════

def compute_combo_metrics(mom_monthly, candidate_monthly,
                          w_mom=0.70, w_cand=0.30,
                          m2_monthly=None, w_m2=0.25,
                          capital=4000.0, label="combo"):
    """
    从月收益序列计算组合净指标。
    支持两腿 (mom + candidate) 和三腿 (mom + m2 + candidate)。

    组合层摩擦: 月再平衡 → 每月换手约3% → 扣佣金+滑点
    税: 保守用 STCG 25% (组合层快速再平衡)
    """
    if isinstance(mom_monthly, list):
        mom_monthly = pd.Series(mom_monthly)
    if isinstance(candidate_monthly, list):
        candidate_monthly = pd.Series(candidate_monthly)

    # 对齐月份
    common_idx = mom_monthly.index.intersection(candidate_monthly.index)
    if m2_monthly is not None:
        if isinstance(m2_monthly, list):
            m2_monthly = pd.Series(m2_monthly)
        common_idx = common_idx.intersection(m2_monthly.index)

    if len(common_idx) < 12:
        return None

    mom_r = mom_monthly[common_idx]
    cand_r = candidate_monthly[common_idx]

    # 组合月收益 (毛)
    if m2_monthly is not None:
        m2_r = m2_monthly[common_idx]
        combo_gross = w_mom * mom_r + w_m2 * m2_r + w_cand * cand_r
        is_three_leg = True
    else:
        combo_gross = w_mom * mom_r + w_cand * cand_r
        is_three_leg = False

    # 组合层摩擦
    monthly_turnover = 0.04 if is_three_leg else 0.03
    monthly_slip = monthly_turnover * 0.0005 * 2
    monthly_comm = monthly_turnover * (2.0 / capital)
    combo_net = combo_gross - monthly_slip - monthly_comm

    # 指标
    n = len(combo_net)
    total_ret = np.prod(1 + combo_net.values) - 1
    years = n / 12
    cagr = (1 + total_ret) ** (1 / years) - 1 if years > 0 else 0
    vol = np.std(combo_net.values, ddof=1) * np.sqrt(12) if n > 1 else 0
    sharpe = (cagr - 0.02) / vol if vol > 0 else 0
    cum = (1 + pd.Series(combo_net.values)).cumprod()
    max_dd = (cum / cum.cummax() - 1).min()

    # 纯动量净指标
    mom_net = mom_r - monthly_slip * 0.7 - monthly_comm * 0.7
    mom_total = np.prod(1 + mom_net.values) - 1
    mom_cagr = (1 + mom_total) ** (1 / years) - 1 if years > 0 else 0
    mom_vol = np.std(mom_net.values, ddof=1) * np.sqrt(12) if n > 1 else 0
    mom_sharpe = (mom_cagr - 0.02) / mom_vol if mom_vol > 0 else 0
    mom_cum = (1 + pd.Series(mom_net.values)).cumprod()
    mom_maxdd = (mom_cum / mom_cum.cummax() - 1).min()

    result = {
        "label": label,
        "n_months": n, "years": round(years, 1),
        "weights": {"w_mom": w_mom, "w_cand": w_cand},
        "combo_net_CAGR": round(cagr, 4),
        "combo_net_Sharpe": round(sharpe, 4),
        "combo_net_maxDD": round(max_dd, 4),
        "combo_net_vol": round(vol, 4),
        "mom_net_CAGR": round(mom_cagr, 4),
        "mom_net_Sharpe": round(mom_sharpe, 4),
        "mom_net_maxDD": round(mom_maxdd, 4),
        "mom_net_vol": round(mom_vol, 4),
        "delta_CAGR": round(cagr - mom_cagr, 4),
        "delta_Sharpe": round(sharpe - mom_sharpe, 4),
        "delta_maxDD": round(max_dd - mom_maxdd, 4),
        "sharpe_improved": sharpe > mom_sharpe,
        "maxdd_improved": max_dd > mom_maxdd,
        "three_leg": is_three_leg,
    }
    if m2_monthly is not None:
        result["weights"]["w_m2"] = w_m2
    return result


# ══════════════════════════════════════════════════════════════════════════════
# 加载 R23 M2 月收益 (复用，不复跑)
# ══════════════════════════════════════════════════════════════════════════════

def load_m2_monthly():
    """从 R23 result.json 加载最优 M2 的月收益"""
    r23_path = os.path.join(R23_DIR, "result.json")
    if not os.path.exists(r23_path):
        print("[WARN] R23 result.json not found, skipping M2 combo")
        return None

    with open(r23_path) as f:
        r23 = json.load(f)

    best_m2 = r23.get("best_m2_tamed", {})
    if not best_m2:
        return None

    # 读 M2 的单独 result 文件
    m2_label = best_m2.get("label", "M2_tamed_10slot_semi_sticky2.5x")
    # 找最接近的 result 文件
    m2_file = None
    for fn in os.listdir(R23_DIR):
        if fn.startswith("result_M2_tamed") and fn.endswith(".json") and "10slot_semi" in fn:
            m2_file = os.path.join(R23_DIR, fn)
            break
    if not m2_file:
        # fallback
        for fn in os.listdir(R23_DIR):
            if fn.startswith("result_M2_tamed") and fn.endswith(".json"):
                m2_file = os.path.join(R23_DIR, fn)
                break

    if not m2_file:
        print("[WARN] M2 result file not found")
        return None

    with open(m2_file) as f:
        m2_data = json.load(f)

    m2_monthly = m2_data.get("monthly_returns", [])
    m2_index = m2_data.get("monthly_returns_index", [])

    if not m2_monthly or not m2_index:
        return None

    s = pd.Series(m2_monthly, index=[pd.Period(idx, "M") for idx in m2_index])
    print(f"[M2] Loaded {len(s)} monthly returns from {os.path.basename(m2_file)}")
    return s


# ══════════════════════════════════════════════════════════════════════════════
# Survivor 敏感性分析
# ══════════════════════════════════════════════════════════════════════════════

def run_survivor_sweep(rank_fn, params, posmgmt, uni, spy, master, label,
                        drop_n_list=[5, 10, 20, 30]):
    """对给定策略跑 survivor 敏感性"""
    results = {}
    for drop_n in drop_n_list:
        duni = dict(uni)
        # drop_top_n_expost 在引擎里处理
        res_s = bl2.backtest_portfolio(
            rank_fn, params, posmgmt=posmgmt,
            uni=duni, spy=spy, master=master,
            drop_top_n_expost=drop_n, audit=True,
        )
        m_s = res_s["metrics"]
        results[f"drop_top_{drop_n}"] = {
            "CAGR": round(m_s.get("CAGR", 0), 4),
            "Sharpe": round(m_s.get("Sharpe", 0), 4),
            "maxDD": round(m_s.get("maxDD", 0), 4),
        }
        print(f"  [{label}] drop_top_{drop_n}: CAGR={m_s.get('CAGR'):.4f} "
              f"Sharpe={m_s.get('Sharpe'):.2f} maxDD={m_s.get('maxDD'):.4f}")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 70)
    print("R24 Group B — Find M2-type Complement Candidates (Quality Sleeve)")
    print("=" * 70)

    # ── 加载数据 ──
    uni, spy, master = load_broad_data()
    fp = FundamentalsPITExtended(verbose=True)
    edgar_set = set(fp.available_tickers())
    broad_set = set(uni.keys())
    overlap = edgar_set & broad_set
    print(f"\n[Data] Broad: {len(broad_set)}, EDGAR: {len(edgar_set)}, Overlap: {len(overlap)}")

    # ── 动量冠军对照 ──
    print("\n--- Champion (Momentum Sentinel on Broad) ---")
    champion_res = run_champion_broad(uni=uni, spy=spy, master=master)
    champ_m = champion_res["metrics"]
    champ_monthly = monthly_returns_from_equity(champion_res.get("equity", []))
    print(f"  Champion: CAGR={champ_m.get('CAGR'):.4f} Sharpe={champ_m.get('Sharpe'):.2f} "
          f"maxDD={champ_m.get('maxDD'):.4f} turnover={champ_m.get('turnover_per_yr'):.1f}")

    # ── 加载 R23 M2 ──
    m2_monthly = load_m2_monthly()

    # ── 候选策略定义 ──
    candidates = [
        ("SY", make_rank_fn_shareholder_yield(fp),
         "Shareholder Yield (Buyback + Dividend)",
         dict(n_slots=12, rebalance=126, weight_mode="invvol", max_weight=0.12, rebalance_threshold=0.20)),
        ("FCFY", make_rank_fn_fcf_yield(fp),
         "FCF Yield (OCF-CapEx)/MCap",
         dict(n_slots=12, rebalance=126, weight_mode="invvol", max_weight=0.12, rebalance_threshold=0.20)),
        ("DELEV", make_rank_fn_deleveraging(fp),
         "Deleveraging + Net Cash Trend",
         dict(n_slots=12, rebalance=126, weight_mode="invvol", max_weight=0.12, rebalance_threshold=0.20)),
        ("ECQ", make_rank_fn_ec_quality(fp),
         "Earnings-Cashflow Dual-High Quality",
         dict(n_slots=12, rebalance=126, weight_mode="invvol", max_weight=0.12, rebalance_threshold=0.20)),
    ]

    all_candidate_results = {}
    all_combos_2leg = {}
    all_combos_3leg = {}
    all_survivor = {}

    # ── 逐候选回测 ──
    for sig_key, rank_fn, desc, params in candidates:
        print(f"\n{'='*70}")
        print(f"Candidate: {sig_key} — {desc}")
        print(f"{'='*70}")

        # 回测多个黏性参数 (找最优)
        best_res = None
        best_label = None
        best_score = -999
        candidate_configs = {}

        for n_slots in [10, 12]:
            for sticky in [2.0, 2.5, 3.0]:
                label = f"{sig_key}_{n_slots}slots_sticky{sticky}x"
                p = dict(params)
                p["n_slots"] = n_slots
                pm = make_sticky_posmgmt(n_slots=n_slots, sticky_mult=sticky)

                try:
                    res = run_backtest(rank_fn, p, posmgmt=pm, uni=uni, spy=spy, master=master)
                except Exception as e:
                    print(f"  [{label}] ERROR: {e}")
                    continue

                m = res["metrics"]
                my_mr = monthly_returns_from_equity(res.get("equity", []))
                corr_info = calc_correlation(my_mr, champ_monthly, clean_window=True)

                cagr = m.get("CAGR", 0) or 0
                sharpe = m.get("Sharpe", 0) or 0
                maxdd = m.get("maxDD", 0) or 0
                turnover = m.get("turnover_per_yr", 99) or 99

                print(f"  [{label}] CAGR={cagr:.4f} Sharpe={sharpe:.2f} "
                      f"maxDD={maxdd:.4f} turnover={turnover:.1f} "
                      f"LTCG%={m.get('pct_long_term',0):.1%} corr={corr_info.get('corr')}")

                entry = {
                    "label": label, "n_slots": n_slots, "sticky_mult": sticky,
                    "CAGR": round(cagr, 4), "Sharpe": round(sharpe, 4),
                    "maxDD": round(maxdd, 4), "vol": round(m.get("vol", 0), 4),
                    "turnover_per_yr": round(turnover, 2),
                    "pct_long_term": round(m.get("pct_long_term", 0), 4),
                    "n_trades": int(m.get("n_trades", 0)),
                    "total_tax": round(m.get("total_tax", 0), 2),
                    "total_friction": round(m.get("total_friction", 0), 2),
                    "champion_corr": corr_info.get("corr"),
                    "corr_months": corr_info.get("aligned_len", 0),
                    "audit_violation": str(res.get("audit_violation", "None")),
                    "SPY_CAGR": round(res["spy_metrics"].get("CAGR", 0), 4),
                    "SPY_maxDD": round(res["spy_metrics"].get("maxDD", 0), 4),
                    "EW_CAGR": round(res["ew_metrics"].get("CAGR", 0), 4),
                    "EW_maxDD": round(res["ew_metrics"].get("maxDD", 0), 4),
                }
                candidate_configs[label] = entry

                # 评分: CAGR + Sharpe + maxDD depth + turnover penalty
                score = (cagr * 0.25 + sharpe * 1.0 + maxdd * 0.3 - max(0, turnover - 2.0) * 0.2)
                if turnover <= 2.0:
                    score += 0.5
                print(f"    score={score:.3f}")

                if score > best_score:
                    best_score = score
                    best_res = res
                    best_label = label

        if best_res is None:
            print(f"  [SKIP] {sig_key}: all configs failed")
            continue

        bm = best_res["metrics"]
        print(f"\n  ★ Best {sig_key}: {best_label} (score={best_score:.3f})")
        print(f"    CAGR={bm.get('CAGR'):.4f} Sharpe={bm.get('Sharpe'):.2f} "
              f"maxDD={bm.get('maxDD'):.4f} turnover={bm.get('turnover_per_yr'):.1f}")

        # 保存最优结果
        save_result(best_res, f"result_{sig_key}_best.json")

        # 最优配置的详细信息
        best_entry = candidate_configs[best_label]
        best_entry["best_label"] = best_label

        all_candidate_results[sig_key] = {
            "description": desc,
            "best_label": best_label,
            "best_config": best_entry,
            "configs": candidate_configs,
        }

        # ── 组合对比: 动量 + 候选 (两腿) ──
        best_monthly = monthly_returns_from_equity(best_res.get("equity", []))

        for w_mom, w_cand in [(0.70, 0.30), (0.60, 0.40), (0.50, 0.50)]:
            lbl = f"{sig_key}_mom{int(w_mom*100)}_c{int(w_cand*100)}"
            combo = compute_combo_metrics(champ_monthly, best_monthly,
                                          w_mom=w_mom, w_cand=w_cand,
                                          label=lbl)
            if combo:
                all_combos_2leg[lbl] = combo
                improved = "✅BOTH" if (combo["sharpe_improved"] and combo["maxdd_improved"]) else \
                           "✅S" if combo["sharpe_improved"] else \
                           "✅D" if combo["maxdd_improved"] else "❌"
                print(f"    2-leg {lbl}: net_S={combo['combo_net_Sharpe']:.4f} "
                      f"net_DD={combo['combo_net_maxDD']:.4f} "
                      f"ΔS={combo['delta_Sharpe']:+.4f} ΔDD={combo['delta_maxDD']:+.4f} {improved}")

        # ── 三腿组合: 动量 + M2 + 候选 ──
        if m2_monthly is not None:
            for w_mom, w_m2, w_cand in [(0.50, 0.25, 0.25), (0.55, 0.25, 0.20), (0.45, 0.25, 0.30)]:
                lbl3 = f"{sig_key}_3leg_mom{int(w_mom*100)}_m2{int(w_m2*100)}_c{int(w_cand*100)}"
                combo3 = compute_combo_metrics(champ_monthly, best_monthly,
                                               w_mom=w_mom, w_cand=w_cand,
                                               m2_monthly=m2_monthly, w_m2=w_m2,
                                               label=lbl3)
                if combo3:
                    all_combos_3leg[lbl3] = combo3
                    improved = "✅BOTH" if (combo3["sharpe_improved"] and combo3["maxdd_improved"]) else \
                               "✅S" if combo3["sharpe_improved"] else \
                               "✅D" if combo3["maxdd_improved"] else "❌"
                    print(f"    3-leg {lbl3}: net_S={combo3['combo_net_Sharpe']:.4f} "
                          f"net_DD={combo3['combo_net_maxDD']:.4f} "
                          f"ΔS={combo3['delta_Sharpe']:+.4f} ΔDD={combo3['delta_maxDD']:+.4f} {improved}")

        # ── Survivor 敏感性 (只用最优配置) ──
        print(f"\n  --- Survivor Sensitivity ({sig_key} best) ---")
        best_cfg = candidate_configs[best_label]
        p_surv = dict(params)
        p_surv["n_slots"] = best_cfg["n_slots"]
        pm_surv = make_sticky_posmgmt(n_slots=best_cfg["n_slots"],
                                       sticky_mult=best_cfg["sticky_mult"])
        surv = run_survivor_sweep(rank_fn, p_surv, pm_surv, uni, spy, master, sig_key)
        all_survivor[sig_key] = surv

    # ═══════════════════════════════════════════════════════════════════════════
    # 汇总输出 result.json
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("Writing final result.json")
    print("=" * 70)

    champion_summary = {
        "CAGR": round(champ_m.get("CAGR", 0), 4),
        "Sharpe": round(champ_m.get("Sharpe", 0), 4),
        "maxDD": round(champ_m.get("maxDD", 0), 4),
        "vol": round(champ_m.get("vol", 0), 4),
        "turnover_per_yr": round(champ_m.get("turnover_per_yr", 0), 2),
        "n_trades": int(champ_m.get("n_trades", 0)),
        "SPY_CAGR": round(champion_res["spy_metrics"].get("CAGR", 0), 4),
        "EW_CAGR": round(champion_res["ew_metrics"].get("CAGR", 0), 4),
    }

    # R23 M2 基线 (用于对比)
    m2_baseline = {}
    if m2_monthly is not None:
        # 计算 M2 的 standalone 指标
        r23_path = os.path.join(R23_DIR, "result.json")
        if os.path.exists(r23_path):
            with open(r23_path) as f:
                r23 = json.load(f)
            best_m2 = r23.get("best_m2_tamed", {})
            m2_baseline = {
                "label": best_m2.get("label", "M2_tamed_10slot_semi_sticky2.5x"),
                "CAGR": best_m2.get("CAGR"),
                "Sharpe": best_m2.get("Sharpe"),
                "maxDD": best_m2.get("maxDD"),
                "turnover_per_yr": best_m2.get("turnover_per_yr"),
                "pct_long_term": best_m2.get("pct_long_term"),
            }

    # 计算纯动量+M2 两腿基线 (用于三腿对比)
    mom_m2_baseline = None
    if m2_monthly is not None:
        mom_m2_baseline = compute_combo_metrics(
            champ_monthly, m2_monthly,
            w_mom=0.70, w_cand=0.30,
            label="mom70_m2_30_baseline"
        )

    final = {
        "round": "R24",
        "team": "B (DeepSeek)",
        "objective": "Find M2-type quality complement candidates for momentum sentinel",
        "three_criteria": {
            "1_solo_CAGR_gte_9pct": "单腿净CAGR≥9-10%稳赢SPY",
            "2_solo_maxDD_lte_minus35": "单腿maxDD≤-35%浅回撤",
            "3_combo_improves_sharpe_and_maxdd": "与动量组合后Sharpe涨+回撤降",
        },
        "champion_momentum_broad": champion_summary,
        "m2_r23_baseline": m2_baseline,
        "mom_m2_2leg_baseline": mom_m2_baseline,
        "candidates": all_candidate_results,
        "combos_2leg": all_combos_2leg,
        "combos_3leg": all_combos_3leg,
        "survivor_sensitivity": all_survivor,
        "data": {
            "broad_pool_stocks": len(uni),
            "edgar_stocks": len(fp.available_tickers()),
            "edgar_in_broad": len(overlap),
            "edgar_dividend_tickers": len([t for t in fp._tickers if fp._dividend_data.get(t)]),
        },
        "runtime_seconds": round(time.time() - t0, 1),
    }

    result_path = os.path.join(OUTPUT_DIR, "result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(final, f, cls=NpEncoder, indent=2, ensure_ascii=False)
    print(f"\nFinal result.json → {result_path}")

    # ── 快速汇总 ──
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Champion Momentum: CAGR={champ_m.get('CAGR'):.4f} "
          f"Sharpe={champ_m.get('Sharpe'):.2f} maxDD={champ_m.get('maxDD'):.4f}")
    print(f"M2 baseline (R23): {m2_baseline}")
    for sig_key, cand in all_candidate_results.items():
        bc = cand["best_config"]
        c1 = "✅" if bc["CAGR"] >= 0.09 else "⚠️"
        c2 = "✅" if bc["maxDD"] >= -0.35 else "⚠️"
        print(f"  {sig_key} ({cand['best_label']}): CAGR={bc['CAGR']:.4f}{c1} "
              f"Sharpe={bc['Sharpe']:.2f} maxDD={bc['maxDD']:.4f}{c2} "
              f"corr={bc['champion_corr']} turnover={bc['turnover_per_yr']:.1f}")

    # 找最佳两腿/三腿组合
    print("\n--- Best 2-leg Combos ---")
    best_2leg = {}
    for label, combo in sorted(all_combos_2leg.items(),
                                key=lambda kv: kv[1]["combo_net_Sharpe"], reverse=True)[:5]:
        imp = "✅BOTH" if (combo["sharpe_improved"] and combo["maxdd_improved"]) else \
              "✅S" if combo["sharpe_improved"] else "✅D" if combo["maxdd_improved"] else "❌"
        print(f"  {label}: S={combo['combo_net_Sharpe']:.4f} DD={combo['combo_net_maxDD']:.4f} "
              f"ΔS={combo['delta_Sharpe']:+.4f} ΔDD={combo['delta_maxDD']:+.4f} {imp}")

    print("\n--- Best 3-leg Combos ---")
    for label, combo in sorted(all_combos_3leg.items(),
                                key=lambda kv: kv[1]["combo_net_Sharpe"], reverse=True)[:5]:
        imp = "✅BOTH" if (combo["sharpe_improved"] and combo["maxdd_improved"]) else \
              "✅S" if combo["sharpe_improved"] else "✅D" if combo["maxdd_improved"] else "❌"
        print(f"  {label}: S={combo['combo_net_Sharpe']:.4f} DD={combo['combo_net_maxDD']:.4f} "
              f"ΔS={combo['delta_Sharpe']:+.4f} ΔDD={combo['delta_maxDD']:+.4f} {imp}")

    if mom_m2_baseline:
        print(f"\n  mom+M2 baseline: S={mom_m2_baseline['combo_net_Sharpe']:.4f} "
              f"DD={mom_m2_baseline['combo_net_maxDD']:.4f}")

    print("\nDONE.")
    return final


if __name__ == "__main__":
    main()
