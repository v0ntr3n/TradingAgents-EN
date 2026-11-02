"""Re-export FinBenAdapter in `core.arena` for unified external benchmark imports."""

from core.finben.finben_adapter import (
    FINBEN_FINTRADE_10_TICKERS,
    FINBEN_TABLE8_REQUIRED_KEYS,
    FinBenAdapter,
)

__all__ = [
    "FINBEN_FINTRADE_10_TICKERS",
    "FINBEN_TABLE8_REQUIRED_KEYS",
    "FinBenAdapter",
]
