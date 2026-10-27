# tradingagents/core/engine/phase_executors/data_collection.py
"""
Data collection phase executor (initialization phase)

Responsibilities:
- Initialize basic information of the analysis context
- Verify the validity of input parameters
- Optional: Preload public basic data (such as basic company information)

Note:
- This stage does not replace the Agent s tools data acquisition capabilities.
- Agent Still get the required data from dataflows through their respective tools
- Agent Write the analysis results to the Context for other Agents to read
"""

from typing import Any, Dict, Optional

from tradingagents.utils.logging_init import get_logger

from ..analysis_context import AnalysisContext
from ..data_access_manager import DataAccessManager
from ..data_contract import DataLayer
from .base import PhaseExecutor

logger = get_logger("default")


class DataCollectionPhase(PhaseExecutor):
    """
    Data collection phase executor (actually initialization phase)

    Main responsibilities:
    1. Validate and normalize input parameters (ticker, trade_date etc.)
    2. Initialize basic information of Context
    3. Optional: Preload public data such as basic company information

    Note: Original data acquisition is completed by each Agent through tools.
    """

    phase_name = "DataCollectionPhase"

    def __init__(
        self,
        llm_provider: Any = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initial data collection phase

        Args:
            llm_provider: LLM Provider (not required at this stage)
            config: stage configuration
        """
        super().__init__(llm_provider, config)

    def execute(
        self,
        context: AnalysisContext,
        data_manager: DataAccessManager
    ) -> Dict[str, Any]:
        """
        Execute initialization phase

        Args:
            context: Analyze context
            data_manager: Data Access Manager

        Returns:
            Summary of initialization results
        """
        self.log_start()

        # Obtain and verify contextual information
        ticker = context.get(DataLayer.CONTEXT, "ticker")
        trade_date = context.get(DataLayer.CONTEXT, "trade_date")
        company_name = context.get(DataLayer.CONTEXT, "company_name")
        market_type = context.get(DataLayer.CONTEXT, "market_type") or self._detect_market_type(ticker)

        logger.info(f"📊 [{self.phase_name}] Initialize analysis context: {ticker} ({trade_date})")

        # Verify necessary parameters
        if not ticker:
            raise ValueError("ticker is a required parameter")
        if not trade_date:
            raise ValueError("trade_date is a required parameter")

        # Normalize ticker format
        normalized_ticker = self._normalize_ticker(ticker, market_type)
        if normalized_ticker != ticker:
            context.set(DataLayer.CONTEXT, "ticker", normalized_ticker, source=self.phase_name)
            logger.debug(f"📊 [{self.phase_name}] ticker Standardize: {ticker} -> {normalized_ticker}")

        # Set market type (if not set)
        if not context.get(DataLayer.CONTEXT, "market_type"):
            context.set(DataLayer.CONTEXT, "market_type", market_type, source=self.phase_name)

        # Build output summary
        outputs = {
            "ticker": normalized_ticker,
            "trade_date": trade_date,
            "company_name": company_name,
            "market_type": market_type,
            "initialized": True
        }

        self.log_end(outputs)
        return outputs

    def _detect_market_type(self, ticker: str) -> str:
        """
        Detect market type based on ticker format

        Args:
            ticker: Stock code

        Returns:
            market type ("cn", "us", "hk")
        """
        if not ticker:
            return "cn"

        ticker_upper = ticker.upper()

        # China A share format
        if ticker_upper.endswith((".SZ", ".SH", ".BJ")):
            return "cn"
        if ticker.isdigit() and len(ticker) == 6:
            return "cn"

        # Hong Kong stock format
        if ticker_upper.endswith(".HK"):
            return "hk"

        # Default is US stocks
        return "us"

    def _normalize_ticker(self, ticker: str, market_type: str) -> str:
        """
        Normalize ticker format

        Note: The front and back ends agree that A-share codes use pure 6-digit numbers without suffixes.

        Args:
            ticker: Original stock symbol
            market_type: market type

        Returns:
            Standardized stock code
        """
        import re

        if not ticker:
            return ticker

        ticker = ticker.strip().upper()

        if market_type == "cn":
            # China A-shares: remove the suffix and keep only the pure 6-digit number (the front and back ends are unified)
            ticker = re.sub(r'\.(SZ|SH|BJ)$', '', ticker)
            return ticker

        # Other markets remain as is
        return ticker

