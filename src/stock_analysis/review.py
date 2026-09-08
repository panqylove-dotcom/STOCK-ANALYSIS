"""报告与复盘：快照保存、财报差异比较、观察条件、复盘日志与偏差统计。

对应 docs/roadmap.md 阶段 4。核心目标：
- 保存分析时点、数据快照与假设，历史报告保持可复现；
- 后续信息不会无痕覆盖原判断（差异比较 + 复盘日志）；
- 统计预测偏差与方法稳定性。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Any

from .analysis import AnalysisReport
from .analysis import (
    Catalyst,
    Evidence,
    FinancialTrend,
    MarketMetrics,
    Observation,
    Risk,
)
from .models import Security


# ---------------------------------------------------------------- 报告快照


def save_report_snapshot(report: AnalysisReport, path: str | Path) -> None:
    """把分析报告保存为 JSON 快照（含分析时点、数据截止与全部假设）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(report.to_json() + "\n", encoding="utf-8")


def load_report_snapshot(path: str | Path) -> AnalysisReport:
    """从 JSON 快照恢复 AnalysisReport（嵌套 dataclass 递归重建）。"""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    data["security"] = Security(**data["security"])
    if data.get("market") is not None:
        data["market"] = MarketMetrics(**data["market"])
    data["financial_trends"] = [
        FinancialTrend(**t) for t in data.get("financial_trends", [])
    ]
    data["observations"] = [
        Observation(**o) for o in data.get("observations", [])
    ]
    data["catalysts"] = [Catalyst(**c) for c in data.get("catalysts", [])]
    data["risks"] = [Risk(**r) for r in data.get("risks", [])]
    data["evidences"] = [Evidence(**e) for e in data.get("evidences", [])]
    return AnalysisReport(**data)


# ---------------------------------------------------------------- 财报差异比较


@dataclass(frozen=True)
class MetricDiff:
    """单个指标在两个报告期之间的变化。"""

    metric: str
    period: str
    before: float | None
    after: float | None
    absolute_change: float | None
    pct_change: float | None


@dataclass(frozen=True)
class FinancialDiff:
    """财报更新前后差异比较结果。"""

    security_ticker: str
    period: str
    diffs: list[MetricDiff] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def compare_financials(
    ticker: str,
    period: str,
    before: dict[str, float | None],
    after: dict[str, float | None],
) -> FinancialDiff:
    """比较同一报告期的两个财务口径（如初值 vs 修正值）。

    - 缺失值保留为 None，不填零；
    - 绝对变化 = after - before；
    - 百分比变化 = after/before - 1，before 非正时标记为 None。
    """
    diffs: list[MetricDiff] = []
    for metric in sorted(set(before) | set(after)):
        b = before.get(metric)
        a = after.get(metric)
        abs_change = (a - b) if (a is not None and b is not None) else None
        pct = None
        if a is not None and b is not None and b != 0:
            pct = a / b - 1.0
        diffs.append(
            MetricDiff(
                metric=metric,
                period=period,
                before=b,
                after=a,
                absolute_change=abs_change,
                pct_change=pct,
            )
        )
    return FinancialDiff(security_ticker=ticker, period=period, diffs=diffs)


# ------------------------------------------------- 观察条件：见 analysis.Observation
# （Observation 已上移到 analysis，报告快照与复盘日志共用同一数据结构）


# ---------------------------------------------------------------- 复盘


@dataclass
class ReviewEntry:
    """一次复盘记录：命题、观察、预测、结果与偏差。"""

    ticker: str
    review_date: str
    thesis: str = ""
    observation_conditions: list[Observation] = field(default_factory=list)
    predicted_value: float | None = None
    actual_value: float | None = None
    notes: str = ""
    bias: float | None = None

    def compute_bias(self) -> float | None:
        """预测偏差 = (预测值 - 实际值) / |实际值|；实际值为 0 或缺失时返回 None。"""
        if self.predicted_value is None or self.actual_value is None:
            return None
        if self.actual_value == 0:
            return None
        self.bias = (self.predicted_value - self.actual_value) / abs(self.actual_value)
        return self.bias


def mean_absolute_bias(entries: list[ReviewEntry]) -> float | None:
    """平均绝对偏差（MAB）：反映预测偏离的平均幅度。"""
    biases = [e.compute_bias() for e in entries]
    biases = [b for b in biases if b is not None]
    if not biases:
        return None
    return sum(abs(b) for b in biases) / len(biases)


def mean_bias(entries: list[ReviewEntry]) -> float | None:
    """平均偏差（带符号）：正值为系统性高估，负值为系统性低估。"""
    biases = [e.compute_bias() for e in entries]
    biases = [b for b in biases if b is not None]
    if not biases:
        return None
    return sum(biases) / len(biases)


def save_review_log(entries: list[ReviewEntry], path: str | Path) -> None:
    """保存复盘日志为 JSON。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(e) for e in entries]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_review_log(path: str | Path) -> list[ReviewEntry]:
    """加载复盘日志。"""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    entries = []
    for item in data:
        item["observation_conditions"] = [
            Observation(**o) if isinstance(o, dict) else o
            for o in item.get("observation_conditions", [])
        ]
        entries.append(ReviewEntry(**item))
    return entries


# ---------------------------------------------------------------- 方法稳定性


def method_stability_summary(
    entries: list[ReviewEntry],
) -> dict[str, Any]:
    """方法稳定性统计：样本量、平均偏差、平均绝对偏差与命中率（偏差绝对值<=0.1）。"""
    biases = [e.compute_bias() for e in entries]
    biases = [b for b in biases if b is not None]
    if not biases:
        return {"n": 0, "mean_bias": None, "mean_absolute_bias": None, "hit_rate": None}
    hit_rate = sum(1 for b in biases if abs(b) <= 0.1) / len(biases)
    return {
        "n": len(biases),
        "mean_bias": mean_bias(entries),
        "mean_absolute_bias": mean_absolute_bias(entries),
        "hit_rate": hit_rate,
    }


# ---------------------------------------------------------------- 复盘报告


def review_summary_markdown(entries: list[ReviewEntry]) -> str:
    """复盘日志的 Markdown 摘要（阶段 4「统计预测偏差与方法稳定性」）。"""
    lines: list[str] = ["# 复盘日志", ""]
    if not entries:
        lines.append("（暂无复盘记录）")
        return "\n".join(lines)
    lines.append("| 标的 | 复盘日期 | 预测值 | 实际值 | 偏差 |")
    lines.append("| --- | --- | ---: | ---: | ---: |")
    for e in entries:
        e.compute_bias()
        pv = f"{e.predicted_value:.2f}" if e.predicted_value is not None else "—"
        av = f"{e.actual_value:.2f}" if e.actual_value is not None else "—"
        bv = f"{e.bias:.2%}" if e.bias is not None else "—"
        lines.append(f"| {e.ticker} | {e.review_date} | {pv} | {av} | {bv} |")
    stats = method_stability_summary(entries)
    lines.append("")
    lines.append("## 方法稳定性")
    lines.append("")
    lines.append(f"- 样本量：{stats['n']}")
    mab = stats["mean_absolute_bias"]
    mb = stats["mean_bias"]
    hr = stats["hit_rate"]
    lines.append(f"- 平均偏差：{mb:.2%}" if mb is not None else "- 平均偏差：—")
    lines.append(f"- 平均绝对偏差：{mab:.2%}" if mab is not None else "- 平均绝对偏差：—")
    lines.append(f"- 命中率（|偏差|≤10%）：{hr:.1%}" if hr is not None else "- 命中率：—")
    return "\n".join(lines)

