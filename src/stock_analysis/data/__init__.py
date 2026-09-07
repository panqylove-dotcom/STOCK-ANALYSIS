"""数据层：统一字段模型、来源记录、缓存与质量检查。

设计原则（见 docs/data-and-metrics.md）：
- Raw 数据原样保存，不覆盖；
- Normalized 统一日期、币种、单位、复权与字段名称；
- Derived 由明确公式计算；
- 每次派生计算记录输入版本、计算时间与异常处理。
"""

from .cleaning import (
    dedupe_bars,
    fill_missing_with_previous_close,
    resample_daily,
    validate_bars,
)
from .loader import CsvPriceLoader
from .quality import DataQualityReport, check_quality, run_quality_checks

__all__ = [
    "CsvPriceLoader",
    "DataQualityReport",
    "check_quality",
    "dedupe_bars",
    "fill_missing_with_previous_close",
    "resample_daily",
    "run_quality_checks",
    "validate_bars",
]

