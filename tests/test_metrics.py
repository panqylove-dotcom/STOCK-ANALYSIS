"""派生指标公式测试（与 docs/data-and-metrics.md 口径一致，纯本地无网络）。"""

import math

import pytest

from stock_analysis.config import Config
from stock_analysis.metrics import (
    annualized_volatility,
    cagr,
    drawdown,
    free_cash_flow,
    interval_return,
    margin,
    max_drawdown,
    net_debt,
    pe_ratio,
    returns_from_prices,
    sharpe_ratio,
    simple_return,
    yoy_growth,
)


def test_simple_return():
    assert simple_return(110, 100) == pytest.approx(0.1)
    assert simple_return(95, 100) == pytest.approx(-0.05)


def test_simple_return_zero_prev_raises():
    with pytest.raises(ValueError):
        simple_return(10, 0)


def test_returns_from_prices():
    rets = returns_from_prices([100, 110, 121])
    assert rets == pytest.approx([0.1, 0.1])


def test_returns_from_prices_short_input():
    assert returns_from_prices([100]) == []
    assert returns_from_prices([]) == []


def test_interval_return():
    assert interval_return(100, 120) == pytest.approx(0.2)


def test_annualized_volatility_constant_returns():
    # 恒定日收益 -> 日标准差为 0 -> 年化波动率为 0
    assert annualized_volatility([0.01, 0.01, 0.01], 252) == pytest.approx(0.0)


def test_annualized_volatility_too_few():
    with pytest.raises(ValueError):
        annualized_volatility([0.01])


def test_annualized_volatility_uses_trading_days():
    rets = [0.01, -0.01, 0.005, -0.005]
    v252 = annualized_volatility(rets, 252)
    v244 = annualized_volatility(rets, 244)
    # 年交易日数越大，年化波动率越大
    assert v252 > v244


def test_drawdown_and_max_drawdown():
    nav = [100, 120, 90, 110]
    dd = drawdown(nav)
    assert dd[0] == 0.0
    assert dd[1] == 0.0  # 创新高
    assert dd[2] == pytest.approx(90 / 120 - 1)  # -25%
    assert max_drawdown(nav) == pytest.approx(-0.25)


def test_max_drawdown_empty():
    assert max_drawdown([]) == 0.0


def test_yoy_growth():
    assert yoy_growth(120, 100) == pytest.approx(0.2)


def test_yoy_growth_zero_prior_raises():
    with pytest.raises(ValueError):
        yoy_growth(100, 0)


def test_cagr():
    # 100 -> 121 三年，CAGR = (1.21)^(1/3)-1
    assert cagr(100, 121, 3) == pytest.approx(1.21 ** (1 / 3) - 1)


def test_cagr_invalid_input():
    with pytest.raises(ValueError):
        cagr(0, 121, 3)
    with pytest.raises(ValueError):
        cagr(100, 121, 0)


def test_margin():
    assert margin(30, 100) == pytest.approx(0.3)
    with pytest.raises(ValueError):
        margin(30, 0)


def test_free_cash_flow():
    assert free_cash_flow(100, 30) == pytest.approx(70)


def test_net_debt():
    assert net_debt(500, 120) == pytest.approx(380)
    # 净现金时净负债为负
    assert net_debt(100, 300) == pytest.approx(-200)


def test_pe_ratio():
    assert pe_ratio(50, 2) == pytest.approx(25)
    with pytest.raises(ValueError):
        pe_ratio(50, 0)
    with pytest.raises(ValueError):
        pe_ratio(50, -1)


def test_sharpe_ratio_zero_vol_is_inf():
    assert sharpe_ratio([0.01, 0.01, 0.01]) == math.inf


def test_sharpe_ratio_matches_manual_calculation():
    cfg = Config(trading_days_per_year=252, risk_free_rate=0.0)
    rets = [0.01, -0.005, 0.008, -0.003]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    vol = math.sqrt(var) * math.sqrt(252)
    annual = (1 + mean) ** 252 - 1
    assert sharpe_ratio(rets, cfg) == pytest.approx(annual / vol)


def test_sharpe_ratio_too_few():
    with pytest.raises(ValueError):
        sharpe_ratio([0.01])

