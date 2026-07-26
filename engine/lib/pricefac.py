#!/usr/bin/env python3
"""价量/行为因子库(全历史·numpy向量化)。返回 date×code 信号(月度选股用)。
市场 = 同日可交易股等权收益(EW-market)。因子构造只用当日及之前信息(无前视)。"""
import numpy as np, pandas as pd


def _ret(M):
    return M["close"].pct_change(fill_method=None)


def mkt_ret(M):
    """市场收益 = 每日可交易股等权收益。"""
    r = _ret(M).where(M["in_market"])
    return r.mean(axis=1)


def beta(M, win=120):
    """个股对 EW-市场 的滚动 beta。低beta异象=做多低beta。"""
    r = _ret(M); rm = mkt_ret(M)
    rm2 = rm.rolling(win).var()
    # cov(r_i, rm) rolling = E[r_i*rm]-E[r_i]E[rm]
    cov = r.mul(rm, axis=0).rolling(win).mean().sub(r.rolling(win).mean().mul(rm.rolling(win).mean(), axis=0))
    return cov.div(rm2.replace(0, np.nan), axis=0)


def idio_vol(M, win=120):
    """特异波动率:对市场回归后残差的波动(近似=总波动√(1-corr²))。低idio-vol异象。"""
    r = _ret(M); rm = mkt_ret(M)
    sd_i = r.rolling(win).std(); sd_m = rm.rolling(win).std()
    cov = r.mul(rm, axis=0).rolling(win).mean().sub(r.rolling(win).mean().mul(rm.rolling(win).mean(), axis=0))
    corr = cov.div((sd_i.mul(sd_m, axis=0)).replace(0, np.nan))
    return sd_i * np.sqrt((1 - corr ** 2).clip(lower=0))


def ret_skew(M, win=60):
    """日收益偏度(win日)。低偏度/负偏度异象(高偏度=彩票,类MAX)。"""
    r = _ret(M)
    return r.rolling(win).skew()


def high52(M, win=250):
    """52周高点接近度 = close / 期间最高价(∈(0,1],越接近1越强)。George-Hwang锚定。"""
    C = M["close"]
    return C / C.rolling(win).max()


def pv_corr(M, win=20):
    """量价配合:价格变化与成交量变化的滚动相关。正=量价配合,负=背离。"""
    r = _ret(M); dv = M["amount"].pct_change(fill_method=None).clip(-3, 3)
    sd_r = r.rolling(win).std(); sd_v = dv.rolling(win).std()
    cov = r.mul(dv).rolling(win).mean().sub(r.rolling(win).mean().mul(dv.rolling(win).mean()))
    return cov.div((sd_r * sd_v).replace(0, np.nan))


def turn_accel(M, short=5, long=60):
    """换手率加速 = 短期均换手 / 长期均换手(>1=放量)。区别于换手率水平。"""
    t = M["turn"]
    return t.rolling(short).mean() / t.rolling(long).mean().replace(0, np.nan)


def amplitude(M, win=20):
    """振幅因子 = (最高−最低)/前收 的 win日均。高振幅=投机。"""
    amp = (M["high"] - M["low"]) / M["pclose"].replace(0, np.nan)
    return amp.rolling(win).mean()


def overnight_ret(M, win=20):
    """隔夜收益累计 = (open/prev_close−1) 的 win日均。A股隔夜动量/反转。"""
    on = M["open"] / M["pclose"].replace(0, np.nan) - 1
    return on.rolling(win).mean()


def intraday_ret(M, win=20):
    """日内收益累计 = (close/open−1) 的 win日均。"""
    intr = M["close"] / M["open"].replace(0, np.nan) - 1
    return intr.rolling(win).mean()
