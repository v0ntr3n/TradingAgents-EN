"""LLM provider and API key resolution for analysis execution."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional
from core.config.settings import get_settings


class AnalysisProviderResolver:
    """Resolve active LLM provider, model name, and API key for analysis runs."""

    @staticmethod
    def resolve_provider_config(parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return resolved provider, quick model, and deep model configuration."""
        params = parameters or {}
        cfg = get_settings().llm
        provider = str(params.get("llm_provider") or cfg.default_provider).lower()
        quick_model = str(params.get("quick_analysis_model") or cfg.quick_think_llm)
        deep_model = str(params.get("deep_analysis_model") or cfg.deep_think_llm)
        env_key = f"{provider.upper()}_API_KEY"
        return {
            "provider": provider,
            "quick_think_llm": quick_model,
            "deep_think_llm": deep_model,
            "has_api_key": bool(os.getenv(env_key)),
        }
