#!/usr/bin/env python3
"""P2 验证:引擎在 akshare-alt(生产现状)vs tushare-alt(迁移后)上,事件腿/红利腿选股对比。
头号腿不涉及(仍 baostock)。验证迁移:①两源都能产出有效选股 ②重叠合理(红利同定义应高;事件因评级变化派生方式不同会中等)③数值 sane。
用法:SENTINEL_TS_STAGE=<暂存alt目录> python engine/test_ts_migration.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cn_engine as ce

PROD_ALT = ce.ALT_DIR                                              # 生产(akshare 静态)
STAGE_ALT = os.environ["SENTINEL_TS_STAGE"]                        # tushare 重建


def picks_on(alt_dir, M):
    ce.ALT_DIR = alt_dir                                           # 切换引擎读的另类数据目录
    ev = ce.rev_pead_pick(M)          # [(code, score)]
    dv = ce.dividend_lowvol_pick(M)   # [(code, yld%, fmc亿)]
    return {c for c, *_ in ev}, {c for c, *_ in dv}, ev, dv


def jac(a, b):
    return len(a & b) / len(a | b) if (a or b) else float("nan")


def main():
    print("加载 baostock M …", flush=True)
    M = ce.load_matrices_cn() if hasattr(ce, "load_matrices_cn") else ce.E.load_matrices(start="2016-01-01")
    print(f"末日 {M['close'].index[-1].date()}\n", flush=True)

    print(f"A: akshare-alt = {PROD_ALT}")
    ea, da, ea_l, da_l = picks_on(PROD_ALT, M)
    print(f"B: tushare-alt = {STAGE_ALT}")
    eb, db, eb_l, db_l = picks_on(STAGE_ALT, M)

    print("\n" + "=" * 60)
    print(f"事件腿:A(akshare) {len(ea)}只 / B(tushare) {len(eb)}只 / 重叠 {jac(ea,eb)*100:.1f}%")
    print(f"红利腿:A(akshare) {len(da)}只 / B(tushare) {len(db)}只 / 重叠 {jac(da,db)*100:.1f}%")
    print("=" * 60)
    print("\nB队(tushare)红利腿今日样例(股息率%/流通亿):")
    for c, y, f in db_l[:8]:
        print(f"  {c}  股息{y}%  流通{f}亿")
    print("\nB队(tushare)事件腿今日样例(score):")
    for c, s in eb_l[:8]:
        print(f"  {c}  {s:.3f}")
    # sanity 断言
    ok = len(db) >= 30 and len(eb) >= 10 and all(0 <= y < 40 for c, y, f in db_l)
    print("\n" + ("✓ SANE:两腿都产出、股息率区间合理" if ok else "✗ 异常:选股数不足或股息率越界,需查"))


if __name__ == "__main__":
    main()
