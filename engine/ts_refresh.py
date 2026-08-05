#!/usr/bin/env python3
"""tushare 定时/增量刷新【事件腿+红利腿】的另类数据,替代冻结的 akshare 静态 parquet。
头号腿行情仍走 baostock(已每日活、AB实测更优);本脚本只管 event/dividend 的 alt 数据。
产出与引擎现有 schema 完全一致的 parquet → 引擎(cn_engine.rev_pead_pick / dividend_lowvol_pick)不用改:
  div_events.parquet (code[sh.600000], ann_date, dps)              ← tushare dividend(div_proc=实施)
  yjyg.parquet       (股票代码[6位], 公告日期, 预测指标, 预告类型, 报告期) ← tushare forecast
  analyst.parquet    (证券代码[6位], 发布日期, 评级变化)               ← tushare report_rc(按机构派生调高/调低)
凭证:SENTINEL_TS_URL / SENTINEL_TS_TOKEN(回退 TS_URL / TS_TOKEN)。数据目录:SENTINEL_ALT_DIR。
用法:
  python ts_refresh.py --full            # 全历史重建(首次迁移;~37min)
  python ts_refresh.py --days 180        # 增量(最近N交易日,定时刷新调用;默认180)
  python ts_refresh.py --since 20260701  # 增量(自 20260701 起的全部交易日;补断档用,优先于 --days)
"""
import os, sys, time, argparse
import requests
import numpy as np
import pandas as pd

TS_URL = os.environ.get("SENTINEL_TS_URL") or os.environ.get("TS_URL")
TS_TOKEN = os.environ.get("SENTINEL_TS_TOKEN") or os.environ.get("TS_TOKEN")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("SENTINEL_DATA_DIR", os.path.join(HERE, "data"))
ALT_DIR = os.environ.get("SENTINEL_ALT_DIR", os.path.join(DATA_DIR, "alt"))
RAW_RC = os.path.join(ALT_DIR, "report_rc_raw.parquet")   # report_rc 原始囤积(派生评级变化用)
SLEEP = 0.42                                              # ~142/min < 150 限频

# 券商评级 → 序数(用于派生"调高/调低")。覆盖常见叫法,未知留 NaN 不计。
RATING_ORD = {
    "卖出": 0, "强烈卖出": 0, "减持": 1, "回避": 1, "中性": 2, "持有": 2, "观望": 2, "同步大市": 2,
    "增持": 3, "跑赢行业": 3, "审慎推荐": 3, "谨慎推荐": 3, "优于大市": 3, "推荐": 4, "买入": 4,
    "强推": 5, "强烈推荐": 5, "强烈买入": 5,
}


def ts(api, params, fields="", retries=3):
    if not (TS_URL and TS_TOKEN):
        raise SystemExit("缺 SENTINEL_TS_URL / SENTINEL_TS_TOKEN(或 TS_URL/TS_TOKEN)")
    for _ in range(retries):
        try:
            r = requests.post(TS_URL, json={"api_name": api, "token": TS_TOKEN, "params": params, "fields": fields},
                              headers={"Accept-Encoding": "gzip"}, timeout=30)
            j = r.json()
            if j.get("code") == 0:
                d = j["data"]
                return pd.DataFrame(d["items"], columns=d["fields"])
            time.sleep(1)
        except Exception:
            time.sleep(1)
    return None


def bare(tc):
    return str(tc).split(".")[0]                       # 600000.SH → 600000


def dotcode(tc):
    num, mk = str(tc).split("."); return f"{mk.lower()}.{num}"   # 600000.SH → sh.600000


def trade_dates(start):
    today = pd.Timestamp.today().strftime("%Y%m%d")     # 截到今天,不含未来排期交易日
    df = ts("trade_cal", {"exchange": "SSE", "start_date": start, "end_date": today, "is_open": "1"}, "cal_date")
    if df is None:
        return []
    return sorted(d for d in df["cal_date"].tolist() if d <= today)


def periods_between(start):
    """报告期(季度末)列表 >= start 且 <= 今天。"""
    y0 = int(start[:4]); yN = pd.Timestamp.today().year
    today = pd.Timestamp.today().strftime("%Y%m%d")
    out = []
    for y in range(y0, yN + 1):
        for md in ("0331", "0630", "0930", "1231"):
            out.append(f"{y}{md}")
    return [p for p in out if start <= p <= today]


# ────────────────── 各源刷新 ──────────────────
def pull_dividend(dates):
    rows = []
    for i, dt in enumerate(dates):
        df = ts("dividend", {"ann_date": dt}, "ts_code,ann_date,div_proc,cash_div_tax")
        if df is not None and len(df):
            df = df[df["div_proc"] == "实施"].copy()
            df["dps"] = pd.to_numeric(df["cash_div_tax"], errors="coerce")
            df = df[df["dps"].fillna(0) > 0]
            for _, r in df.iterrows():
                rows.append({"code": dotcode(r["ts_code"]), "ann_date": pd.to_datetime(dt), "dps": float(r["dps"])})
        time.sleep(SLEEP)
        if (i + 1) % 200 == 0:
            print(f"  dividend {i+1}/{len(dates)}", flush=True)
    return pd.DataFrame(rows, columns=["code", "ann_date", "dps"])


def pull_forecast(periods):
    rows = []
    for p in periods:
        df = ts("forecast_vip", {"period": p}, "ts_code,ann_date,end_date,type")   # _vip 支持 period 批量(free forecast 需 ts_code)
        if df is not None and len(df):
            for _, r in df.iterrows():
                if not r.get("ann_date"):
                    continue
                rows.append({"股票代码": bare(r["ts_code"]), "公告日期": pd.to_datetime(r["ann_date"]),
                             "预测指标": "净利润", "预告类型": r["type"], "报告期": r["end_date"]})
        time.sleep(SLEEP)
    return pd.DataFrame(rows, columns=["股票代码", "公告日期", "预测指标", "预告类型", "报告期"])


def pull_report_rc(dates):
    recs = []
    for i, dt in enumerate(dates):
        df = ts("report_rc", {"report_date": dt}, "ts_code,report_date,org_name,rating")
        if df is not None and len(df):
            recs.append(df)
        time.sleep(SLEEP)
        if (i + 1) % 200 == 0:
            print(f"  report_rc {i+1}/{len(dates)}", flush=True)
    return pd.concat(recs, ignore_index=True) if recs else pd.DataFrame(columns=["ts_code", "report_date", "org_name", "rating"])


def derive_analyst(rc_raw):
    """report_rc 原始 → analyst.parquet(证券代码/发布日期/评级变化)。按(机构,股)连续评级派生调高/调低。"""
    d = rc_raw.dropna(subset=["ts_code", "report_date", "rating"]).copy()
    d["ord"] = d["rating"].map(RATING_ORD)
    d = d.dropna(subset=["ord"])
    d["rd"] = pd.to_datetime(d["report_date"], errors="coerce")
    d = d.dropna(subset=["rd"]).sort_values(["ts_code", "org_name", "rd"])
    d["prev"] = d.groupby(["ts_code", "org_name"])["ord"].shift(1)
    chg = np.where(d["prev"].isna(), "未知",
          np.where(d["ord"] > d["prev"], "调高",
          np.where(d["ord"] < d["prev"], "调低", "维持")))
    out = pd.DataFrame({"证券代码": d["ts_code"].map(bare), "发布日期": d["rd"], "评级变化": chg})
    return out


# ────────────────── A股板块/中文名 → ticker_meta.json ──────────────────
def refresh_cn_meta():
    """从 tushare stock_basic 拉 A股 中文名+行业,合并进 engine/ticker_meta.json 的 A股条目
    (格式 {code[sh.600000]: {cn, sector}},与美股共存)。前端「板块」列即有值。covers 新股。"""
    df = ts("stock_basic", {"list_status": "L"}, "ts_code,name,industry")
    if df is None or df.empty:
        print("  ticker_meta: stock_basic 拉取失败,跳过", flush=True); return
    meta_fp = os.path.join(HERE, "ticker_meta.json")
    meta = {}
    if os.path.exists(meta_fp):
        try:
            import json
            meta = json.load(open(meta_fp, encoding="utf-8"))
        except Exception:
            meta = {}
    def s(x):
        return str(x).strip() if pd.notna(x) else ""
    n = 0
    for _, r in df.iterrows():
        code = dotcode(r["ts_code"])                       # 600000.SH → sh.600000
        meta[code] = {"cn": s(r.get("name")), "sector": s(r.get("industry")) or "其他"}
        n += 1
    import json
    json.dump(meta, open(meta_fp, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"  写 ticker_meta.json: A股 {n} 条(+美股保留),共 {len(meta)} 条", flush=True)


# ────────────────── 合并落盘 ──────────────────
def merge_write(path, new, keys):
    if new is None or new.empty:
        print(f"  {os.path.basename(path)}: 无新增", flush=True); return
    if os.path.exists(path):
        old = pd.read_parquet(path)
        # 只保留新数据实际有的列 + 老数据(schema 对齐)
        allc = pd.concat([old, new], ignore_index=True)
    else:
        allc = new
    allc = allc.drop_duplicates(subset=keys, keep="last")
    allc.to_parquet(path, index=False)
    print(f"  写 {os.path.basename(path)}: {len(allc)} 行(本次并入 {len(new)})", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="全历史重建(2016+)")
    ap.add_argument("--days", type=int, default=180, help="增量:最近N交易日(默认180)")
    ap.add_argument("--since", default="", help="增量:自该日(YYYYMMDD)起的全部交易日;补断档用,优先于 --days")
    ap.add_argument("--start", default="20160101")
    a = ap.parse_args()
    os.makedirs(ALT_DIR, exist_ok=True)

    if a.full:
        start = a.start
        dates = trade_dates(start)
        periods = periods_between(start)
    elif a.since:
        # 断档自愈:自上次成功日起,重拉全部交易日(不受45天窗口限制)。merge 幂等去重,重叠无害。
        since = "".join(ch for ch in a.since if ch.isdigit())[:8] or "20260101"
        dates = trade_dates(since)
        start = dates[0] if dates else since
        periods = periods_between((pd.Timestamp(start) - pd.Timedelta(days=200)).strftime("%Y%m%d"))
    else:
        # 增量:最近 N 交易日(报告期取最近2季)。无 Date.now → 用交易日历末端回退。
        alld = trade_dates("20260101")
        dates = alld[-min(a.days, len(alld)):] if alld else []
        start = dates[0] if dates else "20260101"
        periods = periods_between((pd.Timestamp(start) - pd.Timedelta(days=200)).strftime("%Y%m%d"))
    if not dates:
        raise SystemExit("取不到交易日历(检查凭证/网络)")
    print(f"[ts_refresh] {'全量' if a.full else '增量'} {dates[0]}~{dates[-1]} ({len(dates)}日) → {ALT_DIR}", flush=True)

    # 1. 分红 → div_events
    print("① dividend …", flush=True)
    merge_write(os.path.join(ALT_DIR, "div_events.parquet"), pull_dividend(dates), keys=["code", "ann_date", "dps"])
    # 2. 业绩预告 → yjyg
    print("② forecast …", flush=True)
    merge_write(os.path.join(ALT_DIR, "yjyg.parquet"), pull_forecast(periods), keys=["股票代码", "公告日期", "预告类型", "报告期"])
    # 3. 研报评级 → report_rc_raw(囤积)→ 派生 analyst
    print("③ report_rc …", flush=True)
    rc_new = pull_report_rc(dates)
    merge_write(RAW_RC, rc_new, keys=["ts_code", "report_date", "org_name", "rating"])
    if os.path.exists(RAW_RC):
        analyst = derive_analyst(pd.read_parquet(RAW_RC))
        analyst.to_parquet(os.path.join(ALT_DIR, "analyst.parquet"), index=False)
        print(f"  写 analyst.parquet: {len(analyst)} 行(调高{(analyst['评级变化']=='调高').sum()}/调低{(analyst['评级变化']=='调低').sum()})", flush=True)
    # 4. A股 中文名+板块 → ticker_meta.json(前端「板块」列)
    print("④ ticker_meta(A股板块)…", flush=True)
    refresh_cn_meta()
    print("[ts_refresh] 完成", flush=True)


if __name__ == "__main__":
    main()
