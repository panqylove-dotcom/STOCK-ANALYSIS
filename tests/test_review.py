"""报告与复盘测试：快照、财报差异、复盘日志与偏差统计（离线）。"""

from datetime import date

import pytest

from stock_analysis.analysis import AnalysisReport, MarketMetrics
from stock_analysis.models import Security
from stock_analysis.review import (
    Observation,
    ReviewEntry,
    compare_financials,
    load_report_snapshot,
    load_review_log,
    mean_absolute_bias,
    mean_bias,
    method_stability_summary,
    review_summary_markdown,
    save_report_snapshot,
    save_review_log,
)


def _sample_report() -> AnalysisReport:
    return AnalysisReport(
        security=Security(ticker="TEST", market="CN", currency="CNY", name="测试公司"),
        as_of="2026-09-04",
        data_cutoff="2026-09-03",
        thesis="命题",
        market=MarketMetrics(interval_return=0.2, max_drawdown=-0.1),
        data_gaps=["缺少财务"],
    )


# ---------------------------------------------------------------- 快照


def test_snapshot_roundtrip(tmp_path):
    p = tmp_path / "report.json"
    save_report_snapshot(_sample_report(), p)
    loaded = load_report_snapshot(p)
    assert loaded.security.ticker == "TEST"
    assert loaded.thesis == "命题"
    assert loaded.market.interval_return == pytest.approx(0.2)
    assert loaded.market.max_drawdown == pytest.approx(-0.1)
    assert loaded.data_gaps == ["缺少财务"]


def test_snapshot_creates_parent_dirs(tmp_path):
    p = tmp_path / "nested" / "deep" / "report.json"
    save_report_snapshot(_sample_report(), p)
    assert p.exists()


# ---------------------------------------------------------------- 财报差异


def test_compare_financials_basic():
    diff = compare_financials(
        "TEST",
        "2025Q4",
        {"revenue": 100.0, "net_profit": 10.0},
        {"revenue": 120.0, "net_profit": 12.0},
    )
    assert diff.security_ticker == "TEST"
    by_metric = {d.metric: d for d in diff.diffs}
    assert by_metric["revenue"].before == 100.0
    assert by_metric["revenue"].after == 120.0
    assert by_metric["revenue"].absolute_change == pytest.approx(20.0)
    assert by_metric["revenue"].pct_change == pytest.approx(0.2)


def test_compare_financials_missing_values_kept():
    diff = compare_financials(
        "TEST", "2025Q4", {"revenue": 100.0}, {"revenue": None, "margin": 0.1}
    )
    by_metric = {d.metric: d for d in diff.diffs}
    assert by_metric["revenue"].after is None
    assert by_metric["revenue"].absolute_change is None
    assert by_metric["margin"].before is None
    assert by_metric["margin"].pct_change is None


def test_compare_financials_zero_before_pct_none():
    diff = compare_financials("TEST", "2025Q4", {"x": 0.0}, {"x": 5.0})
    assert diff.diffs[0].pct_change is None
    assert diff.diffs[0].absolute_change == pytest.approx(5.0)


def test_financial_diff_to_json():
    diff = compare_financials("TEST", "2025Q4", {"revenue": 100.0}, {"revenue": 110.0})
    import json

    data = json.loads(diff.to_json())
    assert data["security_ticker"] == "TEST"
    assert data["diffs"][0]["metric"] == "revenue"


# ---------------------------------------------------------------- 复盘


def test_review_entry_compute_bias():
    e = ReviewEntry(ticker="A", review_date="2026-09-04", predicted_value=110.0, actual_value=100.0)
    assert e.compute_bias() == pytest.approx(0.1)  # (110-100)/100


def test_review_entry_bias_zero_actual_none():
    e = ReviewEntry(ticker="A", review_date="2026-09-04", predicted_value=10.0, actual_value=0.0)
    assert e.compute_bias() is None


def test_mean_bias_sign():
    entries = [
        ReviewEntry("A", "2026-01-01", predicted_value=110.0, actual_value=100.0),
        ReviewEntry("B", "2026-01-01", predicted_value=90.0, actual_value=100.0),
    ]
    # +10% 和 -10% 相互抵消
    assert mean_bias(entries) == pytest.approx(0.0, abs=1e-9)
    assert mean_absolute_bias(entries) == pytest.approx(0.1)


def test_mean_bias_empty():
    assert mean_bias([]) is None
    assert mean_absolute_bias([]) is None


def test_method_stability_summary():
    entries = [
        ReviewEntry("A", "2026-01-01", predicted_value=101.0, actual_value=100.0),  # 1%
        ReviewEntry("B", "2026-01-01", predicted_value=120.0, actual_value=100.0),  # 20%
    ]
    stats = method_stability_summary(entries)
    assert stats["n"] == 2
    assert stats["hit_rate"] == pytest.approx(0.5)  # 只有一条 |偏差|<=10%


def test_review_log_roundtrip(tmp_path):
    entries = [
        ReviewEntry("A", "2026-01-01", predicted_value=101.0, actual_value=100.0, notes="x"),
    ]
    p = tmp_path / "review.json"
    save_review_log(entries, p)
    loaded = load_review_log(p)
    assert len(loaded) == 1
    assert loaded[0].ticker == "A"
    assert loaded[0].predicted_value == pytest.approx(101.0)


def test_review_summary_markdown_empty():
    md = review_summary_markdown([])
    assert "（暂无复盘记录）" in md


def test_review_summary_markdown_content():
    entries = [
        ReviewEntry(
            "A",
            "2026-09-04",
            thesis="命题",
            observation_conditions=[Observation("财报", "营收增速>10%")],
            predicted_value=110.0,
            actual_value=100.0,
        )
    ]
    md = review_summary_markdown(entries)
    assert "| A | 2026-09-04 | 110.00 | 100.00 | 10.00% |" in md
    assert "## 方法稳定性" in md
    assert "命中率" in md

