"""组合暴露与相关性分析（docs/roadmap.md 阶段 5）。

纯函数实现：固定输入产生确定输出，不依赖第三方数值库。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean

from .models import Security


@dataclass(frozen=True)
class Position:
    """组合持仓：证券 + 市值（同一币种）。"""

    security: Security
    market_value: float


def weights(positions: Sequence[Position]) -> dict[str, float]:
    """按市值计算权重 {ticker: weight}；总市值必须为正。"""
    if not positions:
        raise ValueError("组合为空")
    total = sum(p.market_value for p in positions)
    if total <= 0:
        raise ValueError("总市值必须为正")
    return {p.security.ticker: p.market_value / total for p in positions}


def hhi(weights: Mapping[str, float]) -> float:
    """Herfindahl-Hirschman 集中度指数：权重平方和（越接近 1 越集中）。"""
    if not weights:
        raise ValueError("权重为空")
    return sum(w * w for w in weights.values())


def effective_number_of_holdings(weights: Mapping[str, float]) -> float:
    """有效持仓数 = 1 / HHI。"""
    return 1.0 / hhi(weights)


def max_position_exposure(weights: Mapping[str, float]) -> tuple[str, float]:
    """最大单一持仓暴露：返回 (ticker, weight)。"""
    if not weights:
        raise ValueError("权重为空")
    ticker = max(weights, key=weights.get)
    return ticker, weights[ticker]


def correlation(x: Sequence[float], y: Sequence[float]) -> float:
    """Pearson 相关系数。样本量 >= 2 且双方方差非零。"""
    if len(x) != len(y):
        raise ValueError("两个序列长度必须一致")
    if len(x) < 2:
        raise ValueError("样本量不足")
    mx, my = fmean(x), fmean(y)
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y)) / (len(x) - 1)
    vx = sum((a - mx) ** 2 for a in x) / (len(x) - 1)
    vy = sum((b - my) ** 2 for b in y) / (len(y) - 1)
    if vx == 0 or vy == 0:
        raise ValueError("序列方差为零，无法计算相关系数")
    return cov / math.sqrt(vx * vy)


def correlation_matrix(
    returns_by_ticker: Mapping[str, Sequence[float]],
) -> dict[tuple[str, str], float]:
    """两两相关系数矩阵 { (a,b): corr }，只存 a<=b 的去重对（对角线为 1）。"""
    tickers = sorted(returns_by_ticker)
    if len(tickers) < 2:
        raise ValueError("至少需要两个标的")
    lengths = {t: len(returns_by_ticker[t]) for t in tickers}
    if len(set(lengths.values())) != 1:
        raise ValueError("所有标的的收益率序列长度必须一致")
    out: dict[tuple[str, str], float] = {}
    for i, a in enumerate(tickers):
        out[(a, a)] = 1.0
        for b in tickers[i + 1:]:
            c = correlation(returns_by_ticker[a], returns_by_ticker[b])
            out[(a, b)] = c
    return out


def portfolio_exposure_summary(
    positions: Sequence[Position],
) -> dict[str, float | int]:
    """组合暴露摘要：总市值、持仓数、HHI、有效持仓数、最大单一暴露。"""
    w = weights(positions)
    top_ticker, top_w = max_position_exposure(w)
    return {
        "total_market_value": sum(p.market_value for p in positions),
        "n_holdings": len(positions),
        "hhi": hhi(w),
        "effective_n": effective_number_of_holdings(w),
        "max_weight": top_w,
        "max_weight_ticker": top_ticker,
    }

