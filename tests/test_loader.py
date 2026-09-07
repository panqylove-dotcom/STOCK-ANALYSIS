"""本地 CSV 加载器测试（离线）。"""

from pathlib import Path

import pytest

from stock_analysis.data.loader import CsvPriceLoader
from stock_analysis.models import PriceBar


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "raw" / "sample_prices.csv"


def test_loader_reads_sample():
    loader = CsvPriceLoader(market="CN", currency="CNY")
    result = loader.load(SAMPLE, ticker="SAMPLE")
    assert result.security.ticker == "SAMPLE"
    assert result.security.currency == "CNY"
    assert len(result.bars) >= 30
    assert all(isinstance(b, PriceBar) for b in result.bars)
    assert result.source.name.startswith("local-csv:")


def test_loader_records_license():
    loader = CsvPriceLoader(license_name="CC-BY-NC 4.0")
    result = loader.load(SAMPLE, ticker="SAMPLE")
    assert result.source.license_name == "CC-BY-NC 4.0"


def test_loader_default_license_personal_use():
    loader = CsvPriceLoader()
    result = loader.load(SAMPLE, ticker="SAMPLE")
    assert result.source.license_name == "personal-use only"


def test_loader_rejects_empty(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("date,open,high,low,close,volume\n", encoding="utf-8")
    loader = CsvPriceLoader()
    with pytest.raises(ValueError, match="无数据"):
        loader.load(p, ticker="X")


def test_loader_rejects_bad_ohlc(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text(
        "date,open,high,low,close,volume\n"
        "2026-01-05,10,9,8,10,100\n",
        encoding="utf-8",
    )
    loader = CsvPriceLoader()
    with pytest.raises(ValueError):
        loader.load(p, ticker="X")

