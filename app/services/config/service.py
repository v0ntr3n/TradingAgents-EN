"""Modular ConfigService facade delegating validation and model catalog lookups."""
from __future__ import annotations

from typing import Any, Dict, List
from app.services.config_service import ConfigService, config_service
from .database_validator import DatabaseValidator
from .datasource_validator import DataSourceValidator
from .llm_validator import LLMConfigValidator
from .model_catalog import list_models_by_provider, load_model_catalog


class ModularConfigService:
    """Facade combining ConfigService CRUD with modular validators and YAML model catalog."""

    def __init__(self, delegate: ConfigService | None = None) -> None:
        self.delegate = delegate or config_service
        self.llm_validator = LLMConfigValidator()
        self.datasource_validator = DataSourceValidator()
        self.database_validator = DatabaseValidator()

    def get_catalog_models(self, provider: str | None = None) -> List[Dict[str, Any]]:
        """Return model definitions from `configs/models_registry.yaml`."""
        if provider:
            return list_models_by_provider(provider)
        return load_model_catalog()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)


def get_modular_config_service() -> ModularConfigService:
    """Return singleton ModularConfigService instance."""
    return ModularConfigService(config_service)
