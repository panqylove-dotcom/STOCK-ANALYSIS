"""数据清洗：去重、缺失值、复权与交易日归一化。

所有函数保持纯函数语义，固定输入产生固定输出，便于测试与追溯。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from ..models import PriceBar


def validate_bars(bars: Iterable[PriceBar]) -> list[PriceBar]:
    """基础校验：日期单调、OHLC 关系合理、价格为非负。

    异常会被拒绝（抛出 ValueError），不静默修改数据。
    """
    out: list[PriceBar] = []
    prev_date: date | None = None
    for bar in bars:
        if bar.date is None:
            raise ValueError("日期缺失")
        if prev_date is not None and bar.date <= prev_date:
            raise ValueError(f"日期非单调递增: {prev_date} -> {bar.date}")
        if min(bar.open, bar.high, bar.low, bar.close) < 0:
            raise ValueError(f"价格为负: {bar}")
        if not (bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high):
            raise ValueError(f"OHLC 关系不合理: {bar}")
        prev_date = bar.date
        out.append(bar)
    return out


def dedupe_bars(bars: Iterable[PriceBar]) -> list[PriceBar]:
    """按日期去重；同日期重复记录仅保留最后一条（视为来源更新覆盖）。"""
    by_date: dict[date, PriceBar] = {}
    for bar in bars:
        by_date[bar.date] = bar
    return [by_date[d] for d in sorted(by_date)]


def fill_missing_with_previous_close(
    bars: Iterable[PriceBar], start: date, end: date
) -> list[PriceBar]:
    """把区间内缺失的交易日用上一交易日收盘价填充（前向填充）。

    用于处理停牌或个别缺失交易日；真实数据源接入后应优先使用交易日历。
    """
    sorted_bars = sorted(bars, key=lambda b: b.date)
    if not sorted_bars:
        raise ValueError("无数据可填充")
    out: list[PriceBar] = []
    cursor = start
    idx = 0
    prev_close: float | None = None
    while cursor <= end:
        # 跳过 weekend，简化示例：真实场景应使用交易日历
        if cursor.weekday() >= 5:
            cursor += timedelta(days=1)
            continue
        if idx < len(sorted_bars) and sorted_bars[idx].date == cursor:
            bar = sorted_bars[idx]
            prev_close = bar.close
            out.append(bar)
            idx += 1
        else:
            if prev_close is None:
                raise ValueError(f"起始日 {cursor} 之前无数据，无法前向填充")
            out.append(
                PriceBar(
                    date=cursor,
                    open=prev_close,
                    high=prev_close,
                    low=prev_close,
                    close=prev_close,
                    volume=0.0,
                    adjusted=True,
                )
            )
        cursor += timedelta(days=1)
    return out


def resample_daily(bars: Iterable[PriceBar], interval: str = "D") -> list[PriceBar]:
    """按周期重采样。当前仅支持 'D'（日线），其余抛出不支持错误。"""
    if interval != "D":
        raise NotImplementedError(f"暂不支持周期: {interval}")
    return validate_bars(bars)

