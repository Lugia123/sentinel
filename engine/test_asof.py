#!/usr/bin/env python3
"""
test_asof.py — Sentinel 引擎 as-of 自动测试(可指定过往日期,非系统时间)
=========================================================================
满足需求:测试接口可指定 as-of 时间,从过往日期模拟,验证系统稳定性 + 无前视。
对多个历史日期跑引擎,校验:①asof 正确 ②无前视(快照价=该ticker当日CSV收盘)
③数值合理(持仓数/档位范围/概率带单调/止损<现价<目标)④跨日期不崩。
用法:python test_asof.py           (默认一组历史日期,--no-sy 快)
      python test_asof.py --dates 2024-06-14,2025-06-16
"""
import sys, os, json, subprocess, argparse
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(os.path.dirname(HERE), "data")
PY = sys.executable
DEFAULT_DATES = ["2024-06-14", "2024-12-16", "2025-06-16", "2025-12-15", "2026-06-01"]


def close_at(ticker, date):
    """某 ticker 在 <=date 的最后收盘价(独立于引擎,做无前视对照)。"""
    fp = os.path.join(DATA, f"{ticker}.csv")
    if not os.path.exists(fp):
        return None
    df = pd.read_csv(fp, parse_dates=["date"])
    sub = df[df["date"] <= pd.Timestamp(date)]
    return round(float(sub["close"].iloc[-1]), 2) if len(sub) else None


def check(snap, asof):
    errs = []
    # asof 一致(引擎取 <=asof 的最后交易日)
    if snap["asof"] > asof:
        errs.append(f"asof {snap['asof']} > 请求 {asof}(前视!)")
    hs = snap["holdings"]
    if not (1 <= len(hs) <= 25):
        errs.append(f"持仓数异常 {len(hs)}")
    for h in hs:
        if not (-3 <= h["grade"] <= 3):
            errs.append(f"{h['ticker']} 档位越界 {h['grade']}")
        if h["price"] <= 0:
            errs.append(f"{h['ticker']} 价格非正 {h['price']}")
        b = h["prob"]["h20"]
        if not (b["band70"][0] <= b["median"] <= b["band70"][1]):
            errs.append(f"{h['ticker']} 概率带非单调 {b['band70']} 中位{b['median']}")
        if not (b["stop"] < h["price"] < b["target"]):
            errs.append(f"{h['ticker']} 止损/目标不夹现价 {b['stop']}<{h['price']}<{b['target']}")
        if not (0 <= b["p_hit_target"] <= 1 and 0 <= b["p_hit_stop"] <= 1):
            errs.append(f"{h['ticker']} 概率越界")
        # 无前视:快照价 == 独立算的 <=snap.asof 收盘
        ref = close_at(h["ticker"], snap["asof"])
        if ref is not None and abs(ref - h["price"]) > 0.02:
            errs.append(f"{h['ticker']} 价格前视? 快照{h['price']} vs CSV{ref}")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", default=",".join(DEFAULT_DATES))
    ap.add_argument("--with-sy", action="store_true")
    args = ap.parse_args()
    dates = args.dates.split(",")
    print(f"=== as-of 测试 {len(dates)} 个历史日期 ===", flush=True)
    npass = 0
    for d in dates:
        cmd = [PY, os.path.join(HERE, "run_daily.py"), "--asof", d]
        if not args.with_sy:
            cmd.append("--no-sy")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"✗ {d}: 引擎崩溃\n{r.stderr[-300:]}", flush=True); continue
        # 引擎写 snapshot_<实际收盘日>.json;从 stdout 拿实际 asof
        snapf = None
        for f in os.listdir(OUT):
            if f.startswith("snapshot_") and f != "snapshot_latest.json":
                pass
        snap = json.load(open(os.path.join(OUT, "snapshot_latest.json")))
        errs = check(snap, d)
        if errs:
            print(f"✗ {d}(实际{snap['asof']}): {len(errs)} 项问题", flush=True)
            for e in errs[:5]:
                print(f"    - {e}", flush=True)
        else:
            npass += 1
            print(f"✓ {d}(实际{snap['asof']}): {len(snap['holdings'])}持仓 风险灯{snap['risk_light']['level']} 全部校验通过", flush=True)
    print(f"\n=== 结果: {npass}/{len(dates)} 通过 ===", flush=True)
    sys.exit(0 if npass == len(dates) else 1)


if __name__ == "__main__":
    main()
