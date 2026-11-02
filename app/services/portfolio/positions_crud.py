"""Portfolio position CRUD and P&L calculation helpers."""
from __future__ import annotations

from typing import Any, Dict


class PortfolioPositionsCRUD:
    """Compute position P&L metrics and normalize portfolio position documents."""

    @staticmethod
    def compute_position_metrics(
        quantity: float,
        avg_cost: float,
        current_price: float,
    ) -> Dict[str, float]:
        """Compute market value, cost basis, unrealized P&L, and return percentage."""
        qty = max(0.0, float(quantity))
        cost = max(0.0, float(avg_cost))
        price = max(0.0, float(current_price))
        cost_basis = qty * cost
        market_value = qty * price
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0
        return {
            "cost_basis": round(cost_basis, 4),
            "market_value": round(market_value, 4),
            "unrealized_pnl": round(pnl, 4),
            "unrealized_pnl_pct": round(pnl_pct, 4),
        }

    @classmethod
    def enrich_position_doc(cls, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Attach calculated P&L fields to a raw portfolio position dictionary."""
        out = dict(doc)
        metrics = cls.compute_position_metrics(
            out.get("quantity", 0.0),
            out.get("avg_cost", 0.0),
            out.get("current_price", out.get("avg_cost", 0.0)),
        )
        out.update(metrics)
        return out
