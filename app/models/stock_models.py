"""
Stock data model - extension based on existing collection
Adoption plan B: Extend fields based on existing collections to maintain backward compatibility
"""
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field
from bson import ObjectId


def to_str_id(v: Any) -> str:
    """ObjectId Convert string tool function"""
    try:
        if isinstance(v, ObjectId):
            return str(v)
        return str(v)
    except Exception:
        return ""


# Enumeration type definition
MarketType = Literal["CN", "HK", "US"]  # market type
ExchangeType = Literal["SZSE", "SSE", "SEHK", "NYSE", "NASDAQ"]  # exchange
StockStatus = Literal["L", "D", "P"]  # Listing status: L-Listing D-Delisting P-Suspension
CurrencyType = Literal["CNY", "HKD", "USD"]  # currency type


class MarketInfo(BaseModel):
    """Market information structure - new fields"""
    market: MarketType = Field(..., description="market identification")
    exchange: ExchangeType = Field(..., description="Exchange code")
    exchange_name: str = Field(..., description="Exchange name")
    currency: CurrencyType = Field(..., description="trading currency")
    timezone: str = Field(..., description="time zone")
    trading_hours: Optional[Dict[str, Any]] = Field(None, description="trading hours")


class TechnicalIndicators(BaseModel):
    """Technical indicator structure - classification expansion design"""
    # trend indicator
    trend: Optional[Dict[str, float]] = Field(None, description="trend indicator")
    # Oscillator  
    oscillator: Optional[Dict[str, float]] = Field(None, description="Oscillator")
    # channel indicator
    channel: Optional[Dict[str, float]] = Field(None, description="channel indicator")
    # volume indicator
    volume: Optional[Dict[str, float]] = Field(None, description="volume indicator")
    # volatility indicator
    volatility: Optional[Dict[str, float]] = Field(None, description="volatility indicator")
    # Custom indicators
    custom: Optional[Dict[str, Any]] = Field(None, description="Custom indicators")


class StockBasicInfoExtended(BaseModel):
    """
    Stock basic information extension model - based on the existing stock_basic_info collection
    Uniformly use symbol as the main stock code field
    """
    # === Standardized fields (Main fields) ===
    symbol: str = Field(..., description="6 stock code", pattern=r"^\d{6}$")
    full_symbol: str = Field(..., description="Complete standardized code(Such as 000001.SZ)")
    name: str = Field(..., description="Stock name")

    # === Compatible fields (Stay backwards compatible) ===
    code: Optional[str] = Field(None, description="6 stock code(Deprecated,Use symbol)")

    # === Basic information fields ===
    area: Optional[str] = Field(None, description="area")
    industry: Optional[str] = Field(None, description="Industry")
    market: Optional[str] = Field(None, description="Exchange name")
    list_date: Optional[str] = Field(None, description="Listing date")
    sse: Optional[str] = Field(None, description="plate")
    sec: Optional[str] = Field(None, description="Sector")
    source: Optional[str] = Field(None, description="Data source")
    updated_at: Optional[datetime] = Field(None, description="Update time")

    # market cap field
    total_mv: Optional[float] = Field(None, description="Total market capitalization(billion)")
    circ_mv: Optional[float] = Field(None, description="Circulation market value(billion)")

    # financial indicators
    pe: Optional[float] = Field(None, description="P/E ratio")
    pb: Optional[float] = Field(None, description="price to book ratio")
    pe_ttm: Optional[float] = Field(None, description="rolling price to earnings ratio")
    pb_mrq: Optional[float] = Field(None, description="Latest price-to-book ratio")
    roe: Optional[float] = Field(None, description="ROE")

    # trading indicators
    turnover_rate: Optional[float] = Field(None, description="turnover rate%")
    volume_ratio: Optional[float] = Field(None, description="Quantity ratio")

    # === extension fields ===
    name_en: Optional[str] = Field(None, description="English name")
    
    # Add market information
    market_info: Optional[MarketInfo] = Field(None, description="market information")
    
    # Add new standardized fields
    board: Optional[str] = Field(None, description="Sector standardization")
    industry_code: Optional[str] = Field(None, description="Industry code")
    sector: Optional[str] = Field(None, description="Standardization of the sector (GICS industry)")
    delist_date: Optional[str] = Field(None, description="Delisting date")
    status: Optional[StockStatus] = Field(None, description="Listing status")
    is_hs: Optional[bool] = Field(None, description="Is it subject to Shanghai-Shenzhen-Hong Kong Stock Connect?")

    # Add equity information
    total_shares: Optional[float] = Field(None, description="total share capital")
    float_shares: Optional[float] = Field(None, description="circulating capital")

    # Hong Kong stocks specific fields
    lot_size: Optional[int] = Field(None, description="Number of shares per lot (specific to Hong Kong stocks)")

    # currency field
    currency: Optional[CurrencyType] = Field(None, description="trading currency")
    
    # version control
    data_version: Optional[int] = Field(None, description="Data version")
    
    class Config:
        # Allow extra fields to maintain backward compatibility
        extra = "allow"
        # Sample data
        json_schema_extra = {
            "example": {
                # Standardized fields
                "symbol": "000001",
                "full_symbol": "000001.SZ",
                "name": "Ping An Bank",

                # Basic information
                "area": "Shenzhen",
                "industry": "bank",
                "market": "Shenzhen Stock Exchange",
                "sse": "motherboard",
                "total_mv": 2500.0,
                "pe": 5.2,
                "pb": 0.8,

                # extension fields
                "market_info": {
                    "market": "CN",
                    "exchange": "SZSE",
                    "exchange_name": "Shenzhen Stock Exchange",
                    "currency": "CNY",
                    "timezone": "Asia/Shanghai"
                },
                "status": "L",
                "data_version": 1
            }
        }


class MarketQuotesExtended(BaseModel):
    """
    Real-time quotation extension model - based on the existing market_quotes collection
    Uniformly use symbol as the main stock code field
    """
    # === Standardized fields (Main fields) ===
    symbol: str = Field(..., description="6 stock code", pattern=r"^\d{6}$")
    full_symbol: Optional[str] = Field(None, description="Complete standardized code")
    market: Optional[MarketType] = Field(None, description="market identification")

    # === Compatible fields (Stay backwards compatible) ===
    code: Optional[str] = Field(None, description="6 stock code(Deprecated,Use symbol)")

    # === Quote field ===
    close: Optional[float] = Field(None, description="closing price")
    pct_chg: Optional[float] = Field(None, description="Increase or decrease%")
    amount: Optional[float] = Field(None, description="Turnover")
    open: Optional[float] = Field(None, description="opening price")
    high: Optional[float] = Field(None, description="highest price")
    low: Optional[float] = Field(None, description="lowest price")
    pre_close: Optional[float] = Field(None, description="previous closing price")
    trade_date: Optional[str] = Field(None, description="transaction date")
    updated_at: Optional[datetime] = Field(None, description="Update time")
    
    # Added quotation field
    current_price: Optional[float] = Field(None, description="current price(Same as close)")
    change: Optional[float] = Field(None, description="Changes")
    volume: Optional[float] = Field(None, description="Volume")
    turnover_rate: Optional[float] = Field(None, description="turnover rate")
    volume_ratio: Optional[float] = Field(None, description="Quantity ratio")
    
    # Five levels of market conditions
    bid_prices: Optional[List[float]] = Field(None, description="Buy price 1-5")
    bid_volumes: Optional[List[float]] = Field(None, description="Buy 1-5 quantities")
    ask_prices: Optional[List[float]] = Field(None, description="Sell 1-5 price")
    ask_volumes: Optional[List[float]] = Field(None, description="Sell 1-5 quantities")
    
    # Timestamp
    timestamp: Optional[datetime] = Field(None, description="Quote timestamp")
    
    # Data source and version
    data_source: Optional[str] = Field(None, description="Data source")
    data_version: Optional[int] = Field(None, description="Data version")
    
    class Config:
        extra = "allow"
        json_schema_extra = {
            "example": {
                # Standardized fields
                "symbol": "000001",
                "full_symbol": "000001.SZ",
                "market": "CN",

                # Quote field
                "close": 12.65,
                "pct_chg": 1.61,
                "amount": 1580000000,
                "open": 12.50,
                "high": 12.80,
                "low": 12.30,
                "trade_date": "2024-01-15",

                # extension fields
                "current_price": 12.65,
                "change": 0.20,
                "volume": 125000000
            }
        }


# Response model related to database operations
class StockBasicInfoResponse(BaseModel):
    """Stock basic information API response model"""
    success: bool = True
    data: Optional[StockBasicInfoExtended] = None
    message: str = ""


class MarketQuotesResponse(BaseModel):
    """Real-time market API response model"""
    success: bool = True
    data: Optional[MarketQuotesExtended] = None
    message: str = ""


class StockListResponse(BaseModel):
    """Stock List API response model"""
    success: bool = True
    data: Optional[List[StockBasicInfoExtended]] = None
    total: int = 0
    page: int = 1
    page_size: int = 20
    message: str = ""
