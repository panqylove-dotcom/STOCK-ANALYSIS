"""统一配置格式与项目版本策略。

设计目标（见 docs/roadmap.md 阶段 1）：
- 所有可调参数集中在此，供分析、测试与报告复用；
- 默认配置不与任何在线服务绑定，保证离线可测试；
- 派生计算记录计算版本，保证可追溯。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Any


#: 项目当前计算/规范版本。任何改变派生指标口径的变更都应递增此版本。
CALCULATION_VERSION = "0.1.0"


@dataclass(frozen=True)
class Config:
    """项目默认配置。字段新增/改名属于口径变更，应同步递增计算版本。"""

    #: 年交易日数：应按市场设置，不能盲目固定为 252（见 docs/data-and-metrics.md）。
    trading_days_per_year: int = 252
    #: 无风险利率（年化，小数）。用于 Sharpe 等指标时必须以同一口径披露。
    risk_free_rate: float = 0.02
    #: 允许的空值表示，避免把缺失误填为零。
    missing_value: str = "N/A"
    #: 计算版本，写入派生结果便于追溯。
    calculation_version: str = CALCULATION_VERSION

    @classmethod
    def from_file(cls, path: str | Path) -> "Config":
        """从 JSON 文件加载配置，未知字段会被拒绝以避免拼写错误。

        配置文件中允许省略字段，省略项使用默认值。
        """
        p = Path(path)
        raw: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
        known = {f.name for f in fields(cls)}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"未知配置字段: {sorted(unknown)}")
        return cls(**raw)

    def to_file(self, path: str | Path) -> None:
        """把当前配置写为 JSON，便于保存分析快照。"""
        Path(path).write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

