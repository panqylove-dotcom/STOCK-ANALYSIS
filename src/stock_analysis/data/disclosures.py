"""法定披露来源适配器（docs/roadmap.md 阶段 2：法定披露来源接入）。

来源（A 股）：
- cninfo：巨潮资讯网（证监会指定法定披露平台）公告检索；
- sse：上交所公告检索接口；
- szse：深交所公告检索接口。

设计约束（与 fetchers.py 一致）：
- 零新增依赖：默认 HTTP 用标准库 urllib 实现；
- 所有网络调用通过注入的 http 可调用对象完成（单元测试注入 mock，不依赖在线服务）；
- 检索结果为 DisclosureRecord 列表，逐条登记访问时间与来源；
- register_local_disclosure：登记手动下载的公告文件（SHA-256 + JSONL 索引）。

接口为 best-effort 适配：官方页面/接口可能变更，解析失败应报错而不是猜测。
公告元数据不能替代原文人工核验（docs/risk-and-disclaimer.md）。
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

#: 北京时间：接口返回的时间戳统一按 +08:00 换算为披露日期。
CN_TZ = timezone(timedelta(hours=8))

CNINFO_TOPSEARCH_URL = "http://www.cninfo.com.cn/new/information/topSearch/query"
CNINFO_HIS_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_BASE = "http://static.cninfo.com.cn/"
SSE_URL = "http://query.sse.com.cn/security/stock/queryCompanyBulletinNew.do"
SSE_REFERER = "http://www.sse.com.cn/"
SZSE_URL = "http://www.szse.cn/api/disc/announcement/annList"
SZSE_REFERER = "http://www.szse.cn/disclosure/listed/notice/index.html"
#: PDF 直链防盗链（403），记录统一指向官方公告详情页。
SZSE_DETAIL_BASE = "https://www.szse.cn/disclosure/listed/bulletinDetail/index.html?"

#: 巨潮接口对 XHR 风格请求头返回 JSON（否则可能被反爬拦截返回 HTML）。
CNINFO_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "http://www.cninfo.com.cn/new/index",
}

#: http(url, *, method, params, form, json_body, headers) -> 已解析的 JSON（dict 或 list）。
HttpJson = Callable[..., Any]


@dataclass(frozen=True)
class DisclosureRecord:
    """一条公告披露记录（检索结果或本地登记均可表示）。"""

    ticker: str
    source: str  # cninfo / sse / szse / local
    title: str
    disclosed_on: date
    accessed_at: str  # ISO 秒级，检索/登记时刻
    url: str | None = None
    file_path: str | None = None
    sha256: str | None = None
    note: str = ""


def record_to_dict(r: DisclosureRecord) -> dict:
    d = asdict(r)
    d["disclosed_on"] = r.disclosed_on.isoformat()
    return d


def record_from_dict(d: dict) -> DisclosureRecord:
    return DisclosureRecord(
        ticker=d["ticker"],
        source=d["source"],
        title=d["title"],
        disclosed_on=date.fromisoformat(d["disclosed_on"]),
        accessed_at=d["accessed_at"],
        url=d.get("url"),
        file_path=d.get("file_path"),
        sha256=d.get("sha256"),
        note=d.get("note", ""),
    )


# ---------------------------------------------------------------------------
# 默认 HTTP（标准库实现；单元测试不经过这里）
# ---------------------------------------------------------------------------

def _strip_jsonp(text: str) -> str:
    """剥离 JSONP 包装，如 cb({"a":1}) -> {"a":1}。"""
    t = text.strip()
    if "(" in t and t.endswith(")"):
        return t[t.index("(") + 1 : -1]
    return t


def _default_http(
    url: str,
    *,
    method: str = "GET",
    params: dict | None = None,
    form: dict | None = None,
    json_body: dict | None = None,
    headers: dict | None = None,
    timeout: float = 15.0,
) -> Any:
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    if params:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{urlencode(params)}"
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    if headers:
        hdrs.update(headers)
    data: bytes | None = None
    if form is not None:
        data = urlencode(form).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif json_body is not None:
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = Request(url, data=data, headers=hdrs, method=method)
    with urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    payload = json.loads(_strip_jsonp(text))
    if not isinstance(payload, (dict, list)):
        raise ValueError(f"接口返回不是 JSON: {url}")
    return payload


def _call_http(
    http: HttpJson,
    retries: int,
    backoff_seconds: float,
    sleep: Callable[[float], None],
    *args,
    **kwargs,
) -> Any:
    """带指数退避的重试包装（与 fetchers.py 行为一致）。"""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return http(*args, **kwargs)
        except Exception as exc:  # 网络/接口瞬时错误重试
            last_exc = exc
            if attempt < retries:
                sleep(backoff_seconds * (2 ** (attempt - 1)))
    raise ValueError(f"披露接口调用失败（重试 {retries} 次）: {last_exc}") from last_exc


# ---------------------------------------------------------------------------
# 解析器（纯函数，输入为已解析 JSON payload）
# ---------------------------------------------------------------------------

def _cn_date(value, tz: timezone = CN_TZ) -> date:
    """兼容 epoch 毫秒 / YYYY-MM-DD / YYYYMMDD 三种时间格式。"""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=tz).date()
    s = str(value).strip()
    if "-" in s:
        return date.fromisoformat(s[:10])
    return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))


def _first(d: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return str(v)
    raise ValueError(f"公告记录缺少字段（尝试过 {keys}）: {d}")


def _clean_title(title: str) -> str:
    for tag in ("<em>", "</em>", "<Em>", "</Em>"):
        title = title.replace(tag, "")
    return title.strip()


def parse_cninfo(payload: dict, ticker: str, accessed_at: str) -> list[DisclosureRecord]:
    out: list[DisclosureRecord] = []
    for a in payload.get("announcements") or []:
        title = _clean_title(_first(a, ("announcementTitle",)))
        disclosed = _cn_date(a.get("announcementTime"))
        adj = a.get("adjunctUrl") or ""
        url = CNINFO_STATIC_BASE + adj.lstrip("/") if adj else None
        out.append(
            DisclosureRecord(
                ticker=ticker,
                source="cninfo",
                title=title,
                disclosed_on=disclosed,
                accessed_at=accessed_at,
                url=url,
                note="巨潮公告检索结果；原文需人工核验",
            )
        )
    return out


def _flatten_rows(rows) -> list[dict]:
    """兼容接口返回的嵌套数组形态（[[{...}]] -> [{...}]）。"""
    out: list[dict] = []
    for item in rows or []:
        if isinstance(item, list):
            out.extend(x for x in item if isinstance(x, dict))
        elif isinstance(item, dict):
            out.append(item)
    return out


def parse_sse(payload: dict, ticker: str, accessed_at: str) -> list[DisclosureRecord]:
    rows = payload.get("result")
    if rows is None:
        # 真实接口形态：result / pageHelp.data 均可能是嵌套数组
        rows = (payload.get("pageHelp") or {}).get("data")
    out: list[DisclosureRecord] = []
    for a in _flatten_rows(rows):
        title = _clean_title(_first(a, ("TITLE", "title", "BULLETIN_NAME")))
        disclosed = _cn_date(_first(a, ("SSEDATE", "NOTICE_DATE", "noticeDate")))
        raw_url = str(a.get("URL") or a.get("url") or "")
        url = (
            raw_url
            if raw_url.startswith("http")
            else (f"http://www.sse.com.cn/{raw_url.lstrip('/')}" if raw_url else None)
        )
        out.append(
            DisclosureRecord(
                ticker=ticker,
                source="sse",
                title=title,
                disclosed_on=disclosed,
                accessed_at=accessed_at,
                url=url,
                note="上交所公告检索结果；原文需人工核验",
            )
        )
    return out


def parse_szse(payload: dict, ticker: str, accessed_at: str) -> list[DisclosureRecord]:
    out: list[DisclosureRecord] = []
    for a in payload.get("data") or []:
        title = _clean_title(_first(a, ("announcementTitle", "title")))
        disclosed = _cn_date(_first(a, ("announcementTime", "publishTime")))
        ident = a.get("id") or a.get("annId")
        attach = str(a.get("announcementPdfUrl") or a.get("attachPath") or "")
        if ident not in (None, ""):
            url = f"{SZSE_DETAIL_BASE}{ident}"
        elif attach:
            url = f"https://www.szse.cn{attach}" if attach.startswith("/") else attach
        else:
            url = None
        out.append(
            DisclosureRecord(
                ticker=ticker,
                source="szse",
                title=title,
                disclosed_on=disclosed,
                accessed_at=accessed_at,
                url=url,
                note="深交所公告检索结果；原文需人工核验",
            )
        )
    return out


# ---------------------------------------------------------------------------
# 检索
# ---------------------------------------------------------------------------

def cninfo_market_column(ticker: str) -> str:
    """6/9 开头走上交所列，其余（0/3 等）走深交所列。"""
    return "sse" if ticker.startswith(("6", "9")) else "szse"


def _fetch_cninfo(
    ticker: str,
    *,
    start: date,
    end: date,
    http: HttpJson,
    retries: int,
    backoff_seconds: float,
    sleep: Callable[[float], None],
    page_size: int,
    max_pages: int,
    accessed_at: str,
) -> list[DisclosureRecord]:
    # 第一步：topSearch 换取 orgId（巨潮 stock 参数要求 代码,orgId）
    search = _call_http(
        http,
        retries,
        backoff_seconds,
        sleep,
        CNINFO_TOPSEARCH_URL,
        method="POST",
        form={"keyWord": ticker, "maxNum": "10"},
        headers=CNINFO_HEADERS,
    )
    # 实际接口返回顶层 JSON 数组；兼容包装为 dict 的形态
    items = (
        search
        if isinstance(search, list)
        else (search.get("searchs") or search.get("result") or search.get("data") or [])
    )
    org_id = None
    for item in items:
        if str(item.get("code", "")).strip() == ticker:
            org_id = item.get("orgId")
            break
    if org_id in (None, ""):
        raise ValueError(f"巨潮未找到证券代码 {ticker} 的 orgId")

    records: list[DisclosureRecord] = []
    for page in range(1, max_pages + 1):
        payload = _call_http(
            http,
            retries,
            backoff_seconds,
            sleep,
            CNINFO_HIS_URL,
            method="POST",
            headers=CNINFO_HEADERS,
            form={
                "pageNum": str(page),
                "pageSize": str(page_size),
                "column": cninfo_market_column(ticker),
                "tabName": "fulltext",
                "stock": f"{ticker},{org_id}",
                "seDate": f"{start.isoformat()}~{end.isoformat()}",
                "category": "",
                "plate": "",
            },
        )
        page_records = parse_cninfo(payload, ticker, accessed_at)
        records.extend(page_records)
        total = int(payload.get("totalAnnouncements") or 0)
        if not page_records or len(records) >= total or page * page_size >= total:
            break
    return records


def _fetch_sse(
    ticker: str,
    *,
    start: date,
    end: date,
    http: HttpJson,
    retries: int,
    backoff_seconds: float,
    sleep: Callable[[float], None],
    page_size: int,
    max_pages: int,
    accessed_at: str,
) -> list[DisclosureRecord]:
    records: list[DisclosureRecord] = []
    for page in range(1, max_pages + 1):
        payload = _call_http(
            http,
            retries,
            backoff_seconds,
            sleep,
            SSE_URL,
            params={
                "jsonCallBack": "jsonpCallback",
                "isPagination": "true",
                "pageHelp.cacheSize": "1",
                "pageHelp.beginPage": str(page),
                "pageHelp.pageSize": str(page_size),
                "SECURITY_CODE": ticker,
                "beginDate": start.strftime("%Y%m%d"),
                "endDate": end.strftime("%Y%m%d"),
                "CATALOGID": "listedCo_notice",
                "title": "",
            },
            headers={"Referer": SSE_REFERER},
        )
        page_records = parse_sse(payload, ticker, accessed_at)
        records.extend(page_records)
        total = int((payload.get("pageHelp") or {}).get("totalCount") or 0)
        if len(page_records) < page_size or (total and len(records) >= total):
            break
    return records


def _fetch_szse(
    ticker: str,
    *,
    start: date,
    end: date,
    http: HttpJson,
    retries: int,
    backoff_seconds: float,
    sleep: Callable[[float], None],
    page_size: int,
    max_pages: int,
    accessed_at: str,
) -> list[DisclosureRecord]:
    records: list[DisclosureRecord] = []
    for page in range(1, max_pages + 1):
        payload = _call_http(
            http,
            retries,
            backoff_seconds,
            sleep,
            SZSE_URL,
            method="POST",
            json_body={
                "stock": [ticker],
                "isSearch": True,
                "pageNum": page,
                "pageSize": page_size,
                "seDate": [start.isoformat(), end.isoformat()],
                "channelCode": ["listedNotice_disc"],
            },
            headers={"Referer": SZSE_REFERER},
        )
        page_records = parse_szse(payload, ticker, accessed_at)
        records.extend(page_records)
        total = int(payload.get("totalSize") or 0)
        if not page_records or len(records) >= total:
            break
    return records


_FETCHERS = {"cninfo": _fetch_cninfo, "sse": _fetch_sse, "szse": _fetch_szse}


def fetch_announcements(
    source: str,
    ticker: str,
    *,
    start: date,
    end: date,
    http: HttpJson | None = None,
    retries: int = 3,
    backoff_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    page_size: int = 30,
    max_pages: int = 10,
) -> list[DisclosureRecord]:
    """按来源检索区间内公告元数据（离线测试注入 http；线上默认 urllib）。

    返回结果按披露日期升序；空区间返回空列表。
    """
    if source not in _FETCHERS:
        raise ValueError(f"未知披露来源: {source}（可选 {sorted(_FETCHERS)}）")
    if start > end:
        raise ValueError(f"开始日期晚于结束日期: {start} > {end}")
    http = http or _default_http
    accessed_at = datetime.now(tz=CN_TZ).isoformat(timespec="seconds")
    records = _FETCHERS[source](
        ticker,
        start=start,
        end=end,
        http=http,
        retries=retries,
        backoff_seconds=backoff_seconds,
        sleep=sleep,
        page_size=page_size,
        max_pages=max_pages,
        accessed_at=accessed_at,
    )
    in_range = [r for r in records if start <= r.disclosed_on <= end]
    return sorted(in_range, key=lambda r: (r.disclosed_on, r.title))


# ---------------------------------------------------------------------------
# 本地核验登记（手动下载的公告文件 -> SHA-256 + JSONL 索引）
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def register_local_disclosure(
    file_path: Path,
    *,
    ticker: str,
    title: str,
    disclosed_on: date,
    url: str | None = None,
    source: str = "local",
    note: str = "手动下载登记；哈希用于完整性核验",
) -> DisclosureRecord:
    p = Path(file_path)
    if not p.is_file():
        raise ValueError(f"公告文件不存在: {p}")
    return DisclosureRecord(
        ticker=ticker,
        source=source,
        title=title,
        disclosed_on=disclosed_on,
        accessed_at=datetime.now(tz=CN_TZ).isoformat(timespec="seconds"),
        url=url,
        file_path=str(p),
        sha256=sha256_file(p),
        note=note,
    )


def append_index(record: DisclosureRecord, index_path: Path) -> None:
    """把记录追加到 JSONL 索引（自动创建父目录）。"""
    p = Path(index_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record_to_dict(record), ensure_ascii=False) + "\n")


def load_index(index_path: Path) -> list[DisclosureRecord]:
    p = Path(index_path)
    if not p.exists():
        return []
    records = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(record_from_dict(json.loads(line)))
    return records
