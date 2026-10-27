"""
Sample SDK Adapter Implementation (tradingagents layer)
Shows how to create a new data source adapter based on BaseStockDataProvider

Architecture description:
- tradingagents layer: Pure data acquisition and standardization, no database operations involved
- app layer: Data synchronization service, responsible for calling this adapter and writing to the database
- Segregation of duties: The adapter is only responsible for data acquisition, and the synchronization service is responsible for data storage.
"""
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, date
import pandas as pd

import os
from ..base_provider import BaseStockDataProvider


class ExampleSDKProvider(BaseStockDataProvider):
    """
    Sample SDK Data Provider (tradingagents layer)

    Responsibilities:
    - Connect external SDK API
    - Get raw data
    - Data standardization
    - Returns data in standard format

    Note:
    - No database operations involved
    - Does not contain business logic
    - Focus on data acquisition and format conversion
    - Called by the synchronization service of the app layer
    """
    
    def __init__(self, api_key: str = None, base_url: str = None, **kwargs):
        super().__init__("ExampleSDK")
        
        # Configuration parameters
        self.api_key = api_key or os.getenv("EXAMPLE_SDK_API_KEY")
        self.base_url = base_url or os.getenv("EXAMPLE_SDK_BASE_URL", "https://api.example-sdk.com")
        self.timeout = int(os.getenv("EXAMPLE_SDK_TIMEOUT", "30"))
        self.enabled = os.getenv("EXAMPLE_SDK_ENABLED", "false").lower() == "true"
        
        # HTTP session
        self.session = None
        
        # Request header
        self.headers = {
            "User-Agent": "TradingAgents/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"
    
    async def connect(self) -> bool:
        """连接到数据源"""
        if not self.enabled:
            self.logger.warning("ExampleSDK Not enabled")
            return False
        
        if not self.api_key:
            self.logger.error("ExampleSDK API Key not configured")
            return False
        
        try:
            # Create HTTP session
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout
            )
            
            # test connection
            test_url = f"{self.base_url}/ping"
            async with self.session.get(test_url) as response:
                if response.status == 200:
                    self.connected = True
                    self.logger.info("ExampleSDK Connection successful")
                    return True
                else:
                    self.logger.error(f"ExampleSDK Connection failed: HTTP {response.status}")
                    return False
                    
        except Exception as e:
            self._handle_error(e, "ExampleSDK Connection failed")
            return False
    
    async def disconnect(self):
        """断开连接"""
        if self.session:
            await self.session.close()
            self.session = None
        
        self.connected = False
        self.logger.info("ExampleSDK The connection has been lost")
    
    async def get_stock_basic_info(self, symbol: str = None) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """获取股票基础信息"""
        if not self.connected:
            await self.connect()
        
        try:
            if symbol:
                # Get individual stock information
                url = f"{self.base_url}/stocks/{symbol}/info"
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return self.standardize_basic_info(data)
                    else:
                        self.logger.warning(f"获取{symbol}基础信息失败: HTTP {response.status}")
                        return None
            else:
                # Get all stock information
                url = f"{self.base_url}/stocks/list"
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return [self.standardize_basic_info(item) for item in data.get("stocks", [])]
                    else:
                        self.logger.warning(f"Failed to get stock list: HTTP {response.status}")
                        return None
                        
        except Exception as e:
            self._handle_error(e, f"Failed to obtain basic stock information symbol={symbol}")
            return None
    
    async def get_stock_list(self, market: str = None) -> Optional[List[Dict[str, Any]]]:
        """获取股票列表"""
        if not self.connected:
            await self.connect()
        
        try:
            url = f"{self.base_url}/stocks/list"
            params = {}
            if market:
                params["market"] = market
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return [self.standardize_basic_info(item) for item in data.get("stocks", [])]
                else:
                    self.logger.warning(f"Failed to get stock list: HTTP {response.status}")
                    return None
                    
        except Exception as e:
            self._handle_error(e, f"Failed to get stock list market={market}")
            return None
    
    async def get_stock_quotes(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取实时行情"""
        if not self.connected:
            await self.connect()
        
        try:
            url = f"{self.base_url}/stocks/{symbol}/quote"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self.standardize_quotes(data)
                else:
                    self.logger.warning(f"获取{symbol}实时行情失败: HTTP {response.status}")
                    return None
                    
        except Exception as e:
            self._handle_error(e, f"Failed to obtain real-time quotes symbol={symbol}")
            return None
    
    async def get_historical_data(
        self, 
        symbol: str, 
        start_date: Union[str, date], 
        end_date: Union[str, date] = None,
        period: str = "daily"
    ) -> Optional[pd.DataFrame]:
        """获取历史数据"""
        if not self.connected:
            await self.connect()
        
        try:
            url = f"{self.base_url}/stocks/{symbol}/history"
            params = {
                "start_date": str(start_date),
                "period": period
            }
            
            if end_date:
                params["end_date"] = str(end_date)
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._convert_to_dataframe(data.get("history", []))
                else:
                    self.logger.warning(f"获取{symbol}历史数据失败: HTTP {response.status}")
                    return None
                    
        except Exception as e:
            self._handle_error(e, f"Failed to obtain historical data symbol={symbol}")
            return None
    
    async def get_financial_data(self, symbol: str, report_type: str = "annual") -> Optional[Dict[str, Any]]:
        """获取财务数据"""
        if not self.connected:
            await self.connect()
        
        try:
            url = f"{self.base_url}/stocks/{symbol}/financials"
            params = {"type": report_type}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._standardize_financial_data(data)
                else:
                    self.logger.warning(f"获取{symbol}财务数据失败: HTTP {response.status}")
                    return None
                    
        except Exception as e:
            self._handle_error(e, f"Failed to get financial data symbol={symbol}")
            return None
    
    async def get_stock_news(self, symbol: str = None, limit: int = 10) -> Optional[List[Dict[str, Any]]]:
        """获取股票新闻"""
        if not self.connected:
            await self.connect()
        
        try:
            if symbol:
                url = f"{self.base_url}/stocks/{symbol}/news"
            else:
                url = f"{self.base_url}/news/market"
            
            params = {"limit": limit}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return [self._standardize_news(item) for item in data.get("news", [])]
                else:
                    self.logger.warning(f"获取新闻失败: HTTP {response.status}")
                    return None
                    
        except Exception as e:
            self._handle_error(e, f"Failed to get news symbol={symbol}")
            return None
    
    # ==================== Data conversion method ====================
    
    def standardize_basic_info(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Standardized stock basic information - rewritten to fit the ExampleSDK format"""
        # Field mapping (Adjust according to the field name of the actual SDK)
        mapped_data = {
            "symbol": raw_data.get("ticker", raw_data.get("symbol")),
            "name": raw_data.get("company_name", raw_data.get("name")),
            "industry": raw_data.get("sector", raw_data.get("industry")),
            "area": raw_data.get("region", raw_data.get("area")),
            "market_cap": raw_data.get("market_capitalization"),
            "list_date": raw_data.get("listing_date"),
            "pe": raw_data.get("pe_ratio"),
            "pb": raw_data.get("pb_ratio"),
            "roe": raw_data.get("return_on_equity")
        }
        
        # Call the standardized method of the parent class
        return super().standardize_basic_info(mapped_data)
    
    def standardize_quotes(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Standardized real-time market data - rewritten to adapt to ExampleSDK format"""
        # Field mapping
        mapped_data = {
            "symbol": raw_data.get("ticker", raw_data.get("symbol")),
            "price": raw_data.get("last_price", raw_data.get("current_price")),
            "open": raw_data.get("open_price"),
            "high": raw_data.get("high_price"),
            "low": raw_data.get("low_price"),
            "prev_close": raw_data.get("previous_close"),
            "change_percent": raw_data.get("percent_change"),
            "volume": raw_data.get("trading_volume"),
            "turnover": raw_data.get("trading_value"),
            "date": raw_data.get("trading_date"),
            "timestamp": raw_data.get("last_updated")
        }
        
        # Call the standardized method of the parent class
        return super().standardize_quotes(mapped_data)
    
    def _convert_to_dataframe(self, history_data: List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert historical data to DataFrame"""
        if not history_data:
            return pd.DataFrame()
        
        # Standardize each record
        standardized_data = []
        for item in history_data:
            standardized_item = {
                "date": item.get("date"),
                "open": self._convert_to_float(item.get("open")),
                "high": self._convert_to_float(item.get("high")),
                "low": self._convert_to_float(item.get("low")),
                "close": self._convert_to_float(item.get("close")),
                "volume": self._convert_to_float(item.get("volume")),
                "amount": self._convert_to_float(item.get("amount"))
            }
            standardized_data.append(standardized_item)
        
        df = pd.DataFrame(standardized_data)
        
        # Set date index
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
        
        return df
    
    def _standardize_financial_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化财务数据"""
        return {
            "symbol": raw_data.get("ticker", raw_data.get("symbol")),
            "report_period": raw_data.get("period"),
            "report_type": raw_data.get("type", "annual"),
            "revenue": self._convert_to_float(raw_data.get("total_revenue")),
            "net_income": self._convert_to_float(raw_data.get("net_income")),
            "total_assets": self._convert_to_float(raw_data.get("total_assets")),
            "total_equity": self._convert_to_float(raw_data.get("shareholders_equity")),
            "cash_flow": self._convert_to_float(raw_data.get("operating_cash_flow")),
            "data_source": self.name.lower(),
            "updated_at": datetime.utcnow()
        }
    
    def _standardize_news(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化新闻数据"""
        return {
            "title": raw_data.get("headline", raw_data.get("title")),
            "content": raw_data.get("summary", raw_data.get("content")),
            "url": raw_data.get("url"),
            "source": raw_data.get("source"),
            "publish_time": self._parse_timestamp(raw_data.get("published_at")),
            "sentiment": raw_data.get("sentiment"),
            "symbols": raw_data.get("related_symbols", []),
            "data_source": self.name.lower(),
            "created_at": datetime.utcnow()
        }
    
    # ==================== Clean up resources ====================
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.disconnect()


# ==================== Usage example ====================

async def example_usage():
    """使用示例"""
    # way 1: Use directly
    provider = ExampleSDKProvider(api_key="your_api_key")
    
    try:
        # connect
        if await provider.connect():
            # Get basic stock information
            basic_info = await provider.get_stock_basic_info("000001")
            print(f"基础信息: {basic_info}")
            
            # Get real-time quotes
            quotes = await provider.get_stock_quotes("000001")
            print(f"实时行情: {quotes}")
            
            # Get historical data
            history = await provider.get_historical_data("000001", "2024-01-01", "2024-01-31")
            print(f"历史数据: {history.head() if history is not None else None}")
            
    finally:
        await provider.disconnect()
    
    # way 2: Use context managers
    async with ExampleSDKProvider(api_key="your_api_key") as provider:
        basic_info = await provider.get_stock_basic_info("000001")
        print(f"基础信息: {basic_info}")


if __name__ == "__main__":
    asyncio.run(example_usage())
