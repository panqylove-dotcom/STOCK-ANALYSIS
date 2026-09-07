"""行业插件框架测试：注册、分发与内置行业插件。"""

import pytest

from stock_analysis.industry import (
    available_industries,
    compute_industry_metrics,
    register_industry,
)


def test_builtin_industries_registered():
    inds = available_industries()
    assert {
        "software",
        "bank",
        "retail",
        "generic",
        "semiconductor",
        "insurance",
    } <= set(inds)


def test_software_rule_of_40():
    out = compute_industry_metrics(
        "software", {"revenue_growth": 0.25, "fcf_margin": 0.18}
    )
    assert out["rule_of_40"] == pytest.approx(0.43)


def test_software_arr_growth():
    out = compute_industry_metrics("software", {"arr": 120.0, "prior_arr": 100.0})
    assert out["arr_growth"] == pytest.approx(0.2)


def test_bank_roe_and_nim():
    out = compute_industry_metrics(
        "bank",
        {
            "net_profit": 20.0,
            "equity": 200.0,
            "net_interest_income": 30.0,
            "interest_earning_assets": 1500.0,
        },
    )
    assert out["roe"] == pytest.approx(0.1)
    assert out["nim"] == pytest.approx(0.02)


def test_retail_metrics():
    out = compute_industry_metrics(
        "retail",
        {
            "revenue": 1000.0,
            "store_area_sqm": 500.0,
            "cogs": 600.0,
            "avg_inventory": 150.0,
            "sssg": 0.03,
        },
    )
    assert out["sales_per_sqm"] == pytest.approx(2.0)
    assert out["inventory_turnover"] == pytest.approx(4.0)
    assert out["sssg"] == pytest.approx(0.03)


def test_missing_inputs_skip_metric():
    out = compute_industry_metrics("bank", {"net_profit": 10.0})
    assert out == {}


def test_semiconductor_metrics():
    out = compute_industry_metrics(
        "semiconductor",
        {"r_and_d": 30.0, "gross_profit": 80.0, "revenue": 100.0},
    )
    assert out["rd_intensity"] == pytest.approx(0.3)
    assert out["gross_margin"] == pytest.approx(0.8)


def test_insurance_metrics():
    out = compute_industry_metrics(
        "insurance",
        {
            "claims": 60.0,
            "expenses": 25.0,
            "premiums": 100.0,
            "investment_income": 9.0,
            "invested_assets": 300.0,
        },
    )
    assert out["combined_ratio"] == pytest.approx(0.85)
    assert out["investment_yield"] == pytest.approx(0.03)


def test_unknown_industry_raises():
    with pytest.raises(ValueError, match="未知行业"):
        compute_industry_metrics("mining", {})


def test_duplicate_registration_raises():
    with pytest.raises(ValueError, match="已注册"):

        @register_industry("software")
        def _dup(m):  # pragma: no cover
            return {}

