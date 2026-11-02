"""Modular LLM provider & model catalog configuration sub-router."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from app.services.config.model_catalog import list_models_by_provider, load_model_catalog

router = APIRouter(tags=["config-llm"])


@router.get("/llm/registry-catalog")
async def get_llm_registry_catalog(
    provider: Optional[str] = Query(default=None, description="Optional provider filter"),
) -> List[Dict[str, Any]]:
    """Return canonical LLM model definitions from `configs/models_registry.yaml`."""
    if provider:
        return list_models_by_provider(provider)
    return load_model_catalog()
