"""
Unified definition of data source encoding
The encoding, name, description and other information of all data sources are defined here

To add a new data source:
1. Add new data source encoding in DataSourceCode enumeration
2. Register data source information in DATA_SOURCE_REGISTRY
3. Implement the data source interface in the corresponding provider
4. Update the data source type options for the frontend (if needed)
"""

from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass


class DataSourceCode(str, Enum):
    """
    Data source encoding enumeration
    
    Naming convention:
    - Use capital letters and underlines
    - Use lowercase letters and underscores for values
    - Keep it simple and clear
    """
    
    # ==================== cache data source ====================
    MONGODB = "mongodb"  # MongoDB Database cache (highest priority)
    
    # ==================== China market data source ====================
    TUSHARE = "tushare"      # Tushare - Professional A-share data
    AKSHARE = "akshare"      # AKShare - Open source financial data (A shares+Hong Kong stocks)
    BAOSTOCK = "baostock"    # BaoStock - Free A-share data
    
    # ==================== US stock data source ====================
    YFINANCE = "yfinance"         # yfinance - Yahoo Finance Python Library
    FINNHUB = "finnhub"           # Finnhub - U.S. stock real-time data
    YAHOO_FINANCE = "yahoo_finance"  # Yahoo Finance - Global Equity Data (Alias)
    ALPHA_VANTAGE = "alpha_vantage"  # Alpha Vantage - US stock technical analysis
    IEX_CLOUD = "iex_cloud"       # IEX Cloud - U.S. stock real-time data
    
    # ==================== Hong Kong stock data source ====================
    # Note: AKShare also supports Hong Kong stocks, which have been defined above
    
    # ==================== Professional data source ====================
    WIND = "wind"        # Wind Wonder - Professional financial terminal
    CHOICE = "choice"    # Oriental Fortune Choice - Professional financial data
    QMT = "qmt"          # Xuntou QMT - Brokerage Quantitative Terminal (requires QMT to run)
    
    # ==================== Other data sources ====================
    QUANDL = "quandl"        # Quandl - Economic and financial data
    LOCAL_FILE = "local_file"  # local file data source
    LOCAL = "local"          # Local data (users import via API)
    CUSTOM = "custom"        # Custom data source


@dataclass
class DataSourceInfo:
    """Data source information"""
    code: str  # Data source encoding
    name: str  # Data source name
    display_name: str  # display name
    provider: str  # provider
    description: str  # Description
    supported_markets: List[str]  # Supported Markets (a_shares, us_stocks, hk_stocks, etc.) 
    requires_api_key: bool  # Do you need an API key?
    is_free: bool  # Is it free?
    official_website: Optional[str] = None  # Official website
    documentation_url: Optional[str] = None  # Document address
    features: List[str] = None  # Feature list
    
    def __post_init__(self):
        if self.features is None:
            self.features = []


# ==================== Data source registry ====================
DATA_SOURCE_REGISTRY: Dict[str, DataSourceInfo] = {
    # MongoDB cache
    DataSourceCode.MONGODB: DataSourceInfo(
        code=DataSourceCode.MONGODB,
        name="MongoDB",
        display_name="MongoDB cache",
        provider="MongoDB Inc.",
        description="Local MongoDB database cache, highest priority data source",
        supported_markets=["a_shares", "us_stocks", "hk_stocks", "crypto", "futures"],
        requires_api_key=False,
        is_free=True,
        features=["local cache", "fastest speed", "Available offline"],
    ),
    
    # Tushare
    DataSourceCode.TUSHARE: DataSourceInfo(
        code=DataSourceCode.TUSHARE,
        name="Tushare",
        display_name="Tushare",
        provider="Tushare",
        description="Professional A-share data interface, providing high-quality historical data and real-time market conditions",
        supported_markets=["a_shares"],
        requires_api_key=True,
        is_free=False,  # The free version has limitations, and the professional version requires payment
        official_website="https://tushare.pro",
        documentation_url="https://tushare.pro/document/2",
        features=["Historical Quotes", "Real-time quotes", "financial data", "fundamental data", "News announcement"],
    ),
    
    # AKShare
    DataSourceCode.AKSHARE: DataSourceInfo(
        code=DataSourceCode.AKSHARE,
        name="AKShare",
        display_name="AKShare",
        provider="AKFamily",
        description="Open source financial data interface, supports A shares and Hong Kong stocks, completely free",
        supported_markets=["a_shares", "hk_stocks"],
        requires_api_key=False,
        is_free=True,
        official_website="https://akshare.akfamily.xyz",
        documentation_url="https://akshare.akfamily.xyz/introduction.html",
        features=["Historical Quotes", "Real-time quotes", "financial data", "News", "completely free"],
    ),
    
    # BaoStock
    DataSourceCode.BAOSTOCK: DataSourceInfo(
        code=DataSourceCode.BAOSTOCK,
        name="BaoStock",
        display_name="BaoStock",
        provider="BaoStock",
        description="Free A-share data interface, providing stable historical data",
        supported_markets=["a_shares"],
        requires_api_key=False,
        is_free=True,
        official_website="http://baostock.com",
        documentation_url="http://baostock.com/baostock/index.php/Python_API%E6%96%87%E6%A1%A3",
        features=["Historical Quotes", "financial data", "completely free", "Data is stable"],
    ),
    
    # yfinance
    DataSourceCode.YFINANCE: DataSourceInfo(
        code=DataSourceCode.YFINANCE,
        name="yfinance",
        display_name="yfinance (Yahoo Finance)",
        provider="Yahoo Finance",
        description="Yahoo Finance Python Library, supports multiple markets such as US stocks and Hong Kong stocks, completely free",
        supported_markets=["us_stocks", "hk_stocks"],
        requires_api_key=False,
        is_free=True,
        official_website="https://finance.yahoo.com",
        documentation_url="https://pypi.org/project/yfinance/",
        features=["Historical Quotes", "Real-time quotes", "Technical indicators", "global market", "completely free"],
    ),

    # Finnhub
    DataSourceCode.FINNHUB: DataSourceInfo(
        code=DataSourceCode.FINNHUB,
        name="Finnhub",
        display_name="Finnhub",
        provider="Finnhub",
        description="U.S. stock real-time data and news interface, providing high-quality market data",
        supported_markets=["us_stocks"],
        requires_api_key=True,
        is_free=True,  # There is a free version
        official_website="https://finnhub.io",
        documentation_url="https://finnhub.io/docs/api",
        features=["Real-time quotes", "historical data", "News", "financial data", "Technical indicators"],
    ),
    
    # Yahoo Finance
    DataSourceCode.YAHOO_FINANCE: DataSourceInfo(
        code=DataSourceCode.YAHOO_FINANCE,
        name="Yahoo Finance",
        display_name="Yahoo Finance",
        provider="Yahoo",
        description="Global stock data interface, supporting multiple markets such as US stocks and Hong Kong stocks",
        supported_markets=["us_stocks", "hk_stocks"],
        requires_api_key=False,
        is_free=True,
        official_website="https://finance.yahoo.com",
        features=["Historical Quotes", "Real-time quotes", "global market", "completely free"],
    ),
    
    # Alpha Vantage
    DataSourceCode.ALPHA_VANTAGE: DataSourceInfo(
        code=DataSourceCode.ALPHA_VANTAGE,
        name="Alpha Vantage",
        display_name="Alpha Vantage",
        provider="Alpha Vantage",
        description="U.S. stock technical analysis data interface, providing a wealth of technical indicators",
        supported_markets=["us_stocks"],
        requires_api_key=True,
        is_free=True,  # There is a free version
        official_website="https://www.alphavantage.co",
        documentation_url="https://www.alphavantage.co/documentation",
        features=["Technical indicators", "historical data", "Forex data", "cryptocurrency"],
    ),
    
    # IEX Cloud
    DataSourceCode.IEX_CLOUD: DataSourceInfo(
        code=DataSourceCode.IEX_CLOUD,
        name="IEX Cloud",
        display_name="IEX Cloud",
        provider="IEX Cloud",
        description="U.S. stock real-time data interface, providing high-quality market data",
        supported_markets=["us_stocks"],
        requires_api_key=True,
        is_free=False,  # Fee required
        official_website="https://iexcloud.io",
        documentation_url="https://iexcloud.io/docs/api",
        features=["Real-time quotes", "historical data", "financial data", "News"],
    ),
    
    # Wind
    DataSourceCode.WIND: DataSourceInfo(
        code=DataSourceCode.WIND,
        name="Wind",
        display_name="Wind Wonder",
        provider="Wind Wonder",
        description="Professional financial terminal, providing comprehensive financial data and analysis tools",
        supported_markets=["a_shares", "hk_stocks", "us_stocks"],
        requires_api_key=True,
        is_free=False,  # Professional version requires payment
        official_website="https://www.wind.com.cn",
        features=["Professional data", "Full market coverage", "high quality data", "Professional analysis"],
    ),
    
    # QMT (XunTou)
    DataSourceCode.QMT: DataSourceInfo(
        code=DataSourceCode.QMT,
        name="QMT",
        display_name="XunTou QMT",
        provider="XunTou",
        description="Xuntou QMT quantification terminal requires QMT client to run (Windows), and is used for unified news AKShare",
        supported_markets=["a_shares"],
        requires_api_key=False,
        is_free=True,  # Requires brokerage to open
        official_website="https://www.xuntou.net/",
        documentation_url="https://qmt.ptradeapi.com/QMT_Python_API_Doc.html",
        features=["Historical Quotes", "Real-time quotes", "K line data", "Requires QMT to run", "News is not supported"],
    ),

    # Choice
    DataSourceCode.CHOICE: DataSourceInfo(
        code=DataSourceCode.CHOICE,
        name="Choice",
        display_name="Oriental Fortune Choice",
        provider="Oriental Fortune",
        description="Professional financial data terminal, providing comprehensive A-share data",
        supported_markets=["a_shares"],
        requires_api_key=True,
        is_free=False,  # Professional version requires payment
        official_website="http://choice.eastmoney.com",
        features=["Professional data", "A stock focus", "high quality data", "Professional analysis"],
    ),
    
    # Quandl
    DataSourceCode.QUANDL: DataSourceInfo(
        code=DataSourceCode.QUANDL,
        name="Quandl",
        display_name="Quandl",
        provider="Nasdaq",
        description="Economic and financial data platform providing global economic data",
        supported_markets=["us_stocks"],
        requires_api_key=True,
        is_free=True,  # There is a free version
        official_website="https://www.quandl.com",
        documentation_url="https://docs.quandl.com",
        features=["economic data", "financial data", "Global coverage"],
    ),
    
    # Local File
    DataSourceCode.LOCAL_FILE: DataSourceInfo(
        code=DataSourceCode.LOCAL_FILE,
        name="Local File",
        display_name="local file",
        provider="local",
        description="Read data from local file",
        supported_markets=["a_shares", "us_stocks", "hk_stocks"],
        requires_api_key=False,
        is_free=True,
        features=["Available offline", "custom data", "completely free"],
    ),

    # Local (Local data imported by users through API)
    DataSourceCode.LOCAL: DataSourceInfo(
        code=DataSourceCode.LOCAL,
        name="Local",
        display_name="local data",
        provider="local",
        description="Local data imported by users through the batch import API interface (only supports A shares)",
        supported_markets=["a_shares"],
        requires_api_key=False,
        is_free=True,
        features=["API import", "Batch import", "completely free", "Only supports A shares"],
    ),

    # Custom
    DataSourceCode.CUSTOM: DataSourceInfo(
        code=DataSourceCode.CUSTOM,
        name="Custom",
        display_name="Custom data source",
        provider="Customize",
        description="Custom data source interface",
        supported_markets=["a_shares", "us_stocks", "hk_stocks"],
        requires_api_key=False,
        is_free=True,
        features=["Custom interface", "Flexible configuration"],
    ),
}


# ==================== Helper function ====================

def get_data_source_info(code: str) -> Optional[DataSourceInfo]:
    """
    Get data source information
    
    Args:
        code: Data source encoding
    
    Returns:
        Data source information, returned if it does not exist None
    """
    return DATA_SOURCE_REGISTRY.get(code)


def list_all_data_sources() -> List[DataSourceInfo]:
    """
    List all data sources
    
    Returns:
        List of all data source information
    """
    return list(DATA_SOURCE_REGISTRY.values())


def list_data_sources_by_market(market: str) -> List[DataSourceInfo]:
    """
    List the data sources that support a specified market
    
    Args:
        market: market type (a_shares, us_stocks, hk_stocks, etc.) 
    
    Returns:
        List of data sources supporting this market
    """
    return [
        info for info in DATA_SOURCE_REGISTRY.values()
        if market in info.supported_markets
    ]


def list_free_data_sources() -> List[DataSourceInfo]:
    """
    List all free data sources
    
    Returns:
        List of free data sources
    """
    return [
        info for info in DATA_SOURCE_REGISTRY.values()
        if info.is_free
    ]


def is_data_source_supported(code: str) -> bool:
    """
    Check if the data source supports
    
    Args:
        code: Data source encoding
    
    Returns:
        Whether to support
    """
    return code in DATA_SOURCE_REGISTRY

