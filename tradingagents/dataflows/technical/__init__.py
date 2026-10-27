"""
Technical indicator calculation module
Provides calculation functions for various technical analysis indicators
"""

# import stockstats
try:
    from .stockstats import StockstatsUtils
    STOCKSTATS_AVAILABLE = True
except ImportError:
    StockstatsUtils = None
    STOCKSTATS_AVAILABLE = False

__all__ = [
    'StockstatsUtils',
    'STOCKSTATS_AVAILABLE',
]

