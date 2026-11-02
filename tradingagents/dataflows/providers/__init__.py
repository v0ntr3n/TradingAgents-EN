"""
Unified data source provider package
Organize data providers by market classification
"""
from .base_provider import BaseStockDataProvider

# Import China market provider (new path)
try:
    from .china import (
        AKShareProvider,
        TushareProvider,
        BaostockProvider as BaoStockProvider,
        AKSHARE_AVAILABLE,
        TUSHARE_AVAILABLE,
        BAOSTOCK_AVAILABLE
    )
except ImportError:
    # Backward compatibility: try importing from old path
    try:
        from .tushare_provider import TushareProvider
    except ImportError:
        TushareProvider = None

    try:
        from .akshare_provider import AKShareProvider
    except ImportError:
        AKShareProvider = None

    try:
        from .baostock_provider import BaoStockProvider
    except ImportError:
        BaoStockProvider = None

    AKSHARE_AVAILABLE = AKShareProvider is not None
    TUSHARE_AVAILABLE = TushareProvider is not None
    BAOSTOCK_AVAILABLE = BaoStockProvider is not None

# Import Hong Kong stock provider
try:
    from .hk import (
        ImprovedHKStockProvider,
        get_improved_hk_provider,
        HK_PROVIDER_AVAILABLE
    )
except ImportError:
    ImprovedHKStockProvider = None
    get_improved_hk_provider = None
    HK_PROVIDER_AVAILABLE = False

# Import US stock provider
try:
    from .us import (
        YFinanceUtils,
        OptimizedUSDataProvider,
        get_data_in_range,
        YFINANCE_AVAILABLE,
        OPTIMIZED_US_AVAILABLE,
        FINNHUB_AVAILABLE
    )
except ImportError:
    # Backward compatibility: try importing from old path
    try:
        from ..yfin_utils import YFinanceUtils
    except ImportError:
        YFinanceUtils = None

    try:
        from ..optimized_us_data import OptimizedUSDataProvider
    except ImportError:
        OptimizedUSDataProvider = None

    try:
        from ..finnhub_utils import get_data_in_range
    except ImportError:
        get_data_in_range = None

    YFINANCE_AVAILABLE = YFinanceUtils is not None
    OPTIMIZED_US_AVAILABLE = OptimizedUSDataProvider is not None
    FINNHUB_AVAILABLE = get_data_in_range is not None

# Other providers (reserved)
try:
    from .yahoo_provider import YahooProvider
except ImportError:
    YahooProvider = None

try:
    from .finnhub_provider import FinnhubProvider
except ImportError:
    FinnhubProvider = None

# TDXProvider Removed
# try:
#     from .tdx_provider import TDXProvider
# except ImportError:
#     TDXProvider = None

__all__ = [
    # base class
    'BaseStockDataProvider',

    # Chinese market
    'TushareProvider',
    'AKShareProvider',
    'BaoStockProvider',
    'AKSHARE_AVAILABLE',
    'TUSHARE_AVAILABLE',
    'BAOSTOCK_AVAILABLE',

    # Hong Kong stocks
    'ImprovedHKStockProvider',
    'get_improved_hk_provider',
    'HK_PROVIDER_AVAILABLE',

    # US stocks
    'YFinanceUtils',
    'OptimizedUSDataProvider',
    'get_data_in_range',
    'YFINANCE_AVAILABLE',
    'OPTIMIZED_US_AVAILABLE',
    'FINNHUB_AVAILABLE',

    # Others (reserved)
    'YahooProvider',
    'FinnhubProvider',
    # 'TDXProvider'  # Removed
]

import sys as _sys
_self_prov = _sys.modules[__name__]
for _cn_mod in (
    'tradingagents.dataflows.providers.china',
    'tradingagents.dataflows.providers.china.akshare',
    'tradingagents.dataflows.providers.china.tushare',
    'tradingagents.dataflows.providers.china.baostock',
    'tradingagents.dataflows.providers.china.fundamentals_snapshot',
    'tradingagents.dataflows.optimized_china_data',
    'tradingagents.config.tushare_config',
):
    _sys.modules[_cn_mod] = _self_prov

OptimizedChinaDataProvider = OptimizedUSDataProvider
BaostockProvider = BaoStockProvider
def get_akshare_provider(*args, **kwargs): return None
def get_tushare_provider(*args, **kwargs): return None
def get_tushare_adapter(*args, **kwargs): return None
def get_baostock_provider(*args, **kwargs): return None
def get_cn_fund_snapshot(*args, **kwargs): return {}
def get_tushare_config(*args, **kwargs): return None
