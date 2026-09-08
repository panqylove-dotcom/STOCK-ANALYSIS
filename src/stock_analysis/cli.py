"""命令行入口：加载 -> 校验 -> 质量检查 -> 计算指标 / 生成报告（离线）。"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
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
    workbook = None
    if getattr(args, "financials", None):
        from .financials import load_financials

        try:
            workbook = load_financials(args.financials)
        except (OSError, ValueError) as exc:
            print(f"读取财务数据文件失败: {exc}", file=sys.stderr)
            return 1
        if workbook.currency != result.security.currency:
            print(
                f"财务数据与行情币种不一致: {workbook.currency} vs "
                f"{result.security.currency}；请先用 markets.convert 换算",
                file=sys.stderr,
            )
            return 1
    bars = result.bars
    metrics = market_metrics_from_bars(bars)
    try:
        _audit_analyze(args, result.source)
    except LicenseViolation as exc:
        print(f"许可检查未通过: {exc}", file=sys.stderr)
        return 4
    assumptions: list[str] = []
    if workbook is not None:
        assumptions.append(
            f"财务数据口径：币种={workbook.currency}，"
            f"会计准则={workbook.standard or '未登记'}，来源={workbook.source}"
        )
        data_gaps = []
        for metric in sorted(workbook.metrics):
            gaps = workbook.annual_gaps(metric)
            if gaps:
                data_gaps.append(f"{metric} 缺少年报数据: {'/'.join(gaps)}")
    else:
        data_gaps = ["示例数据未包含财务字段，估值与财务趋势需补充后生成。"]
    observations: list = []
    if getattr(args, "observe", None):
        try:
            observations = _parse_observe(args.observe)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    report = AnalysisReport(
        security=result.security,
        as_of=date.today().isoformat(),
        data_cutoff=result.source.accessed_at,
        market=metrics,
        financial_trends=workbook.to_trends() if workbook else [],
        observations=observations,
        assumptions=assumptions,
        data_gaps=data_gaps,
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


def _cmd_review_add(args) -> int:
    """向复盘日志追加一条复盘记录（自动计算偏差）。"""
    from .review import ReviewEntry, save_review_log

    try:
        date.fromisoformat(args.review_date)
    except ValueError:
        print(f"--review-date 日期格式错误: {args.review_date}", file=sys.stderr)
        return 1
    try:
        observations = _parse_observe(args.obs or [])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    entry = ReviewEntry(
        ticker=args.ticker,
        review_date=args.review_date,
        thesis=args.thesis or "",
        observation_conditions=observations,
        predicted_value=args.predicted,
        actual_value=args.actual,
        notes=args.note or "",
    )
    bias = entry.compute_bias()
    log_path = Path(args.json)
    try:
        entries = load_review_log(log_path) if log_path.exists() else []
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"读取复盘日志失败: {exc}", file=sys.stderr)
        return 1
    entries.append(entry)
    save_review_log(entries, log_path)
    bias_s = f"{bias:+.2%}" if bias is not None else "—"
    print(f"已追加复盘: {entry.ticker} @ {entry.review_date}（偏差 {bias_s}）")
    print(f"日志: {log_path}（共 {len(entries)} 条）")
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


def _cmd_watch(args) -> int:
    """聚合观察条件（只读；不修改任何文件）。"""
    from .review import load_report_snapshot, load_review_log
    from .watchlist import collect_watch_items, watch_json, watch_markdown

    reports = []
    for item in args.snapshots:
        try:
            reports.append(load_report_snapshot(item))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print(f"读取快照失败 {item}: {exc}", file=sys.stderr)
            return 1
    entries = []
    if args.review_log:
        try:
            entries = load_review_log(args.review_log)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print(f"读取复盘日志失败 {args.review_log}: {exc}", file=sys.stderr)
            return 1
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        print(f"--today 日期格式错误: {args.today}", file=sys.stderr)
        return 1
    items = collect_watch_items(reports, entries)
    if args.format == "json":
        payload = watch_json(items, today=today, stale_days=args.stale_days)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(watch_markdown(items, today=today, stale_days=args.stale_days))
    return 0


def _parse_observe(specs: list[str]) -> list:
    """--observe "描述|触发判据|阈值"（后两段可省略）。"""
    from .analysis import Observation

    out = []
    for spec in specs:
        parts = [p.strip() for p in spec.split("|")]
        if not parts or not parts[0] or len(parts) > 3:
            raise ValueError(f"--observe 格式错误: {spec!r}（应为 描述|判据|阈值）")
        out.append(
            Observation(
                description=parts[0],
                condition=parts[1] if len(parts) > 1 else parts[0],
                threshold=parts[2] if len(parts) > 2 else "",
            )
        )
    return out


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
        load_index,
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

    if args.disclose_action == "check":
        return _disclose_check(args)

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


def _disclose_check(args) -> int:
    """增量检查：以本地索引中该标的最新披露日期为基线，列出其后的新公告。

    索引无该标的记录时回看最近 --days 天；结果需人工核验后用 register 登记。
    """
    from .data.disclosures import fetch_announcements, load_index

    try:
        index_records = load_index(Path(args.index))
    except (ValueError, OSError) as exc:
        print(f"读取披露索引失败: {exc}", file=sys.stderr)
        return 1
    known = [r for r in index_records if r.ticker == args.ticker]
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        print(f"日期格式错误: {args.today}（应为 YYYY-MM-DD）", file=sys.stderr)
        return 1
    if known:
        start = max(r.disclosed_on for r in known)
        print(
            f"基线: 索引内 {args.ticker} 最新披露 {start}（已登记 {len(known)} 条）",
            file=sys.stderr,
        )
    else:
        start = today - timedelta(days=args.days)
        print(
            f"索引内无 {args.ticker} 记录，回看最近 {args.days} 天（{start} 起）",
            file=sys.stderr,
        )
    try:
        records = fetch_announcements(args.source, args.ticker, start=start, end=today)
    except (ValueError, OSError) as exc:
        print(f"披露增量检查失败: {exc}", file=sys.stderr)
        return 1
    seen = {(r.title, r.disclosed_on) for r in known}
    fresh = [r for r in records if (r.title, r.disclosed_on) not in seen]
    if args.save:
        code = _save_pending(fresh, args.save)
        if code:
            return code
    if not fresh:
        print("未发现新公告。")
        return 0
    print("| 披露日期 | 标题 | 链接 |")
    print("| --- | --- | --- |")
    for r in fresh:
        print(f"| {r.disclosed_on} | {r.title} | {r.url or '-'} |")
    print(
        f"新公告 {len(fresh)} 条；原文需人工核验，确认后可用 disclose register 登记",
        file=sys.stderr,
    )
    return 0


def _save_pending(records, save_path: str) -> int:
    """把新公告写成待核验清单 JSONL（供 watchlist/人工跟进复用）。"""
    from .data.disclosures import record_to_dict

    try:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(record_to_dict(r), ensure_ascii=False) for r in records
        ]
        Path(save_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    except (OSError, TypeError, ValueError) as exc:
        print(f"写入待核验清单失败 {save_path}: {exc}", file=sys.stderr)
        return 1
    print(f"待核验清单已保存: {save_path}（{len(records)} 条）")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # 兼容旧用法：`review <log.json>` 等价于 `review summary <log.json>`
    if (
        argv[:1] == ["review"]
        and argv[1:2]
        and argv[1] not in ("summary", "add")
        and not argv[1].startswith("-")
    ):
        argv = ["review", "summary", *argv[1:]]
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
    p_report.add_argument(
        "--financials", metavar="PATH", default=None,
        help="财务工作簿 JSON（data/financials/<TICKER>.json 约定格式），自动填充财务趋势",
    )
    p_report.add_argument(
        "--observe", action="append", default=None, metavar="SPEC",
        help='登记观察条件："描述|触发判据|阈值"（可多次）',
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

    p_review = sub.add_parser("review", help="复盘：摘要统计（summary）或追加记录（add）")
    review_sub = p_review.add_subparsers(dest="review_action", required=True)
    p_rsum = review_sub.add_parser("summary", help="生成复盘摘要（偏差统计）")
    p_rsum.add_argument("json", help="复盘日志 JSON 路径")
    p_rsum.set_defaults(func=_cmd_review)
    p_radd = review_sub.add_parser("add", help="追加一条复盘记录")
    p_radd.add_argument("json", help="复盘日志 JSON 路径（不存在则创建）")
    p_radd.add_argument("--ticker", required=True, help="证券代码")
    p_radd.add_argument(
        "--review-date", dest="review_date", required=True,
        help="复盘日期 YYYY-MM-DD",
    )
    p_radd.add_argument("--thesis", default="", help="研究命题（可选）")
    p_radd.add_argument(
        "--predicted", type=float, default=None, metavar="X",
        help="预测值（可选）",
    )
    p_radd.add_argument(
        "--actual", type=float, default=None, metavar="X", help="实际值（可选）",
    )
    p_radd.add_argument(
        "--obs", action="append", default=None, metavar="SPEC",
        help='观察条件："描述|触发判据|阈值"（可多次）',
    )
    p_radd.add_argument("--note", default="", help="备注（可选）")
    p_radd.set_defaults(func=_cmd_review_add)

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

    p_dcheck = disc_sub.add_parser(
        "check", help="增量检查：以本地索引基线列出该标的之后的新公告（只读）"
    )
    p_dcheck.add_argument("ticker", help="6 位股票代码，如 600000")
    p_dcheck.add_argument(
        "--source", required=True, choices=["cninfo", "sse", "szse"],
        help="披露来源：cninfo 巨潮 / sse 上交所 / szse 深交所",
    )
    p_dcheck.add_argument(
        "--index", default="data/disclosures/index.jsonl",
        help="JSONL 索引路径（默认 data/disclosures/index.jsonl）",
    )
    p_dcheck.add_argument(
        "--days", type=int, default=30,
        help="索引无该标的记录时的回看天数（默认 30）",
    )
    p_dcheck.add_argument(
        "--today", default=None,
        help="基准日期 YYYY-MM-DD（默认今天；用于可复现输出）",
    )
    p_dcheck.add_argument(
        "--save", metavar="PATH", default=None,
        help="把新公告写成待核验清单 JSONL（覆盖写；人工核验后再用 register 登记）",
    )
    p_dcheck.set_defaults(func=_cmd_disclose)

    p_watch = sub.add_parser(
        "watch", help="从报告快照/复盘日志聚合观察条件跟踪清单（只读）"
    )
    p_watch.add_argument("snapshots", nargs="+", help="报告快照 JSON 路径（可多个）")
    p_watch.add_argument(
        "--review-log", dest="review_log", default=None,
        help="复盘日志 JSON（可选，一并聚合观察条件）",
    )
    p_watch.add_argument(
        "--stale-days", dest="stale_days", type=int, default=90,
        help="复盘周期天数，超过则标注建议复盘（默认 90）",
    )
    p_watch.add_argument(
        "--today", default=None,
        help="基准日期 YYYY-MM-DD（默认今天；用于可复现输出）",
    )
    p_watch.add_argument(
        "--format", choices=["markdown", "json"], default="markdown",
        help="输出格式（默认 markdown）",
    )
    p_watch.set_defaults(func=_cmd_watch)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

