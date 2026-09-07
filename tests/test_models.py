"""数据模型测试：字段类型与默认约束。"""

from datetime import date

from stock_analysis.models import FinancialMetric, PriceBar, Security


def test_security_fields():
    sec = Security(ticker="AAPL", market="NASDAQ", currency="USD", name="Apple")
    assert sec.ticker == "AAPL"
    assert sec.market == "NASDAQ"
    assert sec.currency == "USD"


def test_price_bar_defaults():
    bar = PriceBar(date(2026, 1, 2), 100.0, 105.0, 99.0, 102.0, 1_000_000)
    assert bar.adjusted is False


def test_financial_metric_allows_none_value():
    m = FinancialMetric(
        metric="net_debt",
        period="2025Q4",
        value=None,
        currency="CNY",
        source="sample",
    )
    assert m.value is None  # 缺失值保留为 None，不默认填零

