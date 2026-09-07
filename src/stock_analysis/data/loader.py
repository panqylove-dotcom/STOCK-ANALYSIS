"""数据加载器：本地 CSV -> Normalized PriceBar，并记录来源与新鲜度。

真实行情源（阶段 2 后续）应实现同样的 load() 接口并登记来源，
保证派生指标可追溯到原始数据与时间。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..models import PriceBar, Security
from .cleaning import validate_bars


@dataclass(frozen=True)
class SourceRecord:
    """来源记录：名称、检索/访问时间、数据版本、许可与备注。

    license_name 仅做人读说明；机器可检查的许可见
    stock_analysis.audit.DataLicense。
    """

    name: str
    accessed_at: str
    version: str
    license_name: str = "personal-use only"
    note: str = ""


@dataclass
class LoadResult:
    """一次加载的结果：归一化数据 + 来源记录。"""

    bars: list[PriceBar]
    security: Security
    source: SourceRecord


class CsvPriceLoader:
    """从本地 CSV 读取 OHLCV 数据（列: date,open,high,low,close,volume）。"""

    def __init__(
        self,
        *,
        market: str = "CN",
        currency: str = "CNY",
        license_name: str = "personal-use only",
    ) -> None:
        self.market = market
        self.currency = currency
        self.license_name = license_name

    def load(self, path: str | Path, *, ticker: str) -> LoadResult:
        p = Path(path)
        bars: list[PriceBar] = []
        with p.open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                bars.append(
                    PriceBar(
                        date=date.fromisoformat(row["date"].strip()),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                        adjusted=False,
                    )
                )
        if not bars:
            raise ValueError(f"CSV 无数据: {p}")
        validated = validate_bars(bars)
        security = Security(
            ticker=ticker, market=self.market, currency=self.currency
        )
        source = SourceRecord(
            name=f"local-csv:{p.name}",
            accessed_at=str(date.today()),
            version=p.stat().st_mtime_ns.__str__(),
            license_name=self.license_name,
            note="raw 文件未经改写",
        )
        return LoadResult(bars=validated, security=security, source=source)

