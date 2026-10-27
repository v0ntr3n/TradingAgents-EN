#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stock data model definition
Define standardized stock data structures for MongoDB storage and data exchange
"""

from typing import Dict, List, Optional, Any, Union
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field, validator
from enum import Enum

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')


class MarketType(str, Enum):
    """Market type enum"""
    CN = "CN"  # China A shares
    HK = "HK"  # Hong Kong stocks
    US = "US"  # US stocks


class StockStatus(str, Enum):
    """Stock Status Enum"""
    LISTED = "L"      # Listed
    DELISTED = "D"    # delisting
    SUSPENDED = "P"   # Suspended from listing


class ReportType(str, Enum):
    """report type enum"""
    ANNUAL = "annual"      # annual report
    QUARTERLY = "quarterly" # quarterly report


class NewsCategory(str, Enum):
    """News category enum"""
    COMPANY_ANNOUNCEMENT = "company_announcement"  # company announcement
    INDUSTRY_NEWS = "industry_news"               # Industry news
    MARKET_NEWS = "market_news"                   # market news
    RESEARCH_REPORT = "research_report"           # research report


class SentimentType(str, Enum):
    """Emotion type enum"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class BaseStockModel(BaseModel):
    """Stock data basic model"""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    data_source: str = Field(..., description="Data source")
    version: int = Field(default=1, description="Data version")

    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            Decimal: lambda v: float(v)
        }


class StockBasicInfo(BaseStockModel):
    """Stock basic information model"""
    symbol: str = Field(..., description="Standardized stock code", regex=r"^\d{6}$")
    exchange_symbol: str = Field(..., description="Exchange complete code")
    name: str = Field(..., description="Stock name")
    name_en: Optional[str] = Field(None, description="English name")
    market: str = Field(..., description="exchange")
    board: str = Field(..., description="plate")
    industry: str = Field(..., description="Industry")
    industry_code: Optional[str] = Field(None, description="Industry code")
    sector: str = Field(..., description="Sector")
    list_date: date = Field(..., description="Listing date")
    delist_date: Optional[date] = Field(None, description="Delisting date")
    area: str = Field(..., description="area")
    market_cap: Optional[float] = Field(None, description="Total market capitalization")
    float_cap: Optional[float] = Field(None, description="Circulation market value")
    total_shares: Optional[float] = Field(None, description="total share capital")
    float_shares: Optional[float] = Field(None, description="circulating capital")
    currency: str = Field(default="CNY", description="trading currency")
    status: StockStatus = Field(default=StockStatus.LISTED, description="Listing status")
    is_hs: bool = Field(default=False, description="Is it subject to Shanghai-Shenzhen-Hong Kong Stock Connect?")

    @validator('symbol')
    def validate_symbol(cls, v):
        if not v.isdigit() or len(v) != 6:
            raise ValueError('Stock code must be 6 digits')
        return v


class StockDailyQuote(BaseStockModel):
    """Stock daily market model"""
    symbol: str = Field(..., description="Stock code")
    trade_date: date = Field(..., description="transaction date")
    open: float = Field(..., description="opening price")
    high: float = Field(..., description="highest price")
    low: float = Field(..., description="lowest price")
    close: float = Field(..., description="closing price")
    pre_close: float = Field(..., description="previous closing price")
    change: float = Field(..., description="Changes")
    pct_chg: float = Field(..., description="Increase or decrease(%)")
    volume: float = Field(..., description="Volume(shares)")
    amount: float = Field(..., description="Turnover(Yuan)")
    turnover_rate: Optional[float] = Field(None, description="turnover rate(%)")
    volume_ratio: Optional[float] = Field(None, description="Quantity ratio")
    pe: Optional[float] = Field(None, description="P/E ratio")
    pb: Optional[float] = Field(None, description="price to book ratio")
    ps: Optional[float] = Field(None, description="price to sales ratio")
    dv_ratio: Optional[float] = Field(None, description="dividend yield")
    dv_ttm: Optional[float] = Field(None, description="rolling dividend rate")
    total_mv: Optional[float] = Field(None, description="Total market capitalization")
    circ_mv: Optional[float] = Field(None, description="Circulation market value")
    adj_factor: float = Field(default=1.0, description="Reweighting factor")


class StockRealtimeQuote(BaseStockModel):
    """Stock real-time market model"""
    symbol: str = Field(..., description="Stock code")
    name: str = Field(..., description="Stock name")
    current_price: float = Field(..., description="current price")
    pre_close: float = Field(..., description="previous closing price")
    open: float = Field(..., description="Open today")
    high: float = Field(..., description="Jin Gao")
    low: float = Field(..., description="Low today")
    change: float = Field(..., description="Changes")
    pct_chg: float = Field(..., description="Increase or decrease")
    volume: float = Field(..., description="Volume")
    amount: float = Field(..., description="Turnover")
    turnover_rate: Optional[float] = Field(None, description="turnover rate")
    bid_prices: List[float] = Field(default_factory=list, description="Buy price 1-5")
    bid_volumes: List[float] = Field(default_factory=list, description="Buy 1-5 quantities")
    ask_prices: List[float] = Field(default_factory=list, description="Sell 1-5 price")
    ask_volumes: List[float] = Field(default_factory=list, description="Sell 1-5 quantities")
    timestamp: datetime = Field(..., description="Quote time")


class BalanceSheetData(BaseModel):
    """Balance sheet data"""
    total_assets: Optional[float] = Field(None, description="Total assets")
    total_liab: Optional[float] = Field(None, description="Total liabilities")
    total_hldr_eqy_exc_min_int: Optional[float] = Field(None, description="Total shareholders equity")
    total_cur_assets: Optional[float] = Field(None, description="Total current assets")
    total_nca: Optional[float] = Field(None, description="Total non-current assets")
    total_cur_liab: Optional[float] = Field(None, description="Total current liabilities")
    total_ncl: Optional[float] = Field(None, description="Total non-current liabilities")
    cash_and_equivalents: Optional[float] = Field(None, description="Monetary funds")
    goodwill: Optional[float] = Field(None, description="Goodwill (premium assets formed by mergers and acquisitions, fully disclosed in the Q4 annual report, the quarterly report may be empty)")


class IncomeStatementData(BaseModel):
    """Income statement data"""
    total_revenue: Optional[float] = Field(None, description="total operating income")
    revenue: Optional[float] = Field(None, description="operating income")
    oper_cost: Optional[float] = Field(None, description="total operating cost")
    gross_profit: Optional[float] = Field(None, description="gross profit")
    oper_profit: Optional[float] = Field(None, description="operating profit")
    total_profit: Optional[float] = Field(None, description="total profit")
    n_income: Optional[float] = Field(None, description="net profit")
    n_income_attr_p: Optional[float] = Field(None, description="Net profit attributable to parent company")
    basic_eps: Optional[float] = Field(None, description="basic earnings per share")
    diluted_eps: Optional[float] = Field(None, description="diluted earnings per share")


class CashflowStatementData(BaseModel):
    """Cash flow statement data"""
    n_cashflow_act: Optional[float] = Field(None, description="Net cash flow from operating activities")
    n_cashflow_inv_act: Optional[float] = Field(None, description="Net cash flow from investing activities")
    n_cashflow_fin_act: Optional[float] = Field(None, description="Net cash flow from financing activities")
    c_cash_equ_end_period: Optional[float] = Field(None, description="Closing cash and cash equivalents balance")
    c_cash_equ_beg_period: Optional[float] = Field(None, description="Opening cash and cash equivalents balance")


class FinancialIndicators(BaseModel):
    """financial indicator data"""
    roe: Optional[float] = Field(None, description="ROE")
    roa: Optional[float] = Field(None, description="return on total assets")
    gross_margin: Optional[float] = Field(None, description="Gross profit margin")
    net_margin: Optional[float] = Field(None, description="net profit margin")
    debt_to_assets: Optional[float] = Field(None, description="Asset-liability ratio")
    current_ratio: Optional[float] = Field(None, description="current ratio")
    quick_ratio: Optional[float] = Field(None, description="quick ratio")
    eps: Optional[float] = Field(None, description="earnings per share")
    bvps: Optional[float] = Field(None, description="Net assets per share")
    pe: Optional[float] = Field(None, description="P/E ratio")
    pb: Optional[float] = Field(None, description="price to book ratio")
    dividend_yield: Optional[float] = Field(None, description="dividend yield")


class StockFinancialData(BaseStockModel):
    """Stock financial data model"""
    symbol: str = Field(..., description="Stock code")
    report_period: str = Field(..., description="reporting period", regex=r"^\d{8}$")
    report_type: ReportType = Field(..., description="report type")
    ann_date: date = Field(..., description="Announcement date")
    f_ann_date: Optional[date] = Field(None, description="actual announcement date")
    balance_sheet: Optional[BalanceSheetData] = Field(None, description="Balance sheet data")
    income_statement: Optional[IncomeStatementData] = Field(None, description="Income statement data")
    cashflow_statement: Optional[CashflowStatementData] = Field(None, description="Cash flow statement data")
    financial_indicators: Optional[FinancialIndicators] = Field(None, description="financial indicators")


class StockNews(BaseStockModel):
    """stock news model"""
    symbol: Optional[str] = Field(None, description="Related stock codes")
    symbols: List[str] = Field(default_factory=list, description="Related stock list")
    title: str = Field(..., description="News headline")
    content: Optional[str] = Field(None, description="News content")
    summary: Optional[str] = Field(None, description="news summary")
    url: str = Field(..., description="News link")
    source: str = Field(..., description="news source")
    author: Optional[str] = Field(None, description="Author")
    publish_time: datetime = Field(..., description="Release time")
    category: NewsCategory = Field(..., description="News category")
    sentiment: Optional[SentimentType] = Field(None, description="sentiment analysis")
    sentiment_score: Optional[float] = Field(None, description="sentiment score", ge=-1, le=1)
    keywords: List[str] = Field(default_factory=list, description="keywords")
    importance: str = Field(default="medium", description="importance")
    language: str = Field(default="zh-CN", description="language")


class MovingAverages(BaseModel):
    """moving average data"""
    ma5: Optional[float] = Field(None, description="5 daily moving average")
    ma10: Optional[float] = Field(None, description="10 daily moving average")
    ma20: Optional[float] = Field(None, description="20 daily moving average")
    ma60: Optional[float] = Field(None, description="60 daily moving average")


class TechnicalIndicatorsData(BaseModel):
    """Technical indicator data"""
    rsi: Optional[float] = Field(None, description="RSI relative strength indicator")
    macd: Optional[float] = Field(None, description="MACD")
    macd_signal: Optional[float] = Field(None, description="MACD signal line")
    macd_hist: Optional[float] = Field(None, description="MACD bar chart")
    kdj_k: Optional[float] = Field(None, description="KDJ-K value")
    kdj_d: Optional[float] = Field(None, description="KDJ-D value")
    kdj_j: Optional[float] = Field(None, description="KDJ-J value")
    boll_upper: Optional[float] = Field(None, description="Bollinger Bands track")
    boll_mid: Optional[float] = Field(None, description="Bollinger Bands Middle Track")
    boll_lower: Optional[float] = Field(None, description="Bollinger Bands Lower Track")
    cci: Optional[float] = Field(None, description="CCI trend indicator")
    williams_r: Optional[float] = Field(None, description="William indicator")
    bias: Optional[float] = Field(None, description="deviation rate")
    roc: Optional[float] = Field(None, description="rate of change indicator")
    emt: Optional[float] = Field(None, description="Simple volatility indicator")


class StockTechnicalIndicators(BaseStockModel):
    """Stock Technical Indicator Model"""
    symbol: str = Field(..., description="Stock code")
    trade_date: date = Field(..., description="transaction date")
    period: str = Field(default="daily", description="cycle")
    ma: Optional[MovingAverages] = Field(None, description="moving average")
    indicators: Optional[TechnicalIndicatorsData] = Field(None, description="Technical indicators")


class DataSourceConfig(BaseStockModel):
    """Data source configuration model"""
    source_name: str = Field(..., description="Data source name")
    source_type: str = Field(..., description="Data source type")
    priority: int = Field(..., description="priority")
    status: str = Field(default="active", description="Status")
    config: Dict[str, Any] = Field(default_factory=dict, description="Configuration information")
    supported_data_types: List[str] = Field(default_factory=list, description="Supported data types")
    supported_markets: List[MarketType] = Field(default_factory=list, description="supported markets")
    last_sync_time: Optional[datetime] = Field(None, description="Last sync time")


class DataSyncLog(BaseStockModel):
    """Data synchronization log model"""
    task_id: str = Field(..., description="Task ID")
    data_type: str = Field(..., description="data type")
    data_source: str = Field(..., description="data source")
    symbols: List[str] = Field(default_factory=list, description="Synchronized stock list")
    sync_date: date = Field(..., description="Sync date")
    start_time: datetime = Field(..., description="start time")
    end_time: Optional[datetime] = Field(None, description="end time")
    status: str = Field(default="pending", description="Status")
    total_records: int = Field(default=0, description="Total number of records")
    success_records: int = Field(default=0, description="Number of successful records")
    failed_records: int = Field(default=0, description="Number of failed records")
    error_message: Optional[str] = Field(None, description="error message")
    performance: Dict[str, Any] = Field(default_factory=dict, description="Performance indicators")


# Export all models
__all__ = [
    'MarketType', 'StockStatus', 'ReportType', 'NewsCategory', 'SentimentType',
    'BaseStockModel', 'StockBasicInfo', 'StockDailyQuote', 'StockRealtimeQuote',
    'StockFinancialData', 'StockNews', 'StockTechnicalIndicators',
    'DataSourceConfig', 'DataSyncLog',
    'BalanceSheetData', 'IncomeStatementData', 'CashflowStatementData',
    'FinancialIndicators', 'MovingAverages', 'TechnicalIndicatorsData'
]
