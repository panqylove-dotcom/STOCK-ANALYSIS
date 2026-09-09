"""法定披露适配器离线测试：全部注入 mock http，不联网。"""

import hashlib
import json
from datetime import date, datetime

import pytest

from stock_analysis.cli import main as cli_main
from stock_analysis.data import disclosures as ds


def cn_ms(y, m, d, hh=18):
    return int(datetime(y, m, d, hh, tzinfo=ds.CN_TZ).timestamp() * 1000)


# --- 解析器 ---------------------------------------------------------------

def test_parse_cninfo_payload():
    payload = {
        "totalAnnouncements": 1,
        "announcements": [
            {
                "announcementTitle": "<em>600000</em>：2025年年度报告",
                "announcementTime": cn_ms(2026, 1, 5),
                "adjunctUrl": "finalpage/2026-01-05/123.PDF",
            }
        ],
    }
    recs = ds.parse_cninfo(payload, "600000", "2026-01-06T00:00:00+08:00")
    assert len(recs) == 1
    r = recs[0]
    assert r.title == "600000：2025年年度报告"
    assert r.disclosed_on == date(2026, 1, 5)
    assert r.url == "http://static.cninfo.com.cn/finalpage/2026-01-05/123.PDF"
    assert r.source == "cninfo"


def test_parse_sse_payload():
    payload = {
        "result": [
            {
                "TITLE": "浦发银行年度报告",
                "NOTICE_DATE": "20260105",
                "URL": "/disclosure/announcement/x.pdf",
            }
        ]
    }
    recs = ds.parse_sse(payload, "600000", "2026-01-06T00:00:00+08:00")
    assert recs[0].disclosed_on == date(2026, 1, 5)
    assert recs[0].url == "http://www.sse.com.cn/disclosure/announcement/x.pdf"


def test_parse_szse_payload():
    payload = {
        "totalSize": 1,
        "data": [
            {
                "id": "0a619fb3-bad9-49f6-b1fe-74761ac84def",
                "title": "平安银行：关于职工董事任职资格核准的公告",
                "publishTime": "2026-08-22 00:00:00",
                "attachPath": "/disc/disk03/finalpage/2026-08-22/x.PDF",
            }
        ],
    }
    recs = ds.parse_szse(payload, "000001", "2026-01-06T00:00:00+08:00")
    assert recs[0].disclosed_on == date(2026, 8, 22)
    # PDF 直链防盗链，记录应指向官方详情页
    assert recs[0].url == ds.SZSE_DETAIL_BASE + "0a619fb3-bad9-49f6-b1fe-74761ac84def"


def test_parse_sse_pagehelp_shape():
    """真实上交所接口形态：JSONP 解包后 pageHelp.data 嵌套数组 + SSEDATE/URL。"""
    payload = {
        "pageHelp": {
            "totalCount": 1,
            "data": [
                [
                    {
                        "TITLE": "浦发银行关于独立董事任职资格获核准的公告",
                        "SSEDATE": "2026-09-02",
                        "SECURITY_CODE": "600000",
                        "URL": "/disclosure/listedinfo/announcement/c/new/2026-09-02/600000_20260902_H2KO.pdf",
                    }
                ]
            ],
        }
    }
    recs = ds.parse_sse(payload, "600000", "2026-09-03T00:00:00+08:00")
    assert len(recs) == 1
    assert recs[0].disclosed_on == date(2026, 9, 2)
    assert recs[0].url == (
        "http://www.sse.com.cn/disclosure/listedinfo/announcement/c/new/"
        "2026-09-02/600000_20260902_H2KO.pdf"
    )


def test_parse_sse_nested_result():
    """result 键同样可能是嵌套数组（线上实测形态）。"""
    payload = {"result": [[{"TITLE": "某公告", "SSEDATE": "2026-09-02", "URL": ""}]]}
    recs = ds.parse_sse(payload, "600000", "x")
    assert len(recs) == 1
    assert recs[0].url is None


def test_parse_missing_field_raises():
    with pytest.raises(ValueError):
        ds.parse_szse({"data": [{"announcementTime": "2026-01-05"}]}, "000001", "x")


def test_strip_jsonp():
    assert ds._strip_jsonp("cb({\"a\":1})") == '{"a":1}'
    assert ds._strip_jsonp('{"a":1}') == '{"a":1}'


# --- 检索 -----------------------------------------------------------------

def make_cninfo_http(calls):
    def http(url, **kwargs):
        calls.append((url, kwargs))
        if url == ds.CNINFO_TOPSEARCH_URL:
            return [{"code": "600000", "orgId": "gssh0600000"}]  # 真实接口为顶层数组
        return {
            "totalAnnouncements": 2,
            "announcements": [
                {
                    "announcementTitle": "B 公告",
                    "announcementTime": cn_ms(2026, 2, 1),
                    "adjunctUrl": "finalpage/b.PDF",
                },
                {
                    "announcementTitle": "A 公告",
                    "announcementTime": cn_ms(2026, 1, 5),
                    "adjunctUrl": "finalpage/a.PDF",
                },
                {
                    "announcementTitle": "区间外公告",
                    "announcementTime": cn_ms(2025, 12, 1),
                    "adjunctUrl": "finalpage/old.PDF",
                },
            ],
        }

    return http


def test_fetch_cninfo_filters_and_sorts():
    calls = []
    recs = ds.fetch_announcements(
        "cninfo",
        "600000",
        start=date(2026, 1, 1),
        end=date(2026, 2, 28),
        http=make_cninfo_http(calls),
    )
    assert [r.title for r in recs] == ["A 公告", "B 公告"]  # 区间过滤 + 日期升序
    # 第一跳 topSearch 携带代码，第二跳 hisAnnouncement 携带 代码,orgId 与 seDate
    assert calls[0][1]["form"]["keyWord"] == "600000"
    stock = calls[1][1]["form"]["stock"]
    assert stock == "600000,gssh0600000"
    assert calls[1][1]["form"]["seDate"] == "2026-01-01~2026-02-28"


def test_fetch_retry_with_backoff():
    state = {"n": 0}
    sleeps = []

    def flaky_http(url, **kwargs):
        if url == ds.CNINFO_TOPSEARCH_URL:
            state["n"] += 1
            if state["n"] == 1:
                raise OSError("瞬时网络错误")
            return {"searchs": [{"code": "600000", "orgId": "x"}]}  # 兼容 dict 形态
        return {"totalAnnouncements": 0, "announcements": []}

    recs = ds.fetch_announcements(
        "cninfo",
        "600000",
        start=date(2026, 1, 1),
        end=date(2026, 1, 31),
        http=flaky_http,
        sleep=sleeps.append,
    )
    assert recs == []
    assert sleeps == [1.0]  # 一次退避


def test_fetch_sse_szse_params():
    calls = []

    def http(url, **kwargs):
        calls.append((url, kwargs))
        return {"result": []} if "sse" in url else {"data": [], "totalSize": 0}

    ds.fetch_announcements("sse", "600000", start=date(2026, 1, 1), end=date(2026, 1, 2), http=http)
    ds.fetch_announcements("szse", "000001", start=date(2026, 1, 1), end=date(2026, 1, 2), http=http)
    assert calls[0][1]["headers"]["Referer"] == ds.SSE_REFERER
    assert calls[1][1]["json_body"]["stock"] == ["000001"]
    assert calls[1][1]["json_body"]["seDate"] == ["2026-01-01", "2026-01-02"]


def test_fetch_bad_args_raise():
    with pytest.raises(ValueError):
        ds.fetch_announcements("unknown", "600000", start=date(2026, 1, 1), end=date(2026, 1, 2))
    with pytest.raises(ValueError):
        ds.fetch_announcements("cninfo", "600000", start=date(2026, 2, 1), end=date(2026, 1, 1))


def test_cninfo_market_column():
    assert ds.cninfo_market_column("600000") == "sse"
    assert ds.cninfo_market_column("900901") == "sse"
    assert ds.cninfo_market_column("000001") == "szse"
    assert ds.cninfo_market_column("300750") == "szse"


# --- 本地登记 -------------------------------------------------------------

def test_register_and_index(tmp_path):
    f = tmp_path / "annual.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    rec = ds.register_local_disclosure(
        f, ticker="600000", title="2025年年度报告", disclosed_on=date(2026, 1, 5),
        url="http://static.cninfo.com.cn/finalpage/a.PDF",
    )
    assert rec.sha256 == hashlib.sha256(b"%PDF-1.4 fake").hexdigest()
    idx = tmp_path / "data" / "disclosures" / "index.jsonl"
    ds.append_index(rec, idx)
    ds.append_index(rec, idx)
    loaded = ds.load_index(idx)
    assert len(loaded) == 2
    assert loaded[0] == rec


def test_register_missing_file_raises(tmp_path):
    with pytest.raises(ValueError):
        ds.register_local_disclosure(
            tmp_path / "nope.pdf", ticker="600000", title="x", disclosed_on=date(2026, 1, 5)
        )


def test_index_roundtrip_dict(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"x")
    rec = ds.register_local_disclosure(f, ticker="600000", title="t", disclosed_on=date(2026, 1, 5))
    d = ds.record_to_dict(rec)
    assert d["disclosed_on"] == "2026-01-05"
    assert ds.record_from_dict(d) == rec


# --- CLI ------------------------------------------------------------------

def test_cli_disclose_register(tmp_path, capsys):
    f = tmp_path / "q.pdf"
    f.write_bytes(b"abc")
    idx = tmp_path / "idx.jsonl"
    code = cli_main([
        "disclose", "register", str(f),
        "--ticker", "600000", "--title", "三季报",
        "--disclosed-on", "2026-10-30", "--index", str(idx),
    ])
    assert code == 0
    assert "已登记" in capsys.readouterr().out
    lines = idx.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["title"] == "三季报"


def test_cli_disclose_register_missing_file(tmp_path, capsys):
    code = cli_main([
        "disclose", "register", str(tmp_path / "nope.pdf"),
        "--ticker", "600000", "--title", "x",
        "--disclosed-on", "2026-10-30", "--index", str(tmp_path / "i.jsonl"),
    ])
    assert code == 1
    assert "登记失败" in capsys.readouterr().err


def test_cli_disclose_list_with_mock_http(monkeypatch, capsys):
    def fake_http(url, **kwargs):
        if url == ds.CNINFO_TOPSEARCH_URL:
            return [{"code": "600000", "orgId": "gssh0600000"}]
        return {
            "totalAnnouncements": 1,
            "announcements": [
                {
                    "announcementTitle": "A 公告",
                    "announcementTime": cn_ms(2026, 1, 5),
                    "adjunctUrl": "finalpage/a.PDF",
                }
            ],
        }

    monkeypatch.setattr(ds, "_default_http", fake_http)
    code = cli_main([
        "disclose", "list", "600000", "--source", "cninfo",
        "--start", "2026-01-01", "--end", "2026-01-31",
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "披露日期" in out and "A 公告" in out


def test_cli_disclose_list_network_error_returns_1(monkeypatch, capsys):
    def dead_http(url, **kwargs):
        raise OSError("网络不可达")

    monkeypatch.setattr(ds, "_default_http", dead_http)
    code = cli_main([
        "disclose", "list", "600000", "--source", "cninfo",
        "--start", "2026-01-01", "--end", "2026-01-31",
    ])
    assert code == 1
    assert "披露检索失败" in capsys.readouterr().err


# --- CLI：disclose check（增量检查） ---------------------------------------

def _write_index(tmp_path, lines):
    idx = tmp_path / "idx.jsonl"
    idx.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return idx


def _check_http(calls, announcements):
    def http(url, **kwargs):
        calls.append((url, kwargs))
        if url == ds.CNINFO_TOPSEARCH_URL:
            return [{"code": "600000", "orgId": "gssh0600000"}]
        return {
            "totalAnnouncements": len(announcements),
            "announcements": announcements,
        }

    return http


def _ann(title, y, m, d):
    return {
        "announcementTitle": title,
        "announcementTime": cn_ms(y, m, d),
        "adjunctUrl": f"finalpage/{title}.PDF",
    }


def test_cli_disclose_check_lists_new_only(monkeypatch, tmp_path, capsys):
    idx = _write_index(tmp_path, [
        json.dumps({
            "ticker": "600000", "source": "local", "title": "已登记公告",
            "disclosed_on": "2026-08-01", "accessed_at": "2026-08-01T00:00:00+08:00",
        }, ensure_ascii=False),
    ])
    calls = []
    monkeypatch.setattr(ds, "_default_http", _check_http(calls, [
        _ann("已登记公告", 2026, 8, 1),
        _ann("新公告甲", 2026, 9, 1),
    ]))
    code = cli_main([
        "disclose", "check", "600000", "--source", "cninfo",
        "--index", str(idx), "--today", "2026-09-08",
    ])
    assert code == 0
    captured = capsys.readouterr()
    assert "新公告甲" in captured.out
    assert "已登记公告" not in captured.out
    assert "基线" in captured.err and "2026-08-01" in captured.err
    # 检索起点应为索引基线日期
    assert calls[1][1]["form"]["seDate"].startswith("2026-08-01~")


def test_cli_disclose_check_lookback_without_records(monkeypatch, tmp_path, capsys):
    idx = _write_index(tmp_path, [
        json.dumps({
            "ticker": "000001", "source": "local", "title": "他司公告",
            "disclosed_on": "2020-01-01", "accessed_at": "2020-01-01T00:00:00+08:00",
        }, ensure_ascii=False),
    ])
    calls = []
    monkeypatch.setattr(ds, "_default_http", _check_http(calls, []))
    code = cli_main([
        "disclose", "check", "600000", "--source", "cninfo",
        "--index", str(idx), "--today", "2026-09-08",
    ])
    assert code == 0
    captured = capsys.readouterr()
    assert "未发现新公告" in captured.out
    assert "回看最近 30 天" in captured.err
    assert calls[1][1]["form"]["seDate"] == "2026-08-09~2026-09-08"


def test_cli_disclose_check_corrupt_index_returns_1(tmp_path, capsys):
    idx = tmp_path / "idx.jsonl"
    idx.write_text("{broken\n", encoding="utf-8")
    code = cli_main([
        "disclose", "check", "600000", "--source", "cninfo",
        "--index", str(idx), "--today", "2026-09-08",
    ])
    assert code == 1
    assert "读取披露索引失败" in capsys.readouterr().err


def test_cli_disclose_check_bad_today_returns_1(tmp_path, capsys):
    idx = tmp_path / "idx.jsonl"
    code = cli_main([
        "disclose", "check", "600000", "--source", "cninfo",
        "--index", str(idx), "--today", "not-a-date",
    ])
    assert code == 1
    assert "日期格式错误" in capsys.readouterr().err


def test_cli_disclose_check_fetch_error_returns_1(monkeypatch, tmp_path, capsys):
    def dead_http(url, **kwargs):
        raise OSError("网络不可达")

    monkeypatch.setattr(ds, "_default_http", dead_http)
    code = cli_main([
        "disclose", "check", "600000", "--source", "cninfo",
        "--index", str(tmp_path / "absent.jsonl"), "--today", "2026-09-08",
    ])
    assert code == 1
    assert "披露增量检查失败" in capsys.readouterr().err


def test_cli_disclose_check_save_pending_list(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(ds, "_default_http", _check_http(calls, [
        _ann("新公告甲", 2026, 9, 1),
        _ann("新公告乙", 2026, 9, 5),
    ]))
    out = tmp_path / "pending.jsonl"
    code = cli_main([
        "disclose", "check", "600000", "--source", "cninfo",
        "--index", str(tmp_path / "absent.jsonl"), "--today", "2026-09-08",
        "--save", str(out),
    ])
    assert code == 0
    assert "待核验清单已保存" in capsys.readouterr().out
    saved = ds.load_index(out)
    assert [r.title for r in saved] == ["新公告甲", "新公告乙"]
    assert all(r.ticker == "600000" for r in saved)


def test_cli_disclose_check_save_empty_file(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(ds, "_default_http", _check_http(calls, []))
    existing = tmp_path / "pending.jsonl"
    existing.write_text("stale\n", encoding="utf-8")
    code = cli_main([
        "disclose", "check", "600000", "--source", "cninfo",
        "--index", str(tmp_path / "absent.jsonl"), "--today", "2026-09-08",
        "--save", str(existing),
    ])
    assert code == 0
    assert existing.read_text(encoding="utf-8") == "\n"
    assert "未发现新公告" in capsys.readouterr().out


def test_cli_disclose_check_save_error_returns_1(monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(ds, "_default_http", _check_http(calls, [
        _ann("新公告甲", 2026, 9, 1),
    ]))
    code = cli_main([
        "disclose", "check", "600000", "--source", "cninfo",
        "--index", str(tmp_path / "absent.jsonl"), "--today", "2026-09-08",
        "--save", str(tmp_path),
    ])
    assert code == 1
    assert "写入待核验清单失败" in capsys.readouterr().err


def test_cli_disclose_check_since_overrides_baseline(monkeypatch, tmp_path, capsys):
    idx = _write_index(tmp_path, [
        json.dumps({
            "ticker": "600000", "source": "local", "title": "已登记公告",
            "disclosed_on": "2026-08-01", "accessed_at": "2026-08-01T00:00:00+08:00",
        }, ensure_ascii=False),
    ])
    calls = []
    monkeypatch.setattr(ds, "_default_http", _check_http(calls, [
        _ann("已登记公告", 2026, 8, 1),   # 索引已有 -> 应被去重
        _ann("七月旧公告", 2026, 7, 15),  # --since 扩大窗口后应可见
    ]))
    code = cli_main([
        "disclose", "check", "600000", "--source", "cninfo",
        "--index", str(idx), "--today", "2026-09-08", "--since", "2026-07-01",
    ])
    assert code == 0
    captured = capsys.readouterr()
    assert "手动指定" in captured.err
    assert "七月旧公告" in captured.out
    assert "已登记公告" not in captured.out
    assert calls[1][1]["form"]["seDate"].startswith("2026-07-01~")


def test_cli_disclose_check_bad_since_returns_1(tmp_path, capsys):
    code = cli_main([
        "disclose", "check", "600000", "--source", "cninfo",
        "--index", str(tmp_path / "absent.jsonl"),
        "--today", "2026-09-08", "--since", "not-a-date",
    ])
    assert code == 1
    assert "--since 日期格式错误" in capsys.readouterr().err


def test_cli_disclose_check_since_after_today_returns_1(tmp_path, capsys):
    code = cli_main([
        "disclose", "check", "600000", "--source", "cninfo",
        "--index", str(tmp_path / "absent.jsonl"),
        "--today", "2026-09-08", "--since", "2026-10-01",
    ])
    assert code == 1
    assert "不能晚于基准日期" in capsys.readouterr().err
