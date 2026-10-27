"""
Stock data service layer - unified data access interface
Provide standardized data access services based on existing MongoDB collections
"""
import logging
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.database import get_mongo_db
from app.models.stock_models import (
    StockBasicInfoExtended, 
    MarketQuotesExtended,
    MarketInfo,
    MarketType,
    ExchangeType,
    CurrencyType
)

logger = logging.getLogger(__name__)


class StockDataService:
    """
    Stock Data Service - Unified Data Access Layer
    Extends on existing collections while maintaining backward compatibility
    """
    
    def __init__(self):
        self.basic_info_collection = "stock_basic_info"
        self.market_quotes_collection = "market_quotes"
    
    async def get_stock_basic_info(
        self,
        symbol: str,
        source: Optional[str] = None
    ) -> Optional[StockBasicInfoExtended]:
        """
        Get basic stock information
        Args:
            symbol: 6 stock code
            source: data source (tushare/akshare/baostock/multi_source), Default priority:tushare > multi_source > akshare > baostock
        Returns:
            StockBasicInfoExtended: Extended stock fundamentals information
        """
        try:
            db = get_mongo_db()
            symbol6 = str(symbol).zfill(6)

            # 🔥 Build query conditions
            query = {"$or": [{"symbol": symbol6}, {"code": symbol6}]}

            if source:
                # Specify data source
                query["source"] = source
                doc = await db[self.basic_info_collection].find_one(query, {"_id": 0})
            else:
                # 🔥 No data source specified, query by priority
                source_priority = ["tushare", "multi_source", "akshare", "baostock"]
                doc = None

                for src in source_priority:
                    query_with_source = query.copy()
                    query_with_source["source"] = src
                    doc = await db[self.basic_info_collection].find_one(query_with_source, {"_id": 0})
                    if doc:
                        logger.debug(f"✅ 使用数据源: {src}")
                        break

                # If all data sources are not available, try querying without source conditions (compatible with old data)
                if not doc:
                    doc = await db[self.basic_info_collection].find_one(
                        {"$or": [{"symbol": symbol6}, {"code": symbol6}]},
                        {"_id": 0}
                    )
                    if doc:
                        logger.warning(f"⚠️ Use old data (no source field): {symbol6}")

            if not doc:
                # stock_basic_info Not found, try etf_basic_info fallback
                etf_doc = await self._get_etf_as_basic_info(db, symbol6)
                if etf_doc:
                    return etf_doc
                return None

            # Data standardization
            standardized_doc = self._standardize_basic_info(doc)

            return StockBasicInfoExtended(**standardized_doc)

        except Exception as e:
            logger.error(f"Failed to obtain basic stock information symbol={symbol}, source={source}: {e}")
            return None

    async def _get_etf_as_basic_info(
        self, db, symbol6: str
    ) -> Optional[StockBasicInfoExtended]:
        """Find ETFs from etf_basic_info collection, convert to StockBasicInfoExtended format and return."""
        try:
            doc = await db["etf_basic_info"].find_one(
                {"code": symbol6}, {"_id": 0}
            )
            if not doc:
                return None

            if doc.get("code", "").startswith(("50", "51", "52")):
                full_symbol = f"{symbol6}.SH"
                exchange = "SSE"
                exchange_name = "上海证券交易所"
            elif doc.get("code", "").startswith(("15", "16")):
                full_symbol = f"{symbol6}.SZ"
                exchange = "SZSE"
                exchange_name = "深圳证券交易所"
            else:
                full_symbol = f"{symbol6}.SH"
                exchange = "SSE"
                exchange_name = "上海证券交易所"

            standardized = {
                "symbol": symbol6,
                "code": symbol6,
                "full_symbol": doc.get("full_symbol") or full_symbol,
                "name": doc.get("name", symbol6),
                "area": None,
                "industry": doc.get("fund_type") or "ETF",
                "market": exchange_name,
                "sse": "ETF",
                "source": "etf_basic_info",
                "market_info": {
                    "market": "CN",
                    "exchange": exchange,
                    "exchange_name": exchange_name,
                    "currency": "CNY",
                    "timezone": "Asia/Shanghai",
                    "trading_hours": {
                        "open": "09:30",
                        "close": "15:00",
                        "lunch_break": ["11:30", "13:00"],
                    },
                },
            }
            logger.info(f"📊 [ETF rollback] Found from etf_basic_info: {symbol6} -> {standardized['name']}")
            return StockBasicInfoExtended(**standardized)
        except Exception as e:
            logger.debug(f"etf_basic_info Query failed: {e}")
            return None
    
    async def get_market_quotes(self, symbol: str) -> Optional[MarketQuotesExtended]:
        """
        Get real-time market data
        Args:
            symbol: 6 stock code
        Returns:
            MarketQuotesExtended: Expanded real-time market data
        """
        try:
            db = get_mongo_db()
            symbol6 = str(symbol).zfill(6)

            # Query from existing collection (Priority is given to using the symbol field and is compatible with the code field.)
            doc = await db[self.market_quotes_collection].find_one(
                {"$or": [{"symbol": symbol6}, {"code": symbol6}]},
                {"_id": 0}
            )

            if not doc:
                return None

            # Data standardization
            standardized_doc = self._standardize_market_quotes(doc)

            return MarketQuotesExtended(**standardized_doc)

        except Exception as e:
            logger.error(f"Failed to obtain real-time quotes symbol={symbol}: {e}")
            return None
    
    async def get_stock_list(
        self,
        market: Optional[str] = None,
        industry: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        source: Optional[str] = None
    ) -> List[StockBasicInfoExtended]:
        """
        Get a list of stocks
        Args:
            market: Market screening
            industry: Industry screening
            page: Page number
            page_size: page size
            source: Data source (optional), the data source with the highest priority is used by default
        Returns:
            List[StockBasicInfoExtended]: stock list
        """
        try:
            db = get_mongo_db()

            # 🔥 Use unified data source priority management functions
            if not source:
                from app.core.data_source_priority import get_preferred_data_source_async
                source = await get_preferred_data_source_async(market_category="a_shares")

            # Build query conditions
            query = {"source": source}  # 🔥 Add data source filter
            if market:
                query["market"] = market
            if industry:
                query["industry"] = industry

            # Page query
            skip = (page - 1) * page_size
            cursor = db[self.basic_info_collection].find(
                query,
                {"_id": 0}
            ).skip(skip).limit(page_size)

            docs = await cursor.to_list(length=page_size)

            # Data standardization
            result = []
            for doc in docs:
                standardized_doc = self._standardize_basic_info(doc)
                result.append(StockBasicInfoExtended(**standardized_doc))

            return result
            
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            return []
    
    async def update_stock_basic_info(
        self,
        symbol: str,
        update_data: Dict[str, Any],
        source: str = "tushare"
    ) -> bool:
        """
        Update basic stock information
        Args:
            symbol: 6 stock code
            update_data: Update data
            source: data source (tushare/akshare/baostock), Default tushare
        Returns:
            bool: Is the update successful?
        """
        try:
            db = get_mongo_db()
            symbol6 = str(symbol).zfill(6)

            # Add update time
            update_data["updated_at"] = datetime.utcnow()

            # Make sure the symbol field exists
            if "symbol" not in update_data:
                update_data["symbol"] = symbol6

            # 🔥 Make sure the code field exists
            if "code" not in update_data:
                update_data["code"] = symbol6

            # 🔥 Make sure the source field exists
            if "source" not in update_data:
                update_data["source"] = source

            # 🔥 perform update (Use code + source Union query)
            result = await db[self.basic_info_collection].update_one(
                {"code": symbol6, "source": source},
                {"$set": update_data},
                upsert=True
            )

            return result.modified_count > 0 or result.upserted_id is not None

        except Exception as e:
            logger.error(f"Failed to update basic stock information symbol={symbol}, source={source}: {e}")
            return False
    
    async def update_market_quotes(
        self,
        symbol: str,
        quote_data: Dict[str, Any]
    ) -> bool:
        """
        Update real-time market data
        Args:
            symbol: 6 stock code
            quote_data: Market data
        Returns:
            bool: Is the update successful?
        """
        try:
            db = get_mongo_db()
            symbol6 = str(symbol).zfill(6)

            # Add update time
            quote_data["updated_at"] = datetime.utcnow()

            # 🔥 Make sure both symbol and code fields exist (compatible with old indexes)
            if "symbol" not in quote_data:
                quote_data["symbol"] = symbol6
            if "code" not in quote_data:
                quote_data["code"] = symbol6  # code Use the same value as symbol

            # perform update (Use symbol field as query condition)
            result = await db[self.market_quotes_collection].update_one(
                {"symbol": symbol6},
                {"$set": quote_data},
                upsert=True
            )

            return result.modified_count > 0 or result.upserted_id is not None

        except Exception as e:
            logger.error(f"Failed to update real-time quotes symbol={symbol}: {e}")
            return False
    
    def _standardize_basic_info(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standardized basic stock information data
        Map existing fields to standardized fields
        """
        # Leave existing fields unchanged
        result = doc.copy()

        # Get stock code (Use symbol first, compatible code)
        symbol = doc.get("symbol") or doc.get("code", "")
        result["symbol"] = symbol

        # Compatible with old fields
        if "code" in doc and "symbol" not in doc:
            result["code"] = doc["code"]
        
        # Generate complete code (Prioritize existing ones full_symbol)
        if "full_symbol" not in result or not result["full_symbol"]:
            if symbol and len(symbol) == 6:
                # Determine the exchange based on the code
                if symbol.startswith(('60', '68', '90')):
                    result["full_symbol"] = f"{symbol}.SS"
                    exchange = "SSE"
                    exchange_name = "上海证券交易所"
                elif symbol.startswith(('00', '30', '20')):
                    result["full_symbol"] = f"{symbol}.SZ"
                    exchange = "SZSE"
                    exchange_name = "深圳证券交易所"
                elif symbol.startswith(('8', '4', '92')):
                    result["full_symbol"] = f"{symbol}.BJ"
                    exchange = "BSE"
                    exchange_name = "北京证券交易所"
                else:
                    result["full_symbol"] = f"{symbol}.SZ"  # Default Shenzhen Stock Exchange
                    exchange = "SZSE"
                    exchange_name = "深圳证券交易所"
            else:
                exchange = "SZSE"
                exchange_name = "深圳证券交易所"
        else:
            # Parse exchange from full_symbol
            full_symbol = result["full_symbol"]
            if ".SS" in full_symbol or ".SH" in full_symbol:
                exchange = "SSE"
                exchange_name = "上海证券交易所"
            else:
                exchange = "SZSE"
                exchange_name = "深圳证券交易所"
            
            # Add market information
            result["market_info"] = {
                "market": "CN",
                "exchange": exchange,
                "exchange_name": exchange_name,
                "currency": "CNY",
                "timezone": "Asia/Shanghai",
                "trading_hours": {
                    "open": "09:30",
                    "close": "15:00",
                    "lunch_break": ["11:30", "13:00"]
                }
            }
        
        # Field mapping and normalization
        result["board"] = doc.get("sse")  # Sector standardization
        result["sector"] = doc.get("sec")  # Standardization of the sector
        result["status"] = "L"  # Default listing status
        result["data_version"] = 1

        # Handle date field format conversion
        list_date = doc.get("list_date")
        if list_date and isinstance(list_date, int):
            # Convert integer date to string format (YYYYMMDD -> YYYY-MM-DD)
            date_str = str(list_date)
            if len(date_str) == 8:
                result["list_date"] = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            else:
                result["list_date"] = str(list_date)
        elif list_date:
            result["list_date"] = str(list_date)

        # Handle is_hs field type conversion
        # Tushare The returned is_hs is a string: 'S'-Shenzhen Stock Connect, 'H'-Shanghai Stock Connect, 'N'-No, Null value - unknown
        is_hs = doc.get("is_hs")
        if is_hs is not None:
            if isinstance(is_hs, bool):
                result["is_hs"] = is_hs
            elif isinstance(is_hs, str):
                # 'S' or 'H' It means that it is the Shanghai-Shenzhen-Hong Kong Stock Connect.'N' or an empty string means it is not
                result["is_hs"] = is_hs.upper() in ('S', 'H')
            else:
                result["is_hs"] = bool(is_hs)

        return result
    
    def _standardize_market_quotes(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standardized real-time market data
        Map existing fields to standardized fields
        """
        # Leave existing fields unchanged
        result = doc.copy()
        
        # Get stock code (Use symbol first, compatible code)
        symbol = doc.get("symbol") or doc.get("code", "")
        result["symbol"] = symbol

        # Compatible with old fields
        if "code" in doc and "symbol" not in doc:
            result["code"] = doc["code"]

        # Generate full code and market identification (Prioritize existing ones full_symbol)
        if "full_symbol" not in result or not result["full_symbol"]:
            if symbol and len(symbol) == 6:
                if symbol.startswith(('60', '68', '90')):
                    result["full_symbol"] = f"{symbol}.SS"
                elif symbol.startswith(('8', '4', '92')):
                    result["full_symbol"] = f"{symbol}.BJ"
                else:
                    result["full_symbol"] = f"{symbol}.SZ"

        if "market" not in result:
            result["market"] = "CN"
        
        # Field mapping
        result["current_price"] = doc.get("close")  # current price
        if doc.get("close") and doc.get("pre_close"):
            try:
                result["change"] = float(doc["close"]) - float(doc["pre_close"])
            except (ValueError, TypeError):
                result["change"] = None
        
        result["data_source"] = "market_quotes"
        result["data_version"] = 1
        
        return result


# Global service instance
_stock_data_service = None

def get_stock_data_service() -> StockDataService:
    """获取股票数据服务实例"""
    global _stock_data_service
    if _stock_data_service is None:
        _stock_data_service = StockDataService()
    return _stock_data_service
