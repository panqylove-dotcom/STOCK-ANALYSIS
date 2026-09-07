"""stock-analysis: a reproducible, documentation-first equity research framework.

本项目仅用于教育、研究和信息整理，不构成投资建议。
"""

__version__ = "0.1.0"

from .analysis import AnalysisReport, Catalyst, Evidence, Risk
from .review import ReviewEntry

__all__ = [
    "AnalysisReport",
    "Catalyst",
    "Evidence",
    "ReviewEntry",
    "Risk",
    "__version__",
]

