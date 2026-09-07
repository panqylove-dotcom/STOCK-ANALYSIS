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
    assert "## 11. 免责声明" in result.stdout


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

