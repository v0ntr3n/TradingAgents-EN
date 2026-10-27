"""
US stock data provider
contains Finnhub, Yahoo Finance Waiting for US stock data sources
"""

# Import Finnhub tools
try:
    from .finnhub import get_data_in_range
    FINNHUB_AVAILABLE = True
except ImportError:
    get_data_in_range = None
    FINNHUB_AVAILABLE = False

# Import Yahoo Finance tools
try:
    from .yfinance import YFinanceUtils
    YFINANCE_AVAILABLE = True
except ImportError:
    YFinanceUtils = None
    YFINANCE_AVAILABLE = False

# Import optimized US stock data provider
try:
    from .optimized import OptimizedUSDataProvider
    OPTIMIZED_US_AVAILABLE = True
except ImportError:
    OptimizedUSDataProvider = None
    OPTIMIZED_US_AVAILABLE = False

# Use optimized providers by default
DefaultUSProvider = OptimizedUSDataProvider

__all__ = [
    # Finnhub
    'get_data_in_range',
    'FINNHUB_AVAILABLE',

    # Yahoo Finance
    'YFinanceUtils',
    'YFINANCE_AVAILABLE',

    # Optimized provider
    'OptimizedUSDataProvider',
    'OPTIMIZED_US_AVAILABLE',
    'DefaultUSProvider',
]

