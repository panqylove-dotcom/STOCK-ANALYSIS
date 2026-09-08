"""CLI 冒烟测试：基于内置示例数据离线运行。"""

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CSV = ROOT / "data" / "raw" / "sample_prices.csv"


def test_cli_runs_on_sample_csv():
    assert SAMPLE_CSV.exists(), f"缺少示例数据: {SAMPLE_CSV}"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", "stats", str(SAMPLE_CSV)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "数据质量检查" in result.stderr
    assert "来源:" in result.stdout
    assert "区间收益率" in result.stdout
    assert "年化波动率" in result.stdout
    assert "最大回撤" in result.stdout


def test_cli_flags_quality_failure_on_bad_csv(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "date,open,high,low,close,volume\n"
        "2026-01-05,10,11,9,10,-100\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", "stats", str(bad), "--ticker", "BAD"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 2, result.stdout
    assert "质量检查未通过" in result.stderr


def test_cli_skip_quality_forces_through(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "date,open,high,low,close,volume\n"
        "2026-01-05,10,11,9,10,-100\n"
        "2026-01-06,10,11,9,10,1000\n"
        "2026-01-07,10,11,9,10,1000\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "stock_analysis.cli",
            "stats",
            str(bad),
            "--skip-quality",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "区间收益率" in result.stdout


def test_cli_structure_error_returns_1(tmp_path):
    bad = tmp_path / "bad_ohlc.csv"
    bad.write_text(
        "date,open,high,low,close,volume\n"
        "2026-01-05,10,9,8,10,100\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", "stats", str(bad)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 1
    assert "结构错误" in result.stderr


def test_cli_report_markdown():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", "report", str(SAMPLE_CSV)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "研究报告" in result.stdout
    assert "## 12. 免责声明" in result.stdout


def test_cli_report_json():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "stock_analysis.cli",
            "report",
            str(SAMPLE_CSV),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    import json

    data = json.loads(result.stdout)
    assert data["security"]["ticker"] == "UNKNOWN"
    assert "market" in data


def test_cli_report_save_snapshot(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    out = tmp_path / "snapshot.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "stock_analysis.cli",
            "report",
            str(SAMPLE_CSV),
            "--format",
            "json",
            "--save",
            str(out),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()
    assert "报告快照已保存" in result.stderr


def test_cli_diff(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text('{"revenue": 100.0, "net_profit": 10.0}', encoding="utf-8")
    after.write_text('{"revenue": 120.0, "net_profit": 12.0}', encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "stock_analysis.cli",
            "diff",
            str(before),
            str(after),
            "--ticker",
            "TEST",
            "--period",
            "2025Q4",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "| revenue | 100.00 | 120.00 | +20.00 | +20.0% |" in result.stdout


def test_cli_review(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    log = tmp_path / "review.json"
    log.write_text(
        '[{"ticker": "A", "review_date": "2026-09-04", '
        '"predicted_value": 110.0, "actual_value": 100.0}]',
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", "review", str(log)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "## 方法稳定性" in result.stdout
    assert "命中率" in result.stdout


def test_cli_dashboard(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    snapshot = tmp_path / "snapshot.json"
    out = tmp_path / "dash.html"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "stock_analysis.cli",
            "report",
            str(SAMPLE_CSV),
            "--format",
            "json",
            "--save",
            str(snapshot),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "stock_analysis.cli",
            "dashboard",
            str(snapshot),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()
    assert "只读" in result.stdout
    content = out.read_text(encoding="utf-8")
    assert "<table>" in content
    assert "不构成投资建议" in content


def test_cli_dashboard_bad_snapshot(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", "dashboard", str(bad)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 1
    assert "读取快照失败" in result.stderr

# 说明：fetch 子命令需要网络（akshare 在线拉取），遵循测试离线原则，
# 不在此处做端到端测试；拉取逻辑由 tests/test_fetchers.py 的 mock 测试覆盖。


def _run_cli(*argv, env_extra=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", *argv],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )


def test_cli_portfolio_with_returns(tmp_path):
    data = {
        "positions": [
            {"ticker": "A", "market": "CN", "currency": "CNY", "market_value": 600},
            {"ticker": "B", "market": "CN", "currency": "CNY", "market_value": 400},
        ],
        "returns": {
            "A": [0.01, 0.02, -0.01, 0.03],
            "B": [0.02, 0.01, 0.00, 0.01],
        },
    }
    p = tmp_path / "portfolio.json"
    import json as _json

    p.write_text(_json.dumps(data), encoding="utf-8")
    result = _run_cli("portfolio", str(p))
    assert result.returncode == 0, result.stderr
    assert "max_weight" in result.stdout
    assert "| A | 60.00% |" in result.stdout
    assert "A vs B" in result.stdout


def test_cli_portfolio_currency_mismatch(tmp_path):
    data = {
        "positions": [
            {"ticker": "A", "market": "CN", "currency": "CNY", "market_value": 600},
            {"ticker": "B", "market": "NASDAQ", "currency": "USD", "market_value": 400},
        ]
    }
    p = tmp_path / "portfolio.json"
    import json as _json

    p.write_text(_json.dumps(data), encoding="utf-8")
    result = _run_cli("portfolio", str(p))
    assert result.returncode == 1
    assert "币种不一致" in result.stderr


def test_cli_stats_audit_records_analyze(tmp_path):
    audit = tmp_path / "audit.jsonl"
    result = _run_cli(
        "stats",
        str(SAMPLE_CSV),
        "--ticker",
        "SAMPLE",
        "--audit",
        str(audit),
    )
    assert result.returncode == 0, result.stderr
    assert audit.exists()
    assert "analyze" in audit.read_text(encoding="utf-8")


# --- 进程内 CLI 测试：与覆盖率统计同进程，覆盖各子命令主路径 ----------------

import json  # noqa: E402

import pytest  # noqa: E402

from stock_analysis.cli import main as cli_main  # noqa: E402


def test_ip_stats_ok(capsys):
    assert cli_main(["stats", str(SAMPLE_CSV), "--ticker", "SAMPLE"]) == 0
    out = capsys.readouterr().out
    assert "区间收益率" in out and "最大回撤" in out


def test_ip_stats_structure_error_returns_1(tmp_path, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "date,open,high,low,close,volume\n2026-01-05,10,9,8,10,100\n",
        encoding="utf-8",
    )
    assert cli_main(["stats", str(bad)]) == 1
    assert "结构错误" in capsys.readouterr().err


def test_ip_stats_quality_fail_returns_2_and_skip_forces(tmp_path, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "date,open,high,low,close,volume\n"
        "2026-01-05,10,11,9,10,-100\n"
        "2026-01-06,10,11,9,10,1000\n"
        "2026-01-07,10,11,9,10,1000\n",
        encoding="utf-8",
    )
    assert cli_main(["stats", str(bad), "--ticker", "BAD"]) == 2
    assert "质量检查未通过" in capsys.readouterr().err
    assert cli_main(
        ["stats", str(bad), "--ticker", "BAD", "--skip-quality"]
    ) == 0


def test_ip_stats_audit_writes_analyze(tmp_path):
    audit = tmp_path / "audit.jsonl"
    assert cli_main(
        ["stats", str(SAMPLE_CSV), "--ticker", "SAMPLE", "--audit", str(audit)]
    ) == 0
    assert "analyze" in audit.read_text(encoding="utf-8")


def test_ip_diff_markdown_json_and_bad_file(tmp_path, capsys):
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text('{"revenue": 100.0}', encoding="utf-8")
    after.write_text('{"revenue": 120.0}', encoding="utf-8")
    assert cli_main(
        ["diff", str(before), str(after), "--ticker", "T", "--period", "2025Q4"]
    ) == 0
    assert "+20.0%" in capsys.readouterr().out
    assert cli_main(
        ["diff", str(before), str(after), "--format", "json"]
    ) == 0
    import json as _json

    assert _json.loads(capsys.readouterr().out)["diffs"][0]["pct_change"] == pytest.approx(0.2)
    assert cli_main(["diff", str(before), str(tmp_path / "nope.json")]) == 1
    assert "读取财务 JSON 失败" in capsys.readouterr().err


def test_ip_review_bad_log_returns_1(tmp_path, capsys):
    log = tmp_path / "log.json"
    log.write_text("{broken", encoding="utf-8")
    assert cli_main(["review", "summary", str(log)]) == 1
    assert "读取复盘日志失败" in capsys.readouterr().err


def test_ip_dashboard_ok_and_bad_snapshot(tmp_path, capsys):
    snap = tmp_path / "snap.json"
    assert cli_main(
        ["report", str(SAMPLE_CSV), "--format", "json", "--save", str(snap)]
    ) == 0
    out = tmp_path / "dash.html"
    capsys.readouterr()
    assert cli_main(["dashboard", str(snap), "--out", str(out)]) == 0
    assert "仪表盘已保存" in capsys.readouterr().out
    assert "不构成投资建议" in out.read_text(encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert cli_main(["dashboard", str(bad)]) == 1
    assert "读取快照失败" in capsys.readouterr().err


def test_ip_portfolio_paths(tmp_path, capsys):
    good = tmp_path / "p.json"
    good.write_text(json.dumps({
        "positions": [
            {"ticker": "A", "market": "CN", "currency": "CNY", "market_value": 600},
            {"ticker": "B", "market": "CN", "currency": "CNY", "market_value": 400},
        ],
        "returns": {"A": [0.01, 0.02, -0.01], "B": [0.02, 0.01, 0.0]},
    }), encoding="utf-8")
    assert cli_main(["portfolio", str(good)]) == 0
    out = capsys.readouterr().out
    assert "| A | 60.00% |" in out and "A vs B" in out

    mismatch = tmp_path / "m.json"
    mismatch.write_text(json.dumps({"positions": [
        {"ticker": "A", "market": "CN", "currency": "CNY", "market_value": 1},
        {"ticker": "B", "market": "NASDAQ", "currency": "USD", "market_value": 1},
    ]}), encoding="utf-8")
    assert cli_main(["portfolio", str(mismatch)]) == 1
    assert "币种不一致" in capsys.readouterr().err

    fields = tmp_path / "f.json"
    fields.write_text('{"positions": [{"ticker": "A"}]}', encoding="utf-8")
    assert cli_main(["portfolio", str(fields)]) == 1
    assert "组合字段错误" in capsys.readouterr().err

    broken = tmp_path / "broken.json"
    broken.write_text("{oops", encoding="utf-8")
    assert cli_main(["portfolio", str(broken)]) == 1
    assert "读取组合 JSON 失败" in capsys.readouterr().err


def test_ip_fetch_paths(monkeypatch, tmp_path, capsys):
    from datetime import date as _date

    from stock_analysis.data import fetchers as fs

    orig = fs.akshare_daily_cn

    def fake_daily(symbol, *, start, end, adjust="qfq"):
        rows = [
            {"日期": "2026-09-01", "开盘": 10.0, "收盘": 10.5, "最高": 10.8,
             "最低": 9.9, "成交量": 12000},
        ]
        return orig(symbol, start=start, end=end, fetch_fn=lambda *a, **k: rows)

    monkeypatch.setattr(fs, "akshare_daily_cn", fake_daily)
    out_csv = tmp_path / "sub" / "x.csv"
    code = cli_main([
        "fetch", "600000", "--start", "2026-09-01", "--end", "2026-09-01",
        "--out", str(out_csv),
    ])
    assert code == 0
    assert "已保存 1 条日线" in capsys.readouterr().out
    assert out_csv.read_text(encoding="utf-8").startswith("date,open,high,low,close,volume")

    def boom(symbol, **kwargs):
        raise ValueError("接口无数据")

    monkeypatch.setattr(fs, "akshare_daily_cn", boom)
    code = cli_main([
        "fetch", "600000", "--start", "2026-09-01", "--end", "2026-09-01",
        "--out", str(tmp_path / "y.csv"),
    ])
    assert code == 1
    assert "拉取失败" in capsys.readouterr().err

    def no_ak(symbol, **kwargs):
        raise ImportError("pip install stock-analysis[akshare]")

    monkeypatch.setattr(fs, "akshare_daily_cn", no_ak)
    code = cli_main([
        "fetch", "600000", "--start", "2026-09-01", "--end", "2026-09-01",
        "--out", str(tmp_path / "z.csv"),
    ])
    assert code == 3
    assert "akshare" in capsys.readouterr().err

