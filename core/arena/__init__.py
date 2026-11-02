"""
External Financial Agent Benchmarks Package (`core/arena/`):
  - Agent Market Arena (AMA, arXiv:2510.11695v2 — `AMAProtocolAdapter`, `ama_router`, `app`)
  - FinBen FinTrade 10-Stock Benchmark (`arXiv:2402.12659v2` — `FinBenAdapter`)
"""

from core.arena.ama_adapter import (
    AMA_CORE_CRYPTOS,
    AMA_CORE_STOCKS,
    AMA_EXTENDED_CRYPTOS,
    AMA_EXTENDED_STOCKS,
    AMAProtocolAdapter,
    AMATradingActionRequest,
    AMATradingActionResponse,
    ama_router,
    app,
    create_ama_fastapi_app,
)
from core.finben.finben_adapter import (
    FINBEN_FINTRADE_10_TICKERS,
    FINBEN_TABLE8_REQUIRED_KEYS,
    FinBenAdapter,
)

__all__ = [
    "AMA_CORE_CRYPTOS",
    "AMA_CORE_STOCKS",
    "AMA_EXTENDED_CRYPTOS",
    "AMA_EXTENDED_STOCKS",
    "AMAProtocolAdapter",
    "AMATradingActionRequest",
    "AMATradingActionResponse",
    "FINBEN_FINTRADE_10_TICKERS",
    "FINBEN_TABLE8_REQUIRED_KEYS",
    "FinBenAdapter",
    "ama_router",
    "app",
    "create_ama_fastapi_app",
]
