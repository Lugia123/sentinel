"""
strategies — 可插拔策略框架。import 各模块触发注册;STRATEGY_CONFIG 声明启用哪些。
新增策略:在对应模块加类 + @register,再把名字加进下面 config。
"""
from .base import Context, SELECTORS, SIZERS, GRADERS, PREDICTORS, GATES  # noqa
from . import selectors, sizers, graders, predictors, gates  # noqa 触发注册

# 当前启用的策略组合(改这里即可切换/增删策略)
STRATEGY_CONFIG = {
    "selectors": ["momentum", "shareholder_yield"],  # 加新选股腿:追加名字
    "sizer": "risk_parity",
    "grader": "seven_signal",
    "predictor": "vol_scaled",
    "gate": "vol_target",
}


def active_manifest():
    """返回当前启用组件的清单(供 /api/strategies 展示)。"""
    def meta(reg, name):
        inst = reg.get(name)
        return dict(name=name, label=getattr(inst, "label", name),
                    universe=getattr(inst, "universe", None)) if inst else dict(name=name, missing=True)
    return dict(
        selectors=[meta(SELECTORS, n) for n in STRATEGY_CONFIG["selectors"]],
        sizer=meta(SIZERS, STRATEGY_CONFIG["sizer"]),
        grader=meta(GRADERS, STRATEGY_CONFIG["grader"]),
        predictor=meta(PREDICTORS, STRATEGY_CONFIG["predictor"]),
        gate=meta(GATES, STRATEGY_CONFIG["gate"]),
        available=dict(selectors=list(SELECTORS), sizers=list(SIZERS),
                       graders=list(GRADERS), predictors=list(PREDICTORS), gates=list(GATES)),
    )
