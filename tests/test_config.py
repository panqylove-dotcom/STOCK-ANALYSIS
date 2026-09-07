"""配置模块测试：加载、拒绝未知字段、快照往返。"""

import json

import pytest

from stock_analysis.config import CALCULATION_VERSION, Config


def test_default_config():
    cfg = Config()
    assert cfg.trading_days_per_year == 252
    assert cfg.risk_free_rate == 0.02
    assert cfg.calculation_version == CALCULATION_VERSION


def test_from_file_partial(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"trading_days_per_year": 244}), encoding="utf-8")
    cfg = Config.from_file(p)
    assert cfg.trading_days_per_year == 244
    assert cfg.risk_free_rate == 0.02  # 未提供字段使用默认值


def test_from_file_unknown_field_rejected(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"trading_days_per_year": 244, "typo_field": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="未知配置字段"):
        Config.from_file(p)


def test_to_file_roundtrip(tmp_path):
    p = tmp_path / "snapshot.json"
    Config(trading_days_per_year=244, risk_free_rate=0.01).to_file(p)
    loaded = Config.from_file(p)
    assert loaded.trading_days_per_year == 244
    assert loaded.risk_free_rate == 0.01

