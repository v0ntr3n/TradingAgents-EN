"""Modular sub-router for batch stock analysis submission and history queries."""
from __future__ import annotations

from app.routers.analysis import (
    create_batch_analysis,
    get_analysis_history,
    router,
)

__all__ = [
    "router",
    "create_batch_analysis",
    "get_analysis_history",
]
