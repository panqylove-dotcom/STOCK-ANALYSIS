"""组合暴露与相关性分析测试。"""

import pytest

from stock_analysis.models import Security
from stock_analysis.portfolio import (
    Position,
    correlation,
    correlation_matrix,
    effective_number_of_holdings,
    hhi,
    max_position_exposure,
    portfolio_exposure_summary,
    weights,
)


def _sec(t: str) -> Security:
    return Security(ticker=t, market="CN", currency="CNY")


def _positions():
    return [
        Position(_sec("A"), 600.0),
        Position(_sec("B"), 300.0),
        Position(_sec("C"), 100.0),
    ]


def test_weights_sum_to_one():
    w = weights(_positions())
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["A"] == pytest.approx(0.6)


def test_weights_empty_raises():
    with pytest.raises(ValueError):
        weights([])


def test_weights_negative_total_raises():
    with pytest.raises(ValueError):
        weights([Position(_sec("A"), -100.0)])


def test_hhi_and_effective_n_equal_weights():
    w = {"A": 0.5, "B": 0.5}
    assert hhi(w) == pytest.approx(0.5)
    assert effective_number_of_holdings(w) == pytest.approx(2.0)


def test_hhi_concentrated():
    w = {"A": 1.0}
    assert hhi(w) == pytest.approx(1.0)
    assert effective_number_of_holdings(w) == pytest.approx(1.0)


def test_max_position_exposure():
    w = weights(_positions())
    ticker, value = max_position_exposure(w)
    assert ticker == "A"
    assert value == pytest.approx(0.6)


def test_correlation_perfect_positive():
    x = [0.01, 0.02, -0.01, 0.03]
    assert correlation(x, [v * 2 for v in x]) == pytest.approx(1.0, abs=1e-9)


def test_correlation_length_mismatch_raises():
    with pytest.raises(ValueError):
        correlation([0.01, 0.02], [0.01])


def test_correlation_zero_variance_raises():
    with pytest.raises(ValueError):
        correlation([0.01, 0.02, 0.03], [0.0, 0.0, 0.0])


def test_correlation_matrix_symmetric_pairs():
    rets = {
        "A": [0.01, 0.02, -0.01, 0.03],
        "B": [0.02, 0.01, 0.00, 0.01],
        "C": [-0.01, 0.03, 0.02, -0.02],
    }
    m = correlation_matrix(rets)
    assert m[("A", "A")] == 1.0
    assert ("A", "B") in m and ("B", "A") not in m
    assert -1.0 <= m[("A", "B")] <= 1.0


def test_correlation_matrix_length_consistency():
    rets = {"A": [0.01, 0.02], "B": [0.01, 0.02, 0.03]}
    with pytest.raises(ValueError, match="长度"):
        correlation_matrix(rets)


def test_portfolio_exposure_summary():
    s = portfolio_exposure_summary(_positions())
    assert s["total_market_value"] == pytest.approx(1000.0)
    assert s["n_holdings"] == 3
    assert s["max_weight_ticker"] == "A"
    # 0.6^2+0.3^2+0.1^2 = 0.46
    assert s["hhi"] == pytest.approx(0.46)

