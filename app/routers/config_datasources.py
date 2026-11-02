"""Modular market data source configuration sub-router."""
from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter
from app.services.config.datasource_validator import DataSourceValidator
from app.services.config_service import config_service

router = APIRouter(tags=["config-datasources"])


@router.post("/datasource/validate")
async def validate_datasource_endpoint(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate market data source configuration parameters."""
    return await DataSourceValidator.test_datasource_connection(config_service, payload)
