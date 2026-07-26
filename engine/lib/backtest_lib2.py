"""
round9/lib/backtest_lib2.py
===========================
第九轮【扩展版】共享回测引擎 —— 在 round8/lib/backtest_lib.py 基础上加四个新框架杠杆,
不改 round8 原文件(import 复用其指标/PITView/摩擦/基准/指标计算)。

新框架(用户 2026-06-28 校正目标):以收益最佳为目标、持有【灵活】(天/周/月皆可)、
允许【动态仓位管理】(加仓赢家/减仓走弱/移动止盈/单笔风险预算)的【选股交易系统】,
老虎手动可执行,永不做空(看空=减/清仓)。

四大新杠杆(相对 round8):
  ①【按持有期分税】lot 级 FIFO:卖出时逐 lot 按持有天数判 ≥365→LTCG(默认15%) /
     <365→STCG(默认25%),年末结算(支持当年 LT/ST 互抵 + 亏损结转)。这是本轮核心收益杠杆。
  ②【动态仓位管理钩子】posmgmt cfg 驱动:
     (a) 金字塔加仓 pyramid:突破入场后新高 / 浮盈达阈值 时对赢家加一个单元(受单票上限约束)
     (b) 减仓走弱 trim:破中期均线 / 跌出排名前列 时【部分】减仓(而非全清)
     (c) 移动止盈/移动止损 trail:chandelier(吊灯) 或 收盘破均线
     (d) 单笔风险预算 weight_mode='risk':按到止损的距离定股数,使每笔风险占比一致
  ③【低换手再平衡】rebalance ∈ {'M' 月,'Q' 季,'W-MON' 周,int 交易日};
     rebalance_threshold 偏离阈值触发(继续持有的名仅在权重漂移超阈值时才动)→ 压换手、省税省佣金。
  ④【可变集中度】n_slots ∈ 3..8;weight_mode ∈ {'equal','invvol'(波动倒数),'rs'(相对强弱加权),'risk'}。

铁律(全部保留):
  - POINT-IN-TIME 无前视:每决策日 t 用 PITView(末日<=t),所有下单 t+1 open 执行;
    移动止损/止盈的止损位用【<=t-1 收盘】更新,次日才检验 → 不偷看未来。audit_violation 必须 None。
  - 真实摩擦:老虎佣金 max(.99,.0039sh)+平台 max(1,.004sh);滑点 0.05%/边;按持有期分档税。
  - 个股 gap 悲观:跳空击穿止损按 open 成交;同日先止损后止盈按止损。
  - 双基准:同池等权 BH(被幸存者抬高,诚实标注) + SPY-BH,同区间同口径。
  - 幸存者敏感性:drop_top_n_expost 剔全期最强 N 票。

研究推演,非投资建议。
"""

import os
import sys
import math
import numpy as np
import pandas as pd

# 复用 round8 引擎(禁改原文件,只 import)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_lib as bl  # noqa: E402

DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))

# 直接复用的零件
load_universe = bl.load_universe
PITView = bl.PITView
commission = bl.commission
_metrics = bl._metrics
_equal_weight_benchmark = bl._equal_weight_benchmark
_spy_benchmark = bl._spy_benchmark
rank_fn_momentum_demo = bl.rank_fn_momentum_demo


# ----------------------------------------------------------------------------
# 默认参数
# ----------------------------------------------------------------------------
DEFAULT_PARAMS2 = dict(
    capital=4000.0,
    n_slots=6,                 # 集中度 3..8
    rebalance="M",             # 'M'|'Q'|'W-MON'|int(交易日)
    weight_mode="equal",       # 'equal'|'invvol'|'rs'|'risk'
    rebalance_threshold=0.0,   # 继续持有名权重漂移 < 阈值则不动(低换手)。0=每次都对齐
    slippage=0.0005,
    ltcg_rate=0.15,            # 长期资本利得税(>=365天)
    stcg_rate=0.25,            # 短期资本利得税(<365天,普通税率主情景)
    ltcg_days=365,
    min_history=252,
    risk_pct=0.02,             # weight_mode='risk'/金字塔加仓 的单笔风险预算
    max_weight=0.40,           # 单票上限(含金字塔加仓后)
    invvol_lookback=20,        # 波动倒数定权所用 ATR%
    seed=0,
)

DEFAULT_POSMGMT = dict(
    enabled=False,             # 总开关。False=纯轮动(无日内加减仓/止损)
    stop_atr_mult=0.0,         # 硬止损 = entry - k*ATR_entry。0=无硬止损
    trail_mode="none",         # 'none'|'chandelier'|'ma'
    trail_atr_mult=3.0,        # chandelier: stop = HHV_close_since_entry - k*ATR_entry
    trail_ma_period=200,       # 'ma': 收盘 < SMA(period) → 全清(破位)
    # 金字塔加仓(对赢家)
    pyramid=False,
    pyramid_breakout=50,       # 入场后收盘创 N 日新高 → 加仓
    pyramid_step_gain=0.0,     # 或:浮盈 >= 此比例 → 加仓(与 breakout 取或)
    pyramid_max_adds=3,        # 最多加几次
    pyramid_add_frac=0.5,      # 每次加仓规模 = 基础目标权重 * frac
    pyramid_min_gap_days=10,   # 两次加仓最小间隔(防同一突破连加)
    # 减仓走弱(部分,而非全清)
    trim_ma_period=0,          # 收盘 < SMA(period) → 部分减仓。0=关
    trim_frac=0.5,             # 减仓比例
)


# ----------------------------------------------------------------------------
# 税:lot 级 FIFO,持有期分档 + 当年 LT/ST 互抵 + 亏损结转
# ----------------------------------------------------------------------------
class TaxBook:
    """累计当年 LT / ST 已实现损益(signed),年末结算。亏损可跨年结转。"""
    def __init__(self, ltcg_rate, stcg_rate):
        self.ltcg_rate = ltcg_rate
        self.stcg_rate = stcg_rate
        self.year_lt = 0.0
        self.year_st = 0.0
        self.loss_carry = 0.0      # 累计可结转净亏损(正数表示有 carry)
        self.total_tax = 0.0
        self.cum_lt_gain = 0.0     # 诊断:全期 LT 实现盈(仅正)
        self.cum_st_gain = 0.0
        self.cum_lt_real = 0.0     # 诊断:全期 LT 实现净额(signed)
        self.cum_st_real = 0.0

    def realize(self, gain, is_long_term):
        if is_long_term:
            self.year_lt += gain
            self.cum_lt_real += gain
            if gain > 0:
                self.cum_lt_gain += gain
        else:
            self.year_st += gain
            self.cum_st_real += gain
            if gain > 0:
                self.cum_st_gain += gain

    def settle_year(self):
        """返回当年应缴税(>=0),并复位年内桶。"""
        net_lt = self.year_lt
        net_st = self.year_st
        # 当年内 LT/ST 反向互抵
        if net_st < 0 and net_lt > 0:
            off = min(-net_st, net_lt)
            net_lt -= off
            net_st += off
        elif net_lt < 0 and net_st > 0:
            off = min(-net_lt, net_st)
            net_st -= off
            net_lt += off
        # 先用历史结转亏损抵(优先抵高税率 ST)
        taxable_st = max(0.0, net_st)
        taxable_lt = max(0.0, net_lt)
        if self.loss_carry > 0:
            use = min(self.loss_carry, taxable_st)
            taxable_st -= use
            self.loss_carry -= use
            if self.loss_carry > 0:
                use = min(self.loss_carry, taxable_lt)
                taxable_lt -= use
                self.loss_carry -= use
        tax = self.stcg_rate * taxable_st + self.ltcg_rate * taxable_lt
        # 当年净亏损 → 增加结转
        net_total = net_lt + net_st
        if net_total < 0:
            self.loss_carry += -net_total
        self.total_tax += tax
        self.year_lt = 0.0
        self.year_st = 0.0
        return tax


# ----------------------------------------------------------------------------
# 持仓:lot 列表(FIFO)+ 移动止损状态
# ----------------------------------------------------------------------------
class Lot:
    __slots__ = ("shares", "cost", "open_mi")
    def __init__(self, shares, cost, open_mi):
        self.shares = shares      # 股数
        self.cost = cost          # 每股成本(含买入滑点 + 摊买入佣金)
        self.open_mi = open_mi    # master index 入场


class Position:
    __slots__ = ("tkr", "lots", "atr_entry", "first_mi", "hhv_close",
                 "n_adds", "last_add_mi")
    def __init__(self, tkr, atr_entry, first_mi, entry_close):
        self.tkr = tkr
        self.lots = []
        self.atr_entry = atr_entry      # 入场时 ATR(固定,用于止损/加仓单元)
        self.first_mi = first_mi
        self.hhv_close = entry_close
        self.n_adds = 0
        self.last_add_mi = first_mi

    @property
    def shares(self):
        return sum(l.shares for l in self.lots)

    @property
    def avg_cost(self):
        s = self.shares
        if s <= 0:
            return 0.0
        return sum(l.shares * l.cost for l in self.lots) / s


# ----------------------------------------------------------------------------
# 主回测(组合级,支持动态仓位管理 + 分档税 + 低换手 + 可变集中度)
# ----------------------------------------------------------------------------
def backtest_portfolio(rank_fn, params=None, posmgmt=None, uni=None, spy=None,
                       master=None, data_dir=None, exclude=None,
                       drop_top_n_expost=0, audit=True):
    """
    rank_fn(view, params) -> 已过滤+排名的 ticker 列表(best first),无前视。
    params: 见 DEFAULT_PARAMS2。 posmgmt: 见 DEFAULT_POSMGMT(dict)或 callable(详见文末)。
    返回 dict:equity + metrics + 双基准 + trades + 税分账 + 风险画像 + audit。

    执行模型(统一无前视):决策日 t 用 PITView(末日<=t)出信号 → 所有订单 t+1 open 成交;
    移动止损位用 <=t-1 收盘更新,次日才检验(gap 悲观)→ 绝不偷看未来。
    """
    P = dict(DEFAULT_PARAMS2); P.update(params or {})
    M = dict(DEFAULT_POSMGMT)
    pm_callable = None
    if callable(posmgmt):
        pm_callable = posmgmt
    elif posmgmt:
        M.update(posmgmt)

    if uni is None:
        uni, spy, master = load_universe(data_dir, exclude=exclude)
    uni = dict(uni)

    # 幸存者敏感性:剔全期最强 N 票
    dropped = []
    if drop_top_n_expost > 0:
        perf = {t: df["close"].iloc[-1] / df["close"].iloc[0] - 1.0 for t, df in uni.items()}
        dropped = [t for t, _ in sorted(perf.items(), key=lambda kv: -kv[1])][:drop_top_n_expost]
        for t in dropped:
            uni.pop(t, None)

    N = int(P["n_slots"])
    cap0 = float(P["capital"])
    slip = P["slippage"]
    min_hist = P["min_history"]
    max_w = P["max_weight"]

    cal = pd.DatetimeIndex(master)
    master_arr = cal.values

    # ticker -> date->row idx 映射 + 数组(加速)
    tkr_idx = {}
    arrs = {}
    for t, df in uni.items():
        tkr_idx[t] = {pd.Timestamp(x): i for i, x in enumerate(df["date"].values)}
        arrs[t] = dict(
            open=df["open"].values, high=df["high"].values, low=df["low"].values,
            close=df["close"].values, atr14=df["atr14"].values,
        )

    # 调仓信号日(master index 集合)
    if isinstance(P["rebalance"], int):
        rebal_set = set(range(0, len(master), P["rebalance"]))
    else:
        _freq = {"M": "ME", "Q": "QE"}.get(P["rebalance"], P["rebalance"])
        rdays = pd.date_range(cal[0], cal[-1], freq=_freq)
        rebal_set = set()
        for rd in rdays:
            si = int(np.searchsorted(master_arr, np.datetime64(rd), side="right") - 1)
            if 0 <= si < len(master):
                rebal_set.add(si)

    def bar(t, mi_date):
        i = tkr_idx[t].get(pd.Timestamp(mi_date))
        if i is None:
            return None
        a = arrs[t]
        return dict(o=a["open"][i], h=a["high"][i], l=a["low"][i],
                    c=a["close"][i], atr=a["atr14"][i], i=i)

    def sma_close(t, i, period):
        a = arrs[t]["close"]
        if i + 1 < period:
            return np.nan
        return a[i + 1 - period:i + 1].mean()

    def hhv_close(t, i, period):
        a = arrs[t]["close"]
        if i + 1 < period:
            return np.nan
        return a[i + 1 - period:i + 1].max()

    # 状态
    cash = cap0
    positions = {}          # tkr -> Position
    trades = []
    equity_curve = []
    tot_comm = 0.0
    tot_slip = 0.0
    tax = TaxBook(P["ltcg_rate"], P["stcg_rate"])
    cur_year = pd.Timestamp(master[0]).year
    audit_violation = None
    pending = {}            # mi -> list[order dict]

    # ---- 成交执行 ----
    def do_buy(tkr, mi, mi_date, dollars, atr_for_stop=None):
        nonlocal cash, tot_comm, tot_slip
        b = bar(tkr, mi_date)
        if b is None or b["o"] <= 0:
            return
        fill = b["o"] * (1 + slip)
        dollars = min(dollars, cash)
        if dollars <= 0:
            return
        shares = int(dollars // fill)
        if shares <= 0:
            return
        comm = commission(shares)
        cost_total = fill * shares + comm
        if cost_total > cash:
            shares = int((cash - comm) // fill)
            if shares <= 0:
                return
            comm = commission(shares)
            cost_total = fill * shares + comm
        cash -= cost_total
        tot_comm += comm
        tot_slip += b["o"] * slip * shares
        cps = fill + comm / shares      # 每股成本含买入佣金
        if tkr not in positions:
            atr = atr_for_stop if atr_for_stop is not None else b["atr"]
            positions[tkr] = Position(tkr, atr, mi, b["c"])
        positions[tkr].lots.append(Lot(shares, cps, mi))

    def do_sell(tkr, mi, mi_date, shares_to_sell, reason, fill_price=None):
        """FIFO 卖 shares_to_sell(None=全清),逐 lot 分档计税。"""
        nonlocal cash, tot_comm, tot_slip
        pos = positions.get(tkr)
        if pos is None:
            return
        b = bar(tkr, mi_date)
        if b is None:
            return
        have = pos.shares
        s = have if shares_to_sell is None else min(shares_to_sell, have)
        if s <= 0:
            return
        raw_px = fill_price if fill_price is not None else b["o"]
        fill = raw_px * (1 - slip)        # 卖出滑点(止损位也再扣滑点,悲观)
        # 卖出佣金按本次股数
        comm = commission(s)
        comm_ps = comm / s
        remaining = s
        realized_records = []
        new_lots = []
        for lot in pos.lots:
            if remaining <= 0:
                new_lots.append(lot)
                continue
            use = min(lot.shares, remaining)
            net_ps = fill - comm_ps          # 每股净售价(扣卖佣金)
            gain = (net_ps - lot.cost) * use
            held_days = (pd.Timestamp(master[mi]) - pd.Timestamp(master[lot.open_mi])).days
            is_lt = held_days >= P["ltcg_days"]
            tax.realize(gain, is_lt)
            realized_records.append((use, lot.open_mi, gain, is_lt))
            remaining -= use
            if lot.shares > use:
                new_lots.append(Lot(lot.shares - use, lot.cost, lot.open_mi))
        pos.lots = new_lots
        proceeds = fill * s - comm
        cash += proceeds
        tot_comm += comm
        tot_slip += raw_px * slip * s
        net_gain = sum(r[2] for r in realized_records)
        lt_sh = sum(r[0] for r in realized_records if r[3])
        for use, omi, gain, is_lt in realized_records:
            trades.append(dict(
                tkr=tkr, entry_date=str(pd.Timestamp(master[omi]).date()),
                exit_date=str(pd.Timestamp(master[mi]).date()), shares=use,
                hold_days=(pd.Timestamp(master[mi]) - pd.Timestamp(master[omi])).days,
                reason=reason, net=round(gain, 2), long_term=bool(is_lt),
            ))
        if pos.shares <= 0:
            positions.pop(tkr, None)

    def equity_now(mi_date):
        v = cash
        for t, pos in positions.items():
            b = bar(t, mi_date)
            px = b["c"] if b else pos.avg_cost
            v += px * pos.shares
        return v

    def target_weights(ranked, view):
        """前 N 名 → 目标权重 dict。weight_mode 决定定权。"""
        picks = ranked[:N]
        if not picks:
            return {}
        if P["weight_mode"] == "equal":
            w = {t: 1.0 / len(picks) for t in picks}
        elif P["weight_mode"] == "invvol":
            inv = {}
            for t in picks:
                row = view.last_row(t)
                px = row["close"] if row is not None else None
                atr = row["atr14"] if row is not None else None
                if px and atr and atr > 0:
                    inv[t] = px / atr          # 波动倒数 ∝ 价格/ATR
                else:
                    inv[t] = 0.0
            s = sum(inv.values()) or 1.0
            w = {t: inv[t] / s for t in picks}
        elif P["weight_mode"] == "rs":
            n = len(picks)
            raw = {t: (n - i) for i, t in enumerate(picks)}   # 排名加权
            s = sum(raw.values())
            w = {t: raw[t] / s for t in picks}
        else:  # 'risk' 在下单处单独处理,这里等权占位
            w = {t: 1.0 / len(picks) for t in picks}
        # 单票上限
        w = {t: min(v, max_w) for t, v in w.items()}
        return w

    # ---- 主循环 ----
    for mi in range(len(master)):
        mi_date = pd.Timestamp(master[mi])

        # 0) 年末税结算
        if mi_date.year != cur_year:
            paid = tax.settle_year()
            cash -= paid
            cur_year = mi_date.year

        # A) 既有持仓:用【昨日收盘设好的】移动/硬止损,检验今日 bar(gap 悲观),全清
        if M.get("enabled") and (M["stop_atr_mult"] > 0 or M["trail_mode"] != "none"):
            for t in list(positions.keys()):
                pos = positions[t]
                if mi <= pos.first_mi:
                    continue
                b = bar(t, mi_date)
                if b is None:
                    continue
                stop = -np.inf
                if M["stop_atr_mult"] > 0:
                    stop = max(stop, pos.avg_cost - M["stop_atr_mult"] * pos.atr_entry)
                if M["trail_mode"] == "chandelier":
                    stop = max(stop, pos.hhv_close - M["trail_atr_mult"] * pos.atr_entry)
                if stop > -np.inf:
                    if b["o"] <= stop:                       # 跳空击穿 → open 成交(悲观)
                        do_sell(t, mi, mi_date, None, "gap_stop", fill_price=b["o"])
                        continue
                    if b["l"] <= stop:                       # 盘中触止损
                        do_sell(t, mi, mi_date, None, "stop", fill_price=stop)
                        continue
                if M["trail_mode"] == "ma" and M["trail_ma_period"] > 0:
                    ma = sma_close(t, b["i"], M["trail_ma_period"])
                    if not np.isnan(ma) and b["c"] < ma:
                        # 破位:收盘信号 → 次日 open 出(无前视)。这里登记 pending 卖。
                        pending.setdefault(mi + 1, []).append(dict(act="sell", tkr=t, frac=1.0, reason="ma_break"))

        # B) 执行昨日登记的 pending 订单(今日 open)
        if mi in pending:
            for od in pending.pop(mi):
                if od["act"] == "sell":
                    pos = positions.get(od["tkr"])
                    if pos:
                        sh = None if od["frac"] >= 1.0 else int(pos.shares * od["frac"])
                        do_sell(od["tkr"], mi, mi_date, sh, od["reason"])
                elif od["act"] == "buy":
                    do_buy(od["tkr"], mi, mi_date, od["dollars"], od.get("atr"))
                elif od["act"] == "add":
                    do_buy(od["tkr"], mi, mi_date, od["dollars"])
                    pos = positions.get(od["tkr"])
                    if pos:
                        pos.n_adds += 1
                        pos.last_add_mi = mi

        # C) 更新移动止损锚(今日收盘新高,供明日用)
        for t, pos in positions.items():
            b = bar(t, mi_date)
            if b:
                pos.hhv_close = max(pos.hhv_close, b["c"])

        # D) 信号(今日收盘 <= t):金字塔加仓 / 减仓走弱 / 调仓
        eq = equity_now(mi_date)

        # D1) 动态仓位管理日信号(若启用)
        if M.get("enabled") and pm_callable is None:
            for t, pos in list(positions.items()):
                b = bar(t, mi_date)
                if b is None:
                    continue
                w_now = (b["c"] * pos.shares) / eq if eq > 0 else 1.0
                # 金字塔加仓赢家
                if M["pyramid"] and pos.n_adds < M["pyramid_max_adds"] \
                        and (mi - pos.last_add_mi) >= M["pyramid_min_gap_days"] and w_now < max_w:
                    trigger = False
                    if M["pyramid_breakout"] > 0:
                        hh = hhv_close(t, b["i"], M["pyramid_breakout"])
                        if not np.isnan(hh) and b["c"] >= hh:
                            trigger = True
                    if M["pyramid_step_gain"] > 0 and pos.avg_cost > 0:
                        if (b["c"] / pos.avg_cost - 1.0) >= (pos.n_adds + 1) * M["pyramid_step_gain"]:
                            trigger = True
                    if trigger:
                        base = eq / N
                        add_dollars = min(base * M["pyramid_add_frac"], max(0.0, max_w * eq - b["c"] * pos.shares))
                        if add_dollars > 0:
                            pending.setdefault(mi + 1, []).append(dict(act="add", tkr=t, dollars=add_dollars))
                # 减仓走弱(部分)
                if M["trim_ma_period"] > 0:
                    ma = sma_close(t, b["i"], M["trim_ma_period"])
                    if not np.isnan(ma) and b["c"] < ma:
                        pending.setdefault(mi + 1, []).append(
                            dict(act="sell", tkr=t, frac=M["trim_frac"], reason="trim_weak"))

        # D2) 调仓信号日
        if mi in rebal_set and mi + 1 < len(master):
            view = PITView(uni, spy, mi_date, min_hist)
            ranked = rank_fn(view, P)
            if audit and view.audit_max_date is not None and view.audit_max_date > mi_date:
                audit_violation = (str(mi_date.date()), str(view.audit_max_date.date()))
            # 自定义 position_manager 回调(高级):返回订单列表覆盖默认
            if pm_callable is not None:
                orders = pm_callable(view, P, positions, eq, ranked) or []
                for od in orders:
                    pending.setdefault(mi + 1, []).append(od)
            else:
                tw = target_weights(ranked, view)
                target_set = set(tw.keys())
                # 卖出:跌出目标的名 → 全清(轮动)
                for t in list(positions.keys()):
                    if t not in target_set:
                        pending.setdefault(mi + 1, []).append(dict(act="sell", tkr=t, frac=1.0, reason="rotate_out"))
                # 买入/调整:目标名
                for t, w in tw.items():
                    b = bar(t, mi_date)
                    if b is None:
                        continue
                    target_dollars = w * eq
                    if P["weight_mode"] == "risk" and M.get("stop_atr_mult", 0) > 0:
                        # 单笔风险预算:股数 = (eq*risk_pct)/(每股止损距离)
                        risk_per_share = M["stop_atr_mult"] * b["atr"]
                        if risk_per_share > 0:
                            risk_shares = (eq * P["risk_pct"]) / risk_per_share
                            target_dollars = min(w * eq if w else max_w * eq, risk_shares * b["c"])
                            target_dollars = min(target_dollars, max_w * eq)
                    cur_dollars = 0.0
                    if t in positions:
                        cur_dollars = b["c"] * positions[t].shares
                    drift = abs(target_dollars - cur_dollars) / max(1.0, eq)
                    if t not in positions:
                        pending.setdefault(mi + 1, []).append(
                            dict(act="buy", tkr=t, dollars=target_dollars, atr=b["atr"]))
                    elif drift > P["rebalance_threshold"]:
                        if target_dollars > cur_dollars:
                            pending.setdefault(mi + 1, []).append(
                                dict(act="buy", tkr=t, dollars=target_dollars - cur_dollars, atr=b["atr"]))
                        else:
                            frac = (cur_dollars - target_dollars) / cur_dollars if cur_dollars > 0 else 0
                            if frac > 0.02:
                                pending.setdefault(mi + 1, []).append(
                                    dict(act="sell", tkr=t, frac=frac, reason="rebal_trim"))

        # E) 盯市记权益
        equity_curve.append((str(mi_date.date()), equity_now(mi_date)))

    # 收尾:最后一日全清 + 末年税
    last_mi = len(master) - 1
    last_date = pd.Timestamp(master[last_mi])
    for t in list(positions.keys()):
        b = bar(t, last_date)
        if b:
            do_sell(t, last_mi, last_date, None, "final", fill_price=b["c"])
    cash -= tax.settle_year()
    final_eq = cash    # 全清后 = 现金
    equity_curve[-1] = (equity_curve[-1][0], final_eq)

    # 基准
    start_d = pd.Timestamp(equity_curve[0][0]); end_d = pd.Timestamp(equity_curve[-1][0])
    ew_curve = _equal_weight_benchmark(uni, master, start_d, end_d, cap0, slip)
    spy_curve = _spy_benchmark(spy, master, start_d, end_d, cap0, slip)
    dates_between = [pd.Timestamp(d) for d in master if start_d <= pd.Timestamp(d) <= end_d]

    metrics = _metrics([e for _, e in equity_curve], dates_between)
    metrics.update(_trade_metrics(trades))
    metrics["final_equity"] = round(final_eq, 2)
    metrics["total_return"] = round(final_eq / cap0 - 1, 4)
    metrics["n_trades"] = len(trades)
    metrics["total_commission"] = round(tot_comm, 2)
    metrics["total_slippage"] = round(tot_slip, 2)
    metrics["total_tax"] = round(tax.total_tax, 2)
    metrics["tax_ltcg_realized_gain"] = round(tax.cum_lt_gain, 2)
    metrics["tax_stcg_realized_gain"] = round(tax.cum_st_gain, 2)
    metrics["tax_lt_share_of_gain"] = round(
        tax.cum_lt_gain / (tax.cum_lt_gain + tax.cum_st_gain), 3) if (tax.cum_lt_gain + tax.cum_st_gain) > 0 else 0.0
    metrics["total_friction"] = round(tot_comm + tot_slip + tax.total_tax, 2)
    yrs = max(1e-9, (end_d - start_d).days / 365.25)
    metrics["turnover_per_yr"] = round(len(trades) / yrs, 1)

    return dict(
        equity=equity_curve, metrics=metrics, trades=trades,
        benchmark_ew=ew_curve, benchmark_spy=spy_curve,
        ew_metrics=_metrics([e for _, e in ew_curve], [pd.Timestamp(d) for d, _ in ew_curve]),
        spy_metrics=_metrics([e for _, e in spy_curve], [pd.Timestamp(d) for d, _ in spy_curve]),
        dropped_tickers=dropped, audit_violation=audit_violation, params=P, posmgmt=M,
    )


def _trade_metrics(trades):
    if not trades:
        return dict(win_rate=0, avg_win=0, avg_loss=0, payoff=0, profit_factor=0, avg_hold=0,
                    pct_long_term=0)
    nets = np.array([t["net"] for t in trades])
    wins = nets[nets > 0]; losses = nets[nets < 0]
    wr = len(wins) / len(nets)
    aw = wins.mean() if len(wins) else 0
    al = losses.mean() if len(losses) else 0
    payoff = abs(aw / al) if al != 0 else 0
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else float("inf")
    plt = np.mean([1.0 if t.get("long_term") else 0.0 for t in trades])
    return dict(
        win_rate=round(wr, 3), avg_win=round(aw, 2), avg_loss=round(al, 2),
        payoff=round(payoff, 2), profit_factor=round(pf, 2),
        avg_hold=round(np.mean([t["hold_days"] for t in trades]), 1),
        pct_long_term=round(plt, 3),
    )


# ----------------------------------------------------------------------------
# 自测
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    print("backtest_lib2 self-test ...")
    uni, spy, master = load_universe(os.path.join(DATA_DIR, "narrow98"), verbose=True)

    def rank_mom(view, params):
        return rank_fn_momentum_demo(view, params)

    # 测试1:低换手长持有月度动量轮动(LTCG 档),等权 6 槽
    res_long = backtest_portfolio(
        rank_mom, dict(n_slots=6, rebalance="Q", weight_mode="equal",
                       ltcg_rate=0.15, stcg_rate=0.25),
        uni=uni, spy=spy, master=master)
    mL = res_long["metrics"]
    print("\n[T1 长持有季度轮动 LTCG]:",
          {k: mL[k] for k in ["total_return", "CAGR", "maxDD", "Sharpe", "avg_hold",
                              "pct_long_term", "n_trades", "turnover_per_yr",
                              "total_tax", "tax_lt_share_of_gain", "total_friction"]})

    # 测试2:同策略短持有(周度,全 STCG)→ 对比省税
    res_short = backtest_portfolio(
        rank_mom, dict(n_slots=6, rebalance="W-MON", weight_mode="equal"),
        uni=uni, spy=spy, master=master)
    mS = res_short["metrics"]
    print("[T2 短持有周度轮动 STCG]:",
          {k: mS[k] for k in ["total_return", "CAGR", "maxDD", "avg_hold",
                              "pct_long_term", "n_trades", "total_tax", "total_friction"]})
    print(f"   >> LTCG 省税效果:长持有税 ${mL['total_tax']} vs 短持有税 ${mS['total_tax']}, "
          f"LT 占比 {mL['tax_lt_share_of_gain']} vs {mS['tax_lt_share_of_gain']}")

    # 测试3:金字塔加仓 + 移动止损(动态仓位管理生效验证)
    res_pyr = backtest_portfolio(
        rank_mom, dict(n_slots=5, rebalance="M", weight_mode="equal", max_weight=0.35),
        posmgmt=dict(enabled=True, stop_atr_mult=0.0, trail_mode="chandelier",
                     trail_atr_mult=3.0, pyramid=True, pyramid_breakout=50,
                     pyramid_max_adds=3, pyramid_add_frac=0.5),
        uni=uni, spy=spy, master=master)
    mP = res_pyr["metrics"]
    n_add = sum(1 for _ in [])  # 占位
    n_stop = sum(1 for t in res_pyr["trades"] if t["reason"] in ("stop", "gap_stop"))
    print("\n[T3 金字塔+移动止损]:",
          {k: mP[k] for k in ["total_return", "CAGR", "maxDD", "Sharpe", "n_trades",
                              "total_tax", "turnover_per_yr"]})
    print(f"   >> 止损出场 {n_stop} 笔(动态仓位管理生效)")

    # 测试4:集中 3 票 vs 分散 8 票
    res_c3 = backtest_portfolio(rank_mom, dict(n_slots=3, rebalance="Q"), uni=uni, spy=spy, master=master)
    res_c8 = backtest_portfolio(rank_mom, dict(n_slots=8, rebalance="Q"), uni=uni, spy=spy, master=master)
    print("\n[T4 集中度] 3票:", {k: res_c3["metrics"][k] for k in ["CAGR", "maxDD", "Sharpe"]},
          " 8票:", {k: res_c8["metrics"][k] for k in ["CAGR", "maxDD", "Sharpe"]})

    print("\n双基准:EW-BH", res_long["ew_metrics"], " SPY-BH", res_long["spy_metrics"])
    print("audit_violation (must be None):",
          res_long["audit_violation"], res_short["audit_violation"],
          res_pyr["audit_violation"], res_c3["audit_violation"])

    # 分档税正确性单元测试
    print("\n[单元] TaxBook 分档:")
    tb = TaxBook(0.15, 0.25)
    tb.realize(1000.0, True)    # LT 盈 1000 -> 150
    tb.realize(1000.0, False)   # ST 盈 1000 -> 250
    t1 = tb.settle_year()
    assert abs(t1 - 400.0) < 1e-6, t1
    tb2 = TaxBook(0.15, 0.25)
    tb2.realize(2000.0, True)   # LT 盈 2000
    tb2.realize(-500.0, False)  # ST 亏 500 抵 LT -> LT 净 1500 -> 225
    t2 = tb2.settle_year()
    assert abs(t2 - 225.0) < 1e-6, t2
    print(f"   LT1000+ST1000 税={t1}(应400 ✓)  LT2000+ST-500互抵 税={t2}(应225 ✓)")
    print("\nself-test done.")
