"""Modular system and database settings sub-router."""
from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter
from core.config.settings import get_settings

router = APIRouter(tags=["config-system"])


@router.get("/system/unified-settings")
async def get_unified_settings_snapshot() -> Dict[str, Any]:
    """Return non-sensitive snapshot of unified Pydantic v2 AppSettings."""
    cfg = get_settings()
    return {
        "debug": cfg.debug,
        "host": cfg.host,
        "port": cfg.port,
        "timezone": cfg.timezone,
        "llm": cfg.llm.model_dump(),
        "datasource": cfg.datasource.model_dump(),
        "agent_runtime": cfg.agent_runtime.model_dump(),
    }
