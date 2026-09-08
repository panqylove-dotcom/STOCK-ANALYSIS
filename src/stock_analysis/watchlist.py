"""观察清单：聚合报告快照与复盘日志中的观察条件，输出只读跟踪清单。

用途：把"写完报告就忘"变成可持续跟踪——按标的汇总观察条件与状态，
标注分析时点是否超过复盘周期（stale），提醒复盘或补充新信息。
本模块只读，不修改任何文件，不构成投资建议。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .analysis import AnalysisReport
from .review import ReviewEntry


@dataclass(frozen=True)
class WatchItem:
    """一条观察条件（含所属标的与分析时点）。"""

    ticker: str
    as_of: str
    description: str
    condition: str
    threshold: str
    status: str
    origin: str  # report / review


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def collect_watch_items(
    reports: list[AnalysisReport],
    entries: list[ReviewEntry] | None = None,
) -> list[WatchItem]:
    """收集快照与复盘日志中的全部观察条件，按标的、日期排序。"""
    items: list[WatchItem] = []
    for r in reports:
        for o in r.observations:
            items.append(
                WatchItem(
                    ticker=r.security.ticker,
                    as_of=r.as_of,
                    description=o.description,
                    condition=o.condition,
                    threshold=o.threshold,
                    status=o.status,
                    origin="report",
                )
            )
    for e in entries or []:
        for o in e.observation_conditions:
            items.append(
                WatchItem(
                    ticker=e.ticker,
                    as_of=e.review_date,
                    description=o.description,
                    condition=o.condition,
                    threshold=o.threshold,
                    status=o.status,
                    origin="review",
                )
            )
    return sorted(items, key=lambda i: (i.ticker, i.as_of, i.description))


def watch_markdown(
    items: list[WatchItem],
    *,
    today: date,
    stale_days: int = 90,
) -> str:
    """生成只读观察清单 Markdown（按标的分组，标注过期状态）。"""
    lines: list[str] = ["# 观察清单（只读汇总）", ""]
    if not items:
        lines.append("（暂无观察条件：请在报告中登记观察条件，或用 review add 补充）")
        return "\n".join(lines)

    by_ticker: dict[str, list[WatchItem]] = {}
    for it in items:
        by_ticker.setdefault(it.ticker, []).append(it)

    stale_tickers: list[str] = []
    pending_total = 0
    for ticker in sorted(by_ticker):
        group = by_ticker[ticker]
        dates = [d for d in (_parse_date(i.as_of) for i in group) if d]
        latest = max(dates) if dates else None
        age = (today - latest).days if latest else None
        pending = [i for i in group if i.status == "待观察"]
        pending_total += len(pending)
        stale = age is not None and age > stale_days and pending
        if stale:
            stale_tickers.append(ticker)
        lines.append(f"## {ticker}")
        lines.append("")
        age_s = f"{age} 天前" if age is not None else "日期未知"
        flag = "  ⚠️ 超过复盘周期，建议复盘" if stale else ""
        lines.append(f"- 最近分析/复盘：{latest or '未知'}（{age_s}）{flag}")
        lines.append("")
        lines.append("| 状态 | 观察条件 | 触发判据 | 阈值 | 记录日期 | 来源 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for i in group:
            lines.append(
                f"| {i.status} | {i.description} | {i.condition} | "
                f"{i.threshold or '—'} | {i.as_of} | {i.origin} |"
            )
        lines.append("")
    lines.append(f"合计：{len(items)} 条观察条件，待观察 {pending_total} 条。")
    if stale_tickers:
        lines.append(f"超过 {stale_days} 天未复盘且有待观察条件: {', '.join(stale_tickers)}")
    lines.append("")
    lines.append("本清单为只读汇总，不构成投资建议；触发与否需人工核验原始数据。")
    return "\n".join(lines)
