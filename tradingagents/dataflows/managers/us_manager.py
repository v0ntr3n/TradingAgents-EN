"""US and Hong Kong equity market data manager."""
from __future__ import annotations

from typing import Optional


class USDataSourceManager:
    """Coordinate US and HK equity price and fundamental retrieval across providers."""

    def __init__(self, preferred_source: str = "yfinance") -> None:
        self.preferred_source = preferred_source

    def get_us_stock_data(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> str:
        """Fetch formatted US equity price history via DataSourceManager."""
        from tradingagents.dataflows.data_source_manager import get_data_source_manager

        return get_data_source_manager().get_us_stock_data(symbol, start_date, end_date)
