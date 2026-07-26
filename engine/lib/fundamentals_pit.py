"""
fundamentals_pit.py —— PIT (Point-in-Time) SEC EDGAR 基本面加载模块
===================================================================
从 round16/groupA/data/raw_secfacts/ 加载 98 只股票的 SEC XBRL 事实数据，
提供 PIT 查询接口：只用到 filed ≤ as_of - lag_days 的数据。

关键概念 (已验证存在于 raw_secfacts):
- NetIncomeLoss, OperatingIncomeLoss
- NetCashProvidedByUsedInOperatingActivities
- DepreciationDepletionAndAmortization, DepreciationAndAmortization
- Assets, AssetsCurrent, LiabilitiesCurrent
- CashAndCashEquivalentsAtCarryingValue
- InventoryNet
- IncreaseDecreaseInAccountsReceivable, IncreaseDecreaseInAccountsPayable
- IncreaseDecreaseInInventories
- CommonStockSharesOutstanding
- PaymentsForRepurchaseOfCommonStock, ProceedsFromIssuanceOfCommonStock
- StockholdersEquity
- PaymentsToAcquirePropertyPlantAndEquipment

每条记录: {end, val, accn, fy, fp, form, filed, frame?}
"""

import json
import os
import numpy as np
import pandas as pd
from collections import defaultdict

DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
EDGAR_DIR = os.path.join(DATA_DIR, "secfacts")

# 需要加载的 XBRL 概念清单
CONCEPTS = [
    "NetIncomeLoss",
    "NetCashProvidedByUsedInOperatingActivities",
    "DepreciationDepletionAndAmortization",
    "DepreciationAndAmortization",
    "Assets",
    "AssetsCurrent",
    "LiabilitiesCurrent",
    "CashAndCashEquivalentsAtCarryingValue",
    "InventoryNet",
    "IncreaseDecreaseInAccountsReceivable",
    "IncreaseDecreaseInAccountsPayable",
    "IncreaseDecreaseInInventories",
    "CommonStockSharesOutstanding",
    "PaymentsForRepurchaseOfCommonStock",
    "ProceedsFromIssuanceOfCommonStock",
    "StockholdersEquity",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "OperatingIncomeLoss",
]


class FundamentalsPIT:
    """PIT 基本面数据访问器。

    用法:
        fp = FundamentalsPIT()
        ni = fp.get_latest("AAPL", "NetIncomeLoss", as_of="2020-06-30", lag_days=45)
        shares_delta = fp.get_delta("AAPL", "CommonStockSharesOutstanding",
                                      as_of="2020-06-30", lookback_days=365, lag_days=45)
    """

    def __init__(self, data_dir=None, verbose=True):
        self.data_dir = data_dir or EDGAR_DIR
        # ticker -> concept -> sorted list of records (by filed date)
        self._data = defaultdict(lambda: defaultdict(list))
        self._tickers = set()
        self._load(verbose)

    def _load(self, verbose):
        """加载所有 raw_secfacts JSON 文件"""
        if not os.path.isdir(self.data_dir):
            if verbose:
                print(f"[FundamentalsPIT] WARNING: {self.data_dir} not found")
            return

        files = [f for f in os.listdir(self.data_dir) if f.endswith('.json')]
        for fn in files:
            ticker = fn.replace('.json', '')
            self._tickers.add(ticker)
            filepath = os.path.join(self.data_dir, fn)
            try:
                with open(filepath, 'r') as f:
                    raw = json.load(f)
            except (json.JSONDecodeError, IOError):
                continue

            facts = raw.get('facts', {})
            for taxonomy, tax_data in facts.items():
                if not isinstance(tax_data, dict):
                    continue
                for concept_name in CONCEPTS:
                    if concept_name not in tax_data:
                        continue
                    concept = tax_data[concept_name]
                    if not isinstance(concept, dict) or 'units' not in concept:
                        continue
                    units = concept['units']
                    for unit_type, records in units.items():
                        if not records:
                            continue
                        for rec in records:
                            if not isinstance(rec, dict):
                                continue
                            filed = rec.get('filed', '')
                            end = rec.get('end', '')
                            val = rec.get('val')
                            if not filed or val is None:
                                continue
                            # 只保留年度/半年度/季度数据（排除不规则 frame）
                            fp_val = rec.get('fp', '')
                            if fp_val not in ('FY', 'Q1', 'Q2', 'Q3', 'Q4', 'H1', 'H2'):
                                # 有些是 frame 格式如 CY2009，也接受
                                frame = rec.get('frame', '')
                                if not frame:
                                    continue
                            # 按 filed 日期排序
                            self._data[ticker][concept_name].append({
                                'end': end,
                                'filed': filed,
                                'val': float(val),
                                'fp': fp_val,
                                'form': rec.get('form', ''),
                            })

        # 排序每条时间序列
        for ticker in self._data:
            for concept in self._data[ticker]:
                self._data[ticker][concept].sort(key=lambda r: r['filed'])

        if verbose:
            n_tickers = len(self._tickers)
            n_with_data = sum(1 for t in self._tickers if self._data[t])
            print(f"[FundamentalsPIT] Loaded {n_with_data}/{n_tickers} tickers "
                  f"from {len(files)} files")
            # 检查覆盖率
            for concept_name in CONCEPTS:
                n = sum(1 for t in self._tickers
                       if concept_name in self._data[t] and self._data[t][concept_name])
                if n > 0:
                    print(f"  {concept_name}: {n} tickers")

    def available_tickers(self):
        """返回有 EDGAR 数据的 ticker 列表"""
        return sorted([t for t in self._tickers if self._data[t]])

    def get_latest(self, ticker, concept, as_of, lag_days=45):
        """获取 as_of - lag_days 之前最近一次 filed 的该概念值。

        Args:
            ticker: 股票代码
            concept: XBRL 概念名 (如 "NetIncomeLoss")
            as_of: 查询日期 (str 或 pd.Timestamp)
            lag_days: 提交延迟天数 (默认 45 天，模拟真实可得性)

        Returns:
            float 或 None (无数据)
        """
        as_of_ts = pd.Timestamp(as_of)
        cutoff = as_of_ts - pd.Timedelta(days=lag_days)

        records = self._data.get(ticker, {}).get(concept, [])
        best = None
        for rec in records:
            filed_ts = pd.Timestamp(rec['filed'])
            if filed_ts <= cutoff:
                best = rec
            else:
                break  # 已排序，后面的 filed 更晚
        return best['val'] if best else None

    def get_delta(self, ticker, concept, as_of, lookback_days=365, lag_days=45):
        """获取 concept 在 lookback 窗口内的变化量。

        返回: (current - previous) 或 None
        """
        as_of_ts = pd.Timestamp(as_of)
        cutoff = as_of_ts - pd.Timedelta(days=lag_days)
        lookback_start = cutoff - pd.Timedelta(days=lookback_days)

        records = self._data.get(ticker, {}).get(concept, [])
        current = None
        previous = None
        for rec in records:
            filed_ts = pd.Timestamp(rec['filed'])
            if filed_ts <= cutoff:
                current = rec
            if filed_ts <= lookback_start:
                previous = rec

        if current and previous:
            return current['val'] - previous['val']
        return None

    def get_quarterly_series(self, ticker, concept, as_of, n_quarters=4, lag_days=45):
        """获取最近 n 个季度的概念值序列 (用于 TTM 计算)。
        返回: [(end_date, val), ...] 按 end 日期升序
        """
        as_of_ts = pd.Timestamp(as_of)
        cutoff = as_of_ts - pd.Timedelta(days=lag_days)

        records = self._data.get(ticker, {}).get(concept, [])
        qualified = []
        for rec in records:
            if pd.Timestamp(rec['filed']) <= cutoff:
                qualified.append(rec)

        # 按 end 日期排序，取最近 n 条
        qualified.sort(key=lambda r: r['end'])
        return [(r['end'], r['val']) for r in qualified[-n_quarters:]]

    def compute_accruals_sloan(self, ticker, as_of, lag_days=45):
        """计算 Sloan (1996) 应计项目。

        简化公式 (基于资产负债表):
        Accruals_BS = (ΔCurrentAssets - ΔCash) - (ΔCurrentLiabilities) - Depreciation
        标准化: Accruals / AverageTotalAssets

        更稳健的公式 (基于现金流量表):
        Accruals_CF = (NetIncome - OperatingCashFlow) / AverageTotalAssets

        返回: dict with 'accruals_bs', 'accruals_cf', 'total_assets'
        或 None (数据不足)
        """
        as_of_ts = pd.Timestamp(as_of)
        cutoff = as_of_ts - pd.Timedelta(days=lag_days)
        lookback_start = cutoff - pd.Timedelta(days=365)

        recs = self._data.get(ticker, {})

        # ---- 获取最新值和一年前值 ----
        def _get_current_prev(concept_name):
            records = recs.get(concept_name, [])
            cur, prev = None, None
            for r in records:
                if pd.Timestamp(r['filed']) <= cutoff:
                    cur = r
                if pd.Timestamp(r['filed']) <= lookback_start:
                    prev = r
            return (cur['val'] if cur else None, prev['val'] if prev else None)

        # 资产负债表应计
        ca_cur, ca_prev = _get_current_prev("AssetsCurrent")
        cash_cur, cash_prev = _get_current_prev("CashAndCashEquivalentsAtCarryingValue")
        cl_cur, cl_prev = _get_current_prev("LiabilitiesCurrent")
        depr_cur, _ = _get_current_prev("DepreciationDepletionAndAmortization")
        if depr_cur is None:
            depr_cur, _ = _get_current_prev("DepreciationAndAmortization")

        assets_cur, assets_prev = _get_current_prev("Assets")

        # 现金流量表应计
        ni_cur, _ = _get_current_prev("NetIncomeLoss")
        cfo_cur, _ = _get_current_prev("NetCashProvidedByUsedInOperatingActivities")

        result = {}

        # 资产负债表法
        if all(v is not None for v in [ca_cur, ca_prev, cash_cur, cash_prev,
                                         cl_cur, cl_prev, assets_cur, assets_prev]):
            delta_ca = ca_cur - ca_prev
            delta_cash = cash_cur - cash_prev
            delta_cl = cl_cur - cl_prev
            depr = depr_cur if depr_cur else 0
            avg_assets = (assets_cur + assets_prev) / 2
            if avg_assets > 0:
                accruals_bs = (delta_ca - delta_cash - delta_cl - depr) / avg_assets
                result['accruals_bs'] = round(accruals_bs, 6)
                result['total_assets'] = assets_cur

        # 现金流量表法 (更可靠)
        if all(v is not None for v in [ni_cur, cfo_cur, assets_cur, assets_prev]):
            avg_assets = (assets_cur + assets_prev) / 2
            if avg_assets > 0:
                accruals_cf = (ni_cur - cfo_cur) / avg_assets
                result['accruals_cf'] = round(accruals_cf, 6)
                if 'total_assets' not in result:
                    result['total_assets'] = assets_cur

        return result if result else None

    def compute_net_issuance(self, ticker, as_of, lag_days=45):
        """计算净增发 (Pontiff & Woodgate)。

        NetIssuance = log(SharesOutstanding_t / SharesOutstanding_{t-12m})
        负值 = 回购 (好)

        返回: float 或 None
        """
        recs = self._data.get(ticker, {}).get("CommonStockSharesOutstanding", [])
        if not recs:
            return None

        as_of_ts = pd.Timestamp(as_of)
        cutoff = as_of_ts - pd.Timedelta(days=lag_days)
        lookback = cutoff - pd.Timedelta(days=365)

        cur_shares = None
        prev_shares = None
        for r in recs:
            if pd.Timestamp(r['filed']) <= cutoff:
                cur_shares = r['val']
            if pd.Timestamp(r['filed']) <= lookback:
                prev_shares = r['val']

        if cur_shares and prev_shares and prev_shares > 0:
            return np.log(cur_shares / prev_shares)
        return None

    def get_pit_date_range(self, ticker, concept=None):
        """返回某 ticker 的 PIT 可用日期范围"""
        if concept:
            recs = self._data.get(ticker, {}).get(concept, [])
        else:
            recs = []
            for c_recs in self._data.get(ticker, {}).values():
                recs.extend(c_recs)
        if not recs:
            return None, None
        fileds = sorted(set(r['filed'] for r in recs))
        return fileds[0], fileds[-1]


# ---- 自测 ----
if __name__ == "__main__":
    fp = FundamentalsPIT(verbose=True)
    tickers = fp.available_tickers()
    print(f"\nAvailable tickers: {len(tickers)}")
    print(f"First 10: {tickers[:10]}")

    # 测试 AAPL
    as_of = "2020-06-30"
    print(f"\n--- AAPL PIT as of {as_of} (lag=45d) ---")
    for c in ["NetIncomeLoss", "NetCashProvidedByUsedInOperatingActivities",
              "Assets", "AssetsCurrent", "LiabilitiesCurrent",
              "CommonStockSharesOutstanding", "DepreciationDepletionAndAmortization"]:
        v = fp.get_latest("AAPL", c, as_of)
        print(f"  {c}: {v}")

    # 应计
    acc = fp.compute_accruals_sloan("AAPL", as_of)
    print(f"\n  Accruals: {acc}")

    # 净增发
    ni = fp.compute_net_issuance("AAPL", as_of)
    print(f"  NetIssuance: {ni}")

    # 日期范围
    start, end = fp.get_pit_date_range("AAPL")
    print(f"\n  PIT date range: {start} ~ {end}")

    print("\n[FundamentalsPIT] Self-test complete.")
