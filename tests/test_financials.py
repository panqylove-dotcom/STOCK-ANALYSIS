"""财务工作簿离线测试 + report --financials 集成。"""

import json
from pathlib import Path

import pytest

from stock_analysis.cli import main as cli_main
from stock_analysis.financials import (
    load_financials,
    period_sort_key,
    save_financials,
)

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_FIN = ROOT / "data" / "financials" / "SAMPLE.json"
SAMPLE_CSV = ROOT / "data" / "raw" / "sample_prices.csv"


def write(tmp_path, data):
    p = tmp_path / "fin.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_period_sort_key_ordering():
    keys = ["2024", "2023Q4", "2023H1", "2023", "2023H2", "2023Q1"]
    assert sorted(keys, key=period_sort_key) == [
        "2023", "2023Q1", "2023H1", "2023Q4", "2023H2", "2024",
    ]


def test_period_sort_key_invalid():
    with pytest.raises(ValueError):
        period_sort_key("FY2023")


def test_load_trends_and_latest(tmp_path):
    p = write(tmp_path, {
        "currency": "CNY", "standard": "CAS", "source": "2025年报",
        "metrics": {
            "revenue": {"2022": 100.0, "2023": 120.0, "2024": 90.0},
            "net_profit": {"2023": 10.0, "2024": None, "2025": 18.0},
        },
    })
    wb = load_financials(p)
    trends = {t.metric: t for t in wb.to_trends()}
    rev = trends["revenue"]
    assert rev.periods == ["2022", "2023", "2024"]
    assert rev.yoy_changes[0] == pytest.approx(0.2)
    assert rev.yoy_changes[1] == pytest.approx(-0.25)
    assert wb.latest("net_profit") == 18.0  # 跳过 null 取最近非空


def test_quarter_periods_sorted(tmp_path):
    p = write(tmp_path, {
        "currency": "CNY", "source": "季报",
        "metrics": {"revenue": {"2024Q2": 5.0, "2024Q1": 4.0}},
    })
    wb = load_financials(p)
    assert wb.sorted_periods("revenue") == ["2024Q1", "2024Q2"]


def test_annual_gaps(tmp_path):
    p = write(tmp_path, {
        "currency": "CNY", "source": "s",
        "metrics": {
            "revenue": {"2021": 1.0, "2023": 3.0, "2025": 5.0},
            "fcf": {"2024Q1": 1.0, "2024Q3": 2.0},
        },
    })
    wb = load_financials(p)
    assert wb.annual_gaps("revenue") == ["2022", "2024"]
    assert wb.annual_gaps("fcf") == []  # 季度序列不做年度缺口判定


@pytest.mark.parametrize("bad,frag", [
    ({"currency": "", "source": "s", "metrics": {"a": {"2023": 1.0}}}, "currency"),
    ({"currency": "CNY", "source": "", "metrics": {"a": {"2023": 1.0}}}, "source"),
    ({"currency": "CNY", "source": "s", "metrics": {}}, "metrics"),
    ({"currency": "CNY", "source": "s", "metrics": {"a": {"2023": "abc"}}}, "不是数字"),
    ({"currency": "CNY", "source": "s", "metrics": {"a": {"FY23": 1.0}}}, "报告期"),
])
def test_validation_errors(tmp_path, bad, frag):
    with pytest.raises(ValueError, match=frag):
        load_financials(write(tmp_path, bad))


def test_save_roundtrip(tmp_path):
    p = write(tmp_path, {
        "currency": "CNY", "standard": "CAS", "source": "s",
        "metrics": {"b": {"2023Q2": 2.0, "2023Q1": 1.0}, "a": {"2023": 9.0}},
    })
    wb = load_financials(p)
    out = tmp_path / "out" / "wb.json"
    save_financials(wb, out)
    assert load_financials(out) == wb
    text = out.read_text(encoding="utf-8")
    assert text.index('"a"') < text.index('"b"')  # 指标键稳定排序


# --- CLI 集成 ---------------------------------------------------------------

def test_cli_report_with_financials(capsys):
    code = cli_main([
        "report", str(SAMPLE_CSV), "--ticker", "SAMPLE",
        "--financials", str(SAMPLE_FIN),
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "财务趋势" in out
    assert "revenue" in out and "CAGR" in out
    assert "财务数据口径" in out  # 假设区登记币种/准则/来源


def test_cli_report_financials_missing_nulls_reported(tmp_path, capsys):
    p = write(tmp_path, {
        "currency": "CNY", "standard": "CAS", "source": "s",
        "metrics": {"revenue": {"2021": 1.0, "2025": 5.0}},
    })
    code = cli_main([
        "report", str(SAMPLE_CSV), "--ticker", "SAMPLE", "--financials", str(p),
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "revenue 缺少年报数据: 2022/2023/2024" in out


def test_cli_report_financials_currency_mismatch(tmp_path, capsys):
    p = write(tmp_path, {
        "currency": "USD", "standard": "US GAAP", "source": "10-K",
        "metrics": {"revenue": {"2025": 1.0}},
    })
    code = cli_main([
        "report", str(SAMPLE_CSV), "--ticker", "SAMPLE", "--financials", str(p),
    ])
    assert code == 1
    assert "币种不一致" in capsys.readouterr().err


def test_cli_report_financials_bad_file(tmp_path, capsys):
    p = tmp_path / "broken.json"
    p.write_text("{", encoding="utf-8")
    code = cli_main([
        "report", str(SAMPLE_CSV), "--ticker", "SAMPLE", "--financials", str(p),
    ])
    assert code == 1
    assert "读取财务数据文件失败" in capsys.readouterr().err
