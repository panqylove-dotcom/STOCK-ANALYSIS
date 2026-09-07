"""只读 HTML 仪表盘测试。"""

import html as html_module

from stock_analysis.analysis import AnalysisReport, MarketMetrics
from stock_analysis.dashboard import render_dashboard_html, save_dashboard_html
from stock_analysis.models import Security


def _report(ticker: str, drawdown: float | None = -0.2, thesis: str = "") -> AnalysisReport:
    return AnalysisReport(
        security=Security(ticker=ticker, market="CN", currency="CNY"),
        as_of="2026-09-07",
        data_cutoff="2026-09-06",
        thesis=thesis,
        current_judgment="观察",
        confidence="中",
        market=MarketMetrics(
            interval_return=0.1,
            annualized_volatility=0.3,
            max_drawdown=drawdown,
            sharpe=0.5,
        ),
    )


def test_render_contains_table_and_disclaimer():
    html = render_dashboard_html([_report("A"), _report("B")])
    assert "<table>" in html
    assert "CN:A" in html and "CN:B" in html
    assert "不构成投资建议" in html


def test_render_escapes_injection():
    evil = _report("<script>x</script>")
    html = render_dashboard_html([evil])
    assert "<script>x</script>" not in html
    assert html_module.escape("<script>") in html


def test_render_negative_drawdown_class():
    html = render_dashboard_html([_report("A", drawdown=-0.25)])
    assert 'class="neg"' in html
    assert "-25.00%" in html


def test_save_dashboard(tmp_path):
    p = tmp_path / "dashboard.html"
    save_dashboard_html([_report("A", thesis="命题内容")], p)
    content = p.read_text(encoding="utf-8")
    assert "命题内容" in content
    assert p.exists()

