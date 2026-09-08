"""分析引擎测试：财务趋势、DCF、相对表现、清单与结构化输出（离线）。"""

import json
from datetime import date

import pytest

from stock_analysis.analysis import (
    AnalysisReport,
    Catalyst,
    DcfAssumptions,
    Evidence,
    FinancialTrend,
    Risk,
    alpha,
    beta,
    dcf_enterprise_value,
    dcf_equity_value_per_share,
    dcf_sensitivity,
    financial_trend,
    market_metrics_from_bars,
    project_fcf_stream,
    relative_return,
    scenario_dcf,
)
from stock_analysis.analysis import assert_same_standards, assert_same_currencies
from stock_analysis.models import FinancialMetric, PriceBar, Security


# ---------------------------------------------------------------- 口径守卫


def test_assert_same_standards_ok():
    ms = [
        FinancialMetric("revenue", "2025", 100.0, "CNY", "s", standard="PRC GAAP"),
        FinancialMetric("net_profit", "2025", 10.0, "CNY", "s", standard="PRC GAAP"),
    ]
    assert assert_same_standards(ms) == "PRC GAAP"


def test_assert_same_standards_mixed_raises():
    ms = [
        FinancialMetric("revenue", "2025", 100.0, "CNY", "s", standard="PRC GAAP"),
        FinancialMetric("revenue", "2025", 15.0, "USD", "s", standard="US GAAP"),
    ]
    with pytest.raises(ValueError, match="会计准则混用"):
        assert_same_standards(ms)


def test_assert_same_standards_unknown_ignored():
    ms = [
        FinancialMetric("revenue", "2025", 100.0, "CNY", "s", standard=""),
        FinancialMetric("net_profit", "2025", 10.0, "CNY", "s", standard="IFRS"),
    ]
    assert assert_same_standards(ms) == "IFRS"


def test_assert_same_currencies_mixed_raises():
    ms = [
        FinancialMetric("revenue", "2025", 100.0, "CNY", "s"),
        FinancialMetric("revenue", "2025", 15.0, "USD", "s"),
    ]
    with pytest.raises(ValueError, match="币种混用"):
        assert_same_currencies(ms)


def test_assert_same_currencies_ok():
    ms = [FinancialMetric("revenue", "2025", 100.0, "CNY", "s")]
    assert assert_same_currencies(ms) == "CNY"


# ---------------------------------------------------------------- 财务趋势


def test_financial_trend_cagr_and_yoy():
    trend = financial_trend(
        "revenue",
        ["2023", "2024", "2025"],
        [100.0, 120.0, 144.0],
        currency="CNY",
    )
    assert trend.yoy_changes == pytest.approx([0.2, 0.2])
    assert trend.cagr == pytest.approx(0.2)  # (144/100)^(1/2)-1


def test_financial_trend_keeps_missing():
    trend = financial_trend("revenue", ["2023", "2024"], [100.0, None])
    assert trend.values[1] is None
    assert trend.yoy_changes == [None]
    assert trend.cagr is None


def test_financial_trend_zero_prior_yields_none():
    trend = financial_trend("revenue", ["2023", "2024"], [0.0, 100.0])
    assert trend.yoy_changes == [None]


def test_financial_trend_length_mismatch_raises():
    with pytest.raises(ValueError):
        financial_trend("revenue", ["2023"], [100.0, 200.0])


# ---------------------------------------------------------------- DCF


def test_project_fcf_stream():
    stream = project_fcf_stream(100.0, 0.05, 3)
    assert stream == pytest.approx([105.0, 110.25, 115.7625])


def test_project_fcf_stream_invalid():
    with pytest.raises(ValueError):
        project_fcf_stream(0.0, 0.05, 3)
    with pytest.raises(ValueError):
        project_fcf_stream(100.0, 0.05, 0)


def test_dcf_enterprise_value_matches_manual():
    # 手工计算：base=100, g=0, r=0.1, g_term=0, 1 年
    # FCF1 = 100, PV = 100/1.1 = 90.909
    # terminal = 100/(0.1) = 1000, PV = 1000/1.1 = 909.09
    a = DcfAssumptions(name="flat", fcf_growth=0.0, discount_rate=0.1, terminal_growth=0.0)
    ev = dcf_enterprise_value(100.0, a, years=1)
    assert ev == pytest.approx(90.90909 + 909.0909, rel=1e-4)


def test_dcf_requires_discount_above_terminal():
    a = DcfAssumptions(
        name="bad", fcf_growth=0.03, discount_rate=0.03, terminal_growth=0.05
    )
    with pytest.raises(ValueError, match="折现率"):
        dcf_enterprise_value(100.0, a)


def test_dcf_equity_value_per_share():
    ev = dcf_enterprise_value(
        100.0,
        DcfAssumptions(name="base", fcf_growth=0.05, discount_rate=0.1, terminal_growth=0.02),
    )
    per_share = dcf_equity_value_per_share(ev, net_debt=50.0, shares_outstanding=10.0)
    assert per_share == pytest.approx((ev - 50.0) / 10.0)


def test_dcf_equity_value_per_share_invalid_shares():
    with pytest.raises(ValueError):
        dcf_equity_value_per_share(1000.0, 0.0, 0.0)


def test_scenario_dcf_orders_scenarios():
    scenarios = [
        DcfAssumptions(name="bear", fcf_growth=0.0, discount_rate=0.12, terminal_growth=0.01),
        DcfAssumptions(name="base", fcf_growth=0.05, discount_rate=0.1, terminal_growth=0.02),
        DcfAssumptions(name="bull", fcf_growth=0.10, discount_rate=0.09, terminal_growth=0.03),
    ]
    values = scenario_dcf(100.0, scenarios)
    assert set(values) == {"bear", "base", "bull"}
    assert values["bear"] < values["base"] < values["bull"]


def test_dcf_sensitivity_returns_grid():
    out = dcf_sensitivity(100.0, [0.0, 0.05], [0.09, 0.1], years=5)
    assert len(out) == 4
    # 折现率相同下，增长率越高价值越高
    assert out[(0.05, 0.1)] > out[(0.0, 0.1)]


# ---------------------------------------------------------------- 相对表现


def test_relative_return():
    assert relative_return(0.2, 0.05) == pytest.approx(0.15)


def test_beta_known_value():
    # 标的与市场完全同向 -> beta 应为 1
    rets = [0.01, -0.02, 0.03, -0.01, 0.02]
    assert beta(rets, rets) == pytest.approx(1.0, abs=1e-9)


def test_beta_length_mismatch_raises():
    with pytest.raises(ValueError):
        beta([0.01, 0.02], [0.01])


def test_beta_zero_variance_raises():
    with pytest.raises(ValueError):
        beta([0.01, 0.02, 0.03], [0.0, 0.0, 0.0])


def test_alpha_with_beta_one_and_no_alpha():
    rets = [0.01, -0.02, 0.03]
    assert alpha(rets, rets, risk_free_rate=0.0) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------- 市场指标


def _bar(d: str, close: float) -> PriceBar:
    return PriceBar(
        date=date.fromisoformat(d),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
    )


def test_market_metrics_from_bars():
    bars = [_bar("2026-01-05", 100.0), _bar("2026-01-06", 110.0), _bar("2026-01-07", 99.0)]
    m = market_metrics_from_bars(bars)
    assert m.interval_return == pytest.approx(-0.01)
    assert m.annualized_volatility is not None
    assert m.max_drawdown == pytest.approx(-0.1)


def test_market_metrics_with_benchmark():
    bars = [_bar("2026-01-05", 100.0), _bar("2026-01-06", 105.0), _bar("2026-01-07", 103.0)]
    # 基准收益 = 标的收益 -> beta=1, alpha=0, relative=0
    bench = [0.05, 103 / 105 - 1]
    m = market_metrics_from_bars(bars, benchmark_returns=bench)
    assert m.beta == pytest.approx(1.0, abs=1e-9)
    assert m.alpha == pytest.approx(0.0, abs=1e-9)
    assert m.relative_return == pytest.approx(0.0, abs=1e-9)


def test_market_metrics_benchmark_length_mismatch():
    bars = [_bar("2026-01-05", 100.0), _bar("2026-01-06", 105.0), _bar("2026-01-07", 103.0)]
    with pytest.raises(ValueError):
        market_metrics_from_bars(bars, benchmark_returns=[0.05])


# ---------------------------------------------------------------- 结构化输出


def test_report_to_json_roundtrip():
    report = AnalysisReport(
        security=Security(ticker="TEST", market="CN", currency="CNY"),
        as_of="2026-09-04",
        data_cutoff="2026-09-03",
        thesis="测试命题",
        catalysts=[Catalyst("财报", "2026Q4", "营收增速", "利多")],
        risks=[Risk("需求下滑", "中", "高", "订单", "分散客户")],
        evidences=[Evidence("年报", "公司", "2026-03", "2026-09-04", "https://x", "营收")],
    )
    data = json.loads(report.to_json())
    assert data["security"]["ticker"] == "TEST"
    assert data["thesis"] == "测试命题"
    assert data["catalysts"][0]["description"] == "财报"
    assert data["risks"][0]["description"] == "需求下滑"


def test_report_to_markdown_contains_sections():
    report = AnalysisReport(
        security=Security(ticker="TEST", market="CN", currency="CNY", name="测试公司"),
        as_of="2026-09-04",
        data_cutoff="2026-09-03",
        financial_trends=[
            financial_trend("revenue", ["2024", "2025"], [100.0, 120.0], "CNY")
        ],
        scenario_values={"base": 1234.0},
        catalysts=[Catalyst("财报", "2026Q4", "营收增速", "利多")],
        risks=[Risk("需求下滑", "中", "高", "订单", "分散客户")],
        assumptions=["折现率 10%"],
        data_gaps=["缺少分地区收入"],
        evidences=[Evidence("年报", "公司", "2026-03", "2026-09-04", "https://x", "营收")],
    )
    md = report.to_markdown()
    assert "# 测试公司 (CN:TEST) 研究报告" in md
    assert "## 4. 财务趋势" in md
    assert "CAGR：20.0%" in md
    assert "## 5. 估值情景" in md
    assert "## 7. 催化剂" in md
    assert "## 8. 风险与反证" in md
    assert "## 11. 来源" in md
    assert "## 12. 免责声明" in md


def test_report_to_markdown_renders_market_metrics():
    from stock_analysis.analysis import MarketMetrics

    report = AnalysisReport(
        security=Security(ticker="TEST", market="CN", currency="CNY"),
        as_of="2026-09-04",
        data_cutoff="2026-09-03",
        market=MarketMetrics(
            interval_return=0.2,
            annualized_volatility=0.3,
            max_drawdown=-0.1,
            sharpe=0.5,
        ),
    )
    md = report.to_markdown()
    assert "## 6. 市场与技术观察" in md
    assert "| 区间收益率 | 20.00% |" in md
    assert "| 年化波动率 | 30.00% |" in md
    assert "| 最大回撤 | -10.00% |" in md
    assert "| Sharpe | 0.50 |" in md


def test_report_to_markdown_no_market_section_when_empty():
    report = AnalysisReport(
        security=Security(ticker="TEST", market="CN", currency="CNY"),
        as_of="2026-09-04",
        data_cutoff="2026-09-03",
    )
    md = report.to_markdown()
    assert "市场与技术观察" not in md


def test_financial_trend_is_dataclass():
    t = financial_trend("x", ["2023"], [1.0])
    assert isinstance(t, FinancialTrend)

