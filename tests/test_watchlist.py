"""观察条件与观察清单测试（含 CLI report --observe / watch 集成）。"""

import json
from datetime import date
from pathlib import Path

from stock_analysis.analysis import AnalysisReport, Observation
from stock_analysis.cli import main as cli_main
from stock_analysis.models import Security
from stock_analysis.review import (
    ReviewEntry,
    load_report_snapshot,
    save_report_snapshot,
    save_review_log,
)
from stock_analysis.watchlist import collect_watch_items, watch_markdown

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CSV = ROOT / "data" / "raw" / "sample_prices.csv"


def make_report(ticker="600000", as_of="2026-01-01", status="待观察"):
    return AnalysisReport(
        security=Security(ticker=ticker, market="CN", currency="CNY"),
        as_of=as_of,
        data_cutoff="2026-01-01T00:00:00+08:00",
        observations=[
            Observation("营收增速", "年报营收增速>10%", "10%", status)
        ],
    )


def test_observations_markdown_and_roundtrip(tmp_path):
    report = make_report()
    md = report.to_markdown()
    assert "## 3. 观察条件" in md
    assert "营收增速" in md and "年报营收增速>10%" in md
    snap = tmp_path / "snap.json"
    save_report_snapshot(report, snap)
    loaded = load_report_snapshot(snap)
    assert loaded.observations == report.observations
    assert isinstance(loaded.observations[0], Observation)


def test_collect_items_from_reports_and_reviews():
    entries = [
        ReviewEntry(
            ticker="000001",
            review_date="2026-08-01",
            observation_conditions=[Observation("净利转正", "半年报净利>0")],
        )
    ]
    items = collect_watch_items([make_report()], entries)
    assert [(i.ticker, i.origin) for i in items] == [
        ("000001", "review"), ("600000", "report"),
    ]


def test_watch_markdown_flags_stale_pending():
    items = collect_watch_items([make_report(as_of="2026-01-01")], [])
    md = watch_markdown(items, today=date(2026, 9, 8), stale_days=90)
    assert "## 600000" in md
    assert "超过复盘周期" in md
    assert "待观察 1 条" in md


def test_watch_markdown_fresh_not_flagged():
    items = collect_watch_items([make_report(as_of="2026-09-01")], [])
    md = watch_markdown(items, today=date(2026, 9, 8), stale_days=90)
    assert "超过复盘周期" not in md


def test_watch_markdown_empty():
    md = watch_markdown([], today=date(2026, 9, 8))
    assert "暂无观察条件" in md


def test_review_log_observation_roundtrip(tmp_path):
    entries = [
        ReviewEntry(
            ticker="A",
            review_date="2026-08-01",
            observation_conditions=[Observation("c1", "cond", "thr")],
        )
    ]
    p = tmp_path / "log.json"
    save_review_log(entries, p)
    from stock_analysis.review import load_review_log

    loaded = load_review_log(p)
    assert loaded[0].observation_conditions[0].threshold == "thr"


def test_cli_report_observe_then_watch(tmp_path, capsys):
    snap = tmp_path / "snap.json"
    code = cli_main([
        "report", str(SAMPLE_CSV), "--ticker", "SAMPLE",
        "--observe", "估值修复|PE回到历史中位以上|中位PE",
        "--observe", "订单回暖|季报合同负债环比转正",
        "--save", str(snap), "--format", "json",
    ])
    assert code == 0
    capsys.readouterr()
    data = json.loads(snap.read_text(encoding="utf-8"))
    assert len(data["observations"]) == 2
    assert data["observations"][0]["threshold"] == "中位PE"
    assert data["observations"][1]["condition"] == "季报合同负债环比转正"

    code = cli_main(["watch", str(snap), "--today", "2026-09-08"])
    assert code == 0
    out = capsys.readouterr().out
    assert "观察清单" in out and "估值修复" in out and "待观察 2 条" in out


def test_cli_watch_with_review_log(tmp_path, capsys):
    log = tmp_path / "log.json"
    save_review_log(
        [ReviewEntry(
            ticker="R1", review_date="2026-08-20",
            observation_conditions=[Observation("价改落地", "公告披露提价")],
        )],
        log,
    )
    code = cli_main([
        "watch", str(_empty_snapshot(tmp_path)), "--review-log", str(log),
        "--today", "2026-09-08",
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "R1" in out and "价改落地" in out


def _empty_snapshot(tmp_path) -> Path:
    p = tmp_path / "empty.json"
    save_report_snapshot(make_report(ticker="X0", as_of="2026-09-05"), p)
    # 清空观察条件，只验证 review-log 聚合路径
    data = json.loads(p.read_text(encoding="utf-8"))
    data["observations"] = []
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_cli_watch_bad_snapshot_returns_1(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    code = cli_main(["watch", str(bad)])
    assert code == 1
    assert "读取快照失败" in capsys.readouterr().err


def test_cli_watch_bad_today_returns_1(tmp_path, capsys):
    snap = tmp_path / "s.json"
    save_report_snapshot(make_report(), snap)
    code = cli_main(["watch", str(snap), "--today", "not-a-date"])
    assert code == 1
    assert "日期格式错误" in capsys.readouterr().err


def test_cli_report_bad_observe_spec_returns_1(capsys):
    code = cli_main([
        "report", str(SAMPLE_CSV), "--ticker", "SAMPLE",
        "--observe", "a|b|c|d",
    ])
    assert code == 1
    assert "--observe 格式错误" in capsys.readouterr().err


# --- watch JSON 输出与新鲜度 ------------------------------------------------

def test_ticker_freshness_stale_only_with_pending():
    from stock_analysis.watchlist import ticker_freshness

    stale_pending = collect_watch_items([make_report(as_of="2026-01-01")], [])
    fresh_done = collect_watch_items(
        [make_report(ticker="600001", as_of="2026-01-01", status="已触发")], []
    )
    info = ticker_freshness(
        stale_pending + fresh_done, today=date(2026, 9, 8), stale_days=90
    )
    assert info["600000"]["stale"] is True
    assert info["600000"]["age_days"] == (date(2026, 9, 8) - date(2026, 1, 1)).days
    # 超期但没有待观察条件 -> 不标 stale
    assert info["600001"]["stale"] is False


def test_cli_watch_json_format(tmp_path, capsys):
    snap = tmp_path / "snap.json"
    save_report_snapshot(make_report(as_of="2026-01-01"), snap)
    code = cli_main([
        "watch", str(snap), "--today", "2026-09-08", "--format", "json",
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "watchlist-v1"
    assert payload["total"] == 1 and payload["pending_total"] == 1
    assert payload["stale_tickers"] == ["600000"]
    assert payload["tickers"]["600000"]["latest_as_of"] == "2026-01-01"
    assert payload["items"][0]["description"] == "营收增速"
    assert "不构成投资建议" in payload["disclaimer"]
