"""
Agent Tool function module
"""

from .weight_calculator import (
    DEFAULT_ANALYST_IDS,
    REGIMES,
    RegimeAdaptiveWeightCalculator,
    RegimeMultiplicativeWeightManager,
    aggregate_posteriors,
    calculate_report_weights,
    format_weighted_reports_prompt,
)

__all__ = [
    "DEFAULT_ANALYST_IDS",
    "REGIMES",
    "RegimeAdaptiveWeightCalculator",
    "RegimeMultiplicativeWeightManager",
    "aggregate_posteriors",
    "calculate_report_weights",
    "format_weighted_reports_prompt",
]


