"""Template-method base class for market data synchronization workers (`app/worker/base_market_sync.py`)."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("worker.market_sync")


class BaseMarketSyncService:
    """Shared batching, progress tracking, and status reporting template for market sync workers."""

    provider_name: str = "base"

    def __init__(self, batch_size: int = 100) -> None:
        self.batch_size = max(1, int(batch_size))
        self._current_job_id: Optional[str] = None
        self._last_sync_status: Dict[str, Any] = {
            "provider": self.provider_name,
            "status": "idle",
            "updated_at": None,
        }

    def _record_status(self, status: str, **extra: Any) -> Dict[str, Any]:
        payload = {
            "provider": self.provider_name,
            "status": status,
            "job_id": self._current_job_id,
            "updated_at": datetime.utcnow().isoformat(),
            **extra,
        }
        self._last_sync_status = payload
        return payload

    async def sync_basic_info(self, force_update: bool = False) -> Dict[str, Any]:
        """Template method for synchronizing equity basic info."""
        return self._record_status("completed", task="basic_info", force_update=force_update)

    async def sync_daily_quotes(self, trade_date: Optional[str] = None) -> Dict[str, Any]:
        """Template method for synchronizing daily or real-time quotes."""
        return self._record_status("completed", task="daily_quotes", trade_date=trade_date)

    async def sync_historical_data(
        self,
        symbols: Optional[List[str]] = None,
        incremental: bool = True,
    ) -> Dict[str, Any]:
        """Template method for synchronizing historical OHLCV bars."""
        return self._record_status(
            "completed",
            task="historical_data",
            symbol_count=len(symbols or []),
            incremental=incremental,
        )

    async def sync_financial_data(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """Template method for synchronizing quarterly financial statements."""
        return self._record_status("completed", task="financial_data", symbol_count=len(symbols or []))

    async def sync_news_data(
        self,
        symbols: Optional[List[str]] = None,
        max_news_per_stock: int = 20,
        favorites_only: bool = True,
    ) -> Dict[str, Any]:
        """Template method for synchronizing stock news articles."""
        return self._record_status(
            "completed",
            task="news_data",
            symbol_count=len(symbols or []),
            max_news_per_stock=max_news_per_stock,
            favorites_only=favorites_only,
        )

    async def get_sync_status(self) -> Dict[str, Any]:
        """Return latest synchronization status dictionary."""
        return dict(self._last_sync_status)
