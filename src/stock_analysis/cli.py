"""命令行入口：加载 -> 校验 -> 质量检查 -> 计算指标 / 生成报告（离线）。"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
import sys

from .analysis import AnalysisReport, market_metrics_from_bars
from .audit import DataLicense, LicenseViolation, perform_action
from .config import Config
from .dashboard import save_dashboard_html
from .data.loader import CsvPriceLoader
from .data.quality import run_quality_checks
from .models import Security
from .review import (
    compare_financials,
    load_report_snapshot,
    load_review_log,
    review_summary_markdown,
    save_report_snapshot,
)
from .metrics import (
    annualized_volatility,
    interval_return,
    max_drawdown,
    returns_from_prices,
)
from .portfolio import Position, correlation_matrix, portfolio_exposure_summary, weights


class _CmdError(Exception):
    """携带退出码的命令错误。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _load(args):
    """加载并做质量检查；失败抛 _CmdError（1=结构错误，2=质量失败）。"""
    loader = CsvPriceLoader(market=args.market, currency=args.currency)
    try:
        result = loader.load(args.csv, ticker=args.ticker)
    except ValueError as exc:
        raise _CmdError(1, f"数据加载失败（结构错误）: {exc}") from exc
    bars = result.bars
    report = run_quality_checks(bars)
    if not args.skip_quality:
        print("== 数据质量检查 ==", file=sys.stderr)
        print(report.summary(), file=sys.stderr)
        if not report.passed:
            raise _CmdError(
                2,
                "质量检查未通过，请先处理数据问题（可用 --skip-quality 强制继续）。",
            )
    return result


def _audit_analyze(args, source) -> None:
    """若提供 --audit，则把本次 analyze 动作写入审计日志。

    第三方来源默认 personal_use、禁止再分发；违例会被记录并拒绝。
    """
    if not getattr(args, "audit", None):
        return
    license = DataLicense(
        source=source.name, personal_use=True, redistribution=False
    )
    perform_action(
        license,
        "analyze",
        args.audit,
        detail=f"license={source.license_name}",
    )


def _cmd_stats(args) -> int:
    try:
        result = _load(args)
    except _CmdError as exc:
        print(exc, file=sys.stderr)
        return exc.code
    try:
        _audit_analyze(args, result.source)
    except LicenseViolation as exc:
        print(f"许可检查未通过: {exc}", file=sys.stderr)
        return 4
    bars = result.bars
    closes = [b.close for b in bars]
    dates = [b.date for b in bars]

    rets = returns_from_prices(closes)
    nav = closes  # 未复权近似：默认视作净值序列
    print(
        f"== {result.security.ticker} "
        f"({result.security.market}:{result.security.currency}) =="
    )
    print(f"来源: {result.source.name}  (访问于 {result.source.accessed_at})")
    print(f"数据区间: {dates[0]} ~ {dates[-1]}  (共 {len(dates)} 个交易日)")
    print(f"区间收益率: {interval_return(closes[0], closes[-1]):.2%}")
    print(f"年化波动率: {annualized_volatility(rets, args.trading_days):.2%}")
    print(f"最大回撤:   {max_drawdown(nav):.2%}")
    return 0


def _cmd_report(args) -> int:
    try:
        result = _load(args)
    except _CmdError as exc:
        print(exc, file=sys.stderr)
        return exc.code
    bars = result.bars
    metrics = market_metrics_from_bars(bars)
    try:
        _audit_analyze(args, result.source)
    except LicenseViolation as exc:
        print(f"许可检查未通过: {exc}", file=sys.stderr)
        return 4
    report = AnalysisReport(
        security=result.security,
        as_of=date.today().isoformat(),
        data_cutoff=result.source.accessed_at,
        market=metrics,
        data_gaps=["示例数据未包含财务字段，估值与财务趋势需补充后生成。"],
    )
    if args.save:
        save_report_snapshot(report, args.save)
        print(f"报告快照已保存: {args.save}", file=sys.stderr)
    if args.format == "json":
        print(report.to_json())
    else:
        print(report.to_markdown())
    return 0


def _cmd_diff(args) -> int:
    """比较财报更新前后差异（两个 JSON 文件：{metric: value}）。"""
    try:
        before = json.loads(Path(args.before).read_text(encoding="utf-8"))
        after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读取财务 JSON 失败: {exc}", file=sys.stderr)
        return 1
    diff = compare_financials(args.ticker, args.period, before, after)
    if args.format == "json":
        print(diff.to_json())
    else:
        print(f"标的: {diff.security_ticker}  报告期: {diff.period}")
        print("")
        print("| 指标 | 更新前 | 更新后 | 绝对变化 | 百分比 |")
        print("| --- | ---: | ---: | ---: | ---: |")
        for d in diff.diffs:
            b = f"{d.before:,.2f}" if d.before is not None else "—"
            a = f"{d.after:,.2f}" if d.after is not None else "—"
            ac = f"{d.absolute_change:+,.2f}" if d.absolute_change is not None else "—"
            pc = f"{d.pct_change:+.1%}" if d.pct_change is not None else "—"
            print(f"| {d.metric} | {b} | {a} | {ac} | {pc} |")
    return 0


def _cmd_review(args) -> int:
    """从复盘 JSON 生成 Markdown 摘要（含偏差统计）。"""
    try:
        entries = load_review_log(args.json)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        print(f"读取复盘日志失败: {exc}", file=sys.stderr)
        return 1
    print(review_summary_markdown(entries))
    return 0


def _cmd_dashboard(args) -> int:
    """从报告快照 JSON 生成只读 HTML 仪表盘。"""
    reports = []
    for item in args.snapshots:
        try:
            reports.append(load_report_snapshot(item))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print(f"读取快照失败 {item}: {exc}", file=sys.stderr)
            return 1
    save_dashboard_html(reports, args.out)
    print(f"仪表盘已保存: {args.out}（只读，无交易功能）")
    return 0


def _cmd_fetch(args) -> int:
    """从 akshare 拉取 A 股日线并存为 CSV（需安装可选依赖 akshare）。"""
    from .data.fetchers import akshare_daily_cn

    try:
        result = akshare_daily_cn(
            args.symbol,
            start=date.fromisoformat(args.start),
            end=date.fromisoformat(args.end),
            adjust=args.adjust,
        )
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (ValueError, OSError) as exc:
        print(f"拉取失败: {exc}", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["date,open,high,low,close,volume"]
    for b in result.bars:
        lines.append(
            f"{b.date},{b.open:.4f},{b.high:.4f},{b.low:.4f},{b.close:.4f},{b.volume:.0f}"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已保存 {len(result.bars)} 条日线 -> {out}")
    print(f"来源: {result.source.name}（{result.source.license_name}）", file=sys.stderr)
    return 0


def _cmd_portfolio(args) -> int:
    """组合暴露与相关性分析（单币种；多币种需先换算统一）。

    JSON 格式：{"positions":[{"ticker","market","currency","market_value"}...],
               "returns": {ticker: [日收益率...]}（可选）}
    """
    try:
        data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读取组合 JSON 失败: {exc}", file=sys.stderr)
        return 1
    try:
        positions = [
            Position(
                security=Security(
                    ticker=p["ticker"],
                    market=p["market"],
                    currency=p["currency"],
                ),
                market_value=float(p["market_value"]),
            )
            for p in data["positions"]
        ]
    except (KeyError, TypeError, ValueError) as exc:
        print(f"组合字段错误: {exc}", file=sys.stderr)
        return 1
    currencies = {p.security.currency for p in positions}
    if len(currencies) > 1:
        print(
            f"持仓币种不一致: {sorted(currencies)}；"
            "请先用 markets.convert 换算为同一币种",
            file=sys.stderr,
        )
        return 1
    try:
        summary = portfolio_exposure_summary(positions)
    except ValueError as exc:
        print(f"组合分析失败: {exc}", file=sys.stderr)
        return 1
    print(f"币种: {positions[0].security.currency}")
    print("| 指标 | 值 |")
    print("| --- | ---: |")
    for key, value in summary.items():
        v = f"{value:,.4f}" if isinstance(value, float) else value
        print(f"| {key} | {v} |")
    w = weights(positions)
    print("")
    print("| 持仓 | 权重 |")
    print("| --- | ---: |")
    for ticker in sorted(w):
        print(f"| {ticker} | {w[ticker]:.2%} |")
    returns = data.get("returns")
    if returns:
        try:
            corr = correlation_matrix(
                {k: [float(x) for x in v] for k, v in returns.items()}
            )
        except ValueError as exc:
            print(f"相关性计算失败: {exc}", file=sys.stderr)
            return 1
        print("")
        print("| 标的对 | 相关系数 |")
        print("| --- | ---: |")
        for (a, b), c in sorted(corr.items()):
            if a != b:
                print(f"| {a} vs {b} | {c:.3f} |")
    return 0


def _cmd_disclose(args) -> int:
    """法定披露：公告元数据检索（cninfo/sse/szse）或本地核验登记。"""
    from .data.disclosures import (
        append_index,
        fetch_announcements,
        register_local_disclosure,
    )

    if args.disclose_action == "list":
        try:
            records = fetch_announcements(
                args.source,
                args.ticker,
                start=date.fromisoformat(args.start),
                end=date.fromisoformat(args.end),
            )
        except (ValueError, OSError) as exc:
            print(f"披露检索失败: {exc}", file=sys.stderr)
            return 1
        if not records:
            print("区间内未检索到公告。")
            return 0
        print("| 披露日期 | 标题 | 链接 |")
        print("| --- | --- | --- |")
        for r in records:
            print(f"| {r.disclosed_on} | {r.title} | {r.url or '-'} |")
        print(
            f"来源: {args.source}（{len(records)} 条）；公告原文需人工核验",
            file=sys.stderr,
        )
        return 0

    # register：手动下载的公告文件 -> SHA-256 + JSONL 索引
    try:
        record = register_local_disclosure(
            Path(args.file),
            ticker=args.ticker,
            title=args.title,
            disclosed_on=date.fromisoformat(args.disclosed_on),
            url=args.url,
        )
    except (ValueError, OSError) as exc:
        print(f"登记失败: {exc}", file=sys.stderr)
        return 1
    append_index(record, Path(args.index))
    print(f"已登记: {record.title}（{record.disclosed_on}）")
    print(f"SHA-256: {record.sha256}")
    print(f"索引: {args.index}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stock-analysis",
        description="加载本地 CSV，做质量检查并计算指标或生成报告（离线）。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_stats = sub.add_parser("stats", help="计算基础市场指标")
    p_stats.add_argument("csv", help="OHLCV CSV 路径")
    p_stats.add_argument("--ticker", default="UNKNOWN", help="证券代码")
    p_stats.add_argument("--market", default="CN", help="市场代码（如 CN / NASDAQ）")
    p_stats.add_argument("--currency", default="CNY", help="币种（如 CNY / USD）")
    p_stats.add_argument(
        "--trading-days",
        type=int,
        default=Config().trading_days_per_year,
        help="年交易日数（按市场设置）",
    )
    p_stats.add_argument(
        "--skip-quality", action="store_true", help="跳过质量检查（仅用于调试）"
    )
    p_stats.add_argument(
        "--audit", metavar="PATH", default=None, help="将本次 analyze 动作记入审计 JSONL"
    )
    p_stats.set_defaults(func=_cmd_stats)

    p_report = sub.add_parser("report", help="生成结构化研究报告（Markdown/JSON）")
    p_report.add_argument("csv", help="OHLCV CSV 路径")
    p_report.add_argument("--ticker", default="UNKNOWN", help="证券代码")
    p_report.add_argument("--market", default="CN", help="市场代码（如 CN / NASDAQ）")
    p_report.add_argument("--currency", default="CNY", help="币种（如 CNY / USD）")
    p_report.add_argument(
        "--format", choices=["markdown", "json"], default="markdown", help="输出格式"
    )
    p_report.add_argument(
        "--save", metavar="PATH", default=None, help="同时保存报告 JSON 快照到该路径"
    )
    p_report.add_argument(
        "--skip-quality", action="store_true", help="跳过质量检查（仅用于调试）"
    )
    p_report.add_argument(
        "--audit", metavar="PATH", default=None, help="将本次 analyze 动作记入审计 JSONL"
    )
    p_report.set_defaults(func=_cmd_report)

    p_diff = sub.add_parser("diff", help="比较财报更新前后差异")
    p_diff.add_argument("before", help="更新前财务 JSON 路径")
    p_diff.add_argument("after", help="更新后财务 JSON 路径")
    p_diff.add_argument("--ticker", default="UNKNOWN", help="证券代码")
    p_diff.add_argument("--period", default="", help="报告期（如 2025Q4）")
    p_diff.add_argument(
        "--format", choices=["markdown", "json"], default="markdown", help="输出格式"
    )
    p_diff.set_defaults(func=_cmd_diff)

    p_review = sub.add_parser("review", help="生成复盘摘要（偏差统计）")
    p_review.add_argument("json", help="复盘日志 JSON 路径")
    p_review.set_defaults(func=_cmd_review)

    p_dash = sub.add_parser("dashboard", help="从报告快照生成只读 HTML 仪表盘")
    p_dash.add_argument("snapshots", nargs="+", help="报告快照 JSON 路径（可多个）")
    p_dash.add_argument(
        "--out", default="dashboard.html", help="输出 HTML 路径（默认 dashboard.html）"
    )
    p_dash.set_defaults(func=_cmd_dashboard)

    p_fetch = sub.add_parser("fetch", help="从 akshare 拉取 A 股日线存为 CSV（可选依赖）")
    p_fetch.add_argument("symbol", help="6 位股票代码，如 600000")
    p_fetch.add_argument("--start", required=True, help="开始日期 YYYY-MM-DD")
    p_fetch.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")
    p_fetch.add_argument(
        "--adjust",
        default="qfq",
        choices=["qfq", "hfq", ""],
        help="复权方式：qfq 前复权 / hfq 后复权 / 空字符串不复权",
    )
    p_fetch.add_argument(
        "--out", required=True, help="输出 CSV 路径（raw 层，不覆盖已有文件则自行指定）"
    )
    p_fetch.set_defaults(func=_cmd_fetch)

    p_port = sub.add_parser("portfolio", help="组合暴露与相关性分析（单币种）")
    p_port.add_argument("json", help="组合 JSON 路径")
    p_port.set_defaults(func=_cmd_portfolio)

    p_disc = sub.add_parser(
        "disclose", help="法定披露：公告检索（巨潮/上交所/深交所）或本地核验登记"
    )
    disc_sub = p_disc.add_subparsers(dest="disclose_action", required=True)
    p_dlist = disc_sub.add_parser("list", help="检索区间内公告元数据")
    p_dlist.add_argument("ticker", help="6 位股票代码，如 600000")
    p_dlist.add_argument(
        "--source", required=True, choices=["cninfo", "sse", "szse"],
        help="披露来源：cninfo 巨潮 / sse 上交所 / szse 深交所",
    )
    p_dlist.add_argument("--start", required=True, help="开始日期 YYYY-MM-DD")
    p_dlist.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")
    p_dlist.set_defaults(func=_cmd_disclose)
    p_dreg = disc_sub.add_parser("register", help="登记手动下载的公告文件")
    p_dreg.add_argument("file", help="公告文件路径（如 PDF）")
    p_dreg.add_argument("--ticker", required=True, help="证券代码")
    p_dreg.add_argument("--title", required=True, help="公告标题")
    p_dreg.add_argument(
        "--disclosed-on", required=True, dest="disclosed_on",
        help="披露日期 YYYY-MM-DD",
    )
    p_dreg.add_argument("--url", default=None, help="公告原文链接（可选）")
    p_dreg.add_argument(
        "--index", default="data/disclosures/index.jsonl",
        help="JSONL 索引路径（默认 data/disclosures/index.jsonl）",
    )
    p_dreg.set_defaults(func=_cmd_disclose)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

