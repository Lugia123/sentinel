"""
round8/lib/backtest_lib.py
==========================
共享的【无前视(point-in-time)短线选股+交易】回测引擎。

设计目标(第八轮·回归短线本职):
  四个 squad(momentum / breakout / meanrev / invent)只需各自实现:
    1) rank_fn(view, params)        —— 选股排名规则(策略的一半)
    2) entry_exit_cfg (dict)        —— 进出场括号单规则(策略的另一半)
  引擎统一负责:无前视切片、t+1 open 入场、括号单逐日推进(含跳空击穿/同日止损
  优先/maxhold)、真实摩擦(佣金floor+滑点+短期税)、$4000 整股等权、基准对比、
  幸存者偏差敏感性。

铁律落地:
  ① POINT-IN-TIME:rank_fn 只能拿到 PITView,view.history(t) 末日 <= 调仓日 t。
     所有指标都是后向(SMA/ATR/RSI/rolling-high),在全历史上预计算后再按 t 截断,
     最后一行的指标只用到 <= t 的数据,故无前视。view 内置 audit 记录每次访问的末日。
  ② 交易=另一半:t+1 open 入场,ATR 括号单(止损/止盈/移动止损/MA破位/均值回归止盈),
     maxhold 上限。只做多。
  ③ 个股特有风险:(a)跳空击穿止损按 open 成交(悲观);(b)同日先触止损后触止盈
     按止损算(悲观);(c)入场日盘中亦检查止损。
  ④ 真实摩擦:老虎佣金 max(0.99, 0.0039*sh) + 平台 max(1.0, 0.004*sh);滑点 0.05%/边;
     短期资本利得税(默认25%)按年末结算。
  ⑤ 基准:同池等权(每日再平衡近似买入持有)+ SPY 买入持有,均扣同口径。

研究推演,非投资建议。
"""

import os
import glob
import math
import numpy as np
import pandas as pd

DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))

# ----------------------------------------------------------------------------
# 配置常量(可在调用处覆盖 params)
# ----------------------------------------------------------------------------
DEFAULT_PARAMS = dict(
    capital=4000.0,         # 起始本金 USD
    n_slots=6,              # 等权槽位 N (5-8)
    rebalance="W-MON",      # 调仓频率:每周一决策(信号), t+1 open 入场
    slippage=0.0005,        # 滑点 0.05%/边
    tax_rate=0.25,          # 短期资本利得税(普通税率主情景)
    min_history=252,        # 个股需 >=252 根才进入可选池(point-in-time 上市过滤)
    seed=0,
)

# 预计算的指标周期(全部后向,无前视)
_SMA_PERIODS = [5, 10, 20, 50, 100, 150, 200]
_HIGH_PERIODS = [20, 50, 55, 252]      # rolling 最高(收盘)
_HHV_PERIODS = [20, 50, 55, 252]       # rolling 最高(最高价) 用于通道突破
_LLV_PERIODS = [10, 20, 55]
_MOM_PERIODS = [21, 63, 126, 252]      # 动量回看(交易日)
_VOL_AVG = [20, 50]
_ATR_PERIOD = 14
_RSI_PERIODS = [2, 14]


# ----------------------------------------------------------------------------
# 指标(全部后向,绝不使用未来数据)
# ----------------------------------------------------------------------------
def _wilder_atr(df, period=14):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = np.full(len(tr), np.nan)
    if len(tr) >= period:
        atr[period - 1] = tr[:period].mean()
        for i in range(period, len(tr)):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def _wilder_rsi(close, period=14):
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    rsi = np.full(len(close), np.nan)
    if len(close) <= period:
        return rsi
    ag = gain[1:period + 1].mean()
    al = loss[1:period + 1].mean()
    rsi[period] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(period + 1, len(close)):
        ag = (ag * (period - 1) + gain[i]) / period
        al = (al * (period - 1) + loss[i]) / period
        rsi[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return rsi


def _add_indicators(df):
    """在全历史上预计算后向指标。截断到 <=t 时,最后一行仅含 <=t 信息 → 无前视。"""
    df = df.sort_values("date").reset_index(drop=True).copy()
    c = df["close"]
    for p in _SMA_PERIODS:
        df[f"sma{p}"] = c.rolling(p).mean()
        df[f"sma{p}_slope"] = df[f"sma{p}"] - df[f"sma{p}"].shift(10)  # 上行判断
    for p in _HIGH_PERIODS:
        df[f"chigh{p}"] = c.rolling(p).max()       # 收盘 N 日高
    for p in _HHV_PERIODS:
        df[f"hhv{p}"] = df["high"].rolling(p).max()  # 最高价 N 日高(突破用,不含当根的未来)
    for p in _LLV_PERIODS:
        df[f"llv{p}"] = df["low"].rolling(p).min()
    for p in _MOM_PERIODS:
        df[f"mom{p}"] = c / c.shift(p) - 1.0
    for p in _VOL_AVG:
        df[f"vavg{p}"] = df["volume"].rolling(p).mean()
    df["atr14"] = _wilder_atr(df, _ATR_PERIOD)
    for p in _RSI_PERIODS:
        df[f"rsi{p}"] = _wilder_rsi(c.values, p)
    # 52周高/距高百分比(Minervini 趋势模板用)
    df["hi252"] = c.rolling(252).max()
    df["lo252"] = c.rolling(252).min()
    df["pct_from_high"] = c / df["hi252"] - 1.0      # <=0
    df["pct_above_low"] = c / df["lo252"] - 1.0      # >=0
    # 连续下跌天数(meanrev 用)
    down = (c.diff() < 0).astype(int).values
    streak = np.zeros(len(down), dtype=int)
    for i in range(1, len(down)):
        streak[i] = streak[i - 1] + 1 if down[i] else 0
    df["down_streak"] = streak
    return df


# ----------------------------------------------------------------------------
# 数据加载
# ----------------------------------------------------------------------------
def load_universe(data_dir, spy_path=None, exclude=None, verbose=False):
    """
    读 data_dir/*.csv → {ticker: DataFrame(已加指标, date 为 Timestamp)}。
    返回 (universe_dict, spy_df, master_dates)。
    master_dates = 全池+SPY 交易日并集(升序 Timestamp)。
    """
    exclude = set(exclude or [])
    if spy_path is None:
        spy_path = os.path.join(DATA_DIR, "SPY.csv")
    uni = {}
    all_dates = set()
    for path in sorted(glob.glob(os.path.join(data_dir, "*.csv"))):
        tkr = os.path.splitext(os.path.basename(path))[0]
        if tkr in exclude:
            continue
        df = pd.read_csv(path)
        df["date"] = pd.to_datetime(df["date"])
        df = _add_indicators(df)
        uni[tkr] = df
        all_dates.update(df["date"].tolist())
    spy = pd.read_csv(spy_path)
    spy["date"] = pd.to_datetime(spy["date"])
    spy = spy.sort_values("date").reset_index(drop=True)
    spy["sma200"] = spy["close"].rolling(200).mean()
    spy["sma200_slope"] = spy["sma200"] - spy["sma200"].shift(10)
    all_dates.update(spy["date"].tolist())
    master = sorted(all_dates)
    if verbose:
        print(f"[load_universe] {len(uni)} tickers, master {master[0].date()}..{master[-1].date()} ({len(master)} days)")
    return uni, spy, master


# ----------------------------------------------------------------------------
# Point-in-time 视图:rank_fn 只能看到 <= as_of 的数据
# ----------------------------------------------------------------------------
class PITView:
    """
    无前视视图。rank_fn 通过它访问数据,任何 history()/spy_history() 都被截断到 <= as_of,
    并把访问到的"末日"记入 audit_max_date(供 testRules 校验 末日 <= t)。
    """
    __slots__ = ("_uni", "_spy", "as_of", "min_history", "_idx_cache",
                 "audit_max_date", "audit_calls")

    def __init__(self, uni, spy, as_of, min_history):
        self._uni = uni
        self._spy = spy
        self.as_of = as_of
        self.min_history = min_history
        self._idx_cache = {}
        self.audit_max_date = None      # 所有访问中见到的最大末日(必须 <= as_of)
        self.audit_calls = 0

    def _cut(self, df):
        # 返回 <= as_of 的整数终点 idx(含),无则 -1
        dates = df["date"].values
        idx = np.searchsorted(dates, np.datetime64(self.as_of), side="right") - 1
        return idx

    def asof_idx(self, tkr):
        if tkr in self._idx_cache:
            return self._idx_cache[tkr]
        idx = self._cut(self._uni[tkr])
        self._idx_cache[tkr] = idx
        return idx

    def available_tickers(self):
        """point-in-time 可选池:截至 as_of 已有 >= min_history 根的个股。"""
        out = []
        for tkr, df in self._uni.items():
            idx = self.asof_idx(tkr)
            if idx + 1 >= self.min_history:
                out.append(tkr)
        return out

    def history(self, tkr, n=None):
        """<= as_of 的切片(无前视)。n 指定只取最后 n 根。"""
        idx = self.asof_idx(tkr)
        if idx < 0:
            return None
        df = self._uni[tkr]
        start = 0 if n is None else max(0, idx + 1 - n)
        sl = df.iloc[start:idx + 1]
        self._audit(sl["date"].iloc[-1])
        return sl

    def last(self, tkr, field):
        """截至 as_of 的最新字段值(标量),无则 None。"""
        idx = self.asof_idx(tkr)
        if idx < 0:
            return None
        df = self._uni[tkr]
        self._audit(df["date"].iloc[idx])
        return df[field].iloc[idx]

    def last_row(self, tkr):
        idx = self.asof_idx(tkr)
        if idx < 0:
            return None
        row = self._uni[tkr].iloc[idx]
        self._audit(row["date"])
        return row

    def spy_history(self, n=None):
        idx = np.searchsorted(self._spy["date"].values,
                              np.datetime64(self.as_of), side="right") - 1
        if idx < 0:
            return None
        start = 0 if n is None else max(0, idx + 1 - n)
        sl = self._spy.iloc[start:idx + 1]
        self._audit(sl["date"].iloc[-1])
        return sl

    def spy_last(self, field):
        sl = self.spy_history(n=1)
        return None if sl is None else sl[field].iloc[-1]

    def _audit(self, d):
        self.audit_calls += 1
        d = pd.Timestamp(d)
        if self.audit_max_date is None or d > self.audit_max_date:
            self.audit_max_date = d


# ----------------------------------------------------------------------------
# 摩擦
# ----------------------------------------------------------------------------
def commission(shares):
    """老虎佣金 max(0.99, 0.0039*sh) + 平台费 max(1.0, 0.004*sh)。"""
    if shares <= 0:
        return 0.0
    tiger = max(0.99, 0.0039 * shares)
    platform = max(1.0, 0.004 * shares)
    return tiger + platform


# ----------------------------------------------------------------------------
# 括号单 / 进出场默认引擎(cfg 驱动)
# ----------------------------------------------------------------------------
DEFAULT_ENTRY_EXIT = dict(
    atr_period=14,
    stop_atr_mult=2.0,        # 硬止损 = entry - k*ATR_entry
    target_mode="atr",        # 'atr' | 'rr' | 'none'
    target_atr_mult=4.0,      # target = entry + m*ATR_entry
    rr_mult=2.0,              # target_mode='rr' 时 target = entry + rr*risk
    trail_mode="none",        # 'none' | 'chandelier' | 'ma'
    trail_atr_mult=3.0,       # chandelier: stop = max(stop, HHV_close_since_entry - k*ATR_entry)
    trail_ma_period=20,       # 'ma': 收盘 < SMA(period) 则止损出(趋势破位)
    rev_exit_ma=None,         # 均值回归止盈: 收盘 > SMA(period) 则出
    rev_exit_rsi=None,        # 均值回归止盈: RSI2 > 阈值 则出
    maxhold=10,               # 持有上限(交易日),到期收盘出
)


def _sma_field(period):
    return f"sma{period}" if period in _SMA_PERIODS else None


class Position:
    __slots__ = ("tkr", "fill_idx", "entry_price", "shares", "atr_entry",
                 "stop", "target", "hhv_close", "days_held", "cfg")

    def __init__(self, tkr, fill_idx, entry_price, shares, atr_entry, cfg):
        self.tkr = tkr
        self.fill_idx = fill_idx
        self.entry_price = entry_price
        self.shares = shares
        self.atr_entry = atr_entry
        self.cfg = cfg
        risk = cfg["stop_atr_mult"] * atr_entry
        self.stop = entry_price - risk
        if cfg["target_mode"] == "atr":
            self.target = entry_price + cfg["target_atr_mult"] * atr_entry
        elif cfg["target_mode"] == "rr":
            self.target = entry_price + cfg["rr_mult"] * risk
        else:
            self.target = None
        self.hhv_close = entry_price
        self.days_held = 0


def _evaluate_exit(pos, bar, is_entry_day):
    """
    给定某交易日的 bar(含 OHLC + 指标),返回 (exit_price, reason) 或 None。
    悲观规则:跳空击穿按 open 成交;同日先触止损后触止盈按止损;入场日盘中亦查止损。
    顺序:① 跳空/盘中止损(最先)② 跳空/盘中止盈 ③ 收盘类出场(MA破位/均值回归/maxhold)。
    """
    cfg = pos.cfg
    o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]

    # --- 移动止损先更新(用入场前不变的 ATR_entry,基于收盘新高) ---
    if cfg["trail_mode"] == "chandelier":
        pos.hhv_close = max(pos.hhv_close, c)
        trail = pos.hhv_close - cfg["trail_atr_mult"] * pos.atr_entry
        pos.stop = max(pos.stop, trail)

    # --- ① 止损(含跳空击穿) ---
    if not is_entry_day:
        if o <= pos.stop:                         # 跳空击穿:按 open 成交(悲观)
            return o, "gap_stop"
    if l <= pos.stop:                             # 盘中触止损(入场日也查)
        # 同日止盈优先级:止损优先(悲观),直接按 stop
        return pos.stop, "stop"

    # --- ② 止盈(含跳空) ---
    if pos.target is not None:
        if not is_entry_day and o >= pos.target:  # 跳空越过目标:按 open 成交
            return o, "gap_target"
        if h >= pos.target:
            return pos.target, "target"

    # --- ③ 收盘类出场 ---
    # 趋势破位(momentum/breakout): 收盘 < SMA(trail_ma_period)
    if cfg["trail_mode"] == "ma":
        f = _sma_field(cfg["trail_ma_period"])
        ma = bar[f] if f and f in bar and not pd.isna(bar[f]) else None
        if ma is not None and c < ma:
            return c, "ma_break"
    # 均值回归止盈: 收盘 > SMA(rev_exit_ma)
    if cfg["rev_exit_ma"]:
        f = _sma_field(cfg["rev_exit_ma"])
        ma = bar[f] if f and f in bar and not pd.isna(bar[f]) else None
        if ma is not None and c > ma:
            return c, "rev_ma"
    # 均值回归止盈: RSI2 > 阈值
    if cfg["rev_exit_rsi"]:
        r = bar["rsi2"] if "rsi2" in bar and not pd.isna(bar["rsi2"]) else None
        if r is not None and r > cfg["rev_exit_rsi"]:
            return c, "rev_rsi"
    # maxhold
    if pos.days_held >= cfg["maxhold"]:
        return c, "maxhold"
    return None


# ----------------------------------------------------------------------------
# 主回测
# ----------------------------------------------------------------------------
def backtest(rank_fn, entry_exit_cfg=None, params=None, uni=None, spy=None,
             master=None, data_dir=None, exclude=None, drop_top_n_expost=0,
             audit=True):
    """
    rank_fn(view, params) -> 已过滤+排名的 ticker 列表(best first)。
    entry_exit_cfg: 见 DEFAULT_ENTRY_EXIT。
    返回 dict: equity 曲线 + 指标 + 同池等权基准 + SPY 基准 + 交易明细 + audit。

    无前视保证:每个调仓日 t 用 PITView(末日 <= t),t+1 open 入场。
    幸存者敏感性:drop_top_n_expost>0 时,先按【全期买入持有收益】剔除最强 N 票再回测。
    """
    P = dict(DEFAULT_PARAMS)
    P.update(params or {})
    cfg = dict(DEFAULT_ENTRY_EXIT)
    cfg.update(entry_exit_cfg or {})

    if uni is None:
        uni, spy, master = load_universe(data_dir, exclude=exclude)
    uni = dict(uni)  # 浅拷贝,便于剔票

    # --- 幸存者偏差敏感性:剔除全期最强 N 票(事后) ---
    dropped = []
    if drop_top_n_expost > 0:
        perf = {t: (df["close"].iloc[-1] / df["close"].iloc[0] - 1.0)
                for t, df in uni.items()}
        dropped = [t for t, _ in sorted(perf.items(), key=lambda kv: -kv[1])][:drop_top_n_expost]
        for t in dropped:
            uni.pop(t, None)

    N = P["n_slots"]
    cap0 = P["capital"]
    slip = P["slippage"]
    min_hist = P["min_history"]

    # 调仓日(信号日);t+1 open 入场
    cal = pd.DatetimeIndex(master)
    rebal_days = pd.date_range(cal[0], cal[-1], freq=P["rebalance"])
    rebal_days = [d for d in rebal_days if d >= cal[0]]
    # 把每个调仓信号日映射到 master 上"<=该日"的实际交易日 index
    master_arr = cal.values

    def master_idx_le(ts):
        return int(np.searchsorted(master_arr, np.datetime64(ts), side="right") - 1)

    # 每只 ticker: date->master_idx 不必要;改为按 master 日逐日推进,需快速取某 ticker 在某日的 bar。
    # 构建 ticker 的 date->row_idx 映射(基于该 ticker 自身的 df 行)。
    tkr_date_idx = {}
    for t, df in uni.items():
        d = {pd.Timestamp(x): i for i, x in enumerate(df["date"].values)}
        tkr_date_idx[t] = d

    # 待入场队列:在调仓信号日 t 选出的票,下一交易日 open 入场
    pending = {}  # fill_master_idx -> list[ticker]
    # 把每个调仓信号日 → fill 日(master 上的下一根)
    rebal_signal_master_idx = []
    for rd in rebal_days:
        si = master_idx_le(rd)
        if si < 0 or si + 1 >= len(master):
            continue
        rebal_signal_master_idx.append(si)
    rebal_signal_set = set(rebal_signal_master_idx)

    # 状态
    cash = cap0
    positions = []          # list[Position]
    held = set()            # 当前持仓 ticker
    trades = []             # 平仓记录
    equity_curve = []       # (date, equity)
    tot_comm = 0.0
    tot_slip = 0.0
    tot_tax = 0.0
    year_realized = 0.0     # 当年已实现净盈亏(扣佣金)
    cur_year = pd.Timestamp(master[0]).year
    audit_violation = None

    def get_bar(tkr, mdate):
        di = tkr_date_idx[tkr].get(pd.Timestamp(mdate))
        if di is None:
            return None
        return uni[tkr].iloc[di], di

    def close_position(pos, exit_price, mdate, reason):
        nonlocal cash, tot_comm, tot_slip, year_realized
        fill = exit_price * (1 - slip)            # 卖出滑点
        slip_cost = exit_price * slip * pos.shares
        comm = commission(pos.shares)
        proceeds = fill * pos.shares - comm
        cost_basis = pos.entry_price * pos.shares  # entry_price 已含买入滑点
        gross = (fill - pos.entry_price) * pos.shares
        net = gross - comm                         # 卖出端佣金(买入端已在入场扣)
        cash += proceeds
        tot_comm += comm
        tot_slip += slip_cost
        year_realized += net
        held.discard(pos.tkr)
        trades.append(dict(
            tkr=pos.tkr, entry_date=str(pd.Timestamp(master[pos.fill_idx]).date()),
            exit_date=str(pd.Timestamp(mdate).date()), shares=pos.shares,
            entry=round(pos.entry_price, 4), exit=round(fill, 4),
            hold_days=pos.days_held, reason=reason,
            net=round(net, 2), ret=round(fill / pos.entry_price - 1, 4),
        ))

    # 主循环:逐 master 交易日推进
    for mi, mdate in enumerate(master):
        mdate = pd.Timestamp(mdate)
        # --- 年末税结算 ---
        if mdate.year != cur_year:
            tax = P["tax_rate"] * max(0.0, year_realized)
            cash -= tax
            tot_tax += tax
            year_realized = 0.0
            cur_year = mdate.year

        # --- 1) 先处理持仓的当日出场(逐日推进括号单) ---
        still = []
        for pos in positions:
            if mi <= pos.fill_idx:
                still.append(pos)
                continue
            got = get_bar(pos.tkr, mdate)
            if got is None:
                still.append(pos)
                continue
            bar, _ = got
            pos.days_held += 1
            res = _evaluate_exit(pos, bar, is_entry_day=False)
            if res is not None:
                close_position(pos, res[0], mdate, res[1])
            else:
                still.append(pos)
        positions = still

        # --- 2) 处理今天 open 入场(来自上一信号日的 pending) ---
        if mi in pending:
            want = pending.pop(mi)
            for tkr in want:
                if len(positions) >= N or tkr in held:
                    continue
                got = get_bar(tkr, mdate)
                if got is None:
                    continue
                bar, di = got
                # ATR 取【信号日(<=t)】的值,而非入场日(t+1)。入场发生在 t+1 开盘,
                # 此刻入场日自身的 high/low/close 尚未知 → 不能用 bar["atr14"](含当日范围,
                # 属前视)。改用上一根已完成 bar(di-1,末日<=t)的 atr14。
                if di <= 0:
                    continue
                atr = uni[tkr].iloc[di - 1]["atr14"]
                if pd.isna(atr) or atr <= 0:
                    continue
                fill = bar["open"] * (1 + slip)   # 买入滑点
                slot_budget = (cash + _mtm(positions, mdate, get_bar)) / N
                slot_budget = min(slot_budget, cash)
                shares = int(slot_budget // fill)
                if shares <= 0:
                    continue
                comm = commission(shares)
                cost = fill * shares + comm
                if cost > cash:
                    shares = int((cash - comm) // fill)
                    if shares <= 0:
                        continue
                    cost = fill * shares + commission(shares)
                    comm = commission(shares)
                cash -= cost
                tot_comm += comm
                tot_slip += bar["open"] * slip * shares
                pos = Position(tkr, mi, fill, shares, atr, cfg)
                # 入场日盘中即查止损(悲观)
                res = _evaluate_exit(pos, bar, is_entry_day=True)
                if res is not None:
                    close_position(pos, res[0], mdate, res[1])
                else:
                    positions.append(pos)
                    held.add(tkr)

        # --- 3) 调仓信号日:无前视排名,选票排队到下一交易日 open ---
        if mi in rebal_signal_set and len(positions) < N:
            view = PITView(uni, spy, mdate, min_hist)
            ranked = rank_fn(view, P)
            if audit and view.audit_max_date is not None and view.audit_max_date > mdate:
                audit_violation = (str(mdate.date()), str(view.audit_max_date.date()))
            slots_free = N - len(positions) - sum(len(v) for v in pending.values())
            picks = []
            for tkr in ranked:
                if tkr in held or tkr in picks:
                    continue
                picks.append(tkr)
                if len(picks) >= slots_free:
                    break
            if picks and mi + 1 < len(master):
                pending.setdefault(mi + 1, []).extend(picks)

        # --- 4) 记权益曲线(逐日盯市) ---
        eq = cash + _mtm(positions, mdate, get_bar)
        equity_curve.append((str(mdate.date()), eq))

    # 收尾:最后一日强平 + 末年税
    last_date = pd.Timestamp(master[-1])
    for pos in positions:
        got = get_bar(pos.tkr, last_date)
        if got:
            close_position(pos, got[0]["close"], last_date, "final")
    tax = P["tax_rate"] * max(0.0, year_realized)
    cash -= tax
    tot_tax += tax
    final_eq = equity_curve[-1][1]

    # --- 基准:同池等权(每日再平衡近似) + SPY 买入持有 ---
    start_d = pd.Timestamp(equity_curve[0][0])
    end_d = pd.Timestamp(equity_curve[-1][0])
    ew_curve = _equal_weight_benchmark(uni, master, start_d, end_d, cap0, slip)
    spy_curve = _spy_benchmark(spy, master, start_d, end_d, cap0, slip)

    metrics = _metrics([e for _, e in equity_curve], master_dates_between(master, start_d, end_d))
    metrics.update(_trade_metrics(trades))
    metrics["final_equity"] = round(final_eq, 2)
    metrics["total_return"] = round(final_eq / cap0 - 1, 4)
    metrics["n_trades"] = len(trades)
    metrics["total_commission"] = round(tot_comm, 2)
    metrics["total_slippage"] = round(tot_slip, 2)
    metrics["total_tax"] = round(tot_tax, 2)
    metrics["total_friction"] = round(tot_comm + tot_slip + tot_tax, 2)
    yrs = max(1e-9, (end_d - start_d).days / 365.25)
    metrics["turnover_per_yr"] = round(len(trades) / yrs, 1)

    return dict(
        equity=equity_curve, metrics=metrics, trades=trades,
        benchmark_ew=ew_curve, benchmark_spy=spy_curve,
        ew_metrics=_metrics([e for _, e in ew_curve], [pd.Timestamp(d) for d, _ in ew_curve]),
        spy_metrics=_metrics([e for _, e in spy_curve], [pd.Timestamp(d) for d, _ in spy_curve]),
        dropped_tickers=dropped, audit_violation=audit_violation, params=P, cfg=cfg,
    )


def _mtm(positions, mdate, get_bar):
    v = 0.0
    for pos in positions:
        got = get_bar(pos.tkr, mdate)
        px = got[0]["close"] if got else pos.entry_price
        v += px * pos.shares
    return v


def master_dates_between(master, start_d, end_d):
    return [pd.Timestamp(d) for d in master if start_d <= pd.Timestamp(d) <= end_d]


# ----------------------------------------------------------------------------
# 基准
# ----------------------------------------------------------------------------
def _equal_weight_benchmark(uni, master, start_d, end_d, cap0, slip):
    """同池等权指数(每日再平衡 ≈ 等权买入持有);只用当日已上市个股的当日收益。"""
    dates = [pd.Timestamp(d) for d in master if start_d <= pd.Timestamp(d) <= end_d]
    # 预取每 ticker 的 date->close
    closes = {}
    for t, df in uni.items():
        closes[t] = {pd.Timestamp(x): c for x, c in zip(df["date"].values, df["close"].values)}
    eq = cap0
    curve = [(str(dates[0].date()), eq)]
    for i in range(1, len(dates)):
        d0, d1 = dates[i - 1], dates[i]
        rets = []
        for t in uni:
            c0 = closes[t].get(d0)
            c1 = closes[t].get(d1)
            if c0 and c1 and c0 > 0:
                rets.append(c1 / c0 - 1)
        r = np.mean(rets) if rets else 0.0
        eq *= (1 + r)
        curve.append((str(d1.date()), eq))
    return curve


def _spy_benchmark(spy, master, start_d, end_d, cap0, slip):
    s = spy[(spy["date"] >= start_d) & (spy["date"] <= end_d)].reset_index(drop=True)
    if len(s) == 0:
        return [(str(start_d.date()), cap0)]
    p0 = s["close"].iloc[0] * (1 + slip)
    curve = [(str(pd.Timestamp(d).date()), cap0 * (c / p0))
             for d, c in zip(s["date"].values, s["close"].values)]
    return curve


# ----------------------------------------------------------------------------
# 指标
# ----------------------------------------------------------------------------
def _metrics(equity, dates):
    eq = np.asarray(equity, dtype=float)
    if len(eq) < 3:
        return dict(CAGR=0, maxDD=0, Sharpe=0, Sortino=0, Calmar=0, vol=0)
    rets = eq[1:] / eq[:-1] - 1
    yrs = max(1e-9, (dates[-1] - dates[0]).days / 365.25)
    cagr = (eq[-1] / eq[0]) ** (1 / yrs) - 1
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1
    maxdd = dd.min()
    vol = rets.std() * math.sqrt(252)
    sharpe = (rets.mean() * 252) / (rets.std() * math.sqrt(252)) if rets.std() > 0 else 0
    downside = rets[rets < 0]
    dvol = downside.std() * math.sqrt(252) if len(downside) > 1 else 0
    sortino = (rets.mean() * 252) / dvol if dvol > 0 else 0
    calmar = cagr / abs(maxdd) if maxdd < 0 else 0
    return dict(
        CAGR=round(cagr, 4), maxDD=round(maxdd, 4), Sharpe=round(sharpe, 2),
        Sortino=round(sortino, 2), Calmar=round(calmar, 2), vol=round(vol, 4),
    )


def _trade_metrics(trades):
    if not trades:
        return dict(win_rate=0, avg_win=0, avg_loss=0, payoff=0, profit_factor=0, avg_hold=0)
    nets = np.array([t["net"] for t in trades])
    wins = nets[nets > 0]
    losses = nets[nets < 0]
    wr = len(wins) / len(nets)
    aw = wins.mean() if len(wins) else 0
    al = losses.mean() if len(losses) else 0
    payoff = abs(aw / al) if al != 0 else 0
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else float("inf")
    return dict(
        win_rate=round(wr, 3), avg_win=round(aw, 2), avg_loss=round(al, 2),
        payoff=round(payoff, 2), profit_factor=round(pf, 2),
        avg_hold=round(np.mean([t["hold_days"] for t in trades]), 1),
    )


# ----------------------------------------------------------------------------
# 一个简单动量 rank_fn(供自测 + momentum squad 起点)
# ----------------------------------------------------------------------------
def rank_fn_momentum_demo(view, params):
    """126日相对SPY强弱 + 趋势过滤(>200日线 & >50日线 & 200日线上行)。无前视。"""
    spy_hist = view.spy_history(n=200)
    if spy_hist is None or len(spy_hist) < 130:
        return []
    spy_mom = spy_hist["close"].iloc[-1] / spy_hist["close"].iloc[-127] - 1
    scored = []
    for tkr in view.available_tickers():
        row = view.last_row(tkr)
        if row is None:
            continue
        c = row["close"]
        if pd.isna(row["sma200"]) or pd.isna(row["sma50"]) or pd.isna(row["mom126"]):
            continue
        if c <= row["sma200"] or c <= row["sma50"]:
            continue
        if pd.isna(row["sma200_slope"]) or row["sma200_slope"] <= 0:
            continue
        rs = row["mom126"] - spy_mom        # 相对 SPY 强弱
        scored.append((tkr, rs))
    scored.sort(key=lambda kv: -kv[1])
    return [t for t, _ in scored]


if __name__ == "__main__":
    print("backtest_lib self-test ...")
    uni, spy, master = load_universe(os.path.join(DATA_DIR, "narrow98"), verbose=True)
    cfg = dict(stop_atr_mult=2.5, target_mode="none", trail_mode="ma",
               trail_ma_period=20, maxhold=40)
    res = backtest(rank_fn_momentum_demo, cfg, dict(n_slots=6), uni=uni, spy=spy, master=master)
    m = res["metrics"]
    print("STRATEGY:", {k: m[k] for k in ["total_return", "CAGR", "maxDD", "Sharpe",
          "Sortino", "Calmar", "win_rate", "payoff", "n_trades", "turnover_per_yr",
          "total_friction", "total_commission", "total_tax"]})
    print("EW  buy&hold:", res["ew_metrics"])
    print("SPY buy&hold:", res["spy_metrics"])
    print("audit_violation (must be None):", res["audit_violation"])
