"""Compliance-safe formatting for portfolio position research observations."""
from __future__ import annotations

from typing import Any, Dict, Optional
from app.utils.compliance import sanitize_position_analysis_payload


class PositionAdviceFormatter:
    """Sanitize and format position analysis output into compliant research observations."""

    @staticmethod
    def format_advice(
        result_data: Dict[str, Any],
        position_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Sanitize position analysis payload via compliance rules."""
        return sanitize_position_analysis_payload(result_data, position_snapshot=position_snapshot)
