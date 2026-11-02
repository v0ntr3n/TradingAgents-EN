"""Provider-specific LLM connectivity and API key validation helpers."""
from __future__ import annotations

from typing import Any, Dict
from app.utils.api_key_utils import is_valid_api_key


class LLMConfigValidator:
    """Validate LLM provider API keys and endpoint configurations."""

    @staticmethod
    def validate_key_format(provider: str, api_key: str) -> Dict[str, Any]:
        """Verify that the API key is non-empty and not a placeholder."""
        valid = bool(api_key and is_valid_api_key(api_key))
        return {
            "provider": provider,
            "valid": valid,
            "message": "API key format valid" if valid else "Invalid or placeholder API key",
        }

    @staticmethod
    async def test_llm_connection(config_service_instance: Any, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Delegate live LLM connectivity test to the underlying service implementation."""
        return await config_service_instance._test_llm_config(config_data)
