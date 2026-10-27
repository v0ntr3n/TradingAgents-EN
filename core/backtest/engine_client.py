"""
Backtesting engine HTTP client
Call the independently deployed Backtrader service (Avoid GPL contagion)
"""
import logging
import os
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

BACKTEST_SERVICE_URL = os.getenv("BACKTEST_SERVICE_URL", "http://localhost:8900")
# Backtesting may take a long time (large amounts of data, multiple stocks, long periods), default is 20 minutes
TIMEOUT = float(os.getenv("BACKTEST_SERVICE_TIMEOUT", "1200"))


class BacktestEngineClient:
    """Backtrader Serving HTTP clients"""

    def __init__(self, base_url: str | None = None, timeout: float = TIMEOUT):
        self.base_url = (base_url or BACKTEST_SERVICE_URL).rstrip("/")
        self.timeout = timeout

    async def health(self) -> Dict[str, Any]:
        """health check"""
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{self.base_url}/health")
            r.raise_for_status()
            return r.json()

    async def run(self, strategy_dsl: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform backtesting (DSL)
        Args:
            strategy_dsl: Strategy DSL (JSON)
        Returns:
            {"success": bool, "summary": {...}, "error": str|None}
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/run",
                json={"strategy": strategy_dsl},
            )
            r.raise_for_status()
            return r.json()

    async def run_python(
        self, code: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform backtesting (Python code + config) 
        Args:
            code: Backtrader Strategy class Python code (class name GeneratedStrategy)
            config: Backtest configuration (symbols/universe, start_year, end_year, etc.)
        Returns:
            {"success": bool, "summary": {...}, "error": str|None}
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/run_python",
                json={"code": code, "config": config},
            )
            r.raise_for_status()
            return r.json()


def get_engine_client() -> BacktestEngineClient:
    """Get the backtest engine client singleton"""
    return BacktestEngineClient()
