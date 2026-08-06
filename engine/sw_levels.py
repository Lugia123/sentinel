#!/usr/bin/env python3
"""申万行业分级(SW2021 L1/L2/L3)名称 → 层级,用于给东财板块(moneyflow_ind_dc)打层级标签。
东财板块名与申万行业名高度重合(实测 496 板块 492 命中),据此消除"多个半导体"的父子重叠。
带本地文件缓存(7天),避免每次多打 3 次 index_classify。
"""
import os, json, time
from ts_refresh import ts

_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_cn_meta", "sw_levels.json")


def name_to_level():
    """返回 {行业名: 层级(1/2/3)}。名字跨级重复时取更高级(L1 优先)。拉取失败回退空 dict。"""
    # 缓存命中(7天内)
    try:
        if os.path.exists(_CACHE) and time.time() - os.path.getmtime(_CACHE) < 7 * 86400:
            return json.load(open(_CACHE, encoding="utf-8"))
    except Exception:
        pass
    m = {}
    for lv, num in (("L1", 1), ("L2", 2), ("L3", 3)):
        df = ts("index_classify", {"level": lv, "src": "SW2021"}, "industry_name")
        if df is None:
            continue
        for n in df["industry_name"]:
            key = str(n).strip()
            if key and key not in m:   # 先 L1 → 保留最高级
                m[key] = num
    if m:
        try:
            os.makedirs(os.path.dirname(_CACHE), exist_ok=True)
            json.dump(m, open(_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass
    return m


if __name__ == "__main__":
    m = name_to_level()
    from collections import Counter
    print("层级分布:", Counter(m.values()), "共", len(m), "个行业名")
