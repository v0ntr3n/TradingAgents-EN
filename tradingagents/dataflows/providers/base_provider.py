"""
统一股票数据提供器基类
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, date
import logging
import pandas as pd


class BaseStockDataProvider(ABC):
    """
    Stock data provider base class
    Defines a unified interface for all data source providers
    """
    
    def __init__(self, provider_name: str):
        """
        Initialize data provider
        
        Args:
            provider_name: provider name
        """
        self.provider_name = provider_name
        self.connected = False
        self.logger = logging.getLogger(f"{__name__}.{provider_name}")
    
    # ==================== Connection management ====================
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Connect to data source
        
        Returns:
            bool: Is the connection successful?
        """
        pass
    
    async def disconnect(self):
        """断开连接"""
        self.connected = False
        self.logger.info(f"✅ {self.provider_name} 连接已断开")
    
    def is_available(self) -> bool:
        """检查数据源是否可用"""
        return self.connected
    
    # ==================== core data interface ====================
    
    @abstractmethod
    async def get_stock_basic_info(self, symbol: str = None) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """
        Get basic stock information
        
        Args:
            symbol: Stock code, if empty, get all stocks
            
        Returns:
            Single stock information dictionary or stock list
        """
        pass
    
    @abstractmethod
    async def get_stock_quotes(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time quotes
        
        Args:
            symbol: Stock code
            
        Returns:
            Real-time market data dictionary
        """
        pass
    
    @abstractmethod
    async def get_historical_data(
        self, 
        symbol: str, 
        start_date: Union[str, date], 
        end_date: Union[str, date] = None
    ) -> Optional[pd.DataFrame]:
        """
        Get historical data
        
        Args:
            symbol: Stock code
            start_date: start date
            end_date: end date
            
        Returns:
            historical data DataFrame
        """
        pass
    
    # ==================== Extended interface ====================
    
    async def get_stock_list(self, market: str = None) -> Optional[List[Dict[str, Any]]]:
        """
        Get a list of stocks
        
        Args:
            market: market code (CN/HK/US)
            
        Returns:
            stock list
        """
        return await self.get_stock_basic_info()
    
    async def get_financial_data(self, symbol: str, report_type: str = "annual") -> Optional[Dict[str, Any]]:
        """
        Get financial data
        
        Args:
            symbol: Stock code
            report_type: report type (annual/quarterly)
            
        Returns:
            Financial Data Dictionary
        """
        # The default implementation returns None, subclasses can override
        return None
    
    # ==================== Data normalization methods ====================
    
    def standardize_basic_info(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standardized stock basic information
        
        Args:
            raw_data: raw data
            
        Returns:
            standardized data
        """
        # Basic standardization logic
        return {
            "code": raw_data.get("code", raw_data.get("symbol", "")),
            "name": raw_data.get("name", ""),
            "symbol": raw_data.get("symbol", raw_data.get("code", "")),
            "full_symbol": raw_data.get("full_symbol", raw_data.get("ts_code", "")),
            
            # market information
            "market_info": self._determine_market_info(raw_data),
            
            # business information
            "industry": raw_data.get("industry"),
            "area": raw_data.get("area"),
            "list_date": self._format_date_output(raw_data.get("list_date")),
            
            # metadata
            "data_source": self.provider_name.lower(),
            "data_version": 1,
            "updated_at": datetime.utcnow()
        }
    
    def standardize_quotes(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standardized real-time market data
        
        Args:
            raw_data: raw data
            
        Returns:
            standardized data
        """
        symbol = raw_data.get("symbol", raw_data.get("code", ""))
        
        return {
            # Basic fields
            "code": symbol,
            "symbol": symbol,
            "full_symbol": raw_data.get("full_symbol", raw_data.get("ts_code", symbol)),
            "market": self._determine_market(raw_data),
            
            # price data
            "close": self._convert_to_float(raw_data.get("close")),
            "current_price": self._convert_to_float(raw_data.get("current_price", raw_data.get("close"))),
            "open": self._convert_to_float(raw_data.get("open")),
            "high": self._convert_to_float(raw_data.get("high")),
            "low": self._convert_to_float(raw_data.get("low")),
            "pre_close": self._convert_to_float(raw_data.get("pre_close")),
            
            # Change data
            "change": self._convert_to_float(raw_data.get("change")),
            "pct_chg": self._convert_to_float(raw_data.get("pct_chg")),
            
            # Transaction data
            "volume": self._convert_to_float(raw_data.get("volume", raw_data.get("vol"))),
            "amount": self._convert_to_float(raw_data.get("amount")),
            
            # time data
            "trade_date": self._format_date_output(raw_data.get("trade_date")),
            "timestamp": datetime.utcnow(),
            
            # metadata
            "data_source": self.provider_name.lower(),
            "data_version": 1,
            "updated_at": datetime.utcnow()
        }
    
    # ==================== Helper methods ====================
    
    def _determine_market_info(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """确定市场信息"""
        # Default implementation, subclasses can override
        return {
            "market": "CN",
            "exchange": "UNKNOWN",
            "exchange_name": "未知交易所",
            "currency": "CNY",
            "timezone": "Asia/Shanghai"
        }
    
    def _determine_market(self, raw_data: Dict[str, Any]) -> str:
        """确定市场代码"""
        market_info = self._determine_market_info(raw_data)
        return market_info.get("market", "CN")
    
    def _convert_to_float(self, value: Any) -> Optional[float]:
        """转换为浮点数"""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _format_date_output(self, date_value: Any) -> Optional[str]:
        """Format date into output format (YYYY-MM-DD)"""
        if not date_value:
            return None
        
        date_str = str(date_value)
        
        # Processing YYYYMMDD format
        if len(date_str) == 8 and date_str.isdigit():
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        
        # Process other formats
        if isinstance(date_value, (date, datetime)):
            return date_value.strftime('%Y-%m-%d')
        
        return date_str
    
    # ==================== Context manager support ====================
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.disconnect()
    
    def __repr__(self):
        return f"<{self.__class__.__name__}(name='{self.provider_name}', connected={self.connected})>"
