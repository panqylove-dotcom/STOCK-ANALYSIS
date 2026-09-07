"""审计日志与数据许可控制测试。"""

import pytest

from stock_analysis.audit import (
    DataLicense,
    LicenseViolation,
    append_audit,
    check_action,
    perform_action,
    read_audit,
)


def test_append_and_read_audit(tmp_path):
    p = tmp_path / "audit.jsonl"
    append_audit(p, "analyze", "load sample", now="2026-09-07T10:00:00+00:00")
    append_audit(p, "DENIED:reissue", "no license", now="2026-09-07T10:01:00+00:00")
    records = read_audit(p)
    assert len(records) == 2
    assert records[0].action == "analyze"
    assert records[1].timestamp == "2026-09-07T10:01:00+00:00"


def test_check_action_redistribute_denied():
    lic = DataLicense(source="vendor-x", personal_use=True, redistribution=False)
    check_action(lic, "analyze")  # 不应抛错
    with pytest.raises(LicenseViolation, match="再分发"):
        check_action(lic, "reissue")


def test_check_action_redistribute_allowed():
    lic = DataLicense(source="vendor-x", personal_use=True, redistribution=True)
    check_action(lic, "bulk_export")  # 不应抛错


def test_check_action_analyze_denied():
    lic = DataLicense(source="vendor-x", personal_use=False)
    with pytest.raises(LicenseViolation, match="使用许可"):
        check_action(lic, "analyze")


def test_check_action_unknown_denied():
    lic = DataLicense(source="vendor-x")
    with pytest.raises(LicenseViolation, match="未知动作"):
        check_action(lic, "moonshot")


def test_perform_action_writes_success_audit(tmp_path):
    p = tmp_path / "audit.jsonl"
    lic = DataLicense(source="vendor-x")
    assert perform_action(lic, "analyze", p, "ok", now="2026-09-07T10:00:00+00:00")
    records = read_audit(p)
    assert len(records) == 1
    assert records[0].action == "analyze"


def test_perform_action_denied_records_and_raises(tmp_path):
    p = tmp_path / "audit.jsonl"
    lic = DataLicense(source="vendor-x", redistribution=False)
    with pytest.raises(LicenseViolation):
        perform_action(lic, "reissue", p, now="2026-09-07T10:00:00+00:00")
    records = read_audit(p)
    assert len(records) == 1
    assert records[0].action == "DENIED:reissue"

