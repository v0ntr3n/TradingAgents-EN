from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['basics_sync', 'stock_data_service', 'unified_stock_service', 'foreign_stock_service', 'historical_data_service', 'financial_data_service', 'news_data_service', 'quotes_service', 'quotes_ingestion_service', 'basics_sync_service', 'multi_source_basics_sync_service', 'official_industry_service', 'technical_indicator_materialization_service', 'trade_date_cache_service', 'trading_calendar_service', 'data_consistency_checker', 'data_validation_service', 'basics_sync.utils', 'basics_sync.processing']:
    _sys.modules[f"app.services.{_sub}"] = _self_mod
    setattr(_self_mod, _sub.split(".")[0], _self_mod)

# === basics_sync.py ===
import sys as _sys

# === utils.py ===
"""
Blocking utility functions related to Tushare:
- fetch_stock_basic_df: Get a list of stocks (make sure Tushare is connected)
- find_latest_trade_date: Detect the latest available trading day (YYYYMMDD)
- fetch_daily_basic_mv_map: Get daily basic indicator mapping (market cap/valuation/transaction) based on the trading day
"""
from datetime import datetime, timedelta
from typing import Dict


def fetch_stock_basic_df():
    """
    Get the stock base list (DataFrame format) from Tushare, which requires correct configuration and connection.
    Depends on environment variables:TUSHARE_ENABLED=true And TUSHARE_TOKEN is provided in .env.

    Note: This is a synchronous function and will wait for the Tushare connection to complete.
    """
    import time
    import logging
    from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
    from app.core.config import settings

    logger = logging.getLogger(__name__)

    # 🔧 Remove TUSHARE_ENABLED check to be consistent with financial data and historical data synchronization
    # Only check the Tushare connection status and report an error if the connection fails.
    # Note: If you need multiple data source support, please use MultiSourceBasicsSyncService

    provider = get_tushare_provider()

    # Wait for the connection to complete (up to 5 seconds)
    max_wait_seconds = 5
    wait_interval = 0.1
    elapsed = 0.0

    logger.info("⏳ Waiting for Tushare to connect...")
    while not getattr(provider, "connected", False) and elapsed < max_wait_seconds:
        time.sleep(wait_interval)
        elapsed += wait_interval

    # Check connection status and API availability
    if not getattr(provider, "connected", False) or provider.api is None:
        logger.error(f"❌ Tushare 连接失败（等待 {max_wait_seconds}s 后超时）")
        logger.error("💡 Please check:")
        logger.error("   1. .env A valid TUSHARE_TOKEN")
        logger.error("   2. Tushare Token Not expired and have enough points")
        logger.error("   3. 网络连接正常")
        raise RuntimeError(
            f"Tushare not connected after waiting {max_wait_seconds}s. "
            "Check TUSHARE_TOKEN in .env and ensure it's valid."
        )

    logger.info("✅ Tushare Connected, start getting stock list...")

    # Directly call Tushare API to obtain DataFrame
    try:
        df = provider.api.stock_basic(
            list_status='L',
            fields='ts_code,symbol,name,area,industry,market,exchange,list_date,is_hs'
        )

        # 🔧 Enhanced error diagnosis
        if df is None:
            logger.error("❌ Tushare API Return None")
            logger.error("💡 Possible reasons:")
            logger.error("   1. Tushare Token Invalid or expired")
            logger.error("   2. API 积分不足")
            logger.error("   3. 网络连接问题")
            raise RuntimeError("Tushare API returned None. Check token validity and API credits.")

        if hasattr(df, 'empty') and df.empty:
            logger.error("❌ Tushare API Return empty DataFrame")
            logger.error("💡 Possible reasons:")
            logger.error("   1. list_status='L' Parameter may be incorrect")
            logger.error("   2. Tushare Data source is temporarily unavailable")
            logger.error("   3. API Call limits (please check points and call frequency)")
            raise RuntimeError("Tushare API returned empty DataFrame. Check API parameters and data availability.")

        logger.info(f"✅ 成功获取 {len(df)} 条股票数据")
        return df

    except Exception as e:
        logger.error(f"❌ Failed to call Tushare API: {e}")
        raise RuntimeError(f"Failed to fetch stock basic DataFrame: {e}")


def find_latest_trade_date() -> str:
    """
    Detect the most recent available trading day (YYYYMMDD).
    - Look back up to 5 days from today;
    - If neither is available, it will fall back to yesterday s date.
    """
    from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

    provider = get_tushare_provider()
    api = provider.api
    if api is None:
        raise RuntimeError("Tushare API unavailable")

    today = datetime.now()
    for delta in range(0, 6):
        d = (today - timedelta(days=delta)).strftime("%Y%m%d")
        try:
            db = api.daily_basic(trade_date=d, fields="ts_code,total_mv")
            if db is not None and not db.empty:
                return d
        except Exception:
            continue
    return (today - timedelta(days=1)).strftime("%Y%m%d")


def fetch_daily_basic_mv_map(trade_date: str) -> Dict[str, Dict[str, float]]:
    """
    Get the daily basic indicator mapping based on the trading day.
    Cover fields:total_mv/circ_mv/pe/pb/ps/turnover_rate/volume_ratio/pe_ttm/pb_mrq/ps_ttm/dv_ratio/dv_ttm
    """
    from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

    provider = get_tushare_provider()
    api = provider.api
    if api is None:
        raise RuntimeError("Tushare API unavailable")

    # 🔥 New: Add ps, ps_ttm, total_share, float_share, dv_ratio, dv_ttm fields
    fields = "ts_code,total_mv,circ_mv,pe,pb,ps,turnover_rate,volume_ratio,pe_ttm,pb_mrq,ps_ttm,total_share,float_share,dv_ratio,dv_ttm"
    db = api.daily_basic(trade_date=trade_date, fields=fields)

    data_map: Dict[str, Dict[str, float]] = {}
    if db is not None and not db.empty:
        for _, row in db.iterrows():  # type: ignore
            ts_code = row.get("ts_code")
            if ts_code is not None:
                try:
                    metrics = {}
                    # 🔥 New: Add ps, ps_ttm, total_share, float_share, dv_ratio, dv_ttm to field list
                    for field in [
                        "total_mv",
                        "circ_mv",
                        "pe",
                        "pb",
                        "ps",
                        "turnover_rate",
                        "volume_ratio",
                        "pe_ttm",
                        "pb_mrq",
                        "ps_ttm",
                        "total_share",
                        "float_share",
                        "dv_ratio",
                        "dv_ttm",
                    ]:
                        value = row.get(field)
                        if value is not None and str(value).lower() not in ["nan", "none", ""]:
                            metrics[field] = float(value)
                    if metrics:
                        data_map[str(ts_code)] = metrics
                except Exception:
                    pass
    return data_map




def fetch_latest_roe_map() -> Dict[str, Dict[str, float]]:
    """
    Get the ROE mapping for the most recent available financial period (ts_code -> {"roe": float}) . 
    Prioritize the detection in reverse order of the end_date of the latest quarter to find the first period of non-empty data.
    """
    from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
    from datetime import datetime

    provider = get_tushare_provider()
    api = provider.api
    if api is None:
        raise RuntimeError("Tushare API unavailable")

    # Generate the end dates of the most recent fiscal quarters, format YYYYMMDD
    def quarter_ends(now: datetime):
        y = now.year
        q_dates = [
            f"{y}0331",
            f"{y}0630",
            f"{y}0930",
            f"{y}1231",
        ]
        # Include the previous year to increase the probability of success
        py = y - 1
        q_dates_prev = [
            f"{py}1231",
            f"{py}0930",
            f"{py}0630",
            f"{py}0331",
        ]
        # Just the last 6 issues
        return q_dates_prev + q_dates

    candidates = quarter_ends(datetime.now())
    data_map: Dict[str, Dict[str, float]] = {}

    for end_date in candidates:
        try:
            df = api.fina_indicator(end_date=end_date, fields="ts_code,end_date,roe")
            if df is not None and not df.empty:
                for _, row in df.iterrows():  # type: ignore
                    ts_code = row.get("ts_code")
                    val = row.get("roe")
                    if ts_code is None or val is None:
                        continue
                    try:
                        v = float(val)
                    except Exception:
                        continue
                    data_map[str(ts_code)] = {"roe": v}
                if data_map:
                    break  # Just find the latest issue
        except Exception:
            continue

    return data_map

# === processing.py ===
"""
Shared document indicator processing functions
- add_financial_metrics: Append daily underlying metrics (market cap/valuation/transactions) to document
"""
from typing import Dict


def add_financial_metrics(doc: Dict, daily_metrics: Dict) -> None:
    """
    Write financial and trading indicators to doc (modify in place).
    - Market value: total_mv/circ_mv (converted from 10,000 yuan to 100 million yuan)
    - Valuation: pe/pb/pe_ttm/pb_mrq/ps/ps_ttm (filter NaN/None)
    - Transaction: turnover_rate/volume_ratio (filter NaN/None)
    - Equity: total_share/float_share (10,000 shares, filter NaN/None)
    - Dividends:dv_ratio/dv_ttm -> dividend_yield/dividend_yield_ttm (Filter NaN/None)
    """
    # Market value (10,000 yuan -> billion)
    if "total_mv" in daily_metrics and daily_metrics["total_mv"] is not None:
        doc["total_mv"] = daily_metrics["total_mv"] / 10000
    if "circ_mv" in daily_metrics and daily_metrics["circ_mv"] is not None:
        doc["circ_mv"] = daily_metrics["circ_mv"] / 10000

    # Valuation indicators (🔥 New ps and ps_ttm)
    for field in ["pe", "pb", "pe_ttm", "pb_mrq", "ps", "ps_ttm"]:
        if field in daily_metrics and daily_metrics[field] is not None:
            try:
                value = float(daily_metrics[field])
                if not (value != value):  # filter NaN
                    doc[field] = value
            except (ValueError, TypeError):
                pass

    # trading indicators
    for field in ["turnover_rate", "volume_ratio"]:
        if field in daily_metrics and daily_metrics[field] is not None:
            try:
                value = float(daily_metrics[field])
                if not (value != value):  # filter NaN
                    doc[field] = value
            except (ValueError, TypeError):
                pass

    # 🔥 Equity data (10,000 shares)
    for field in ["total_share", "float_share"]:
        if field in daily_metrics and daily_metrics[field] is not None:
            try:
                value = float(daily_metrics[field])
                if not (value != value):  # filter NaN
                    doc[field] = value
            except (ValueError, TypeError):
                pass

    for source_field, target_field in {"dv_ratio": "dividend_yield", "dv_ttm": "dividend_yield_ttm"}.items():
        if source_field in daily_metrics and daily_metrics[source_field] is not None:
            try:
                value = float(daily_metrics[source_field])
                if not (value != value):  # filter NaN
                    doc[target_field] = value
            except (ValueError, TypeError):
                pass


# === __init__.py ===
"""
Basic data synchronization sub-package: encapsulates blocking calls and processing functions related to synchronization of basic stock information.
- utils.py: Blocking retrieval function with Tushare (stock list, latest trading day, daily basic data)
- processing.py: Shared document building/metric handling functions
"""

# === stock_data_service.py ===
"""
Stock data service layer - unified data access interface
Provide standardized data access services based on existing MongoDB collections
"""
import logging
from datetime import datetime, date
from typing import Optional, Dict, Any, List
try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = AsyncIOMotorDatabase = AsyncIOMotorCollection = object

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

# === unified_stock_service.py ===
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified stock data service (cross-market, supports multiple data sources)

Function:
1. Cross-market data access (A shares/Hong Kong stocks/US stocks)
2. Multiple data source priority query
3. Unified query interface

Design description:
- Reference A-share multi-data source design
- The same stock can have multiple data source records
- Pass (code, source) Union query
- Data source priority is read from database configuration
"""

import logging
from typing import Dict, List, Optional
try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = AsyncIOMotorDatabase = AsyncIOMotorCollection = object

logger = logging.getLogger("webapi")


class UnifiedStockService:
    """Unified stock data service (cross-market, supports multiple data sources)"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        
        # Collection mapping
        self.collection_map = {
            "CN": {
                "basic_info": "stock_basic_info",
                "quotes": "market_quotes",
                "daily": "stock_daily_quotes",
                "financial": "stock_financial_data",
                "news": "stock_news"
            },
            "HK": {
                "basic_info": "stock_basic_info_hk",
                "quotes": "market_quotes_hk",
                "daily": "stock_daily_quotes_hk",
                "financial": "stock_financial_data_hk",
                "news": "stock_news_hk"
            },
            "US": {
                "basic_info": "stock_basic_info_us",
                "quotes": "market_quotes_us",
                "daily": "stock_daily_quotes_us",
                "financial": "stock_financial_data_us",
                "news": "stock_news_us"
            },
            "ETF": {
                "basic_info": "etf_basic_info",
                "quotes": "market_quotes",  # ETF Share real-time quotes with A-shares
                "daily": "etf_daily_quotes",
                "financial": None,  # ETF None PE/PB/ROE
                "news": "stock_news"
            }
        }

    async def get_stock_info(
        self, 
        market: str, 
        code: str, 
        source: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Obtain basic stock information (supports multiple data sources)
        
        Args:
            market: market type (CN/HK/US)
            code: Stock code
            source: Specify data source (optional)
        
        Returns:
            Dictionary of basic stock information
        """
        collection_name = self.collection_map[market]["basic_info"]
        collection = self.db[collection_name]
        
        if source:
            # Specify data source
            query = {"code": code, "source": source}
            doc = await collection.find_one(query, {"_id": 0})
            if doc:
                logger.debug(f"✅ 使用指定数据源: {source}")
        else:
            # 🔥 Query by priority (refer to A-share design)
            source_priority = await self._get_source_priority(market)
            doc = None
            
            for src in source_priority:
                query = {"code": code, "source": src}
                doc = await collection.find_one(query, {"_id": 0})
                if doc:
                    logger.debug(f"✅ 使用数据源: {src} (优先级查询)")
                    break
            
            # If not found, try query without specifying source (compatible with old data)
            if not doc:
                doc = await collection.find_one({"code": code}, {"_id": 0})
                if doc:
                    logger.debug("✅ Use default data source (compatibility mode)")
        
        return doc

    async def _get_source_priority(self, market: str) -> List[str]:
        """
        Get data source priority from database
        
        Args:
            market: market type (CN/HK/US/ETF)
        
        Returns:
            Data source priority list
        """
        if market == "ETF":
            return ["akshare"]

        market_category_map = {
            "CN": "a_shares",
            "HK": "hk_stocks",
            "US": "us_stocks"
        }

        market_category_id = market_category_map.get(market)
        
        try:
            # Query from datasource_groupings collection
            groupings = await self.db.datasource_groupings.find({
                "market_category_id": market_category_id,
                "enabled": True
            }).sort("priority", -1).to_list(length=None)
            
            if groupings:
                priority_list = [g["data_source_name"] for g in groupings]
                logger.debug(f"📊 {market} Data source priority (from database): {priority_list}")
                return priority_list
        except Exception as e:
            logger.warning(f"⚠️ Failed to read data source priority from database: {e}")
        
        # Default priority
        default_priority = {
            "CN": ["tushare", "akshare", "baostock"],
            "HK": ["yfinance_hk", "akshare_hk"],
            "US": ["yfinance_us"]
        }
        priority_list = default_priority.get(market, [])
        logger.debug(f"📊 {market} 数据源优先级（默认）: {priority_list}")
        return priority_list

    async def get_stock_quote(self, market: str, code: str) -> Optional[Dict]:
        """
        Get real-time quotes
        
        Args:
            market: market type (CN/HK/US)
            code: Stock code
        
        Returns:
            Real-time Quote Dictionary
        """
        collection_name = self.collection_map[market]["quotes"]
        collection = self.db[collection_name]
        return await collection.find_one({"code": code}, {"_id": 0})

    async def search_stocks(
        self, 
        market: str, 
        query: str, 
        limit: int = 20
    ) -> List[Dict]:
        """
        Search for stocks (remove duplication, only return the optimal data source for each stock)
        
        Args:
            market: market type (CN/HK/US)
            query: Search keywords
            limit: Return quantity limit
        
        Returns:
            stock list
        """
        collection_name = self.collection_map[market]["basic_info"]
        collection = self.db[collection_name]

        # Supports code and name search
        filter_query = {
            "$or": [
                {"code": {"$regex": query, "$options": "i"}},
                {"name": {"$regex": query, "$options": "i"}},
                {"name_en": {"$regex": query, "$options": "i"}}
            ]
        }

        # Query all matching records
        cursor = collection.find(filter_query)
        all_results = await cursor.to_list(length=None)
        
        if not all_results:
            return []
        
        # Grouped by code, each code only retains the highest priority data source
        source_priority = await self._get_source_priority(market)
        unique_results = {}
        
        for doc in all_results:
            code = doc.get("code")
            source = doc.get("source")
            
            if code not in unique_results:
                unique_results[code] = doc
            else:
                # Compare priorities
                current_source = unique_results[code].get("source")
                try:
                    if source in source_priority and current_source in source_priority:
                        if source_priority.index(source) < source_priority.index(current_source):
                            unique_results[code] = doc
                except ValueError:
                    # If the source is not in the priority list, keep the current record
                    pass
        
        # Return to the previous limit bar
        result_list = list(unique_results.values())[:limit]
        logger.info(f"🔍 搜索 {market} 市场: '{query}' -> {len(result_list)} 条结果（已去重）")
        return result_list

    async def get_daily_quotes(
        self,
        market: str,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get historical K-line data
        
        Args:
            market: market type (CN/HK/US)
            code: Stock code
            start_date: start date (YYYY-MM-DD)
            end_date: end date (YYYY-MM-DD)
            limit: Return quantity limit
        
        Returns:
            K Line data list
        """
        collection_name = self.collection_map[market]["daily"]
        collection = self.db[collection_name]
        
        query = {"code": code}
        if start_date or end_date:
            query["trade_date"] = {}
            if start_date:
                query["trade_date"]["$gte"] = start_date
            if end_date:
                query["trade_date"]["$lte"] = end_date
        
        cursor = collection.find(query, {"_id": 0}).sort("trade_date", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_supported_markets(self) -> List[Dict]:
        """
        Get a list of supported markets
        
        Returns:
            Market list
        """
        return [
            {
                "code": "CN",
                "name": "A股",
                "name_en": "China A-Share",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            },
            {
                "code": "HK",
                "name": "港股",
                "name_en": "Hong Kong Stock",
                "currency": "HKD",
                "timezone": "Asia/Hong_Kong"
            },
            {
                "code": "US",
                "name": "美股",
                "name_en": "US Stock",
                "currency": "USD",
                "timezone": "America/New_York"
            }
        ]


# === foreign_stock_service.py ===
"""
Hong Kong and US stock data services
🔥 Reuse unified data source manager (UnifiedStockService)
🔥 Called according to the data source priority configured in the database API
🔥 Request deduplication mechanism: prevent repeated calls for concurrent requests API
"""
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime, timedelta
import logging
import json
import re
import asyncio
try:
    import yfinance as yf
except ImportError:
    yf = None
from collections import defaultdict


# Reuse existing caching system
from tradingagents.dataflows.cache import get_cache

# Reuse existing data source providers
from tradingagents.dataflows.providers.hk.hk_stock import HKStockProvider

logger = logging.getLogger(__name__)


class ForeignStockService:
    """Hong Kong stock and US stock data services (reusing the unified data source manager, calling according to database priority)"""

    # Cache time configuration (seconds)
    CACHE_TTL = {
        "HK": {
            "quote": 600,        # 10 minutes (real-time quotes)
            "info": 86400,       # 1 Days (basic information)
            "kline": 7200,       # 2 Hourly (K line data)
        },
        "US": {
            "quote": 600,        # 10 minutes
            "info": 86400,       # 1 day
            "kline": 7200,       # 2 hours
        }
    }

    def __init__(self, db=None):
        # Use a unified cache system (MongoDB/Redis/File is automatically selected)
        self.cache = get_cache()

        # Initialize Hong Kong stock data source provider
        self.hk_provider = HKStockProvider()

        # Save database connection (used to query data source priority)
        self.db = db

        # 🔥 Request deduplication: for each (market, code, data_type) Create independent lock
        self._request_locks = defaultdict(asyncio.Lock)

        # 🔥 Ongoing request caching (for sharing results)
        self._pending_requests = {}

        logger.info("✅ ForeignStockService Initialization completed (request deduplication enabled)")

    def _create_requests_session(self):
        """Create requests.Session with proxy and UA (for third-party requests such as yfinance)"""
        try:
            import requests
            import os
            session = requests.Session()
            http_proxy = os.environ.get('HTTP_PROXY', '')
            https_proxy = os.environ.get('HTTPS_PROXY', '')
            proxies = {}
            if http_proxy:
                proxies['http'] = http_proxy
            if https_proxy:
                proxies['https'] = https_proxy
            if proxies:
                session.proxies.update(proxies)
            ua = os.environ.get('TA_HTTP_USER_AGENT', '').strip() or (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/121.0 Safari/537.36 TradingAgentsCN/1.0'
            )
            session.headers.update({'User-Agent': ua})
            return session
        except Exception:
            return None
    
    async def get_quote(self, market: str, code: str, force_refresh: bool = False) -> Dict:
        """
        Get real-time quotes
        
        Args:
            market: market type (HK/US)
            code: Stock code
            force_refresh: Whether to force refresh (skip cache)
        
        Returns:
            Real-time market data
        
        Process:
        1. Check whether to force refresh
        2. Get from cache (Redis → MongoDB → File) 
        3. cache miss → Call data source API (by priority)
        4. Save to cache
        """
        if market == 'HK':
            return await self._get_hk_quote(code, force_refresh)
        elif market == 'US':
            return await self._get_us_quote(code, force_refresh)
        else:
            raise ValueError(f"不支持的市场类型: {market}")
    
    async def get_basic_info(self, market: str, code: str, force_refresh: bool = False) -> Dict:
        """
        Get basic information
        
        Args:
            market: market type (HK/US)
            code: Stock code
            force_refresh: Whether to force refresh
        
        Returns:
            Basic information data
        """
        if market == 'HK':
            return await self._get_hk_info(code, force_refresh)
        elif market == 'US':
            return await self._get_us_info(code, force_refresh)
        else:
            raise ValueError(f"不支持的市场类型: {market}")
    
    async def get_kline(self, market: str, code: str, period: str = 'day', 
                       limit: int = 120, force_refresh: bool = False) -> List[Dict]:
        """
        Get K-line data
        
        Args:
            market: market type (HK/US)
            code: Stock code
            period: cycle (day/week/month)
            limit: Number of data items
            force_refresh: Whether to force refresh
        
        Returns:
            K Line data list
        """
        if market == 'HK':
            return await self._get_hk_kline(code, period, limit, force_refresh)
        elif market == 'US':
            return await self._get_us_kline(code, period, limit, force_refresh)
        else:
            raise ValueError(f"不支持的市场类型: {market}")
    
    async def _get_hk_quote(self, code: str, force_refresh: bool = False) -> Dict:
        """
        Get real-time quotes of Hong Kong stocks (with request to remove duplicates)
        🔥 Called according to the data source priority configured in the database API
        🔥 Prevent repeated calls from concurrent requests API
        """
        # 1. Check cache (unless force refresh)
        if not force_refresh:
            cache_key = self.cache.find_cached_stock_data(
                symbol=code,
                data_source="hk_realtime_quote"
            )

            if cache_key:
                cached_data = self.cache.load_stock_data(cache_key)
                if cached_data:
                    logger.info(f"⚡ 从缓存获取港股行情: {code}")
                    return self._parse_cached_data(cached_data, 'HK', code)

        # 2. 🔥 Request deduplication: Use locks to ensure that there is only one API call for the same stock at the same time
        request_key = f"HK_quote_{code}_{force_refresh}"
        lock = self._request_locks[request_key]

        async with lock:
            # 🔥 Check the cache again (maybe while waiting for the lock, other requests have completed and cached the data)
            # Even if force_refresh=True, Also check if there are other concurrent requests that just completed
            cache_key = self.cache.find_cached_stock_data(
                symbol=code,
                data_source="hk_realtime_quote"
            )
            if cache_key:
                cached_data = self.cache.load_stock_data(cache_key)
                if cached_data:
                    # Check the cache time. If it is within the last 1 second, it means that the concurrent request has just cached it.
                    try:
                        data_dict = json.loads(cached_data) if isinstance(cached_data, str) else cached_data
                        updated_at = data_dict.get('updated_at', '')
                        if updated_at:
                            cache_time = datetime.fromisoformat(updated_at)
                            time_diff = (datetime.now() - cache_time).total_seconds()
                            if time_diff < 1:  # 1 The cache within seconds indicates that the concurrent request has just been completed.
                                logger.info(f"⚡ [去重] 使用并发请求的结果: {code} (缓存时间: {time_diff:.2f}秒前)")
                                return self._parse_cached_data(cached_data, 'HK', code)
                    except Exception as e:
                        logger.debug(f"检查缓存时间失败: {e}")

                    # If it is not a forced refresh, use cache
                    if not force_refresh:
                        logger.info(f"⚡ [After deduplication] Get Hong Kong stock quotes from cache: {code}")
                        return self._parse_cached_data(cached_data, 'HK', code)

            logger.info(f"🔄 开始获取港股行情: {code} (force_refresh={force_refresh})")

            # 3. Get data source priority from database (using unified method)
            source_priority = await self._get_source_priority('HK')

            # 4. Try each data source in order of priority
            quote_data = None
            data_source = None

            # Data source name mapping (database name → processing function)
            # 🔥 These are the only valid data source names
            source_handlers = {
                'yahoo_finance': ('yfinance', self._get_hk_quote_from_yfinance),
                'akshare': ('akshare', self._get_hk_quote_from_akshare),
            }

            # Filter valid data sources and remove duplicates
            valid_priority = []
            seen = set()
            for source_name in source_priority:
                source_key = source_name.lower()
                # Only keep valid data sources
                if source_key in source_handlers and source_key not in seen:
                    seen.add(source_key)
                    valid_priority.append(source_name)

            if not valid_priority:
                logger.warning("⚠️ There is no valid Hong Kong stock data source configured in the database, and the default order is used.")
                valid_priority = ['yahoo_finance', 'akshare']

            logger.info(f"📊 [HK有效数据源] {valid_priority} (股票: {code})")

            for source_name in valid_priority:
                source_key = source_name.lower()
                handler_name, handler_func = source_handlers[source_key]
                try:
                    # 🔥 AKShare Use the asynchronous version, other data sources use asyncio.to_thread to avoid blocking the event loop
                    if source_key == 'akshare':
                        # AKShare Already an asynchronous function, call it directly
                        quote_data = await handler_func(code)
                    else:
                        # Other data sources use thread pools to execute synchronized functions
                        quote_data = await asyncio.to_thread(handler_func, code)
                    data_source = handler_name

                    if quote_data:
                        logger.info(f"✅ {data_source}获取港股行情成功: {code}")
                        break
                except Exception as e:
                    logger.warning(f"⚠️ {source_name}获取失败 ({code}): {e}")
                    continue

            if not quote_data:
                raise Exception(f"无法获取港股{code}的行情数据：所有数据源均失败")

            # 5. Format data
            formatted_data = self._format_hk_quote(quote_data, code, data_source)

            # 6. Save to cache
            self.cache.save_stock_data(
                symbol=code,
                data=json.dumps(formatted_data, ensure_ascii=False),
                data_source="hk_realtime_quote"
            )
            logger.info(f"💾 港股行情已缓存: {code}")

            return formatted_data

    async def _get_source_priority(self, market: str) -> List[str]:
        """
        Get data source priority from database (unified approach)
        🔥 Reuse UnifiedStockService implementation
        """
        market_category_map = {
            "CN": "a_shares",
            "HK": "hk_stocks",
            "US": "us_stocks"
        }

        market_category_id = market_category_map.get(market)

        try:
            # Query from datasource_groupings collection
            groupings = await self.db.datasource_groupings.find({
                "market_category_id": market_category_id,
                "enabled": True
            }).sort("priority", -1).to_list(length=None)

            if groupings:
                priority_list = [g["data_source_name"] for g in groupings]
                logger.info(f"📊 [{market}Data source priority] Read from database: {priority_list}")
                return priority_list
        except Exception as e:
            logger.warning(f"⚠️ [{market}Data source priority] Failed to read from database: {e}, Use default order")

        # Default priority
        default_priority = {
            "CN": ["tushare", "akshare", "baostock"],
            "HK": ["yfinance", "akshare"],
            "US": ["yfinance", "alpha_vantage", "finnhub"]
        }
        priority_list = default_priority.get(market, [])
        logger.info(f"📊 [{market}Data source priority] Use default: {priority_list}")
        return priority_list

    def _get_hk_quote_from_yfinance(self, code: str) -> Dict:
        """Get Hong Kong stock quotes from yfinance"""
        quote_data = self.hk_provider.get_real_time_price(code)
        if not quote_data:
            raise Exception("无数据")

        # 🔥 Supplement yesterday's closing price and price range (yfinance's history(period="1d")Excluding yesterday's closing price and price change)
        try:
            ticker = yf.Ticker(self.hk_provider._normalize_hk_symbol(code))

            # Try to read yesterday's closing price and price range directly from info
            info = getattr(ticker, 'info', None) or {}
            prev_close = info.get('regularMarketPreviousClose')
            change_percent = info.get('regularMarketChangePercent')

            # If info is unavailable or missing, fall back to history to calculate yesterday's closing price (take the closing prices of the last two days)
            if prev_close is None:
                try:
                    hist = ticker.history(period="2d")
                    if not hist.empty and len(hist) >= 2:
                        prev_close = float(hist['Close'].iloc[-2])
                except Exception:
                    prev_close = None

            # Calculate the increase or decrease
            if change_percent is None:
                try:
                    price = quote_data.get('price')
                    if price is not None and prev_close is not None and prev_close > 0:
                        change_percent = (float(price) - float(prev_close)) / float(prev_close) * 100.0
                except Exception:
                    change_percent = None

            if prev_close is not None:
                quote_data['prev_close'] = float(prev_close)
            if change_percent is not None:
                quote_data['change_percent'] = float(change_percent)
        except Exception:
            # Fails silently and does not affect the basic market conditions
            pass

        return quote_data

    async def _get_hk_quote_from_akshare(self, code: str) -> Dict:
        """Get Hong Kong stock quotes from AKShare (asynchronous version to avoid blocking the event loop)"""
        from tradingagents.dataflows.providers.hk.improved_hk import get_hk_stock_info_akshare_async
        try:
            # 🔥 Use an asynchronous version to avoid blocking the event loop
            info = await get_hk_stock_info_akshare_async(code)
            if not info or 'error' in info:
                raise Exception("无数据")

            # Check if price data is available
            if not info.get('price'):
                raise Exception("无价格数据")

            return info
        except asyncio.TimeoutError:
            logger.error(f"⏰ AKShare call timeout: {code}")
            raise Exception("AKShare API call timeout")
        except Exception as e:
            logger.error(f"❌ AKShare Failed to obtain Hong Kong stock quotes: {code} - {e}")
            raise
    
    async def _get_us_quote(self, code: str, force_refresh: bool = False) -> Dict:
        """
        Get real-time quotes of U.S. stocks (with request to remove duplicates)
        🔥 Called according to the data source priority configured in the database API
        🔥 Prevent repeated calls from concurrent requests API
        """
        # 1. Check cache (unless force refresh)
        if not force_refresh:
            cache_key = self.cache.find_cached_stock_data(
                symbol=code,
                data_source="us_realtime_quote"
            )

            if cache_key:
                cached_data = self.cache.load_stock_data(cache_key)
                if cached_data:
                    logger.info(f"⚡ 从缓存获取美股行情: {code}")
                    return self._parse_cached_data(cached_data, 'US', code)

        # 2. 🔥 Request deduplication: Use locks to ensure that there is only one API call for the same stock at the same time
        request_key = f"US_quote_{code}_{force_refresh}"
        lock = self._request_locks[request_key]

        async with lock:
            # 🔥 Check the cache again (maybe while waiting for the lock, other requests have completed and cached the data)
            cache_key = self.cache.find_cached_stock_data(
                symbol=code,
                data_source="us_realtime_quote"
            )
            if cache_key:
                cached_data = self.cache.load_stock_data(cache_key)
                if cached_data:
                    # Check the cache time. If it is within the last 1 second, it means that the concurrent request has just cached it.
                    try:
                        data_dict = json.loads(cached_data) if isinstance(cached_data, str) else cached_data
                        updated_at = data_dict.get('updated_at', '')
                        if updated_at:
                            cache_time = datetime.fromisoformat(updated_at)
                            time_diff = (datetime.now() - cache_time).total_seconds()
                            if time_diff < 1:  # 1 The cache within seconds indicates that the concurrent request has just been completed.
                                logger.info(f"⚡ [去重] 使用并发请求的结果: {code} (缓存时间: {time_diff:.2f}秒前)")
                                return self._parse_cached_data(cached_data, 'US', code)
                    except Exception as e:
                        logger.debug(f"检查缓存时间失败: {e}")

                    # If it is not a forced refresh, use cache
                    if not force_refresh:
                        logger.info(f"⚡ [After deduplication] Get US stock quotes from cache: {code}")
                        return self._parse_cached_data(cached_data, 'US', code)

            logger.info(f"🔄 开始获取美股行情: {code} (force_refresh={force_refresh})")

            # 3. Get data source priority from database (using unified method)
            source_priority = await self._get_source_priority('US')

            # 4. Try each data source in order of priority
            quote_data = None
            data_source = None

            # Data source name mapping (database name → processing function)
            # 🔥 The only valid data source names are:alpha_vantage, yahoo_finance, finnhub
            source_handlers = {
                'alpha_vantage': ('alpha_vantage', self._get_us_quote_from_alpha_vantage),
                'yahoo_finance': ('yfinance', self._get_us_quote_from_yfinance),
                'finnhub': ('finnhub', self._get_us_quote_from_finnhub),
            }

            # Filter valid data sources and remove duplicates
            valid_priority = []
            seen = set()
            for source_name in source_priority:
                source_key = source_name.lower()
                # Only keep valid data sources
                if source_key in source_handlers and source_key not in seen:
                    seen.add(source_key)
                    valid_priority.append(source_name)

            if not valid_priority:
                logger.warning("⚠️ There is no valid US stock data source configured in the database, and the default order is used.")
                valid_priority = ['yahoo_finance', 'alpha_vantage', 'finnhub']

            logger.info(f"📊 [US有效数据源] {valid_priority} (股票: {code})")

            for source_name in valid_priority:
                source_key = source_name.lower()
                handler_name, handler_func = source_handlers[source_key]
                try:
                    # 🔥 Use asyncio.to_thread to avoid blocking the event loop
                    quote_data = await asyncio.to_thread(handler_func, code)
                    data_source = handler_name

                    if quote_data:
                        logger.info(f"✅ {data_source}获取美股行情成功: {code}")
                        break
                except Exception as e:
                    logger.warning(f"⚠️ {source_name}获取失败 ({code}): {e}")
                    continue

            if not quote_data:
                raise Exception(f"无法获取美股{code}的行情数据：所有数据源均失败")

            # 5. Format data
            formatted_data = {
                'code': code,
                'name': quote_data.get('name', f'美股{code}'),
                'market': 'US',
                'price': quote_data.get('price'),
                'open': quote_data.get('open'),
                'high': quote_data.get('high'),
                'low': quote_data.get('low'),
                'volume': quote_data.get('volume'),
                'change_percent': quote_data.get('change_percent'),
                'trade_date': quote_data.get('trade_date'),
                'currency': quote_data.get('currency', 'USD'),
                'source': data_source,
                'updated_at': datetime.now().isoformat()
            }

            # 6. Save to cache
            self.cache.save_stock_data(
                symbol=code,
                data=json.dumps(formatted_data, ensure_ascii=False),
                data_source="us_realtime_quote"
            )
            logger.info(f"💾 美股行情已缓存: {code}")

            return formatted_data

    def _get_us_quote_from_yfinance(self, code: str) -> Dict:
        """Get US stock quotes from yfinance"""
        ticker = yf.Ticker(code)
        hist = ticker.history(period='1d')

        if hist.empty:
            raise Exception("无数据")

        latest = hist.iloc[-1]
        info = ticker.info

        return {
            'name': info.get('longName') or info.get('shortName'),
            'price': float(latest['Close']),
            'open': float(latest['Open']),
            'high': float(latest['High']),
            'low': float(latest['Low']),
            'volume': int(latest['Volume']),
            'change_percent': round(((latest['Close'] - latest['Open']) / latest['Open'] * 100), 2),
            'trade_date': hist.index[-1].strftime('%Y-%m-%d'),
            'currency': info.get('currency', 'USD')
        }

    def _get_us_quote_from_alpha_vantage(self, code: str) -> Dict:
        """Get U.S. stock quotes from Alpha Vantage"""
        try:
            from tradingagents.dataflows.providers.us.alpha_vantage_common import get_api_key, _make_api_request

            # get API Key
            api_key = get_api_key()
            if not api_key:
                raise Exception("Alpha Vantage API Key Not configured")

            # call GLOBAL_QUOTE API
            params = {
                "symbol": code.upper(),
            }

            data = _make_api_request("GLOBAL_QUOTE", params)

            if not data or "Global Quote" not in data:
                raise Exception("Alpha Vantage Return data is empty")

            quote = data["Global Quote"]

            if not quote:
                raise Exception("无数据")

            # Try to get the stock name (Alpha Vantage GLOBAL_QUOTE does not contain the name and requires an additional call)
            stock_name = None
            try:
                # Try using yfinance to get the name (fast and free)
                import yfinance as yf
                ticker = yf.Ticker(code)
                info = ticker.info
                if info:
                    stock_name = info.get('longName') or info.get('shortName')
            except Exception:
                # Fails silently, using default name
                pass

            if not stock_name:
                stock_name = f'美股{code}'

            # Parse data
            return {
                'symbol': quote.get('01. symbol', code),
                'name': stock_name,  # Add stock name
                'price': float(quote.get('05. price', 0)),
                'open': float(quote.get('02. open', 0)),
                'high': float(quote.get('03. high', 0)),
                'low': float(quote.get('04. low', 0)),
                'volume': int(quote.get('06. volume', 0)),
                'latest_trading_day': quote.get('07. latest trading day', ''),
                'previous_close': float(quote.get('08. previous close', 0)),
                'change': float(quote.get('09. change', 0)),
                'change_percent': quote.get('10. change percent', '0%').rstrip('%'),
            }

        except Exception as e:
            logger.error(f"❌ Alpha Vantage Failed to obtain US stock quotes: {e}")
            raise

    def _get_us_quote_from_finnhub(self, code: str) -> Dict:
        """Get US stock quotes from Finnhub"""
        try:
            import finnhub
            import os

            # get API Key
            api_key = os.getenv('FINNHUB_API_KEY')
            if not api_key:
                raise Exception("Finnhub API Key Not configured")

            # Create client
            client = finnhub.Client(api_key=api_key)

            # Get real-time quotes
            quote = client.quote(code.upper())

            if not quote or 'c' not in quote:
                raise Exception("无数据")

            # Try to get the stock name (Finnhub quote does not contain the name and requires an additional call)
            stock_name = None
            try:
                # Try using Finnhub's company_profile2 to get the name
                profile = client.company_profile2(symbol=code.upper())
                if profile:
                    stock_name = profile.get('name')
            except Exception:
                # If Finnhub fails, try using yfinance
                try:
                    import yfinance as yf
                    ticker = yf.Ticker(code)
                    info = ticker.info
                    if info:
                        stock_name = info.get('longName') or info.get('shortName')
                except Exception:
                    pass

            if not stock_name:
                stock_name = f'美股{code}'

            # Parse data
            return {
                'symbol': code.upper(),
                'name': stock_name,  # Add stock name
                'price': quote.get('c', 0),  # current price
                'open': quote.get('o', 0),   # open price
                'high': quote.get('h', 0),   # high price
                'low': quote.get('l', 0),    # low price
                'previous_close': quote.get('pc', 0),  # previous close
                'change': quote.get('d', 0),  # change
                'change_percent': quote.get('dp', 0),  # change percent
                'timestamp': quote.get('t', 0),  # timestamp
            }

        except Exception as e:
            logger.error(f"❌ Finnhub Failed to obtain US stock quotes: {e}")
            raise
    
    async def _get_hk_info(self, code: str, force_refresh: bool = False) -> Dict:
        """
        Get basic information about Hong Kong stocks
        🔥 Called according to the data source priority configured in the database API
        """
        # 1. Check cache (unless force refresh)
        if not force_refresh:
            cache_key = self.cache.find_cached_stock_data(
                symbol=code,
                data_source="hk_basic_info"
            )

            if cache_key:
                cached_data = self.cache.load_stock_data(cache_key)
                if cached_data:
                    logger.info(f"⚡ Obtain basic information of Hong Kong stocks from cache: {code}")
                    return self._parse_cached_data(cached_data, 'HK', code)

        # 2. Get data source priority from database
        source_priority = await self._get_source_priority('HK')

        # 3. Try each data source according to priority (allowing multiple sources to be merged to complete missing fields)
        info_data = None
        data_source = None
        merged_data: Dict = {}
        merged_sources: list = []

        # Data source name mapping
        source_handlers = {
            'akshare': ('akshare', self._get_hk_info_from_akshare),
            'yahoo_finance': ('yfinance', self._get_hk_info_from_yfinance),
            'finnhub': ('finnhub', self._get_hk_info_from_finnhub),
        }

        # Filter valid data sources and remove duplicates
        valid_priority = []
        seen = set()
        for source_name in source_priority:
            source_key = source_name.lower()
            if source_key in source_handlers and source_key not in seen:
                seen.add(source_key)
                valid_priority.append(source_name)

        if not valid_priority:
            logger.warning("⚠️ There is no valid Hong Kong stock basic information data source configured in the database, and the default order is used.")
            valid_priority = ['akshare', 'yahoo_finance', 'finnhub']

        logger.info(f"📊 [HK Effective data sources for basic information] {valid_priority}")

        # Try and merge the data one by one, giving priority to the first successful data as the basis
        for source_name in valid_priority:
            source_key = source_name.lower()
            handler_name, handler_func = source_handlers[source_key]
            try:
                # 🔥 Use asyncio.to_thread to avoid blocking the event loop
                import asyncio
                data = await asyncio.to_thread(handler_func, code)
                if not data:
                    raise Exception("无数据")

                logger.info(f"✅ {handler_name}获取港股基础信息成功: {code}")

                # Initialize base data
                if not merged_sources:
                    info_data = data
                    data_source = handler_name
                    merged_data = dict(data)
                    merged_sources.append(handler_name)
                    continue

                # Merge and complete missing fields
                def pick(base_val, new_val):
                    return base_val if base_val not in (None, '') else new_val

                for k in [
                    'name', 'market_cap', 'industry', 'sector',
                    'pe_ratio', 'pb_ratio', 'dividend_yield', 'currency'
                ]:
                    merged_data[k] = pick(merged_data.get(k), data.get(k))

                merged_sources.append(handler_name)
            except Exception as e:
                logger.warning(f"⚠️ {source_name}获取基础信息失败: {e}")
                continue

        if not merged_data:
            raise Exception(f"无法获取港股{code}的基础信息：所有数据源均失败")

        # 4. Try to calculate and complete PS, ROE, debt ratio (from financial indicators)
        try:
            from tradingagents.dataflows.providers.hk.improved_hk import get_hk_financial_indicators
            financial_indicators = get_hk_financial_indicators(code)

            if isinstance(financial_indicators, dict) and financial_indicators:
                # Complement ROE and debt ratio
                if merged_data.get('roe') is None and financial_indicators.get('roe_avg') is not None:
                    merged_data['roe'] = financial_indicators.get('roe_avg')
                if merged_data.get('debt_ratio') is None and financial_indicators.get('debt_asset_ratio') is not None:
                    merged_data['debt_ratio'] = financial_indicators.get('debt_asset_ratio')

                # Calculate PS = Market value / operating income (the units must be consistent, and the default is HKD)
                if merged_data.get('ps_ratio') is None:
                    mcap = merged_data.get('market_cap')
                    operate_income = financial_indicators.get('operate_income')
                    try:
                        if mcap and operate_income and float(operate_income) > 0:
                            merged_data['ps_ratio'] = float(mcap) / float(operate_income)
                            logger.info(
                                f"📊 计算港股{code} PS: market_cap={mcap} operate_income={operate_income} -> {merged_data['ps_ratio']:.4f}"
                            )
                    except Exception as e:
                        logger.warning(f"⚠️ 计算PS失败: {e}")
        except Exception as e:
            logger.warning(f"⚠️ 获取财务指标失败: {e}")

        # 5. Formatted data (source uses synthetic tags)
        source_label = '+'.join(merged_sources) if merged_sources else (data_source or 'unknown')
        formatted_data = self._format_hk_info(merged_data, code, source_label)

        # 6. Save to cache
        self.cache.save_stock_data(
            symbol=code,
            data=json.dumps(formatted_data, ensure_ascii=False),
            data_source="hk_basic_info"
        )
        logger.info(f"💾 港股基础信息已缓存: {code}")

        return formatted_data

    async def _get_us_info(self, code: str, force_refresh: bool = False) -> Dict:
        """
        Get basic information on U.S. stocks
        🔥 Called according to the data source priority configured in the database API
        """
        # 1. Check cache (unless force refresh)
        if not force_refresh:
            cache_key = self.cache.find_cached_stock_data(
                symbol=code,
                data_source="us_basic_info"
            )

            if cache_key:
                cached_data = self.cache.load_stock_data(cache_key)
                if cached_data:
                    logger.info(f"⚡ Get basic U.S. stock information from cache: {code}")
                    return self._parse_cached_data(cached_data, 'US', code)

        # 2. Get data source priority from database
        source_priority = await self._get_source_priority('US')

        # 3. Try each data source by priority and perform multi-source merge
        merged_data: Dict[str, Any] = {}
        merged_sources: List[str] = []

        # Data source name mapping
        source_handlers = {
            'alpha_vantage': ('alpha_vantage', self._get_us_info_from_alpha_vantage),
            'yahoo_finance': ('yfinance', self._get_us_info_from_yfinance),
            'finnhub': ('finnhub', self._get_us_info_from_finnhub),
        }

        # Filter valid data sources and remove duplicates
        valid_priority = []
        seen = set()
        for source_name in source_priority:
            source_key = source_name.lower()
            if source_key in source_handlers and source_key not in seen:
                seen.add(source_key)
                valid_priority.append(source_name)

        if not valid_priority:
            logger.warning("⚠️ There is no valid US stock data source configured in the database, and the default order is used.")
            valid_priority = ['yahoo_finance', 'alpha_vantage', 'finnhub']

        logger.info(f"📊 [US Effective data sources for basic information] {valid_priority}")

        import asyncio
        for source_name in valid_priority:
            source_key = source_name.lower()
            handler_name, handler_func = source_handlers[source_key]
            try:
                info_data = await asyncio.to_thread(handler_func, code)
                if info_data:
                    logger.info(f"✅ {handler_name}获取美股基础信息成功: {code}")
                    merged_sources.append(handler_name)
                    # Complete field by field
                    for k in ['name', 'industry', 'sector', 'market_cap', 'pe_ratio', 'pb_ratio', 'dividend_yield', 'currency']:
                        if merged_data.get(k) in (None, ''):
                            merged_data[k] = info_data.get(k)
            except Exception as e:
                logger.warning(f"⚠️ {source_name}获取基础信息失败: {e}")
                continue

        if not merged_data:
            raise Exception(f"无法获取美股{code}的基础信息：所有数据源均失败")

        # 4. Try to use yfinance's quick information to fill in missing fields (such as market capitalization, PS, ROE, debt ratio)
        try:
            ticker = yf.Ticker(code)
            info_raw = getattr(ticker, 'info', None) or {}

            # Market cap completion (use info.marketCap first, followed by fast_info.market_cap)
            if not merged_data.get('market_cap'):
                mcap = info_raw.get('marketCap')
                try:
                    fast_info = getattr(ticker, 'fast_info', None)
                    if not mcap and fast_info is not None:
                        mcap = getattr(fast_info, 'market_cap', None)
                        if mcap is None and isinstance(fast_info, dict):
                            mcap = fast_info.get('market_cap')
                except Exception:
                    pass
                if mcap:
                    merged_data['market_cap'] = mcap

            # Calculate/complete PS (using totalRevenue)
            if merged_data.get('ps_ratio') is None:
                mcap = merged_data.get('market_cap')
                total_revenue = info_raw.get('totalRevenue')
                try:
                    if mcap and total_revenue and float(total_revenue) > 0:
                        merged_data['ps_ratio'] = float(mcap) / float(total_revenue)
                        logger.info(
                            f"📊 计算美股{code} PS: market_cap={mcap} totalRevenue={total_revenue} -> {merged_data['ps_ratio']:.4f}"
                        )
                except Exception as e:
                    logger.warning(f"⚠️ 计算PS失败: {e}")

            # Complete ROE and debt ratio (indicators provided by yfinance)
            if merged_data.get('roe') is None and info_raw.get('returnOnEquity') is not None:
                merged_data['roe'] = info_raw.get('returnOnEquity')
            if merged_data.get('debt_ratio') is None and info_raw.get('debtToEquity') is not None:
                merged_data['debt_ratio'] = info_raw.get('debtToEquity')
        except Exception as e:
            logger.warning(f"⚠️ yfinance Indicator completion failed: {e}")

        # 5. Build formatted data (source uses synthetic tags)
        source_label = '+'.join(merged_sources) if merged_sources else 'unknown'
        market_cap = merged_data.get('market_cap')
        ps_val = merged_data.get('ps_ratio')

        formatted_data = {
            'code': code,
            'name': merged_data.get('name') or f'美股{code}',
            'market': 'US',
            'industry': merged_data.get('industry'),
            'sector': merged_data.get('sector'),
            'total_mv': market_cap / 1e8 if market_cap else None,
            'pe_ttm': merged_data.get('pe_ratio'),
            'pe': merged_data.get('pe_ratio'),
            'pb': merged_data.get('pb_ratio'),
            'ps': ps_val,
            'ps_ttm': ps_val,
            'roe': merged_data.get('roe'),
            'debt_ratio': merged_data.get('debt_ratio'),
            'dividend_yield': merged_data.get('dividend_yield'),
            'currency': merged_data.get('currency', 'USD'),
            'source': source_label,
            'updated_at': datetime.now().isoformat()
        }

        # 6. Save to cache
        self.cache.save_stock_data(
            symbol=code,
            data=json.dumps(formatted_data, ensure_ascii=False),
            data_source="us_basic_info"
        )
        logger.info(f"💾 美股基础信息已缓存: {code}")

        return formatted_data

    async def _get_hk_kline(self, code: str, period: str, limit: int, force_refresh: bool = False) -> List[Dict]:
        """
        Get Hong Kong stock K-line data
        🔥 Called according to the data source priority configured in the database API
        """
        # 1. Check cache (unless force refresh)
        cache_key_str = f"hk_kline_{period}_{limit}"
        if not force_refresh:
            cache_key = self.cache.find_cached_stock_data(
                symbol=code,
                data_source=cache_key_str
            )

            if cache_key:
                cached_data = self.cache.load_stock_data(cache_key)
                if cached_data:
                    logger.info(f"⚡ 从缓存获取港股K线: {code}")
                    return self._parse_cached_kline(cached_data)

        # 2. Get data source priority from database
        source_priority = await self._get_source_priority('HK')

        # 3. Try each data source in order of priority
        kline_data = None
        data_source = None

        # Data source name mapping
        source_handlers = {
            'akshare': ('akshare', self._get_hk_kline_from_akshare),
            'yahoo_finance': ('yfinance', self._get_hk_kline_from_yfinance),
            'finnhub': ('finnhub', self._get_hk_kline_from_finnhub),
        }

        # Filter valid data sources and remove duplicates
        valid_priority = []
        seen = set()
        for source_name in source_priority:
            source_key = source_name.lower()
            if source_key in source_handlers and source_key not in seen:
                seen.add(source_key)
                valid_priority.append(source_name)

        if not valid_priority:
            logger.warning("⚠️ There is no valid Hong Kong stock K-line data source configured in the database, and the default order is used.")
            valid_priority = ['akshare', 'yahoo_finance', 'finnhub']

        logger.info(f"📊 [HK K Online valid data source] {valid_priority}")

        for source_name in valid_priority:
            source_key = source_name.lower()
            handler_name, handler_func = source_handlers[source_key]
            try:
                # 🔥 Use asyncio.to_thread to avoid blocking the event loop
                import asyncio
                kline_data = await asyncio.to_thread(handler_func, code, period, limit)
                data_source = handler_name

                if kline_data:
                    logger.info(f"✅ {data_source}获取港股K线成功: {code}")
                    break
            except Exception as e:
                logger.warning(f"⚠️ {source_name}获取K线失败: {e}")
                continue

        if not kline_data:
            raise Exception(f"无法获取港股{code}的K线数据：所有数据源均失败")

        # 4. Save to cache
        self.cache.save_stock_data(
            symbol=code,
            data=json.dumps(kline_data, ensure_ascii=False),
            data_source=cache_key_str
        )
        logger.info(f"💾 港股K线已缓存: {code}")

        return kline_data

    async def _get_us_kline(self, code: str, period: str, limit: int, force_refresh: bool = False) -> List[Dict]:
        """
        Get U.S. stock K-line data
        🔥 Called according to the data source priority configured in the database API
        """
        # 1. Check cache (unless force refresh)
        cache_key_str = f"us_kline_{period}_{limit}"
        if not force_refresh:
            cache_key = self.cache.find_cached_stock_data(
                symbol=code,
                data_source=cache_key_str
            )

            if cache_key:
                cached_data = self.cache.load_stock_data(cache_key)
                if cached_data:
                    logger.info(f"⚡ 从缓存获取美股K线: {code}")
                    return self._parse_cached_kline(cached_data)

        # 2. Get data source priority from database
        source_priority = await self._get_source_priority('US')

        # 3. Try each data source in order of priority
        kline_data = None
        data_source = None

        # Data source name mapping
        source_handlers = {
            'alpha_vantage': ('alpha_vantage', self._get_us_kline_from_alpha_vantage),
            'yahoo_finance': ('yfinance', self._get_us_kline_from_yfinance),
            'finnhub': ('finnhub', self._get_us_kline_from_finnhub),
        }

        # Filter valid data sources and remove duplicates
        valid_priority = []
        seen = set()
        for source_name in source_priority:
            source_key = source_name.lower()
            if source_key in source_handlers and source_key not in seen:
                seen.add(source_key)
                valid_priority.append(source_name)

        if not valid_priority:
            logger.warning("⚠️ There is no valid US stock data source configured in the database, and the default order is used.")
            valid_priority = ['yahoo_finance', 'alpha_vantage', 'finnhub']

        logger.info(f"📊 [US K Online valid data source] {valid_priority}")

        for source_name in valid_priority:
            source_key = source_name.lower()
            handler_name, handler_func = source_handlers[source_key]
            try:
                # 🔥 Use asyncio.to_thread to avoid blocking the event loop
                import asyncio
                kline_data = await asyncio.to_thread(handler_func, code, period, limit)
                data_source = handler_name

                if kline_data:
                    logger.info(f"✅ {data_source}获取美股K线成功: {code}")
                    break
            except Exception as e:
                logger.warning(f"⚠️ {source_name}获取K线失败: {e}")
                continue

        if not kline_data:
            raise Exception(f"无法获取美股{code}的K线数据：所有数据源均失败")

        # 4. Save to cache
        self.cache.save_stock_data(
            symbol=code,
            data=json.dumps(kline_data, ensure_ascii=False),
            data_source=cache_key_str
        )
        logger.info(f"💾 美股K线已缓存: {code}")

        return kline_data
    
    def _format_hk_quote(self, data: Dict, code: str, source: str) -> Dict:
        """格式化港股行情数据"""
        price = data.get('price') or data.get('close')
        prev_close = data.get('prev_close')
        change_percent = data.get('change_percent')

        # If yesterday's closing price is missing but there is a rise or fall and the latest price, then yesterday's closing price will be inferred.
        if prev_close is None:
            try:
                if price is not None and change_percent is not None:
                    prev_close = float(price) / (1.0 + float(change_percent) / 100.0)
            except Exception:
                prev_close = None

        # If the increase or decrease is missing but yesterday's closing price and the latest price are available, the increase or decrease will be calculated.
        if change_percent is None:
            try:
                if price is not None and prev_close is not None and prev_close > 0:
                    change_percent = (float(price) - float(prev_close)) / float(prev_close) * 100.0
            except Exception:
                change_percent = None

        # Calculate amplitude (amplitude) = (high-low)/Collected yesterday * 100%
        amplitude = None
        try:
            high = data.get('high')
            low = data.get('low')
            if high is not None and low is not None and prev_close is not None and prev_close > 0:
                amplitude = (float(high) - float(low)) / float(prev_close) * 100.0
        except Exception:
            amplitude = None

        return {
            'code': code,
            'name': data.get('name', f'港股{code}'),
            'market': 'HK',
            'price': price,
            'open': data.get('open'),
            'high': data.get('high'),
            'low': data.get('low'),
            'volume': data.get('volume'),
            'amount': data.get('amount'),  # may be missing
            'prev_close': prev_close,
            'change_percent': change_percent,
            'turnover_rate': data.get('turnover_rate'),  # Hong Kong stocks are often missing
            'amplitude': None if amplitude is None else round(float(amplitude), 2),
            'currency': data.get('currency', 'HKD'),
            'source': source,
            'trade_date': data.get('timestamp', datetime.now().strftime('%Y-%m-%d')),
            'updated_at': datetime.now().isoformat()
        }

    def _format_hk_info(self, data: Dict, code: str, source: str) -> Dict:
        """格式化港股基础信息"""
        market_cap = data.get('market_cap')
        return {
            'code': code,
            'name': data.get('name', f'港股{code}'),
            'market': 'HK',
            'industry': data.get('industry'),
            'sector': data.get('sector'),
            # Front-end expectation total_mv (unit: 100 million yuan)
            'total_mv': market_cap / 1e8 if market_cap else None,
            # The frontend expects pe_ttm or pe
            'pe_ttm': data.get('pe_ratio'),
            'pe': data.get('pe_ratio'),
            # Front-end expectations pb
            'pb': data.get('pb_ratio'),
            # Front-end expectations ps
            'ps': data.get('ps_ratio'),
            'ps_ttm': data.get('ps_ratio'),
            # 🔥 Get roe and from financial indicators debt_ratio
            'roe': data.get('roe'),
            'debt_ratio': data.get('debt_ratio'),
            'dividend_yield': data.get('dividend_yield'),
            'currency': data.get('currency', 'HKD'),
            'source': source,
            'updated_at': datetime.now().isoformat()
        }

    def _parse_cached_data(self, cached_data: str, market: str, code: str) -> Dict:
        """解析缓存的数据"""
        try:
            # try to parse JSON
            if isinstance(cached_data, str):
                data = json.loads(cached_data)
            else:
                data = cached_data

            # Make sure you include the necessary fields
            if isinstance(data, dict):
                data['market'] = market
                data['code'] = code
                return data
            else:
                raise ValueError("缓存数据格式错误")
        except Exception as e:
            logger.warning(f"⚠️ 解析缓存数据失败: {e}")
            # Return empty data, trigger re-acquisition
            return None

    def _parse_cached_kline(self, cached_data: str) -> List[Dict]:
        """解析缓存的K线数据"""
        try:
            # try to parse JSON
            if isinstance(cached_data, str):
                data = json.loads(cached_data)
            else:
                data = cached_data

            # Make sure it's a list
            if isinstance(data, list):
                return data
            else:
                raise ValueError("缓存K线数据格式错误")
        except Exception as e:
            logger.warning(f"⚠️ Failed to parse cached K-line data: {e}")
            # Returns an empty list, triggering reacquisition
            return []

    def _get_us_info_from_yfinance(self, code: str) -> Dict:
        """Get basic information on US stocks from yfinance"""
        ticker = yf.Ticker(code)
        
        info = {}
        try:
            info = ticker.info
        except Exception as e:
            logger.warning(f"⚠️ yfinance info Failed to obtain ({code}): {e}")

        # Try to get fast_info as a supplement
        fast_info = None
        try:
            fast_info = getattr(ticker, 'fast_info', None)
        except Exception:
            pass

        if not info and not fast_info:
            raise Exception("无数据")

        # Extract data
        data = {
            'name': info.get('longName') or info.get('shortName'),
            'industry': info.get('industry'),
            'sector': info.get('sector'),
            'market_cap': info.get('marketCap'),
            'pe_ratio': info.get('trailingPE'),
            'pb_ratio': info.get('priceToBook'),
            'dividend_yield': info.get('dividendYield'),
            'currency': info.get('currency', 'USD'),
        }

        # Use fast_info completion
        if fast_info:
            if not data['market_cap']:
                data['market_cap'] = getattr(fast_info, 'market_cap', None)
            if data['currency'] == 'USD': # Default value, try to update
                curr = getattr(fast_info, 'currency', None)
                if curr:
                    data['currency'] = curr

        # Check if there is valid data
        valid_fields = [k for k, v in data.items() if v is not None]
        if not valid_fields:
            raise Exception("无有效数据")

        return data

    def _safe_float(self, value, default=None):
        """Safely convert to floating point, handle 'None' Strings and null values"""
        if value is None or value == '' or value == 'None' or value == 'N/A':
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _get_us_info_from_alpha_vantage(self, code: str) -> Dict:
        """Get basic information on U.S. stocks from Alpha Vantage"""
        from tradingagents.dataflows.providers.us.alpha_vantage_common import get_api_key, _make_api_request

        # get API Key
        api_key = get_api_key()
        if not api_key:
            raise Exception("Alpha Vantage API Key Not configured")

        # call OVERVIEW API
        params = {"symbol": code.upper()}
        data = _make_api_request("OVERVIEW", params)

        if not data or not data.get('Symbol'):
            raise Exception("无数据")

        return {
            'name': data.get('Name'),
            'industry': data.get('Industry'),
            'sector': data.get('Sector'),
            'market_cap': self._safe_float(data.get('MarketCapitalization')),
            'pe_ratio': self._safe_float(data.get('TrailingPE')),
            'pb_ratio': self._safe_float(data.get('PriceToBookRatio')),
            'dividend_yield': self._safe_float(data.get('DividendYield')),
            'currency': 'USD',
        }

    def _get_us_info_from_finnhub(self, code: str) -> Dict:
        """Get basic information on US stocks from Finnhub"""
        import finnhub
        import os

        # get API Key
        api_key = os.getenv('FINNHUB_API_KEY')
        if not api_key:
            raise Exception("Finnhub API Key Not configured")

        # Create client
        client = finnhub.Client(api_key=api_key)

        # Get company information
        profile = client.company_profile2(symbol=code.upper())

        if not profile:
            raise Exception("无数据")

        return {
            'name': profile.get('name'),
            'industry': profile.get('finnhubIndustry'),
            'sector': None,  # Finnhub Not available sector
            'market_cap': profile.get('marketCapitalization') * 1000000 if profile.get('marketCapitalization') else None,  # Convert to USD
            'pe_ratio': None,  # Finnhub profile Not provided directly PE
            'pb_ratio': None,  # Finnhub profile Not provided directly PB
            'dividend_yield': None,  # Finnhub profile Dividend rate is not provided directly
            'currency': profile.get('currency', 'USD'),
        }

    def _get_us_kline_from_yfinance(self, code: str, period: str, limit: int) -> List[Dict]:
        """Obtain US stock K-line data from yfinance (improved window and fallback logic)"""
        import math
        from datetime import datetime, timedelta

        ticker = yf.Ticker(code)

        # cycles map to yfinance interval
        period_map = {
            'day': '1d',
            'week': '1wk',
            'month': '1mo',
            '5m': '5m',
            '15m': '15m',
            '30m': '30m',
            '60m': '60m'
        }
        interval = period_map.get(period, '1d')

        # Calculate reasonable time windows for different intervals to avoid being too long and causing empty data/current limiting
        # Trading day minutes are approximately 390 minutes
        intraday_bars_per_day = {
            '5m': 78,
            '15m': 26,
            '30m': 13,
            '60m': 7  # Round slightly larger to ensure sufficient data
        }

        def calc_days_back(interval: str, limit: int) -> int:
            if interval in intraday_bars_per_day:
                bars_per_day = intraday_bars_per_day[interval]
                # At least 2 days, plus one redundancy, and no more than 60 days (Yahoo limit)
                days = max(2, math.ceil(limit / bars_per_day) + 2)
                return min(days, 59)
            elif interval == '1wk':
                # One stick per week, grab 2 times the number of redundant weeks, converted into days
                return max(30, limit * 14)
            elif interval == '1mo':
                # One stick per month, capture 2 times the number of redundant months, and convert it into days
                return max(120, limit * 45)
            else:  # '1d'
                # One stick per day, grab 2 times the number of redundant days
                return max(180, limit * 2)

        days_back = calc_days_back(interval, limit)

        # First attempt: period mode (more stable, automatically handles missing trading days)
        hist = ticker.history(period=f'{days_back}d', interval=interval, auto_adjust=False)

        # Fallback: Use start/end to clarify the time range (period returns empty in some scenarios)
        if hist is None or hist.empty:
            end = datetime.now()
            start = end - timedelta(days=days_back)
            hist = ticker.history(start=start, end=end, interval=interval, auto_adjust=False)

        if hist is None or hist.empty:
            raise Exception("无数据")

        # Return only the required quantity (truncated from the tail)
        hist = hist.tail(limit)

        # Format data
        kline_data = []
        for date, row in hist.iterrows():
            try:
                date_str = date.strftime('%Y-%m-%d')
                kline_data.append({
                    'date': date_str,
                    'trade_date': date_str,  # The front end requires this field
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': int(row.get('Volume', 0))
                })
            except Exception:
                # Skip abnormal lines to ensure overall availability
                continue

        if not kline_data:
            raise Exception("无数据")

        return kline_data

    def _get_us_kline_from_alpha_vantage(self, code: str, period: str, limit: int) -> List[Dict]:
        """Get US stock K-line data from Alpha Vantage (avoid premium restrictions)"""
        from tradingagents.dataflows.providers.us.alpha_vantage_common import get_api_key, _make_api_request
        import pandas as pd

        # get API Key
        api_key = get_api_key()
        if not api_key:
            raise Exception("Alpha Vantage API Key Not configured")

        # Select the API function based on the period and use outputsize=compact avoid premium
        if period in ['5m', '15m', '30m', '60m']:
            function = "TIME_SERIES_INTRADAY"
            params = {
                "symbol": code.upper(),
                "interval": period,
                "outputsize": "compact"  # Avoid premium restrictions
            }
            time_series_key = f"Time Series ({period})"
        elif period == 'week':
            function = "TIME_SERIES_WEEKLY"
            params = {
                "symbol": code.upper()
            }
            time_series_key = "Weekly Time Series"
        elif period == 'month':
            function = "TIME_SERIES_MONTHLY"
            params = {
                "symbol": code.upper()
            }
            time_series_key = "Monthly Time Series"
        else:
            function = "TIME_SERIES_DAILY"
            params = {
                "symbol": code.upper(),
                "outputsize": "compact"  # Avoid premium restrictions
            }
            time_series_key = "Time Series (Daily)"

        data = _make_api_request(function, params)

        # Avoid exceptions caused by permission/current limiting errors and gracefully return no data to allow the upper layer to try other sources.
        if not data or time_series_key not in data:
            raise Exception("无数据")

        time_series = data[time_series_key]

        # Convert to DataFrame
        df = pd.DataFrame.from_dict(time_series, orient='index')
        df.index = pd.to_datetime(df.index)
        df = df.sort_index(ascending=False)  # latest first

        # limited quantity
        df = df.head(limit)

        # Format data
        kline_data = []
        for date, row in df.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            kline_data.append({
                'date': date_str,
                'trade_date': date_str,  # The front end requires this field
                'open': float(row['1. open']),
                'high': float(row['2. high']),
                'low': float(row['3. low']),
                'close': float(row['4. close']),
                'volume': int(row['5. volume'])
            })

        return kline_data

    def _get_us_kline_from_finnhub(self, code: str, period: str, limit: int) -> List[Dict]:
        """Obtain US stock K-line data from Finnhub"""
        import finnhub
        import os
        from datetime import datetime, timedelta

        # get API Key
        api_key = os.getenv('FINNHUB_API_KEY')
        if not api_key:
            raise Exception("Finnhub API Key Not configured")

        # Create client
        client = finnhub.Client(api_key=api_key)

        # Calculate date range
        end_date = datetime.now()

        # Calculate start date based on period
        if period == 'day':
            start_date = end_date - timedelta(days=limit)
            resolution = 'D'
        elif period == 'week':
            start_date = end_date - timedelta(weeks=limit)
            resolution = 'W'
        elif period == 'month':
            start_date = end_date - timedelta(days=limit * 30)
            resolution = 'M'
        elif period == '5m':
            start_date = end_date - timedelta(days=limit)
            resolution = '5'
        elif period == '15m':
            start_date = end_date - timedelta(days=limit)
            resolution = '15'
        elif period == '30m':
            start_date = end_date - timedelta(days=limit)
            resolution = '30'
        elif period == '60m':
            start_date = end_date - timedelta(days=limit)
            resolution = '60'
        else:
            start_date = end_date - timedelta(days=limit)
            resolution = 'D'

        # Get K-line data
        candles = client.stock_candles(
            code.upper(),
            resolution,
            int(start_date.timestamp()),
            int(end_date.timestamp())
        )

        if not candles or candles.get('s') != 'ok':
            raise Exception("无数据")

        # Format data
        kline_data = []
        for i in range(len(candles['t'])):
            date_str = datetime.fromtimestamp(candles['t'][i]).strftime('%Y-%m-%d')
            kline_data.append({
                'date': date_str,
                'trade_date': date_str,  # The front end requires this field
                'open': float(candles['o'][i]),
                'high': float(candles['h'][i]),
                'low': float(candles['l'][i]),
                'close': float(candles['c'][i]),
                'volume': int(candles['v'][i])
            })

        return kline_data

    async def get_hk_news(self, code: str, days: int = 2, limit: int = 50) -> Dict:
        """
        Get Hong Kong stock news

        Args:
            code: Stock code
            days: Lookback days
            limit: Return quantity limit

        Returns:
            Dictionary containing news lists and data sources
        """
        from datetime import datetime, timedelta

        logger.info(f"📰 开始获取港股新闻: {code}, days={days}, limit={limit}")

        # 1. Try to get from cache
        cache_key_str = f"hk_news_{days}_{limit}"
        cache_key = self.cache.find_cached_stock_data(
            symbol=code,
            data_source=cache_key_str
        )

        if cache_key:
            cached_data = self.cache.load_stock_data(cache_key)
            if cached_data:
                try:
                    result = json.loads(cached_data)
                    items_len = len(result.get('items', [])) if isinstance(result, dict) else 0
                    source = result.get('source')
                    logger.info(
                        f"⚡ 从缓存获取港股新闻: {code} items={items_len} source={source} days={result.get('days')} limit={result.get('limit')}"
                    )
                    if items_len > 0:
                        return result
                    else:
                        logger.info(f"🧹 The cache is empty or invalid (items=0, source={source}) , Continue to pull: {code}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to parse Hong Kong stock news cache: {e}, Ignore cache and re-fetch {code}")

        # 2. Get data source priority from database
        source_priority = await self._get_source_priority('HK')

        # 3. Try each data source in order of priority
        news_data = None
        data_source = None

        # Data source name mapping
        source_handlers = {
            'yfinance': ('yfinance', self._get_hk_news_from_yfinance),
            'akshare': ('akshare', self._get_hk_news_from_akshare),
            'finnhub': ('finnhub', self._get_hk_news_from_finnhub),
        }

        # Filter valid data sources and remove duplicates
        valid_priority = []
        seen = set()
        for source_name in source_priority:
            source_key = source_name.lower()
            if source_key in source_handlers and source_key not in seen:
                seen.add(source_key)
                valid_priority.append(source_name)

        if not valid_priority:
            logger.warning("⚠️ There is no valid Hong Kong stock news data source configured in the database, and the default order is used.")
            valid_priority = ['yfinance', 'finnhub', 'akshare']
        else:
            # Always use yfinance as fallback data source (if not in database priority)
            if 'yfinance' not in [s.lower() for s in valid_priority]:
                valid_priority.append('yfinance')

        logger.info(f"📊 [HK Effective data source for news] {valid_priority}")

        for source_name in valid_priority:
            source_key = source_name.lower()
            handler_name, handler_func = source_handlers[source_key]
            try:
                # 🔥 Use asyncio.to_thread to avoid blocking the event loop
                import asyncio
                news_data = await asyncio.to_thread(handler_func, code, days, limit)
                data_source = handler_name

                if news_data:
                    logger.info(f"✅ {data_source}获取港股新闻成功: {code}, 返回 {len(news_data)} 条")
                    break
            except Exception as e:
                logger.warning(f"⚠️ {source_name}获取新闻失败: {e}")
                continue

        if not news_data:
            logger.warning(f"⚠️ 无法获取港股{code}的新闻数据：所有数据源均失败")
            news_data = []
            data_source = 'none'

        # 4. Build return data
        result = {
            'code': code,
            'days': days,
            'limit': limit,
            'source': data_source,
            'items': news_data
        }

        # 5. Cache data (only non-empty results are cached)
        if len(news_data) > 0:
            self.cache.save_stock_data(
                symbol=code,
                data=json.dumps(result, ensure_ascii=False),
                data_source=cache_key_str
            )
        else:
            logger.info(f"🗃️ 不缓存空新闻结果: {code} source={data_source} items=0")

        return result

    async def get_us_news(self, code: str, days: int = 2, limit: int = 50) -> Dict:
        """
        Get US stock news

        Args:
            code: Stock code
            days: Lookback days
            limit: Return quantity limit

        Returns:
            Dictionary containing news lists and data sources
        """
        from datetime import datetime, timedelta

        logger.info(f"📰 开始获取美股新闻: {code}, days={days}, limit={limit}")

        # 1. Try to get from cache
        cache_key_str = f"us_news_{days}_{limit}"
        cache_key = self.cache.find_cached_stock_data(
            symbol=code,
            data_source=cache_key_str
        )

        if cache_key:
            cached_data = self.cache.load_stock_data(cache_key)
            if cached_data:
                try:
                    result = json.loads(cached_data)
                    items = result.get('items', []) if isinstance(result, dict) else []
                    valid_count = 0
                    for it in items:
                        try:
                            if it.get('title') and it.get('url'):
                                valid_count += 1
                        except Exception:
                            continue
                    logger.info(f"⚡ 从缓存获取美股新闻: {code} items={len(items)} valid_items={valid_count} source={result.get('source')}")
                    if valid_count > 0:
                        return result
                    else:
                        logger.info(f"🧹 The cache is empty or invalid (valid_items=0) , Continue to pull: {code}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to parse US stock news cache: {e}, Ignore cache and re-fetch {code}")

        # 2. Get data source priority from database
        source_priority = await self._get_source_priority('US')

        # 3. Try each data source in order of priority
        news_data = None
        data_source = None

        # Data source name mapping (added yfinance as news source)
        source_handlers = {
            'yfinance': ('yfinance', self._get_us_news_from_yfinance),
            'alpha_vantage': ('alpha_vantage', self._get_us_news_from_alpha_vantage),
            'finnhub': ('finnhub', self._get_us_news_from_finnhub),
        }

        # Filter valid data sources and remove duplicates
        valid_priority = []
        seen = set()
        for source_name in source_priority:
            source_key = source_name.lower()
            if source_key in source_handlers and source_key not in seen:
                seen.add(source_key)
                valid_priority.append(source_name)

        if not valid_priority:
            logger.warning("⚠️ There is no valid US stock news data source configured in the database, and the default order is used.")
            valid_priority = ['alpha_vantage', 'finnhub']
        else:
            # Always use yfinance as fallback data source (if not in database priority)
            if 'yfinance' not in [s.lower() for s in valid_priority]:
                valid_priority.append('yfinance')

        logger.info(f"📊 [US Effective data source for news] {valid_priority}")

        for source_name in valid_priority:
            source_key = source_name.lower()
            handler_name, handler_func = source_handlers[source_key]
            try:
                # 🔥 Use asyncio.to_thread to avoid blocking the event loop
                import asyncio
                news_data = await asyncio.to_thread(handler_func, code, days, limit)
                data_source = handler_name

                if news_data:
                    logger.info(f"✅ {data_source}获取美股新闻成功: {code}, 返回 {len(news_data)} 条")
                    break
            except Exception as e:
                logger.warning(f"⚠️ {source_name}获取新闻失败: {e}")
                continue

        if not news_data:
            logger.warning(f"⚠️ 无法获取美股{code}的新闻数据：所有数据源均失败")
            news_data = []
            data_source = 'none'

        # 4. Build return data
        result = {
            'code': code,
            'days': days,
            'limit': limit,
            'source': data_source,
            'items': news_data
        }

        # 5. Cache data (only cache non-empty and valid results)
        valid_count = 0
        for it in news_data:
            try:
                if it.get('title') and it.get('url'):
                    valid_count += 1
            except Exception:
                continue

        if valid_count > 0:
            self.cache.save_stock_data(
                symbol=code,
                data=json.dumps(result, ensure_ascii=False),
                data_source=cache_key_str
            )
        else:
            logger.info(f"🗃️ Do not cache empty or invalid news results: {code} source={data_source} items={len(news_data)} valid_items={valid_count}")

        return result

    def _get_us_news_from_yfinance(self, code: str, days: int, limit: int) -> List[Dict]:
        """Get US stock news from yfinance"""
        from datetime import datetime, timedelta

        ticker = yf.Ticker(code)
        raw_news = getattr(ticker, 'news', None) or []

        if not raw_news:
            raise Exception("无数据")

        cutoff_ts = (datetime.now() - timedelta(days=days)).timestamp()
        items: List[Dict] = []
        seen_urls = set()

        for item in raw_news:
            try:
                # Compatible with a variety of field naming
                title = item.get('title') or item.get('headline') or (
                    item.get('content', {}) or {}
                ).get('title') or ''

                url = item.get('link') or item.get('url') or (
                    (item.get('content', {}) or {}).get('clickThroughUrl', {}) or {}
                ).get('url') or ''

                publisher = item.get('publisher') or item.get('source') or (
                    item.get('content', {}) or {}
                ).get('publisher') or ''

                pub_ts = item.get('providerPublishTime') or item.get('published') or (
                    item.get('content', {}) or {}
                ).get('providerPublishTime')

                # Handling millisecond timestamps
                if isinstance(pub_ts, (int, float)) and pub_ts > 10**12:
                    pub_ts = pub_ts / 1000.0

                # Time filtering (if timestamp exists)
                if pub_ts and float(pub_ts) < cutoff_ts:
                    continue

                # Skip obviously invalid items
                if not title or not url:
                    continue

                if url in seen_urls:
                    continue
                seen_urls.add(url)

                summary = item.get('summary') or (
                    item.get('content', {}) or {}
                ).get('summary')

                items.append({
                    'title': title,
                    'summary': summary,
                    'url': url,
                    'source': publisher,
                    'publish_time': datetime.fromtimestamp(pub_ts).strftime('%Y-%m-%d %H:%M:%S') if pub_ts else '',
                    'sentiment': None,
                    'sentiment_score': None,
                })

                if len(items) >= limit:
                    break
            except Exception:
                # A single parsing exception does not affect the overall
                continue

        if not items:
            raise Exception("无数据")

        # Descending by time (if available)
        try:
            items.sort(key=lambda x: x.get('publish_time', ''), reverse=True)
        except Exception:
            pass

        return items

    def _get_us_news_from_alpha_vantage(self, code: str, days: int, limit: int) -> List[Dict]:
        """Get U.S. stock news from Alpha Vantage"""
        from tradingagents.dataflows.providers.us.alpha_vantage_common import get_api_key, _make_api_request
        from datetime import datetime, timedelta

        # get API Key
        api_key = get_api_key()
        if not api_key:
            raise Exception("Alpha Vantage API Key Not configured")

        # Calculation time range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # call NEWS_SENTIMENT API
        params = {
            "tickers": code.upper(),
            "time_from": start_date.strftime('%Y%m%dT%H%M'),
            "time_to": end_date.strftime('%Y%m%dT%H%M'),
            "sort": "LATEST",
            "limit": str(limit),
        }

        data = _make_api_request("NEWS_SENTIMENT", params)

        if not data or 'feed' not in data:
            raise Exception("无数据")

        # Format news data
        news_list = []
        for article in data.get('feed', [])[:limit]:
            # parsing time
            time_published = article.get('time_published', '')
            try:
                # Alpha Vantage time format: 20240101T120000
                pub_time = datetime.strptime(time_published, '%Y%m%dT%H%M%S')
                pub_time_str = pub_time.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pub_time_str = time_published

            # Extract sentiment scores for related stocks
            sentiment_score = None
            sentiment_label = article.get('overall_sentiment_label', 'Neutral')

            ticker_sentiment = article.get('ticker_sentiment', [])
            for ts in ticker_sentiment:
                if ts.get('ticker', '').upper() == code.upper():
                    sentiment_score = ts.get('ticker_sentiment_score')
                    sentiment_label = ts.get('ticker_sentiment_label', sentiment_label)
                    break

            news_list.append({
                'title': article.get('title', ''),
                'summary': article.get('summary', ''),
                'url': article.get('url', ''),
                'source': article.get('source', ''),
                'publish_time': pub_time_str,
                'sentiment': sentiment_label,
                'sentiment_score': sentiment_score,
            })

        return news_list

    def _get_us_news_from_finnhub(self, code: str, days: int, limit: int) -> List[Dict]:
        """Get US stock news from Finnhub"""
        import finnhub
        import os
        from datetime import datetime, timedelta

        # get API Key
        api_key = os.getenv('FINNHUB_API_KEY')
        if not api_key:
            raise Exception("Finnhub API Key Not configured")

        # Create client
        client = finnhub.Client(api_key=api_key)

        # Calculation time range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Get company news
        news = client.company_news(
            code.upper(),
            _from=start_date.strftime('%Y-%m-%d'),
            to=end_date.strftime('%Y-%m-%d')
        )

        if not news:
            raise Exception("无数据")

        # Format news data
        news_list = []
        for article in news[:limit]:
            # parse timestamp
            timestamp = article.get('datetime', 0)
            pub_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

            news_list.append({
                'title': article.get('headline', ''),
                'summary': article.get('summary', ''),
                'url': article.get('url', ''),
                'source': article.get('source', ''),
                'publish_time': pub_time,
                'sentiment': None,  # Finnhub No sentiment analysis provided
                'sentiment_score': None,
            })

        return news_list

    def _get_hk_news_from_finnhub(self, code: str, days: int, limit: int) -> List[Dict]:
        """Get Hong Kong stock news from Finnhub"""
        import finnhub
        import os
        from datetime import datetime, timedelta

        # get API Key
        api_key = os.getenv('FINNHUB_API_KEY')
        if not api_key:
            raise Exception("Finnhub API Key Not configured")

        # Create client
        client = finnhub.Client(api_key=api_key)

        # Calculation time range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Standardize the Hong Kong stock code to the format expected by Yahoo/Finnhub
        hk_symbol = self.hk_provider._normalize_hk_symbol(code)

        # Get company news
        news = client.company_news(
            hk_symbol,
            _from=start_date.strftime('%Y-%m-%d'),
            to=end_date.strftime('%Y-%m-%d')
        )

        if not news:
            raise Exception("无数据")

        # Format news data
        news_list = []
        for article in news[:limit]:
            # parse timestamp
            timestamp = article.get('datetime', 0)
            pub_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

            news_list.append({
                'title': article.get('headline', ''),
                'summary': article.get('summary', ''),
                'url': article.get('url', ''),
                'source': article.get('source', ''),
                'publish_time': pub_time,
                'sentiment': None,  # Finnhub No sentiment analysis provided
                'sentiment_score': None,
            })

        return news_list

    def _get_hk_news_from_yfinance(self, code: str, days: int, limit: int) -> List[Dict]:
        """Get Hong Kong stock news from Yahoo Finance"""
        from datetime import datetime, timedelta
        import os

        # Normalized to Yahoo Expected format: 4 digits + .HK
        normalized_symbol = self.hk_provider._normalize_hk_symbol(code)
        # Note: The new version of yfinance relies on the internal curl_cffi session, and an error will be reported if requests.Session is passed in.
        # Therefore, the self-built session is no longer passed in here, and the proxy takes effect through the environment variable HTTP_PROXY/HTTPS_PROXY.
        ticker = yf.Ticker(normalized_symbol)

        articles = getattr(ticker, 'news', [])
        raw_count = len(articles) if isinstance(articles, list) else 0
        logger.info(f"🧾 yfinance Number of original news items: {raw_count} symbol={normalized_symbol}")
        # Record the source of the agent to facilitate troubleshooting
        try:
            env_http = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
            env_https = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
            logger.info(
                f"🌐 Yahoo Finance Use environmental agents: http={env_http} https={env_https}"
            )
        except Exception:
            pass

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        def _to_datetime(a):
            """Compatible with the latest news structure of yfinance, priority is given to providerPublishTime or content.pubDate"""
            content = a.get('content') or {}
            ts = a.get('providerPublishTime')
            if isinstance(ts, (int, float)) and ts > 0:
                try:
                    return datetime.fromtimestamp(ts)
                except Exception:
                    pass
            pub = (
                a.get('pubDate')
                or a.get('published')
                or content.get('pubDate')
                or content.get('published')
            )
            if isinstance(pub, str) and pub:
                for fmt in ('%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d %H:%M:%S'):
                    try:
                        return datetime.strptime(pub, fmt)
                    except Exception:
                        continue
            return None

        filtered = []
        invalid_ts = 0
        out_of_range = 0
        # Print the first 3 original examples to facilitate troubleshooting field differences
        try:
            for i, a in enumerate(articles[:3], 1):
                content = a.get('content') or {}
                title = a.get('title') or content.get('title', '')
                provider = a.get('publisher') or (content.get('provider') or {}).get('displayName')
                ts = a.get('providerPublishTime') or a.get('pubDate') or content.get('pubDate')
                logger.info(f"🔎 原始示例[{i}] title={title} provider={provider} ts={ts} keys={list(a.keys())}")
        except Exception:
            pass
        for a in articles:
            dt = _to_datetime(a)
            if dt is None:
                invalid_ts += 1
                continue
            if dt < start_date or dt > end_date:
                out_of_range += 1
                continue
            filtered.append((dt, a))
        logger.info(
            f"📏 过滤统计: 保留={len(filtered)} 无时间戳={invalid_ts} 超范围={out_of_range} 窗口={start_date.isoformat()}~{end_date.isoformat()}"
        )

        filtered.sort(key=lambda x: x[0], reverse=True)

        news_list: List[Dict] = []
        for dt, a in filtered[:limit]:
            content = a.get('content') or {}
            # Compatible with old and new fields
            title = a.get('title') or content.get('title', '')
            summary = (
                a.get('summary')
                or content.get('summary')
                or content.get('description')
                or ''
            )
            url = (
                a.get('link')
                or content.get('url')
                or content.get('clickThroughUrl')
                or ''
            )
            provider = a.get('publisher')
            if not provider:
                prov = content.get('provider') or {}
                provider = prov.get('displayName') or prov.get('name') or ''

            news_list.append({
                'title': title,
                'summary': summary,
                'url': url,
                'source': provider,
                'publish_time': dt.strftime('%Y-%m-%d %H:%M:%S'),
                'sentiment': None,
                'sentiment_score': None,
            })

        if not news_list:
            raise Exception("无数据")
        return news_list

    def _get_hk_info_from_akshare(self, code: str) -> Dict:
        """Obtain basic information and financial indicators of Hong Kong stocks from AKShare"""
        from tradingagents.dataflows.providers.hk.improved_hk import (
            get_hk_stock_info_akshare,
            get_hk_financial_indicators
        )

        # 1. Get basic information (including current prices)
        info = get_hk_stock_info_akshare(code)
        if not info or 'error' in info:
            raise Exception("无数据")

        # 2. Get financial indicators (EPS, BPS, ROE, debt ratio, etc.)
        financial_indicators = {}
        try:
            financial_indicators = get_hk_financial_indicators(code)
            logger.info(f"✅ 获取港股{code}财务指标成功: {list(financial_indicators.keys())}")
        except Exception as e:
            logger.warning(f"⚠️ 获取港股{code}财务指标失败: {e}")

        # 3. Calculate PE, PB, PS (refer to the calculation method of the analysis module)
        current_price = info.get('price')  # current price
        pe_ratio = None
        pb_ratio = None
        ps_ratio = None

        if current_price and financial_indicators:
            # Calculate PE = current price / EPS_TTM
            eps_ttm = financial_indicators.get('eps_ttm')
            if eps_ttm and eps_ttm > 0:
                pe_ratio = current_price / eps_ttm
                logger.info(f"📊 计算 PE: {current_price} / {eps_ttm} = {pe_ratio:.2f}")

            # Calculate PB = current price / BPS
            bps = financial_indicators.get('bps')
            if bps and bps > 0:
                pb_ratio = current_price / bps
                logger.info(f"📊 计算 PB: {current_price} / {bps} = {pb_ratio:.2f}")

            # Calculate PS = Market capitalization/operating income (market capitalization data is required and cannot be calculated at the moment)
            # ps_ratio For the time being None

        # 4. Merge data
        return {
            'name': info.get('name', f'港股{code}'),
            'market_cap': None,  # AKShare Basic information does not include market value
            'industry': None,
            'sector': None,
            # 🔥 Calculated valuation metric
            'pe_ratio': pe_ratio,
            'pb_ratio': pb_ratio,
            'ps_ratio': ps_ratio,
            'dividend_yield': None,
            'currency': 'HKD',
            # 🔥 Obtained from financial indicators
            'roe': financial_indicators.get('roe_avg'),  # average return on equity
            'debt_ratio': financial_indicators.get('debt_asset_ratio'),  # Asset-liability ratio
        }

    def _get_hk_info_from_yfinance(self, code: str) -> Dict:
        """Get basic information on Hong Kong stocks from Yahoo Finance"""

        # yfinance Internally uses curl_cffi session; proxy takes effect through environment variables
        ticker = yf.Ticker(f"{code}.HK")
        info = ticker.info

        return {
            'name': info.get('longName') or info.get('shortName') or f'港股{code}',
            'market_cap': info.get('marketCap'),
            'industry': info.get('industry'),
            'sector': info.get('sector'),
            'pe_ratio': info.get('trailingPE'),
            'pb_ratio': info.get('priceToBook'),
            'dividend_yield': info.get('dividendYield'),
            'currency': info.get('currency', 'HKD'),
        }

    def _get_hk_info_from_finnhub(self, code: str) -> Dict:
        """Get basic information on Hong Kong stocks from Finnhub"""
        import finnhub
        import os

        # get API Key
        api_key = os.getenv('FINNHUB_API_KEY')
        if not api_key:
            raise Exception("Finnhub API Key Not configured")

        # Create client
        client = finnhub.Client(api_key=api_key)

        # Hong Kong stock codes need to add the .HK suffix
        hk_symbol = f"{code}.HK" if not code.endswith('.HK') else code

        # Get basic company information
        profile = client.company_profile2(symbol=hk_symbol)

        if not profile:
            raise Exception("无数据")

        return {
            'name': profile.get('name', f'港股{code}'),
            'market_cap': profile.get('marketCapitalization') * 1e6 if profile.get('marketCapitalization') else None,  # Finnhub Returns millions of units
            'industry': profile.get('finnhubIndustry'),
            'sector': None,
            'pe_ratio': None,
            'pb_ratio': None,
            'dividend_yield': None,
            'currency': profile.get('currency', 'HKD'),
        }

    def _get_hk_kline_from_akshare(self, code: str, period: str, limit: int) -> List[Dict]:
        """Get Hong Kong stock K-line data from AKShare"""
        import akshare as ak
        import pandas as pd
        from datetime import datetime, timedelta
        from tradingagents.dataflows.providers.hk.improved_hk import get_improved_hk_provider

        # standardized code
        provider = get_improved_hk_provider()
        normalized_code = provider._normalize_hk_symbol(code)

        # Use directly AKShare API
        df = ak.stock_hk_daily(symbol=normalized_code, adjust="qfq")

        if df is None or df.empty:
            raise Exception("无数据")

        # Filter recent data
        df = df.tail(limit)

        # Format data
        kline_data = []
        for _, row in df.iterrows():
            # AKShare Returned column names:date, open, close, high, low, volume
            date_str = row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])
            kline_data.append({
                'date': date_str,
                'trade_date': date_str,
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': int(row['volume']) if 'volume' in row else 0
            })

        return kline_data

    def _get_hk_kline_from_yfinance(self, code: str, period: str, limit: int) -> List[Dict]:
        """Obtain Hong Kong stock K-line data from Yahoo Finance"""
        import yfinance as yf
        import pandas as pd

        # yfinance Internally uses curl_cffi session; proxy takes effect through environment variables
        ticker = yf.Ticker(f"{code}.HK")

        # period mapping
        period_map = {
            'day': '1d',
            'week': '1wk',
            'month': '1mo',
            '5m': '5m',
            '15m': '15m',
            '30m': '30m',
            '60m': '60m'
        }

        interval = period_map.get(period, '1d')
        hist = ticker.history(period=f'{limit}d', interval=interval)

        if hist.empty:
            raise Exception("无数据")

        # Format data
        kline_data = []
        for date, row in hist.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            kline_data.append({
                'date': date_str,
                'trade_date': date_str,
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row['Volume'])
            })

        return kline_data[-limit:]  # Return the last limit item

    def _get_hk_kline_from_finnhub(self, code: str, period: str, limit: int) -> List[Dict]:
        """Obtain Hong Kong stock K-line data from Finnhub"""
        import finnhub
        import os
        from datetime import datetime, timedelta

        # get API Key
        api_key = os.getenv('FINNHUB_API_KEY')
        if not api_key:
            raise Exception("Finnhub API Key Not configured")

        # Create client
        client = finnhub.Client(api_key=api_key)

        # Hong Kong stock codes need to add the .HK suffix
        hk_symbol = f"{code}.HK" if not code.endswith('.HK') else code

        # period mapping
        resolution_map = {
            'day': 'D',
            'week': 'W',
            'month': 'M',
            '5m': '5',
            '15m': '15',
            '30m': '30',
            '60m': '60'
        }

        resolution = resolution_map.get(period, 'D')

        # Calculation time range
        end_time = int(datetime.now().timestamp())
        start_time = int((datetime.now() - timedelta(days=limit * 2)).timestamp())

        # Get K-line data
        candles = client.stock_candles(hk_symbol, resolution, start_time, end_time)

        if not candles or candles.get('s') != 'ok':
            raise Exception("无数据")

        # Format data
        kline_data = []
        for i in range(len(candles['t'])):
            date_str = datetime.fromtimestamp(candles['t'][i]).strftime('%Y-%m-%d')
            kline_data.append({
                'date': date_str,
                'trade_date': date_str,
                'open': float(candles['o'][i]),
                'high': float(candles['h'][i]),
                'low': float(candles['l'][i]),
                'close': float(candles['c'][i]),
                'volume': int(candles['v'][i])
            })

        return kline_data[-limit:]  # Return the last limit item

    def _get_hk_news_from_akshare(self, code: str, days: int, limit: int) -> List[Dict]:
        """Get Hong Kong stock news from AKShare"""
        try:
            import akshare as ak
            from datetime import datetime, timedelta

            # AKShare Hong Kong stock news interface
            # Note: AKShare may not have a dedicated Hong Kong stock news interface. Here we use the general news interface.
            # If there is no suitable interface, throw an exception and let the system try the next data source.

            # Try to get Hong Kong stock news (use Oriental Fortune Hong Kong stock news)
            try:
                df = ak.stock_news_em(symbol=code)
                if df is None or df.empty:
                    raise Exception("无数据")

                # Format news data
                news_list = []
                for _, row in df.head(limit).iterrows():
                    pub_time = row['发布时间'] if '发布时间' in row else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    news_list.append({
                        'title': row['新闻标题'] if '新闻标题' in row else '',
                        'summary': row['新闻内容'] if '新闻内容' in row else '',
                        'url': row['新闻链接'] if '新闻链接' in row else '',
                        'source': 'AKShare-东方财富',
                        'publish_time': pub_time,
                        'sentiment': None,
                        'sentiment_score': None,
                    })

                return news_list
            except Exception as e:
                logger.debug(f"AKShare Oriental wealth interface failed: {e}")
                raise Exception("AKShare Hong Kong stock news is not supported at the moment")

        except Exception as e:
            logger.warning(f"⚠️ AKShare Failed to obtain Hong Kong stock news: {e}")
            raise


# === historical_data_service.py ===
#!/usr/bin/env python3
"""
Unified historical data management service
Provide a unified historical data storage and query interface for three data sources
"""
import asyncio
import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Union
import pandas as pd
try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = AsyncIOMotorDatabase = AsyncIOMotorCollection = object

from app.core.database import get_database

logger = logging.getLogger(__name__)


class HistoricalDataService:
    """统一历史数据管理服务"""
    
    def __init__(self):
        """初始化服务"""
        self.db = None
        self.collection = None
        
    async def initialize(self):
        """初始化数据库连接"""
        try:
            # 🔥 If db already exists (possibly set externally), it will not be re-created
            # 🔥 This can avoid being re-created after replacing the connection in UnifiedThreadPoolSyncService
            if self.db is None:
                self.db = get_database()
            
            # 🔥 Set collection if it is not already set
            if self.collection is None:
                self.collection = self.db.stock_daily_quotes

            # 🔥 Make sure the index exists (improves query and upsert performance)
            await self._ensure_indexes()

            logger.info("✅ Historical data service initialization successful")
        except Exception as e:
            logger.error(f"❌ Historical data service initialization failed: {e}")
            raise

    async def _ensure_indexes(self):
        """确保必要的索引存在"""
        try:
            # 🔥 Key fix: Re-fetch collection from self.db, make sure to use correct connection
            if self.db is None:
                await self.initialize()
            collection = self.db.stock_daily_quotes
            
            logger.info("📊 Check and create historical data index...")

            # 1. Composite unique index: ticker symbol+transaction date+data source+period (for upsert)
            await collection.create_index([
                ("symbol", 1),
                ("trade_date", 1),
                ("data_source", 1),
                ("period", 1)
            ], unique=True, name="symbol_date_source_period_unique", background=True)

            # 2. Stock code index (query historical data of a single stock)
            await collection.create_index([("symbol", 1)], name="symbol_index", background=True)

            # 3. Transaction date index (query by date range)
            await collection.create_index([("trade_date", -1)], name="trade_date_index", background=True)

            # 4. Composite Index: Stock Symbol+Transaction date (common inquiries)
            await collection.create_index([
                ("symbol", 1),
                ("trade_date", -1)
            ], name="symbol_date_index", background=True)

            logger.info("✅ 历史数据索引检查完成")
        except Exception as e:
            # Index creation failure should not prevent the service from starting
            logger.warning(f"⚠️ Warning when creating index (may already exist): {e}")
    
    async def save_historical_data(
        self,
        symbol: str,
        data: pd.DataFrame,
        data_source: str,
        market: str = "CN",
        period: str = "daily",
        overwrite: bool = True
    ) -> int:
        """
        Save historical data to database

        Args:
            symbol: Stock code
            data: historical data DataFrame
            data_source: data source (tushare/akshare/baostock/local)
            market: market type (CN/HK/US)
            period: data period (daily/weekly/monthly)
            overwrite: Whether to overwrite existing data (default True, maintain backward compatibility)

        Returns:
            Number of records saved
        """
        # 🔥 Critical fix: reacquire database connection on every use, ensure correct event loop is used
        # 🔥 This avoids event loop conflicts when asyncio.gather is executed in parallel
        from app.core.database import get_mongo_db
        self.db = get_mongo_db()
        
        # 🔥 Critical fix: re-fetch from self.db on every use collection
        # 🔥 This ensures that the latest db connection is used (bound to the correct event loop)
        collection = self.db.stock_daily_quotes
        
        try:
            if data is None or data.empty:
                logger.warning(f"⚠️ {symbol} Historical data is empty, skip saving")
                return 0

            from datetime import datetime
            total_start = datetime.now()

            logger.info(f"💾 开始保存 {symbol} 历史数据: {len(data)}条记录 (数据源: {data_source})")

            # ⏱️ Performance Monitoring: Unit Conversion
            convert_start = datetime.now()
            # 🔥 Do unit conversion at the DataFrame level (vectorization operation, much faster than row-by-row)
            if data_source == "tushare":
                # Turnover: thousand yuan -> Yuan
                if 'amount' in data.columns:
                    data['amount'] = data['amount'] * 1000
                elif 'turnover' in data.columns:
                    data['turnover'] = data['turnover'] * 1000

                # Volume: Lots -> shares
                if 'volume' in data.columns:
                    data['volume'] = data['volume'] * 100
                elif 'vol' in data.columns:
                    data['vol'] = data['vol'] * 100

            # 🔥 Hong Kong stock/US stock data: Add pre_close field (obtained from the previous day's close)
            if market in ["HK", "US"] and 'pre_close' not in data.columns and 'close' in data.columns:
                # Use shift(1) Move the close column down one row to get the previous day's closing price
                data['pre_close'] = data['close'].shift(1)
                logger.debug(f"✅ {symbol} Add pre_close field (taken from previous day s close)")

            convert_duration = (datetime.now() - convert_start).total_seconds()

            # ⏱️ Performance Monitoring: Building Action Lists
            prepare_start = datetime.now()
            # Prepare for batch operations
            operations = []
            saved_count = 0
            batch_size = 200  # Further reduce batch size to avoid timeouts (from 500 to 200)

            # 🔥 Reduce log output: only print progress when processing large amounts of data
            processed_count = 0

            for date_index, row in data.iterrows():
                processed_count += 1
                try:
                    # Normalize data (pass date index)
                    doc = self._standardize_record(symbol, row, data_source, market, period, date_index)

                    # Determine the operation type based on the overwrite parameter
                    filter_doc = {
                        "symbol": doc["symbol"],
                        "trade_date": doc["trade_date"],
                        "data_source": doc["data_source"],
                        "period": doc["period"]
                    }

                    from pymongo import ReplaceOne, UpdateOne
                    if overwrite:
                        # Override mode: use ReplaceOne with upsert
                        operations.append(ReplaceOne(
                            filter=filter_doc,
                            replacement=doc,
                            upsert=True
                        ))
                    else:
                        # No overwrite mode: use UpdateOne with setOnInsert (only insert if not present)
                        operations.append(UpdateOne(
                            filter=filter_doc,
                            update={"$setOnInsert": doc},
                            upsert=True
                        ))

                    # Batch execution (every 200 items)
                    if len(operations) >= batch_size:
                        batch_saved = await self._execute_bulk_write_with_retry(symbol, operations)
                        saved_count += batch_saved
                        operations = []

                except Exception as e:
                    # Get date information for error logs
                    date_str = str(date_index) if hasattr(date_index, '__str__') else 'unknown'
                    logger.error(f"❌ 处理记录失败 {symbol} {date_str}: {e}")
                    continue

            # Perform remaining operations
            if operations:
                final_batch_saved = await self._execute_bulk_write_with_retry(
                    symbol, operations
                )
                saved_count += final_batch_saved

            total_duration = (datetime.now() - total_start).total_seconds()
            logger.info(f"✅ {symbol} 历史数据保存完成: {saved_count}条记录，耗时 {total_duration:.2f}秒")
            return saved_count
            
        except Exception as e:
            logger.error(f"❌ 保存历史数据失败 {symbol}: {e}")
            return 0

    async def _execute_bulk_write_with_retry(
        self,
        symbol: str,
        operations: List,
        max_retries: int = 5  # Increase the number of retries: from 3 to 5
    ) -> int:
        """
        Perform batch writes with retry mechanism

        Args:
            symbol: Stock code
            operations: Bulk operation list
            max_retries: Maximum number of retries

        Returns:
            Number of records successfully saved
        """
        saved_count = 0
        retry_count = 0

        while retry_count < max_retries:
            try:
                # 🔥 Detect whether running in the thread pool (by checking the current event loop)
                import threading
                current_thread = threading.current_thread()
                is_in_thread_pool = not isinstance(current_thread, threading._MainThread)

                if is_in_thread_pool:
                    # 🔥 In a thread pool: Using a synchronous MongoDB client
                    from app.core.database import get_mongo_db_sync
                    sync_db = get_mongo_db_sync()
                    sync_collection = sync_db.stock_daily_quotes
                    result = sync_collection.bulk_write(operations, ordered=False)
                else:
                    # 🔥 In the main thread: Using an asynchronous MongoDB client
                    # 🔥 Key fix: Re-fetch collection from self.db on every use, make sure to use correct connection
                    if self.db is None:
                        await self.initialize()
                    collection = self.db.stock_daily_quotes
                    result = await collection.bulk_write(operations, ordered=False)
                saved_count = result.upserted_count + result.modified_count
                # 🔥 Reduce logging: only print details if there are errors or retries
                return saved_count

            except asyncio.TimeoutError as e:
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = 3 ** retry_count  # Longer exponential backoff: 3 seconds, 9 seconds, 27 seconds, 81 seconds
                    logger.warning(f"⚠️ {symbol} 批量写入超时 (第{retry_count}/{max_retries}次重试)，等待{wait_time}秒后重试...")
                    # 🔥 Choose the sleep mode according to the operating environment
                    if is_in_thread_pool:
                        import time
                        time.sleep(wait_time)
                    else:
                        await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ {symbol} 批量写入失败，已重试{max_retries}次: {e}")
                    return 0

            except Exception as e:
                # Check if it is a timeout related error
                error_msg = str(e).lower()
                if 'timeout' in error_msg or 'timed out' in error_msg:
                    retry_count += 1
                    if retry_count < max_retries:
                        wait_time = 3 ** retry_count
                        logger.warning(f"⚠️ {symbol} 批量写入超时 (第{retry_count}/{max_retries}次重试)，等待{wait_time}秒后重试... 错误: {e}")
                        # 🔥 Choose the sleep mode according to the operating environment
                        if is_in_thread_pool:
                            import time
                            time.sleep(wait_time)
                        else:
                            await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"❌ {symbol} 批量写入失败，已重试{max_retries}次: {e}")
                        return 0
                else:
                    logger.error(f"❌ {symbol} 批量写入失败: {e}")
                    return 0

        return saved_count

    def _standardize_record(
        self,
        symbol: str,
        row: pd.Series,
        data_source: str,
        market: str,
        period: str = "daily",
        date_index = None
    ) -> Dict[str, Any]:
        """标准化单条记录"""
        now = datetime.utcnow()

        # Get the date - first get it from the column, only use the index if the index is of date type
        trade_date = None

        # First try to get the date from the column
        date_from_column = row.get('date') or row.get('trade_date')

        # If there is a date in the column, the date in the column is used first
        if date_from_column is not None:
            trade_date = self._format_date(date_from_column)
        # Only use the index if there is no date in the column and the index is a date/time/date string
        # Note: The DataFrame index passed in by batch-import is in the form "20240101" string, explicit support is required here str
        elif date_index is not None and isinstance(date_index, (date, datetime, pd.Timestamp, str)):
            trade_date = self._format_date(date_index)
        # Otherwise use the current date
        else:
            trade_date = self._format_date(None)

        # Basic field mapping
        doc = {
            "symbol": symbol,
            "code": symbol,  # Add code field to be consistent with symbol (backwards compatible)
            "full_symbol": self._get_full_symbol(symbol, market),
            "market": market,
            "trade_date": trade_date,
            "period": period,
            "data_source": data_source,
            "created_at": now,
            "updated_at": now,
            "version": 1
        }
        
        # OHLCV Data (unit conversion is done at the DataFrame level)
        amount_value = self._safe_float(row.get('amount') or row.get('turnover'))
        volume_value = self._safe_float(row.get('volume') or row.get('vol'))

        doc.update({
            "open": self._safe_float(row.get('open')),
            "high": self._safe_float(row.get('high')),
            "low": self._safe_float(row.get('low')),
            "close": self._safe_float(row.get('close')),
            "pre_close": self._safe_float(row.get('pre_close') or row.get('preclose')),
            "volume": volume_value,
            "amount": amount_value
        })
        
        # Calculate rise and fall data
        if doc["close"] and doc["pre_close"]:
            doc["change"] = round(doc["close"] - doc["pre_close"], 4)
            doc["pct_chg"] = round((doc["change"] / doc["pre_close"]) * 100, 4)
        else:
            doc["change"] = self._safe_float(row.get('change'))
            doc["pct_chg"] = self._safe_float(row.get('pct_chg') or row.get('change_percent'))
        
        # optional fields
        optional_fields = {
            "turnover_rate": row.get('turnover_rate') or row.get('turn'),
            "volume_ratio": row.get('volume_ratio'),
            "pe": row.get('pe'),
            "pb": row.get('pb'),
            "ps": row.get('ps'),
            "adjustflag": row.get('adjustflag') or row.get('adj_factor'),
            "tradestatus": row.get('tradestatus'),
            "isST": row.get('isST')
        }
        
        for key, value in optional_fields.items():
            if value is not None:
                doc[key] = self._safe_float(value)
        
        return doc
    
    def _get_full_symbol(self, symbol: str, market: str) -> str:
        """生成完整股票代码"""
        if market == "CN":
            if symbol.startswith('6'):
                return f"{symbol}.SH"
            elif symbol.startswith(('0', '3')):
                return f"{symbol}.SZ"
            else:
                return f"{symbol}.SZ"  # Default Shenzhen
        elif market == "HK":
            return f"{symbol}.HK"
        elif market == "US":
            return symbol
        else:
            return symbol
    
    def _format_date(self, date_value) -> str:
        """格式化日期"""
        if date_value is None:
            return datetime.now().strftime('%Y-%m-%d')

        if isinstance(date_value, str):
            # 🔥 Process "20160704 00:00:00" Format (index format passed in by batch-import)
            if ' ' in date_value:
                date_value = date_value.split(' ')[0]  # Get only the date part

            # Handle different date formats
            if len(date_value) == 8:  # YYYYMMDD
                return f"{date_value[:4]}-{date_value[4:6]}-{date_value[6:8]}"
            elif len(date_value) == 10:  # YYYY-MM-DD
                return date_value
            else:
                # Try parsing other formats
                try:
                    parsed_date = pd.to_datetime(date_value)
                    return parsed_date.strftime('%Y-%m-%d')
                except Exception:
                    return date_value
        elif isinstance(date_value, (date, datetime)):
            return date_value.strftime('%Y-%m-%d')
        elif isinstance(date_value, pd.Timestamp):
            return date_value.strftime('%Y-%m-%d')
        else:
            return str(date_value)
    
    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None or value == '' or pd.isna(value):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    async def get_historical_data(
        self,
        symbol: str,
        start_date: str = None,
        end_date: str = None,
        data_source: str = None,
        period: str = None,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """
        Query historical data

        Args:
            symbol: Stock code
            start_date: start date (YYYY-MM-DD)
            end_date: end date (YYYY-MM-DD)
            data_source: Data source filtering
            period: Data cycle filtering (daily/weekly/monthly)
            limit: Limit the number of returns

        Returns:
            Historical data list
        """
        # 🔥 Key fix: check self.db instead self.collection
        if self.db is None:
            await self.initialize()
        
        # 🔥 Re-fetch the collection from self.db, making sure to use the correct connection
        collection = self.db.stock_daily_quotes
        
        try:
            # Build query conditions
            query = {"symbol": symbol}
            
            if start_date or end_date:
                date_filter = {}
                if start_date:
                    date_filter["$gte"] = start_date
                if end_date:
                    date_filter["$lte"] = end_date
                query["trade_date"] = date_filter
            
            if data_source:
                query["data_source"] = data_source

            if period:
                query["period"] = period
            
            # Execute query
            cursor = collection.find(query).sort("trade_date", -1)
            
            if limit:
                cursor = cursor.limit(limit)
            
            results = await cursor.to_list(length=None)
            
            logger.info(f"📊 查询历史数据: {symbol} 返回 {len(results)} 条记录")
            return results
            
        except Exception as e:
            logger.error(f"❌ 查询历史数据失败 {symbol}: {e}")
            return []
    
    async def get_latest_date(self, symbol: str, data_source: str) -> Optional[str]:
        """获取最新数据日期"""
        # 🔥 Key fix: check self.db instead self.collection
        if self.db is None:
            await self.initialize()
        
        # 🔥 Re-fetch the collection from self.db, making sure to use the correct connection
        collection = self.db.stock_daily_quotes
        
        try:
            result = await collection.find_one(
                {"symbol": symbol, "data_source": data_source},
                sort=[("trade_date", -1)]
            )
            
            if result:
                return result["trade_date"]
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取最新日期失败 {symbol}: {e}")
            return None
    
    async def get_data_statistics(self) -> Dict[str, Any]:
        """获取数据统计信息"""
        # 🔥 Key fix: check self.db instead self.collection
        if self.db is None:
            await self.initialize()
        
        # 🔥 Re-fetch the collection from self.db, making sure to use the correct connection
        collection = self.db.stock_daily_quotes
        
        try:
            # Total number of records
            total_count = await collection.count_documents({})
            
            # Statistics by data source
            source_stats = await collection.aggregate([
                {"$group": {
                    "_id": "$data_source",
                    "count": {"$sum": 1},
                    "latest_date": {"$max": "$trade_date"}
                }}
            ]).to_list(length=None)
            
            # Statistics by market
            market_stats = await collection.aggregate([
                {"$group": {
                    "_id": "$market",
                    "count": {"$sum": 1}
                }}
            ]).to_list(length=None)
            
            # Stock quantity statistics
            symbol_count = len(await collection.distinct("symbol"))
            
            return {
                "total_records": total_count,
                "total_symbols": symbol_count,
                "by_source": {item["_id"]: {
                    "count": item["count"],
                    "latest_date": item.get("latest_date")
                } for item in source_stats},
                "by_market": {item["_id"]: item["count"] for item in market_stats},
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ 获取统计信息失败: {e}")
            return {}


# Global service instance
_historical_data_service = None


async def get_historical_data_service() -> HistoricalDataService:
    """获取历史数据服务实例"""
    global _historical_data_service
    if _historical_data_service is None:
        _historical_data_service = HistoricalDataService()
        await _historical_data_service.initialize()
    return _historical_data_service

# === financial_data_service.py ===
#!/usr/bin/env python3
"""
Financial data services
Unified management of financial data storage and query from three data sources
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import pandas as pd
try:
    from pymongo import ReplaceOne
except ImportError:
    from unittest.mock import MagicMock as _MM; BulkWriteResult = UpdateOne = InsertOne = DeleteOne = MongoClient = Database = ASCENDING = DESCENDING = ReturnDocument = _MM()
    DuplicateKeyError = PyMongoError = OperationFailure = ServerSelectionTimeoutError = ConnectionFailure = Exception

from app.core.database import get_mongo_db
from core.skill_runtime.data_access import expand_financial_document_to_periods

logger = logging.getLogger(__name__)


class FinancialDataService:
    """财务数据统一管理服务"""
    
    def __init__(self):
        self.collection_name = "stock_financial_data"
        self.period_collection_name = "stock_financial_periods"
        self.db = None
        
    async def initialize(self):
        """初始化服务"""
        try:
            self.db = get_mongo_db()
            if self.db is None:
                raise Exception("MongoDB Database not initialized")

            # 🔥 Make sure the index exists (improves query and upsert performance)
            await self._ensure_indexes()

            logger.info("✅ Financial data service initialization successful")

        except Exception as e:
            logger.error(f"❌ Financial data service initialization failed: {e}")
            raise

    async def _ensure_indexes(self):
        """确保必要的索引存在"""
        snapshot_collection = self.db[self.collection_name]
        period_collection = self.db[self.period_collection_name]

        logger.info("📊 Examine and create indexes for financial data...")

        snapshot_indexes = [
            {
                "keys": [("symbol", 1), ("report_period", 1), ("data_source", 1)],
                "name": "symbol_period_source_unique",
                "unique": True,
            },
            {
                "keys": [("symbol", 1)],
                "name": "symbol_index",
            },
            {
                "keys": [("report_period", -1)],
                "name": "report_period_index",
            },
            {
                "keys": [("symbol", 1), ("report_period", -1)],
                "name": "symbol_period_index",
            },
            {
                "keys": [("report_type", 1)],
                "name": "report_type_index",
            },
            {
                "keys": [("updated_at", -1)],
                "name": "updated_at_index",
            },
        ]
        period_indexes = [
            {
                "keys": [("symbol", 1), ("source", 1), ("report_period", -1), ("ann_date", -1)],
                "name": "symbol_1_source_1_report_period_-1_ann_date_-1",
            },
            {
                "keys": [("code", 1), ("source", 1), ("report_period", -1)],
                "name": "code_1_source_1_report_period_-1",
            },
            {
                "keys": [("symbol", 1), ("report_period", -1)],
                "name": "symbol_1_report_period_-1",
            },
        ]

        for index_spec in snapshot_indexes:
            await self._create_index(snapshot_collection, self.collection_name, index_spec)

        logger.info("📊 Examine and create periodic financial data indexes...")
        for index_spec in period_indexes:
            await self._create_index(period_collection, self.period_collection_name, index_spec)

        logger.info("✅ 财务数据索引检查完成")

    async def _create_index(self, collection, collection_name: str, index_spec: Dict[str, Any]) -> None:
        """Create indexes one by one to avoid blocking other indexes if a single index fails."""
        try:
            await collection.create_index(
                index_spec["keys"],
                name=index_spec["name"],
                background=True,
                unique=index_spec.get("unique", False),
            )
        except Exception as e:
            logger.warning(
                f"⚠️ 创建索引时出现警告 {collection_name}.{index_spec['name']}（可能已存在或存在重复数据）: {e}"
            )
    
    async def save_financial_data(
        self,
        symbol: str,
        financial_data: Dict[str, Any],
        data_source: str,
        market: str = "CN",
        report_period: str = None,
        report_type: str = "quarterly"
    ) -> int:
        """
        Save financial data to database
        
        Args:
            symbol: Stock code
            financial_data: Financial Data Dictionary
            data_source: data source (tushare/akshare/baostock/qmt)
            market: market type (CN/HK/US)
            report_period: reporting period (YYYYMMDD)
            report_type: report type (quarterly/annual)
            
        Returns:
            Number of records saved
        """
        if self.db is None:
            await self.initialize()
        
        try:
            logger.info(f"💾 开始保存 {symbol} 财务数据 (数据源: {data_source})")
            
            collection = self.db[self.collection_name]
            
            # Standardized financial data
            standardized_data = self._standardize_financial_data(
                symbol, financial_data, data_source, market, report_period, report_type
            )
            
            if not standardized_data:
                logger.warning(f"⚠️ {symbol} 财务数据标准化后为空")
                return 0
            
            # Batch operations
            operations = []
            saved_count = 0
            
            # If it is multi-period data, process each period separately.
            if isinstance(standardized_data, list):
                for data_item in standardized_data:
                    filter_doc = {
                        "symbol": data_item["symbol"],
                        "report_period": data_item["report_period"],
                        "data_source": data_item["data_source"]
                    }
                    
                    operations.append(ReplaceOne(
                        filter=filter_doc,
                        replacement=data_item,
                        upsert=True
                    ))
                    saved_count += 1
            else:
                # Single period data
                filter_doc = {
                    "symbol": standardized_data["symbol"],
                    "report_period": standardized_data["report_period"],
                    "data_source": standardized_data["data_source"]
                }
                
                operations.append(ReplaceOne(
                    filter=filter_doc,
                    replacement=standardized_data,
                    upsert=True
                ))
                saved_count = 1
            
            # Perform batch operations
            if operations:
                result = await collection.bulk_write(operations)
                actual_saved = result.upserted_count + result.modified_count
                standardized_records = standardized_data if isinstance(standardized_data, list) else [standardized_data]
                period_saved = await self._sync_financial_period_records(standardized_records)
                
                logger.info(
                    f"✅ {symbol} 财务数据保存完成: 原始{actual_saved}条, 期间{period_saved}条"
                )
                return actual_saved
            
            return 0
            
        except Exception as e:
            logger.error(f"❌ 保存财务数据失败 {symbol}: {e}")
            return 0

    async def _sync_financial_period_records(self, standardized_records: List[Dict[str, Any]]) -> int:
        """Synchronize the latest financial snapshot to the expanded collection by period for direct reading by filter/factor links."""
        period_collection = self.db[self.period_collection_name]
        operations: List[ReplaceOne] = []

        for record in standardized_records:
            for period_record in expand_financial_document_to_periods(record):
                symbol = period_record.get("symbol") or period_record.get("code")
                source = period_record.get("source") or period_record.get("data_source")
                report_period = period_record.get("report_period") or period_record.get("report_date")
                ann_date = period_record.get("ann_date") or ""
                if not symbol or not source or not report_period:
                    continue

                operations.append(
                    ReplaceOne(
                        filter={
                            "symbol": symbol,
                            "source": source,
                            "report_period": report_period,
                            "ann_date": ann_date,
                        },
                        replacement=period_record,
                        upsert=True,
                    )
                )

        if not operations:
            return 0

        await period_collection.bulk_write(operations, ordered=False)
        return len(operations)
    
    async def get_financial_data(
        self,
        symbol: str,
        report_period: str = None,
        data_source: str = None,
        report_type: str = None,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """
        Query financial data
        
        Args:
            symbol: Stock code
            report_period: Reporting period screening
            data_source: Data source filtering
            report_type: Report type filter
            limit: Limit the number of returns
            
        Returns:
            Financial data list
        """
        if self.db is None:
            await self.initialize()
        
        try:
            collection = self.db[self.collection_name]
            
            # Build query conditions
            query = {"symbol": symbol}
            
            if report_period:
                query["report_period"] = report_period
            
            if data_source:
                query["data_source"] = data_source
            
            if report_type:
                query["report_type"] = report_type
            
            # Execute query
            cursor = collection.find(query, {"_id": 0}).sort("report_period", -1)
            
            if limit:
                cursor = cursor.limit(limit)
            
            results = await cursor.to_list(length=None)
            
            logger.info(f"📊 查询财务数据: {symbol} 返回 {len(results)} 条记录")
            return results
            
        except Exception as e:
            logger.error(f"❌ 查询财务数据失败 {symbol}: {e}")
            return []
    
    async def get_latest_financial_data(
        self,
        symbol: str,
        data_source: str = None
    ) -> Optional[Dict[str, Any]]:
        """获取最新财务数据"""
        results = await self.get_financial_data(
            symbol=symbol,
            data_source=data_source,
            limit=1
        )
        
        return results[0] if results else None
    
    async def get_financial_statistics(self) -> Dict[str, Any]:
        """获取财务数据统计信息"""
        if self.db is None:
            await self.initialize()
        
        try:
            collection = self.db[self.collection_name]
            
            # Statistics by data source
            pipeline = [
                {"$group": {
                    "_id": {
                        "data_source": "$data_source",
                        "report_type": "$report_type"
                    },
                    "count": {"$sum": 1},
                    "latest_period": {"$max": "$report_period"},
                    "symbols": {"$addToSet": "$symbol"}
                }}
            ]
            
            results = await collection.aggregate(pipeline).to_list(length=None)
            
            # Format statistical results
            stats = {}
            total_records = 0
            total_symbols = set()
            
            for result in results:
                source = result["_id"]["data_source"]
                report_type = result["_id"]["report_type"]
                count = result["count"]
                symbols = result["symbols"]
                
                if source not in stats:
                    stats[source] = {}
                
                stats[source][report_type] = {
                    "count": count,
                    "latest_period": result["latest_period"],
                    "symbol_count": len(symbols)
                }
                
                total_records += count
                total_symbols.update(symbols)
            
            return {
                "total_records": total_records,
                "total_symbols": len(total_symbols),
                "by_source": stats,
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to obtain financial data statistics: {e}")
            return {}
    
    def _standardize_financial_data(
        self,
        symbol: str,
        financial_data: Dict[str, Any],
        data_source: str,
        market: str,
        report_period: str = None,
        report_type: str = "quarterly"
    ) -> Optional[Dict[str, Any]]:
        """标准化财务数据"""
        try:
            now = datetime.now(timezone.utc)
            
            # Different normalization processes depending on the data source
            if data_source == "tushare":
                return self._standardize_tushare_data(
                    symbol, financial_data, market, report_period, report_type, now
                )
            elif data_source == "akshare":
                return self._standardize_akshare_data(
                    symbol, financial_data, market, report_period, report_type, now
                )
            elif data_source == "baostock":
                return self._standardize_baostock_data(
                    symbol, financial_data, market, report_period, report_type, now
                )
            elif data_source == "qmt":
                return self._standardize_qmt_data(
                    symbol, financial_data, market, report_period, report_type, now
                )
            else:
                logger.warning(f"⚠️ 不支持的数据源: {data_source}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 标准化财务数据失败 {symbol}: {e}")
            return None
    
    def _standardize_tushare_data(
        self,
        symbol: str,
        financial_data: Dict[str, Any],
        market: str,
        report_period: str,
        report_type: str,
        now: datetime
    ) -> Dict[str, Any]:
        """Standardize Tushare financial data"""
        # Tushare The data has been standardized in the provider and can be used directly
        resolved_period = report_period or financial_data.get("report_period")
        resolved_report_type = self._resolve_report_type(
            resolved_period,
            financial_data.get("report_type"),
            report_type,
        )

        base_data = {
            "code": symbol,  # Add code field for compatibility with unique indexes
            "symbol": symbol,
            "full_symbol": self._get_full_symbol(symbol, market),
            "market": market,
            "report_period": resolved_period,
            "report_type": resolved_report_type,
            "data_source": "tushare",
            "created_at": now,
            "updated_at": now,
            "version": 1
        }

        # Merge Tushare's standardized financial data
        # Exclude some fields that do not need to be repeated
        exclude_fields = {'symbol', 'data_source', 'updated_at'}
        for key, value in financial_data.items():
            if key not in exclude_fields:
                base_data[key] = value

        # Make sure key fields exist
        if 'ann_date' in financial_data:
            base_data['ann_date'] = financial_data['ann_date']

        return base_data
    
    def _standardize_akshare_data(
        self,
        symbol: str,
        financial_data: Dict[str, Any],
        market: str,
        report_period: str,
        report_type: str,
        now: datetime
    ) -> Dict[str, Any]:
        """Standardize AKShare financial data"""
        # AKShare Data needs to extract key metrics from multiple datasets
        resolved_period = report_period or self._extract_latest_period(financial_data)
        resolved_report_type = self._resolve_report_type(resolved_period, None, report_type)

        base_data = {
            "code": symbol,  # Add code field for compatibility with unique indexes
            "symbol": symbol,
            "full_symbol": self._get_full_symbol(symbol, market),
            "market": market,
            "report_period": resolved_period,
            "report_type": resolved_report_type,
            "data_source": "akshare",
            "created_at": now,
            "updated_at": now,
            "version": 1
        }

        # Extract key financial indicators
        base_data.update(self._extract_akshare_indicators(financial_data))
        base_data["raw_data"] = financial_data
        return base_data
    
    def _standardize_baostock_data(
        self,
        symbol: str,
        financial_data: Dict[str, Any],
        market: str,
        report_period: str,
        report_type: str,
        now: datetime
    ) -> Dict[str, Any]:
        """Standardized BaoStock financial data"""
        resolved_period = report_period or self._extract_baostock_period(financial_data)
        resolved_report_type = self._resolve_report_type(resolved_period, None, report_type)

        base_data = {
            "code": symbol,  # Add code field for compatibility with unique indexes
            "symbol": symbol,
            "full_symbol": self._get_full_symbol(symbol, market),
            "market": market,
            "report_period": resolved_period,
            "report_type": resolved_report_type,
            "data_source": "baostock",
            "created_at": now,
            "updated_at": now,
            "version": 1
        }

        # Consolidate BaoStock financial data
        base_data.update(financial_data)
        return base_data

    def _standardize_qmt_data(
        self,
        symbol: str,
        financial_data: Dict[str, Any],
        market: str,
        report_period: str,
        report_type: str,
        now: datetime
    ) -> Dict[str, Any]:
        """标准化QMT财务数据"""
        resolved_period = report_period or financial_data.get("report_period") or self._generate_current_period()
        resolved_report_type = self._resolve_report_type(
            resolved_period,
            financial_data.get("report_type"),
            report_type,
        )

        base_data = {
            "code": symbol,
            "symbol": symbol,
            "full_symbol": self._get_full_symbol(symbol, market),
            "market": market,
            "report_period": resolved_period,
            "report_type": resolved_report_type,
            "data_source": "qmt",
            "created_at": now,
            "updated_at": now,
            "version": 1
        }

        exclude_fields = {"symbol", "data_source", "updated_at"}
        for key, value in financial_data.items():
            if key not in exclude_fields:
                base_data[key] = value

        return base_data
    
    def _get_full_symbol(self, symbol: str, market: str) -> str:
        """获取完整股票代码"""
        if market == "CN":
            if symbol.startswith("6"):
                return f"{symbol}.SH"
            else:
                return f"{symbol}.SZ"
        return symbol

    def _normalize_period_value(self, value: Any) -> Optional[str]:
        """Normalized reporting period, compatible with YYYY-MM-DD and YYYYMMDD."""
        normalized = str(value or "").strip().replace('-', '')
        if len(normalized) == 8 and normalized.isdigit():
            return normalized
        return None

    def _extract_latest_period_from_records(self, records: Any) -> Optional[str]:
        """Extracts the latest reporting period from a list record or matrix column name."""
        if not isinstance(records, list):
            return None

        latest_period: Optional[str] = None
        for record in records:
            if not isinstance(record, dict):
                continue

            for date_field in ['报告期', '报告日期', 'date', '日期', 'end_date', 'report_period']:
                period = self._normalize_period_value(record.get(date_field))
                if period and (latest_period is None or period > latest_period):
                    latest_period = period

            for key in record.keys():
                period = self._normalize_period_value(key)
                if period and (latest_period is None or period > latest_period):
                    latest_period = period

        return latest_period

    def _extract_matrix_indicator_value(
        self,
        records: Any,
        indicator_names: List[str],
        report_period: Optional[str],
    ) -> Optional[float]:
        """Extracts metric values ​​from the AKShare metric matrix for the specified reporting period."""
        if not report_period or not isinstance(records, list):
            return None

        for record in records:
            if not isinstance(record, dict):
                continue
            indicator_name = str(record.get('指标') or record.get('indicator') or '').strip()
            if indicator_name not in indicator_names:
                continue

            for key, value in record.items():
                if self._normalize_period_value(key) == report_period:
                    return self._safe_float(value)

        return None
    
    def _extract_latest_period(self, financial_data: Dict[str, Any]) -> str:
        """Extract latest reporting period from AKShare data"""
        # Try to extract reporting periods from various datasets
        for key in ['main_indicators', 'balance_sheet', 'income_statement']:
            if key in financial_data and financial_data[key]:
                period = self._extract_latest_period_from_records(financial_data[key])
                if period:
                    return period
        
        # If extraction is not possible, use the current quarter
        return self._generate_current_period()

    def _extract_baostock_period(self, financial_data: Dict[str, Any]) -> str:
        """Extract reporting periods from BaoStock financial data"""
        for key in [
            'profit_data',
            'operation_data',
            'growth_data',
            'balance_data',
            'cash_flow_data',
        ]:
            dataset = financial_data.get(key)
            if not dataset:
                continue
            if isinstance(dataset, list) and dataset:
                dataset = dataset[0]
            if isinstance(dataset, dict):
                for field in ['statDate', 'pubDate', 'report_date', 'report_period']:
                    value = dataset.get(field)
                    if value:
                        return str(value).replace('-', '')
        return self._generate_current_period()

    def _resolve_report_type(
        self,
        report_period: Optional[str],
        explicit_report_type: Optional[str],
        fallback_report_type: Optional[str],
    ) -> str:
        """Infer the report type based on the reporting period to avoid being fixed as quarterly during unified synchronization."""
        if explicit_report_type:
            return explicit_report_type

        normalized_period = str(report_period or '').replace('-', '')
        if len(normalized_period) >= 8 and normalized_period.endswith('1231'):
            return 'annual'

        if fallback_report_type:
            return fallback_report_type

        return 'quarterly'
    
    def _extract_akshare_indicators(self, financial_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key financial indicators from AKShare data"""
        indicators = {}
        latest_period = self._extract_latest_period(financial_data)

        # Extracted from key financial indicators
        if 'main_indicators' in financial_data and financial_data['main_indicators']:
            main_records = financial_data['main_indicators']
            main_data = main_records[0] if main_records else {}
            indicators.update({
                "revenue": self._safe_float(main_data.get('营业收入')),
                "net_income": self._safe_float(main_data.get('净利润')),
                "total_assets": self._safe_float(main_data.get('总资产')),
                "total_equity": self._safe_float(main_data.get('股东权益合计')),
            })

            # 🔥 New: Extract ROE (Return on Equity)
            roe = main_data.get('净资产收益率(ROE)') or main_data.get('净资产收益率')
            if roe is not None:
                indicators["roe"] = self._safe_float(roe)

            # 🔥 Newly added: Extract liability ratio (asset-liability ratio)
            debt_ratio = main_data.get('资产负债率') or main_data.get('负债率')
            if debt_ratio is not None:
                indicators["debt_to_assets"] = self._safe_float(debt_ratio)

            matrix_indicator_specs = {
                "revenue": ["营业收入", "营业总收入"],
                "net_income": ["净利润", "归母净利润", "归属于母公司股东的净利润"],
                "total_assets": ["总资产"],
                "total_equity": ["股东权益合计", "股东权益合计(净资产)", "所有者权益合计"],
                "roe": ["净资产收益率(ROE)", "净资产收益率", "净资产收益率_平均"],
                "debt_to_assets": ["资产负债率", "负债率"],
            }
            for field_name, indicator_names in matrix_indicator_specs.items():
                if indicators.get(field_name) is not None:
                    continue
                matrix_value = self._extract_matrix_indicator_value(
                    main_records,
                    indicator_names,
                    latest_period,
                )
                if matrix_value is not None:
                    indicators[field_name] = matrix_value

        # Taken from the balance sheet
        if 'balance_sheet' in financial_data and financial_data['balance_sheet']:
            balance_data = financial_data['balance_sheet'][0] if financial_data['balance_sheet'] else {}
            indicators.update({
                "total_liab": self._safe_float(balance_data.get('负债合计')),
                "cash_and_equivalents": self._safe_float(balance_data.get('货币资金')),
            })

            # 🔥 If there is no debt ratio in the main indicator, it is calculated from the balance sheet
            if "debt_to_assets" not in indicators:
                total_liab = indicators.get("total_liab")
                total_assets = indicators.get("total_assets")
                if total_liab is not None and total_assets is not None and total_assets > 0:
                    indicators["debt_to_assets"] = (total_liab / total_assets) * 100

        return indicators
    
    def _generate_current_period(self) -> str:
        """生成当前报告期"""
        now = datetime.now()
        year = now.year
        month = now.month
        
        # Determine quarter based on month
        if month <= 3:
            quarter = 1
        elif month <= 6:
            quarter = 2
        elif month <= 9:
            quarter = 3
        else:
            quarter = 4
        
        # Generate reporting period format YYYYMMDD
        quarter_end_months = {1: "03", 2: "06", 3: "09", 4: "12"}
        quarter_end_days = {1: "31", 2: "30", 3: "30", 4: "31"}
        
        return f"{year}{quarter_end_months[quarter]}{quarter_end_days[quarter]}"
    
    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                # Remove possible units and formatting characters
                value = value.replace(',', '').replace('万', '').replace('亿', '')
            return float(value)
        except (ValueError, TypeError):
            return None


# Global service instance
_financial_data_service = None


async def get_financial_data_service() -> FinancialDataService:
    """获取财务数据服务实例"""
    global _financial_data_service
    if _financial_data_service is None:
        _financial_data_service = FinancialDataService()
        await _financial_data_service.initialize()
    return _financial_data_service

# === news_data_service.py ===
"""
News data service
Provide unified news data storage, query and management functions
"""
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging
try:
    from pymongo import ReplaceOne
except ImportError:
    from unittest.mock import MagicMock as _MM; BulkWriteResult = UpdateOne = InsertOne = DeleteOne = MongoClient = Database = ASCENDING = DESCENDING = ReturnDocument = _MM()
    DuplicateKeyError = PyMongoError = OperationFailure = ServerSelectionTimeoutError = ConnectionFailure = Exception
try:
    from pymongo.errors import BulkWriteError
except ImportError:
    from unittest.mock import MagicMock as _MM; BulkWriteResult = UpdateOne = InsertOne = DeleteOne = MongoClient = Database = ASCENDING = DESCENDING = ReturnDocument = _MM()
    DuplicateKeyError = PyMongoError = OperationFailure = ServerSelectionTimeoutError = ConnectionFailure = Exception
try:
    from bson import ObjectId
except ImportError:
    ObjectId = str

from app.core.database import get_database

logger = logging.getLogger(__name__)


def convert_objectid_to_str(data: Union[Dict, List[Dict]]) -> Union[Dict, List[Dict]]:
    """
    Convert MongoDB ObjectId to string to avoid JSON serialization errors

    Args:
        data: Single document or list of documents

    Returns:
        converted data
    """
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and '_id' in item:
                item['_id'] = str(item['_id'])
        return data
    elif isinstance(data, dict):
        if '_id' in data:
            data['_id'] = str(data['_id'])
        return data
    return data


@dataclass
class NewsQueryParams:
    """新闻查询参数"""
    symbol: Optional[str] = None
    symbols: Optional[List[str]] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    category: Optional[str] = None
    sentiment: Optional[str] = None
    importance: Optional[str] = None
    data_source: Optional[str] = None
    keywords: Optional[List[str]] = None
    limit: int = 50
    skip: int = 0
    sort_by: str = "publish_time"
    sort_order: int = -1  # -1 for desc, 1 for asc


@dataclass
class NewsStats:
    """新闻统计信息"""
    total_count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    high_importance_count: int = 0
    medium_importance_count: int = 0
    low_importance_count: int = 0
    categories: Dict[str, int] = None
    sources: Dict[str, int] = None
    
    def __post_init__(self):
        if self.categories is None:
            self.categories = {}
        if self.sources is None:
            self.sources = {}


class NewsDataService:
    """新闻数据服务"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._db = None
        self._collection = None
        self._indexes_ensured = False

    async def _ensure_indexes(self):
        """确保必要的索引存在"""
        if self._indexes_ensured:
            return

        try:
            collection = self._get_collection()
            self.logger.info("📊 Check and create index of news data...")

            # 1. Unique index: prevent duplicate news (URL+Title+Release time)
            await collection.create_index([
                ("url", 1),
                ("title", 1),
                ("publish_time", 1)
            ], unique=True, name="url_title_time_unique", background=True)

            # 2. Stock code index (query news about a single stock)
            await collection.create_index([("symbol", 1)], name="symbol_index", background=True)

            # 3. Multi-stock code index (query news involving multiple stocks)
            await collection.create_index([("symbols", 1)], name="symbols_index", background=True)

            # 4. Release time index (query by time range)
            await collection.create_index([("publish_time", -1)], name="publish_time_desc", background=True)

            # 5. Composite Index: Stock Symbol+Release time (common queries)
            await collection.create_index([
                ("symbol", 1),
                ("publish_time", -1)
            ], name="symbol_time_index", background=True)

            # 6. Data source index (filter by data source)
            await collection.create_index([("data_source", 1)], name="data_source_index", background=True)

            # 7. Category index (filter by news category)
            await collection.create_index([("category", 1)], name="category_index", background=True)

            # 8. Sentiment index (filter by sentiment)
            await collection.create_index([("sentiment", 1)], name="sentiment_index", background=True)

            # 9. Importance index (filter by importance)
            await collection.create_index([("importance", 1)], name="importance_index", background=True)

            # 10. Update time index (data maintenance)
            await collection.create_index([("updated_at", -1)], name="updated_at_index", background=True)

            self._indexes_ensured = True
            self.logger.info("✅ 新闻数据索引检查完成")
        except Exception as e:
            # Index creation failure should not prevent the service from starting
            self.logger.warning(f"⚠️ Warning when creating index (may already exist): {e}")

    def _get_collection(self):
        """获取新闻数据集合"""
        if self._collection is None:
            self._db = get_database()
            self._collection = self._db.stock_news
        return self._collection
    
    @property
    def db(self):
        """Get database connection (compatibility properties)"""
        if self._db is None:
            self._db = get_database()
        return self._db
    
    async def save_news_data(
        self,
        news_data: Union[Dict[str, Any], List[Dict[str, Any]]],
        data_source: str,
        market: str = "CN"
    ) -> int:
        """
        Save news data

        Args:
            news_data: News data (single or multiple items)
            data_source: Data source identifier
            market: market identification

        Returns:
            Number of records saved
        """
        try:
            # 🔥 Make sure the index exists (created on first call)
            await self._ensure_indexes()

            collection = self._get_collection()
            now = datetime.utcnow()
            
            # normalized data
            if isinstance(news_data, dict):
                news_list = [news_data]
            else:
                news_list = news_data
            
            if not news_list:
                return 0
            
            # Prepare for batch operations
            operations = []

            for i, news in enumerate(news_list):
                # Standardized news data
                standardized_news = self._standardize_news_data(
                    news, data_source, market, now
                )

                # 🔍 Record the details of the first 3 pieces of data
                if i < 3:
                    self.logger.info(f"   📝 标准化后的新闻 {i+1}:")
                    self.logger.info(f"      symbol: {standardized_news.get('symbol')}")
                    self.logger.info(f"      title: {standardized_news.get('title', '')[:50]}...")
                    self.logger.info(f"      publish_time: {standardized_news.get('publish_time')} (type: {type(standardized_news.get('publish_time'))})")
                    self.logger.info(f"      url: {standardized_news.get('url', '')[:80]}...")

                # Use URL, title and publication time as unique identifiers
                filter_query = {
                    "url": standardized_news["url"],
                    "title": standardized_news["title"],
                    "publish_time": standardized_news["publish_time"]
                }

                operations.append(
                    ReplaceOne(
                        filter_query,
                        standardized_news,
                        upsert=True
                    )
                )
            
            # Perform batch operations (thread-safe)
            if operations:
                # 🔥 Use thread-safe bulk_write
                from app.utils.thread_safe_db import safe_bulk_write

                result = await safe_bulk_write(
                    collection_name=collection.name,
                    operations=operations,
                    ordered=False,
                    async_db=self.db,
                    max_retries=3
                )
                saved_count = result.upserted_count + result.modified_count

                self.logger.info(f"💾 新闻数据保存完成: {saved_count}条记录 (数据源: {data_source})")
                return saved_count

            return 0

        except BulkWriteError as e:
            # Handle batch write errors without outright failure
            write_errors = e.details.get('writeErrors', [])
            error_count = len(write_errors)
            self.logger.warning(f"⚠️ 部分新闻数据保存失败: {error_count}条错误")

            # Log detailed error information
            for i, error in enumerate(write_errors[:3], 1):  # Only log the first 3 errors
                error_msg = error.get('errmsg', 'Unknown error')
                error_code = error.get('code', 'N/A')
                self.logger.warning(f"   错误 {i}: [Code {error_code}] {error_msg}")

            # Count the number of successful saves
            success_count = len(operations) - error_count
            if success_count > 0:
                self.logger.info(f"💾 成功保存 {success_count} 条新闻数据")

            return success_count
            
        except Exception as e:
            self.logger.error(f"❌ 保存新闻数据失败: {e}")
            return 0

    def save_news_data_sync(
        self,
        news_data: Union[Dict[str, Any], List[Dict[str, Any]]],
        data_source: str,
        market: str = "CN"
    ) -> int:
        """
        Save news data (synchronized version)
        For non-async context, use the synchronous PyMongo client

        Args:
            news_data: News data (single or multiple items)
            data_source: Data source identifier
            market: market identification

        Returns:
            Number of records saved
        """
        try:
            from app.core.database import get_mongo_db_sync

            # Get sync database connection
            db = get_mongo_db_sync()
            collection = db.stock_news
            now = datetime.utcnow()

            # normalized data
            if isinstance(news_data, dict):
                news_list = [news_data]
            else:
                news_list = news_data

            if not news_list:
                return 0

            # Prepare for batch operations
            operations = []

            self.logger.info(f"📝 开始标准化 {len(news_list)} 条新闻数据...")

            for i, news in enumerate(news_list, 1):
                # Standardized news data
                standardized_news = self._standardize_news_data(news, data_source, market, now)

                # Record the details of the first 3 news items
                if i <= 3:
                    self.logger.info(f"   📝 标准化后的新闻 {i}:")
                    self.logger.info(f"      symbol: {standardized_news.get('symbol')}")
                    self.logger.info(f"      title: {standardized_news.get('title', '')[:50]}...")
                    publish_time = standardized_news.get('publish_time')
                    self.logger.info(f"      publish_time: {publish_time} (type: {type(publish_time)})")
                    self.logger.info(f"      url: {standardized_news.get('url', '')[:60]}...")

                # Use URL+Title+Release time as unique identifier
                filter_query = {
                    "url": standardized_news.get("url"),
                    "title": standardized_news.get("title"),
                    "publish_time": standardized_news.get("publish_time")
                }

                operations.append(
                    ReplaceOne(
                        filter_query,
                        standardized_news,
                        upsert=True
                    )
                )

            # Perform batch operations (synchronous mode)
            if operations:
                result = collection.bulk_write(operations)
                saved_count = result.upserted_count + result.modified_count

                self.logger.info(f"💾 新闻数据保存完成: {saved_count}条记录 (数据源: {data_source})")
                return saved_count

            return 0

        except BulkWriteError as e:
            # Handle batch write errors without outright failure
            write_errors = e.details.get('writeErrors', [])
            error_count = len(write_errors)
            self.logger.warning(f"⚠️ 部分新闻数据保存失败: {error_count}条错误")

            # Log detailed error information
            for i, error in enumerate(write_errors[:3], 1):  # Only log the first 3 errors
                error_msg = error.get('errmsg', 'Unknown error')
                error_code = error.get('code', 'N/A')
                self.logger.warning(f"   错误 {i}: [Code {error_code}] {error_msg}")

            # Count the number of successful saves
            success_count = len(operations) - error_count
            if success_count > 0:
                self.logger.info(f"💾 成功保存 {success_count} 条新闻数据")

            return success_count

        except Exception as e:
            self.logger.error(f"❌ 保存新闻数据失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return 0

    def _standardize_news_data(
        self,
        news_data: Dict[str, Any],
        data_source: str,
        market: str,
        now: datetime
    ) -> Dict[str, Any]:
        """标准化新闻数据"""
        
        # Extract basic information
        symbol = news_data.get("symbol")
        symbols = news_data.get("symbols", [])
        
        # If there is a main stock symbol but symbols is empty, add to symbols
        if symbol and symbol not in symbols:
            symbols = [symbol] + symbols
        
        # standardized data structures
        standardized = {
            # Basic information
            "symbol": symbol,
            "full_symbol": self._get_full_symbol(symbol, market) if symbol else None,
            "market": market,
            "symbols": symbols,
            
            # News content
            "title": news_data.get("title", ""),
            "content": news_data.get("content", ""),
            "summary": news_data.get("summary", ""),
            "url": news_data.get("url", ""),
            "source": news_data.get("source", ""),
            "author": news_data.get("author", ""),
            
            # time information
            "publish_time": self._parse_datetime(news_data.get("publish_time")),
            
            # Categories and tags
            "category": news_data.get("category", "general"),
            "sentiment": news_data.get("sentiment", "neutral"),
            "sentiment_score": self._safe_float(news_data.get("sentiment_score")),
            "keywords": news_data.get("keywords", []),
            "importance": news_data.get("importance", "medium"),
            # Note: Do not include the language field to avoid conflict with MongoDB text index

            # metadata
            "data_source": data_source,
            "created_at": now,
            "updated_at": now,
            "version": 1
        }
        
        return standardized
    
    def _get_full_symbol(self, symbol: str, market: str) -> str:
        """获取完整股票代码"""
        if not symbol:
            return None
        
        if market == "CN":
            if len(symbol) == 6:
                if symbol.startswith(('60', '68')):
                    return f"{symbol}.SH"
                elif symbol.startswith(('00', '30')):
                    return f"{symbol}.SZ"
        
        return symbol
    
    def _parse_datetime(self, dt_value) -> Optional[datetime]:
        """解析日期时间"""
        if dt_value is None:
            return None
        
        if isinstance(dt_value, datetime):
            return dt_value
        
        if isinstance(dt_value, str):
            try:
                # Try multiple date formats
                formats = [
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%d",
                ]
                
                for fmt in formats:
                    try:
                        return datetime.strptime(dt_value, fmt)
                    except ValueError:
                        continue
                
                # If all else fails, return the current time
                self.logger.warning(f"⚠️ 无法解析日期时间: {dt_value}")
                return datetime.utcnow()
                
            except Exception:
                return datetime.utcnow()
        
        return datetime.utcnow()
    
    def _safe_float(self, value) -> Optional[float]:
        """安全转换为浮点数"""
        if value is None:
            return None
        
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    async def query_news(self, params: NewsQueryParams) -> List[Dict[str, Any]]:
        """
        Query news data
        
        Args:
            params: query parameters
            
        Returns:
            News data list
        """
        try:
            collection = self._get_collection()

            self.logger.info("🔍 [query_news] Start querying news data")
            self.logger.info(f"   参数: symbol={params.symbol}, start_time={params.start_time}, end_time={params.end_time}, limit={params.limit}")

            # Build query conditions
            query = {}

            if params.symbol:
                query["symbol"] = params.symbol
                self.logger.info(f"   Add query conditions: symbol={params.symbol}")

            if params.symbols:
                query["symbols"] = {"$in": params.symbols}
                self.logger.info(f"   Add query conditions: symbols in {params.symbols}")

            if params.start_time or params.end_time:
                time_query = {}
                if params.start_time:
                    time_query["$gte"] = params.start_time
                if params.end_time:
                    time_query["$lte"] = params.end_time
                query["publish_time"] = time_query
                self.logger.info(f"   Add query conditions: publish_time between {params.start_time} and {params.end_time}")

            if params.category:
                query["category"] = params.category
                self.logger.info(f"   Add query conditions: category={params.category}")

            if params.sentiment:
                query["sentiment"] = params.sentiment
                self.logger.info(f"   Add query conditions: sentiment={params.sentiment}")

            if params.importance:
                query["importance"] = params.importance
                self.logger.info(f"   Add query conditions: importance={params.importance}")

            if params.data_source:
                query["data_source"] = params.data_source
                self.logger.info(f"   Add query conditions: data_source={params.data_source}")

            if params.keywords:
                # Text search
                query["$text"] = {"$search": " ".join(params.keywords)}
                self.logger.info(f"   Add query conditions: text search={params.keywords}")

            self.logger.info(f"   最终查询条件: {query}")

            # Count the total first
            total_count = await collection.count_documents(query)
            self.logger.info(f"   The total number of records in the database that meet the criteria: {total_count}")

            # Execute query
            cursor = collection.find(query)

            # sort
            cursor = cursor.sort(params.sort_by, params.sort_order)
            self.logger.info(f"   排序: {params.sort_by} ({params.sort_order})")

            # Pagination
            cursor = cursor.skip(params.skip).limit(params.limit)
            self.logger.info(f"   分页: skip={params.skip}, limit={params.limit}")

            # Get results
            results = await cursor.to_list(length=None)
            self.logger.info(f"   查询返回: {len(results)} 条记录")

            # 🔧 Convert ObjectId to string to avoid JSON serialization errors
            results = convert_objectid_to_str(results)

            if results:
                self.logger.info("   前3条预览:")
                for i, r in enumerate(results[:3], 1):
                    self.logger.info(f"      {i}. symbol={r.get('symbol')}, title={r.get('title', 'N/A')[:50]}..., publish_time={r.get('publish_time')}")
            else:
                self.logger.warning("   ⚠️ 查询结果为空")

            self.logger.info(f"✅ [query_news] 查询完成，返回 {len(results)} 条记录")
            return results

        except Exception as e:
            self.logger.error(f"❌ 查询新闻数据失败: {e}", exc_info=True)
            return []
    
    async def get_latest_news(
        self,
        symbol: str = None,
        limit: int = 10,
        hours_back: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Get the latest news
        
        Args:
            symbol: Stock code, if empty, get all news
            limit: Return quantity limit
            hours_back: Lookback hours
            
        Returns:
            Latest news list
        """
        start_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        params = NewsQueryParams(
            symbol=symbol,
            start_time=start_time,
            limit=limit,
            sort_by="publish_time",
            sort_order=-1
        )
        
        return await self.query_news(params)
    
    async def get_news_statistics(
        self,
        symbol: str = None,
        start_time: datetime = None,
        end_time: datetime = None
    ) -> NewsStats:
        """
        Get news statistics
        
        Args:
            symbol: Stock code
            start_time: start time
            end_time: end time
            
        Returns:
            News statistics
        """
        try:
            collection = self._get_collection()
            
            # Build matching conditions
            match_stage = {}
            
            if symbol:
                match_stage["symbol"] = symbol
            
            if start_time or end_time:
                time_query = {}
                if start_time:
                    time_query["$gte"] = start_time
                if end_time:
                    time_query["$lte"] = end_time
                match_stage["publish_time"] = time_query
            
            # aggregation pipeline
            pipeline = []
            
            if match_stage:
                pipeline.append({"$match": match_stage})
            
            pipeline.extend([
                {
                    "$group": {
                        "_id": None,
                        "total_count": {"$sum": 1},
                        "positive_count": {
                            "$sum": {"$cond": [{"$eq": ["$sentiment", "positive"]}, 1, 0]}
                        },
                        "negative_count": {
                            "$sum": {"$cond": [{"$eq": ["$sentiment", "negative"]}, 1, 0]}
                        },
                        "neutral_count": {
                            "$sum": {"$cond": [{"$eq": ["$sentiment", "neutral"]}, 1, 0]}
                        },
                        "high_importance_count": {
                            "$sum": {"$cond": [{"$eq": ["$importance", "high"]}, 1, 0]}
                        },
                        "medium_importance_count": {
                            "$sum": {"$cond": [{"$eq": ["$importance", "medium"]}, 1, 0]}
                        },
                        "low_importance_count": {
                            "$sum": {"$cond": [{"$eq": ["$importance", "low"]}, 1, 0]}
                        },
                        "categories": {"$push": "$category"},
                        "sources": {"$push": "$data_source"}
                    }
                }
            ])
            
            # Perform aggregation
            result = await collection.aggregate(pipeline).to_list(length=1)
            
            if result:
                data = result[0]
                
                # Statistical categories and sources
                categories = {}
                for cat in data.get("categories", []):
                    categories[cat] = categories.get(cat, 0) + 1
                
                sources = {}
                for src in data.get("sources", []):
                    sources[src] = sources.get(src, 0) + 1
                
                return NewsStats(
                    total_count=data.get("total_count", 0),
                    positive_count=data.get("positive_count", 0),
                    negative_count=data.get("negative_count", 0),
                    neutral_count=data.get("neutral_count", 0),
                    high_importance_count=data.get("high_importance_count", 0),
                    medium_importance_count=data.get("medium_importance_count", 0),
                    low_importance_count=data.get("low_importance_count", 0),
                    categories=categories,
                    sources=sources
                )
            
            return NewsStats()
            
        except Exception as e:
            self.logger.error(f"❌ 获取新闻统计失败: {e}")
            return NewsStats()
    
    async def delete_old_news(self, days_to_keep: int = 90) -> int:
        """
        Delete expired news
        
        Args:
            days_to_keep: retention days
            
        Returns:
            Number of records deleted
        """
        try:
            collection = self._get_collection()
            
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
            
            result = await collection.delete_many({
                "publish_time": {"$lt": cutoff_date}
            })
            
            deleted_count = result.deleted_count
            self.logger.info(f"🗑️ 删除过期新闻: {deleted_count}条记录")
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"❌ 删除过期新闻失败: {e}")
            return 0

    async def search_news(
        self,
        query_text: str,
        symbol: str = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search news in full text

        Args:
            query_text: Search text
            symbol: Stock code filter
            limit: Return quantity limit

        Returns:
            Search result list
        """
        try:
            collection = self._get_collection()

            # Build query conditions
            query = {"$text": {"$search": query_text}}

            if symbol:
                query["symbol"] = symbol

            # Perform a search, sorted by relevance
            cursor = collection.find(
                query,
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})])

            cursor = cursor.limit(limit)
            results = await cursor.to_list(length=None)

            # 🔧 Convert ObjectId to string to avoid JSON serialization errors
            results = convert_objectid_to_str(results)

            self.logger.info(f"🔍 全文搜索返回 {len(results)} 条结果")
            return results

        except Exception as e:
            self.logger.error(f"❌ 全文搜索失败: {e}")
            return []


# Global service instance
_service_instance = None

async def get_news_data_service() -> NewsDataService:
    """获取新闻数据服务实例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = NewsDataService()
        logger.info("✅ News data service initialization successful")
    return _service_instance

# === quotes_service.py ===
"""
QuotesService: Provides A-share batch real-time snapshot acquisition (AKShare Oriental Fortune spot interface), with memory TTL cache.
- Do not use Tongda Xin (TDX) as a back-up data source.
- Only used to enrich items before filtering and returning.
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _quotes_service_safe_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        # Handling commas/percent signs/whitespace in strings
        if isinstance(v, str):
            s = v.strip().replace(",", "")
            if s.endswith("%"):
                s = s[:-1]
            if s == "-" or s == "":
                return None
            return float(s)
        # Processing pandas/numpy numerical values
        return float(v)
    except Exception:
        return None


class QuotesService:
    def __init__(self, ttl_seconds: int = 30) -> None:
        self._ttl = ttl_seconds
        self._cache_ts: float = 0.0
        self._cache: Dict[str, Dict[str, Optional[float]]] = {}
        self._lock = asyncio.Lock()

    async def get_quotes(self, codes: List[str]) -> Dict[str, Dict[str, Optional[float]]]:
        """Get a near-real-time snapshot of a batch of stocks (latest price, change, volume).
        - Priority is given to using the cache; if the cache times out or is empty, a full market snapshot will be refreshed.
        - Returns only the requested codes.
        """
        codes = [c.strip() for c in codes if c]
        now = time.time()
        async with self._lock:
            if self._cache and (now - self._cache_ts) < self._ttl:
                return {c: q for c, q in self._cache.items() if c in codes and q}
            # Refresh the cache (block IO and put it on the thread)
            data = await asyncio.to_thread(self._fetch_spot_akshare)
            self._cache = data
            self._cache_ts = time.time()
            return {c: q for c, q in self._cache.items() if c in codes and q}

    def _fetch_spot_akshare(self) -> Dict[str, Dict[str, Optional[float]]]:
        """Pull quotes through the AKShare Oriental Wealth full market snapshot interface and standardize them into a dictionary.
        Expected columns (common): code, name, latest price, increase or decrease, and transaction volume.
        Different versions may have differences and are compatible with multiple column names.
        """
        try:
            import akshare as ak  # Already used in the project, no additional installation required
            df = ak.stock_zh_a_spot_em()
            if df is None or getattr(df, "empty", True):
                logger.warning("AKShare spot Return empty data")
                return {}
            # Compatible with common column names
            code_col = next((c for c in ["代码", "代码code", "symbol", "股票代码"] if c in df.columns), None)
            price_col = next((c for c in ["最新价", "现价", "最新价(元)", "price", "最新"] if c in df.columns), None)
            pct_col = next((c for c in ["涨跌幅", "涨跌幅(%)", "涨幅", "pct_chg"] if c in df.columns), None)
            amount_col = next((c for c in ["成交额", "成交额(元)", "amount", "成交额(万元)"] if c in df.columns), None)

            if not code_col or not price_col:
                logger.error(f"AKShare spot Missing required column: code={code_col}, price={price_col}")
                return {}

            result: Dict[str, Dict[str, Optional[float]]] = {}
            for _, row in df.iterrows():  # type: ignore
                code_raw = row.get(code_col)
                if not code_raw:
                    continue
                # Standardize stock symbols: remove leading 0s, then pad to 6 digits
                code_str = str(code_raw).strip()
                # If it is a pure number, remove the leading 0 and pad it to 6 digits.
                if code_str.isdigit():
                    code_clean = code_str.lstrip('0') or '0'  # Remove leading 0s, if all 0s, keep one 0
                    code = code_clean.zfill(6)  # Complete to 6 digits
                else:
                    code = code_str.zfill(6)
                close = _quotes_service_safe_float(row.get(price_col))
                pct = _quotes_service_safe_float(row.get(pct_col)) if pct_col else None
                amt = _quotes_service_safe_float(row.get(amount_col)) if amount_col else None
                # If the transaction volume unit is 10,000 yuan, it will be uniformly converted into yuan (some interfaces are 10,000 yuan, there is no forced conversion here, the unit will be displayed on the front end as it is)
                result[code] = {"close": close, "pct_chg": pct, "amount": amt}
            logger.info(f"AKShare spot 拉取完成: {len(result)} 条")
            return result
        except Exception as e:
            logger.error(f"Failed to obtain AKShare real-time snapshot: {e}")
            return {}


_quotes_service: Optional[QuotesService] = None


def get_quotes_service() -> QuotesService:
    global _quotes_service
    if _quotes_service is None:
        _quotes_service = QuotesService(ttl_seconds=30)
    return _quotes_service


# === quotes_ingestion_service.py ===
import asyncio
import logging
from datetime import datetime, time as dtime, timedelta
from typing import Dict, Optional, Tuple, List
from zoneinfo import ZoneInfo
from collections import deque

try:
    from pymongo import UpdateOne
except ImportError:
    from unittest.mock import MagicMock as _MM; BulkWriteResult = UpdateOne = InsertOne = DeleteOne = MongoClient = Database = ASCENDING = DESCENDING = ReturnDocument = _MM()
    DuplicateKeyError = PyMongoError = OperationFailure = ServerSelectionTimeoutError = ConnectionFailure = Exception

from app.core.config import settings
from app.core.database import get_mongo_db
try:
    from app.services.data_sources.manager import DataSourceManager
except ImportError:
    DataSourceManager = None

logger = logging.getLogger(__name__)


REALTIME_QUOTES_FETCH_TIMEOUT_SECONDS = 8


class QuotesIngestionService:
    """
    Regularly obtain near-real-time market information from the data source adaptation layer and store it in a MongoDB collection `market_quotes`. 

    Core features:
    - Scheduling frequency: controlled by settings.QUOTES_INGEST_INTERVAL_SECONDS (default 360 seconds=6 minutes)
    - Interface rotation:Tushare → AKShare Oriental Fortune → AKShare Sina Finance (to avoid a single interface being restricted)
    - Intelligent current limit: Tushare free users can use up to 2 times per hour, and paid users automatically switch to high-frequency mode (5 seconds)
    - Close time: Skip the task and keep the last closing data; perform a one-time bottom-up if necessary
    - Fields:code(6 Bit), close, pct_chg, amount, open, high, low, pre_close, trade_date, updated_at
    """

    def __init__(self, collection_name: str = "market_quotes") -> None:
        from collections import deque

        self.collection_name = collection_name
        self.status_collection_name = "quotes_ingestion_status"  # Status record collection
        self.tz = ZoneInfo(settings.TIMEZONE)

        # Tushare Permission detection related attributes
        self._tushare_permission_checked = False  # Have permissions been checked?
        self._tushare_has_premium = False  # Is there paid permission?
        self._tushare_last_call_time = None  # Last call time (for free user current limit)
        self._tushare_hourly_limit = 2  # Maximum number of calls per hour for free users
        self._tushare_call_count = 0  # Number of calls in the current hour
        self._tushare_call_times = deque()  # Queue that records call time (used for current limiting)

        # Interface rotation related properties
        self._rotation_sources = ["tushare", "akshare_eastmoney", "akshare_sina"]
        self._rotation_index = 0  # Current rotation index

        # Caching DataSourceManager instances (lazy loading, reuse throughout the service life cycle, avoiding rebuilding each time)
        self._dsm: Optional[DataSourceManager] = None

    def _get_dsm(self) -> DataSourceManager:
        """Return cached DataSourceManager instance (lazy loading)"""
        if self._dsm is None:
            self._dsm = DataSourceManager()
        return self._dsm

    @staticmethod
    def _normalize_stock_code(code: str) -> str:
        """
        Standardized stock code is 6 digits

        Handle the following situations:
        - sz000001 -> 000001
        - sh600036 -> 600036
        - 000001 -> 000001
        - 1 -> 000001

        Args:
            code: Original stock symbol

        Returns:
            str: Standardized 6-digit stock code
        """
        if not code:
            return ""

        code_str = str(code).strip()

        # If the code length exceeds 6 characters, remove the previous exchange prefix (such as sz, sh) 
        if len(code_str) > 6:
            # Extract all numeric characters
            code_str = ''.join(filter(str.isdigit, code_str))

        # If it is a pure number, complete it to 6 digits
        if code_str.isdigit():
            code_clean = code_str.lstrip('0') or '0'  # Remove leading 0s, if all 0s, keep one 0
            return code_clean.zfill(6)  # Complete to 6 digits

        # If it's not purely numeric, try to extract the numeric part
        code_digits = ''.join(filter(str.isdigit, code_str))
        if code_digits:
            return code_digits.zfill(6)

        # Unable to extract valid code, returns empty string
        return ""

    async def ensure_indexes(self) -> None:
        db = get_mongo_db()
        coll = db[self.collection_name]
        try:
            await coll.create_index("code", unique=True)
            await coll.create_index("updated_at")
        except Exception as e:
            logger.warning(f"Failed to create market index (ignored): {e}")

    async def _record_sync_status(
        self,
        success: bool,
        source: Optional[str] = None,
        records_count: int = 0,
        error_msg: Optional[str] = None
    ) -> None:
        """
        Record sync status

        Args:
            success: Is it successful?
            source: Data source name
            records_count: Record quantity
            error_msg: error message
        """
        try:
            db = get_mongo_db()
            status_coll = db[self.status_collection_name]

            now = datetime.now(self.tz)

            status_doc = {
                "job": "quotes_ingestion",
                "last_sync_time": now,
                "last_sync_time_iso": now.isoformat(),
                "success": success,
                "data_source": source,
                "records_count": records_count,
                "interval_seconds": settings.QUOTES_INGEST_INTERVAL_SECONDS,
                "error_message": error_msg,
                "updated_at": now,
            }

            await status_coll.update_one(
                {"job": "quotes_ingestion"},
                {"$set": status_doc},
                upsert=True
            )

        except Exception as e:
            logger.warning(f"Logging sync status failed (ignored): {e}")

    async def get_sync_status(self) -> Dict[str, any]:
        """
        Get sync status

        Returns:
            {
                "last_sync_time": "2025-10-28 15:06:00",
                "last_sync_time_iso": "2025-10-28T15:06:00+08:00",
                "interval_seconds": 360,
                "interval_minutes": 6,
                "data_source": "tushare",
                "success": True,
                "records_count": 5440,
                "error_message": None
            }
        """
        try:
            db = get_mongo_db()
            status_coll = db[self.status_collection_name]

            doc = await status_coll.find_one({"job": "quotes_ingestion"})

            if not doc:
                return {
                    "last_sync_time": None,
                    "last_sync_time_iso": None,
                    "interval_seconds": settings.QUOTES_INGEST_INTERVAL_SECONDS,
                    "interval_minutes": settings.QUOTES_INGEST_INTERVAL_SECONDS / 60,
                    "data_source": None,
                    "success": None,
                    "records_count": 0,
                    "error_message": "尚未执行过同步"
                }

            # Remove _id field
            doc.pop("_id", None)
            doc.pop("job", None)

            # Add minutes
            doc["interval_minutes"] = doc.get("interval_seconds", 0) / 60

            # 🔥 Format time (make sure to convert to local time zone)
            if "last_sync_time" in doc and doc["last_sync_time"]:
                dt = doc["last_sync_time"]
                # MongoDB Returns a datetime object in UTC time (aware or naive)
                # If it is naive, add UTC time zone; if it is aware, convert to local time zone
                if dt.tzinfo is None:
                    # naive datetime, Assume that UTC
                    dt = dt.replace(tzinfo=ZoneInfo("UTC"))
                # Convert to local time zone
                dt_local = dt.astimezone(self.tz)
                doc["last_sync_time"] = dt_local.strftime("%Y-%m-%d %H:%M:%S")

            return doc

        except Exception as e:
            logger.error(f"获取同步状态失败: {e}")
            return {
                "last_sync_time": None,
                "last_sync_time_iso": None,
                "interval_seconds": settings.QUOTES_INGEST_INTERVAL_SECONDS,
                "interval_minutes": settings.QUOTES_INGEST_INTERVAL_SECONDS / 60,
                "data_source": None,
                "success": None,
                "records_count": 0,
                "error_message": f"获取状态失败: {str(e)}"
            }

    def _check_tushare_permission(self) -> bool:
        """
        Detect Tushare rt_k interface permissions

        Returns:
            True: There is paid permission (can be called frequently)
            False: Free users (max 2 times per hour)
        """
        if self._tushare_permission_checked:
            return self._tushare_has_premium or False

        try:
            from app.services.data_sources.tushare_adapter import TushareAdapter
            adapter = TushareAdapter()

            if not adapter.is_available():
                logger.info("Tushare Not available, skip permission check")
                self._tushare_has_premium = False
                self._tushare_permission_checked = True
                return False

            # Try calling the rt_k interface to test permissions
            try:
                df = adapter._provider.api.rt_k(ts_code='000001.SZ')
                if df is not None and not getattr(df, 'empty', True):
                    logger.info("✅ Tushare rt_k interface permission detected (paid users)")
                    self._tushare_has_premium = True
                else:
                    logger.info("⚠️ Tushare rt_k The interface returns empty data (maybe free users or interface restrictions)")
                    self._tushare_has_premium = False
            except Exception as e:
                error_msg = str(e).lower()
                if "权限" in error_msg or "permission" in error_msg or "没有访问" in error_msg:
                    logger.info("⚠️ Tushare rt_k The interface has no permissions (free users)")
                    self._tushare_has_premium = False
                else:
                    logger.warning(f"⚠️ Tushare rt_k Interface test failed: {e}")
                    self._tushare_has_premium = False

            self._tushare_permission_checked = True
            return self._tushare_has_premium or False

        except Exception as e:
            logger.warning(f"Tushare Permission check failed: {e}")
            self._tushare_has_premium = False
            self._tushare_permission_checked = True
            return False

    async def _check_tushare_permission_async(self) -> bool:
        return await asyncio.to_thread(self._check_tushare_permission)

    async def _find_latest_trade_date_async(
        self,
        manager: DataSourceManager,
        preferred_sources: Optional[List[str]] = None,
    ) -> Optional[str]:
        return await asyncio.to_thread(manager.find_latest_trade_date_with_fallback, preferred_sources)

    async def _get_realtime_quotes_with_fallback_async(
        self,
        manager: DataSourceManager,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        return await asyncio.to_thread(manager.get_realtime_quotes_with_fallback)

    def _can_call_tushare(self) -> bool:
        """
        Determine whether the Tushare rt_k interface can be called

        Returns:
            True: Can be called
            False: Exceeds the limit and cannot be called
        """
        # If you are a paid user, there is no limit on the number of calls
        if self._tushare_has_premium:
            return True

        # Free users: Check the number of calls per hour
        now = datetime.now(self.tz)
        one_hour_ago = now - timedelta(hours=1)

        # Clear records from 1 hour ago
        while self._tushare_call_times and self._tushare_call_times[0] < one_hour_ago:
            self._tushare_call_times.popleft()

        # Check if limit is exceeded
        if len(self._tushare_call_times) >= self._tushare_hourly_limit:
            logger.warning(
                f"⚠️ Tushare rt_k The interface has reached the hourly call limit ({self._tushare_hourly_limit}times), "
                f"Skip this call and use the AKShare alternative interface"
            )
            return False

        return True

    def _record_tushare_call(self) -> None:
        """Record Tushare call time"""
        self._tushare_call_times.append(datetime.now(self.tz))

    def _get_next_source(self) -> Tuple[str, Optional[str]]:
        """
        Get the next data source (rotation mechanism)

        Returns:
            (source_type, akshare_api):
                - source_type: "tushare" | "akshare"
                - akshare_api: "eastmoney" | "sina" (only if source_type="akshare" valid when)
        """
        if not settings.QUOTES_ROTATION_ENABLED:
            # Rotation is not enabled, using default priority (AKShare Eastern Fortune)
            return "akshare", "eastmoney"

        # Rotation logic: AKShare Oriental Fortune ↔ AKShare Sina Finance (Tushare has been removed)
        current_source = self._rotation_sources[self._rotation_index]

        # Update rotation index (use next interface next time)
        self._rotation_index = (self._rotation_index + 1) % len(self._rotation_sources)

        if current_source == "akshare_eastmoney":
            return "akshare", "eastmoney"
        else:  # akshare_sina
            return "akshare", "sina"

    def _is_trading_time(self, now: Optional[datetime] = None) -> bool:
        """
        Determine whether it is during trading hours or post-closing buffer period

        Trading hours:
        - Morning:9:30-11:30
        - Afternoon:13:00-15:00
        - Post-closing buffer period:15:00-15:30 (Make sure to get the closing price)

        Description of the post-closing buffer period:
        - Continue to obtain for 30 minutes after the trading time ends
        - Assuming once every 6 minutes, 3 more synchronization opportunities can be added (15:06, 15:12, 15:18) 
        - Greatly reduces the risk of missing the closing price
        """
        now = now or datetime.now(self.tz)
        # working day Mon-Fri
        if now.weekday() > 4:
            return False
        t = now.time()
        # Shanghai Stock Exchange/Shenzhen Stock Exchange regular trading hours
        morning = dtime(9, 30)
        noon = dtime(11, 30)
        afternoon_start = dtime(13, 0)
        # Post-closing buffer period (extended by 30 minutes to 15:30) 
        buffer_end = dtime(15, 30)

        return (morning <= t <= noon) or (afternoon_start <= t <= buffer_end)

    async def _collection_empty(self) -> bool:
        db = get_mongo_db()
        coll = db[self.collection_name]
        try:
            count = await coll.estimated_document_count()
            return count == 0
        except Exception:
            return True

    async def _collection_stale(self, latest_trade_date: Optional[str]) -> bool:
        if not latest_trade_date:
            return False
        db = get_mongo_db()
        coll = db[self.collection_name]
        try:
            cursor = coll.find({}, {"trade_date": 1}).sort("trade_date", -1).limit(1)
            docs = await cursor.to_list(length=1)
            if not docs:
                return True
            doc_td = str(docs[0].get("trade_date") or "")
            return doc_td < str(latest_trade_date)
        except Exception:
            return True

    async def _bulk_upsert(self, quotes_map: Dict[str, Dict], trade_date: str, source: Optional[str] = None) -> None:
        db = get_mongo_db()
        coll = db[self.collection_name]
        ops = []
        updated_at = datetime.now(self.tz)
        for code, q in quotes_map.items():
            if not code:
                continue
            # Use a standardized approach to stock symbols (removing the exchange prefix, e.g. sz000001 -> 000001) 
            code6 = self._normalize_stock_code(code)
            if not code6:
                continue

            # 🔥 Log: record the written volume value
            volume = q.get("volume")
            if code6 in ["300750", "000001", "600000"]:  # Only record a few example stocks
                logger.info(f"📊 [write market_quotes] {code6} - volume={volume}, amount={q.get('amount')}, source={source}")

            ops.append(
                UpdateOne(
                    {"code": code6},
                    {"$set": {
                        "code": code6,
                        "symbol": code6,  # Add symbol field to be consistent with code
                        "close": q.get("close"),
                        "pct_chg": q.get("pct_chg"),
                        "amount": q.get("amount"),
                        "volume": volume,
                        "open": q.get("open"),
                        "high": q.get("high"),
                        "low": q.get("low"),
                        "pre_close": q.get("pre_close"),
                        "trade_date": trade_date,
                        "updated_at": updated_at,
                    }},
                    upsert=True,
                )
            )
        if not ops:
            logger.info("No data to write, skip")
            return
        result = await coll.bulk_write(ops, ordered=False)
        logger.info(
            f"✅ Quotation storage completed source={source}, matched={result.matched_count}, upserted={len(result.upserted_ids) if result.upserted_ids else 0}, modified={result.modified_count}"
        )

    async def backfill_from_historical_data(self) -> None:
        """
        Import the previous day s closing data from the historical data collection to market_quotes
        - If the market_quotes collection is empty, import all data
        - If market_quotes collection is not empty, check and fix missing volume field
        """
        try:
            # Check if market_quotes is empty
            is_empty = await self._collection_empty()

            if not is_empty:
                # The collection is not empty, check whether there are records with missing trading volume
                logger.info("✅ market_quotes The collection is not empty, check if the volume needs to be fixed...")
                await self._fix_missing_volume()
                return

            logger.info("📊 market_quotes The collection is empty, start importing from historical data")

            db = get_mongo_db()
            manager = self._get_dsm()

            # Get the latest trading day
            try:
                latest_trade_date = await self._find_latest_trade_date_async(manager)
                if not latest_trade_date:
                    logger.warning("⚠️ Unable to obtain the latest trading day, skipping historical data import")
                    return
            except Exception as e:
                logger.warning(f"⚠️ Failed to get latest trading day: {e}, Skip historical data import")
                return

            logger.info(f"📊 从历史数据集合导入 {latest_trade_date} 的收盘数据到 market_quotes")

            # Query the latest trading day data from the stock_daily_quotes collection
            daily_quotes_collection = db["stock_daily_quotes"]
            cursor = daily_quotes_collection.find({
                "trade_date": latest_trade_date,
                "period": "daily"
            })

            docs = await cursor.to_list(length=None)

            if not docs:
                logger.warning(f"⚠️ 历史数据集合中未找到 {latest_trade_date} 的数据")
                logger.warning("⚠️ market_quotes and historical data collections are empty, please synchronize historical data or real-time quotes first")
                return

            logger.info(f"✅ 从历史数据集合找到 {len(docs)} 条记录")

            # Convert to quotes_map format
            quotes_map = {}
            for doc in docs:
                code = doc.get("symbol") or doc.get("code")
                if not code:
                    continue
                code6 = str(code).zfill(6)

                # 🔥 To get the trading volume, use the volume field first
                volume_value = doc.get("volume") or doc.get("vol")
                data_source = doc.get("data_source", "")

                # 🔥 Log: record the original volume value
                if code6 in ["300750", "000001", "600000"]:  # Only record a few example stocks
                    logger.info(f"📊 [回填] {code6} - volume={doc.get('volume')}, vol={doc.get('vol')}, data_source={data_source}")

                quotes_map[code6] = {
                    "close": doc.get("close"),
                    "pct_chg": doc.get("pct_chg"),
                    "amount": doc.get("amount"),
                    "volume": volume_value,
                    "open": doc.get("open"),
                    "high": doc.get("high"),
                    "low": doc.get("low"),
                    "pre_close": doc.get("pre_close"),
                }

            if quotes_map:
                await self._bulk_upsert(quotes_map, latest_trade_date, "historical_data")
                logger.info(f"✅ 成功从历史数据导入 {len(quotes_map)} 条收盘数据到 market_quotes")
            else:
                logger.warning("⚠️ Historical data is empty after conversion and cannot be imported.")

        except Exception as e:
            logger.error(f"❌ 从历史数据导入失败: {e}")
            import traceback
            logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")

    async def backfill_last_close_snapshot(self) -> None:
        """Complement the last closing snapshot at once (for cold start or data staleness). Calls are allowed during the off-market period."""
        try:
            manager = self._get_dsm()
            # Use near-real-time snapshots as a back-up, and the last closing data returned during the off-market period is
            quotes_map, source = await self._get_realtime_quotes_with_fallback_async(manager)
            if not quotes_map:
                logger.warning("backfill: Market data not obtained, skip")
                return
            try:
                trade_date = await self._find_latest_trade_date_async(manager) or datetime.now(self.tz).strftime("%Y%m%d")
            except Exception:
                trade_date = datetime.now(self.tz).strftime("%Y%m%d")
            await self._bulk_upsert(quotes_map, trade_date, source)
        except Exception as e:
            logger.error(f"❌ backfill Quotation replenishment failed: {e}")

    async def backfill_last_close_snapshot_if_needed(self) -> None:
        """If the set is empty or trade_date lags behind the latest trading day, execute once backfill"""
        try:
            is_empty = await self._collection_empty()

            # If the collection is empty, priority is given to importing from historical data.
            if is_empty:
                logger.info("🔁 market_quotes The collection is empty, try to import from historical data")
                await self.backfill_from_historical_data()
                return

            # If the collection is not empty but the data is stale, use the real-time interface to update
            manager = self._get_dsm()
            latest_td = await self._find_latest_trade_date_async(manager)
            if await self._collection_stale(latest_td):
                logger.info("🔁 Trigger off/start period backfill to populate latest closing data")
                await self.backfill_last_close_snapshot()
        except Exception as e:
            logger.warning(f"backfill Trigger check failed (ignored): {e}")

    def _fetch_quotes_from_source(self, source_type: str, akshare_api: Optional[str] = None) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Get quotes from specified data source

        Args:
            source_type: "tushare" | "akshare"
            akshare_api: "eastmoney" | "sina" (only if source_type="akshare" valid when)

        Returns:
            (quotes_map, source_name)
        """
        try:
            if source_type == "tushare":
                # 🔥 The Tushare real-time market interface call has been disabled and is managed by the scheduled task run_tushare_realtime_quotes_hourly
                # Avoid conflict with the scheduled task of 31 minutes per hour (free users can only call it once per hour)
                logger.info("⏸️ Tushare The real-time market interface has been disabled and the call is skipped (managed by scheduled tasks)")
                return None, None

            elif source_type == "akshare":
                from app.services.data_sources.akshare_adapter import AKShareAdapter
                adapter = AKShareAdapter()

                if not adapter.is_available():
                    logger.warning("AKShare 不可用")
                    return None, None

                api_name = akshare_api or "eastmoney"
                logger.info(f"📊 使用 AKShare {api_name} 接口获取实时行情")
                quotes_map = adapter.get_realtime_quotes(source=api_name)

                if quotes_map:
                    return quotes_map, f"akshare_{api_name}"
                else:
                    logger.warning(f"AKShare {api_name} 返回空数据")
                    return None, None

            else:
                logger.error(f"未知数据源类型: {source_type}")
                return None, None

        except Exception as e:
            logger.error(f"从 {source_type} 获取行情失败: {e}")
            return None, None

    async def run_once(self) -> None:
        """
        Execute one collection and storage

        Core logic:
        1. Detecting Tushare permissions (first run)
        2. Try to get quotes in rotating order:Tushare → AKShare Oriental Fortune → AKShare Sina Finance
        3. If any interface succeeds, it will be included in the database. If it fails, the collection will be skipped.
        """
        # Processing during non-trading hours
        if not self._is_trading_time():
            if settings.QUOTES_BACKFILL_ON_OFFHOURS:
                await self.backfill_last_close_snapshot_if_needed()
            else:
                logger.info("⏭️ During non-trading hours, skip market collection")
            return

        try:
            # First run: Detecting Tushare permissions
            if settings.QUOTES_AUTO_DETECT_TUSHARE_PERMISSION and not self._tushare_permission_checked:
                logger.info("🔍 First run, check Tushare rt_k interface permissions...")
                has_premium = await self._check_tushare_permission_async()

                if has_premium:
                    logger.info(
                        "✅ Tushare paid permission detected! It is recommended to set QUOTES_INGEST_INTERVAL_SECONDS to 5-60 seconds to fully utilize the permissions"
                    )
                else:
                    logger.info(
                        f"ℹ️ Tushare 免费用户，每小时最多调用 {self._tushare_hourly_limit} 次 rt_k 接口。"
                        f"Current collection interval: {settings.QUOTES_INGEST_INTERVAL_SECONDS} seconds"
                    )

            # Get next data source
            source_type, akshare_api = self._get_next_source()

            # Synchronizing the third-party market interface may block for a long time; put it in a thread and add a timeout to avoid blocking the entire event loop.
            try:
                quotes_map, source_name = await asyncio.wait_for(
                    asyncio.to_thread(self._fetch_quotes_from_source, source_type, akshare_api),
                    timeout=REALTIME_QUOTES_FETCH_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                source_hint = source_type if source_type != "akshare" else f"akshare_{akshare_api or 'eastmoney'}"
                logger.error(
                    "❌ Timeout for obtaining real-time quotes: source=%s, timeout=%ss",
                    source_hint,
                    REALTIME_QUOTES_FETCH_TIMEOUT_SECONDS,
                )
                await self._record_sync_status(
                    success=False,
                    source=source_hint,
                    records_count=0,
                    error_msg=f"获取实时行情超时（>{REALTIME_QUOTES_FETCH_TIMEOUT_SECONDS}s）",
                )
                return

            if not quotes_map:
                logger.warning(f"⚠️ {source_name or source_type} No market data was obtained, skip this warehousing.")
                # Logging failure status
                await self._record_sync_status(
                    success=False,
                    source=source_name or source_type,
                    records_count=0,
                    error_msg="未获取到行情数据"
                )
                return

            # Get trading day
            try:
                manager = self._get_dsm()
                trade_date = await self._find_latest_trade_date_async(manager) or datetime.now(self.tz).strftime("%Y%m%d")
            except Exception:
                trade_date = datetime.now(self.tz).strftime("%Y%m%d")

            # Warehouse
            await self._bulk_upsert(quotes_map, trade_date, source_name)

            # Record success status
            await self._record_sync_status(
                success=True,
                source=source_name,
                records_count=len(quotes_map),
                error_msg=None
            )

        except Exception as e:
            logger.error(f"❌ 行情入库失败: {e}")
            # Logging failure status
            await self._record_sync_status(
                success=False,
                source=None,
                records_count=0,
                error_msg=str(e)
            )


# === basics_sync_service.py ===
"""
Stock basics synchronization service
- Fetches A-share stock basic info from Tushare
- Enriches with latest market cap (total_mv)
- Upserts into MongoDB collection `stock_basic_info`
- Persists status in collection `sync_status` with key `stock_basics`
- Provides a singleton accessor for reuse across routers/scheduler

This module is async-friendly and offloads blocking IO (Tushare/pandas) to a thread.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = AsyncIOMotorDatabase = AsyncIOMotorCollection = object
try:
    from pymongo import UpdateOne
except ImportError:
    from unittest.mock import MagicMock as _MM; BulkWriteResult = UpdateOne = InsertOne = DeleteOne = MongoClient = Database = ASCENDING = DESCENDING = ReturnDocument = _MM()
    DuplicateKeyError = PyMongoError = OperationFailure = ServerSelectionTimeoutError = ConnectionFailure = Exception

from app.core.database import get_mongo_db
from app.core.config import settings

logger = logging.getLogger(__name__)

STATUS_COLLECTION = "sync_status"
DATA_COLLECTION = "stock_basic_info"
JOB_KEY = "stock_basics"


@dataclass
class SyncStats:
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    status: str = "idle"  # idle|running|success|failed
    total: int = 0
    inserted: int = 0
    updated: int = 0
    errors: int = 0
    message: str = ""
    last_trade_date: Optional[str] = None  # YYYYMMDD


class BasicsSyncService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._running = False
        self._last_status: Optional[Dict[str, Any]] = None
        self._indexes_ensured = False

    async def _try_mark_running(self, force: bool = False) -> bool:
        async with self._lock:
            if self._running and not force:
                return False
            self._running = True
            return True

    async def start_full_sync(self, force: bool = False) -> Dict[str, Any]:
        """Starts a background sync task and returns it to running status immediately."""
        if not await self._try_mark_running(force=force):
            logger.info("Stock basics sync already running; skip start")
            return await self.get_status()

        db = get_mongo_db()

        await self._ensure_indexes(db)

        stats = SyncStats()
        stats.started_at = datetime.utcnow().isoformat()
        stats.status = "running"
        stats.message = "Synchronization task started"
        await self._persist_status(db, stats.__dict__.copy())

        asyncio.create_task(self._run_full_sync_impl(db, stats))
        return stats.__dict__.copy()

    async def _ensure_indexes(self, db: AsyncIOMotorDatabase) -> None:
        """确保必要的索引存在"""
        if self._indexes_ensured:
            return

        try:
            collection = db[DATA_COLLECTION]
            logger.info("📊 Check and create basic stock information index...")

            # 1. Composite unique index: ticker symbol+Data source (for upsert)
            await collection.create_index([
                ("code", 1),
                ("source", 1)
            ], unique=True, name="code_source_unique", background=True)

            # 2. Stock symbol index (query all data sources)
            await collection.create_index([("code", 1)], name="code_index", background=True)

            # 3. Data source index (filter by data source)
            await collection.create_index([("source", 1)], name="source_index", background=True)

            # 4. Stock name index (search by name)
            await collection.create_index([("name", 1)], name="name_index", background=True)

            # 5. Industry Index (filter by industry)
            await collection.create_index([("industry", 1)], name="industry_index", background=True)

            # 6. Market Index (filter by market)
            await collection.create_index([("market", 1)], name="market_index", background=True)

            # 7. Total market capitalization index (sorted by market capitalization)
            await collection.create_index([("total_mv", -1)], name="total_mv_desc", background=True)

            # 8. Circulation market capitalization index (sorted by circulation market capitalization)
            await collection.create_index([("circ_mv", -1)], name="circ_mv_desc", background=True)

            # 9. Update time index (data maintenance)
            await collection.create_index([("updated_at", -1)], name="updated_at_desc", background=True)

            # 10. PE Index (filter by valuation)
            await collection.create_index([("pe", 1)], name="pe_index", background=True)

            # 11. PB Index (filter by valuation)
            await collection.create_index([("pb", 1)], name="pb_index", background=True)

            # 12. Turnover rate index (filtered by activity)
            await collection.create_index([("turnover_rate", -1)], name="turnover_rate_desc", background=True)

            self._indexes_ensured = True
            logger.info("✅ Basic stock information index check completed")
        except Exception as e:
            # Index creation failure should not prevent the service from starting
            logger.warning(f"⚠️ Warning when creating index (may already exist): {e}")

    async def get_status(self, db: Optional[AsyncIOMotorDatabase] = None) -> Dict[str, Any]:
        """Return last persisted status; falls back to in-memory snapshot."""
        try:
            db = db or get_mongo_db()
            doc = await db[STATUS_COLLECTION].find_one({"job": JOB_KEY})
            if doc:
                doc.pop("_id", None)
                return doc
        except Exception as e:
            logger.warning(f"Failed to load sync status from DB: {e}")
        return self._last_status or {"job": JOB_KEY, "status": "idle"}

    async def _persist_status(self, db: AsyncIOMotorDatabase, stats: Dict[str, Any]) -> None:
        stats["job"] = JOB_KEY
        await db[STATUS_COLLECTION].update_one({"job": JOB_KEY}, {"$set": stats}, upsert=True)
        self._last_status = {k: v for k, v in stats.items() if k != "_id"}

    async def _execute_bulk_write_with_retry(
        self,
        db: AsyncIOMotorDatabase,
        operations: List,
        max_retries: int = 3
    ) -> tuple:
        """
        Perform batch writes with retry mechanism (thread-safe)

        Args:
            db: MongoDB Database instance
            operations: Bulk operation list
            max_retries: Maximum number of retries

        Returns:
            (New quantity, Update quantity)
        """
        try:
            # 🔥 Use thread-safe bulk_write
            from app.utils.thread_safe_db import safe_bulk_write

            result = await safe_bulk_write(
                collection_name=DATA_COLLECTION,
                operations=operations,
                ordered=False,
                async_db=db,
                max_retries=max_retries
            )

            inserted = len(result.upserted_ids) if result.upserted_ids else 0
            updated = result.modified_count or 0
            logger.debug(f"✅ 批量写入成功: 新增 {inserted}, 更新 {updated}")
            return inserted, updated

        except Exception as e:
            logger.error(f"❌ 批量写入失败: {e}")
            return 0, 0

    async def run_full_sync(self, force: bool = False) -> Dict[str, Any]:
        """Run a full sync. If already running, return current status unless force."""
        if not await self._try_mark_running(force=force):
            logger.info("Stock basics sync already running; skip start")
            return await self.get_status()

        db = get_mongo_db()

        # 🔥 Make sure the index exists (improves query and upsert performance)
        await self._ensure_indexes(db)

        stats = SyncStats()
        stats.started_at = datetime.utcnow().isoformat()
        stats.status = "running"
        await self._persist_status(db, stats.__dict__.copy())

        return await self._run_full_sync_impl(db, stats)

    async def _run_full_sync_impl(
        self,
        db: AsyncIOMotorDatabase,
        stats: SyncStats,
    ) -> Dict[str, Any]:
        """Execute real synchronization logic; reused by synchronization entrance and background task entrance."""

        try:
            # 🔧 Remove TUSHARE_ENABLED check to be consistent with financial data and historical data synchronization
            # Only check the Tushare connection status and report an error if the connection fails.
            # Note: If you need multiple data source support, please use MultiSourceBasicsSyncService

            # Step 1: Fetch stock basic list from Tushare (blocking -> thread)
            stock_df = await asyncio.to_thread(self._fetch_stock_basic_df)
            if stock_df is None or getattr(stock_df, "empty", True):
                raise RuntimeError("Tushare returned empty stock_basic list")

            # Step 2: Determine latest trade_date and fetch daily_basic for financial metrics (blocking -> thread)
            latest_trade_date = await asyncio.to_thread(self._find_latest_trade_date)
            stats.last_trade_date = latest_trade_date
            daily_data_map = await asyncio.to_thread(self._fetch_daily_basic_mv_map, latest_trade_date)

            # Step 2b: Fetch latest ROE snapshot from fina_indicator (blocking -> thread)
            roe_map = await asyncio.to_thread(self._fetch_latest_roe_map)

            # Step 3: Upsert into MongoDB (batched bulk writes)
            ops: List[UpdateOne] = []
            now_iso = datetime.utcnow().isoformat()
            for _, row in stock_df.iterrows():  # type: ignore
                name = row.get("name") or ""
                area = row.get("area") or ""
                industry = row.get("industry") or ""
                market = row.get("market") or ""
                list_date = row.get("list_date") or ""
                ts_code = row.get("ts_code") or ""

                # Extract 6-digit stock code from ts_code (e.g., "000001.SZ" -> "000001")
                if isinstance(ts_code, str) and "." in ts_code:
                    code = ts_code.split(".")[0]  # Keep the 6-digit format
                else:
                    # Fallback to symbol with zero-padding if ts_code is invalid
                    symbol = row.get("symbol") or ""
                    code = str(symbol).zfill(6) if symbol else ""

                # Determine the exchange based on ts_code
                if isinstance(ts_code, str):
                    if ts_code.endswith(".SH"):
                        sse = "上海证券交易所"
                    elif ts_code.endswith(".SZ"):
                        sse = "深圳证券交易所"
                    elif ts_code.endswith(".BJ"):
                        sse = "北京证券交易所"
                    else:
                        sse = "未知"
                else:
                    sse = "未知"

                category = "stock_cn"

                # Extract daily financial metrics - use ts_code directly for matching
                daily_metrics = {}
                if isinstance(ts_code, str) and ts_code in daily_data_map:
                    daily_metrics = daily_data_map[ts_code]

                # Process market cap (convert from Ten thousand yuan to billion yuan)
                total_mv_yi = None
                circ_mv_yi = None
                if "total_mv" in daily_metrics:
                    try:
                        total_mv_yi = float(daily_metrics["total_mv"]) / 10000.0
                    except Exception:
                        pass
                if "circ_mv" in daily_metrics:
                    try:
                        circ_mv_yi = float(daily_metrics["circ_mv"]) / 10000.0
                    except Exception:
                        pass

                # Generate full_symbol (full normalized code)
                full_symbol = self._generate_full_symbol(code)

                doc = {
                    "code": code,
                    "symbol": code,  # Add symbol field (standardized field)
                    "name": name,
                    "area": area,
                    "industry": industry,
                    "market": market,
                    "list_date": list_date,
                    "sse": sse,
                    "sec": category,
                    "source": "tushare",  # 🔥 Data source identifier
                    "updated_at": now_iso,
                    "full_symbol": full_symbol,  # Add full standardized code
                }

                # Add market cap fields
                if total_mv_yi is not None:
                    doc["total_mv"] = total_mv_yi
                if circ_mv_yi is not None:
                    doc["circ_mv"] = circ_mv_yi

                # Add financial ratios (🔥 Added ps, ps_ttm and dividend rate)
                for field in ["pe", "pb", "ps", "pe_ttm", "pb_mrq", "ps_ttm"]:
                    if field in daily_metrics:
                        doc[field] = daily_metrics[field]
                for source_field, target_field in {"dv_ratio": "dividend_yield", "dv_ttm": "dividend_yield_ttm"}.items():
                    if source_field in daily_metrics:
                        doc[target_field] = daily_metrics[source_field]
                # ROE from fina_indicator snapshot
                if isinstance(ts_code, str) and ts_code in roe_map:
                    roe_val = roe_map[ts_code].get("roe")
                    if roe_val is not None:
                        doc["roe"] = roe_val

                # Add trading metrics
                for field in ["turnover_rate", "volume_ratio"]:
                    if field in daily_metrics:
                        doc[field] = daily_metrics[field]

                # 🔥 Add share capital fields (total_share, float_share)
                for field in ["total_share", "float_share"]:
                    if field in daily_metrics:
                        doc[field] = daily_metrics[field]

                # 🔥 Use (code, source) Union query conditions
                ops.append(
                    UpdateOne({"code": code, "source": "tushare"}, {"$set": doc}, upsert=True)
                )

            inserted = 0
            updated = 0
            errors = 0
            # Execute in chunks to avoid oversized batches
            BATCH = 1000
            for i in range(0, len(ops), BATCH):
                batch = ops[i : i + BATCH]
                batch_inserted, batch_updated = await self._execute_bulk_write_with_retry(db, batch)

                if batch_inserted > 0 or batch_updated > 0:
                    inserted += batch_inserted
                    updated += batch_updated
                else:
                    errors += 1
                    logger.error(f"Bulk write error on batch {i//BATCH}")

            stats.total = len(ops)
            stats.inserted = inserted
            stats.updated = updated
            stats.errors = errors
            stats.status = "success" if errors == 0 else "success_with_errors"
            stats.finished_at = datetime.utcnow().isoformat()
            await self._persist_status(db, stats.__dict__.copy())
            logger.info(
                f"Stock basics sync finished: total={stats.total} inserted={inserted} updated={updated} errors={errors} trade_date={latest_trade_date}"
            )
            return stats.__dict__

        except Exception as e:
            stats.status = "failed"
            stats.message = str(e)
            stats.finished_at = datetime.utcnow().isoformat()
            await self._persist_status(db, stats.__dict__.copy())
            logger.exception(f"Stock basics sync failed: {e}")
            return stats.__dict__
        finally:
            async with self._lock:
                self._running = False

    # ---- Blocking helpers (run in thread) ----
    def _fetch_stock_basic_df(self):
        """Delegate to blocking implementation of basics_sync.utils"""
        return _fetch_stock_basic_df_util()

    def _find_latest_trade_date(self) -> str:
        """Delegate to basics_sync.utils (blocking)"""
        return _find_latest_trade_date_util()

    def _fetch_daily_basic_mv_map(self, trade_date: str) -> Dict[str, Dict[str, float]]:
        """Delegate to basics_sync.utils (blocking)"""
        return _fetch_daily_basic_mv_map_util(trade_date)

    def _fetch_latest_roe_map(self) -> Dict[str, Dict[str, float]]:
        """Delegate to basics_sync.utils (blocking)"""
        return _fetch_latest_roe_map_util()

    def _generate_full_symbol(self, code: str) -> str:
        """
        Generate complete standardized code based on stock symbol

        Args:
            code: 6 stock code

        Returns:
            Full normalized code (e.g. 000001.SZ), or original code returned if the code is invalid (make sure it is not empty)
        """
        # Make sure code is not empty
        if not code:
            return ""

        # Normalize to string and remove spaces
        code = str(code).strip()

        # If the length is not 6, return the original code (avoid returning None)
        if len(code) != 6:
            return code

        # Determine the exchange based on the code
        if code.startswith(('60', '68', '90')):
            return f"{code}.SS"  # Shanghai Stock Exchange
        elif code.startswith(('00', '30', '20')):
            return f"{code}.SZ"  # Shenzhen Stock Exchange
        elif code.startswith(('8', '4')):
            return f"{code}.BJ"  # Beijing Stock Exchange
        else:
            # Unrecognized code, return original code (make sure it is not empty)
            return code if code else ""


# Singleton accessor
_basics_sync_service: Optional[BasicsSyncService] = None


def get_basics_sync_service() -> BasicsSyncService:
    global _basics_sync_service
    if _basics_sync_service is None:
        _basics_sync_service = BasicsSyncService()
    return _basics_sync_service


# === multi_source_basics_sync_service.py ===
"""
Multi-source stock basics synchronization service
- Supports multiple data sources with fallback mechanism
- Priority: Tushare > AKShare > BaoStock 
- Fetches A-share stock basic info with extended financial metrics
- Upserts into MongoDB collection `stock_basic_info`
- Provides unified interface for different data sources
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = AsyncIOMotorDatabase = AsyncIOMotorCollection = object
try:
    from pymongo import UpdateOne
except ImportError:
    from unittest.mock import MagicMock as _MM; BulkWriteResult = UpdateOne = InsertOne = DeleteOne = MongoClient = Database = ASCENDING = DESCENDING = ReturnDocument = _MM()
    DuplicateKeyError = PyMongoError = OperationFailure = ServerSelectionTimeoutError = ConnectionFailure = Exception

from app.core.database import get_mongo_db


logger = logging.getLogger(__name__)

# Collection names
COLLECTION_NAME = "stock_basic_info"
STATUS_COLLECTION = "sync_status"
JOB_KEY = "stock_basics_multi_source"
STOCK_LIST_FETCH_TIMEOUT_SECONDS = 45


class DataSourcePriority(Enum):
    """数据源优先级枚举"""
    TUSHARE = 1
    AKSHARE = 2
    BAOSTOCK = 3


@dataclass
class SyncStats:
    """同步统计信息"""
    job: str = JOB_KEY
    data_type: str = "stock_basics"  # Add data_type field to comply with database indexing requirements
    status: str = "idle"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    total: int = 0
    inserted: int = 0
    updated: int = 0
    errors: int = 0
    last_trade_date: Optional[str] = None
    data_sources_used: List[str] = field(default_factory=list)
    source_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    message: Optional[str] = None


class MultiSourceBasicsSyncService:
    """Multi-data source stock basic information synchronization service"""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._running = False
        self._last_status: Optional[Dict[str, Any]] = None
        self._current_task: Optional[asyncio.Task] = None

    async def start_background_sync(self, force: bool = False, preferred_sources: List[str] = None) -> Dict[str, Any]:
        """Start the synchronization task in the background and immediately return to the current state to avoid blocking front-end requests."""
        async with self._lock:
            if self._running:
                status = await self.get_status()
                status["launch_mode"] = "already_running"
                return status

            loop = asyncio.get_running_loop()
            self._current_task = loop.create_task(
                self.run_full_sync(force=force, preferred_sources=preferred_sources)
            )

        status = {
            "job": JOB_KEY,
            "status": "queued",
            "message": "同步任务已提交到后台执行",
            "started_at": datetime.now().isoformat(),
            "launch_mode": "background",
            "preferred_sources": preferred_sources or [],
        }
        self._last_status = status
        return status

    async def _try_mark_running(self, force: bool = False) -> bool:
        async with self._lock:
            if self._running and not force:
                return False
            self._running = True
            return True

    async def start_full_sync(
        self,
        force: bool = False,
        preferred_sources: List[str] = None,
    ) -> Dict[str, Any]:
        """Starts a background sync task and returns it to running status immediately."""
        if not await self._try_mark_running(force=force):
            logger.info("Multi-source stock basics sync already running; skip start")
            return await self.get_status()

        db = get_mongo_db()
        stats = SyncStats()
        stats.started_at = datetime.now().isoformat()
        stats.status = "running"
        stats.message = "Synchronization task started"
        await self._persist_status(db, stats.__dict__.copy())

        asyncio.create_task(self._run_full_sync_impl(db, stats, preferred_sources))
        return stats.__dict__.copy()

    async def get_status(self) -> Dict[str, Any]:
        """获取同步状态"""
        if self._last_status and self._last_status.get("status") == "queued":
            return self._last_status

        db = get_mongo_db()
        doc = await db[STATUS_COLLECTION].find_one({"job": JOB_KEY})
        
        if doc:
            # Remove MongoDB's _id field to avoid serialization issues
            doc.pop("_id", None)
            
            # 🔥 Detect zombie tasks: If the status is running but it has been more than 30 minutes, it will be automatically marked as timed out.
            if doc.get("status") == "running":
                started_at_str = doc.get("started_at")
                if started_at_str:
                    try:
                        started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
                        # If started_at has zone information, convert to local time
                        if started_at.tzinfo:
                            started_at = started_at.astimezone().replace(tzinfo=None)
                        
                        # Check if more than 30 minutes have passed
                        elapsed = datetime.now() - started_at
                        if elapsed > timedelta(minutes=30):
                            logger.warning(
                                f"⚠️ 检测到僵尸任务: {JOB_KEY} 已运行 {elapsed.total_seconds() / 60:.1f} 分钟，"
                                f"Automatically marked as timeout failure"
                            )
                            # Update status is failed
                            doc["status"] = "failed"
                            doc["message"] = f"任务超时（运行时间超过30分钟，实际运行 {elapsed.total_seconds() / 60:.1f} 分钟）"
                            doc["finished_at"] = datetime.now().isoformat()
                            
                            # Save updated status
                            await self._persist_status(db, doc)
                    except Exception as e:
                        logger.error(f"❌ 检测僵尸任务时出错: {e}")
            
            # Update memory cache
            self._last_status = doc
            return doc
        
        return {"job": JOB_KEY, "status": "never_run"}

    async def _persist_status(self, db: AsyncIOMotorDatabase, stats: Dict[str, Any]) -> None:
        """持久化同步状态"""
        stats["job"] = JOB_KEY

        # Use upsert to avoid duplicate key errors
        # Update or insert based on data_type and job
        filter_query = {
            "data_type": stats.get("data_type", "stock_basics"),
            "job": JOB_KEY
        }

        await db[STATUS_COLLECTION].update_one(
            filter_query,
            {"$set": stats},
            upsert=True
        )

        self._last_status = {k: v for k, v in stats.items() if k != "_id"}

    async def _execute_bulk_write_with_retry(
        self,
        db: AsyncIOMotorDatabase,
        operations: List,
        max_retries: int = 3
    ) -> Tuple[int, int]:
        """
        Perform batch writes with retry mechanism (thread-safe)

        Args:
            db: MongoDB Database instance
            operations: Bulk operation list
            max_retries: Maximum number of retries

        Returns:
            (New quantity, Update quantity)
        """
        try:
            # 🔥 Use thread-safe bulk_write
            from app.utils.thread_safe_db import safe_bulk_write

            result = await safe_bulk_write(
                collection_name=COLLECTION_NAME,
                operations=operations,
                ordered=False,
                async_db=db,
                max_retries=max_retries
            )

            inserted = result.upserted_count
            updated = result.modified_count
            logger.debug(f"✅ 批量写入成功: 新增 {inserted}, 更新 {updated}")
            return inserted, updated

        except Exception as e:
            logger.error(f"❌ 批量写入失败: {e}")
            return 0, 0

    async def run_full_sync(self, force: bool = False, preferred_sources: List[str] = None) -> Dict[str, Any]:
        """
        Run a full sync

        Args:
            force: Whether to force it to run (even if it is already running)
            preferred_sources: List of preferred data sources to use
        """
        if not await self._try_mark_running(force=force):
            logger.info("Multi-source stock basics sync already running; skip start")
            return await self.get_status()

        db = get_mongo_db()
        stats = SyncStats()
        stats.started_at = datetime.now().isoformat()
        stats.status = "running"
        await self._persist_status(db, stats.__dict__.copy())

        return await self._run_full_sync_impl(db, stats, preferred_sources)

    @staticmethod
    def _normalize_preferred_sources(preferred_sources: Optional[List[str]]) -> Optional[List[str]]:
        if not preferred_sources:
            return preferred_sources

        normalized: List[str] = []
        removed_sources: List[str] = []
        for source in preferred_sources:
            source_name = str(source or "").strip().lower()
            if not source_name:
                continue
            if source_name == "qmt":
                removed_sources.append(source_name)
                continue
            if source_name not in normalized:
                normalized.append(source_name)

        if removed_sources:
            logger.info(
                "🧹 [Synchronization of basic information from multiple data sources] Sources unsuitable for underlying information to initiate synchronization have been excluded from priority data sources: %s",
                removed_sources,
            )
        return normalized or None

    async def _fetch_stock_list_with_retry(
        self,
        manager,
        preferred_sources: Optional[List[str]],
    ) -> Tuple[Any, Optional[str]]:
        async def _fetch_once(sources: Optional[List[str]], attempt_label: str) -> Tuple[Any, Optional[str]]:
            start = time.perf_counter()
            logger.info(
                "📥 [Synchronization of basic information from multiple data sources] Start getting stock list: attempt=%s, preferred_sources=%s, timeout=%ss",
                attempt_label,
                sources or [],
                STOCK_LIST_FETCH_TIMEOUT_SECONDS,
            )
            stock_df, source_used = await asyncio.wait_for(
                asyncio.to_thread(manager.get_stock_list_with_fallback, sources, True),
                timeout=STOCK_LIST_FETCH_TIMEOUT_SECONDS,
            )
            elapsed = time.perf_counter() - start
            logger.info(
                "📥 [Synchronization of basic information from multiple data sources] Stock list acquisition completed: attempt=%s, source=%s, records=%s, elapsed=%.2fs",
                attempt_label,
                source_used,
                0 if stock_df is None else len(stock_df),
                elapsed,
            )
            return stock_df, source_used

        try:
            return await _fetch_once(preferred_sources, "primary")
        except asyncio.TimeoutError:
            logger.warning(
                "⏱ [Synchronization of basic information from multiple data sources] Stock list retrieval timed out: preferred_sources=%s, timeout=%ss",
                preferred_sources or [],
                STOCK_LIST_FETCH_TIMEOUT_SECONDS,
            )
            retry_sources = [source for source in (preferred_sources or []) if source != "qmt"]
            if retry_sources:
                logger.warning(
                    "↩️ [Synchronization of basic information from multiple data sources] Retry stock list retrieval and postpone QMT: retry_sources=%s",
                    retry_sources,
                )
                return await _fetch_once(retry_sources, "retry_without_qmt")
            raise

    async def _run_full_sync_impl(
        self,
        db: AsyncIOMotorDatabase,
        stats: SyncStats,
        preferred_sources: List[str] = None,
    ) -> Dict[str, Any]:
        """Execute real synchronization logic; reused by synchronization entrance or background task entrance."""

        try:
            preferred_sources = self._normalize_preferred_sources(preferred_sources)
            sync_start = time.perf_counter()
            logger.info(
                "🚀 [Synchronization of basic information from multiple data sources] Start execution: preferred_sources=%s",
                preferred_sources or [],
            )

            # Step 1: Get data source manager
            from app.services.data_sources.manager import DataSourceManager
            step_start = time.perf_counter()
            manager = DataSourceManager()
            available_adapters = manager.get_available_adapters()

            if not available_adapters:
                raise RuntimeError("No available data sources found")

            logger.info(
                "✅ [Synchronization of basic information from multiple data sources] Available data sources=%s, Time consuming=%.2fs",
                [adapter.name for adapter in available_adapters],
                time.perf_counter() - step_start,
            )

            # If a preferred data source is specified, log
            if preferred_sources:
                logger.info(f"Using preferred data sources: {preferred_sources}")

            # Step 2: Trying to get a list of stocks from a data source (excluding local data sources)
            stock_df, source_used = await self._fetch_stock_list_with_retry(manager, preferred_sources)
            if stock_df is None or getattr(stock_df, "empty", True):
                raise RuntimeError("All data sources failed to provide stock list")

            stats.data_sources_used.append(f"stock_list:{source_used}")
            logger.info(f"Successfully fetched {len(stock_df)} stocks from {source_used}")

            # Step 3: Get the latest trading dates and financial data
            step_start = time.perf_counter()
            latest_trade_date = await asyncio.to_thread(
                manager.find_latest_trade_date_with_fallback, preferred_sources
            )
            stats.last_trade_date = latest_trade_date
            logger.info(
                "🗓️ [Synchronization of basic information from multiple data sources] Latest trading day=%s, Time consuming=%.2fs",
                latest_trade_date,
                time.perf_counter() - step_start,
            )

            daily_data_map = {}
            daily_source = ""
            if latest_trade_date:
                step_start = time.perf_counter()
                daily_df, daily_source = await asyncio.to_thread(
                    manager.get_daily_basic_with_fallback, latest_trade_date, preferred_sources
                )
                if daily_df is not None and not daily_df.empty:
                    for _, row in daily_df.iterrows():
                        ts_code = row.get("ts_code")
                        if ts_code:
                            daily_data_map[ts_code] = row.to_dict()
                    stats.data_sources_used.append(f"daily_data:{daily_source}")
                logger.info(
                    "📈 [Synchronization of basic information from multiple data sources] daily_basic source=%s, records=%s, elapsed=%.2fs",
                    daily_source or "-",
                    0 if daily_df is None else len(daily_df),
                    time.perf_counter() - step_start,
                )

            step_start = time.perf_counter()
            industry_mapping = await fetch_industry_mapping(refresh_if_empty=True)
            use_system_industry_mapping = bool(industry_mapping)
            if use_system_industry_mapping:
                stats.data_sources_used.append(f"industry_mapping:{INDUSTRY_SOURCE_SYSTEM}")
                logger.info(f"📊 使用系统行业映射集合: {len(industry_mapping)} 只股票")
            logger.info(
                "🏷️ [Synchronization of basic information from multiple data sources] Industry mapping loading completed: enabled=%s, elapsed=%.2fs",
                use_system_industry_mapping,
                time.perf_counter() - step_start,
            )

            # Step 5: Process and update data (batch processing)
            ops = []
            inserted = updated = errors = 0
            batch_size = 500  # 🔥 Process 500 stocks per batch to avoid timeouts
            total_stocks = len(stock_df)

            logger.info(f"🚀 开始处理 {total_stocks} 只股票，数据源: {source_used}")

            for idx, (_, row) in enumerate(stock_df.iterrows(), 1):
                try:
                    # Extract basic information
                    name = row.get("name") or ""
                    area = row.get("area") or ""
                    industry = row.get("industry") or ""
                    market = row.get("market") or ""
                    list_date = row.get("list_date") or ""
                    ts_code = row.get("ts_code") or ""

                    # Extract 6-digit stock code
                    if isinstance(ts_code, str) and "." in ts_code:
                        code = ts_code.split(".")[0]
                    else:
                        symbol = row.get("symbol") or ""
                        code = str(symbol).zfill(6) if symbol else ""

                    mapped_industry = industry_mapping.get(code, "") if use_system_industry_mapping else ""
                    resolved_industry = mapped_industry or industry or "未知"

                    # Determine the exchange based on ts_code
                    if isinstance(ts_code, str):
                        if ts_code.endswith(".SH"):
                            sse = "上海证券交易所"
                        elif ts_code.endswith(".SZ"):
                            sse = "深圳证券交易所"
                        elif ts_code.endswith(".BJ"):
                            sse = "北京证券交易所"
                        else:
                            sse = "未知"
                    else:
                        sse = "未知"

                    category = "stock_cn"

                    # Get financial data
                    daily_metrics = {}
                    if isinstance(ts_code, str) and ts_code in daily_data_map:
                        daily_metrics = daily_data_map[ts_code]

                    # Generate full_symbol (make sure it is not empty)
                    full_symbol = ts_code if ts_code else self._generate_full_symbol(code)

                    # 🔥 Determine data source identification
                    # Set the source field according to the actual data source used
                    # NOTE: No longer used "multi_source" As default, there must be an explicit data source
                    if not source_used:
                        logger.warning(f"⚠️ 股票 {code} 没有明确的数据源，跳过")
                        errors += 1
                        continue
                    data_source = source_used

                    # Build documentation
                    doc = {
                        "code": code,
                        "symbol": code,  # Add symbol field (standardized field)
                        "name": name,
                        "area": area,
                        "industry": resolved_industry,
                        "market": market,
                        "list_date": list_date,
                        "sse": sse,
                        "full_symbol": full_symbol,  # Add full_symbol field
                        "category": category,
                        "source": data_source,  # 🔥 Use actual data sources
                        "updated_at": datetime.now(),
                    }

                    if mapped_industry:
                        doc["industry_source"] = INDUSTRY_SOURCE_SYSTEM

                    # Add financial metrics
                    self._add_financial_metrics(doc, daily_metrics)

                    # 🔥 Use (code, source) Union query conditions
                    ops.append(UpdateOne({"code": code, "source": data_source}, {"$set": doc}, upsert=True))

                except Exception as e:
                    logger.error(f"Error processing stock {row.get('ts_code', 'unknown')}: {e}")
                    errors += 1

                # 🔥 Perform database operations in batches
                if len(ops) >= batch_size or idx == total_stocks:
                    if ops:
                        progress_pct = (idx / total_stocks) * 100
                        logger.info(f"📝 执行批量写入: {len(ops)} 条记录 ({idx}/{total_stocks}, {progress_pct:.1f}%)")

                        batch_inserted, batch_updated = await self._execute_bulk_write_with_retry(db, ops)

                        if batch_inserted > 0 or batch_updated > 0:
                            inserted += batch_inserted
                            updated += batch_updated
                            logger.info(f"✅ 批量写入完成: 新增 {batch_inserted}, 更新 {batch_updated} | 累计: 新增 {inserted}, 更新 {updated}, 错误 {errors}")
                        else:
                            errors += len(ops)
                            logger.warning(f"⚠️ 批量写入失败，标记 {len(ops)} 条记录为错误")

                        ops = []  # Clear operation list

            # Step 7: Update statistics
            stats.total = total_stocks  # 🔥 Use total number of shares
            stats.inserted = inserted
            stats.updated = updated
            stats.errors = errors
            stats.status = "success" if errors == 0 else "success_with_errors"
            stats.finished_at = datetime.now().isoformat()

            try:
                await self._persist_status(db, stats.__dict__.copy())
                logger.info(
                    f"✅ Multi-source sync finished: total={stats.total} inserted={inserted} "
                    f"updated={updated} errors={errors} sources={stats.data_sources_used}"
                )
                logger.info(
                    "✅ [Synchronization of basic information from multiple data sources] Total time spent %.2fs",
                    time.perf_counter() - sync_start,
                )
            except Exception as persist_error:
                logger.error(f"❌ 保存成功状态时出错: {persist_error}")
                # Return results even if saving fails
            finally:
                # 🔥 Clear the memory cache to ensure that the latest status is read from the database the next time you query
                self._last_status = None
            
            return stats.__dict__

        except Exception as e:
            stats.status = "failed"
            stats.message = str(e)
            stats.finished_at = datetime.now().isoformat()
            try:
                await self._persist_status(db, stats.__dict__.copy())
            except Exception as persist_error:
                logger.error(f"❌ 保存失败状态时出错: {persist_error}")
            logger.exception(f"Multi-source sync failed: {e}")
            return stats.__dict__
        finally:
            # 🔥 Ensure that both the running status and the final status are updated regardless of success or failure
            async with self._lock:
                self._running = False
                # Clear the memory cache and force the latest status to be read from the database next time
                self._last_status = None



    def _add_financial_metrics(self, doc: Dict, daily_metrics: Dict) -> None:
        """entrusted to basics_sync.processing.add_financial_metrics"""
        return _add_financial_metrics_util(doc, daily_metrics)

    def _generate_full_symbol(self, code: str) -> str:
        """
        Generate complete standardized code based on stock symbol

        Args:
            code: 6 stock code

        Returns:
            Full normalized code, or original code if unrecognized (make sure not empty)
        """
        # Make sure code is not empty
        if not code:
            return ""

        # Normalize to string and remove spaces
        code = str(code).strip()

        # If the length is not 6, return the original code
        if len(code) != 6:
            return code

        # Determine the exchange based on the code prefix
        if code.startswith(('60', '68', '90')):  # Shanghai Stock Exchange
            return f"{code}.SS"
        elif code.startswith(('00', '30', '20')):  # Shenzhen Stock Exchange
            return f"{code}.SZ"
        elif code.startswith(('8', '4', '92')):  # Beijing Stock Exchange (92 is the unified number range starting from 2025-10)
            return f"{code}.BJ"
        else:
            # Unrecognized code, return original code (make sure it is not empty)
            return code if code else ""


# Global service instance
_multi_source_sync_service = None

def get_multi_source_sync_service() -> MultiSourceBasicsSyncService:
    """获取多数据源同步服务实例"""
    global _multi_source_sync_service
    if _multi_source_sync_service is None:
        _multi_source_sync_service = MultiSourceBasicsSyncService()
    return _multi_source_sync_service

# === official_industry_service.py ===
"""
System industry mapping services

The system has a built-in stock code -> A mapping collection of industries. All readers draw data from this collection uniformly.
In the future, data can be supplied through the official website interface; currently, when the official website interface is not configured, Tushare is temporarily used as the data supply source.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional

try:
    from pymongo import UpdateMany, UpdateOne
except ImportError:
    from unittest.mock import MagicMock as _MM; BulkWriteResult = UpdateOne = InsertOne = DeleteOne = MongoClient = Database = ASCENDING = DESCENDING = ReturnDocument = _MM()
    DuplicateKeyError = PyMongoError = OperationFailure = ServerSelectionTimeoutError = ConnectionFailure = Exception

from app.core.database import get_mongo_db

logger = logging.getLogger(__name__)

INDUSTRY_MAPPING_COLLECTION = "stock_industry_mappings"
INDUSTRY_SOURCE_SYSTEM = "system_industry_mapping"

_industry_cache: Optional[Dict[str, str]] = None
_cache_time: Optional[datetime] = None
_CACHE_TTL_HOURS = 24


def _normalize_code(code: Any) -> str:
    value = str(code or "").strip()
    if not value:
        return ""
    if "." in value:
        value = value.split(".", 1)[0]
    return value.zfill(6)


def _normalize_mapping_payload(data: Any) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if isinstance(data, dict):
        items = data.items()
        for code, value in items:
            normalized_code = _normalize_code(code)
            if not normalized_code:
                continue
            if isinstance(value, str):
                industry = value.strip()
            elif isinstance(value, dict):
                industry = str(value.get("industry") or value.get("industry_name") or "").strip()
            else:
                industry = ""
            if industry and industry != "未知":
                result[normalized_code] = industry
        return result

    if isinstance(data, list):
        for item in data:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            elif hasattr(item, "dict"):
                item = item.dict()
            if not isinstance(item, dict):
                continue

            normalized_code = _normalize_code(item.get("code") or item.get("symbol") or item.get("ts_code"))
            industry = str(item.get("industry") or item.get("industry_name") or "").strip()
            if normalized_code and industry and industry != "未知":
                result[normalized_code] = industry

    return result


def _invalidate_cache() -> None:
    global _industry_cache, _cache_time
    _industry_cache = None
    _cache_time = None


def get_official_industry_url() -> Optional[str]:
    """Obtain the official website industry data URL from the configuration."""
    try:
        from app.core.config import settings
        url = getattr(settings, "OFFICIAL_INDUSTRY_DATA_URL", None)
        if url and str(url).strip():
            return str(url).strip()
    except Exception:
        pass
    import os
    return os.getenv("OFFICIAL_INDUSTRY_DATA_URL", "").strip() or None


async def _load_mapping_from_collection() -> Dict[str, str]:
    db = get_mongo_db()
    collection = db[INDUSTRY_MAPPING_COLLECTION]
    cursor = collection.find(
        {"industry": {"$nin": [None, "", "未知"]}},
        {"_id": 0, "code": 1, "industry": 1}
    )

    mapping: Dict[str, str] = {}
    async for doc in cursor:
        code = _normalize_code(doc.get("code"))
        industry = str(doc.get("industry") or "").strip()
        if code and industry:
            mapping[code] = industry
    return mapping


async def upsert_industry_mapping(mapping: Dict[str, str], provider: str) -> Dict[str, Any]:
    """Batch write system industry mapping collection."""
    if not mapping:
        return {"provider": provider, "total": 0, "upserted": 0, "modified": 0}

    db = get_mongo_db()
    collection = db[INDUSTRY_MAPPING_COLLECTION]
    now = datetime.utcnow()

    operations = []
    for code, industry in mapping.items():
        normalized_code = _normalize_code(code)
        normalized_industry = str(industry or "").strip()
        if not normalized_code or not normalized_industry or normalized_industry == "未知":
            continue
        operations.append(UpdateOne(
            {"code": normalized_code},
            {
                "$set": {
                    "code": normalized_code,
                    "industry": normalized_industry,
                    "provider": provider,
                    "updated_at": now,
                }
            },
            upsert=True
        ))

    if not operations:
        return {"provider": provider, "total": 0, "upserted": 0, "modified": 0}

    result = await collection.bulk_write(operations, ordered=False)
    _invalidate_cache()
    logger.info(f"✅ Industry mapping collection update completed: provider={provider}, total={len(operations)}, modified={result.modified_count}, upserted={result.upserted_count}")
    return {
        "provider": provider,
        "total": len(operations),
        "upserted": result.upserted_count,
        "modified": result.modified_count,
    }


async def upsert_industry_mapping_from_records(records: Iterable[Any], provider: str = "tushare_fallback") -> Dict[str, Any]:
    """Extract industries from stock list records and write to the system industry map collection."""
    mapping = _normalize_mapping_payload(list(records))
    return await upsert_industry_mapping(mapping, provider=provider)


async def _fetch_mapping_from_official_url() -> Dict[str, str]:
    url = get_official_industry_url()
    if not url:
        return {}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        mapping = _normalize_mapping_payload(data)
        if mapping:
            logger.info(f"✅ 从官网接口获取行业映射成功: {len(mapping)} 只股票")
        return mapping
    except Exception as e:
        logger.warning(f"获取官网行业数据失败: {url}, {e}")
        return {}


async def _fetch_mapping_from_tushare() -> Dict[str, str]:
    try:
        from tradingagents.dataflows.providers.china.tushare import TushareProvider

        provider = TushareProvider()
        connected = await provider.connect()
        if not connected:
            logger.warning("Tushare Connection failed, unable to refresh industry mapping collection")
            return {}

        stock_list = await provider.get_stock_list(market="CN")
        mapping = _normalize_mapping_payload(stock_list)
        if mapping:
            logger.info(f"✅ 从 Tushare 临时供数获取行业映射成功: {len(mapping)} 只股票")
        return mapping
    except Exception as e:
        logger.warning(f"Failed to get industry mapping from Tushare: {e}")
        return {}


async def refresh_industry_mapping(prefer_official: bool = True) -> Dict[str, Any]:
    """Refresh the system industry mapping collection. Prioritize the official website interface and fall back to Tushare if it is not configured."""
    mapping: Dict[str, str] = {}
    provider = "none"

    if prefer_official:
        mapping = await _fetch_mapping_from_official_url()
        if mapping:
            provider = "official_api"

    if not mapping:
        mapping = await _fetch_mapping_from_tushare()
        if mapping:
            provider = "tushare_fallback"

    if not mapping:
        logger.warning("⚠️ No industry mapping data was obtained, and the system industry mapping collection remains unchanged.")
        return {"provider": provider, "total": 0, "upserted": 0, "modified": 0}

    return await upsert_industry_mapping(mapping, provider=provider)


async def fetch_industry_mapping(refresh_if_empty: bool = True) -> Dict[str, str]:
    """Read the system industry mapping collection and automatically refresh it when necessary."""
    global _industry_cache, _cache_time

    if _industry_cache is not None and _cache_time is not None:
        if datetime.utcnow() - _cache_time < timedelta(hours=_CACHE_TTL_HOURS):
            return _industry_cache

    mapping = await _load_mapping_from_collection()
    if not mapping and refresh_if_empty:
        await refresh_industry_mapping(prefer_official=True)
        mapping = await _load_mapping_from_collection()

    _industry_cache = mapping
    _cache_time = datetime.utcnow()
    return mapping


def get_industry_sync(code: str) -> Optional[str]:
    """Synchronously read individual stock sectors from memory cache."""
    global _industry_cache
    if not _industry_cache:
        return None
    return _industry_cache.get(_normalize_code(code))


async def get_industry(code: str) -> Optional[str]:
    """Asynchronously read a single stock industry."""
    mapping = await fetch_industry_mapping(refresh_if_empty=True)
    return mapping.get(_normalize_code(code))


async def sync_industry_to_stock_basic_info(db=None) -> Dict[str, int]:
    """Batch backfill the system industry mapping collection into stock_basic_info."""
    if db is None:
        db = get_mongo_db()

    mapping = await fetch_industry_mapping(refresh_if_empty=True)
    if not mapping:
        return {"updated": 0, "total": 0}

    collection = db["stock_basic_info"]
    operations = []
    now = datetime.utcnow()
    for code, industry in mapping.items():
        operations.append(UpdateMany(
            {"code": code},
            {
                "$set": {
                    "industry": industry,
                    "industry_source": INDUSTRY_SOURCE_SYSTEM,
                    "industry_updated_at": now,
                }
            }
        ))

    if not operations:
        return {"updated": 0, "total": 0}

    result = await collection.bulk_write(operations, ordered=False)
    logger.info(f"✅ 系统行业映射已同步到 stock_basic_info: 更新 {result.modified_count} 条")
    return {"updated": result.modified_count, "total": len(mapping)}

# === technical_indicator_materialization_service.py ===

from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional

import pandas as pd

from app.core.database import get_mongo_db_sync
from tradingagents.tools.analysis.indicators import IndicatorSpec, compute_many


LOOKBACK_LIMIT = 120
TECHNICAL_SPECS = [
    IndicatorSpec("ma", {"n": 20}),
    IndicatorSpec("macd"),
    IndicatorSpec("rsi", {"n": 14}),
    IndicatorSpec("kdj", {"n": 9, "m1": 3, "m2": 3}),
]
OUTPUT_FIELDS = ["ma20", "rsi14", "kdj_k", "kdj_d", "kdj_j", "dif", "dea", "macd_hist"]

ProgressLogger = Optional[Callable[[str], None]]


def _technical_indicator_materialization_service_safe_float(value: object) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iter_symbol_sources(collection) -> Iterable[Dict[str, str]]:
    pipeline = [
        {"$match": {"period": "daily"}},
        {
            "$group": {
                "_id": {
                    "code": {"$ifNull": ["$code", "$symbol"]},
                    "symbol": {"$ifNull": ["$symbol", "$code"]},
                    "source": "$data_source",
                }
            }
        },
        {"$sort": {"_id.code": 1, "_id.source": 1}},
    ]
    for row in collection.aggregate(pipeline, allowDiskUse=True):
        item = row.get("_id") or {}
        code = str(item.get("code") or "").zfill(6)
        symbol = str(item.get("symbol") or code).zfill(6)
        source = str(item.get("source") or "")
        if not code or not source:
            continue
        yield {"code": code, "symbol": symbol, "source": source}


def _load_recent_quotes(collection, symbol: str, source: str) -> List[Dict[str, object]]:
    cursor = collection.find(
        {"symbol": symbol, "data_source": source, "period": "daily"},
        {
            "_id": 0,
            "trade_date": 1,
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1,
            "volume": 1,
            "amount": 1,
        },
    ).sort("trade_date", -1).limit(LOOKBACK_LIMIT)
    return list(cursor)


def _build_snapshot(symbol_row: Dict[str, str], quotes: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
    if len(quotes) < 35:
        return None

    frame = pd.DataFrame(quotes)
    if frame.empty or "trade_date" not in frame.columns:
        return None

    frame = frame.sort_values("trade_date").reset_index(drop=True)
    frame["vol"] = frame.get("volume")
    enriched = compute_many(frame, TECHNICAL_SPECS)
    last = enriched.iloc[-1]

    trade_date = last.get("trade_date")
    if trade_date is None:
        return None

    snapshot = {
        "code": symbol_row["code"],
        "symbol": symbol_row["symbol"],
        "source": symbol_row["source"],
        "trade_date": str(trade_date),
        "updated_at": datetime.utcnow(),
        "version": 1,
    }
    for field in OUTPUT_FIELDS:
        snapshot[field] = _technical_indicator_materialization_service_safe_float(last.get(field))

    if all(snapshot.get(field) is None for field in OUTPUT_FIELDS):
        return None

    return snapshot


def materialize_technical_indicators(progress_every: int = 200, progress_logger: ProgressLogger = None) -> Dict[str, int]:
    db = get_mongo_db_sync()
    quote_collection = db["stock_daily_quotes"]
    target_collection = db["stock_technical_indicators"]

    processed = 0
    written = 0

    for symbol_row in _iter_symbol_sources(quote_collection):
        processed += 1
        quotes = _load_recent_quotes(quote_collection, symbol_row["symbol"], symbol_row["source"])
        snapshot = _build_snapshot(symbol_row, quotes)
        if snapshot is None:
            continue

        target_collection.update_one(
            {
                "code": snapshot["code"],
                "source": snapshot["source"],
                "trade_date": snapshot["trade_date"],
            },
            {
                "$set": snapshot,
                "$setOnInsert": {"created_at": snapshot["updated_at"]},
            },
            upsert=True,
        )
        written += 1

        if progress_logger and processed % progress_every == 0:
            progress_logger(f"processed={processed} written={written}")

    if progress_logger:
        progress_logger(f"done processed={processed} written={written}")

    return {"processed": processed, "written": written}

# === trade_date_cache_service.py ===
"""
Last transaction date caching service
Use Redis to cache the last valid transaction date of each data source to avoid frequent calls API
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Redis Key name
CACHE_KEY_PREFIX = "trade_date:latest"
CACHE_KEY_TUSHARE = f"{CACHE_KEY_PREFIX}:tushare"
CACHE_KEY_AKSHARE = f"{CACHE_KEY_PREFIX}:akshare"
CACHE_KEY_BAOSTOCK = f"{CACHE_KEY_PREFIX}:baostock"


class TradeDateCacheService:
    """最后交易日期缓存服务"""
    
    @property
    def redis(self):
        """Get the synchronous Redis client (for sync methods)."""
        try:
            from app.core.database import get_redis_sync_client

            return get_redis_sync_client()
        except Exception as e:
            logger.warning(f"⚠️  Synchronous Redis client initialization failed: {e}, Will directly call the API to get the transaction date", exc_info=True)
            return None
    
    @property
    def redis_async(self):
        """Get an asynchronous Redis client (for async methods)."""
        try:
            from app.core.database import get_redis_client

            return get_redis_client()
        except RuntimeError:
            logger.warning("Asynchronous Redis client is not initialized and asynchronous methods may not be available")
            return None
    
    def _is_today(self, date_str: str) -> bool:
        """判断日期字符串是否是今天"""
        try:
            cache_date = datetime.strptime(date_str, "%Y-%m-%d")
            today = datetime.now().date()
            return cache_date.date() == today
        except Exception:
            return False
    
    def get_cached_trade_date_sync(self, source: str) -> Optional[str]:
        """
        Get last transaction date from cache (sync version)
        
        Args:
            source: Data source name ('tushare', 'akshare', 'baostock')
            
        Returns:
            If the cache exists and was updated today, return the transaction date (YYYYMMDD format), otherwise return None
        """
        if not self.redis:
            return None
        
        try:
            cache_key = self._get_cache_key(source)
            cached_data = self.redis.get(cache_key)
            
            if cached_data:
                data = json.loads(cached_data)
                update_date = data.get("update_date")
                trade_date = data.get("trade_date")
                
                # Determine whether it was updated on the same day
                if self._is_today(update_date):
                    logger.debug(f"✅ [{source}] 从缓存获取最后交易日期: {trade_date} (更新于: {update_date})")
                    return trade_date
                else:
                    logger.debug(f"⚠️  [{source}] Cache has expired (updated on: {update_date}), Need to reacquire")
                    return None
            
            return None
        except Exception as e:
            logger.warning(f"⚠️  [{source}] 读取缓存失败: {e}")
            return None
    
    async def _get_cached_trade_date_async(self, source: str) -> Optional[str]:
        """异步获取缓存"""
        if not self.redis_async:
            return None
        
        try:
            cache_key = self._get_cache_key(source)
            cached_data = await self.redis_async.get(cache_key)
            
            if cached_data:
                data = json.loads(cached_data)
                update_date = data.get("update_date")
                trade_date = data.get("trade_date")
                
                # Determine whether it was updated on the same day
                if self._is_today(update_date):
                    logger.debug(f"✅ [{source}] 从缓存获取最后交易日期: {trade_date} (更新于: {update_date})")
                    return trade_date
                else:
                    logger.debug(f"⚠️  [{source}] Cache has expired (updated on: {update_date}), Need to reacquire")
                    return None
            
            return None
        except Exception as e:
            logger.warning(f"⚠️  [{source}] 读取缓存失败: {e}")
            return None
    
    async def get_cached_trade_date(self, source: str) -> Optional[str]:
        """
        Get last transaction date from cache (async version)
        
        Args:
            source: Data source name ('tushare', 'akshare', 'baostock')
            
        Returns:
            If the cache exists and was updated today, return the transaction date (YYYYMMDD format), otherwise return None
        """
        return await self._get_cached_trade_date_async(source)
    
    def set_cached_trade_date_sync(self, source: str, trade_date: str) -> bool:
        """
        Save last transaction date to cache (sync version)
        
        Args:
            source: Data source name ('tushare', 'akshare', 'baostock')
            trade_date: Transaction date (YYYYMMDD format)
            
        Returns:
            Is the save successful?
        """
        if not self.redis:
            return False
        
        try:
            cache_key = self._get_cache_key(source)
            today = datetime.now().strftime("%Y-%m-%d")
            
            data = {
                "trade_date": trade_date,
                "update_date": today,
                "source": source
            }
            
            # Save to Redis, set TTL to 7 days (prevent cache from persisting forever)
            self.redis.setex(
                cache_key,
                7 * 24 * 3600,  # 7 day TTL
                json.dumps(data, ensure_ascii=False)
            )
            
            logger.info(f"✅ [{source}] 已缓存最后交易日期: {trade_date} (更新于: {today})")
            return True
        except Exception as e:
            logger.warning(f"⚠️  [{source}] 保存缓存失败: {e}")
            return False
    
    async def _set_cached_trade_date_async(self, source: str, trade_date: str) -> bool:
        """异步保存缓存"""
        if not self.redis_async:
            return False
        
        try:
            cache_key = self._get_cache_key(source)
            today = datetime.now().strftime("%Y-%m-%d")
            
            data = {
                "trade_date": trade_date,
                "update_date": today,
                "source": source
            }
            
            # Save to Redis, set TTL to 7 days (prevent cache from persisting forever)
            await self.redis_async.setex(
                cache_key,
                7 * 24 * 3600,  # 7 day TTL
                json.dumps(data, ensure_ascii=False)
            )
            
            logger.info(f"✅ [{source}] 已缓存最后交易日期: {trade_date} (更新于: {today})")
            return True
        except Exception as e:
            logger.warning(f"⚠️  [{source}] 保存缓存失败: {e}")
            return False
    
    async def set_cached_trade_date(self, source: str, trade_date: str) -> bool:
        """
        Save last transaction date to cache (asynchronous version)
        
        Args:
            source: Data source name ('tushare', 'akshare', 'baostock')
            trade_date: Transaction date (YYYYMMDD format)
            
        Returns:
            Is the save successful?
        """
        return await self._set_cached_trade_date_async(source, trade_date)
    
    def _get_cache_key(self, source: str) -> str:
        """获取缓存键名"""
        key_map = {
            "tushare": CACHE_KEY_TUSHARE,
            "akshare": CACHE_KEY_AKSHARE,
            "baostock": CACHE_KEY_BAOSTOCK,
        }
        return key_map.get(source.lower(), f"{CACHE_KEY_PREFIX}:{source.lower()}")
    
    def clear_cache_sync(self, source: Optional[str] = None) -> bool:
        """
        Clear cache (sync version)
        
        Args:
            source: Data source name, if None clears all caches
            
        Returns:
            Is the clearing successful?
        """
        if not self.redis:
            return False
        
        try:
            if source:
                cache_key = self._get_cache_key(source)
                self.redis.delete(cache_key)
                logger.info(f"✅ [{source}] 缓存已清除")
            else:
                # Clear all transaction date cache
                keys = [CACHE_KEY_TUSHARE, CACHE_KEY_AKSHARE, CACHE_KEY_BAOSTOCK]
                for key in keys:
                    self.redis.delete(key)
                logger.info("✅ All transaction date cache cleared")
            return True
        except Exception as e:
            logger.warning(f"⚠️  清除缓存失败: {e}")
            return False
    
    async def _clear_cache_async(self, source: Optional[str] = None) -> bool:
        """异步清除缓存"""
        if not self.redis_async:
            return False
        
        try:
            if source:
                cache_key = self._get_cache_key(source)
                await self.redis_async.delete(cache_key)
                logger.info(f"✅ [{source}] 缓存已清除")
            else:
                # Clear all transaction date cache
                keys = [CACHE_KEY_TUSHARE, CACHE_KEY_AKSHARE, CACHE_KEY_BAOSTOCK]
                for key in keys:
                    await self.redis_async.delete(key)
                logger.info("✅ All transaction date cache cleared")
            return True
        except Exception as e:
            logger.warning(f"⚠️  清除缓存失败: {e}")
            return False
    
    async def clear_cache(self, source: Optional[str] = None) -> bool:
        """
        Clear cache (asynchronous version)
        
        Args:
            source: Data source name, if None clears all caches
            
        Returns:
            Is the clearing successful?
        """
        return await self._clear_cache_async(source)


# Singleton instance
_trade_date_cache_service: Optional[TradeDateCacheService] = None


def get_trade_date_cache_service() -> TradeDateCacheService:
    """获取交易日期缓存服务单例"""
    global _trade_date_cache_service
    if _trade_date_cache_service is None:
        _trade_date_cache_service = TradeDateCacheService()
    return _trade_date_cache_service

# === trading_calendar_service.py ===
"""
Trading Calendar Service

Query the latest actual trading day of A shares from Tushare/AkShare when the system starts.
The results are cached in Redis for modules such as JIT data synchronization to accurately determine the freshness of the data.

Redis Key: trading_calendar:last_trade_date
cache format:
  {
    "last_trade_date": "2026-02-27",   # YYYY-MM-DD
    "is_today_trade_day": true,
    "fetched_at": "2026-02-27",        # On the day of this inquiry
    "source": "tushare"
  }

TTL: 25 hours (refreshed every day when the system starts, will not exist indefinitely)
"""


import asyncio
import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

REDIS_KEY = "trading_calendar:last_trade_date"
CACHE_TTL_SECONDS = 25 * 3600  # 25 hours, guaranteed to be refreshed at startup every day


class TradingCalendarService:
    """A Stock trading calendar service (single case)"""

    # ------------------------------------------------------------------ #
    # internal tools                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _today_str() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def _fmt(raw: str) -> str:
        """Uniformly formatted as YYYY-MM-DD (compatible with YYYYMMDD and YYYY-MM-DD input)"""
        raw = raw.strip()
        if len(raw) == 8 and "-" not in raw:
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        return raw

    @staticmethod
    def _is_loop_mismatch_error(error: Exception) -> bool:
        error_text = str(error).lower()
        return "attached to a different loop" in error_text or "different loop" in error_text

    @staticmethod
    def _build_cache_payload(last_trade_date: str, is_today: bool, source: str) -> dict:
        return {
            "last_trade_date": last_trade_date,
            "is_today_trade_day": is_today,
            "fetched_at": TradingCalendarService._today_str(),
            "source": source,
        }

    # ------------------------------------------------------------------ #
    # Get last trading day from external API                                            #
    # ------------------------------------------------------------------ #

    async def _fetch_from_tushare(self) -> Optional[str]:
        """Call tushare daily_basic to go back day by day and find the most recent trading day (YYYY-MM-DD)"""
        try:
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
            import asyncio

            provider = get_tushare_provider()
            if not provider.is_available() or provider.api is None:
                return None

            today = datetime.now()
            for delta in range(0, 10):
                d = (today - timedelta(days=delta)).strftime("%Y%m%d")
                try:
                    df = await asyncio.to_thread(
                        provider.api.daily_basic,
                        trade_date=d,
                        fields="ts_code",
                        limit=1,
                    )
                    if df is not None and not df.empty:
                        logger.info(f"📅 [TradingCalendar] Tushare Confirm the latest trading day: {d}")
                        return self._fmt(d)
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"⚠️ [TradingCalendar] Tushare Query failed: {e}")
        return None

    async def _fetch_from_akshare(self) -> Optional[str]:
        """Call akshare tool_trade_date_hist_sina to get the recent trading calendar, whichever is more recent ≤ Today s trading day"""
        try:
            import akshare as ak
            import asyncio
            import pandas as pd

            df = await asyncio.to_thread(ak.tool_trade_date_hist_sina)
            if df is None or df.empty:
                return None

            # Column name may be trade_date or column 0
            col = df.columns[0]
            dates = pd.to_datetime(df[col]).dt.date
            today_d = date.today()
            valid = sorted([d for d in dates if d <= today_d], reverse=True)
            if valid:
                result = valid[0].strftime("%Y-%m-%d")
                logger.info(f"📅 [TradingCalendar] AkShare Confirm the latest trading day: {result}")
                return result
        except Exception as e:
            logger.warning(f"⚠️ [TradingCalendar] AkShare Query failed: {e}")
        return None

    async def _fetch_last_trade_date(self) -> tuple[str, str]:
        """
        By priority (tushare → akshare → Simple lookback) to get the most recent trading day.
        Returns: (last_trade_date: YYYY-MM-DD, source: str)
        """
        result = await self._fetch_from_tushare()
        if result:
            return result, "tushare"

        result = await self._fetch_from_akshare()
        if result:
            return result, "akshare"

        # The final tip: look forward to the first Monday from today~Friday (holidays are not guaranteed to be accurate)
        today = datetime.now()
        for delta in range(0, 5):
            d = today - timedelta(days=delta)
            if d.weekday() < 5:
                fallback = d.strftime("%Y-%m-%d")
                logger.warning(f"⚠️ [TradingCalendar] All APIs fail, falling back to the most recent working day: {fallback}")
                return fallback, "fallback"

        return today.strftime("%Y-%m-%d"), "fallback"

    # ------------------------------------------------------------------ #
    # Redis Read and write                                                          #
    # ------------------------------------------------------------------ #

    async def _redis(self):
        # Prefer using app.core.database by init_database() Initialized asynchronous Redis client,
        # Because lifespan only calls init_db()→init_database(), without calling redis_client.init_redis()
        from app.core.database import get_redis_client
        return get_redis_client()

    async def _read_cache(self) -> Optional[dict]:
        try:
            r = await self._redis()
            raw = await r.get(REDIS_KEY)
            if raw:
                return json.loads(raw)
        except Exception as e:
            if self._is_loop_mismatch_error(e):
                logger.debug("[TradingCalendar] Asynchronous Redis client across event loop, fallback to synchronous Redis read")
                return await asyncio.to_thread(self._read_cache_sync)
            logger.debug(f"[TradingCalendar] Failed to read Redis cache: {e}")
        return None

    @staticmethod
    def _read_cache_sync() -> Optional[dict]:
        try:
            from app.core.database import get_redis_sync_client

            redis_sync = get_redis_sync_client()
            raw = redis_sync.get(REDIS_KEY)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.debug(f"[TradingCalendar] Synchronizing Redis read cache failed: {e}")
        return None

    async def _write_cache(self, last_trade_date: str, is_today: bool, source: str):
        payload = self._build_cache_payload(last_trade_date, is_today, source)
        try:
            r = await self._redis()
            await r.setex(REDIS_KEY, CACHE_TTL_SECONDS, json.dumps(payload, ensure_ascii=False))
            logger.info(f"✅ [TradingCalendar] Cached to Redis: {payload}")
        except Exception as e:
            if self._is_loop_mismatch_error(e):
                try:
                    await asyncio.to_thread(self._write_cache_sync, payload)
                    logger.info(f"✅ [TradingCalendar] Redis fallback cache synchronized: {payload}")
                    return
                except Exception as sync_error:
                    logger.warning(f"⚠️ [TradingCalendar] Synchronous Redis fallback write failed: {sync_error}")
            logger.warning(f"⚠️ [TradingCalendar] Writing to Redis cache failed: {e}")

    @staticmethod
    def _write_cache_sync(payload: dict) -> None:
        from app.core.database import get_redis_sync_client

        redis_sync = get_redis_sync_client()
        redis_sync.setex(REDIS_KEY, CACHE_TTL_SECONDS, json.dumps(payload, ensure_ascii=False))

    # ------------------------------------------------------------------ #
    # public interface                                                            #
    # ------------------------------------------------------------------ #

    async def warm_up(self):
        """Called when the system starts, refresh the transaction calendar cache (always re-query the API, ignore the old cache)"""
        logger.info("🚀 [TradingCalendar] Start initializing the trading calendar cache...")
        try:
            last_trade_date, source = await self._fetch_last_trade_date()
            is_today = last_trade_date == self._today_str()
            await self._write_cache(last_trade_date, is_today, source)
            logger.info(
                f"✅ [TradingCalendar] 初始化完成: 最近交易日={last_trade_date}, "
                f"Is today a trading day?={is_today}, data source={source}"
            )
        except Exception as e:
            logger.error(f"❌ [TradingCalendar] Initialization failed: {e}", exc_info=True)

    async def get_last_trade_date(self) -> Optional[str]:
        """
        Get the latest trading day (YYYY-MM-DD).
        Read the Redis cache first; if the cache does not exist or is not written today, the API will be re-queried.
        """
        cache = await self._read_cache()
        if cache and cache.get("fetched_at") == self._today_str():
            return cache.get("last_trade_date")

        # Cache expired, retrieve again
        last_trade_date, source = await self._fetch_last_trade_date()
        is_today = last_trade_date == self._today_str()
        await self._write_cache(last_trade_date, is_today, source)
        return last_trade_date

    async def is_today_trade_day(self) -> bool:
        """判断今天是否是交易日"""
        cache = await self._read_cache()
        if cache and cache.get("fetched_at") == self._today_str():
            return bool(cache.get("is_today_trade_day", False))

        last = await self.get_last_trade_date()
        return last == self._today_str()


# ------------------------------------------------------------------ #
# Singleton                                                               #
# ------------------------------------------------------------------ #
_instance: Optional[TradingCalendarService] = None


def get_trading_calendar_service() -> TradingCalendarService:
    global _instance
    if _instance is None:
        _instance = TradingCalendarService()
    return _instance


# === data_consistency_checker.py ===
"""
Data consistency checking and processing services
Handle data inconsistencies between multiple data sources
"""
import logging
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class DataConsistencyResult:
    """数据一致性检查结果"""
    is_consistent: bool
    primary_source: str
    secondary_source: str
    differences: Dict[str, Any]
    confidence_score: float
    recommended_action: str
    details: Dict[str, Any]

@dataclass
class FinancialMetricComparison:
    """财务指标比较结果"""
    metric_name: str
    primary_value: Optional[float]
    secondary_value: Optional[float]
    difference_pct: Optional[float]
    is_significant: bool
    tolerance: float

class DataConsistencyChecker:
    """数据一致性检查器"""
    
    def __init__(self):
        # Set tolerance thresholds for various indicators
        self.tolerance_thresholds = {
            'pe': 0.05,      # PE Allow 5% difference
            'pb': 0.05,      # PB Allow 5% difference
            'total_mv': 0.02, # Market capitalization allows 2% difference
            'price': 0.01,   # Stock price allows 1% difference
            'volume': 0.10,  # 10% difference allowed in trading volume
            'turnover_rate': 0.05  # A 5% difference is allowed in turnover rate
        }
        
        # Key metric weights (used to calculate confidence scores)
        self.metric_weights = {
            'pe': 0.25,
            'pb': 0.25,
            'total_mv': 0.20,
            'price': 0.15,
            'volume': 0.10,
            'turnover_rate': 0.05
        }
    
    def check_daily_basic_consistency(
        self, 
        primary_data: pd.DataFrame, 
        secondary_data: pd.DataFrame,
        primary_source: str,
        secondary_source: str
    ) -> DataConsistencyResult:
        """
        Check the consistency of daily_basic data
        
        Args:
            primary_data: Master data source data
            secondary_data: secondary data source data
            primary_source: Primary data source name
            secondary_source: Secondary data source name
        """
        try:
            logger.info(f"🔍 检查数据一致性: {primary_source} vs {secondary_source}")
            
            # 1. basic check
            if primary_data.empty or secondary_data.empty:
                return DataConsistencyResult(
                    is_consistent=False,
                    primary_source=primary_source,
                    secondary_source=secondary_source,
                    differences={'error': 'One or both datasets are empty'},
                    confidence_score=0.0,
                    recommended_action='use_primary_only',
                    details={'reason': 'Empty dataset detected'}
                )
            
            # 2. Stock symbol matching
            common_stocks = self._find_common_stocks(primary_data, secondary_data)
            if len(common_stocks) == 0:
                return DataConsistencyResult(
                    is_consistent=False,
                    primary_source=primary_source,
                    secondary_source=secondary_source,
                    differences={'error': 'No common stocks found'},
                    confidence_score=0.0,
                    recommended_action='use_primary_only',
                    details={'reason': 'No overlapping stocks'}
                )
            
            logger.info(f"📊 找到{len(common_stocks)}只共同股票进行比较")
            
            # 3. Indicator-by-Indicator Comparison
            metric_comparisons = []
            for metric in ['pe', 'pb', 'total_mv']:
                comparison = self._compare_metric(
                    primary_data, secondary_data, common_stocks, metric
                )
                if comparison:
                    metric_comparisons.append(comparison)
            
            # 4. Calculate overall consistency
            consistency_result = self._calculate_overall_consistency(
                metric_comparisons, primary_source, secondary_source
            )
            
            return consistency_result
            
        except Exception as e:
            logger.error(f"❌ 数据一致性检查失败: {e}")
            return DataConsistencyResult(
                is_consistent=False,
                primary_source=primary_source,
                secondary_source=secondary_source,
                differences={'error': str(e)},
                confidence_score=0.0,
                recommended_action='use_primary_only',
                details={'exception': str(e)}
            )
    
    def _find_common_stocks(self, df1: pd.DataFrame, df2: pd.DataFrame) -> List[str]:
        """Find common stocks in two datasets"""
        # Try different ticker listings
        code_cols = ['ts_code', 'symbol', 'code', 'stock_code']
        
        df1_codes = set()
        df2_codes = set()
        
        for col in code_cols:
            if col in df1.columns:
                df1_codes.update(df1[col].dropna().astype(str).tolist())
            if col in df2.columns:
                df2_codes.update(df2[col].dropna().astype(str).tolist())
        
        return list(df1_codes.intersection(df2_codes))
    
    def _compare_metric(
        self, 
        df1: pd.DataFrame, 
        df2: pd.DataFrame, 
        common_stocks: List[str], 
        metric: str
    ) -> Optional[FinancialMetricComparison]:
        """比较特定指标"""
        try:
            if metric not in df1.columns or metric not in df2.columns:
                return None
            
            # Get indicator values for common stocks
            df1_values = []
            df2_values = []
            
            for stock in common_stocks[:100]:  # Limit the number of comparisons
                val1 = self._get_stock_metric_value(df1, stock, metric)
                val2 = self._get_stock_metric_value(df2, stock, metric)
                
                if val1 is not None and val2 is not None:
                    df1_values.append(val1)
                    df2_values.append(val2)
            
            if len(df1_values) == 0:
                return None
            
            # Calculate average and difference
            avg1 = np.mean(df1_values)
            avg2 = np.mean(df2_values)
            
            if avg1 != 0:
                diff_pct = abs(avg2 - avg1) / abs(avg1)
            else:
                diff_pct = float('inf') if avg2 != 0 else 0
            
            tolerance = self.tolerance_thresholds.get(metric, 0.1)
            is_significant = diff_pct > tolerance
            
            return FinancialMetricComparison(
                metric_name=metric,
                primary_value=avg1,
                secondary_value=avg2,
                difference_pct=diff_pct,
                is_significant=is_significant,
                tolerance=tolerance
            )
            
        except Exception as e:
            logger.warning(f"⚠️ 比较指标{metric}失败: {e}")
            return None
    
    def _get_stock_metric_value(self, df: pd.DataFrame, stock_code: str, metric: str) -> Optional[float]:
        """获取特定股票的指标值"""
        try:
            # Try different matching methods
            for code_col in ['ts_code', 'symbol', 'code']:
                if code_col in df.columns:
                    mask = df[code_col].astype(str) == stock_code
                    if mask.any():
                        value = df.loc[mask, metric].iloc[0]
                        if pd.notna(value) and value != 0:
                            return float(value)
            return None
        except Exception:
            return None
    
    def _calculate_overall_consistency(
        self, 
        comparisons: List[FinancialMetricComparison],
        primary_source: str,
        secondary_source: str
    ) -> DataConsistencyResult:
        """计算整体一致性结果"""
        if not comparisons:
            return DataConsistencyResult(
                is_consistent=False,
                primary_source=primary_source,
                secondary_source=secondary_source,
                differences={'error': 'No valid metric comparisons'},
                confidence_score=0.0,
                recommended_action='use_primary_only',
                details={'reason': 'No comparable metrics'}
            )
        
        # Calculate weighted confidence score
        total_weight = 0
        weighted_score = 0
        differences = {}
        
        for comp in comparisons:
            weight = self.metric_weights.get(comp.metric_name, 0.1)
            total_weight += weight
            
            # Consistency score: The smaller the difference, the higher the score
            if comp.difference_pct is not None and comp.difference_pct != float('inf'):
                consistency_score = max(0, 1 - (comp.difference_pct / comp.tolerance))
            else:
                consistency_score = 0
            
            weighted_score += weight * consistency_score
            
            # Record differences
            differences[comp.metric_name] = {
                'primary_value': comp.primary_value,
                'secondary_value': comp.secondary_value,
                'difference_pct': comp.difference_pct,
                'is_significant': comp.is_significant,
                'tolerance': comp.tolerance
            }
        
        confidence_score = weighted_score / total_weight if total_weight > 0 else 0
        
        # Determine overall consistency
        significant_differences = sum(1 for comp in comparisons if comp.is_significant)
        is_consistent = significant_differences <= len(comparisons) * 0.3  # Allow 30% of indicators to be significantly different
        
        # Recommended action
        if confidence_score > 0.8:
            recommended_action = 'use_either'  # The data is highly consistent and can be used from any data source
        elif confidence_score > 0.6:
            recommended_action = 'use_primary_with_warning'  # Use master data source with warning
        elif confidence_score > 0.3:
            recommended_action = 'use_primary_only'  # Use only primary data sources
        else:
            recommended_action = 'investigate_sources'  # Data source issues need to be investigated
        
        return DataConsistencyResult(
            is_consistent=is_consistent,
            primary_source=primary_source,
            secondary_source=secondary_source,
            differences=differences,
            confidence_score=confidence_score,
            recommended_action=recommended_action,
            details={
                'total_comparisons': len(comparisons),
                'significant_differences': significant_differences,
                'consistency_threshold': 0.3
            }
        )

    def resolve_data_conflicts(
        self, 
        primary_data: pd.DataFrame,
        secondary_data: pd.DataFrame,
        consistency_result: DataConsistencyResult
    ) -> Tuple[pd.DataFrame, str]:
        """
        Resolve data conflicts based on consistency check results
        
        Returns:
            Tuple[pd.DataFrame, str]: (final data, Solution strategy description)
        """
        action = consistency_result.recommended_action
        
        if action == 'use_either':
            logger.info("✅ The data is highly consistent, using the main data source")
            return primary_data, "The data source is highly consistent, using the main data source"
        
        elif action == 'use_primary_with_warning':
            logger.warning("⚠️ There are differences in the data but within the acceptable range, use the primary data source")
            return primary_data, f"There are slight differences in the data (confidence: {consistency_result.confidence_score:.2f}) , Use master data sources"
        
        elif action == 'use_primary_only':
            logger.warning("🚨 The data is very different, so only the primary data source is used")
            return primary_data, f"数据差异显著（置信度: {consistency_result.confidence_score:.2f}），仅使用主数据源"
        
        else:  # investigate_sources
            logger.error("❌ There are serious problems with the data source that require manual investigation")
            return primary_data, f"There are serious inconsistencies in the data source (confidence: {consistency_result.confidence_score:.2f}) , It is recommended to check the data source"

# === data_validation_service.py ===
"""
Data verification service

Check the completeness and validity of stock data in the database before analysis:
1. Does basic stock information exist?
2. Whether historical data exists and is within the analysis time range
3. Whether financial data exists (optional)
4. Whether real-time market data exists (optional)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass

from app.core.database import get_mongo_db

logger = logging.getLogger(__name__)


@dataclass
class DataValidationResult:
    """数据校验结果"""
    is_valid: bool
    message: str
    missing_data: List[str]
    details: Dict[str, Any]


class DataValidationService:
    """数据校验服务"""
    
    def __init__(self):
        """初始化服务"""
        self.db = None
    
    def _get_db(self):
        """获取数据库连接（懒加载）"""
        if self.db is None:
            self.db = get_mongo_db()
        return self.db

    async def validate_stock_data(
        self,
        symbol: str,
        analysis_date: str,
        market_type: str = "cn",
        check_basic_info: bool = True,
        check_historical_data: bool = False,  # 🔥 Historical data checking is disabled by default (to avoid false positives)
        check_financial_data: bool = False,
        check_realtime_quotes: bool = False,
        check_data_freshness: bool = False,  # 🔥 Data freshness check: Prevent the use of stale data
        historical_days: int = 365  # By default, historical data of the past 1 year is checked.
    ) -> DataValidationResult:
        """
        Verify the integrity and validity of stock data
        
        Args:
            symbol: Stock code (6 digits)
            analysis_date: Analysis date (YYYY-MM-DD format)
            market_type: Market type (cn/hk/us)
            check_basic_info: Whether to check basic information
            check_historical_data: Whether to check historical data
            check_financial_data: Whether to check financial data (optional)
            check_realtime_quotes: Whether to check real-time market conditions (optional)
            check_data_freshness: Whether to check data freshness (to prevent analysis with stale data)
            historical_days: Number of days of historical data to be checked (default 365 days)
            
        Returns:
            DataValidationResult: Verification result
        """
        db = self._get_db()
        symbol6 = str(symbol).zfill(6)
        missing_data = []
        details = {}
        
        try:
            # Parse and analyze dates (supports multiple formats: YYYY-MM-DD or ISO 8601 format, or already a datetime object)
            analysis_dt = None

            # If it is already a datetime object, use it directly
            if isinstance(analysis_date, datetime):
                analysis_dt = analysis_date
            else:
                # If it is a string, try to parse
                date_formats = [
                    '%Y-%m-%d',  # YYYY-MM-DD
                    '%Y-%m-%dT%H:%M:%S',  # ISO 8601 with time
                    '%Y-%m-%dT%H:%M:%S.%f',  # ISO 8601 with microseconds
                    '%Y-%m-%d %H:%M:%S',  # Space separated date times
                ]

                # if contains 'T', Try extracting the date part first
                if 'T' in analysis_date:
                    analysis_date_part = analysis_date.split('T')[0]
                    try:
                        analysis_dt = datetime.strptime(analysis_date_part, '%Y-%m-%d')
                    except ValueError:
                        pass

                # If parsing is not successful, try all formats
                if analysis_dt is None:
                    for fmt in date_formats:
                        try:
                            analysis_dt = datetime.strptime(analysis_date, fmt)
                            break
                        except ValueError:
                            continue

            if analysis_dt is None:
                return DataValidationResult(
                    is_valid=False,
                    message=f"分析日期格式错误: {analysis_date}，应为 YYYY-MM-DD 格式或 ISO 8601 格式",
                    missing_data=["analysis_date_format"],
                    details={"error": "日期格式错误"}
                )
            
            # Convert analysis date to string format (for subsequent inspection)
            analysis_date_str = analysis_dt.strftime('%Y-%m-%d')
            
            # 1. Check basic stock information
            if check_basic_info:
                basic_info_valid, basic_info_msg, basic_info_details = await self._check_basic_info(
                    db, symbol6, market_type
                )
                details["basic_info"] = basic_info_details
                if not basic_info_valid:
                    missing_data.append("基础信息")
                    return DataValidationResult(
                        is_valid=False,
                        message=f"股票 {symbol6} 的基础信息不存在，请先同步股票基础数据",
                        missing_data=missing_data,
                        details=details
                    )

            # 2. Check data freshness (to prevent the use of stale data during analysis)
            if check_data_freshness:
                freshness_valid, freshness_msg, freshness_details = await self._check_data_freshness(
                    db, symbol6, market_type, analysis_date_str
                )
                details["data_freshness"] = freshness_details
                if not freshness_valid:
                    missing_data.append("最新行情数据")
                    logger.warning(f"⚠️ [Data freshness] stocks {symbol6}: {freshness_msg}")
                    return DataValidationResult(
                        is_valid=False,
                        message=freshness_msg,
                        missing_data=missing_data,
                        details=details
                    )
                else:
                    logger.info(f"✅ [数据新鲜度] 股票 {symbol6}: {freshness_msg}")

            # 3. Check historical data
            if check_historical_data:
                # Calculate the date range that needs to be checked (make sure they are all in string format YYYY-MM-DD)
                start_date = (analysis_dt - timedelta(days=historical_days)).strftime('%Y-%m-%d')
                end_date = analysis_date_str  # Use the defined analysis_date_str

                historical_valid, historical_msg, historical_details = await self._check_historical_data(
                    db, symbol6, market_type, start_date, end_date, analysis_date_str
                )
                details["historical_data"] = historical_details
                if not historical_valid:
                    missing_data.append("历史数据")
                    return DataValidationResult(
                        is_valid=False,
                        message=f"股票 {symbol6} 在 {start_date} 至 {end_date} 期间的历史数据不足，请先同步历史数据",
                        missing_data=missing_data,
                        details=details
                    )
            
            # 3. Check financial data (optional)
            if check_financial_data:
                financial_valid, financial_msg, financial_details = await self._check_financial_data(
                    db, symbol6, market_type, analysis_date_str
                )
                details["financial_data"] = financial_details
                if not financial_valid:
                    missing_data.append("财务数据")
                    # Missing financial data does not prevent analysis, only a warning is logged
                    logger.warning(f"⚠️ 股票 {symbol6} 的财务数据不存在: {financial_msg}")
            
            # 4. Check real-time quotes (optional)
            if check_realtime_quotes:
                quotes_valid, quotes_msg, quotes_details = await self._check_realtime_quotes(
                    db, symbol6, market_type
                )
                details["realtime_quotes"] = quotes_details
                if not quotes_valid:
                    missing_data.append("实时行情")
                    # Lack of real-time market data does not prevent analysis, only warnings are recorded
                    logger.warning(f"⚠️ 股票 {symbol6} 的实时行情数据不存在: {quotes_msg}")
            
            # All required data is present
            return DataValidationResult(
                is_valid=True,
                message=f"股票 {symbol6} 的数据校验通过",
                missing_data=[],
                details=details
            )
            
        except Exception as e:
            logger.error(f"❌ 数据校验过程出错: {e}", exc_info=True)
            return DataValidationResult(
                is_valid=False,
                message=f"数据校验过程出错: {str(e)}",
                missing_data=["validation_error"],
                details={"error": str(e)}
            )
    
    async def _check_basic_info(
        self,
        db,
        symbol: str,
        market_type: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check whether basic stock information exists
        
        Returns:
            (is_valid, message, details)
        """
        try:
            # Select collections based on market type
            collection_map = {
                "cn": "stock_basic_info",
                "hk": "stock_basic_info_hk",
                "us": "stock_basic_info_us"
            }
            collection_name = collection_map.get(market_type, "stock_basic_info")
            
            # Query basic stock information
            query = {"$or": [{"symbol": symbol}, {"code": symbol}]}
            doc = await db[collection_name].find_one(query, {"_id": 0, "symbol": 1, "code": 1, "name": 1, "list_date": 1})
            
            if doc:
                return True, f"股票 {symbol} 基础信息存在", {
                    "exists": True,
                    "name": doc.get("name"),
                    "list_date": doc.get("list_date")
                }
            else:
                return False, f"股票 {symbol} 基础信息不存在", {
                    "exists": False,
                    "collection": collection_name
                }
        except Exception as e:
            logger.error(f"检查基础信息时出错: {e}")
            return False, f"检查基础信息时出错: {str(e)}", {"error": str(e)}
    
    async def _check_data_freshness(
        self,
        db,
        symbol: str,
        market_type: str,
        analysis_date: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check the freshness of daily stock market data to prevent the use of stale data for analysis.

        Rule: The latest trade_date of the stock in stock_daily_quotes (or collection with the same name) is relative to
        Data is considered stale when the analysis date (usually today) is more than 2 business days behind.

        Returns:
            (is_valid, message, details)
        """
        try:
            # Select daily quotation collection according to market type (priority decreases in order)
            collection_candidates = {
                "cn": ["stock_daily_quotes", "stock_daily_history", "market_quotes"],
                "hk": ["stock_daily_quotes_hk", "stock_daily_history_hk", "market_quotes_hk"],
                "us": ["stock_daily_quotes_us", "stock_daily_history_us", "market_quotes_us"],
            }
            candidates = collection_candidates.get(market_type, ["stock_daily_quotes", "market_quotes"])

            # Parse analysis date
            try:
                analysis_dt = datetime.strptime(analysis_date, '%Y-%m-%d')
            except ValueError:
                return True, "Parse date format cannot be parsed, freshness check skipped", {"skipped": True}

            latest_dt = None
            used_collection = None

            for col_name in candidates:
                # Query the latest daily price record of the stock
                doc = await db[col_name].find_one(
                    {"$or": [{"symbol": symbol}, {"code": symbol}, {"ts_code": {"$regex": f"^{symbol}"}}]},
                    {"_id": 0, "trade_date": 1, "date": 1, "updated_at": 1},
                    sort=[("trade_date", -1), ("date", -1), ("updated_at", -1)]
                )
                if not doc:
                    continue

                # Try parsing date from trade_date / date field
                raw_date = doc.get("trade_date") or doc.get("date")
                if raw_date:
                    for fmt in ('%Y-%m-%d', '%Y%m%d', '%Y/%m/%d'):
                        try:
                            latest_dt = datetime.strptime(str(raw_date), fmt)
                            break
                        except ValueError:
                            continue

                # If there is no trade_date/date, fall back and check updated_at
                if latest_dt is None and doc.get("updated_at"):
                    try:
                        updated_at = doc["updated_at"]
                        if isinstance(updated_at, datetime):
                            latest_dt = updated_at.replace(tzinfo=None)
                        else:
                            latest_dt = datetime.fromisoformat(str(updated_at))
                    except Exception:
                        pass

                if latest_dt is not None:
                    used_collection = col_name
                    break

            # If no data is found at all, it is considered missing data (returns False)
            if latest_dt is None:
                return False, (
                    f"股票 {symbol} 在数据库中没有日行情数据，"
                    "Please complete data synchronization before analysis"
                ), {
                    "latest_trade_date": None,
                    "analysis_date": analysis_date,
                    "collections_checked": candidates
                }

            # Calculate the number of working days behind
            # if latest_dt >= analysis_dt (Historical analysis), indicating that the data coverage is in place, directly through
            if latest_dt.date() >= analysis_dt.date():
                return True, (
                    f"Data freshness is normal (latest data date: {latest_dt.strftime('%Y-%m-%d')}) "
                ), {
                    "latest_trade_date": latest_dt.strftime('%Y-%m-%d'),
                    "analysis_date": analysis_date,
                    "collection": used_collection,
                    "days_behind": 0
                }

            # Calculate latest_dt → analysis_dt Number of working days between (Monday to Friday)
            missed_weekdays = 0
            cur = latest_dt.date()
            end = analysis_dt.date()
            while cur < end:
                cur_wd = cur.weekday()
                if cur_wd < 5:  # 0=Monday … 4=Friday
                    missed_weekdays += 1
                cur += timedelta(days=1)

            # Threshold: Allow up to 2 working days behind (can cover weekends + 1 day holiday)
            MAX_MISSED_WEEKDAYS = 2
            if missed_weekdays <= MAX_MISSED_WEEKDAYS:
                return True, (
                    f"数据新鲜度正常（最新数据日期: {latest_dt.strftime('%Y-%m-%d')}，"
                    f"backward {missed_weekdays} working days)"
                ), {
                    "latest_trade_date": latest_dt.strftime('%Y-%m-%d'),
                    "analysis_date": analysis_date,
                    "collection": used_collection,
                    "missed_weekdays": missed_weekdays
                }
            else:
                return False, (
                    f"股票 {symbol} 的行情数据已过期：数据库最新数据日期为 "
                    f"{latest_dt.strftime('%Y-%m-%d')}，"
                    f"date of analysis {analysis_date} Falling behind {missed_weekdays} working days."
                    "Please wait until data synchronization is completed before reinitiating analysis."
                ), {
                    "latest_trade_date": latest_dt.strftime('%Y-%m-%d'),
                    "analysis_date": analysis_date,
                    "collection": used_collection,
                    "missed_weekdays": missed_weekdays,
                    "threshold": MAX_MISSED_WEEKDAYS
                }

        except Exception as e:
            # When the freshness check is abnormal, it will be released conservatively (the analysis will not be blocked), but an error will be recorded.
            logger.error(f"⚠️ Data freshness check exception: {e}", exc_info=True)
            return True, f"Data freshness check exception (skipped): {str(e)}", {"error": str(e), "skipped": True}

    async def _check_historical_data(
        self,
        db,
        symbol: str,
        market_type: str,
        start_date: str,
        end_date: str,
        analysis_date: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check whether historical data exists and is within the analysis time range
        
        Returns:
            (is_valid, message, details)
        """
        try:
            # Select collections based on market type
            collection_map = {
                "cn": "stock_daily_quotes",  # Unified historical data collection
                "hk": "stock_daily_quotes_hk",
                "us": "stock_daily_quotes_us"
            }
            # If there is no corresponding collection, try using a universal collection
            collection_name = collection_map.get(market_type, "stock_daily_quotes")
            
            # If the collection does not exist, try using the old historical data collection
            collections_to_try = [
                collection_name,
                "stock_daily_history",  # Old historical data collection
                "stock_daily_quotes"  # universal collection
            ]
            
            data_found = False
            data_count = 0
            earliest_date = None
            latest_date = None
            analysis_date_data = None
            
            for coll_name in collections_to_try:
                try:
                    # Check if the collection exists
                    collection_names = await db.list_collection_names()
                    if coll_name not in collection_names:
                        continue

                    # 🔥 Detect which field is used to store the stock (symbol or code)
                    # Collections only have symbol indexes; use them directly $or The query will cause the code branch to scan the entire table (it takes several seconds for millions of documents)
                    if await db[coll_name].find_one({"symbol": symbol}, {"_id": 1}):
                        stock_filter = {"symbol": symbol}
                    else:
                        stock_filter = {"code": symbol}

                    # Query the total number of historical data
                    total_count = await db[coll_name].count_documents({
                        **stock_filter,
                        "trade_date": {"$gte": start_date, "$lte": end_date}
                    })

                    if total_count > 0:
                        data_found = True
                        data_count = total_count

                        # Query the earliest and latest dates
                        earliest_doc = await db[coll_name].find_one(
                            {**stock_filter, "trade_date": {"$gte": start_date}},
                            sort=[("trade_date", 1)]
                        )
                        latest_doc = await db[coll_name].find_one(
                            {**stock_filter, "trade_date": {"$lte": end_date}},
                            sort=[("trade_date", -1)]
                        )

                        if earliest_doc:
                            earliest_date = earliest_doc.get("trade_date")
                        if latest_doc:
                            latest_date = latest_doc.get("trade_date")

                        # Check whether data exists on the analysis date
                        analysis_doc = await db[coll_name].find_one({
                            **stock_filter,
                            "trade_date": analysis_date
                        })
                        analysis_date_data = analysis_doc is not None

                        break  # Exit the loop after finding the data
                except Exception as e:
                    logger.debug(f"查询集合 {coll_name} 时出错: {e}")
                    continue
            
            if data_found:
                # Check if the data is sufficient (at least a certain number of trading days are required)
                min_required_days = 30  # It takes at least 30 trading days
                if data_count < min_required_days:
                    return False, f"历史数据不足（仅 {data_count} 条，需要至少 {min_required_days} 条）", {
                        "exists": True,
                        "count": data_count,
                        "min_required": min_required_days,
                        "earliest_date": earliest_date,
                        "latest_date": latest_date,
                        "analysis_date_exists": analysis_date_data
                    }
                
                # Check whether data exists on the analysis date
                # If the data on the analysis date does not exist, intelligent judgment will be made based on the transaction time.
                # 🔥 Historical data checking has been done in collection priority order (stock_daily_quotes > stock_daily_history > stock_daily_quotes) 
                message = f"历史数据存在（共 {data_count} 条）"
                warning_flag = False  # initialization warning flag
                is_in_trading_hours = False  # Whether the mark is within trading hours
                
                if not analysis_date_data:
                    # Calculate the difference between the analysis date and the latest data date
                    if latest_date:
                        try:
                            from datetime import datetime, time as dtime
                            from zoneinfo import ZoneInfo
                            from app.core.config import settings
                            
                            latest_dt = datetime.strptime(str(latest_date), '%Y-%m-%d')
                            analysis_dt_check = datetime.strptime(analysis_date, '%Y-%m-%d')
                            days_diff = (analysis_dt_check - latest_dt).days
                            
                            # Determine whether the analysis date is today
                            tz = ZoneInfo(settings.TIMEZONE)
                            today = datetime.now(tz).date()
                            analysis_date_obj = analysis_dt_check.date()
                            is_today = (analysis_date_obj == today)
                            
                            # 🔥 If the analysis date is today, check the transaction time no matter what days_diff is
                            if is_today:
                                # The analysis date is today, check the current time
                                current_time = datetime.now(tz).time()
                                market_open_time = dtime(9, 30)  # opening time
                                market_close_time = dtime(16, 30)  # End time of buffer period after closing
                                
                                logger.info(f"🔍 [Data verification] The analysis date is today, current time:{current_time.strftime('%H:%M:%S')}, Opening time:09:30, Closing time:16:30")
                                
                                # 🔥 Check the read-only local library: the transaction day is judged by working days, and the external data interface is not adjusted.
                                #  (Pulling data is"sync"For buttons, the test only reports the current status of the local library)
                                is_trading_day = today.weekday() < 5
                                logger.info(f"🔍 [Data verification] Whether the trading day (approximate working days):{is_trading_day}")
                                
                                if is_trading_day:
                                    if current_time < market_open_time:
                                        # It's not the opening time yet, so it's normal to lack data for the day.
                                        message += f", Analysis Date ({analysis_date}) It is a trading day but has not yet opened (current time:{current_time.strftime('%H:%M')}, Opening time:09:30) , Lack of data for the current day is normal"
                                        logger.info(f"ℹ️ 股票 {symbol} 分析日期 {analysis_date} 是交易日但尚未开盘，缺少当天数据属正常情况")
                                        warning_flag = False  # No warning before opening
                                    elif market_open_time <= current_time <= market_close_time:
                                        # During trading hours, it is normal that the data for the day has not been generated yet.
                                        # 🔥 No more real-time data will be pulled on-site to supplement (testing is read-only, please use"sync"function)
                                        is_in_trading_hours = True  # Marked within trading hours (no warning will be forced later)
                                        message += f", Analysis Date ({analysis_date}) During trading hours, data for the day has not yet been generated (current time:{current_time.strftime('%H:%M')}) , It s normal"
                                        warning_flag = False  # No warning during trading hours
                                        logger.info(f"ℹ️ 股票 {symbol} 分析日期 {analysis_date} 在交易时间内，当天数据尚未生成，属正常情况，warning_flag=False")
                                    else:
                                        # The closing time has passed and data should already be available.
                                        message += f"，但分析日期（{analysis_date}）当天的数据不存在（最新数据日期：{latest_date}，相差 {days_diff} 天）"
                                        warning_flag = True  # No data after close, warning required
                                        logger.warning(f"⚠️ 股票 {symbol} 分析日期 {analysis_date} 的数据不存在，最新数据日期：{latest_date}，warning_flag=True")
                                else:
                                    # Not a trading day
                                    message += f", Analysis Date ({analysis_date}) It is not a trading day. It is normal to lack data on that day."
                                    warning_flag = False  # No warning on non-trading days
                                    logger.info(f"ℹ️ 股票 {symbol} 分析日期 {analysis_date} 不是交易日，缺少当天数据属正常情况，warning_flag=False")
                            elif not is_today and days_diff > 0:
                                # The analysis date is a future date or a past date
                                message += f"，但分析日期（{analysis_date}）当天的数据不存在（最新数据日期：{latest_date}，相差 {days_diff} 天）"
                                warning_flag = True  # No data for future or past dates, requires warning
                                logger.warning(f"⚠️ 股票 {symbol} 分析日期 {analysis_date} 的数据不存在，最新数据日期：{latest_date}")
                            else:
                                # The analysis date is not today, and days_diff <= 0
                                message += f"，但分析日期（{analysis_date}）当天的数据不存在"
                                warning_flag = True  # No data, warning required
                                logger.warning(f"⚠️ 股票 {symbol} 分析日期 {analysis_date} 的数据不存在")
                        except Exception as e:
                            logger.error(f"检查分析日期数据时出错: {e}", exc_info=True)
                            message += f"，但分析日期（{analysis_date}）当天的数据不存在"
                            warning_flag = True  # Check error, need warning
                            logger.warning(f"⚠️ 股票 {symbol} 分析日期 {analysis_date} 的数据不存在")
                    else:
                        # Without latest_date, it is impossible to judge
                        message += f"，但分析日期（{analysis_date}）当天的数据不存在"
                        warning_flag = True  # No data, warning required
                        logger.warning(f"⚠️ 股票 {symbol} 分析日期 {analysis_date} 的数据不存在")
                
                # 🔥 If analysis_date_data is True, it means that the data exists and no warning is needed.
                if analysis_date_data:
                    warning_flag = False
                    logger.info("✅ [Data verification] Analyze date data exists, set warning_flag=False")
                
                # 🔥 If within trading hours, no warning is forced (to prevent being overwritten by other logic)
                if is_in_trading_hours:
                    warning_flag = False
                    logger.info("✅ [Data verification] During trading hours, mandatory setting warning_flag=False")
                
                # 🔥 Final log: records the final value of the warning flag
                logger.info(f"📊 [Data verification] eventually warning_flag={warning_flag}, analysis_date_data={analysis_date_data}, is_in_trading_hours={is_in_trading_hours}")
                
                return True, message, {
                    "exists": True,
                    "count": data_count,
                    "earliest_date": earliest_date,
                    "latest_date": latest_date,
                    "analysis_date_exists": analysis_date_data,
                    "date_range": f"{start_date} 至 {end_date}",
                    "warning": warning_flag  # 🔥 Intelligently determine whether to warn based on transaction time
                }
            else:
                return False, f"历史数据不存在（日期范围: {start_date} 至 {end_date}）", {
                    "exists": False,
                    "date_range": f"{start_date} 至 {end_date}",
                    "collections_checked": collections_to_try
                }
        except Exception as e:
            logger.error(f"检查历史数据时出错: {e}")
            return False, f"检查历史数据时出错: {str(e)}", {"error": str(e)}

    async def _check_financial_data(
        self,
        db,
        symbol: str,
        market_type: str,
        analysis_date: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check if financial data exists
        
        Returns:
            (is_valid, message, details)
        """
        try:
            # Select collections based on market type
            collection_map = {
                "cn": "stock_financial_data",
                "hk": "stock_financial_data_hk",
                "us": "stock_financial_data_us"
            }
            collection_name = collection_map.get(market_type, "stock_financial_data")
            
            # Query the latest financial data (no date limit, because financial data is updated regularly)
            doc = await db[collection_name].find_one(
                {"$or": [{"symbol": symbol}, {"code": symbol}]},
                sort=[("report_period", -1)],
                projection={"_id": 0, "symbol": 1, "report_period": 1, "report_type": 1}
            )
            
            if doc:
                return True, f"Financial data exists (latest reporting period: {doc.get('report_period')}) ", {
                    "exists": True,
                    "latest_report_period": doc.get("report_period"),
                    "report_type": doc.get("report_type")
                }
            else:
                return False, "财务数据不存在", {
                    "exists": False,
                    "collection": collection_name
                }
        except Exception as e:
            logger.error(f"检查财务数据时出错: {e}")
            return False, f"检查财务数据时出错: {str(e)}", {"error": str(e)}
    
    async def _check_realtime_quotes(
        self,
        db,
        symbol: str,
        market_type: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check whether real-time market data exists
        
        Returns:
            (is_valid, message, details)
        """
        try:
            # Select collections based on market type
            collection_map = {
                "cn": "market_quotes",
                "hk": "market_quotes_hk",
                "us": "market_quotes_us"
            }
            collection_name = collection_map.get(market_type, "market_quotes")
            
            # Check real-time market conditions
            doc = await db[collection_name].find_one(
                {"$or": [{"symbol": symbol}, {"code": symbol}]},
                projection={"_id": 0, "symbol": 1, "code": 1, "close": 1, "update_time": 1}
            )
            
            if doc:
                return True, "实时行情存在", {
                    "exists": True,
                    "current_price": doc.get("close"),
                    "update_time": doc.get("update_time")
                }
            else:
                return False, "实时行情不存在", {
                    "exists": False,
                    "collection": collection_name
                }
        except Exception as e:
            logger.error(f"检查实时行情时出错: {e}")
            return False, f"检查实时行情时出错: {str(e)}", {"error": str(e)}


# Singleton instance
_validation_service = None


def get_data_validation_service() -> DataValidationService:
    """获取数据校验服务单例"""
    global _validation_service
    if _validation_service is None:
        _validation_service = DataValidationService()
    return _validation_service
