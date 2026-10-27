"""
Policy DSL semantic verification (L2)
After the Schema verification passes, check whether the policy logic is reasonable
"""
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _get_entry_months(dsl: Dict[str, Any]) -> List[int]:
    """Extract calendar_month from entry_rules months"""
    for r in dsl.get("entry_rules", []):
        if r.get("type") == "calendar_month" and r.get("months"):
            return r["months"]
    return []


def _get_exit_months(dsl: Dict[str, Any]) -> List[int]:
    """Extract calendar_month from exit_rules months"""
    for r in dsl.get("exit_rules", []):
        if r.get("type") == "calendar_month" and r.get("months"):
            return r["months"]
    return []


def _get_holding_days(dsl: Dict[str, Any]) -> int:
    """Extracted from exit_rules holding_days"""
    for r in dsl.get("exit_rules", []):
        if r.get("type") == "holding_days" and r.get("days") is not None:
            return r["days"]
    return 0


def validate_dsl_semantics(dsl: Dict[str, Any]) -> List[str]:
    """
    Semantic verification, returns error/warning list (empty list indicates pass)
    """
    errors: List[str] = []

    # 1. symbols Not empty
    uni = dsl.get("universe", {})
    symbols = uni.get("symbols") if isinstance(uni, dict) else []
    if not symbols:
        errors.append("Stock pool symbols cannot be empty")

    # 2. start_year < end_year
    cfg = dsl.get("config", {}) or {}
    start_year = cfg.get("start_year")
    end_year = cfg.get("end_year")
    if start_year is not None and end_year is not None:
        try:
            sy, ey = int(start_year), int(end_year)
            if sy >= ey:
                errors.append(f"Backtest interval start_year({sy}) should be less than end_year({ey})")
        except (TypeError, ValueError):
            pass

    # 3. entry_months Relationship with exit_months
    entry_months = _get_entry_months(dsl)
    exit_months = _get_exit_months(dsl)
    if entry_months and exit_months:
        min_entry = min(entry_months)
        max_exit = max(exit_months)
        if min_entry >= max_exit:
            errors.append(
                f"buying month({entry_months})and selling month({exit_months})The order is unreasonable,"
                "The buying month should be earlier than the selling month (such as buying in January and selling in February)"
            )

    # 4. Spring Festival strategy: If the description contains "Spring Festival" and "after the Spring Festival", holding_days should not be too long.
    desc = (dsl.get("description") or "").lower()
    holding_days = _get_holding_days(dsl)
    if holding_days > 0 and ("Spring Festival" in desc or "After the Spring Festival" in desc):
        if holding_days > 45:
            errors.append(
                f"The Spring Festival strategy sell after the Spring Festival usually holds positions for about 20-35 trading days. Currently holding_days={holding_days} On the long side,"
                "It is recommended to change to exit calendar_month months=[2] or holding_days<=35"
            )

    # 5. max_positions with the number of symbols
    max_pos = cfg.get("max_positions", 10)
    if symbols and max_pos > len(symbols):
        pass  # Allowed, no error reported
    if symbols and max_pos < 1:
        errors.append("max_positions at least for 1")

    return errors
