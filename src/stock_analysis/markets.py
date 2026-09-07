"""多市场/多币种支持：市场注册表、年交易日数、时区与汇率换算。

对应 docs/roadmap.md 阶段 5。口径要求（docs/data-and-metrics.md）：
- 年交易日数按市场设置，不能盲目固定为 252；
- 跨币种比较前必须完成标准化，汇率必须记录来源与日期。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MarketSpec:
    """单个市场的标准化参数。"""

    code: str
    name: str
    currency: str
    trading_days_per_year: int
    timezone: str


#: 内置市场注册表（数值为常用近似，接入真实交易日历后应替换）。
KNOWN_MARKETS: dict[str, MarketSpec] = {
    "CN": MarketSpec("CN", "中国 A 股", "CNY", 242, "Asia/Shanghai"),
    "HKEX": MarketSpec("HKEX", "港股", "HKD", 245, "Asia/Hong_Kong"),
    "NASDAQ": MarketSpec("NASDAQ", "美国纳斯达克", "USD", 252, "America/New_York"),
    "NYSE": MarketSpec("NYSE", "美国纽约", "USD", 252, "America/New_York"),
    "LSE": MarketSpec("LSE", "伦敦", "GBP", 251, "Europe/London"),
    "TSE": MarketSpec("TSE", "东京", "JPY", 242, "Asia/Tokyo"),
}


def get_market(code: str) -> MarketSpec:
    """按市场代码获取市场参数，未知市场抛错（不允许静默默认）。"""
    try:
        return KNOWN_MARKETS[code]
    except KeyError:
        raise ValueError(
            f"未知市场: {code}；已知市场: {sorted(KNOWN_MARKETS)}"
        ) from None


@dataclass(frozen=True)
class FxRate:
    """汇率：记录来源与日期，保证可追溯。"""

    base: str
    quote: str
    rate: float
    as_of: date
    source: str


def convert(amount: float, fx: FxRate, *, from_currency: str, to_currency: str) -> float:
    """按给定汇率把金额从 from_currency 换算到 to_currency。

    同币种直接返回；方向不匹配时自动取倒数；未知方向抛错。
    """
    if amount is None:
        raise ValueError("金额不能为 None")
    if from_currency == to_currency:
        return amount
    if fx.rate <= 0:
        raise ValueError("汇率必须为正")
    if fx.base == from_currency and fx.quote == to_currency:
        return amount * fx.rate
    if fx.base == to_currency and fx.quote == from_currency:
        return amount / fx.rate
    raise ValueError(
        f"汇率方向不匹配: {fx.base}->{fx.quote} 无法换算 {from_currency}->{to_currency}"
    )

