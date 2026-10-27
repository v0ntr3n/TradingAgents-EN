#!/usr/bin/env python3
"""
Optimized US stock data acquisition tool
Integrate caching strategies to reduce API calls and improve response speed
"""

import os
import time
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from typing import Optional, Dict, Any
import yfinance as yf
import pandas as pd

# Import cache manager (supports old and new paths)
try:
    from ...cache import StockDataCache
    def get_cache():
        return StockDataCache()
except ImportError:
    from ...cache_manager import get_cache

# Import configuration (supports old and new paths)
try:
    from ...config import get_config
except ImportError:
    def get_config():
        return {}

from tradingagents.config.runtime_settings import get_float, get_timezone_name
# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')


class OptimizedUSDataProvider:
    """Optimized US stock data provider - integrated caching and API limit handling"""

    def __init__(self):
        self.cache = get_cache()
        self.config = get_config()
        self.last_api_call = 0
        self.min_api_interval = get_float("TA_US_MIN_API_INTERVAL_SECONDS", "ta_us_min_api_interval_seconds", 1.0)

        # 🔥 Initialize the data source manager (read configuration from database)
        try:
            from tradingagents.dataflows.data_source_manager import USDataSourceManager
            self.us_manager = USDataSourceManager()
            logger.info(f"✅ US stock data source manager initialized successfully")
        except Exception as e:
            logger.warning(f"⚠️ US stock data source manager initialization failed: {e}, Default order will be used")
            self.us_manager = None

        logger.info(f"📊 Optimization of US stock data provider initialization completed")

    def get_daily_data(self, symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        Get daily data on US stocks (Return DataFrame)
        Unified return format: columns=['date', 'open', 'high', 'low', 'close', 'volume']
        """
        logger.info(f"📈 获取美股DataFrame数据: {symbol} ({start_date} 到 {end_date})")

        # 0. Try to get from cache
        try:
            # Find cache (Yahoo Finance)
            cache_key = self.cache.find_cached_stock_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                data_source="yfinance",
                max_age_hours=24  # U.S. stock data cached for 24 hours
            )
            
            if cache_key:
                df = self.cache.load_stock_data(cache_key)
                if df is not None and not df.empty:
                    # Make sure the date column is formatted correctly
                    if 'date' not in df.columns and isinstance(df.index, pd.DatetimeIndex):
                        df = df.reset_index()
                        df.rename(columns={'index': 'date', 'Date': 'date'}, inplace=True)
                    
                    # Make sure column names are lowercase
                    df.columns = [c.lower() for c in df.columns]
                    
                    # Make sure you include the required columns
                    required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
                    if all(col in df.columns for col in required_cols):
                        # Format date
                        if pd.api.types.is_datetime64_any_dtype(df['date']):
                            df['date'] = df['date'].dt.strftime('%Y-%m-%d')
                        
                        df = df[required_cols]
                        logger.info(f"✅ [缓存] 获取美股DataFrame成功: {symbol} ({len(df)}条)")
                        return df
        except Exception as e:
            logger.warning(f"⚠️ 读取缓存失败: {e}")

        # 1. Try using Yahoo Finance (Most commonly used and returned DataFrame)
        try:
            self._wait_for_rate_limit()
            ticker = yf.Ticker(symbol.upper())
            df = ticker.history(start=start_date, end=end_date)
            
            if not df.empty:
                # Reset index, turn Date into column
                df = df.reset_index()
                
                # Standardized column names
                df.columns = [c.lower() for c in df.columns]
                
                # Make sure you include the required columns
                required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
                if all(col in df.columns for col in required_cols):
                    # Format date column as string
                    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
                    
                    # Select and sort columns
                    df = df[required_cols]
                    
                    # Save to cache
                    try:
                        self.cache.save_stock_data(
                            symbol=symbol,
                            data=df,
                            start_date=start_date,
                            end_date=end_date,
                            data_source="yfinance"
                        )
                    except Exception as e:
                        logger.warning(f"⚠️ 保存缓存失败: {e}")
                    
                    logger.info(f"✅ [Yahoo Finance] 获取美股DataFrame成功: {symbol} ({len(df)}条)")
                    return df
        except Exception as e:
            logger.error(f"❌ [Yahoo Finance] Failed to get DataFrame: {e}")

        # 2. If YFinance fails, try Alpha Vantage
        try:
            self._wait_for_rate_limit()
            from tradingagents.dataflows.providers.us.alpha_vantage_common import get_api_key
            import requests
            
            api_key = get_api_key()
            if api_key:
                url = "https://www.alphavantage.co/query"
                params = {
                    "function": "TIME_SERIES_DAILY",
                    "symbol": symbol.upper(),
                    "apikey": api_key,
                    "outputsize": "full"
                }
                response = requests.get(url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    ts = data.get("Time Series (Daily)", {})
                    if ts:
                        df = pd.DataFrame.from_dict(ts, orient='index')
                        df.index = pd.to_datetime(df.index)
                        df = df.sort_index()
                        df = df[(df.index >= start_date) & (df.index <= end_date)]
                        
                        if not df.empty:
                            df = df.reset_index()
                            df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
                            df['date'] = df['date'].dt.strftime('%Y-%m-%d')
                            # Convert numeric type
                            for col in ['open', 'high', 'low', 'close', 'volume']:
                                df[col] = df[col].astype(float)
                                
                            logger.info(f"✅ [Alpha Vantage] 获取美股DataFrame成功: {symbol} ({len(df)}条)")
                            return df
        except Exception as e:
            logger.error(f"❌ [Alpha Vantage] Failed to get DataFrame: {e}")

        logger.warning(f"⚠️ Unable to obtain US stock DataFrame data: {symbol}")
        return None

    def _wait_for_rate_limit(self):
        """等待API限制"""
        current_time = time.time()
        time_since_last_call = current_time - self.last_api_call

        if time_since_last_call < self.min_api_interval:
            wait_time = self.min_api_interval - time_since_last_call
            logger.info(f"⏳ API限制等待 {wait_time:.1f}s...")
            time.sleep(wait_time)

        self.last_api_call = time.time()

    def get_stock_data(self, symbol: str, start_date: str, end_date: str,
                      force_refresh: bool = False) -> str:
        """
        Get U.S. stock data - use cache first

        Args:
            symbol: Stock code
            start_date: start date (YYYY-MM-DD)
            end_date: end date (YYYY-MM-DD)
            force_refresh: Whether to force cache refresh

        Returns:
            Formatted stock data string
        """
        logger.info(f"📈 获取美股数据: {symbol} ({start_date} 到 {end_date})")

        # Check cache (unless force refresh)
        if not force_refresh:
            # 🔥 Find the cache in data source priority order
            from ...data_source_manager import get_us_data_source_manager, USDataSource
            us_manager = get_us_data_source_manager()

            # Get data source priority order
            priority_order = us_manager._get_data_source_priority_order(symbol)

            # Data source name mapping
            source_name_mapping = {
                USDataSource.ALPHA_VANTAGE: "alpha_vantage",
                USDataSource.YFINANCE: "yfinance",
                USDataSource.FINNHUB: "finnhub",
            }

            # Find cache in order of priority
            for source in priority_order:
                if source == USDataSource.MONGODB:
                    continue  # MongoDB Caching is handled separately

                source_name = source_name_mapping.get(source)
                if source_name:
                    cache_key = self.cache.find_cached_stock_data(
                        symbol=symbol,
                        start_date=start_date,
                        end_date=end_date,
                        data_source=source_name
                    )

                    if cache_key:
                        cached_data = self.cache.load_stock_data(cache_key)
                        if cached_data:
                            logger.info(f"⚡ [数据来源: 缓存-{source_name}] 从缓存加载美股数据: {symbol}")
                            return cached_data

        # Cache miss, obtained from API - using data source manager's priority order
        formatted_data = None
        data_source = None

        # 🔥 Get priority order from data source manager
        if self.us_manager:
            try:
                source_priority = self.us_manager._get_data_source_priority_order(symbol)
                logger.info(f"📊 [U.S. stock data source priority] Read from database: {[s.value for s in source_priority]}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to get data source priority: {e}, Use default order")
                source_priority = None
        else:
            source_priority = None

        # If no priority is configured, the default order is used
        if not source_priority:
            # Default order:yfinance > alpha_vantage > finnhub
            from tradingagents.dataflows.data_source_manager import USDataSource
            source_priority = [USDataSource.YFINANCE, USDataSource.ALPHA_VANTAGE, USDataSource.FINNHUB]
            logger.info(f"📊 [U.S. stock data source priority] Use default order: {[s.value for s in source_priority]}")

        # Try each data source in order of priority
        for source in source_priority:
            try:
                source_name = source.value
                logger.info(f"🌐 [数据来源: API调用-{source_name.upper()}] 尝试从 {source_name.upper()} 获取数据: {symbol}")
                self._wait_for_rate_limit()

                # Call different methods based on data source type
                if source_name == 'finnhub':
                    formatted_data = self._get_data_from_finnhub(symbol, start_date, end_date)
                elif source_name == 'alpha_vantage':
                    formatted_data = self._get_data_from_alpha_vantage(symbol, start_date, end_date)
                elif source_name == 'yfinance':
                    formatted_data = self._get_data_from_yfinance(symbol, start_date, end_date)
                else:
                    logger.warning(f"⚠️ 未知的数据源类型: {source_name}")
                    continue

                if formatted_data and "❌" not in formatted_data:
                    data_source = source_name
                    logger.info(f"✅ [数据来源: API调用成功-{source_name.upper()}] {source_name.upper()} 数据获取成功: {symbol}")
                    break  # Successfully obtain data and break out of the loop
                else:
                    logger.warning(f"⚠️ [Data source: API failed-{source_name.upper()}] {source_name.upper()} Data acquisition failed, try the next data source")
                    formatted_data = None

            except Exception as e:
                logger.error(f"❌ [数据来源: API异常-{source.value.upper()}] {source.value.upper()} API调用失败: {e}")
                formatted_data = None
                continue  # Try next data source

        # If all configured data sources fail, try alternatives
        if not formatted_data:
            try:
                # Detect stock type
                from tradingagents.utils.stock_utils import StockUtils
                market_info = StockUtils.get_market_info(symbol)

                if market_info['is_hk']:
                    # Hong Kong stocks give priority to using AKShare data source
                    logger.info(f"🇭🇰 [Data source: API call-AKShare] Try using AKShare to obtain Hong Kong stock data: {symbol}")
                    try:
                        from tradingagents.dataflows.interface import get_hk_stock_data_unified
                        hk_data_text = get_hk_stock_data_unified(symbol, start_date, end_date)

                        if hk_data_text and "❌" not in hk_data_text:
                            formatted_data = hk_data_text
                            data_source = "akshare_hk"
                            logger.info(f"✅ [Data source: API Call successful-AKShare] AKShare Hong Kong stock data obtained successfully: {symbol}")
                        else:
                            raise Exception("AKShare Failed to obtain Hong Kong stock data")

                    except Exception as e:
                        logger.error(f"⚠️ [Data source: API failed-AKShare] AKShare Failed to obtain Hong Kong stock data: {e}")
                        # Alternate plan:Yahoo Finance
                        logger.info(f"🔄 [Data source: API Call-Yahoo Finance Alternate] Use Yahoo Finance alternative to obtain Hong Kong stock data: {symbol}")

                        self._wait_for_rate_limit()
                        ticker = yf.Ticker(symbol)  # Hong Kong stock codes remain in their original format
                        data = ticker.history(start=start_date, end=end_date)

                        if not data.empty:
                            formatted_data = self._format_stock_data(symbol, data, start_date, end_date)
                            data_source = "yfinance_hk"
                            logger.info(f"✅ [Data source: API Call successful-Yahoo Finance] Yahoo Finance Hong Kong stock data obtained successfully: {symbol}")
                        else:
                            logger.error(f"❌ [Data source: API failed-Yahoo Finance] Yahoo Finance Hong Kong stock data is empty: {symbol}")
                else:
                    # US stocks use Yahoo Finance
                    logger.info(f"🇺🇸 [Data source: API call-Yahoo Finance] Get US stock data from Yahoo Finance API: {symbol}")
                    self._wait_for_rate_limit()

                    # Get data
                    ticker = yf.Ticker(symbol.upper())
                    data = ticker.history(start=start_date, end=end_date)

                    if data.empty:
                        error_msg = f"未找到股票 '{symbol}' 在 {start_date} 到 {end_date} 期间的数据"
                        logger.error(f"❌ [Data source: API failed-Yahoo Finance] {error_msg}")
                    else:
                        # Format data
                        formatted_data = self._format_stock_data(symbol, data, start_date, end_date)
                        data_source = "yfinance"
                        logger.info(f"✅ [Data source: API Call successful-Yahoo Finance] Yahoo Finance US stock data obtained successfully: {symbol}")

            except Exception as e:
                logger.error(f"❌ [Data source: API Abnormal] Data acquisition failed: {e}")
                formatted_data = None

        # Generate backup data if all APIs fail
        if not formatted_data:
            error_msg = "所有美股数据源都不可用"
            logger.error(f"❌ [Data source: All APIs failed] {error_msg}")
            logger.warning(f"⚠️ [Data source: backup data] Generate backup data: {symbol}")
            return self._generate_fallback_data(symbol, start_date, end_date, error_msg)

        # Save to cache
        self.cache.save_stock_data(
            symbol=symbol,
            data=formatted_data,
            start_date=start_date,
            end_date=end_date,
            data_source=data_source
        )

        logger.info(f"💾 [数据来源: {data_source}] 数据已缓存: {symbol}")
        return formatted_data

    def _format_stock_data(self, symbol: str, data: pd.DataFrame,
                          start_date: str, end_date: str) -> str:
        """格式化股票数据为字符串"""

        # Remove time zone information
        if data.index.tz is not None:
            data.index = data.index.tz_localize(None)

        # Round values
        numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
        for col in numeric_columns:
            if col in data.columns:
                data[col] = data[col].round(2)

        # Get the latest prices and statistics
        latest_price = data['Close'].iloc[-1]
        price_change = data['Close'].iloc[-1] - data['Close'].iloc[0]
        price_change_pct = (price_change / data['Close'].iloc[0]) * 100

        # 🔥 Use unified technical indicator calculation functions
        # Note: U.S. stock data column names are in capital letters Close, High, Low
        from tradingagents.tools.analysis.indicators import add_all_indicators
        data = add_all_indicators(data, close_col='Close', high_col='High', low_col='Low')

        # Get the latest technical indicators
        latest = data.iloc[-1]

        # Formatted output
        result = f"""# {symbol} 美股数据分析

## 📊 基本信息
- 股票代码: {symbol}
- 数据期间: {start_date} 至 {end_date}
- 数据条数: {len(data)}条
- 最新价格: ${latest_price:.2f}
- 期间涨跌: ${price_change:+.2f} ({price_change_pct:+.2f}%)

## 📈 价格统计
- 期间最高: ${data['High'].max():.2f}
- 期间最低: ${data['Low'].min():.2f}
- 平均成交量: {data['Volume'].mean():,.0f}

## 🔍 技术指标（最新值）
**移动平均线**:
- MA5: ${latest['ma5']:.2f}
- MA10: ${latest['ma10']:.2f}
- MA20: ${latest['ma20']:.2f}
- MA60: ${latest['ma60']:.2f}

**MACD指标**:
- DIF: {latest['macd_dif']:.2f}
- DEA: {latest['macd_dea']:.2f}
- MACD: {latest['macd']:.2f}

**RSI指标**:
- RSI(14): {latest['rsi']:.2f}

**布林带**:
- 上轨: ${latest['boll_upper']:.2f}
- 中轨: ${latest['boll_mid']:.2f}
- 下轨: ${latest['boll_lower']:.2f}

## 📋 最近5日数据
{data[['Open', 'High', 'Low', 'Close', 'Volume']].tail().to_string()}

数据来源: Yahoo Finance API
更新时间: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}
"""

        return result

    def _try_get_old_cache(self, symbol: str, start_date: str, end_date: str) -> Optional[str]:
        """Try to get expired cached data as backup"""
        try:
            # Find any relevant caches, regardless of TTL
            for metadata_file in self.cache.metadata_dir.glob(f"*_meta.json"):
                try:
                    import json
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)

                    if (metadata.get('symbol') == symbol and
                        metadata.get('data_type') == 'stock_data' and
                        metadata.get('market_type') == 'us'):

                        cache_key = metadata_file.stem.replace('_meta', '')
                        cached_data = self.cache.load_stock_data(cache_key)
                        if cached_data:
                            return cached_data + "\n\n⚠️ Note: Using expired cached data"
                except Exception:
                    continue
        except Exception:
            pass

        return None

    def _get_data_from_finnhub(self, symbol: str, start_date: str, end_date: str) -> str:
        """Get stock data from FINNHUB API"""
        try:
            import finnhub
            import os
            from datetime import datetime, timedelta


            # Get API key
            api_key = os.getenv('FINNHUB_API_KEY')
            if not api_key:
                return None

            client = finnhub.Client(api_key=api_key)

            # Get real-time quotes
            quote = client.quote(symbol.upper())
            if not quote or 'c' not in quote:
                return None

            # Get company information
            profile = client.company_profile2(symbol=symbol.upper())
            company_name = profile.get('name', symbol.upper()) if profile else symbol.upper()

            # Format data
            current_price = quote.get('c', 0)
            change = quote.get('d', 0)
            change_percent = quote.get('dp', 0)

            formatted_data = f"""# {symbol.upper()} 美股数据分析

## 📊 实时行情
- 股票名称: {company_name}
- 当前价格: ${current_price:.2f}
- 涨跌额: ${change:+.2f}
- 涨跌幅: {change_percent:+.2f}%
- 开盘价: ${quote.get('o', 0):.2f}
- 最高价: ${quote.get('h', 0):.2f}
- 最低价: ${quote.get('l', 0):.2f}
- 前收盘: ${quote.get('pc', 0):.2f}
- 更新时间: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}

## 📈 数据概览
- 数据期间: {start_date} 至 {end_date}
- 数据来源: FINNHUB API (实时数据)
- 当前价位相对位置: {((current_price - quote.get('l', current_price)) / max(quote.get('h', current_price) - quote.get('l', current_price), 0.01) * 100):.1f}%
- 日内振幅: {((quote.get('h', 0) - quote.get('l', 0)) / max(quote.get('pc', 1), 0.01) * 100):.2f}%

生成时间: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}
"""

            return formatted_data

        except Exception as e:
            logger.error(f"❌ FINNHUB Data acquisition failed: {e}")
            return None

    def _get_data_from_yfinance(self, symbol: str, start_date: str, end_date: str) -> str:
        """Get stock data from Yahoo Finance API"""
        try:
            # Get data
            ticker = yf.Ticker(symbol.upper())
            data = ticker.history(start=start_date, end=end_date)

            if data.empty:
                error_msg = f"未找到股票 '{symbol}' 在 {start_date} 到 {end_date} 期间的数据"
                logger.error(f"❌ Yahoo Finance Data is empty: {error_msg}")
                return None

            # Format data
            formatted_data = self._format_stock_data(symbol, data, start_date, end_date)
            return formatted_data

        except Exception as e:
            logger.error(f"❌ Yahoo Finance Data acquisition failed: {e}")
            return None

    def _get_data_from_alpha_vantage(self, symbol: str, start_date: str, end_date: str) -> str:
        """Get stock data from Alpha Vantage API"""
        try:
            from tradingagents.dataflows.providers.us.alpha_vantage_common import get_api_key
            import requests
            from datetime import datetime

            # get API Key
            api_key = get_api_key()
            if not api_key:
                logger.warning("⚠️ Alpha Vantage API Key Not configured")
                return None

            # call Alpha Vantage API (TIME_SERIES_DAILY)
            url = f"https://www.alphavantage.co/query"
            params = {
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol.upper(),
                "apikey": api_key,
                "outputsize": "full"  # Get complete historical data
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data_json = response.json()

            # Check for errors
            if "Error Message" in data_json:
                logger.error(f"❌ Alpha Vantage API Error: {data_json['Error Message']}")
                return None

            if "Note" in data_json:
                logger.warning(f"⚠️ Alpha Vantage API Limit: {data_json['Note']}")
                return None

            # Parse time series data
            time_series = data_json.get("Time Series (Daily)", {})
            if not time_series:
                logger.error("❌ Alpha Vantage Return data is empty")
                return None

            # Convert to DataFrame
            df = pd.DataFrame.from_dict(time_series, orient='index')
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()

            # Rename columns
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            df = df.astype(float)

            # Filter date range
            df = df[(df.index >= start_date) & (df.index <= end_date)]

            if df.empty:
                logger.error(f"❌ Alpha Vantage Data is empty within the specified date range")
                return None

            # Format data
            formatted_data = self._format_stock_data(symbol, df, start_date, end_date)
            return formatted_data

        except Exception as e:
            logger.error(f"❌ Alpha Vantage Data acquisition failed: {e}")
            return None

    def _generate_fallback_data(self, symbol: str, start_date: str, end_date: str, error_msg: str) -> str:
        """生成备用数据"""
        return f"""# {symbol} 美股数据获取失败

## ❌ 错误信息
{error_msg}

## 📊 模拟数据（仅供演示）
- 股票代码: {symbol}
- 数据期间: {start_date} 至 {end_date}
- 最新价格: ${random.uniform(100, 300):.2f}
- 模拟涨跌: {random.uniform(-5, 5):+.2f}%

## ⚠️ 重要提示
由于API限制或网络问题，无法获取实时数据。
建议稍后重试或检查网络连接。

生成时间: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}
"""


# global instance
_us_data_provider = None

def get_optimized_us_data_provider() -> OptimizedUSDataProvider:
    """Get global US stock data provider instance"""
    global _us_data_provider
    if _us_data_provider is None:
        _us_data_provider = OptimizedUSDataProvider()
    return _us_data_provider


def get_us_stock_data_cached(symbol: str, start_date: str, end_date: str,
                           force_refresh: bool = False) -> str:
    """
    Convenient function to obtain US stock data

    Args:
        symbol: Stock code
        start_date: start date (YYYY-MM-DD)
        end_date: end date (YYYY-MM-DD)
        force_refresh: Whether to force cache refresh

    Returns:
        Formatted stock data string
    """
    # 🔧 Smart date range handling: automatically expands to configured lookback days, handles weekends/holidays
    from tradingagents.utils.dataflow_utils import get_trading_date_range
    from app.core.config import get_settings
    from datetime import datetime

    original_start_date = start_date
    original_end_date = end_date

    # Get market analysis lookback days from configuration (default 60 days)
    try:
        settings = get_settings()
        lookback_days = settings.MARKET_ANALYST_LOOKBACK_DAYS
        logger.info(f"📅 [美股配置验证] MARKET_ANALYST_LOOKBACK_DAYS: {lookback_days}天")
    except Exception as e:
        lookback_days = 60  # Default 60 days
        logger.warning(f"⚠️ [美股配置验证] 无法获取配置，使用默认值: {lookback_days}天")
        logger.warning(f"⚠️ [US stock allocation verification] Error details: {e}")

    # Use end_date as the target date to look back a specified number of days
    start_date, end_date = get_trading_date_range(end_date, lookback_days=lookback_days)

    logger.info(f"📅 [美股智能日期] 原始输入: {original_start_date} 至 {original_end_date}")
    logger.info(f"📅 [美股智能日期] 回溯天数: {lookback_days}天")
    logger.info(f"📅 [美股智能日期] 计算结果: {start_date} 至 {end_date}")
    logger.info(f"📅 [美股智能日期] 实际天数: {(datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days}天")

    provider = get_optimized_us_data_provider()
    return provider.get_stock_data(symbol, start_date, end_date, force_refresh)
