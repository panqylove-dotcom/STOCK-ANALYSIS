"""财务数据工作簿：`data/financials/<TICKER>.json` 约定格式的加载与校验。

打通「法定披露 -> 逐项录入 -> 报告自动填充」闭环（docs/data-and-metrics.md）：
财务数字必须登记币种、会计准则与来源，缺失值用 null 显式表达，不默认填零。

格式约定：

.. code-block:: json

    {
      "currency": "CNY",
      "standard": "CAS",
      "source": "2025年年度报告（巨潮披露 2026-04-30）",
      "metrics": {
        "revenue":    {"2023": 100.0, "2024": 120.0, "2025": 150.0},
        "net_profit": {"2023": 10.0, "2024": 13.0, "2025": null}
      }
    }

期间键支持 `YYYY`、`YYYYQn`、`YYYYHn`（如 2025、2025Q3、2025H1），按时间排序。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .analysis import FinancialTrend, financial_trend

#: 期间键：2023 / 2023Q4 / 2023H1（可带前后空白）
_PERIOD_RE = re.compile(r"^(\d{4})(?:(Q[1-4])|(H[12]))?$")

#: 排序序：年报(0) < Q1 < Q2 < H1(累计) < Q3 < Q4 < H2(累计)
_SUB_ORDER = {"Q1": 1, "Q2": 3, "H1": 4, "Q3": 5, "Q4": 7, "H2": 8, None: 0}


def period_sort_key(period: str) -> tuple[int, int]:
    """期间键 -> (年, 子期序)。无法解析的期间键抛 ValueError。"""
    m = _PERIOD_RE.match(str(period).strip())
    if not m:
        raise ValueError(f"无法解析报告期: {period!r}（支持 2023 / 2023Q4 / 2023H1）")
    year = int(m.group(1))
    sub = m.group(2) or m.group(3)
    return year, _SUB_ORDER[sub]


@dataclass(frozen=True)
class FinancialWorkbook:
    """一只股票的财务录入工作簿：币种/准则/来源 + 指标时序。"""

    currency: str
    standard: str
    source: str
    metrics: dict[str, dict[str, float | None]] = field(default_factory=dict)

    def sorted_periods(self, metric: str) -> list[str]:
        periods = list(self.metrics.get(metric, {}))
        return sorted(periods, key=period_sort_key)

    def annual_gaps(self, metric: str) -> list[str]:
        """年报序列（全为 YYYY 形态）中缺失的年份；非纯年度序列返回 []。"""
        periods = self.sorted_periods(metric)
        if not periods or any("Q" in p.upper() or "H" in p.upper() for p in periods):
            return []
        years = [int(p) for p in periods]
        return [str(y) for y in range(years[0] + 1, years[-1]) if y not in years]

    def to_trends(self) -> list[FinancialTrend]:
        """每个指标生成趋势对象（同比/CAGR 由 analysis.financial_trend 计算）。"""
        trends = []
        for metric in sorted(self.metrics):
            periods = self.sorted_periods(metric)
            values = [self.metrics[metric][p] for p in periods]
            trends.append(
                financial_trend(metric, periods, values, currency=self.currency)
            )
        return trends

    def latest(self, metric: str) -> float | None:
        """指标最近一个非空值（用于 DCF 基期等场景）；全部缺失返回 None。"""
        for p in reversed(self.sorted_periods(metric)):
            v = self.metrics[metric][p]
            if v is not None:
                return v
        return None


def load_financials(path: str | Path) -> FinancialWorkbook:
    """加载并校验财务工作簿；不合规数据抛 ValueError（附具体原因）。"""
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("财务文件顶层必须是 JSON 对象")
    currency = str(raw.get("currency") or "").strip()
    if not currency:
        raise ValueError("缺少 currency：录入时必须显式登记币种")
    source = str(raw.get("source") or "").strip()
    if not source:
        raise ValueError("缺少 source：财务数字必须可追溯到披露来源")
    metrics_raw = raw.get("metrics")
    if not isinstance(metrics_raw, dict) or not metrics_raw:
        raise ValueError("缺少 metrics：至少录入一个指标的时序")
    metrics: dict[str, dict[str, float | None]] = {}
    for metric, series in metrics_raw.items():
        if not isinstance(series, dict) or not series:
            raise ValueError(f"指标 {metric} 必须是非空的 期间->数值 对象")
        clean: dict[str, float | None] = {}
        for period, value in series.items():
            period_sort_key(period)  # 校验期间可排序
            if value is None:
                clean[str(period).strip()] = None
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                clean[str(period).strip()] = float(value)
            else:
                raise ValueError(f"指标 {metric} 期间 {period} 的值不是数字或 null: {value!r}")
        metrics[str(metric).strip()] = clean
    return FinancialWorkbook(
        currency=currency,
        standard=str(raw.get("standard") or "").strip(),
        source=source,
        metrics=metrics,
    )


def save_financials(workbook: FinancialWorkbook, path: str | Path) -> None:
    """按约定格式保存工作簿（键序稳定，便于版本控制 diff）。"""
    data = {
        "currency": workbook.currency,
        "standard": workbook.standard,
        "source": workbook.source,
        "metrics": {
            m: {p: workbook.metrics[m][p] for p in workbook.sorted_periods(m)}
            for m in sorted(workbook.metrics)
        },
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
