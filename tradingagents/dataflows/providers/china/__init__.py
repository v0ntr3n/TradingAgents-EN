"""
China market data provider
Contains data sources from Chinese markets such as A-shares and Hong Kong stocks
"""

# Import the AKShare provider
try:
    from .akshare import AKShareProvider
    AKSHARE_AVAILABLE = True
except ImportError:
    AKShareProvider = None
    AKSHARE_AVAILABLE = False

# Import Tushare provider
try:
    from .tushare import TushareProvider
    TUSHARE_AVAILABLE = True
except ImportError:
    TushareProvider = None
    TUSHARE_AVAILABLE = False

# Import Baostock provider
try:
    from .baostock import BaostockProvider
    BAOSTOCK_AVAILABLE = True
except ImportError:
    BaostockProvider = None
    BAOSTOCK_AVAILABLE = False

# Import Fundamental Snapshot Tool
try:
    from .fundamentals_snapshot import get_fundamentals_snapshot
    FUNDAMENTALS_SNAPSHOT_AVAILABLE = True
except ImportError:
    get_fundamentals_snapshot = None
    FUNDAMENTALS_SNAPSHOT_AVAILABLE = False

__all__ = [
    'AKShareProvider',
    'AKSHARE_AVAILABLE',
    'TushareProvider',
    'TUSHARE_AVAILABLE',
    'BaostockProvider',
    'BAOSTOCK_AVAILABLE',
    'get_fundamentals_snapshot',
    'FUNDAMENTALS_SNAPSHOT_AVAILABLE',
]

