"""China A-share market data manager with provider fallback."""
from __future__ import annotations

from typing import Any, Optional
import pandas as pd
from tradingagents.dataflows.unified_dataframe import get_china_daily_df_unified


class ChinaDataSourceManager:
    """Coordinate China A-share daily bar and fundamental retrieval across providers."""

    def __init__(self, preferred_source: str = "akshare") -> None:
        self.preferred_source = preferred_source

    def get_daily_dataframe(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch standardized daily China A-share DataFrame."""
        return get_china_daily_df_unified(symbol, start_date, end_date)

    def get_formatted_stock_data(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> str:
        """Delegate formatted string retrieval to the primary DataSourceManager."""
        from tradingagents.dataflows.data_source_manager import get_data_source_manager

        return get_data_source_manager().get_stock_data(symbol, start_date, end_date)
