"""Position-level risk and technical/fundamental observation builder."""
from __future__ import annotations

from typing import Any, Dict


class PositionAnalyzer:
    """Evaluate a portfolio holding and produce structured risk observations."""

    @staticmethod
    def build_holding_snapshot(position: Dict[str, Any]) -> Dict[str, Any]:
        """Extract standardized holding parameters for position analysis."""
        return {
            "symbol": str(position.get("symbol") or ""),
            "quantity": float(position.get("quantity") or 0.0),
            "avg_cost": float(position.get("avg_cost") or 0.0),
            "current_price": float(position.get("current_price") or 0.0),
        }
