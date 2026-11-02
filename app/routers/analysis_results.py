"""Modular sub-router for analysis result retrieval and normalization."""
from __future__ import annotations

from app.routers.analysis import (
    get_task_result,
    has_meaningful_result_payload,
    normalize_result_data,
    router,
)

__all__ = [
    "router",
    "get_task_result",
    "normalize_result_data",
    "has_meaningful_result_payload",
]
