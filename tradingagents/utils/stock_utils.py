"""
Stock instrument functions
Provides stock code identification, classification and processing functions
"""

import re
from typing import Dict, Tuple, Optional
from enum import Enum

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")


class StockMarket(Enum):
    """Stock market enum"""
    CHINA_A = "china_a"      # China A shares
    HONG_KONG = "hong_kong"  # Hong Kong stocks
    US = "us"                # US stocks
    UNKNOWN = "unknown"      # unknown


class SecurityType(Enum):
    """Security type enum"""
    STOCK = "stock"          # stocks
    FUND = "fund"            # fund/ETF
    BOND = "bond"            # bonds
    INDEX = "index"          # Index
    UNKNOWN = "unknown"      # unknown


class StockUtils:
    """Stock instruments"""
    
    @staticmethod
    def identify_stock_market(ticker: str) -> StockMarket:
        """
        Identify the market to which the stock code belongs

        Args:
            ticker: Stock code

        Returns:
            StockMarket: stock market types
        """
        if not ticker:
            return StockMarket.UNKNOWN

        ticker = str(ticker).strip().upper()

        # China A-shares: pure 6-digit number, or with exchange suffix (000001.SZ, 600519.SH, 600519.SS, etc.)
        if re.match(r'^\d{6}$', ticker):
            return StockMarket.CHINA_A
        # Compatible with Tushare/Yahoo and other formats: 002594.SZ, 000001.SZ, 600519.SH, 600519.SS, 600519.XSHG,000001.XSHE
        if re.match(r'^\d{6}\.(SZ|SH|SS|XSHE|XSHG)$', ticker):
            return StockMarket.CHINA_A

        # Hong Kong stocks: 4-5 digits .HK or pure 4-5 digits (supports 0700.HK, 09988.HK, 00700, 9988 formats)
        if re.match(r'^\d{4,5}\.HK$', ticker) or re.match(r'^\d{4,5}$', ticker):
            return StockMarket.HONG_KONG

        # US stocks: 1-5 letters
        if re.match(r'^[A-Z]{1,5}$', ticker):
            return StockMarket.US

        return StockMarket.UNKNOWN

    @staticmethod
    def identify_security_type(ticker: str) -> SecurityType:
        """
        Identify security type (stock/fund/bond/index)

        A Stock code rules:
        - Stocks:
          - Shanghai main board:600xxx, 601xxx, 603xxx, 605xxx
          - Shanghai Science and Technology Innovation Board:688xxx
          - Shenzhen main board:000xxx, 001xxx
          - Shenzhen Small and Medium Enterprises Board:002xxx
          - Shenzhen GEM:300xxx, 301xxx
          - North Exchange:8xxxxx, 4xxxxx, 92xxxx (920 Unified number segment starting from 2025-10)
        - Fund/ETF:
          - Shanghai Exchange:5xxxxx (Such as 510050 Shanghai Stock Exchange 50ETF)
          - Shenzhen Exchange:1xxxxx (Such as 159919 Shanghai and Shenzhen 300ETF)
          - LOF Fund:16xxxx
        - Bond:
          - Treasury bonds:01xxxx
          - Corporate bonds:12xxxx, 11xxxx
          - Convertible bonds:11xxxx, 12xxxx, 13xxxx
        - Index:
          - Shanghai Composite Index:000xxx (Such as 000001 Shanghai Composite Index)
          - Shenzhen Stock Exchange Index:399xxx

        Args:
            ticker: Securities code

        Returns:
            SecurityType: Security type
        """
        if not ticker:
            return SecurityType.UNKNOWN

        # Remove the suffix and keep only the number part
        ticker = str(ticker).strip().upper()
        code = re.sub(r'\.(SZ|SH|BJ)$', '', ticker)

        if not code.isdigit() or len(code) != 6:
            return SecurityType.UNKNOWN

        prefix = code[:2]
        prefix3 = code[:3]

        # Fund/ETF identification (priority judgment, because the fund code range is clearer)
        # Shanghai Exchange Fund:5xxxxx
        if prefix == '51' or prefix == '50' or prefix == '52':
            return SecurityType.FUND
        # Shenzhen Exchange Fund:1xxxxx (15xxxx, 16xxxx)
        if prefix == '15' or prefix == '16':
            return SecurityType.FUND

        # Index identification
        # Shanghai Composite Index: Starting with 000xxx but within a specific range
        # Note: 000001-000999 is a stock in Shenzhen and an index in Shanghai
        # Simplified processing: 399xxx is the Shenzhen Stock Exchange Index
        if prefix3 == '399':
            return SecurityType.INDEX

        # Bond identification (simplified, mainly identifying convertible bonds)
        # Convertible bonds Shenzhen:12xxxx, 13xxxx
        # Convertible bonds Shanghai:11xxxx
        if prefix == '11' or prefix == '12' or prefix == '13':
            # Further distinction:110xxx, 113xxx, 127xxx, 128xxx It's a convertible bond
            if prefix3 in ['110', '113', '127', '128', '123']:
                return SecurityType.BOND

        # Stock identification (remaining 6-digit code)
        # Shanghai main board:600xxx, 601xxx, 603xxx, 605xxx
        if prefix in ['60']:
            return SecurityType.STOCK
        # Shanghai Science and Technology Innovation Board:688xxx
        if prefix3 == '688':
            return SecurityType.STOCK
        # Shenzhen main board:000xxx, 001xxx
        if prefix in ['00']:
            return SecurityType.STOCK
        # Shenzhen Small and Medium Enterprises Board:002xxx
        if prefix3 == '002':
            return SecurityType.STOCK
        # Shenzhen GEM:300xxx, 301xxx
        if prefix in ['30']:
            return SecurityType.STOCK
        # North Exchange:8xxxxx, 4xxxxx, 92xxxx (920 Unified number segment starting from 2025-10)
        if prefix[0] in ['8', '4'] or prefix == '92':
            return SecurityType.STOCK

        return SecurityType.UNKNOWN

    @staticmethod
    def is_stock(ticker: str) -> bool:
        """
        Determine whether it is a stock (excluding funds, bonds, and indices)

        Args:
            ticker: Securities code

        Returns:
            bool: Is it a stock?
        """
        return StockUtils.identify_security_type(ticker) == SecurityType.STOCK

    @staticmethod
    def is_fund(ticker: str) -> bool:
        """
        Determine whether it is a fund/ETF

        Args:
            ticker: Securities code

        Returns:
            bool: Is it a fund?/ETF
        """
        return StockUtils.identify_security_type(ticker) == SecurityType.FUND

    @staticmethod
    def is_china_stock(ticker: str) -> bool:
        """
        Determine whether it is China A-share
        
        Args:
            ticker: Stock code
            
        Returns:
            bool: Is it a Chinese A-share?
        """
        return StockUtils.identify_stock_market(ticker) == StockMarket.CHINA_A
    
    @staticmethod
    def is_hk_stock(ticker: str) -> bool:
        """
        Determine whether it is a Hong Kong stock
        
        Args:
            ticker: Stock code
            
        Returns:
            bool: Is it a Hong Kong stock?
        """
        return StockUtils.identify_stock_market(ticker) == StockMarket.HONG_KONG
    
    @staticmethod
    def is_us_stock(ticker: str) -> bool:
        """
        Determine whether it is a US stock
        
        Args:
            ticker: Stock code
            
        Returns:
            bool: Is it a US stock?
        """
        return StockUtils.identify_stock_market(ticker) == StockMarket.US
    
    @staticmethod
    def get_currency_info(ticker: str) -> Tuple[str, str]:
        """
        Get currency information based on stock code
        
        Args:
            ticker: Stock code
            
        Returns:
            Tuple[str, str]: (currency name, currency symbol)
        """
        market = StockUtils.identify_stock_market(ticker)
        
        if market == StockMarket.CHINA_A:
            return "RMB", "¥"
        elif market == StockMarket.HONG_KONG:
            return "Hong Kong dollar", "HK$"
        elif market == StockMarket.US:
            return "US dollars", "$"
        else:
            return "unknown", "?"
    
    @staticmethod
    def get_data_source(ticker: str) -> str:
        """
        Get recommended data sources based on stock ticker
        
        Args:
            ticker: Stock code
            
        Returns:
            str: Data source name
        """
        market = StockUtils.identify_stock_market(ticker)
        
        if market == StockMarket.CHINA_A:
            return "china_unified"  # Use a unified Chinese stock data source
        elif market == StockMarket.HONG_KONG:
            return "yahoo_finance"  # Hong Kong stocks use Yahoo Finance
        elif market == StockMarket.US:
            return "yahoo_finance"  # US stocks use Yahoo Finance
        else:
            return "unknown"
    
    @staticmethod
    def normalize_hk_ticker(ticker: str) -> str:
        """
        Standardized Hong Kong stock code format
        
        Args:
            ticker: Original Hong Kong stock code
            
        Returns:
            str: Standardized Hong Kong stock code
        """
        if not ticker:
            return ticker
            
        ticker = str(ticker).strip().upper()
        
        # If it is a pure 4-5 digit number, add the .HK suffix
        if re.match(r'^\d{4,5}$', ticker):
            return f"{ticker}.HK"

        # If it is already in the correct format, return directly
        if re.match(r'^\d{4,5}\.HK$', ticker):
            return ticker
            
        return ticker
    
    @staticmethod
    def get_market_info(ticker: str) -> Dict:
        """
        Get detailed information on the stock market
        
        Args:
            ticker: Stock code
            
        Returns:
            Dict: Market Information Dictionary
        """
        market = StockUtils.identify_stock_market(ticker)
        currency_name, currency_symbol = StockUtils.get_currency_info(ticker)
        data_source = StockUtils.get_data_source(ticker)
        
        market_names = {
            StockMarket.CHINA_A: "China A shares",
            StockMarket.HONG_KONG: "Hong Kong stocks",
            StockMarket.US: "US stocks",
            StockMarket.UNKNOWN: "unknown market"
        }
        
        return {
            "ticker": ticker,
            "market": market.value,
            "market_name": market_names[market],
            "currency_name": currency_name,
            "currency_symbol": currency_symbol,
            "data_source": data_source,
            "is_china": market == StockMarket.CHINA_A,
            "is_hk": market == StockMarket.HONG_KONG,
            "is_us": market == StockMarket.US
        }


# Convenience functions to maintain backward compatibility
def is_china_stock(ticker: str) -> bool:
    """Determine whether it is a Chinese A-share (backwards compatible)"""
    return StockUtils.is_china_stock(ticker)


def is_hk_stock(ticker: str) -> bool:
    """Determine whether it is a Hong Kong stock"""
    return StockUtils.is_hk_stock(ticker)


def is_us_stock(ticker: str) -> bool:
    """Determine whether it is a US stock"""
    return StockUtils.is_us_stock(ticker)


def get_stock_market_info(ticker: str) -> Dict:
    """Get stock market information"""
    return StockUtils.get_market_info(ticker)
