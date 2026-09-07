"""审计日志与数据许可控制（docs/roadmap.md 阶段 5）。

- audit(action, detail)：记录本地操作，输出 JSONL，便于事后复核；
- 数据许可：来源登记时声明 license，reissue/bulk_export 等敏感动作
  必须先检查许可是否允许，不允许则拒绝并记录审计。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class AuditRecord:
    """单条审计记录。"""

    timestamp: str
    action: str
    detail: str = ""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_audit(path: str | Path, action: str, detail: str = "", *, now: str | None = None) -> AuditRecord:
    """追加一条审计记录到 JSONL 文件。"""
    record = AuditRecord(timestamp=now or utc_now_iso(), action=action, detail=detail)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record.__dict__, ensure_ascii=False) + "\n")
    return record


def read_audit(path: str | Path) -> list[AuditRecord]:
    """读取审计日志（按写入顺序）。"""
    p = Path(path)
    records: list[AuditRecord] = []
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                d = json.loads(line)
                records.append(AuditRecord(**d))
    return records


# ---------------------------------------------------------------- 数据许可


class LicenseViolation(Exception):
    """数据许可不允许所请求的动作。"""


@dataclass(frozen=True)
class DataLicense:
    """数据许可声明。

    - personal_use：允许个人研究使用；
    - redistribution：允许把原始数据再分发/提交入库。
    """

    source: str
    personal_use: bool = True
    redistribution: bool = False


def check_action(license: DataLicense, action: str) -> None:
    """检查动作是否被许可允许；不允许抛 LicenseViolation。"""
    if action in ("reissue", "bulk_export", "redistribute"):
        if not license.redistribution:
            raise LicenseViolation(
                f"来源 '{license.source}' 不允许 {action}（未获再分发许可）"
            )
    elif action == "analyze":
        if not license.personal_use:
            raise LicenseViolation(
                f"来源 '{license.source}' 不允许 analyze（未获使用许可）"
            )
    # 未知动作默认拒绝
    else:
        raise LicenseViolation(f"未知动作: {action}")


def perform_action(
    license: DataLicense,
    action: str,
    audit_path: str | Path | None,
    detail: str = "",
    *,
    now: str | None = None,
) -> bool:
    """执行受许可控制的审计动作：允许则记录成功，拒绝则记录违规并重抛。"""
    try:
        check_action(license, action)
    except LicenseViolation as exc:
        if audit_path is not None:
            append_audit(audit_path, f"DENIED:{action}", str(exc), now=now)
        raise
    if audit_path is not None:
        append_audit(audit_path, action, detail, now=now)
    return True

