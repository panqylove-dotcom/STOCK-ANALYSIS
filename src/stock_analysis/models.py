"""统一证券、交易日、价格与财务字段模型（docs/roadmap.md 阶段 2 的先行简化版）。

阶段 1 目标：先固定字段命名与类型，保证测试不依赖在线服务；
后续再接入真实行情源并把数据映射到这些模型。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Security:
    """证券标识。市场与币种必须显式给出，禁止默认。"""

    ticker: str
    market: str
    currency: str
    name: str = ""


@dataclass(frozen=True)
class PriceBar:
    """单日 OHLCV 数据。收盘价为当日最后成交价，未复权/复权状态由数据层标注。"""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    adjusted: bool = False


@dataclass(frozen=True)
class FinancialMetric:
    """带来源与口径的财务指标。事实、计算、假设必须区分记录。

    standard 登记会计准则（如 PRC GAAP / US GAAP / IFRS）。
    跨公司/跨期比较前必须统一准则（docs/data-and-metrics.md），
    混用应用 analysis.assert_same_standards 拦截。
    """

    metric: str
    period: str
    value: float | None
    currency: str
    source: str
    standard: str = ""
    note: str = ""

