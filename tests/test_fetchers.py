"""行情源适配器测试：注入 mock，不联网。"""

from datetime import date

import pytest

from stock_analysis.data.fetchers import akshare_daily_cn


def _mock_cn_rows(sym: str, s: date, e: date) -> list[dict]:
    return [
        {
            "日期": "2026-09-01",
            "开盘": 10.0,
            "收盘": 10.5,
            "最高": 10.8,
            "最低": 9.9,
            "成交量": 12000,
        },
        {
            "日期": "2026-09-02",
            "开盘": 10.5,
            "收盘": 11.0,
            "最高": 11.2,
            "最低": 10.4,
            "成交量": 15000,
        },
    ]


def test_mock_fetch_cn_daily():
    result = akshare_daily_cn(
        "600000",
        start=date(2026, 9, 1),
        end=date(2026, 9, 2),
        fetch_fn=_mock_cn_rows,
    )
    assert result.security.currency == "CNY"
    assert len(result.bars) == 2
    assert result.bars[0].close == pytest.approx(10.5)
    assert result.bars[0].adjusted is True  # 默认前复权
    assert "akshare" in result.source.name
    assert "法定披露未核验" in result.source.license_name


def test_mock_fetch_english_columns():
    def rows(sym, s, e):
        return [
            {
                "date": "2026-09-01",
                "open": 1,
                "close": 2,
                "high": 3,
                "low": 0.5,
                "volume": 100,
            }
        ]

    result = akshare_daily_cn(
        "000001", start=date(2026, 9, 1), end=date(2026, 9, 1), fetch_fn=rows
    )
    assert result.bars[0].high == pytest.approx(3.0)


def test_mock_fetch_empty_raises():
    with pytest.raises(ValueError, match="未返回数据"):
        akshare_daily_cn(
            "600000",
            start=date(2026, 9, 1),
            end=date(2026, 9, 2),
            fetch_fn=lambda *a, **k: [],
        )


def test_mock_fetch_missing_field_raises():
    def rows(sym, s, e):
        return [{"日期": "2026-09-01", "开盘": 1}]

    with pytest.raises(ValueError, match="缺少字段"):
        akshare_daily_cn(
            "600000", start=date(2026, 9, 1), end=date(2026, 9, 1), fetch_fn=rows
        )


def test_no_akshare_installed_gives_helpful_import_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "akshare":
            raise ImportError("no akshare")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError, match="stock-analysis\\[akshare\\]"):
        akshare_daily_cn("600000", start=date(2026, 9, 1), end=date(2026, 9, 2))


def test_retry_then_success():
    calls = {"n": 0}

    def flaky(sym, s, e):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("瞬时网络错误")
        return _mock_cn_rows(sym, s, e)

    slept: list[float] = []
    result = akshare_daily_cn(
        "600000",
        start=date(2026, 9, 1),
        end=date(2026, 9, 2),
        fetch_fn=flaky,
        retries=3,
        backoff_seconds=0.01,
        sleep=slept.append,
    )
    assert len(result.bars) == 2
    assert calls["n"] == 3
    assert slept == [0.01, 0.02]  # 指数退避


def test_retry_exhausted_raises():
    def always_fail(sym, s, e):
        raise ConnectionError("持续失败")

    with pytest.raises(ValueError, match="重试 2 次"):
        akshare_daily_cn(
            "600000",
            start=date(2026, 9, 1),
            end=date(2026, 9, 2),
            fetch_fn=always_fail,
            retries=2,
            backoff_seconds=0.0,
            sleep=lambda s: None,
        )

