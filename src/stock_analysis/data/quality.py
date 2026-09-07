"""数据质量与新鲜度检查（docs/data-and-metrics.md「数据质量检查」）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable

from ..models import PriceBar


@dataclass
class DataQualityReport:
    """质量检查结果。check 为 (检查名, 是否通过, 说明) 列表。"""

    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    passed: bool = True

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append((name, ok, detail))
        if not ok:
            self.passed = False

    def summary(self) -> str:
        lines = [f"{name}: {'通过' if ok else '失败'} {detail}" for name, ok, detail in self.checks]
        return "\n".join(lines) or "(无检查项)"


Check = Callable[[list[PriceBar], DataQualityReport], None]


def _check_ordering(bars: list[PriceBar], report: DataQualityReport) -> None:
    dates = [b.date for b in bars]
    ok = all(a < b for a, b in zip(dates, dates[1:]))
    report.add("日期严格递增", ok, f"{len(bars)} 条记录")


def _check_no_missing(bars: list[PriceBar], report: DataQualityReport) -> None:
    missing = sum(1 for b in bars if b.close is None)
    report.add("无缺失收盘价", missing == 0, f"缺失 {missing} 条")


def _check_positive_close(bars: list[PriceBar], report: DataQualityReport) -> None:
    bad = [b for b in bars if b.close is not None and b.close <= 0]
    report.add("收盘价为正", len(bad) == 0, f"非正收盘价 {len(bad)} 条")


def _check_ohlc_consistency(bars: list[PriceBar], report: DataQualityReport) -> None:
    bad = [
        b
        for b in bars
        if not (b.low <= min(b.open, b.close) <= max(b.open, b.close) <= b.high)
    ]
    report.add("OHLC 一致", len(bad) == 0, f"异常 {len(bad)} 条")


def _check_volume_nonnegative(bars: list[PriceBar], report: DataQualityReport) -> None:
    bad = [b for b in bars if b.volume < 0]
    report.add("成交量非负", len(bad) == 0, f"负成交量 {len(bad)} 条")


def _check_freshness(
    bars: list[PriceBar],
    report: DataQualityReport,
    *,
    as_of: date | None = None,
    max_lag_days: int = 10,
) -> None:
    if not bars:
        report.add("数据新鲜度", False, "无数据")
        return
    latest = max(b.date for b in bars)
    today = as_of or date.today()
    lag = (today - latest).days
    report.add(
        "数据新鲜度",
        lag <= max_lag_days,
        f"最新数据 {latest}，滞后 {lag} 天（阈值 {max_lag_days} 天）",
    )


def run_quality_checks(
    bars: list[PriceBar],
    *,
    as_of: date | None = None,
    max_lag_days: int = 10,
    freshness: bool = True,
) -> DataQualityReport:
    """执行全部质量检查。"""
    report = DataQualityReport()
    _check_ordering(bars, report)
    _check_no_missing(bars, report)
    _check_positive_close(bars, report)
    _check_ohlc_consistency(bars, report)
    _check_volume_nonnegative(bars, report)
    if freshness:
        _check_freshness(bars, report, as_of=as_of, max_lag_days=max_lag_days)
    return report


def check_quality(bars: list[PriceBar], **kwargs) -> DataQualityReport:
    """兼容别名，便于调用方统一入口。"""
    return run_quality_checks(bars, **kwargs)


def utc_now() -> datetime:
    """UTC 当前时间（便于记录数据访问/计算时间，测试可替换）。"""
    return datetime.now(timezone.utc)

