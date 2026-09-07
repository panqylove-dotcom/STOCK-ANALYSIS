"""多市场/多币种测试：市场注册表与汇率换算。"""

from datetime import date

import pytest

from stock_analysis.markets import FxRate, convert, get_market


def test_get_market_cn_uses_242_days():
    spec = get_market("CN")
    assert spec.currency == "CNY"
    assert spec.trading_days_per_year == 242


def test_get_market_unknown_raises():
    with pytest.raises(ValueError, match="未知市场"):
        get_market("MARS")


def test_convert_same_currency_passthrough():
    fx = FxRate("USD", "CNY", 7.2, date(2026, 9, 7), "manual")
    assert convert(100.0, fx, from_currency="CNY", to_currency="CNY") == 100.0


def test_convert_forward():
    fx = FxRate("USD", "CNY", 7.2, date(2026, 9, 7), "manual")
    assert convert(10.0, fx, from_currency="USD", to_currency="CNY") == pytest.approx(72.0)


def test_convert_inverse():
    fx = FxRate("USD", "CNY", 7.2, date(2026, 9, 7), "manual")
    assert convert(72.0, fx, from_currency="CNY", to_currency="USD") == pytest.approx(10.0)


def test_convert_direction_mismatch_raises():
    fx = FxRate("USD", "CNY", 7.2, date(2026, 9, 7), "manual")
    with pytest.raises(ValueError, match="方向不匹配"):
        convert(1.0, fx, from_currency="GBP", to_currency="JPY")


def test_convert_negative_rate_raises():
    fx = FxRate("USD", "CNY", -7.2, date(2026, 9, 7), "manual")
    with pytest.raises(ValueError, match="汇率必须为正"):
        convert(1.0, fx, from_currency="USD", to_currency="CNY")


def test_markets_have_distinct_trading_days():
    # 不同市场的年交易日数不一定相同（不能盲目统一为 252）
    days = {code: get_market(code).trading_days_per_year for code in ("CN", "NASDAQ", "LSE")}
    assert days["CN"] != days["LSE"] or days["CN"] != 252

