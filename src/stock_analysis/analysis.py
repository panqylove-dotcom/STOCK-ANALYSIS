"""分析引擎：财务趋势、估值（DCF 情景）、相对表现、催化剂/风险清单与结构化输出。

对应 docs/roadmap.md 阶段 3。设计原则：
- 纯函数、固定输入产生确定输出，便于单元测试与边界测试；
- 所有假设必须显式传入并可调整，不伪装成已知事实；
- 估值输出优先使用区间（情景），关键变量做敏感性分析；
- 输出可序列化为 Markdown / JSON，便于保存分析快照。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field, asdict
from datetime import date
from statistics import fmean
from typing import Any

from .config import Config
from .models import FinancialMetric, PriceBar, Security


# ---------------------------------------------------------------- 口径守卫


def assert_same_standards(metrics: Sequence[FinancialMetric]) -> str:
    """校验一组财务指标使用同一会计准则，返回该准则。

    - 准则未登记（空字符串）不影响检查，但会被忽略；
    - 发现两种及以上准则时抛错，阻止直接比较（docs/data-and-metrics.md：
      对不同市场、币种、会计准则的数据比较前先完成标准化）。
    """
    known = {m.standard for m in metrics if m.standard}
    if len(known) > 1:
        raise ValueError(
            f"会计准则混用，不能直接比较: {sorted(known)}；请先完成口径标准化"
        )
    return known.pop() if known else ""


def assert_same_currencies(metrics: Sequence[FinancialMetric]) -> str:
    """校验一组财务指标使用同一币种，返回该币种。"""
    currencies = {m.currency for m in metrics if m.currency}
    if len(currencies) > 1:
        raise ValueError(
            f"币种混用，不能直接比较: {sorted(currencies)}；请先用 markets.convert 换算"
        )
    return currencies.pop() if currencies else ""


# ---------------------------------------------------------------- 财务趋势


@dataclass(frozen=True)
class FinancialTrend:
    """单指标趋势：原始序列 + 同比变化 + 复合年增长率。"""

    metric: str
    periods: list[str]
    values: list[float | None]
    yoy_changes: list[float | None]
    cagr: float | None
    currency: str


def financial_trend(
    metric: str,
    periods: list[str],
    values: list[float | None],
    currency: str = "CNY",
) -> FinancialTrend:
    """由按期排列的数值构造趋势对象，计算同比变化与 CAGR。

    缺失值（None）保留，不默认填零；年初值为负或接近零时，
    同比变化标记为 None（应改用绝对变化口径）。
    """
    if len(periods) != len(values):
        raise ValueError("periods 与 values 长度必须一致")
    yoy: list[float | None] = []
    for prev, cur in zip(values, values[1:]):
        if prev is None or cur is None or prev == 0:
            yoy.append(None)
        else:
            yoy.append(cur / prev - 1.0)
    non_null = [v for v in values if v is not None]
    cagr_value: float | None = None
    if len(non_null) >= 2 and non_null[0] > 0 and non_null[-1] > 0:
        years = max(len(non_null) - 1, 1)
        cagr_value = (non_null[-1] / non_null[0]) ** (1.0 / years) - 1.0
    return FinancialTrend(
        metric=metric,
        periods=list(periods),
        values=list(values),
        yoy_changes=yoy,
        cagr=cagr_value,
        currency=currency,
    )


# ---------------------------------------------------------------- DCF 情景


@dataclass(frozen=True)
class DcfAssumptions:
    """DCF 情景假设。所有字段必须显式给出，禁止默认猜测。"""

    name: str
    fcf_growth: float
    discount_rate: float
    terminal_growth: float

    def validate(self) -> None:
        if self.discount_rate <= self.terminal_growth:
            raise ValueError(
                f"情景 '{self.name}': 折现率必须大于永续增长率"
            )
        if self.fcf_growth < -1:
            raise ValueError(f"情景 '{self.name}': FCF 增长率低于 -100%")


def project_fcf_stream(base_fcf: float, growth: float, years: int) -> list[float]:
    """显式预测期 FCF 序列：第 t 年 = base * (1+g)^t。"""
    if base_fcf <= 0:
        raise ValueError("期初 FCF 必须为正")
    if years <= 0:
        raise ValueError("预测期年数必须为正")
    out: list[float] = []
    for t in range(1, years + 1):
        out.append(base_fcf * (1.0 + growth) ** t)
    return out


def dcf_enterprise_value(
    base_fcf: float,
    assumptions: DcfAssumptions,
    years: int = 10,
) -> float:
    """两阶段 DCF 企业价值 = 显式预测期现值 + 终值现值。

    terminal value = FCF_{N+1} / (r - g_terminal)
    """
    assumptions.validate()
    stream = project_fcf_stream(base_fcf, assumptions.fcf_growth, years)
    r = assumptions.discount_rate
    g = assumptions.terminal_growth
    pv = sum(fcf / (1.0 + r) ** t for t, fcf in enumerate(stream, start=1))
    terminal_fcf = stream[-1] * (1.0 + g)
    terminal_value = terminal_fcf / (r - g)
    pv_terminal = terminal_value / (1.0 + r) ** years
    return pv + pv_terminal


def dcf_equity_value_per_share(
    enterprise_value: float,
    net_debt: float,
    shares_outstanding: float,
) -> float:
    """每股内在价值 = (企业价值 - 净负债) / 股本。"""
    if shares_outstanding <= 0:
        raise ValueError("股本必须为正")
    return (enterprise_value - net_debt) / shares_outstanding


def scenario_dcf(
    base_fcf: float,
    scenarios: list[DcfAssumptions],
    years: int = 10,
) -> dict[str, float]:
    """多情景 DCF，返回 {情景名: 企业价值}。"""
    return {
        s.name: dcf_enterprise_value(base_fcf, s, years=years)
        for s in scenarios
    }


def dcf_sensitivity(
    base_fcf: float,
    growth_range: list[float],
    discount_range: list[float],
    years: int = 10,
) -> dict[tuple[float, float], float]:
    """敏感性分析：{ (增长率, 折现率): 企业价值 }。"""
    out: dict[tuple[float, float], float] = {}
    for g in growth_range:
        for r in discount_range:
            assump = DcfAssumptions(
                name=f"g={g:.1%},r={r:.1%}",
                fcf_growth=g,
                discount_rate=r,
                terminal_growth=0.02,
            )
            try:
                out[(g, r)] = dcf_enterprise_value(base_fcf, assump, years=years)
            except ValueError:
                continue
    return out


# ---------------------------------------------------------------- 相对表现


def relative_return(stock_return: float, benchmark_return: float) -> float:
    """相对收益 = 标的区间收益 - 基准区间收益。"""
    return stock_return - benchmark_return


def beta(
    stock_returns: list[float],
    market_returns: list[float],
) -> float:
    """Beta = Cov(r_s, r_m) / Var(r_m)。样本量必须一致且 >= 2。"""
    if len(stock_returns) != len(market_returns):
        raise ValueError("标的市场收益率样本量必须一致")
    if len(stock_returns) < 2:
        raise ValueError("样本量不足")
    ms = fmean(market_returns)
    ss = fmean(stock_returns)
    var_m = sum((m - ms) ** 2 for m in market_returns) / (len(market_returns) - 1)
    if var_m == 0:
        raise ValueError("市场收益方差为零，无法计算 Beta")
    cov = sum(
        (s - ss) * (m - ms)
        for s, m in zip(stock_returns, market_returns)
    ) / (len(stock_returns) - 1)
    return cov / var_m


def alpha(
    stock_returns: list[float],
    market_returns: list[float],
    risk_free_rate: float = 0.0,
) -> float:
    """Alpha = 平均标的超额收益 - Beta * 平均市场超额收益（简化口径）。

    必须同时披露区间、频率、无风险利率与样本量（docs/data-and-metrics.md）。
    """
    b = beta(stock_returns, market_returns)
    ms = fmean(market_returns)
    ss = fmean(stock_returns)
    return (ss - risk_free_rate) - b * (ms - risk_free_rate)


# ---------------------------------------------------------------- 清单


@dataclass(frozen=True)
class Catalyst:
    """催化剂：应有时间窗与可观测结果。"""

    description: str
    expected_window: str
    observable_result: str
    potential_impact: str = ""


@dataclass(frozen=True)
class Risk:
    """风险：记录可能性、影响、先行指标与缓释因素。"""

    description: str
    likelihood: str
    impact: str
    leading_indicator: str = ""
    mitigation: str = ""


@dataclass(frozen=True)
class Evidence:
    """证据账本条目：来源可追溯。"""

    title: str
    publisher: str
    published_on: str
    accessed_on: str
    url: str = ""
    supports: str = ""


# ---------------------------------------------------------------- 报告


@dataclass
class MarketMetrics:
    """市场与技术观察汇总。"""

    interval_return: float | None = None
    annualized_volatility: float | None = None
    max_drawdown: float | None = None
    sharpe: float | None = None
    beta: float | None = None
    alpha: float | None = None
    relative_return: float | None = None


@dataclass
class AnalysisReport:
    """结构化分析报告：可序列化为 Markdown / JSON。"""

    security: Security
    as_of: str
    data_cutoff: str
    thesis: str = ""
    current_judgment: str = "信息不足"
    confidence: str = "低"
    next_event: str = ""
    financial_trends: list[FinancialTrend] = field(default_factory=list)
    scenario_values: dict[str, float] = field(default_factory=dict)
    market: MarketMetrics = field(default_factory=MarketMetrics)
    catalysts: list[Catalyst] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    evidences: list[Evidence] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)
    disclaimer: str = (
        "本报告仅用于教育、研究和信息整理，不构成投资建议、证券推荐或收益承诺。"
        "数据可能存在延迟、错误或口径差异，使用者应独立核实并自行承担决策风险。"
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_markdown(self) -> str:
        """按 docs/report-template.md 结构输出 Markdown。"""
        lines: list[str] = []
        lines.append(f"# {self.security.name or self.security.ticker} "
                     f"({self.security.market}:{self.security.ticker}) 研究报告")
        lines.append("")
        lines.append("## 1. 报告元数据")
        lines.append("")
        lines.append("| 项目 | 内容 |")
        lines.append("| --- | --- |")
        lines.append(f"| 证券与币种 | {self.security.ticker} / {self.security.currency} |")
        lines.append(f"| 分析日期 | {self.as_of} |")
        lines.append(f"| 数据截止时间 | {self.data_cutoff} |")
        lines.append(f"| 当前判断 | {self.current_judgment} |")
        lines.append(f"| 结论置信度 | {self.confidence} |")
        lines.append(f"| 下一观察事件 | {self.next_event} |")
        lines.append("")
        lines.append("## 2. 执行摘要")
        lines.append("")
        lines.append(f"- **一句话投资命题：** {self.thesis or '（待填写）'}")
        lines.append("")
        if self.financial_trends:
            lines.append("## 3. 财务趋势")
            lines.append("")
            for t in self.financial_trends:
                lines.append(f"### {t.metric}（{t.currency}）")
                lines.append("")
                lines.append("| 期间 | 数值 | 同比 |")
                lines.append("| --- | ---: | ---: |")
                for i, period in enumerate(t.periods):
                    v = t.values[i]
                    y = t.yoy_changes[i - 1] if i > 0 and t.yoy_changes else None
                    v_s = f"{v:,.2f}" if v is not None else "未知"
                    y_s = f"{y:+.1%}" if y is not None else "—"
                    lines.append(f"| {period} | {v_s} | {y_s} |")
                cagr_s = f"{t.cagr:.1%}" if t.cagr is not None else "未知"
                lines.append("")
                lines.append(f"CAGR：{cagr_s}")
                lines.append("")
        if self.scenario_values:
            lines.append("## 4. 估值情景（DCF 企业价值）")
            lines.append("")
            lines.append("| 情景 | 企业价值 |")
            lines.append("| --- | ---: |")
            for name, value in self.scenario_values.items():
                lines.append(f"| {name} | {value:,.0f} |")
            lines.append("")
        mm = self.market
        market_rows = [
            ("区间收益率", mm.interval_return),
            ("年化波动率", mm.annualized_volatility),
            ("最大回撤", mm.max_drawdown),
            ("Sharpe", mm.sharpe),
            ("Beta", mm.beta),
            ("Alpha", mm.alpha),
            ("相对收益", mm.relative_return),
        ]
        if any(v is not None for _, v in market_rows):
            lines.append("## 5. 市场与技术观察")
            lines.append("")
            lines.append("| 指标 | 值 |")
            lines.append("| --- | ---: |")
            for name, v in market_rows:
                if v is None:
                    continue
                if name in ("区间收益率", "年化波动率", "最大回撤", "相对收益"):
                    lines.append(f"| {name} | {v:.2%} |")
                elif name == "Sharpe":
                    lines.append(f"| {name} | {v:.2f} |")
                else:
                    lines.append(f"| {name} | {v:.2f} |")
            lines.append("")
        if self.catalysts:
            lines.append("## 6. 催化剂")
            lines.append("")
            lines.append("| 催化剂 | 预计时间 | 可观察结果 | 可能影响 |")
            lines.append("| --- | --- | --- | --- |")
            for c in self.catalysts:
                lines.append(
                    f"| {c.description} | {c.expected_window} | "
                    f"{c.observable_result} | {c.potential_impact} |"
                )
            lines.append("")
        if self.risks:
            lines.append("## 7. 风险与反证")
            lines.append("")
            lines.append("| 风险 | 可能性 | 影响 | 先行指标 | 缓释因素 |")
            lines.append("| --- | --- | --- | --- | --- |")
            for r in self.risks:
                lines.append(
                    f"| {r.description} | {r.likelihood} | {r.impact} | "
                    f"{r.leading_indicator} | {r.mitigation} |"
                )
            lines.append("")
        if self.assumptions:
            lines.append("## 8. 假设")
            lines.append("")
            for a in self.assumptions:
                lines.append(f"- {a}")
            lines.append("")
        if self.data_gaps:
            lines.append("## 9. 数据缺口")
            lines.append("")
            for g in self.data_gaps:
                lines.append(f"- {g}")
            lines.append("")
        if self.evidences:
            lines.append("## 10. 来源")
            lines.append("")
            lines.append("| 编号 | 来源与链接 | 发布日期 | 访问日期 | 支持内容 |")
            lines.append("| --- | --- | --- | --- | --- |")
            for i, e in enumerate(self.evidences, start=1):
                lines.append(
                    f"| {i} | {e.title} ({e.url}) | {e.published_on} | "
                    f"{e.accessed_on} | {e.supports} |"
                )
            lines.append("")
        lines.append("## 11. 免责声明")
        lines.append("")
        lines.append(self.disclaimer)
        lines.append("")
        return "\n".join(lines)


def market_metrics_from_bars(
    bars: list[PriceBar],
    *,
    benchmark_returns: list[float] | None = None,
    config: Config | None = None,
) -> MarketMetrics:
    """从日线数据计算市场指标；提供基准收益率时计算 Beta/Alpha/相对收益。"""
    cfg = config or Config()
    closes = [b.close for b in bars]
    from .metrics import (
        annualized_volatility,
        interval_return,
        max_drawdown,
        returns_from_prices,
        sharpe_ratio,
    )

    rets = returns_from_prices(closes)
    metrics = MarketMetrics()
    if len(closes) >= 2:
        metrics.interval_return = interval_return(closes[0], closes[-1])
    if len(rets) >= 2:
        metrics.annualized_volatility = annualized_volatility(
            rets, cfg.trading_days_per_year
        )
        metrics.max_drawdown = max_drawdown(closes)
        try:
            metrics.sharpe = sharpe_ratio(rets, cfg)
        except ValueError:
            metrics.sharpe = None
    if benchmark_returns is not None:
        if len(benchmark_returns) != len(rets):
            raise ValueError("基准收益率序列长度必须等于标的日收益率序列")
        try:
            metrics.beta = beta(rets, benchmark_returns)
            metrics.alpha = alpha(rets, benchmark_returns, cfg.risk_free_rate)
        except ValueError:
            metrics.beta = None
            metrics.alpha = None
        if metrics.interval_return is not None and benchmark_returns:
            bench_ret = 1.0
            for r in benchmark_returns:
                bench_ret *= 1.0 + r
            metrics.relative_return = metrics.interval_return - (bench_ret - 1.0)
    return metrics

