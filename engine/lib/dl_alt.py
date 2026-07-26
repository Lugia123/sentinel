#!/usr/bin/env python3
"""多源另类数据下载器 → data/alt/<name>.parquet。用法:python lib/dl_alt.py <name>
name ∈ {analyst, ggcg, lhb, jiejin, dzjy}。全部"按日期/全量拉",含历史退市股(survivorship LOW)。"""
import os, sys, time
import akshare as ak, pandas as pd, warnings
warnings.filterwarnings("ignore")
DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
OUT = os.path.join(DATA_DIR, "alt"); os.makedirs(OUT, exist_ok=True)

def trade_days(y0=2007):
    d = ak.tool_trade_date_hist_sina()["trade_date"]
    d = pd.to_datetime(d)
    return [x.strftime("%Y%m%d") for x in d if x.year >= y0 and x <= pd.Timestamp.today()]

def retry(fn, tries=3, sleep=2):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(sleep)

# ---- 分析师评级(cninfo,按交易日,2018-06+) ----
def dl_analyst():
    days = [d for d in trade_days(2018) if d >= "20180601"]
    rows = []
    for k, d in enumerate(days):
        try:
            df = retry(lambda: ak.stock_rank_forecast_cninfo(date=d))
            if df is not None and len(df):
                df = df.copy(); df["交易日"] = d
                rows.append(df)
        except Exception as e:
            print(f"{d} FAIL {type(e).__name__}", flush=True)
        if k % 50 == 0:
            print(f"{k}/{len(days)} {d} rows_so_far={sum(len(r) for r in rows)}", flush=True)
    save(pd.concat(rows, ignore_index=True), "analyst", "发布日期")

# ---- 高管/股东增减持(全量一次,含公告日期) ----
def dl_ggcg():
    df = retry(lambda: ak.stock_ggcg_em(symbol="全部"), tries=2, sleep=5)
    save(df, "ggcg", None)

# ---- 龙虎榜(按年拉,2007+) ----
def dl_lhb():
    rows = []
    for y in range(2007, 2027):
        s, e = f"{y}0101", f"{y}1231"
        try:
            df = retry(lambda: ak.stock_lhb_detail_em(start_date=s, end_date=e))
            if df is not None and len(df):
                rows.append(df)
            print(f"{y}: {0 if df is None else len(df)}", flush=True)
        except Exception as ex:
            print(f"{y} FAIL {type(ex).__name__}", flush=True)
    save(pd.concat(rows, ignore_index=True), "lhb", "上榜日")

# ---- 限售解禁(按年拉,2010+;排除未来列) ----
def dl_jiejin():
    rows = []
    for y in range(2010, 2027):
        s, e = f"{y}0101", f"{y}1231"
        try:
            df = retry(lambda: ak.stock_restricted_release_detail_em(start_date=s, end_date=e))
            if df is not None and len(df):
                # 剔除未来列(解禁后N日涨跌幅是前视)
                drop = [c for c in df.columns if "解禁后" in c]
                rows.append(df.drop(columns=drop))
            print(f"{y}: {0 if df is None else len(df)}", flush=True)
        except Exception as ex:
            print(f"{y} FAIL {type(ex).__name__}", flush=True)
    save(pd.concat(rows, ignore_index=True), "jiejin", "解禁时间")

# ---- 大宗交易(按交易日,2007+) ----
def dl_dzjy():
    days = trade_days(2010)
    rows = []
    for k, d in enumerate(days):
        try:
            df = retry(lambda: ak.stock_dzjy_mrmx(symbol="A股", start_date=d, end_date=d))
            if df is not None and len(df):
                rows.append(df)
        except Exception:
            pass
        if k % 100 == 0:
            print(f"{k}/{len(days)} {d} rows={sum(len(r) for r in rows)}", flush=True)
    save(pd.concat(rows, ignore_index=True), "dzjy", None)

# ---- ★机构调研统计(东财,按年锚点调用+去重,单次返回累计窗~90s) ----
def dl_jgdy():
    rows = []
    for y in range(2010, 2027):
        anchor = f"{y}1231" if y < 2026 else pd.Timestamp.today().strftime("%Y%m%d")
        try:
            df = retry(lambda: ak.stock_jgdy_tj_em(date=anchor), tries=2, sleep=5)
            if df is not None and len(df):
                rows.append(df)
                dmin = pd.to_datetime(df["接待日期"], errors="coerce").min()
                dmax = pd.to_datetime(df["接待日期"], errors="coerce").max()
                print(f"anchor {anchor}: {len(df)} 接待日{dmin}~{dmax}", flush=True)
        except Exception as ex:
            print(f"anchor {anchor} FAIL {type(ex).__name__}", flush=True)
    all_df = pd.concat(rows, ignore_index=True)
    # 去重:同一(代码,接待日期)保留一条
    all_df = all_df.drop_duplicates(subset=["代码", "接待日期"])
    save(all_df, "jgdy", "接待日期")

# ---- 股东户数(按报告期,2013+,筹码集中度) ----
def dl_gdhs():
    rows = []
    for y in range(2013, 2027):
        for q in ("0331", "0630", "0930", "1231"):
            d = f"{y}{q}"
            try:
                df = retry(lambda: ak.stock_zh_a_gdhs(symbol=d))
                if df is not None and len(df):
                    df = df.copy(); df["报告期"] = d; rows.append(df)
                    print(f"{d}: {len(df)}", flush=True)
            except Exception as ex:
                print(f"{d} FAIL {type(ex).__name__}", flush=True)
    save(pd.concat(rows, ignore_index=True), "gdhs", None)

# ---- 融资融券(深+沪,按交易日,2010/2014+) ----
def dl_margin():
    days = trade_days(2010)
    rows = []
    for k, d in enumerate(days):
        for fn in (lambda: ak.stock_margin_detail_szse(date=d),
                   lambda: ak.stock_margin_detail_sse(date=d)):
            try:
                df = fn()
                if df is not None and len(df):
                    df = df.copy(); df["交易日"] = d; rows.append(df)
            except Exception:
                pass
        if k % 150 == 0:
            print(f"{k}/{len(days)} {d} rows={sum(len(r) for r in rows)}", flush=True)
    save(pd.concat(rows, ignore_index=True), "margin", "交易日")

# ---- 股票回购(全量一次) ----
def dl_repurchase():
    df = retry(lambda: ak.stock_repurchase_em())
    save(df, "repurchase", None)

def save(df, name, datecol):
    fp = os.path.join(OUT, f"{name}.parquet")
    df.to_parquet(fp, index=False)
    dc = f"  {datecol}范围={df[datecol].min()}~{df[datecol].max()}" if datecol and datecol in df.columns else ""
    print(f"\nSAVED {fp}  rows={len(df)}  cols={list(df.columns)}{dc}", flush=True)

if __name__ == "__main__":
    {"analyst": dl_analyst, "ggcg": dl_ggcg, "lhb": dl_lhb,
     "jiejin": dl_jiejin, "dzjy": dl_dzjy, "jgdy": dl_jgdy,
     "gdhs": dl_gdhs, "margin": dl_margin, "repurchase": dl_repurchase}[sys.argv[1]]()
