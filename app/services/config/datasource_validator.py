"""Market data source connectivity validation (Tushare, AKShare, BaoStock, Finnhub)."""
from __future__ import annotations

from typing import Any, Dict


class DataSourceValidator:
    """Validate market data source credentials and availability."""

    @staticmethod
    async def test_datasource_connection(
        config_service_instance: Any,
        config_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Test connectivity for a configured market data source."""
        return await config_service_instance._test_data_source_config(config_data)
