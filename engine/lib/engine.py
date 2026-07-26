#!/usr/bin/env python3
"""A股 回测引擎(R0 地基)。survivorship-free + T+1 + 涨跌停不可成交 + 印花税/佣金/滑点 +
停牌 + 【无个人资本利得税】(与美股引擎最大区别)。信号只用 t 及之前,买卖在 t+1 开盘执行。

canonical 口径,跨轮不变。R1+ 只需提供 rank 信号矩阵(date×code,越大越优),引擎负责执行+摩擦。
"""
import os, glob
import numpy as np
import pandas as pd

DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
DAILY = os.path.join(DATA_DIR, "daily")

# ---- 摩擦(A股)----
STAMP = 0.0005      # 印花税(卖单,单边 0.05%)
COMM = 0.00025      # 佣金(双边,每边 0.025%)
SLIP = 0.001        # 滑点(每边 0.1%)
# 无个人资本利得税

TRADING_DAYS = 242


def board_limit_pct(code, is_st):
    """涨跌停幅度:主板±10 / 创业科创±20 / 北交±30 / 主板ST±5。code 形如 sh.600000 / sz.300xxx。"""
    c = code.split(".")[-1]
    if c[:3] in ("688",) or c[:2] in ("30",):   # 科创/创业(注册制±20)
        return 0.20
    if c[:1] in ("8", "4") or c[:3] == "920":    # 北交所
        return 0.30
    # 主板:ST ±5,否则 ±10
    return 0.05 if is_st else 0.10


def load_matrices(codes=None, start="2007-01-01", end=None, min_days=250):
    """读 daily CSV → 对齐成 date×code 矩阵。返回 dict:close/open/pclose/pct/status/st/
    can_buy(次日可买:非一字涨停开盘且不停牌)/can_sell/in_market(在市)。后复权价。
    survivorship-free:退市股到其最后交易日为止有值,之后 NaN(自动退出组合)。"""
    files = ([os.path.join(DAILY, c.replace(".", "_") + ".csv") for c in codes]
             if codes else sorted(glob.glob(os.path.join(DAILY, "*.csv"))))
    files = [f for f in files if os.path.exists(f)]
    close, open_, pcl, pct, stat, stf, amt, trn = {}, {}, {}, {}, {}, {}, {}, {}
    high, low = {}, {}
    for f in files:
        code = os.path.basename(f)[:-4].replace("_", ".", 1)
        df = pd.read_csv(f)
        if len(df) < min_days:
            continue
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"] >= pd.Timestamp(start)]
        if end:
            df = df[df["date"] <= pd.Timestamp(end)]
        if len(df) < min_days:
            continue
        df = df.set_index("date")
        close[code] = df["close"].astype(float)
        open_[code] = df["open"].astype(float)
        high[code] = df["high"].astype(float)
        low[code] = df["low"].astype(float)
        pcl[code] = df["preclose"].astype(float)
        pct[code] = df["pctChg"].astype(float)
        stat[code] = df["tradestatus"].astype(float)   # 1 正常 / 0 停牌
        stf[code] = df["isST"].astype(float)
        amt[code] = pd.to_numeric(df.get("amount"), errors="coerce")   # 成交额(元)
        trn[code] = pd.to_numeric(df.get("turn"), errors="coerce")     # 换手率(%)
    C = pd.DataFrame(close).sort_index()
    O = pd.DataFrame(open_).reindex(C.index)
    P = pd.DataFrame(pcl).reindex(C.index)
    PCT = pd.DataFrame(pct).reindex(C.index)
    ST = pd.DataFrame(stat).reindex(C.index)
    SF = pd.DataFrame(stf).reindex(C.index)
    AMT = pd.DataFrame(amt).reindex(C.index)
    TRN = pd.DataFrame(trn).reindex(C.index)
    # 流通市值代理:turn% = 100×volume/float_shares,amount = volume×vwap
    # → float_mktcap ≈ 100×amount/turn(单调于真实流通市值,用于规模分层/中性化)。turn=0 停牌→NaN
    FMC = (AMT * 100.0 / TRN.replace(0.0, np.nan))
    in_market = C.notna()
    halted = (ST == 0)
    # 次日开盘相对前收的涨幅;一字涨停开盘=不可买(open 已在涨停价);跌停开盘=不可卖
    open_ret = O / P - 1.0
    lim = pd.DataFrame(index=C.index, columns=C.columns, dtype=float)
    for code in C.columns:
        is_st_series = SF[code].fillna(0) > 0
        base = 0.10
        c = code.split(".")[-1]
        if c[:3] == "688" or c[:2] == "30":
            base = 0.20
        elif c[:1] in ("8", "4"):
            base = 0.30
        lim[code] = np.where(is_st_series, 0.05, base)
    buf = 0.005  # 缓冲:开盘涨幅 ≥ 上限-0.5% 视为涨停不可买
    can_buy = in_market & (~halted) & (open_ret < (lim - buf))
    can_sell = in_market & (~halted) & (open_ret > (-(lim - buf)))
    HI = pd.DataFrame(high).reindex(C.index).reindex(columns=C.columns)
    LO = pd.DataFrame(low).reindex(C.index).reindex(columns=C.columns)
    return dict(close=C, open=O, high=HI, low=LO, pclose=P, pct=PCT, status=ST, st=SF,
                amount=AMT, turn=TRN, fmc=FMC,
                in_market=in_market, can_buy=can_buy, can_sell=can_sell)


def backtest(signal, M, n_hold=30, rebalance="M", capital=1_000_000, weight="equal"):
    """月度(或指定)再平衡回测。signal:date×code,越大越优(只用当日及之前信息,引擎在 t 选、t+1 开盘执行)。
    weight: 'equal' 等权 / 'invvol' 逆波动 / DataFrame(date×code 每股权重矩阵,用于「每股动作」覆盖层——
        引擎先按 signal 选 top-n_hold,再在 target 内取该矩阵当日值(负/NaN→0,即清仓;组内归一);
        全 0 兜底等权。矩阵只用当日及之前信息,须对齐 M['close'].index。)。
    无资本利得税;卖印花税+双边佣金+滑点。返回 equity(Series)+ 明细。"""
    C, O = M["close"], M["open"]
    can_buy, can_sell = M["can_buy"], M["can_sell"]
    dates = C.index
    # 再平衡日:每月最后交易日
    if rebalance == "M":
        rb = pd.Series(dates).groupby([dates.year, dates.month]).last().values
    else:
        rb = dates[::int(rebalance)]
    rb = pd.DatetimeIndex(rb)

    cash = float(capital)
    pos = {}                     # code -> shares
    equity = []
    turnover_sum = 0.0

    # ---- 预计算 numpy(消 per-day Series 重建,提速 ~10x)----
    cols = list(C.columns)
    cidx = {c: j for j, c in enumerate(cols)}
    Cv = C.values                          # 原始收盘(NaN=无数据)
    Cf = C.ffill().values                  # 前向填充(停牌/退市后按最近有效价估值)
    Ov = O.values
    CBv = can_buy.values                   # bool
    CSv = can_sell.values
    INMv = M["in_market"].values           # bool
    notna = ~np.isnan(Cv)
    last_idx = np.full(len(cols), -1, dtype=int)   # 每股最后有效交易日的整数索引(退市判定)
    for j in range(len(cols)):
        nz = np.nonzero(notna[:, j])[0]
        if len(nz): last_idx[j] = nz[-1]
    rb_set = set(rb)

    # 逆波动权重用 63 日收益波动(numpy)
    vol63 = C.pct_change(fill_method=None).rolling(63).std().values
    # 每股动作权重矩阵(可选):对齐到回测日历并前填(仅用当日及之前信息)
    wdf = None
    if isinstance(weight, pd.DataFrame):
        wdf = weight.reindex(index=dates).ffill()

    for i, day in enumerate(dates):
        row = Cf[i]
        # 退市强制清算:持仓超过其最后有效交易日 → 按最后有效价清算(survivorship-free 正确性)
        gone = [c for c in pos if i > last_idx[cidx[c]]]
        for c in gone:
            sh = pos.pop(c); p = row[cidx[c]]
            if not np.isnan(p):
                cash += sh * p * (1 - SLIP - COMM - STAMP)
        # 估值(停牌股按 ffill 最近有效价)
        mv = 0.0
        for c, sh in pos.items():
            p = row[cidx[c]]
            if not np.isnan(p): mv += sh * p
        equity.append((day, cash + mv))

        if day not in rb_set or i + 1 >= len(dates):
            continue
        nd_i = i + 1                          # t+1 执行
        # 选股:signal 当日值 ∩ 当日在市,取前 n_hold
        srow = signal.iloc[i]
        sig = srow[srow.notna()]
        inm_row = INMv[i]
        sig = sig[[(c in cidx) and inm_row[cidx[c]] for c in sig.index]]
        if len(sig) == 0:
            continue
        target = list(sig.sort_values(ascending=False).head(n_hold).index)

        # 目标权重
        if wdf is not None:
            raw = wdf.iloc[i].reindex(target).values.astype(float)
            raw = np.where(np.isfinite(raw), raw, 0.0)
            raw = np.clip(raw, 0.0, None)
            s = raw.sum()
            w = dict(zip(target, raw / s)) if s > 0 else {c: 1.0 / len(target) for c in target}
        elif weight == "invvol":
            vv = np.array([vol63[i, cidx[c]] for c in target])
            good = (vv > 0) & np.isfinite(vv)
            inv = np.full(len(vv), np.nan)
            inv[good] = 1.0 / vv[good]
            if np.isfinite(inv).any():
                inv = np.where(np.isnan(inv), np.nanmean(inv), inv); inv = inv / inv.sum()
            else:
                inv = np.full(len(target), 1.0 / len(target))
            w = dict(zip(target, inv))
        else:
            w = {c: 1.0 / len(target) for c in target}

        tset = set(target)
        cur_val = equity[-1][1]
        px = Ov[nd_i]                         # t+1 开盘价执行
        # 先卖:不在目标 或 超配;受 can_sell(涨跌停/停牌)限制
        for c in list(pos.keys()):
            if not CSv[nd_i, cidx[c]]:
                continue
            p = px[cidx[c]]
            tgt_sh = (cur_val * w[c]) / p if (c in tset and not np.isnan(p)) else 0.0
            if pos[c] > tgt_sh:
                if np.isnan(p): continue
                sell = pos[c] - tgt_sh
                cash += sell * p * (1 - SLIP - COMM - STAMP)
                turnover_sum += sell * p
                pos[c] = tgt_sh
                if pos[c] <= 1e-6: del pos[c]
        # 再买:目标里欠配;受 can_buy 限制
        for c in target:
            if not CBv[nd_i, cidx[c]]:
                continue
            p = px[cidx[c]]
            if np.isnan(p): continue
            tgt_sh = (cur_val * w[c]) / p
            cur_sh = pos.get(c, 0.0)
            if tgt_sh > cur_sh:
                buy = tgt_sh - cur_sh
                cost = buy * p * (1 + SLIP + COMM)
                if cost > cash:
                    buy = cash / (p * (1 + SLIP + COMM)); cost = cash
                cash -= cost
                turnover_sum += buy * p
                pos[c] = cur_sh + buy

    eq = pd.Series(dict(equity)).sort_index()
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    # 换手按【平均权益】归一(不是初始资本,否则复利增长会把换手虚高数十倍)
    ann_turnover = turnover_sum / max(eq.mean(), 1.0) / max(years, 0.1)
    return dict(equity=eq, turnover=ann_turnover)


def metrics(eq):
    """CAGR / Sharpe / maxDD / Calmar / vol(年化)。"""
    eq = eq.dropna()
    r = eq.pct_change(fill_method=None).dropna()
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1
    vol = r.std() * np.sqrt(TRADING_DAYS)
    sharpe = (r.mean() * TRADING_DAYS) / vol if vol > 0 else 0
    dd = (eq / eq.cummax() - 1).min()
    calmar = cagr / abs(dd) if dd < 0 else np.nan
    return dict(CAGR=round(cagr, 4), Sharpe=round(sharpe, 3),
                maxDD=round(dd, 4), Calmar=round(calmar, 3), vol=round(vol, 4))
