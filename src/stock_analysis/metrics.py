"""派生指标计算，公式与 docs/data-and-metrics.md 保持一致。

所有函数都是纯函数：固定输入产生确定输出，便于单元测试与边界测试。
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from statistics import fmean

from .config import Config


def simple_return(p_t: float, p_prev: float) -> float:
    """简单收益率 = P_t / P_(t-1) - 1"""
    if p_prev == 0:
        raise ValueError("上一期价格不能为零")
    return p_t / p_prev - 1.0


def returns_from_prices(prices: Sequence[float]) -> list[float]:
    """由收盘价序列计算日简单收益率序列（长度减一）。"""
    if len(prices) < 2:
        return []
    out: list[float] = []
    for prev, cur in zip(prices, prices[1:]):
        out.append(simple_return(cur, prev))
    return out


def interval_return(p_start: float, p_end: float) -> float:
    """区间收益率 = P_end / P_start - 1"""
    if p_start == 0:
        raise ValueError("区间起始价格不能为零")
    return p_end / p_start - 1.0


def annualized_volatility(
    daily_returns: Iterable[float], trading_days_per_year: int = 252
) -> float:
    """年化波动率 = 日收益率标准差 × sqrt(年交易日数)"""
    rets = list(daily_returns)
    if len(rets) < 2:
        raise ValueError("至少需要两个日收益率才能计算标准差")
    mean = fmean(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(trading_days_per_year)


def drawdown(nav: Sequence[float]) -> list[float]:
    """回撤 = 当前净值 / 历史峰值 - 1（返回与输入等长的序列）"""
    out: list[float] = []
    peak = -math.inf
    for v in nav:
        peak = max(peak, v)
        out.append(v / peak - 1.0 if peak else 0.0)
    return out


def max_drawdown(nav: Sequence[float]) -> float:
    """最大回撤 = 观察期内回撤的最小值（最负值）"""
    dd = drawdown(nav)
    return min(dd) if dd else 0.0


def yoy_growth(current: float, prior_year: float) -> float:
    """同比增长率 = 本期值 / 上年同期值 - 1。

    当期初值为负数或接近零时不应使用普通增长率，调用方应同时给出绝对变化。
    """
    if prior_year == 0:
        raise ValueError("上年同期值不能为零；应改用绝对变化口径")
    return current / prior_year - 1.0


def cagr(begin_value: float, end_value: float, years: float) -> float:
    """复合年增长率 = (期末值 / 期初值)^(1 / 年数) - 1"""
    if begin_value <= 0:
        raise ValueError("期初值必须为正")
    if years <= 0:
        raise ValueError("年数必须为正")
    return (end_value / begin_value) ** (1.0 / years) - 1.0


def margin(numerator: float, revenue: float) -> float:
    """利润率类指标 = 分子 / 营业收入。"""
    if revenue == 0:
        raise ValueError("营业收入不能为零")
    return numerator / revenue


def free_cash_flow(operating_cash_flow: float, capex: float) -> float:
    """自由现金流 = 经营活动现金流 - 资本性支出"""
    return operating_cash_flow - capex


def net_debt(interest_bearing_debt: float, cash: float) -> float:
    """净负债 = 有息负债 - 现金及现金等价物"""
    return interest_bearing_debt - cash


def pe_ratio(price: float, eps: float) -> float:
    """市盈率 = 股价 / 每股收益。负盈利或零 EPS 应标记为不适用，不返回无意义数值。"""
    if eps <= 0:
        raise ValueError("EPS 非正时市盈率不适用，请改用其他口径")
    return price / eps


def sharpe_ratio(
    daily_returns: Sequence[float],
    config: Config | None = None,
) -> float:
    """年化 Sharpe = (年化收益 - 无风险利率) / 年化波动率。

    必须同时披露区间、频率、无风险利率与样本量。
    """
    cfg = config or Config()
    if len(daily_returns) < 2:
        raise ValueError("样本量不足")
    n = len(daily_returns)
    mean_daily = fmean(daily_returns)
    vol_daily = math.sqrt(
        sum((r - mean_daily) ** 2 for r in daily_returns) / (n - 1)
    )
    if vol_daily == 0:
        return math.inf
    annual_return = (1 + mean_daily) ** cfg.trading_days_per_year - 1
    annual_vol = vol_daily * math.sqrt(cfg.trading_days_per_year)
    return (annual_return - cfg.risk_free_rate) / annual_vol

