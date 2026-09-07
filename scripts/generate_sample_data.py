"""生成确定性示例行情数据（data/raw/sample_prices.csv）。

使用固定随机种子，保证输出可复现，测试不依赖在线服务。
运行方式: python scripts/generate_sample_data.py
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path


def generate(
    start: date,
    trading_days: int,
    seed: int = 42,
) -> list[tuple[str, float, float, float, float, int]]:
    """生成 trading_days 个交易日的 OHLCV 数据（跳过周末）。"""
    rng = random.Random(seed)
    rows: list[tuple[str, float, float, float, float, int]] = []
    d = start
    price = 100.0
    produced = 0
    while produced < trading_days:
        if d.weekday() < 5:
            o = round(price, 2)
            daily_return = rng.uniform(-0.02, 0.02)
            c = round(o * (1 + daily_return), 2)
            high = round(max(o, c) * (1 + rng.uniform(0.002, 0.008)), 2)
            low = round(min(o, c) * (1 - rng.uniform(0.002, 0.008)), 2)
            volume = rng.randint(800_000, 1_500_000)
            rows.append((d.isoformat(), o, high, low, c, volume))
            price = c
            produced += 1
        d += timedelta(days=1)
    return rows


def main() -> None:
    out_path = Path(__file__).resolve().parents[1] / "data" / "raw" / "sample_prices.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = generate(start=date(2026, 1, 2), trading_days=250)
    lines = ["date,open,high,low,close,volume"]
    lines += [f"{d},{o:.2f},{h:.2f},{l:.2f},{c:.2f},{v}" for d, o, h, l, c, v in rows]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已生成 {len(rows)} 个交易日 -> {out_path}")


if __name__ == "__main__":
    main()

