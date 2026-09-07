"""数据质量与新鲜度检查测试。"""

from datetime import date, timedelta

from stock_analysis.data.quality import run_quality_checks
from stock_analysis.models import PriceBar


def _bar(d: date, close: float, volume: float = 1000.0) -> PriceBar:
    return PriceBar(d, open=close, high=close, low=close, close=close, volume=volume)


def test_quality_passes_for_good_data():
    today = date(2026, 6, 1)
    bars = [_bar(today - timedelta(days=i), 10 + i) for i in range(5, 0, -1)]
    report = run_quality_checks(bars, as_of=today, max_lag_days=10)
    assert report.passed is True
    assert len(report.checks) >= 5


def test_quality_flags_stale_data():
    today = date(2026, 6, 1)
    bars = [_bar(date(2026, 1, 2), 10)]
    report = run_quality_checks(bars, as_of=today, max_lag_days=10)
    assert report.passed is False
    stale = [c for c in report.checks if c[0] == "数据新鲜度"]
    assert stale and stale[0][1] is False


def test_quality_flags_negative_volume():
    today = date(2026, 6, 1)
    bars = [
        _bar(today - timedelta(days=2), 10),
        _bar(today - timedelta(days=1), 11, volume=-5),
    ]
    report = run_quality_checks(bars, as_of=today)
    assert report.passed is False
    assert any(c[0] == "成交量非负" and not c[1] for c in report.checks)


def test_quality_flags_duplicate_dates():
    d = date(2026, 6, 1)
    bars = [_bar(d, 10), _bar(d, 11)]
    report = run_quality_checks(bars, as_of=d)
    assert report.passed is False
    assert any(c[0] == "日期严格递增" and not c[1] for c in report.checks)


def test_quality_freshness_disabled():
    bars = [_bar(date(2026, 1, 2), 10)]
    report = run_quality_checks(bars, as_of=date(2026, 6, 1), freshness=False)
    assert report.passed is True

