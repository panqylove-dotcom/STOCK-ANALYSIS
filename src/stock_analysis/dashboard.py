"""只读可视化仪表盘：把报告快照集合渲染为单个静态 HTML 文件。

离线、无外部依赖、无 JavaScript；仅供浏览，不提供交易操作。
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from pathlib import Path

from .analysis import AnalysisReport

_CSS = """
body { font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; }
h1 { font-size: 1.4rem; }
table { border-collapse: collapse; margin: .5rem 0 1.5rem; }
th, td { border: 1px solid #ccc; padding: 4px 10px; text-align: left; font-size: .9rem; }
th { background: #f2f2f2; }
.neg { color: #b00020; }
.pos { color: #0a7d32; }
.note { color: #666; font-size: .8rem; }
"""


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    cls = "neg" if v < 0 else "pos"
    return f'<span class="{cls}">{v:.2%}</span>'


def _fmt_num(v: float | None, digits: int = 2) -> str:
    return "—" if v is None else f"{v:.{digits}f}"


def render_dashboard_html(reports: Sequence[AnalysisReport]) -> str:
    """把多份报告渲染为只读 HTML 仪表盘。"""
    rows: list[str] = []
    for r in reports:
        m = r.market
        rows.append(
            "<tr>"
            f"<td>{html.escape(r.security.market)}:{html.escape(r.security.ticker)}</td>"
            f"<td>{html.escape(r.as_of)}</td>"
            f"<td>{html.escape(r.current_judgment)}</td>"
            f"<td>{html.escape(r.confidence)}</td>"
            f"<td>{_fmt_pct(m.interval_return)}</td>"
            f"<td>{_fmt_pct(m.annualized_volatility)}</td>"
            f"<td>{_fmt_pct(m.max_drawdown)}</td>"
            f"<td>{_fmt_num(m.sharpe)}</td>"
            "</tr>"
        )
    cards: list[str] = []
    for r in reports:
        if r.thesis:
            cards.append(
                "<h2>"
                f"{html.escape(r.security.ticker)} 投资命题"
                "</h2><p>"
                f"{html.escape(r.thesis)}</p>"
            )
    body = "\n".join(
        [
            "<h1>STOCK-ANALYSIS 只读仪表盘</h1>",
            '<p class="note">仅用于研究与信息展示，不构成投资建议；无交易功能。</p>',
            "<table>",
            "<tr><th>标的</th><th>分析日期</th><th>判断</th><th>置信度</th>"
            "<th>区间收益</th><th>年化波动</th><th>最大回撤</th><th>Sharpe</th></tr>",
            *rows,
            "</table>",
            *cards,
        ]
    )
    return (
        "<!DOCTYPE html>\n<html lang=\"zh\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<title>STOCK-ANALYSIS 只读仪表盘</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def save_dashboard_html(reports: Sequence[AnalysisReport], path: str | Path) -> None:
    """渲染并保存仪表盘 HTML。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_dashboard_html(reports), encoding="utf-8")

