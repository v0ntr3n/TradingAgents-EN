"""
Local data source adapter for user-imported data
"""
from typing import Optional, Dict
import logging
import pandas as pd

from .base import DataSourceAdapter

logger = logging.getLogger(__name__)


class LocalAdapter(DataSourceAdapter):
    """Local data source adapter (data imported by users through API)"""

    def __init__(self):
        super().__init__()  # Call parent class initialization

    @property
    def name(self) -> str:
        return "local"

    def _get_default_priority(self) -> int:
        return 10  # The default is the highest priority (the larger the number, the higher the priority)

    def is_available(self) -> bool:
        """Check if the local data source is available (check if there is local data in MongoDB)"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            collection = db.stock_basic_info
            
            # Check if there is source='local' data
            count = collection.count_documents({"source": "local"}, limit=1)
            return count > 0
        except Exception as e:
            logger.warning(f"Local: Failed to check availability: {e}")
            return False

    def get_stock_list(self) -> Optional[pd.DataFrame]:
        """获取本地股票列表"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            collection = db.stock_basic_info
            
            # Query source='local' stocks
            cursor = collection.find({"source": "local"})
            stocks = list(cursor)
            
            if not stocks:
                logger.info("Local: No local stocks found")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(stocks)
            
            # Standardize field names (make sure you have the required fields)
            if 'symbol' in df.columns and 'name' in df.columns:
                logger.info(f"Local: Successfully fetched {len(df)} local stocks")
                return df
            else:
                logger.warning("Local: Missing required fields (symbol, name)")
                return None
                
        except Exception as e:
            logger.error(f"Local: Failed to fetch stock list: {e}")
            return None

    def get_daily_basic(self, trade_date: str) -> Optional[pd.DataFrame]:
        """Obtain daily basic financial data (local data sources are not supported yet)"""
        logger.warning("Local: get_daily_basic not supported")
        return None

    def find_latest_trade_date(self) -> Optional[str]:
        """Find the latest transaction date (from local K-line data)"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            collection = db.stock_daily_quotes

            # Query data_source='local' latest transaction date
            cursor = collection.find(
                {"data_source": "local"},
                {"trade_date": 1}
            ).sort("trade_date", -1).limit(1)

            result = list(cursor)
            if result:
                latest_date = result[0].get('trade_date')
                logger.info(f"Local: Latest trade date: {latest_date}")
                return latest_date
            else:
                logger.info("Local: No trade date found")
                return None

        except Exception as e:
            logger.error(f"Local: Failed to find latest trade date: {e}")
            return None

    def get_realtime_quotes(self) -> Optional[Dict[str, Dict[str, Optional[float]]]]:
        """Get real-time quotes (read from local database)"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            collection = db.market_quotes
            
            # Query all market data
            cursor = collection.find({})
            quotes = list(cursor)
            
            if not quotes:
                logger.info("Local: No local quotes found")
                return None
            
            # Convert to dictionary format
            result = {}
            for quote in quotes:
                symbol = quote.get('symbol')
                if symbol:
                    result[symbol] = {
                        'close': quote.get('close'),
                        'pct_chg': quote.get('pct_chg'),
                        'amount': quote.get('amount')
                    }
            
            logger.info(f"Local: Successfully fetched {len(result)} quotes")
            return result
            
        except Exception as e:
            logger.error(f"Local: Failed to fetch realtime quotes: {e}")
            return None

    def get_kline(self, code: str, period: str = "day", limit: int = 120, adj: Optional[str] = None):
        """Get K-line data (read from local database)"""
        try:
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            collection = db.stock_daily_quotes

            period_map = {
                "day": "daily",
                "week": "weekly",
                "month": "monthly",
                "5m": "5min",
                "15m": "15min",
                "30m": "30min",
                "60m": "60min",
            }
            normalized_period = period_map.get(period, period)
            
            # Query K line data
            cursor = collection.find(
                {"symbol": code, "data_source": "local", "period": normalized_period}
            ).sort("trade_date", 1).limit(limit)
            
            klines = list(cursor)
            
            if not klines:
                logger.info(f"Local: No kline data found for {code} (period={normalized_period})")
                return []
            
            # Convert to standard format
            result = []
            for kline in klines:
                result.append({
                    'time': kline.get('trade_date'),
                    'open': kline.get('open'),
                    'high': kline.get('high'),
                    'low': kline.get('low'),
                    'close': kline.get('close'),
                    'volume': kline.get('volume'),
                    'amount': kline.get('amount')
                })
            
            logger.info(f"Local: Successfully fetched {len(result)} klines for {code} (period={normalized_period})")
            return result
            
        except Exception as e:
            logger.error(f"Local: Failed to fetch kline for {code}: {e}")
            return []

    def get_news(self, code: str, days: int = 2, limit: int = 50, include_announcements: bool = True):
        """Get news/announcements (not supported by local data sources)"""
        logger.warning("Local: get_news not supported")
        return []

