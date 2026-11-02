"""Database connectivity and latency checks for MongoDB and Redis."""
from __future__ import annotations

from typing import Any, Dict


class DatabaseValidator:
    """Validate MongoDB and Redis connection parameters."""

    @staticmethod
    async def test_database_connection(
        config_service_instance: Any,
        config_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run ping and authentication checks against MongoDB or Redis."""
        return await config_service_instance._test_database_config(config_data)
