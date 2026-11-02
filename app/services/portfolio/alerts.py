"""Stop-loss and take-profit threshold alert evaluation for portfolio positions."""
from __future__ import annotations

from typing import Any, Dict, Optional


class PositionAlertEvaluator:
    """Check whether a holding breaches configured stop-loss or take-profit thresholds."""

    @staticmethod
    def evaluate_thresholds(
        current_price: float,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Return alert status and trigger reason for a position."""
        price = float(current_price)
        if stop_loss_price is not None and price <= float(stop_loss_price):
            return {"triggered": True, "type": "stop_loss", "price": price}
        if take_profit_price is not None and price >= float(take_profit_price):
            return {"triggered": True, "type": "take_profit", "price": price}
        return {"triggered": False, "type": None, "price": price}
