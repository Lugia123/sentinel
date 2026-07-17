#!/usr/bin/env python3
"""cn_engine 周频调仓 + 换手阻尼 测试。验证:①本周新选 ②周内保持名单 ③到期重选 ④失效股当周剔除 ⑤turnMA窗生效。
用法:python engine/test_rebalance.py   (会临时占用 data/snapshot_cn_latest.json,跑完还原)
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cn_engine as ce

SNAP = os.path.join(ce.OUT_DIR, "snapshot_cn_latest.json")
BAK = SNAP + ".testbak"
D_LATE = "2026-07-10"   # 数据末端附近的真实交易日
fails = []


def check(name, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (f"  [{detail}]" if detail else ""))
    if not cond:
        fails.append(name)


def write_prev(rebalance_asof, sc_tickers, ev_tickers=()):
    holds = [dict(ticker=t, sleeve="smallcap") for t in sc_tickers] + \
            [dict(ticker=t, sleeve="event") for t in ev_tickers]
    json.dump(dict(rebalance_asof=rebalance_asof, holdings=holds),
              open(SNAP, "w"), ensure_ascii=False)


def sc_names(snap):
    return [h["ticker"] for h in snap["holdings"] if h["sleeve"] in ("smallcap", "both")]


def main():
    if os.path.exists(SNAP):
        os.rename(SNAP, BAK)
    try:
        print(f"TURN_WIN={ce.TURN_WIN} REBAL_DAYS={ce.REBAL_DAYS}")

        # ── 场景1:无上次快照 → 本周新选 ──
        print("\n[1] 无历史 → 本周新选(重选)")
        if os.path.exists(SNAP):
            os.remove(SNAP)
        s1, _ = ce.compute_snapshot_cn(asof=D_LATE)
        n1 = sc_names(s1)
        check("重选:rebalance_asof=asof", s1["rebalance_asof"] == s1["asof"], f"{s1['rebalance_asof']} vs {s1['asof']}")
        check("头号腿选到票", 30 <= len(n1) <= 50, f"{len(n1)}只")
        check("reason标'本周新选'", any("本周新选" in h["reason"] for h in s1["holdings"] if h["sleeve"] in ("smallcap", "both")))
        check("indicators带turn_win", all(h["indicators"].get("turn_win") == ce.TURN_WIN
                                          for h in s1["holdings"] if h["sleeve"] == "smallcap"))
        check("portfolio.rebalance=周频", s1["portfolio"]["rebalance"] == "周频")

        # ── 场景2:上次调仓在5交易日内 → 周内保持名单 ──
        print("\n[2] 上次调仓在5交易日内 → 保持名单")
        held = n1[:20]                       # 假装上次持有这20只(全在选池,应存活)
        write_prev(rebalance_asof="2026-07-08", sc_tickers=held)   # 距7-10约2交易日
        s2, _ = ce.compute_snapshot_cn(asof=D_LATE)
        n2 = sc_names(s2)
        check("保持:rebalance_asof=上次(7-08)", s2["rebalance_asof"] == "2026-07-08", s2["rebalance_asof"])
        check("持仓名单=上次(存活子集)", set(n2) <= set(held) and len(n2) >= 15, f"{len(n2)}只,子集={set(n2)<=set(held)}")
        check("reason标'周频持仓第N日'", any("周频持仓" in h["reason"] for h in s2["holdings"] if h["sleeve"] in ("smallcap", "both")))
        check("days_since_rebalance>0", s2["portfolio"]["days_since_rebalance"] > 0, str(s2["portfolio"]["days_since_rebalance"]))

        # ── 场景3:失效股(伪造不存在代码)当周剔除 ──
        print("\n[3] 持仓含失效股 → 当周剔除不回补")
        write_prev(rebalance_asof="2026-07-08", sc_tickers=held[:10] + ["sh.000000", "sz.999999"])
        s3, _ = ce.compute_snapshot_cn(asof=D_LATE)
        n3 = sc_names(s3)
        check("失效股被剔除", "sh.000000" not in n3 and "sz.999999" not in n3)
        check("不回补(≤存活数)", len(n3) <= 10, f"{len(n3)}只")

        # ── 场景4:上次调仓超过5交易日 → 到期重选 ──
        print("\n[4] 上次调仓>5交易日 → 到期重选")
        write_prev(rebalance_asof="2026-06-01", sc_tickers=held)   # 远早于5交易日
        s4, _ = ce.compute_snapshot_cn(asof=D_LATE)
        n4 = sc_names(s4)
        check("重选:rebalance_asof=asof", s4["rebalance_asof"] == s4["asof"], s4["rebalance_asof"])
        check("重新选满", 30 <= len(n4) <= 50, f"{len(n4)}只")
        check("名单≠伪造持仓(真重选)", set(n4) != set(held))

        print("\n" + ("全部通过 ✓" if not fails else f"失败 {len(fails)}: {fails}"))
        return 0 if not fails else 1
    finally:
        if os.path.exists(BAK):
            os.replace(BAK, SNAP)
        elif os.path.exists(SNAP):
            os.remove(SNAP)


if __name__ == "__main__":
    sys.exit(main())
