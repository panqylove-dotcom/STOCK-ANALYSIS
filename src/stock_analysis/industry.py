"""行业专用指标插件框架（docs/roadmap.md 阶段 5）。

设计：插件 = 函数 fn(metrics: dict[str, float]) -> dict[str, float]，
输入为上游提供的原始指标，输出为行业特有派生指标。
通过注册表按行业名分发，新增行业不需修改引擎。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

IndustryPlugin = Callable[[Mapping[str, float]], dict[str, float]]

_REGISTRY: dict[str, IndustryPlugin] = {}


def register_industry(name: str) -> Callable[[IndustryPlugin], IndustryPlugin]:
    """装饰器：注册行业插件。重复注册同名行业报错。"""

    def deco(fn: IndustryPlugin) -> IndustryPlugin:
        if name in _REGISTRY:
            raise ValueError(f"行业插件已注册: {name}")
        _REGISTRY[name] = fn
        return fn

    return deco


def available_industries() -> list[str]:
    return sorted(_REGISTRY)


def compute_industry_metrics(
    industry: str, metrics: Mapping[str, float]
) -> dict[str, float]:
    """按行业名计算专用指标；未知行业抛错。"""
    try:
        plugin = _REGISTRY[industry]
    except KeyError:
        raise ValueError(
            f"未知行业: {industry}；已注册: {available_industries()}"
        ) from None
    return dict(plugin(metrics))


# ---------------------------------------------------------------- 内置插件


@register_industry("software")
def _software(m: Mapping[str, float]) -> dict[str, float]:
    """软件行业：NDR、Rule of 40。"""
    out: dict[str, float] = {}
    if "revenue_growth" in m and "fcf_margin" in m:
        out["rule_of_40"] = m["revenue_growth"] + m["fcf_margin"]
    if "arr" in m and "prior_arr" in m and m["prior_arr"] != 0:
        out["arr_growth"] = m["arr"] / m["prior_arr"] - 1.0
    return out


@register_industry("bank")
def _bank(m: Mapping[str, float]) -> dict[str, float]:
    """银行：ROE、净息差 NIM（不适用普通企业净负债口径）。"""
    out: dict[str, float] = {}
    if "net_profit" in m and "equity" in m and m["equity"] != 0:
        out["roe"] = m["net_profit"] / m["equity"]
    if "net_interest_income" in m and "interest_earning_assets" in m:
        if m["interest_earning_assets"] != 0:
            out["nim"] = m["net_interest_income"] / m["interest_earning_assets"]
    return out


@register_industry("retail")
def _retail(m: Mapping[str, float]) -> dict[str, float]:
    """零售：坪效与库存周转（同店销售同比由调用方提供）。"""
    out: dict[str, float] = {}
    if "revenue" in m and "store_area_sqm" in m and m["store_area_sqm"] != 0:
        out["sales_per_sqm"] = m["revenue"] / m["store_area_sqm"]
    if "cogs" in m and "avg_inventory" in m and m["avg_inventory"] != 0:
        out["inventory_turnover"] = m["cogs"] / m["avg_inventory"]
    if "sssg" in m:
        out["sssg"] = m["sssg"]
    return out


@register_industry("generic")
def _generic(m: Mapping[str, float]) -> dict[str, float]:
    """通用：无专用指标，原样返回空 dict。"""
    return {}


@register_industry("semiconductor")
def _semiconductor(m: Mapping[str, float]) -> dict[str, float]:
    """半导体：研发强度与毛利率。"""
    out: dict[str, float] = {}
    if "r_and_d" in m and "revenue" in m and m["revenue"] != 0:
        out["rd_intensity"] = m["r_and_d"] / m["revenue"]
    if "gross_profit" in m and "revenue" in m and m["revenue"] != 0:
        out["gross_margin"] = m["gross_profit"] / m["revenue"]
    return out


@register_industry("insurance")
def _insurance(m: Mapping[str, float]) -> dict[str, float]:
    """保险：综合成本率与投资收益率。"""
    out: dict[str, float] = {}
    if (
        "claims" in m
        and "expenses" in m
        and "premiums" in m
        and m["premiums"] != 0
    ):
        out["combined_ratio"] = (m["claims"] + m["expenses"]) / m["premiums"]
    if "investment_income" in m and "invested_assets" in m:
        if m["invested_assets"] != 0:
            out["investment_yield"] = m["investment_income"] / m["invested_assets"]
    return out

