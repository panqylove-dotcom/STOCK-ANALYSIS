"""review summary/add CLI 测试。"""

import json

from stock_analysis.cli import main as cli_main
from stock_analysis.review import Observation, load_review_log


def test_review_add_creates_log(tmp_path, capsys):
    log = tmp_path / "log.json"
    code = cli_main([
        "review", "add", str(log),
        "--ticker", "600000", "--review-date", "2026-09-08",
        "--predicted", "110", "--actual", "100", "--note", "高估",
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "偏差 +10.00%" in out
    entries = load_review_log(log)
    assert len(entries) == 1
    assert entries[0].notes == "高估"
    assert entries[0].bias is not None


def test_review_add_appends_and_keeps_existing(tmp_path, capsys):
    log = tmp_path / "log.json"
    log.write_text(
        '[{"ticker": "A", "review_date": "2026-08-01", '
        '"observation_conditions": [{"description": "d", "condition": "c"}], '
        '"predicted_value": 10.0, "actual_value": 10.0}]',
        encoding="utf-8",
    )
    code = cli_main([
        "review", "add", str(log),
        "--ticker", "B", "--review-date", "2026-09-08",
        "--obs", "价改落地|公告披露提价|提价>=5%",
    ])
    assert code == 0
    capsys.readouterr()
    entries = load_review_log(log)
    assert [e.ticker for e in entries] == ["A", "B"]
    obs = entries[1].observation_conditions
    assert len(obs) == 1 and isinstance(obs[0], Observation)
    assert obs[0].threshold == "提价>=5%"


def test_review_add_bad_date_returns_1(tmp_path, capsys):
    code = cli_main([
        "review", "add", str(tmp_path / "log.json"),
        "--ticker", "A", "--review-date", "2026/09/08",
    ])
    assert code == 1
    assert "日期格式错误" in capsys.readouterr().err


def test_review_add_corrupt_log_returns_1(tmp_path, capsys):
    log = tmp_path / "log.json"
    log.write_text("{broken", encoding="utf-8")
    code = cli_main([
        "review", "add", str(log), "--ticker", "A",
        "--review-date", "2026-09-08",
    ])
    assert code == 1
    assert "读取复盘日志失败" in capsys.readouterr().err


def test_review_legacy_positional_still_summarizes(tmp_path, capsys):
    log = tmp_path / "log.json"
    log.write_text(
        '[{"ticker": "A", "review_date": "2026-09-04", '
        '"predicted_value": 110.0, "actual_value": 100.0}]',
        encoding="utf-8",
    )
    code = cli_main(["review", str(log)])  # 旧用法兼容
    assert code == 0
    assert "方法稳定性" in capsys.readouterr().out


def test_review_summary_subcommand(tmp_path, capsys):
    log = tmp_path / "log.json"
    log.write_text("[]", encoding="utf-8")
    code = cli_main(["review", "summary", str(log)])
    assert code == 0
    assert "复盘日志" in capsys.readouterr().out


def test_review_add_then_watch(tmp_path, capsys):
    """review add 的观察条件应能进入 watch 清单。"""
    from stock_analysis.review import ReviewEntry, save_review_log
    from stock_analysis.analysis import AnalysisReport
    from stock_analysis.models import Security
    from stock_analysis.review import save_report_snapshot

    log = tmp_path / "log.json"
    code = cli_main([
        "review", "add", str(log),
        "--ticker", "600000", "--review-date", "2026-09-08",
        "--obs", "中报增速|营收同比>10%|10%",
    ])
    assert code == 0
    capsys.readouterr()
    snap = tmp_path / "snap.json"
    save_report_snapshot(
        AnalysisReport(
            security=Security(ticker="600000", market="CN", currency="CNY"),
            as_of="2026-09-08",
            data_cutoff="2026-09-08T00:00:00+08:00",
        ),
        snap,
    )
    code = cli_main(["watch", str(snap), "--review-log", str(log), "--today", "2026-09-08"])
    assert code == 0
    out = capsys.readouterr().out
    assert "中报增速" in out and "review" in out
