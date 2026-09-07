"""数据清洗测试：校验、去重、缺失值填充、重采样。"""

from datetime import date

import pytest

from stock_analysis.data.cleaning import (
    dedupe_bars,
    fill_missing_with_previous_close,
    resample_daily,
    validate_bars,
)
from stock_analysis.models import PriceBar


def _bar(d: str, close: float, **kw) -> PriceBar:
    return PriceBar(
        date=date.fromisoformat(d),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
        **kw,
    )


def test_validate_bars_ok():
    bars = [_bar("2026-01-05", 10), _bar("2026-01-06", 11)]
    assert validate_bars(bars) == bars


def test_validate_bars_non_monotonic_raises():
    bars = [_bar("2026-01-06", 11), _bar("2026-01-05", 10)]
    with pytest.raises(ValueError, match="非单调"):
        validate_bars(bars)


def test_validate_bars_ohlc_inconsistent_raises():
    bar = PriceBar(date(2026, 1, 5), open=10, high=9, low=8, close=10, volume=1)
    with pytest.raises(ValueError, match="OHLC"):
        validate_bars([bar])


def test_validate_bars_negative_price_raises():
    bar = PriceBar(date(2026, 1, 5), open=-1, high=1, low=-1, close=1, volume=1)
    with pytest.raises(ValueError, match="价格为负"):
        validate_bars([bar])


def test_dedupe_bars_keeps_last():
    bars = [
        _bar("2026-01-05", 10),
        _bar("2026-01-05", 12),  # 同日重复，取最后
        _bar("2026-01-06", 11),
    ]
    out = dedupe_bars(bars)
    assert len(out) == 2
    assert out[0].close == 12


def test_fill_missing_with_previous_close():
    bars = [_bar("2026-01-05", 10), _bar("2026-01-07", 11)]  # 中间 01-06 缺失
    out = fill_missing_with_previous_close(bars, date(2026, 1, 5), date(2026, 1, 7))
    dates = [b.date for b in out]
    assert date(2026, 1, 6) in dates
    filled = next(b for b in out if b.date == date(2026, 1, 6))
    assert filled.close == 10  # 用上一交易日收盘价填充
    assert filled.adjusted is True


def test_fill_missing_before_first_raises():
    bars = [_bar("2026-01-06", 11)]
    with pytest.raises(ValueError, match="之前无数据"):
        fill_missing_with_previous_close(bars, date(2026, 1, 5), date(2026, 1, 6))


def test_resample_daily_only():
    bars = [_bar("2026-01-05", 10)]
    assert resample_daily(bars, "D") == bars
    with pytest.raises(NotImplementedError):
        resample_daily(bars, "W")

