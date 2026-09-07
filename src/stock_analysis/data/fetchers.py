"""在线行情源适配器（docs/roadmap.md 阶段 2：接入至少一个行情源）。

设计约束：
- akshare 为可选依赖（pip install "stock-analysis[akshare]"），未安装时
  抛出带安装提示的 ImportError，不影响离线功能；
- fetch 函数由参数注入（fetch_fn），单元测试用 mock，不依赖在线服务；
- 拉取结果登记来源记录（含访问时间与许可声明）。

注意：第三方行情数据不能替代法定披露核验（docs/risk-and-disclaimer.md）。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date, datetime

from ..models import PriceBar, Security
from .cleaning import validate_bars
from .loader import LoadResult, SourceRecord

#: 拉取函数签名：fetch_fn(symbol, start, end) -> 行字典列表，
#: 每行含 日期/开盘/收盘/最高/最低/成交量（akshare 中文列名）或
#: date/open/close/high/low/volume（英文列名）。
FetchFn = Callable[[str, date, date], list[dict]]


_COLUMN_ALIASES = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "收盘价格": "close",
    "股票代码": "ticker",
}


def _normalize_row(row: dict) -> dict:
    out: dict = {}
    for key, value in row.items():
        key2 = _COLUMN_ALIASES.get(str(key).strip(), str(key).strip().lower())
        out[key2] = value
    return out


def _to_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value).strip()[:10])


def akshare_daily_cn(
    symbol: str,
    *,
    start: date,
    end: date,
    adjust: str = "qfq",
    fetch_fn: FetchFn | None = None,
    retries: int = 3,
    backoff_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> LoadResult:
    """拉取 A 股日线（默认前复权）。

    fetch_fn: 注入的拉取函数（测试用 mock）；默认使用 akshare
    stock_zh_a_hist。akshare 未安装时抛 ImportError 并给出安装提示。
    retries/backoff_seconds: 网络失败时的重试次数与指数退避；
    sleep 可注入（测试用），不改变离线测试原则。
    """
    if fetch_fn is None:
        try:
            import akshare as ak  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "需要 akshare：pip install 'stock-analysis[akshare]'"
            ) from exc

        def fetch_fn(sym: str, s: date, e: date) -> list[dict]:
            df = ak.stock_zh_a_hist(
                symbol=sym,
                period="daily",
                start_date=s.strftime("%Y%m%d"),
                end_date=e.strftime("%Y%m%d"),
                adjust=adjust,
            )
            return df.to_dict("records")

    last_exc: Exception | None = None
    raw_rows: list[dict] = []
    for attempt in range(1, retries + 1):
        try:
            raw_rows = fetch_fn(symbol, start, end)
            break
        except Exception as exc:  # 网络/接口瞬时错误重试
            last_exc = exc
            if attempt < retries:
                sleep(backoff_seconds * (2 ** (attempt - 1)))
    else:
        raise ValueError(f"拉取失败（重试 {retries} 次）: {last_exc}") from last_exc
    if not raw_rows:
        raise ValueError(f"行情源未返回数据: {symbol} {start}~{end}")

    bars: list[PriceBar] = []
    for raw in raw_rows:
        row = _normalize_row(raw)
        try:
            bars.append(
                PriceBar(
                    date=_to_date(row["date"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                    adjusted=(adjust != ""),
                )
            )
        except KeyError as exc:
            raise ValueError(f"行情行缺少字段 {exc}: {row}") from exc

    validated = validate_bars(bars)
    market = "NASDAQ" if adjust == "" else "CN"
    security = Security(ticker=symbol, market="CN", currency="CNY")
    source = SourceRecord(
        name=f"akshare:stock_zh_a_hist({symbol}, adjust={adjust!r})",
        accessed_at=datetime.now().isoformat(timespec="seconds"),
        version=f"akshare-daily-{adjust or 'raw'}",
        license_name="third-party, personal-use only; 法定披露未核验",
        note="第三方行情，复权口径见 version；重要数字需回到交易所/披露核验",
    )
    _ = market  # 预留：多市场扩展
    return LoadResult(bars=validated, security=security, source=source)

