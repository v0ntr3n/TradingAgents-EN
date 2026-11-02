"""Modular sub-router for single-stock analysis task creation and cancellation."""
from __future__ import annotations

from app.routers.analysis import (
    cancel_task,
    create_single_analysis_task,
    get_task_status,
    router,
)

__all__ = [
    "router",
    "create_single_analysis_task",
    "get_task_status",
    "cancel_task",
]
