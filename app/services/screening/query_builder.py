"""MongoDB aggregation pipeline and filter builder for stock screening."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class ScreeningQueryBuilder:
    """Construct MongoDB match filters and sort specifications from screening conditions."""

    @staticmethod
    def build_range_clause(
        field_name: str,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Build a MongoDB `$gte` / `$lte` range query for a numeric field."""
        clause: Dict[str, Any] = {}
        if min_val is not None:
            clause["$gte"] = float(min_val)
        if max_val is not None:
            clause["$lte"] = float(max_val)
        return {field_name: clause} if clause else {}

    @classmethod
    def _condition_to_clause(cls, cond: Dict[str, Any]) -> Dict[str, Any]:
        field = str(cond.get("field") or "").strip()
        if not field:
            return {}
        if "min" in cond or "max" in cond:
            return cls.build_range_clause(field, cond.get("min"), cond.get("max"))
        if "value" in cond:
            return {field: cond["value"]}
        return {}

    @classmethod
    def build_match_filter(cls, conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Convert a list of condition dicts into a combined MongoDB match filter."""
        clauses = [c for cond in (conditions or []) for c in [cls._condition_to_clause(cond)] if c]
        if not clauses:
            return {}
        return {"$and": clauses} if len(clauses) > 1 else clauses[0]
