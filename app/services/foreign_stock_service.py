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
import yfinance as yf
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
            import requests, os
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
                logger.warning(f"⚠️ There is no valid Hong Kong stock data source configured in the database, and the default order is used.")
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
            except:
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

