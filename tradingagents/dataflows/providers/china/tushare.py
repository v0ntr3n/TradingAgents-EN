"""
Unified Tushare data provider
Merges all the advantages of app layer and tradingagents layer
"""
import os
# 🔧 Avoid permission errors caused by Tushare writing user home directory tk.csv
os.environ['TS_CACHE_DIR'] = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data', 'tushare_cache')
os.environ['TS_DATA_DIR'] = os.environ['TS_CACHE_DIR']
os.environ['TEMP'] = os.environ['TS_CACHE_DIR']

from typing import Optional, Dict, Any, List, Union
from datetime import datetime, date, timedelta
import pandas as pd
import asyncio
import logging

from ..base_provider import BaseStockDataProvider
from tradingagents.config.providers_config import get_provider_config

# try to import tushare
try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
    # monkey patch upass avoid writing tk.csv
    try:
        from tushare import upass
        _orig_set_token = upass.set_token
        _orig_get_token = upass.get_token
        def _patched_set_token(token):
            os.environ['TUSHARE_TOKEN'] = token
        def _patched_get_token():
            return os.environ.get('TUSHARE_TOKEN', '')
        upass.set_token = _patched_set_token
        upass.get_token = _patched_get_token
    except Exception:
        pass
except ImportError:
    TUSHARE_AVAILABLE = False
    ts = None

logger = logging.getLogger(__name__)


class TushareProvider(BaseStockDataProvider):
    """
    Unified Tushare data provider
    Merges all the advantages of app layer and tradingagents layer
    """
    
    def __init__(self):
        super().__init__("Tushare")
        self.api = None
        self.config = get_provider_config("tushare")
        self.token_source = None  # Record Token source: 'database' or 'env'
        self._event_loop_closed = False  # 🔥 Marks whether the event loop has been closed

        if not TUSHARE_AVAILABLE:
            self.logger.error("❌ Tushare The library is not installed, please run: pip install tushare")

    def is_event_loop_closed(self) -> bool:
        """
        Check if the event loop has been closed

        Returns:
            True False if the event loop is closed otherwise
        """
        return self._event_loop_closed

    def _get_token_from_database(self) -> Optional[str]:
        """
        Read from database Tushare Token

        Priority: Database Configuration > environment variables
        In this way, after users modify the configuration in the web background, it can take effect immediately.
        """
        try:
            self.logger.info("🔍 [DB Query] Start reading from database Token...")
            from app.core.database import get_mongo_db_sync
            db = get_mongo_db_sync()
            config_collection = db.system_configs

            # Get the latest activation configuration
            self.logger.info("🔍 [DB Query] Query is_active=True configuration...")
            config_data = config_collection.find_one(
                {"is_active": True},
                sort=[("version", -1)]
            )

            if config_data:
                self.logger.info(f"✅ [DB Query] Find activation configuration, version: {config_data.get('version')}")
                if config_data.get('data_source_configs'):
                    self.logger.info(f"✅ [DB查询] 配置中有 {len(config_data['data_source_configs'])} 个数据源")
                    for ds_config in config_data['data_source_configs']:
                        ds_type = ds_config.get('type')
                        self.logger.info(f"🔍 [DB Query] Check data source: {ds_type}")
                        if ds_type == 'tushare':
                            api_key = ds_config.get('api_key')
                            self.logger.info(f"✅ [DB Query] Find Tushare configuration, api_key length: {len(api_key) if api_key else 0}")
                            if api_key and not api_key.startswith("your_"):
                                self.logger.info(f"✅ [DB Query] Token valid (length: {len(api_key)})")
                                return api_key
                            else:
                                self.logger.warning(f"⚠️ [DB Query] Token Invalid or a placeholder")
                else:
                    self.logger.warning("⚠️ [DB Query] Not in configuration data_source_configs")
            else:
                self.logger.warning("⚠️ [DB Query] Activated configuration not found")

            self.logger.info("⚠️ [DB Query] No valid one found in database Tushare Token")
        except Exception as e:
            self.logger.error(f"❌ [DB Query] Failed to read Token from database: {e}")
            import traceback
            self.logger.error(f"❌ [DB Query] stack trace:\n{traceback.format_exc()}")

        return None

    def _ensure_api_client(self, validate: bool = False) -> bool:
        """Make sure Tushare API Client is initialized. Tushare is an HTTP API and does not maintain long connections.

        🔥 Each call will read the latest Token from the database (Priority: Database > environment variables);
        If it is inconsistent with the Token used by the current API Client, it will be automatically reinitialized.
        It is guaranteed that users modify the Token in the web background to take effect immediately without restarting the backend.
        """
        if not TUSHARE_AVAILABLE:
            self.logger.error("❌ Tushare Library is not available")
            self.api = None
            self.connected = False
            return False

        try:
            # 🔥 Re-read the Token every time it is called to avoid caching old Token
            db_token = self._get_token_from_database()
            env_token = self.config.get('token') or os.getenv("TUSHARE_TOKEN", "")
            token_candidates = []
            if db_token:
                token_candidates.append(("database", db_token.strip()))
            if env_token:
                token_candidates.append(("env", env_token.strip()))

            if not token_candidates:
                self.logger.error("❌ Tushare token Not configured, please configure it in the web backend or .env file TUSHARE_TOKEN")
                self.api = None
                self.connected = False
                return False

            # The Token that should be used currently (database first)
            effective_token = token_candidates[0][1]

            # 🔥 Token Unchanged and API Client is ready: reuse directly to avoid unnecessary rebuilding
            if (
                self.api is not None
                and not validate
                and getattr(self, "_current_token", None) == effective_token
            ):
                self.connected = True
                return True

            # 🔥 Token Changed: Deprecated old API Client, reinitialized
            if self.api is not None:
                self.logger.info("🔄 Tushare Token Changed, reinitialized API Client")

            for source, token in token_candidates:
                try:
                    self.logger.info(f"🔄 initialization Tushare API Client (Token Source: {source})")
                    # Directly pass the token to pro_api without calling set_token to avoid writing the tk.csv file
                    # ts.set_token(token) The token will be cached in ~/tk.csv, In restricted environments such as sandboxes, Permission denied
                    api = ts.pro_api(token)

                    if validate:
                        test_data = api.stock_basic(list_status='L', limit=1)
                        if test_data is None or test_data.empty:
                            self.logger.warning(f"⚠️ Tushare Token test failed (Token Source: {source})")
                            continue

                    self.api = api
                    self._current_token = token
                    self.connected = True
                    self.token_source = source
                    self.logger.info(f"✅ Tushare API Client Ready (Token Source: {source})")
                    return True
                except Exception as e:
                    self.logger.warning(f"⚠️ Failed to initialize Tushare API Client (Token Source: {source}): {e}")
                    continue

            self.api = None
            self.connected = False
            return False

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Tushare API Client: {e}")
            self.api = None
            self.connected = False
            return False

    def connect_sync(self) -> bool:
        """Synchronously initialize Tushare API Client (compatible with old interface)."""
        return self._ensure_api_client(validate=True)

    async def connect(self) -> bool:
        """Asynchronous initialization of Tushare API Client (compatible with old interface)."""
        return await asyncio.to_thread(self.connect_sync)
    
    def is_available(self) -> bool:
        """Check whether Tushare API Client is available."""
        return self._ensure_api_client(validate=False)
    
    # ==================== Basic data interface ====================
    
    def get_stock_list_sync(self, market: str = None) -> Optional[pd.DataFrame]:
        """Get the stock list (synchronized version), including Shanghai and Shenzhen+Beijing Exchange"""
        if not self.is_available():
            return None

        try:
            df = self.api.stock_basic(
                list_status='L',
                exchange='SSE,SZSE,BSE',  # Shanghai and Shenzhen + North Exchange (if not uploaded, North Exchange may not be included by default)
                fields='ts_code,symbol,name,area,industry,market,exchange,list_date,is_hs'
            )
            if df is not None and not df.empty:
                self.logger.info(f"✅ 成功获取 {len(df)} 条股票数据")
                return df
            else:
                self.logger.warning("⚠️ Tushare API Return empty data")
                return None
        except Exception as e:
            self.logger.error(f"❌ 获取股票列表失败: {e}")
            return None

    async def get_stock_list(self, market: str = None) -> Optional[List[Dict[str, Any]]]:
        """获取股票列表（异步版本）"""
        if not self.is_available():
            return None

        try:
            # Build query parameters (default includes Shanghai and Shenzhen+Beijing Exchange)
            params = {
                'list_status': 'L',  # Get only listed stocks
                'exchange': 'SSE,SZSE,BSE',  # Shanghai and Shenzhen + Beijing Exchange
                'fields': 'ts_code,symbol,name,area,industry,market,exchange,list_date,is_hs'
            }
            
            if market:
                # Filter by market
                if market == "CN":
                    params['exchange'] = 'SSE,SZSE,BSE'  # Shanghai and Shenzhen + Beijing Exchange
                elif market == "HK":
                    return None  # Tushare Hong Kong stocks need to be handled separately
                elif market == "US":
                    return None  # Tushare Does not support US stocks
            
            # Get data
            df = await asyncio.to_thread(self.api.stock_basic, **params)
            
            if df is None or df.empty:
                return None
            
            # Convert to standard format
            stock_list = []
            for _, row in df.iterrows():
                stock_info = self.standardize_basic_info(row.to_dict())
                stock_list.append(stock_info)
            
            self.logger.info(f"✅ 获取股票列表: {len(stock_list)}只")
            return stock_list
            
        except Exception as e:
            self.logger.error(f"❌ 获取股票列表失败: {e}")
            return None
    
    async def get_stock_basic_info(self, symbol: str = None) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """获取股票基础信息"""
        if not self.is_available():
            return None
        
        try:
            if symbol:
                # Get individual stock information
                ts_code = self._normalize_ts_code(symbol)
                df = await asyncio.to_thread(
                    self.api.stock_basic,
                    ts_code=ts_code,
                    fields='ts_code,symbol,name,area,industry,market,exchange,list_date,is_hs,act_name,act_ent_type'
                )
                
                if df is None or df.empty:
                    return None
                
                return self.standardize_basic_info(df.iloc[0].to_dict())
            else:
                # Get all stock information
                return await self.get_stock_list()
                
        except Exception as e:
            self.logger.error(f"❌ Failed to obtain basic stock information symbol={symbol}: {e}")
            return None
    
    async def get_stock_quotes(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time quotes for a single stock

        🔥 Strategy: Use the daily interface to obtain the latest day s data (do not use the rt_k batch interface)
        - rt_k The interface is a batch interface, and calling a single stock wastes quota.
        - daily The interface can obtain the latest daily data of a single stock, including more indicators

        Note: This method is suitable for acquiring a small amount of stocks, but is recommended for large amounts of stocks. get_realtime_quotes_batch()
        """
        if not self.is_available():
            return None

        try:
            ts_code = self._normalize_ts_code(symbol)

            # 🔥 Use the daily interface to get the latest day's data (more quota savings)
            from datetime import datetime, timedelta

            # Get data for the last 3 days (taking into account weekends and holidays)
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=3)).strftime('%Y%m%d')

            df = await asyncio.to_thread(
                self.api.daily,
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )

            if df is not None and not df.empty:
                # Get the latest day's data
                row = df.iloc[0].to_dict()

                # Standardized fields
                quote_data = {
                    'ts_code': row.get('ts_code'),
                    'symbol': symbol,
                    'trade_date': row.get('trade_date'),
                    'open': row.get('open'),
                    'high': row.get('high'),
                    'low': row.get('low'),
                    'close': row.get('close'),  # closing price
                    'pre_close': row.get('pre_close'),
                    'change': row.get('change'),  # Changes
                    'pct_chg': row.get('pct_chg'),  # Increase or decrease
                    'volume': row.get('vol'),  # Trading volume (lots)
                    'amount': row.get('amount'),  # Turnover (thousand yuan)
                }

                return self.standardize_quotes(quote_data)

            return None

        except Exception as e:
            # Check whether it is a current limiting error
            if self._is_rate_limit_error(str(e)):
                self.logger.error(f"❌ Failed to obtain real-time quotes (current limit) symbol={symbol}: {e}")
                raise  # Throw a current limiting error and let the upper layer handle it

            self.logger.error(f"❌ Failed to obtain real-time quotes symbol={symbol}: {e}")
            return None

    async def get_realtime_quotes_batch(self) -> Optional[Dict[str, Dict[str, Any]]]:
        """
        Obtain real-time market information in batches
        Use the wildcard function of the rt_k interface to obtain all A-share real-time quotes at once

        Returns:
            Dict[str, Dict]: {symbol: quote_data}
            For example: {'000001': {'close': 10.5, 'pct_chg': 1.2, ...}, ...}
        """
        if not self.is_available():
            return None

        try:
            # Use wildcards to get all market quotes at once
            # 3*.SZ: GEM  6*.SH: Shanghai Stock Exchange  0*.SZ: Shenzhen Stock Exchange Main Board  4*.BJ,8*.BJ,9*.BJ: Beijing Exchange
            df = await asyncio.to_thread(
                self.api.rt_k,
                ts_code='3*.SZ,6*.SH,0*.SZ,4*.BJ,8*.BJ,9*.BJ'
            )

            if df is None or df.empty:
                self.logger.warning("⚠️ rt_k The interface returns empty data")
                return None

            self.logger.info(f"✅ 获取到 {len(df)} 只股票的实时行情")

            # 🔥 Get the current date (UTC+8) 
            from datetime import datetime, timezone, timedelta
            cn_tz = timezone(timedelta(hours=8))
            now_cn = datetime.now(cn_tz)
            trade_date = now_cn.strftime("%Y%m%d")  # Format: 20251114 (consistent with Tushare format)

            # Convert to dictionary format
            result = {}
            for _, row in df.iterrows():
                ts_code = row.get('ts_code')
                if not ts_code or '.' not in ts_code:
                    continue

                # Extract 6-digit code
                symbol = ts_code.split('.')[0]

                # Build market data
                quote_data = {
                    'ts_code': ts_code,
                    'symbol': symbol,
                    'name': row.get('name'),
                    'open': row.get('open'),
                    'high': row.get('high'),
                    'low': row.get('low'),
                    'close': row.get('close'),  # current price
                    'pre_close': row.get('pre_close'),
                    'volume': row.get('vol'),  # Trading volume (shares)
                    'amount': row.get('amount'),  # Turnover (yuan)
                    'num': row.get('num'),  # Number of transactions
                    'trade_date': trade_date,  # 🔥 Add transaction date field
                }

                # Calculate the increase or decrease
                if quote_data.get('close') and quote_data.get('pre_close'):
                    try:
                        close = float(quote_data['close'])
                        pre_close = float(quote_data['pre_close'])
                        if pre_close > 0:
                            pct_chg = ((close - pre_close) / pre_close) * 100
                            quote_data['pct_chg'] = round(pct_chg, 2)
                            quote_data['change'] = round(close - pre_close, 2)
                    except (ValueError, TypeError):
                        pass

                result[symbol] = quote_data

            return result

        except Exception as e:
            # Check whether it is a current limiting error
            if self._is_rate_limit_error(str(e)):
                self.logger.error(f"❌ Failed to obtain real-time market data in batches (current limit): {e}")
                raise  # Throw a current limiting error and let the upper layer handle it

            self.logger.error(f"❌ Failed to obtain real-time quotes in batches: {e}")
            return None

    def _is_rate_limit_error(self, error_msg: str) -> bool:
        """Detect whether it is an API current limiting error"""
        rate_limit_keywords = [
            "每分钟最多访问",
            "每分钟最多",
            "rate limit",
            "too many requests",
            "访问频率",
            "请求过于频繁"
        ]
        error_msg_lower = error_msg.lower()
        return any(keyword in error_msg_lower for keyword in rate_limit_keywords)
    
    async def get_historical_data(
        self,
        symbol: str,
        start_date: Union[str, date],
        end_date: Union[str, date] = None,
        period: str = "daily"
    ) -> Optional[pd.DataFrame]:
        """
        Get historical data

        Args:
            symbol: Stock code
            start_date: start date
            end_date: end date
            period: data period (daily/weekly/monthly)
        """
        if not self.is_available():
            availability_issues = []
            if not TUSHARE_AVAILABLE:
                availability_issues.append("Tushare库未安装")
            if self.api is None:
                availability_issues.append("Tushare API Client not initialized")
            
            self.logger.warning(
                f"⚠️ [Tushare API调用] 无法调用 get_historical_data，Tushare API Client 不可用\n"
                f"   Stock code: {symbol}\n"
                f"   start date: {start_date}\n"
                f"   end date: {end_date}\n"
                f"   cycle: {period}\n"
                f"   🔍 Unavailable reason: {', '.join(availability_issues) if availability_issues else 'unknown'}"
            )
            return None

        try:
            ts_code = self._normalize_ts_code(symbol)

            # Format date
            start_str = self._format_date(start_date)
            end_str = self._format_date(end_date) if end_date else datetime.now().strftime('%Y%m%d')

            # 🔧 Use the pro_bar interface to obtain the previous weight data (consistent with Flush)
            # Note: Tushare's daily/weekly/monthly interface does not support restoration of rights
            # Must use ts.pro_bar() function and specify adj='qfq' parameters
            # ⚠️ ETF/Funds (starting with 50/51/52/56/58/15/16) are not supported by pro_bar and need to use the fund_daily interface

            # period mapping
            freq_map = {
                "daily": "D",
                "weekly": "W",
                "monthly": "M"
            }
            freq = freq_map.get(period, "D")

            is_etf = self._is_etf(ts_code)

            # ⏱️ Log actual API call times (using high-precision timing)
            import time
            api_call_start = time.perf_counter()  # Use perf_counter for higher precision
            
            try:
                # 🔍 Verify that the API object is valid
                if self.api is None:
                    self.logger.error("❌ [Tushare API call] API The object is None and the Tushare interface cannot be called.")
                    return None

                # actual call Tushare API
                try:
                    if is_etf:
                        # ETF/The fund uses the fund_daily interface (pro_bar does not support ETF)
                        self.logger.info(
                            f"📊 [Tushare API call] To detect the ETF target, use the fund_daily interface: {ts_code}"
                        )
                        df = await asyncio.to_thread(
                            self.api.fund_daily,
                            ts_code=ts_code,
                            start_date=start_str,
                            end_date=end_str,
                        )
                    else:
                        # Stocks use the pro_bar interface (supports restoration of rights)
                        df = await asyncio.to_thread(
                            ts.pro_bar,
                            ts_code=ts_code,
                            api=self.api,  # Pass in api object
                            start_date=start_str,
                            end_date=end_str,
                            freq=freq,
                            adj='qfq'  # Previous reinstatement (consistent with Flush)
                        )
                except RuntimeError as runtime_error:
                    # 🔥 Capture "cannot schedule new futures after shutdown" Error
                    if "shutdown" in str(runtime_error).lower():
                        self.logger.warning(f"⚠️ [Tushare API call] The event loop has been closed and stopped getting data: {symbol}")
                        self._event_loop_closed = True  # 🔥 set flag
                        return None
                    raise  # Other RuntimeErrors continue to be thrown
                api_call_duration = time.perf_counter() - api_call_start
                
                # Determine whether the network request is actually executed based on the time taken
                if api_call_duration < 0.01:  # Less than 10 milliseconds, probably a fast failure
                    self.logger.warning(
                        f"⚠️ [Tushare API调用] ts.pro_bar() 执行完成（疑似快速失败）\n"
                        f"   Time consuming: {api_call_duration:.6f}seconds (very short, network request may not be performed)\n"
                        f"   Return type: {type(df).__name__ if df is not None else 'None'}\n"
                        f"   Return data: {'empty DataFrame' if (df is not None and df.empty) else ('None' if df is None else f'{len(df)}OK')}\n"
                        f"   💡 Possible reasons: Tushare Internal parameter validation failure or fail-fast logic"
                    )
                else:
                    self.logger.info(
                        f"✅ [Tushare API调用] ts.pro_bar() 执行完成\n"
                        f"   Time consuming: {api_call_duration:.6f}seconds\n"
                        f"   Return type: {type(df).__name__ if df is not None else 'None'}\n"
                        f"   Return data: {'empty DataFrame' if (df is not None and df.empty) else ('None' if df is None else f'{len(df)}OK')}"
                    )
            except Exception as api_exception:
                api_call_duration = time.perf_counter() - api_call_start
                self.logger.error(
                    f"❌ [Tushare API调用] ts.pro_bar() 抛出异常\n"
                    f"   Time consuming: {api_call_duration:.6f}seconds\n"
                    f"   Exception type: {type(api_exception).__name__}\n"
                    f"   Exception information: {str(api_exception)}\n"
                    f"   Call parameters: ts_code={ts_code}, start_date={start_str}, end_date={end_str}, freq={freq}, adj=qfq"
                )
                raise  # Rethrow the exception and let the upper layer handle it

            if df is None or df.empty:
                self.logger.warning(
                    f"⚠️ Tushare API Return empty data: symbol={symbol}, ts_code={ts_code}, "
                    f"period={period}, start={start_str}, end={end_str}"
                )
                self.logger.warning(
                    f"💡 Possible reasons: "
                    f"1) There was no trading data for this stock during this period "
                    f"2) Incorrect date range "
                    f"3) Stock code format error "
                    f"4) Tushare API Limit or insufficient points"
                )
                return None

            # Data normalization
            df = self._standardize_historical_data(df)

            self.logger.info(f"✅ 获取{period}历史数据: {symbol} {len(df)}条记录 (前复权 qfq)")
            return df
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.logger.error(
                f"❌ 获取历史数据失败 symbol={symbol}, period={period}\n"
                f"   parameters: ts_code={ts_code if 'ts_code' in locals() else 'N/A'}, "
                f"start={start_str if 'start_str' in locals() else 'N/A'}, "
                f"end={end_str if 'end_str' in locals() else 'N/A'}\n"
                f"   Error type: {type(e).__name__}\n"
                f"   error message: {str(e)}\n"
                f"   stack trace:\n{error_details}"
            )
            return None
    
    # ==================== Extended interface ====================
    
    async def get_daily_basic(self, trade_date: str) -> Optional[pd.DataFrame]:
        """获取每日基础财务数据"""
        if not self.is_available():
            return None
        
        try:
            date_str = trade_date.replace('-', '')
            df = await asyncio.to_thread(
                self.api.daily_basic,
                trade_date=date_str,
                fields='ts_code,total_mv,circ_mv,pe,pb,turnover_rate,volume_ratio,pe_ttm,pb_mrq'
            )
            
            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取每日基础数据: {trade_date} {len(df)}条记录")
                return df
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Failed to obtain daily basic data trade_date={trade_date}: {e}")
            return None

    async def get_valuation_history(
        self,
        code: str,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """Get the stock historical valuation series (PE_TTM, PB_MRQ, PS_TTM, PCF_TTM).

        Use Tushare daily_basic s date range query to obtain the full amount of data in one call.
        The return format is consistent with Baostock get_valuation_history.
        """
        if not self.is_available():
            return {"source": "tushare", "data": []}

        try:
            ts_code = self._normalize_ts_code(code)
            start_str = start_date.replace('-', '')
            end_str = end_date.replace('-', '')
            df = await asyncio.to_thread(
                self.api.daily_basic,
                ts_code=ts_code,
                start_date=start_str,
                end_date=end_str,
                fields='ts_code,trade_date,close,pe_ttm,pb,ps_ttm,pcf_ncf_ttm',
            )
            if df is None or df.empty:
                self.logger.warning(f"⚠️ Tushare Valuation history is empty: {code} {start_date}~{end_date}")
                return {"source": "tushare", "data": []}

            records: List[Dict[str, Any]] = []
            for _, row in df.iterrows():
                records.append({
                    "date": str(row.get("trade_date", "")),
                    "close": float(row["close"]) if pd.notna(row.get("close")) else None,
                    "pe_ttm": float(row["pe_ttm"]) if pd.notna(row.get("pe_ttm")) else None,
                    "pb_mrq": float(row["pb"]) if pd.notna(row.get("pb")) else None,
                    "ps_ttm": float(row["ps_ttm"]) if pd.notna(row.get("ps_ttm")) else None,
                    "pcf_ttm": float(row["pcf_ncf_ttm"]) if pd.notna(row.get("pcf_ncf_ttm")) else None,
                })
            self.logger.info(f"✅ Tushare 估值历史: {code} {start_date}~{end_date} → {len(records)}条")
            return {"source": "tushare", "data": records}
        except Exception as e:
            self.logger.error(f"❌ Tushare Valuation history failure {code}: {e}")
            return {"source": "tushare", "data": []}
    
    async def find_latest_trade_date(self) -> Optional[str]:
        """查找最新交易日期"""
        if not self.is_available():
            return None
        
        try:
            today = datetime.now()
            for delta in range(0, 10):  # Look back up to 10 days
                check_date = (today - timedelta(days=delta)).strftime('%Y%m%d')
                
                try:
                    df = await asyncio.to_thread(
                        self.api.daily_basic,
                        trade_date=check_date,
                        fields='ts_code',
                        limit=1
                    )
                    
                    if df is not None and not df.empty:
                        formatted_date = f"{check_date[:4]}-{check_date[4:6]}-{check_date[6:8]}"
                        self.logger.info(f"✅ 找到最新交易日期: {formatted_date}")
                        return formatted_date
                        
                except Exception:
                    continue
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Failed to find latest transaction date: {e}")
            return None
    
    async def get_financial_data(self, symbol: str, report_type: str = "quarterly",
                                period: str = None, limit: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Get financial data

        Args:
            symbol: Stock code
            report_type: report type (quarterly/annual)
            period: designated reporting period (YYYYMMDD Format), If empty, get the latest data
            limit: Get the number of records, None means pulling all reporting periods that can be obtained for the stock

        Returns:
            Financial data dictionary including income statement, balance sheet, cash flow statement and financial indicators
        """
        if not self.is_available():
            return None

        try:
            ts_code = self._normalize_ts_code(symbol)
            self.logger.debug(f"📊 获取Tushare财务数据: {ts_code}, 类型: {report_type}")

            # Build query parameters
            query_params = {
                'ts_code': ts_code,
            }

            if limit is not None:
                query_params['limit'] = limit

            # If a reporting period is specified, add the period parameter
            if period:
                query_params['period'] = period

            financial_data = {}

            # 1. Get income statement data (income statement)
            try:
                income_df = await asyncio.to_thread(
                    self.api.income,
                    **query_params
                )
                if income_df is not None and not income_df.empty:
                    financial_data['income_statement'] = income_df.to_dict('records')
                    self.logger.debug(f"✅ {ts_code} 利润表数据获取成功: {len(income_df)} 条记录")
                else:
                    self.logger.debug(f"⚠️ {ts_code} 利润表数据为空")
            except Exception as e:
                self.logger.warning(f"❌ 获取{ts_code}利润表数据失败: {e}")

            # 2. Get balance sheet data (balance sheet)
            try:
                balance_df = await asyncio.to_thread(
                    self.api.balancesheet,
                    **query_params
                )
                if balance_df is not None and not balance_df.empty:
                    financial_data['balance_sheet'] = balance_df.to_dict('records')
                    self.logger.debug(f"✅ {ts_code} 资产负债表数据获取成功: {len(balance_df)} 条记录")
                else:
                    self.logger.debug(f"⚠️ {ts_code} 资产负债表数据为空")
            except Exception as e:
                self.logger.warning(f"❌ 获取{ts_code}资产负债表数据失败: {e}")

            # 3. Get cash flow statement data (cash flow statement)
            try:
                cashflow_df = await asyncio.to_thread(
                    self.api.cashflow,
                    **query_params
                )
                if cashflow_df is not None and not cashflow_df.empty:
                    financial_data['cashflow_statement'] = cashflow_df.to_dict('records')
                    self.logger.debug(f"✅ {ts_code} 现金流量表数据获取成功: {len(cashflow_df)} 条记录")
                else:
                    self.logger.debug(f"⚠️ {ts_code} 现金流量表数据为空")
            except Exception as e:
                self.logger.warning(f"❌ 获取{ts_code}现金流量表数据失败: {e}")

            # 4. Get financial indicator data (financial indicators)
            try:
                indicator_df = await asyncio.to_thread(
                    self.api.fina_indicator,
                    **query_params
                )
                if indicator_df is not None and not indicator_df.empty:
                    financial_data['financial_indicators'] = indicator_df.to_dict('records')
                    self.logger.debug(f"✅ {ts_code} 财务指标数据获取成功: {len(indicator_df)} 条记录")
                else:
                    self.logger.debug(f"⚠️ {ts_code} 财务指标数据为空")
            except Exception as e:
                self.logger.warning(f"❌ 获取{ts_code}财务指标数据失败: {e}")

            # 5. Obtain main business composition data (Optional)
            try:
                mainbz_df = await asyncio.to_thread(
                    self.api.fina_mainbz,
                    **query_params
                )
                if mainbz_df is not None and not mainbz_df.empty:
                    financial_data['main_business'] = mainbz_df.to_dict('records')
                    self.logger.debug(f"✅ {ts_code} 主营业务构成数据获取成功: {len(mainbz_df)} 条记录")
                else:
                    self.logger.debug(f"⚠️ {ts_code} 主营业务构成数据为空")
            except Exception as e:
                self.logger.debug(f"获取{ts_code}主营业务构成数据失败: {e}")  # Main business data is not required, keep the debug level

            if financial_data:
                # Standardized financial data
                standardized_data = self._standardize_tushare_financial_data(financial_data, ts_code)
                self.logger.info(f"✅ {ts_code} Tushare财务数据获取完成: {len(financial_data)} 个数据集")
                return standardized_data
            else:
                self.logger.warning(f"⚠️ {ts_code} No Tushare financial data was obtained")
                return None

        except Exception as e:
            self.logger.error(f"❌ Failed to obtain Tushare financial data symbol={symbol}: {e}")
            return None

    async def get_dividend_data(self, symbol: str, limit: int = 10) -> Optional[List[Dict[str, Any]]]:
        """
        Get dividend and share data

        Args:
            symbol: Stock code
            limit: Get the number of records, default is 10

        Returns:
            A list of dividend stock record records, each entry contains ts_code, end_date, ann_date, div_proc,
            stk_div, stk_bo_rate, stk_co_rate, cash_div, cash_div_tax,
            record_date, ex_date, pay_date etc fields
        """
        if not self.is_available():
            return None

        try:
            ts_code = self._normalize_ts_code(symbol)
            self.logger.debug(f"💰 Get Tushare dividend and share data: {ts_code}")

            dividend_df = await asyncio.to_thread(
                self.api.dividend,
                ts_code=ts_code,
                fields='ts_code,end_date,ann_date,div_proc,stk_div,stk_bo_rate,stk_co_rate,'
                       'cash_div,cash_div_tax,record_date,ex_date,pay_date,div_listdate,'
                       'imp_ann_date,base_date,base_share'
            )

            if dividend_df is not None and not dividend_df.empty:
                # Only retained dividend records that have been implemented (exclusion plans, etc.)
                # Arranged in descending order by dividend year
                dividend_df = dividend_df.sort_values('end_date', ascending=False)
                records = dividend_df.head(limit).to_dict('records')
                self.logger.info(f"✅ {ts_code} 分红送股数据获取成功: {len(records)} 条记录")
                return records
            else:
                self.logger.debug(f"⚠️ {ts_code} 分红送股数据为空")
                return []

        except Exception as e:
            self.logger.error(f"❌ Failed to obtain Tushare dividend and share data symbol={symbol}: {e}")
            return None

    async def get_stock_news(self, symbol: str = None, limit: int = 10,
                           hours_back: int = 24, src: str = None) -> Optional[List[Dict[str, Any]]]:
        """
        Get stock news (requires Tushare news permission)

        Args:
            symbol: Stock code, get market news when None
            limit: Return quantity limit
            hours_back: Number of hours to look back, default is 24 hours
            src: News source, automatically selected by default

        Returns:
            News list
        """
        if not self.is_available():
            return None

        try:
            from datetime import datetime, timedelta

            # Calculation time range
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours_back)

            start_date = start_time.strftime('%Y-%m-%d %H:%M:%S')
            end_date = end_time.strftime('%Y-%m-%d %H:%M:%S')

            self.logger.debug(f"📰 获取Tushare新闻: symbol={symbol}, 时间范围={start_date} 到 {end_date}")

            # List of supported news sources (sorted by priority)
            news_sources = [
                'sina',        # Sina Finance
                'eastmoney',   # Oriental Fortune
                '10jqka',      # Flush
                'wallstreetcn', # Wall Street Insights
                'cls',         # Financial Associated Press
                'yicai',       # China Business News
                'jinrongjie',  # financial sector
                'yuncaijing',  # Cloud Finance
                'fenghuang'    # Phoenix News
            ]

            # If a data source is specified, it will be used first
            if src and src in news_sources:
                sources_to_try = [src]
            else:
                sources_to_try = news_sources[:3]  # Try the first 3 sources by default

            all_news = []

            for source in sources_to_try:
                try:
                    self.logger.debug(f"📰 尝试从 {source} 获取新闻...")

                    # Get news data
                    news_df = await asyncio.to_thread(
                        self.api.news,
                        src=source,
                        start_date=start_date,
                        end_date=end_date
                    )

                    if news_df is not None and not news_df.empty:
                        source_news = self._process_tushare_news(news_df, source, symbol, limit)
                        all_news.extend(source_news)

                        self.logger.info(f"✅ 从 {source} 获取到 {len(source_news)} 条新闻")

                        # If you've gotten enough news, stop trying other sources
                        if len(all_news) >= limit:
                            break
                    else:
                        self.logger.debug(f"⚠️ {source} 未返回新闻数据")

                except Exception as e:
                    self.logger.debug(f"从 {source} 获取新闻失败: {e}")
                    continue

                # API Current limiting
                await asyncio.sleep(0.2)

            # Deduplication and sorting
            if all_news:
                # Sort by time and remove duplicates
                unique_news = self._deduplicate_news(all_news)
                sorted_news = sorted(unique_news, key=lambda x: x.get('publish_time', datetime.min), reverse=True)

                # Limit the number of returns
                final_news = sorted_news[:limit]

                self.logger.info(f"✅ Tushare新闻获取成功: {len(final_news)} 条（去重后）")
                return final_news
            else:
                self.logger.warning("⚠️ No Tushare news data was obtained")
                return []

        except Exception as e:
            # If it is a permissions issue, give a clear prompt
            if any(keyword in str(e).lower() for keyword in ['权限', 'permission', 'unauthorized', 'access denied']):
                self.logger.warning(f"⚠️ Tushare The news interface requires separate permissions (paid function): {e}")
            elif "积分" in str(e) or "point" in str(e).lower():
                self.logger.warning(f"⚠️ Tushare Insufficient points to obtain news data: {e}")
            else:
                self.logger.error(f"❌ Failed to get Tushare news: {e}")
            return None

    def _process_tushare_news(self, news_df: pd.DataFrame, source: str,
                            symbol: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Processing Tushare news data"""
        news_list = []

        # Limit the number of processes
        df_limited = news_df.head(limit * 2)  # Get more for filtering

        for _, row in df_limited.iterrows():
            news_item = {
                "title": str(row.get('title', '') or row.get('content', '')[:50] + '...'),
                "content": str(row.get('content', '')),
                "summary": self._generate_summary(row.get('content', '')),
                "url": "",  # Tushare News interface is not provided URL
                "source": self._get_source_name(source),
                "author": "",
                "publish_time": self._parse_tushare_news_time(row.get('datetime', '')),
                "category": self._classify_tushare_news(row.get('channels', ''), row.get('content', '')),
                "sentiment": self._analyze_news_sentiment(row.get('content', ''), row.get('title', '')),
                "importance": self._assess_news_importance(row.get('content', ''), row.get('title', '')),
                "keywords": self._extract_keywords(row.get('content', ''), row.get('title', '')),
                "data_source": "tushare",
                "original_source": source
            }

            # If a stock code is specified, filter related news
            if symbol:
                if self._is_news_relevant_to_symbol(news_item, symbol):
                    news_list.append(news_item)
            else:
                news_list.append(news_item)

        return news_list

    def _get_source_name(self, source_code: str) -> str:
        """获取新闻源中文名称"""
        source_names = {
            'sina': '新浪财经',
            'eastmoney': '东方财富',
            '10jqka': '同花顺',
            'wallstreetcn': '华尔街见闻',
            'cls': '财联社',
            'yicai': '第一财经',
            'jinrongjie': '金融界',
            'yuncaijing': '云财经',
            'fenghuang': '凤凰新闻'
        }
        return source_names.get(source_code, source_code)

    def _generate_summary(self, content: str) -> str:
        """生成新闻摘要"""
        if not content:
            return ""

        content_str = str(content)
        if len(content_str) <= 200:
            return content_str

        # Simple summary generation: take the first 200 characters
        return content_str[:200] + "..."

    def _is_news_relevant_to_symbol(self, news_item: Dict[str, Any], symbol: str) -> bool:
        """判断新闻是否与股票相关"""
        content = news_item.get("content", "").lower()
        title = news_item.get("title", "").lower()

        # Standardized stock code
        symbol_clean = symbol.replace('.SH', '').replace('.SZ', '').zfill(6)

        # keyword matching
        return any([
            symbol_clean in content,
            symbol_clean in title,
            symbol in content,
            symbol in title
        ])

    def _deduplicate_news(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """新闻去重"""
        seen_titles = set()
        unique_news = []

        for news in news_list:
            title = news.get('title', '')
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_news.append(news)

        return unique_news

    def _analyze_news_sentiment(self, content: str, title: str) -> str:
        """分析新闻情绪"""
        text = f"{title} {content}".lower()

        positive_keywords = ['利好', '上涨', '增长', '盈利', '突破', '创新高', '买入', '推荐']
        negative_keywords = ['利空', '下跌', '亏损', '风险', '暴跌', '卖出', '警告', '下调']

        positive_count = sum(1 for keyword in positive_keywords if keyword in text)
        negative_count = sum(1 for keyword in negative_keywords if keyword in text)

        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        else:
            return 'neutral'

    def _assess_news_importance(self, content: str, title: str) -> str:
        """评估新闻重要性"""
        text = f"{title} {content}".lower()

        high_importance_keywords = ['业绩', '财报', '重大', '公告', '监管', '政策', '并购', '重组']
        medium_importance_keywords = ['分析', '预测', '观点', '建议', '行业', '市场']

        if any(keyword in text for keyword in high_importance_keywords):
            return 'high'
        elif any(keyword in text for keyword in medium_importance_keywords):
            return 'medium'
        else:
            return 'low'

    def _extract_keywords(self, content: str, title: str) -> List[str]:
        """提取关键词"""
        text = f"{title} {content}"

        # Simple keyword extraction
        keywords = []
        common_keywords = ['股票', '公司', '市场', '投资', '业绩', '财报', '政策', '行业', '分析', '预测']

        for keyword in common_keywords:
            if keyword in text:
                keywords.append(keyword)

        return keywords[:5]  # Return up to 5 keywords

    def _parse_tushare_news_time(self, time_str: str) -> Optional[datetime]:
        """Parsing Tushare news time"""
        if not time_str:
            return datetime.utcnow()

        try:
            # Tushare time format: 2018-11-21 09:30:00
            return datetime.strptime(str(time_str), '%Y-%m-%d %H:%M:%S')
        except Exception as e:
            self.logger.debug(f"Failed to parse Tushare news time: {e}")
            return datetime.utcnow()

    def _classify_tushare_news(self, channels: str, content: str) -> str:
        """分类Tushare新闻"""
        channels = str(channels).lower()
        content = str(content).lower()

        # Classification based on channel and content keywords
        if any(keyword in channels or keyword in content for keyword in ['公告', '业绩', '财报']):
            return 'company_announcement'
        elif any(keyword in channels or keyword in content for keyword in ['政策', '监管', '央行']):
            return 'policy_news'
        elif any(keyword in channels or keyword in content for keyword in ['行业', '板块']):
            return 'industry_news'
        elif any(keyword in channels or keyword in content for keyword in ['市场', '指数', '大盘']):
            return 'market_news'
        else:
            return 'other'

    async def get_financial_data_by_period(self, symbol: str, start_period: str = None,
                                         end_period: str = None, report_type: str = "quarterly") -> Optional[List[Dict[str, Any]]]:
        """
        Get financial data by time range

        Args:
            symbol: Stock code
            start_period: Start reporting period (YYYYMMDD)
            end_period: End reporting period (YYYYMMDD)
            report_type: report type (quarterly/annual)

        Returns:
            List of financial data, arranged in reverse order by reporting period
        """
        if not self.is_available():
            return None

        try:
            ts_code = self._normalize_ts_code(symbol)
            self.logger.debug(f"📊 Get Tushare financial data by period: {ts_code}, {start_period} - {end_period}")

            # Build query parameters
            query_params = {'ts_code': ts_code}

            if start_period:
                query_params['start_date'] = start_period
            if end_period:
                query_params['end_date'] = end_period

            # Obtain income statement data as primary data source
            income_df = await asyncio.to_thread(
                self.api.income,
                **query_params
            )

            if income_df is None or income_df.empty:
                self.logger.warning(f"⚠️ {ts_code} 指定期间无财务数据")
                return None

            # Get complete financial data grouped by reporting period
            financial_data_list = []

            for _, income_row in income_df.iterrows():
                period = income_row['end_date']

                # Get complete financial data for the period
                period_data = await self.get_financial_data(
                    symbol=symbol,
                    period=period,
                    limit=1
                )

                if period_data:
                    financial_data_list.append(period_data)

                # API Current limiting
                await asyncio.sleep(0.1)

            self.logger.info(f"✅ {ts_code} 按期间获取财务数据完成: {len(financial_data_list)} 个报告期")
            return financial_data_list

        except Exception as e:
            self.logger.error(f"❌ Failed to obtain Tushare financial data by period symbol={symbol}: {e}")
            return None

    async def get_financial_indicators_only(self, symbol: str, limit: int = 4) -> Optional[Dict[str, Any]]:
        """
        Get only financial indicator data (lightweight interface)

        Args:
            symbol: Stock code
            limit: Get the number of records

        Returns:
            financial indicator data
        """
        if not self.is_available():
            return None

        try:
            ts_code = self._normalize_ts_code(symbol)

            # Get only financial metrics
            indicator_df = await asyncio.to_thread(
                self.api.fina_indicator,
                ts_code=ts_code,
                limit=limit
            )

            if indicator_df is not None and not indicator_df.empty:
                indicators = indicator_df.to_dict('records')

                return {
                    "symbol": symbol,
                    "ts_code": ts_code,
                    "financial_indicators": indicators,
                    "data_source": "tushare",
                    "updated_at": datetime.utcnow()
                }

            return None

        except Exception as e:
            self.logger.error(f"❌ Failed to obtain Tushare financial indicators symbol={symbol}: {e}")
            return None

    # ==================== Data normalization methods ====================

    def standardize_basic_info(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化股票基础信息"""
        ts_code = raw_data.get('ts_code', '')
        symbol = raw_data.get('symbol', ts_code.split('.')[0] if '.' in ts_code else ts_code)

        return {
            # Basic fields
            "code": symbol,
            "name": raw_data.get('name', ''),
            "symbol": symbol,
            "full_symbol": ts_code,

            # market information
            "market_info": self._determine_market_info_from_ts_code(ts_code),

            # business information
            "area": self._safe_str(raw_data.get('area')),
            "industry": self._safe_str(raw_data.get('industry')),
            "market": raw_data.get('market'),  # Main Board/GEM/Science and Technology Innovation Board
            "list_date": self._format_date_output(raw_data.get('list_date')),

            # Hong Kong Stock Connect Information
            "is_hs": raw_data.get('is_hs'),

            # Actual controller information
            "act_name": raw_data.get('act_name'),
            "act_ent_type": raw_data.get('act_ent_type'),

            # metadata
            "data_source": "tushare",
            "data_version": 1,
            "updated_at": datetime.utcnow()
        }

    def standardize_quotes(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化实时行情数据"""
        ts_code = raw_data.get('ts_code', '')
        symbol = ts_code.split('.')[0] if '.' in ts_code else ts_code

        return {
            # Basic fields
            "code": symbol,
            "symbol": symbol,
            "full_symbol": ts_code,
            "market": self._determine_market(ts_code),

            # price data
            "close": self._convert_to_float(raw_data.get('close')),
            "current_price": self._convert_to_float(raw_data.get('close')),
            "open": self._convert_to_float(raw_data.get('open')),
            "high": self._convert_to_float(raw_data.get('high')),
            "low": self._convert_to_float(raw_data.get('low')),
            "pre_close": self._convert_to_float(raw_data.get('pre_close')),

            # Change data
            "change": self._convert_to_float(raw_data.get('change')),
            "pct_chg": self._convert_to_float(raw_data.get('pct_chg')),

            # Transaction data
            # 🔥 Trading volume unit conversion: Tushare returns lots, which need to be converted into shares
            "volume": self._convert_to_float(raw_data.get('vol')) * 100 if raw_data.get('vol') else None,
            # 🔥 Transaction volume unit conversion: The Tushare daily interface returns thousands of yuan, which needs to be converted into yuan.
            "amount": self._convert_to_float(raw_data.get('amount')) * 1000 if raw_data.get('amount') else None,

            # financial indicators
            "total_mv": self._convert_to_float(raw_data.get('total_mv')),
            "circ_mv": self._convert_to_float(raw_data.get('circ_mv')),
            "pe": self._convert_to_float(raw_data.get('pe')),
            "pb": self._convert_to_float(raw_data.get('pb')),
            "turnover_rate": self._convert_to_float(raw_data.get('turnover_rate')),

            # time data
            "trade_date": self._format_date_output(raw_data.get('trade_date')),
            "timestamp": datetime.utcnow(),

            # metadata
            "data_source": "tushare",
            "data_version": 1,
            "updated_at": datetime.utcnow()
        }

    # ==================== Helper methods ====================

    def _normalize_ts_code(self, symbol: str) -> str:
        """Standardized to Tushare s ts_code format"""
        if '.' in symbol:
            return symbol  # Already in ts_code format

        # 6 digit code, need to add suffix
        if symbol.isdigit() and len(symbol) == 6:
            # Shanghai Stock Exchange: 60/68 (A shares), 50/51/52/58/56 (ETF/LOF, etc.), 11 (treasury bonds/convertible bonds), 90 (B shares)
            if symbol.startswith(('60', '68', '90', '50', '51', '52', '58', '56', '11')):
                return f"{symbol}.SH"  # Shanghai Stock Exchange
            # Shenzhen Stock Exchange: 00/30 (A shares), 15/16/12 (ETF/LOF/convertible bonds, etc.), 20 (B shares)
            elif symbol.startswith(('00', '30', '20', '15', '16', '12')):
                return f"{symbol}.SZ"  # Shenzhen Stock Exchange
            elif symbol.startswith(('8', '4', '92')):
                return f"{symbol}.BJ"  # Beijing Exchange
            else:
                return f"{symbol}.SZ"  # Default Shenzhen Stock Exchange

        return symbol

    @staticmethod
    def _is_etf(ts_code: str) -> bool:
        """Determine whether it is an ETF/fund type target (pro_bar does not support it, you need to go to fund_daily).

        Shanghai Stock Exchange ETF: 50/51/52/56/58 Beginning
        Shenzhen Stock Exchange ETF: 15/16 Beginning
        """
        code = ts_code.split('.')[0] if '.' in ts_code else ts_code
        if not code.isdigit() or len(code) != 6:
            return False
        return code.startswith(('50', '51', '52', '56', '58', '15', '16'))

    def _determine_market_info_from_ts_code(self, ts_code: str) -> Dict[str, Any]:
        """Determine market information based on ts_code"""
        if '.SH' in ts_code:
            return {
                "market": "CN",
                "exchange": "SSE",
                "exchange_name": "上海证券交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }
        elif '.SZ' in ts_code:
            return {
                "market": "CN",
                "exchange": "SZSE",
                "exchange_name": "深圳证券交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }
        elif '.BJ' in ts_code:
            return {
                "market": "CN",
                "exchange": "BSE",
                "exchange_name": "北京证券交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }
        else:
            return {
                "market": "CN",
                "exchange": "UNKNOWN",
                "exchange_name": "未知交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }

    def _determine_market(self, ts_code: str) -> str:
        """确定市场代码"""
        market_info = self._determine_market_info_from_ts_code(ts_code)
        return market_info.get("market", "CN")

    def _format_date(self, date_value: Union[str, date]) -> str:
        """Format date to Tushare format (YYYYMMDD)"""
        if isinstance(date_value, str):
            return date_value.replace('-', '')
        elif isinstance(date_value, date):
            return date_value.strftime('%Y%m%d')
        else:
            return str(date_value).replace('-', '')

    def _standardize_historical_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化历史数据"""
        # Rename columns
        column_mapping = {
            'trade_date': 'date',
            'vol': 'volume'
        }
        df = df.rename(columns=column_mapping)

        # Format date
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
            df.set_index('date', inplace=True)

        # Sort by date
        df = df.sort_index()

        return df

    def _standardize_tushare_financial_data(self, financial_data: Dict[str, Any], ts_code: str) -> Dict[str, Any]:
        """
        Standardize Tushare financial data

        Args:
            financial_data: Raw financial data dictionary
            ts_code: Tushare Stock code

        Returns:
            Standardized financial data
        """
        try:
            # priority use"Disclosed"latest reports to avoid future scheduled disclosure periods from covering currently available financial reports.
            income_statements = financial_data.get('income_statement', []) or []
            balance_statements = financial_data.get('balance_sheet', []) or []
            cashflow_statements = financial_data.get('cashflow_statement', []) or []
            indicator_statements = financial_data.get('financial_indicators', []) or []

            latest_income = self._pick_latest_disclosed_record(income_statements)
            if not latest_income and income_statements:
                latest_income = income_statements[0]

            latest_period = str((latest_income or {}).get('end_date') or '')

            latest_balance = self._pick_record_by_period(balance_statements, latest_period)
            if not latest_balance:
                latest_balance = self._pick_latest_disclosed_record(balance_statements)
            if not latest_balance and balance_statements:
                latest_balance = balance_statements[0]

            latest_cashflow = self._pick_record_by_period(cashflow_statements, latest_period)
            if not latest_cashflow:
                latest_cashflow = self._pick_latest_disclosed_record(cashflow_statements)
            if not latest_cashflow and cashflow_statements:
                latest_cashflow = cashflow_statements[0]

            latest_indicator = self._pick_record_by_period(indicator_statements, latest_period)
            if not latest_indicator:
                latest_indicator = self._pick_latest_disclosed_record(indicator_statements)
            if not latest_indicator and indicator_statements:
                latest_indicator = indicator_statements[0]

            latest_income = latest_income or {}
            latest_balance = latest_balance or {}
            latest_cashflow = latest_cashflow or {}
            latest_indicator = latest_indicator or {}

            # Extract basic information
            symbol = ts_code.split('.')[0] if '.' in ts_code else ts_code
            report_period = latest_income.get('end_date') or latest_balance.get('end_date') or latest_cashflow.get('end_date')
            ann_date = latest_income.get('ann_date') or latest_balance.get('ann_date') or latest_cashflow.get('ann_date')

            # Calculate TTM data
            revenue_ttm = self._calculate_ttm_from_tushare(income_statements, 'revenue')
            net_profit_ttm = self._calculate_ttm_from_tushare(income_statements, 'n_income_attr_p')

            standardized_data = {
                # Basic information
                "symbol": symbol,
                "ts_code": ts_code,
                "report_period": report_period,
                "ann_date": ann_date,
                "report_type": self._determine_report_type(report_period),

                # Income statement core indicators
                "revenue": self._safe_float(latest_income.get('revenue')),  # Operating income (based on the original reporting period, A-share quarterly reports are usually accumulated at the beginning of the year)
                "revenue_ttm": revenue_ttm,  # Operating Revenue (TTM)
                "oper_rev": self._safe_float(latest_income.get('oper_rev')),  # operating income
                "net_income": self._safe_float(latest_income.get('n_income')),  # Net profit (based on the original reporting period, A-share quarterly reports are usually accumulated at the beginning of the year)
                "net_profit": self._safe_float(latest_income.get('n_income_attr_p')),  # Net profit attributable to the parent company (original reporting period, A-share quarterly reports are usually accumulated at the beginning of the year)
                "net_profit_ttm": net_profit_ttm,  # Net profit attributable to parent company (TTM)
                "oper_profit": self._safe_float(latest_income.get('operate_profit')),  # operating profit
                "total_profit": self._safe_float(latest_income.get('total_profit')),  # total profit
                "oper_cost": self._safe_float(latest_income.get('oper_cost')),  # operating costs
                "oper_exp": self._safe_float(latest_income.get('oper_exp')),  # operating expenses
                "admin_exp": self._safe_float(latest_income.get('admin_exp')),  # overhead
                "fin_exp": self._safe_float(latest_income.get('fin_exp')),  # financial charges
                "rd_exp": self._safe_float(latest_income.get('rd_exp')),  # R&D expenses
                "credit_impa_loss": self._safe_float(latest_income.get('credit_impa_loss')),  # Credit impairment losses (including bad debt provisions accrued in the current period)
                "assets_impair_loss": self._safe_float(latest_income.get('assets_impair_loss')),  # Asset impairment losses

                # Balance sheet core indicators
                "total_assets": self._safe_float(latest_balance.get('total_assets')),  # total assets
                "total_liab": self._safe_float(latest_balance.get('total_liab')),  # total liabilities
                "total_equity": self._safe_float(latest_balance.get('total_hldr_eqy_exc_min_int')),  # Shareholders' equity
                "total_cur_assets": self._safe_float(latest_balance.get('total_cur_assets')),  # current assets
                "total_nca": self._safe_float(latest_balance.get('total_nca')),  # non-current assets
                "total_cur_liab": self._safe_float(latest_balance.get('total_cur_liab')),  # current liabilities
                "total_ncl": self._safe_float(latest_balance.get('total_ncl')),  # non-current liabilities
                "money_cap": self._safe_float(latest_balance.get('money_cap')),  # Monetary funds
                "accounts_receiv": self._safe_float(latest_balance.get('accounts_receiv')),  # Accounts receivable
                "inventories": self._safe_float(latest_balance.get('inventories')),  # Inventory
                "fix_assets": self._safe_float(latest_balance.get('fix_assets')),  # fixed assets
                "goodwill": self._safe_float(latest_balance.get('goodwill')),  # Goodwill (intangible assets formed from merger and acquisition premiums, complete data is usually available only in Q4 annual reports)

                # Core indicators of cash flow statement
                "n_cashflow_act": self._safe_float(latest_cashflow.get('n_cashflow_act')),  # cash flow from operating activities
                "n_cashflow_inv_act": self._safe_float(latest_cashflow.get('n_cashflow_inv_act')),  # cash flow from investing activities
                "n_cashflow_fin_act": self._safe_float(latest_cashflow.get('n_cashflow_fin_act')),  # cash flow from financing activities
                "c_cash_equ_end_period": self._safe_float(latest_cashflow.get('c_cash_equ_end_period')),  # Ending cash
                "c_cash_equ_beg_period": self._safe_float(latest_cashflow.get('c_cash_equ_beg_period')),  # Opening cash

                # financial indicators
                "roe": self._safe_float(latest_indicator.get('roe')),  # ROE
                "roa": self._safe_float(latest_indicator.get('roa')),  # return on total assets
                "roe_waa": self._safe_float(latest_indicator.get('roe_waa')),  # Weighted average return on equity
                "roe_dt": self._safe_float(latest_indicator.get('roe_dt')),  # ROE(Deduct extraordinary gains and losses)
                "roa2": self._safe_float(latest_indicator.get('roa2')),  # return on total assets(Deduct extraordinary gains and losses)
                "gross_margin": self._safe_float(latest_indicator.get('grossprofit_margin')),  # 🔥 Fix: Use grossprofit_margin (sales gross profit margin %) instead of gross_margin (gross profit absolute value)
                "netprofit_margin": self._safe_float(latest_indicator.get('netprofit_margin')),  # net sales profit margin
                "cogs_of_sales": self._safe_float(latest_indicator.get('cogs_of_sales')),  # COGS
                "expense_of_sales": self._safe_float(latest_indicator.get('expense_of_sales')),  # Sales period expense rate
                "profit_to_gr": self._safe_float(latest_indicator.get('profit_to_gr')),  # Net profit/total operating income
                "saleexp_to_gr": self._safe_float(latest_indicator.get('saleexp_to_gr')),  # Selling expenses/total operating income
                "adminexp_of_gr": self._safe_float(latest_indicator.get('adminexp_of_gr')),  # Administrative expenses/total operating income
                "finaexp_of_gr": self._safe_float(latest_indicator.get('finaexp_of_gr')),  # Financial expenses/total operating income
                "debt_to_assets": self._safe_float(latest_indicator.get('debt_to_assets')),  # Asset-liability ratio
                "assets_to_eqt": self._safe_float(latest_indicator.get('assets_to_eqt')),  # equity multiplier
                "dp_assets_to_eqt": self._safe_float(latest_indicator.get('dp_assets_to_eqt')),  # equity multiplier(DuPont Analysis)
                "ca_to_assets": self._safe_float(latest_indicator.get('ca_to_assets')),  # Current assets/total assets
                "nca_to_assets": self._safe_float(latest_indicator.get('nca_to_assets')),  # Non-current assets/total assets
                "current_ratio": self._safe_float(latest_indicator.get('current_ratio')),  # current ratio
                "quick_ratio": self._safe_float(latest_indicator.get('quick_ratio')),  # quick ratio
                "cash_ratio": self._safe_float(latest_indicator.get('cash_ratio')),  # cash ratio

                # Original data retained (for detailed analysis)
                "raw_data": {
                    "income_statement": financial_data.get('income_statement', []),
                    "balance_sheet": financial_data.get('balance_sheet', []),
                    "cashflow_statement": financial_data.get('cashflow_statement', []),
                    "financial_indicators": financial_data.get('financial_indicators', []),
                    "main_business": financial_data.get('main_business', [])
                },

                # metadata
                "data_source": "tushare",
                "updated_at": datetime.utcnow()
            }

            return standardized_data

        except Exception as e:
            self.logger.error(f"❌ Standardizing Tushare financial data fails: {e}")
            return {
                "symbol": ts_code.split('.')[0] if '.' in ts_code else ts_code,
                "data_source": "tushare",
                "updated_at": datetime.utcnow(),
                "error": str(e)
            }

    def _pick_record_by_period(self, statements: List[Dict[str, Any]], period: str) -> Optional[Dict[str, Any]]:
        """Match records by reporting period."""
        if not statements or not period:
            return None
        target = str(period)
        for record in statements:
            if str(record.get('end_date') or '') == target:
                return record
        return None

    def _pick_latest_disclosed_record(self, statements: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Select the most recent record for the reporting period among the disclosed records.

        Rules:
        1. Priority ann_date/f_ann_date <= Today s record
        2. Select the latest among available records in reverse order by end_date
        """
        if not statements:
            return None

        today = datetime.utcnow().strftime('%Y%m%d')
        disclosed: List[Dict[str, Any]] = []

        for record in statements:
            ann_date = str(record.get('ann_date') or record.get('f_ann_date') or '').replace('-', '')
            end_date = str(record.get('end_date') or '').replace('-', '')

            if not end_date:
                continue

            # ann_date When missing, the record will be retained by default to avoid accidental deletion of historical data.
            if not ann_date or ann_date <= today:
                disclosed.append(record)

        if not disclosed:
            return None

        disclosed.sort(key=lambda rec: str(rec.get('end_date') or '').replace('-', ''), reverse=True)
        return disclosed[0]

    def _calculate_ttm_from_tushare(self, income_statements: list, field: str) -> Optional[float]:
        """
        Calculate TTM (last 12 months) from Tushare income statement data

        Tushare Income statement data are cumulative values (cumulative from the beginning of the year to the reporting period):
        - 2025Q1 (20250331): 2025 Total from January to March of the year
        - 2025Q2 (20250630): 2025 Total from January to June of the year
        - 2025Q3 (20250930): 2025 Total from January to September of the year
        - 2025Q4 (20251231): 2025 Total from January to December of the year (annual report)

        TTM Calculation formula:
        TTM = The most recent annual report after the same period last year + (Cumulative for the current period – Cumulative for the same period last year)

        For example:2025Q2 TTM = 2024 annual report + (2025Q2 - 2024Q2)
                        = 2024 January-December + (2025 January-June 2024 - January-June 2024)
                        = 2024 July-December + 2025 January to June
                        = Last 12 months

        Args:
            income_statements: Income statement data list (in reverse order of reporting period)
            field: Field name ('revenue' or 'n_income_attr_p') 

        Returns:
            TTM value, returned if it cannot be calculated None
        """
        if not income_statements or len(income_statements) < 1:
            return None

        try:
            latest = income_statements[0]
            latest_period = latest.get('end_date')
            latest_value = self._safe_float(latest.get(field))

            if not latest_period or latest_value is None:
                return None

            # Determine the type of the latest issue
            month_day = latest_period[4:8]

            # If the latest issue is the annual report (1231), use it directly
            if month_day == '1231':
                self.logger.debug(f"✅ TTM Calculate: Using annual report data {latest_period} = {latest_value:.2f}")
                return latest_value

            # If it is a quarterly/semi-annual report, calculation is required TTM = base period + (Cumulative for the current period – Cumulative for the same period last year)

            # 1. Find the same period last year
            latest_year = latest_period[:4]
            last_year = str(int(latest_year) - 1)
            last_year_same_period = last_year + latest_period[4:]

            last_year_same = None
            for stmt in income_statements:
                if stmt.get('end_date') == last_year_same_period:
                    last_year_same = stmt
                    break

            if not last_year_same:
                # There is a lack of data for the same period last year and cannot be accurately calculated. TTM
                self.logger.warning(f"⚠️ TTM Calculation failed: Missing data for the same period last year (requires: {last_year_same_period}, latest issue: {latest_period}) ")
                return None

            last_year_value = self._safe_float(last_year_same.get(field))
            if last_year_value is None:
                self.logger.warning(f"⚠️ TTM Calculation failed: The data value for the same period last year is empty ({last_year_same_period}) ")
                return None

            # 2. Find"The most recent annual report after the same period last year"as base period
            # For example: If the latest period is 2025Q2 and the same period last year is 2024Q2, then search for the 2024 annual report (20241231)
            base_period = None
            for stmt in income_statements:
                period = stmt.get('end_date')
                # Must meet: after the same period last year and is an annual report (1231)
                if period and period > last_year_same_period and period[4:8] == '1231':
                    base_period = stmt
                    break

            if not base_period:
                # No suitable annual report found, unable to calculate
                # This situation usually occurs when: the latest period is 2025Q1, but the 2024 annual report has not been released yet
                self.logger.warning(f"⚠️ TTM Calculation failed: Missing base annual report (needs in {last_year_same_period} Subsequent annual reports, latest issue: {latest_period}) ")
                return None

            base_value = self._safe_float(base_period.get(field))
            if base_value is None:
                self.logger.warning(f"⚠️ TTM Calculation failed: The base annual report data value is empty ({base_period.get('end_date')}) ")
                return None

            # 3. Calculate TTM = Baseline Annual Report + (Cumulative for the current period – Cumulative for the same period last year)
            ttm_value = base_value + (latest_value - last_year_value)

            self.logger.debug(
                f"✅ TTM计算: {base_period.get('end_date')}({base_value:.2f}) + "
                f"({latest_period}({latest_value:.2f}) - {last_year_same_period}({last_year_value:.2f})) = {ttm_value:.2f}"
            )

            return ttm_value

        except Exception as e:
            self.logger.warning(f"❌ TTM计算异常: {e}")
            return None

    def _determine_report_type(self, report_period: str) -> str:
        """根据报告期确定报告类型"""
        if not report_period:
            return "quarterly"

        try:
            # Reporting period format: YYYYMMDD
            month_day = report_period[4:8]
            if month_day == "1231":
                return "annual"  # annual report
            else:
                return "quarterly"  # quarterly report
        except:
            return "quarterly"

    def _safe_float(self, value) -> Optional[float]:
        """Safe conversion to floating point numbers, handling various exceptions"""
        if value is None:
            return None

        try:
            # Handling string types
            if isinstance(value, str):
                value = value.strip()
                if not value or value.lower() in ['nan', 'null', 'none', '--', '']:
                    return None
                # Remove possible unit symbols
                value = value.replace(',', '').replace('万', '').replace('亿', '')

            # Handling numeric types
            if isinstance(value, (int, float)):
                # Check if it is NaN
                if isinstance(value, float) and (value != value):  # NaN Check
                    return None
                return float(value)

            # try to convert
            return float(value)

        except (ValueError, TypeError, AttributeError):
            return None

    def _calculate_gross_profit(self, revenue, oper_cost) -> Optional[float]:
        """安全计算毛利润"""
        revenue_float = self._safe_float(revenue)
        oper_cost_float = self._safe_float(oper_cost)

        if revenue_float is not None and oper_cost_float is not None:
            return revenue_float - oper_cost_float
        return None

    def _safe_str(self, value) -> Optional[str]:
        """Safe conversion to string, handling NaN values"""
        if value is None:
            return None
        if isinstance(value, float) and (value != value):  # Check NaN
            return None
        return str(value) if value else None

    # ==================== Sector/industry data interface ====================

    async def get_ths_index_list(self, index_type: str = "N") -> Optional[pd.DataFrame]:
        """
        Get the list of Flush sectors

        Args:
            index_type: Section type
                - N: Industry sector
                - S: Concept section
                - R: Geographical sector
                - I: Industry Index (requires 6,000 points)

        Returns:
            Section list DataFrame, containing ts_code, name, count, exchange, list_date, type
        """
        if not self.is_available():
            return None

        try:
            df = await asyncio.to_thread(
                self.api.ths_index,
                type=index_type
            )
            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取同花顺{index_type}型板块列表: {len(df)} 个")
                return df
            return None
        except Exception as e:
            self.logger.error(f"❌ Failed to obtain the Flush section list: {e}")
            return None

    async def get_ths_daily(self, ts_code: str, start_date: str = None,
                           end_date: str = None) -> Optional[pd.DataFrame]:
        """
        Get the daily quotes of the Flush sector

        Args:
            ts_code: Sector code (e.g. 885691.TI represents the brewing industry)
            start_date: start date YYYYMMDD
            end_date: end date YYYYMMDD

        Returns:
            Sector daily data DataFrame, including ts_code, trade_date, open, close, high, low,
            avg_price, change, pct_change, vol, turnover_rate, total_mv, float_mv
        """
        if not self.is_available():
            return None

        try:
            params = {'ts_code': ts_code}
            if start_date:
                params['start_date'] = start_date.replace('-', '')
            if end_date:
                params['end_date'] = end_date.replace('-', '')

            df = await asyncio.to_thread(
                self.api.ths_daily,
                **params
            )
            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取板块 {ts_code} 日线数据: {len(df)} 条")
                return df
            return None
        except Exception as e:
            self.logger.error(f"❌ Failed to obtain sector daily data: {e}")
            return None

    async def get_ths_member(self, ts_code: str = None,
                            con_code: str = None) -> Optional[pd.DataFrame]:
        """
        Get Flush sector constituent stocks

        Args:
            ts_code: Section code (forward query: Section→constituent stocks)
            con_code: Stock code (reverse query: individual stocks→section)

        Returns:
            DataFrame, contains ts_code (Section code), code (Stock code), name (Stock name)
        """
        if not self.is_available():
            return None

        try:
            params = {}
            if ts_code:
                params['ts_code'] = ts_code
            if con_code:
                params['con_code'] = con_code

            if not params:
                self.logger.warning("⚠️ get_ths_member Need to specify ts_code or con_code")
                return None

            df = await asyncio.to_thread(
                self.api.ths_member,
                **params
            )
            if df is not None and not df.empty:
                if ts_code:
                    self.logger.info(f"✅ 获取板块 {ts_code} 成分股: {len(df)} 只")
                else:
                    self.logger.info(f"✅ 获取股票 {con_code} 所属板块: {len(df)} 个")
                return df
            return None
        except Exception as e:
            self.logger.error(f"❌ 获取板块成分股失败: {e}")
            return None

    async def get_moneyflow_ths(self, trade_date: str = None,
                               ts_code: str = None,
                               start_date: str = None,
                               end_date: str = None) -> Optional[pd.DataFrame]:
        """
        Get a straight flush**individual stocks**Fund flow (note: this is the individual stock level, not the sector level)

        Args:
            trade_date: transaction date YYYYMMDD
            ts_code: Stock code
            start_date: start date YYYYMMDD
            end_date: end date YYYYMMDD

        Returns:
            DataFrame, Contains individual stock capital flow data
            - net_amount: Net inflow amount (10,000 yuan)
            - net_amount_rate: Net inflow ratio
            - buy_elg_amount: Extra large order purchase amount
            - buy_lg_amount: Large order purchase amount
            - buy_md_amount: Mid order buying amount
            - buy_sm_amount: Small order purchase amount
        """
        if not self.is_available():
            return None

        try:
            params = {}
            if trade_date:
                params['trade_date'] = trade_date.replace('-', '')
            if ts_code:
                params['ts_code'] = ts_code
            if start_date:
                params['start_date'] = start_date.replace('-', '')
            if end_date:
                params['end_date'] = end_date.replace('-', '')

            df = await asyncio.to_thread(
                self.api.moneyflow_ths,
                **params
            )
            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取个股资金流向数据: {len(df)} 条")
                return df
            return None
        except Exception as e:
            self.logger.error(f"❌ Failed to obtain the capital flow of individual stocks: {e}")
            return None

    async def get_moneyflow_ind_ths(self, trade_date: str = None,
                                    ts_code: str = None,
                                    start_date: str = None,
                                    end_date: str = None) -> Optional[pd.DataFrame]:
        """
        Get a straight flush**Industry sector**Fund flow

        Args:
            trade_date: Transaction date YYYYMMDD (single day query)
            ts_code: Industry sector code (such as 881166.TI)
            start_date: Start date YYYYMMDD (range query)
            end_date: End date YYYYMMDD (range query)

        Returns:
            DataFrame, Contains industry sector capital flow data
            - ts_code: Section code
            - industry: Industry name
            - lead_stock: Leading stocks
            - close: Sector index closing
            - pct_change: Increase or decrease(%)
            - net_amount: Net inflow amount (100 million yuan)
            - net_buy_amount: Purchase amount (100 million yuan)
            - net_sell_amount: Sales amount (100 million yuan)
            - company_num: Number of constituent stocks
        """
        if not self.is_available():
            return None

        try:
            params = {}
            if trade_date:
                params['trade_date'] = trade_date.replace('-', '')
            if ts_code:
                params['ts_code'] = ts_code
            if start_date:
                params['start_date'] = start_date.replace('-', '')
            if end_date:
                params['end_date'] = end_date.replace('-', '')

            df = await asyncio.to_thread(
                self.api.moneyflow_ind_ths,
                **params
            )
            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取行业板块资金流向: {len(df)} 条")
                return df
            return None
        except Exception as e:
            self.logger.error(f"❌ Failed to obtain the capital flow of the industry sector: {e}")
            return None

    async def get_moneyflow_cnt_ths(self, trade_date: str = None,
                                    ts_code: str = None,
                                    start_date: str = None,
                                    end_date: str = None) -> Optional[pd.DataFrame]:
        """
        Get a straight flush**Concept section**Fund flow

        Note: The maximum number of entries per transaction is 5,000. There are about 387 concept sections. If the date range exceeds 12 days,
        It will be automatically pulled in segments and then merged.

        Args:
            trade_date: Transaction date YYYYMMDD (single day query)
            ts_code: Concept section code (such as 886034.TI)
            start_date: Start date YYYYMMDD (range query)
            end_date: End date YYYYMMDD (range query)

        Returns:
            DataFrame, Contains data on capital flows in concept sectors
            - ts_code: Section code
            - name: concept name
            - lead_stock: Leading stocks
            - close_price: Sector index closing
            - pct_change: Increase or decrease(%)
            - net_amount: Net inflow amount (100 million yuan)
            - net_buy_amount: Purchase amount (100 million yuan)
            - net_sell_amount: Sales amount (100 million yuan)
            - company_num: Number of constituent stocks
        """
        if not self.is_available():
            return None

        try:
            params = {}
            if trade_date:
                params['trade_date'] = trade_date.replace('-', '')
            if ts_code:
                params['ts_code'] = ts_code
            if start_date:
                params['start_date'] = start_date.replace('-', '')
            if end_date:
                params['end_date'] = end_date.replace('-', '')

            # About 387 concept plates/day, more than 12 days (387*12=4644) Close to 5000 limit
            # If it is a date range query and the span is large, pull it in segments
            need_split = (start_date and end_date and not trade_date and not ts_code)
            if need_split:
                from datetime import datetime, timedelta
                sd = datetime.strptime(params['start_date'], '%Y%m%d')
                ed = datetime.strptime(params['end_date'], '%Y%m%d')
                days_span = (ed - sd).days
                if days_span > 12:
                    # Pull in segments, 12 days each
                    dfs = []
                    seg_start = sd
                    while seg_start <= ed:
                        seg_end = min(seg_start + timedelta(days=11), ed)
                        seg_params = {
                            'start_date': seg_start.strftime('%Y%m%d'),
                            'end_date': seg_end.strftime('%Y%m%d'),
                        }
                        df_seg = await asyncio.to_thread(
                            self.api.moneyflow_cnt_ths, **seg_params
                        )
                        if df_seg is not None and not df_seg.empty:
                            dfs.append(df_seg)
                        seg_start = seg_end + timedelta(days=1)
                    if dfs:
                        df = pd.concat(dfs, ignore_index=True)
                        self.logger.info(f"✅ 获取概念板块资金流向(分段): {len(df)} 条")
                        return df
                    return None

            df = await asyncio.to_thread(
                self.api.moneyflow_cnt_ths,
                **params
            )
            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取概念板块资金流向: {len(df)} 条")
                return df
            return None
        except Exception as e:
            self.logger.error(f"❌ Failed to obtain the capital flow of the concept sector: {e}")
            return None

    async def get_moneyflow_ind_ths(self, trade_date: str = None,
                                   ts_code: str = None) -> Optional[pd.DataFrame]:
        """
        Obtain the capital flow of the industry

        Args:
            trade_date: transaction date YYYYMMDD
            ts_code: Industry code

        Returns:
            DataFrame, Contains industry capital flow data
            - industry: Industry name
            - pct_change: Industry index rise and fall
            - company_num: Number of constituent stocks
            - net_buy_amount: Inflow of funds (100 million yuan)
            - net_sell_amount: Outflow of funds (billion yuan)
            - net_amount: Net amount (billion yuan)
        """
        if not self.is_available():
            return None

        try:
            params = {}
            if trade_date:
                params['trade_date'] = trade_date.replace('-', '')
            if ts_code:
                params['ts_code'] = ts_code

            df = await asyncio.to_thread(
                self.api.moneyflow_ind_ths,
                **params
            )
            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取行业资金流向数据: {len(df)} 条")
                return df
            return None
        except Exception as e:
            self.logger.error(f"❌ Failed to obtain industry capital flows: {e}")
            return None

    def get_stock_industry_sync(self, ticker: str) -> Optional[str]:
        """
        Synchronously obtain the industry to which the stock belongs (extracted from stock_basic)

        Args:
            ticker: Stock code (such as 000001 or 000001.SZ)

        Returns:
            Industry name, such as "bank"
        """
        if not self.is_available():
            return None

        try:
            ts_code = self._normalize_ts_code(ticker)
            df = self.api.stock_basic(
                ts_code=ts_code,
                fields='ts_code,name,industry'
            )
            if df is not None and not df.empty:
                industry = df.iloc[0].get('industry')
                if industry:
                    self.logger.info(f"✅ 股票 {ticker} 所属行业: {industry}")
                    return str(industry)
            return None
        except Exception as e:
            self.logger.error(f"❌ 获取股票行业失败: {e}")
            return None

    async def get_stock_industry(self, ticker: str) -> Optional[str]:
        """异步获取股票所属行业"""
        return await asyncio.to_thread(self.get_stock_industry_sync, ticker)

    async def get_industry_stocks(self, industry: str) -> Optional[pd.DataFrame]:
        """
        Get all stocks in a certain industry (exact match)

        Args:
            industry: Industry name (e.g. "bank", "Nationwide Real Estate") 

        Returns:
            of all stocks in the industry DataFrame
        """
        if not self.is_available():
            return None

        try:
            # Get all stocks and then match the industry exactly
            df = await asyncio.to_thread(
                self.api.stock_basic,
                list_status='L',
                fields='ts_code,symbol,name,industry,market,list_date'
            )

            if df is None or df.empty:
                return None

            # Exactly match industry names
            result_df = df[df['industry'] == industry].copy()

            if not result_df.empty:
                self.logger.info(f"✅ 获取 {industry} 行业股票: {len(result_df)} 只")
                return result_df
            else:
                self.logger.warning(f"⚠️ 未找到 {industry} 行业的股票")
                return None

        except Exception as e:
            self.logger.error(f"❌ Failed to obtain industry stock list: {e}")
            return None

    async def get_sector_stocks_daily_basic(self, industry: str,
                                            trade_date: str) -> Optional[pd.DataFrame]:
        """
        Get daily fundamental indicators for all stocks in a certain industry

        Args:
            industry: Industry name
            trade_date: transaction date

        Returns:
            Including indicators such as PE, PB, total market capitalization, etc. DataFrame
        """
        if not self.is_available():
            return None

        try:
            # 1. Get a list of industry stocks
            stocks_df = await self.get_industry_stocks(industry)
            if stocks_df is None or stocks_df.empty:
                return None

            # 2. Get the daily_basic data of the current day
            date_str = trade_date.replace('-', '')
            daily_df = await asyncio.to_thread(
                self.api.daily_basic,
                trade_date=date_str,
                fields='ts_code,trade_date,close,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm,total_mv,circ_mv,turnover_rate'
            )

            if daily_df is None or daily_df.empty:
                return None

            # 3. Screen stocks within the industry
            industry_codes = set(stocks_df['ts_code'].tolist())
            result_df = daily_df[daily_df['ts_code'].isin(industry_codes)].copy()

            # 4. Consolidated stock name
            result_df = result_df.merge(
                stocks_df[['ts_code', 'name']],
                on='ts_code',
                how='left'
            )

            self.logger.info(f"✅ 获取 {industry} 行业 {len(result_df)} 只股票的每日指标")
            return result_df

        except Exception as e:
            self.logger.error(f"❌ Failed to obtain industry stock daily indicators: {e}")
            return None

    # ==================== index data API ====================

    async def get_index_basic(
        self,
        market: str = None,
        ts_code: str = None
    ) -> Optional[pd.DataFrame]:
        """
        Get basic information about the index

        Args:
            market: exchange (SSE Shanghai Stock Exchange/SZSE Shenzhen Stock Exchange/SW Shenwan/MSCI/CSI)
            ts_code: index code

        Returns:
            DataFrame contains: ts_code, name, market, category, base_date, base_point
        """
        if not self.is_available():
            return None

        try:
            params = {}
            if market:
                params['market'] = market
            if ts_code:
                params['ts_code'] = ts_code

            df = self.api.index_basic(**params)
            self.logger.info(f"✅ 获取指数基本信息: {len(df)} 条")
            return df
        except Exception as e:
            self.logger.error(f"❌ Failed to obtain basic index information: {e}")
            return None

    async def get_index_daily(
        self,
        ts_code: str,
        start_date: str = None,
        end_date: str = None,
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        Get index daily quotes (with cache)

        Args:
            ts_code: index code (Such as 000001.SH)
            start_date: start date YYYYMMDD
            end_date: end date YYYYMMDD
            use_cache: Whether to use cache (default True)

        Returns:
            DataFrame contains: trade_date, open, high, low, close, vol, amount, pct_chg
        """
        if not self.is_available():
            return None

        # Try to get from cache
        cache_key = f"index_daily_{ts_code}_{start_date}_{end_date}"
        if use_cache:
            try:
                from tradingagents.dataflows.cache import get_cache
                cache = get_cache()
                # Index daily data cache is valid for 24 hours
                cached_key = cache.find_cached_stock_data(
                    symbol=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    data_source="tushare_index",
                    max_age_hours=24
                )
                if cached_key:
                    cached_data = cache.load_stock_data(cached_key)
                    if cached_data is not None and not cached_data.empty if hasattr(cached_data, 'empty') else cached_data:
                        self.logger.info(f"📦 从缓存获取指数 {ts_code} 日线: {len(cached_data)} 条")
                        return cached_data
            except Exception as e:
                self.logger.debug(f"⚠️ 缓存读取失败: {e}")

        try:
            params = {'ts_code': ts_code}
            if start_date:
                params['start_date'] = start_date
            if end_date:
                params['end_date'] = end_date

            df = self.api.index_daily(**params)
            self.logger.info(f"✅ 获取指数 {ts_code} 日线: {len(df)} 条")

            # Save to cache
            if use_cache and df is not None and not df.empty:
                try:
                    from tradingagents.dataflows.cache import get_cache
                    cache = get_cache()
                    cache.save_stock_data(
                        symbol=ts_code,
                        data=df,
                        start_date=start_date,
                        end_date=end_date,
                        data_source="tushare_index"
                    )
                    self.logger.debug(f"💾 指数 {ts_code} 日线已缓存")
                except Exception as e:
                    self.logger.debug(f"⚠️ 缓存保存失败: {e}")

            return df
        except Exception as e:
            self.logger.error(f"❌ 获取指数日线失败: {e}")
            return None

    async def get_index_dailybasic(
        self,
        ts_code: str = None,
        trade_date: str = None,
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        Get daily indicators of broad market index (with cache)

        Args:
            ts_code: index code
            trade_date: transaction date YYYYMMDD
            use_cache: Whether to use cache (default True)

        Returns:
            DataFrame contains: ts_code, trade_date, pe, pe_ttm, pb,
                          turnover_rate, total_mv, float_mv
        """
        if not self.is_available():
            return None

        # Try to get from cache
        cache_symbol = ts_code or f"all_{trade_date}"
        if use_cache:
            try:
                from tradingagents.dataflows.cache import get_cache
                cache = get_cache()
                cached_key = cache.find_cached_stock_data(
                    symbol=f"index_basic_{cache_symbol}",
                    start_date=trade_date,
                    end_date=trade_date,
                    data_source="tushare_index_basic",
                    max_age_hours=24
                )
                if cached_key:
                    cached_data = cache.load_stock_data(cached_key)
                    if cached_data is not None and not cached_data.empty if hasattr(cached_data, 'empty') else cached_data:
                        self.logger.info(f"📦 从缓存获取指数每日指标: {len(cached_data)} 条")
                        return cached_data
            except Exception as e:
                self.logger.debug(f"⚠️ 缓存读取失败: {e}")

        try:
            params = {}
            if ts_code:
                params['ts_code'] = ts_code
            if trade_date:
                params['trade_date'] = trade_date

            df = self.api.index_dailybasic(**params)
            self.logger.info(f"✅ 获取指数每日指标: {len(df)} 条")

            # Save to cache
            if use_cache and df is not None and not df.empty:
                try:
                    from tradingagents.dataflows.cache import get_cache
                    cache = get_cache()
                    cache.save_stock_data(
                        symbol=f"index_basic_{cache_symbol}",
                        data=df,
                        start_date=trade_date,
                        end_date=trade_date,
                        data_source="tushare_index_basic"
                    )
                except Exception as e:
                    self.logger.debug(f"⚠️ 缓存保存失败: {e}")

            return df
        except Exception as e:
            self.logger.error(f"❌ Failed to get index daily indicator: {e}")
            return None

    async def get_daily_info(
        self,
        trade_date: str,
        exchange: str = None,
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        Get daily market transaction statistics (with caching)

        Args:
            trade_date: transaction date YYYYMMDD
            exchange: exchange (SSE/SZSE)
            use_cache: Whether to use cache (default True)

        Returns:
            DataFrame contains: trade_date, ts_code, ts_name, com_count,
                          total_share, float_share, total_mv, float_mv,
                          amount, vol, up_count, down_count, etc.
        """
        if not self.is_available():
            return None

        # Try to get from cache
        cache_symbol = f"daily_info_{trade_date}_{exchange or 'all'}"
        if use_cache:
            try:
                from tradingagents.dataflows.cache import get_cache
                cache = get_cache()
                cached_key = cache.find_cached_stock_data(
                    symbol=cache_symbol,
                    start_date=trade_date,
                    end_date=trade_date,
                    data_source="tushare_daily_info",
                    max_age_hours=24
                )
                if cached_key:
                    cached_data = cache.load_stock_data(cached_key)
                    if cached_data is not None and not cached_data.empty if hasattr(cached_data, 'empty') else cached_data:
                        self.logger.info(f"📦 从缓存获取市场交易统计: {len(cached_data)} 条")
                        return cached_data
            except Exception as e:
                self.logger.debug(f"⚠️ 缓存读取失败: {e}")

        try:
            params = {'trade_date': trade_date}
            if exchange:
                params['exchange'] = exchange

            df = self.api.daily_info(**params)
            self.logger.info(f"✅ 获取市场交易统计: {len(df)} 条")

            # Save to cache
            if use_cache and df is not None and not df.empty:
                try:
                    from tradingagents.dataflows.cache import get_cache
                    cache = get_cache()
                    cache.save_stock_data(
                        symbol=cache_symbol,
                        data=df,
                        start_date=trade_date,
                        end_date=trade_date,
                        data_source="tushare_daily_info"
                    )
                except Exception as e:
                    self.logger.debug(f"⚠️ 缓存保存失败: {e}")

            return df
        except Exception as e:
            self.logger.error(f"❌ Failed to obtain market transaction statistics: {e}")
            return None

    async def get_index_weight(
        self,
        index_code: str,
        trade_date: str = None
    ) -> Optional[pd.DataFrame]:
        """
        Get index components and weights

        Args:
            index_code: index code (Such as 000300.SH)
            trade_date: transaction date YYYYMMDD

        Returns:
            DataFrame contains: index_code, con_code, trade_date, weight
        """
        if not self.is_available():
            return None

        try:
            params = {'index_code': index_code}
            if trade_date:
                params['trade_date'] = trade_date

            df = self.api.index_weight(**params)
            self.logger.info(f"✅ 获取指数 {index_code} 成分权重: {len(df)} 条")
            return df
        except Exception as e:
            self.logger.error(f"❌ Failed to obtain index component weights: {e}")
            return None

    # ==================== Market analysis related interfaces ====================

    async def get_hsgt_moneyflow(
        self,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> Optional[pd.DataFrame]:
        """
        Obtain the flow of funds from Shanghai-Shenzhen-Hong Kong Stock Connect (Northbound funds)

        Args:
            trade_date: transaction date (YYYYMMDD)
            start_date: start date (YYYYMMDD)
            end_date: end date (YYYYMMDD)

        Returns:
            DataFrame contains:
            - trade_date: transaction date
            - ggt_ss: Southbound Hong Kong (Shanghai) net inflow
            - ggt_sz: Hong Kong Stock Connect (Shenzhen) net inflow
            - hgt: Shanghai Stock Connect net inflows
            - sgt: Shenzhen stock connect net inflow
            - north_money: Net northbound capital inflow (hgt+sgt) 
            - south_money: Net southbound capital inflow (ggt_ss+ggt_sz) 
        """
        if not self.is_available():
            return None

        try:
            params = {}
            if trade_date:
                params['trade_date'] = trade_date.replace('-', '')
            if start_date:
                params['start_date'] = start_date.replace('-', '')
            if end_date:
                params['end_date'] = end_date.replace('-', '')

            df = await asyncio.to_thread(
                self.api.moneyflow_hsgt,
                **params
            )

            logger.info(f"Obtained original northbound capital flow data: {df}")
            if df is not None and not df.empty:
                # Calculate the total amount of northbound and southbound funds
                df['north_money'] = df['hgt'].fillna(0) + df['sgt'].fillna(0)
                df['south_money'] = df['ggt_ss'].fillna(0) + df['ggt_sz'].fillna(0)
                self.logger.info(f"✅ 获取沪深港通资金流向: {len(df)} 条")
                return df
            return None

        except Exception as e:
            self.logger.error(f"❌ Failed to obtain Shanghai-Shenzhen-Hong Kong Stock Connect fund flow: {e}")
            return None

    async def get_margin_detail(
        self,
        trade_date: str = None,
        start_date: str = None,
        end_date: str = None,
        exchange_id: str = None
    ) -> Optional[pd.DataFrame]:
        """
        Obtain summary of margin trading and securities lending transactions (balance of margin financing and securities lending)

        Args:
            trade_date: transaction date (YYYYMMDD)
            start_date: start date (YYYYMMDD)
            end_date: end date (YYYYMMDD)
            exchange_id: Exchange code (SSE Shanghai Stock Exchange, SZSE Shenzhen Stock Exchange)

        Returns:
            DataFrame contains:
            - trade_date: transaction date
            - exchange_id: exchange
            - rzye: Financing balance (yuan)
            - rzmre: Financing purchase amount (yuan)
            - rzche: Financing repayment amount (yuan)
            - rqye: Securities lending balance (yuan)
            - rqmcl: Securities selling volume
            - rzrqye: Balance of margin trading and securities lending (yuan)
        """
        if not self.is_available():
            return None

        try:
            params = {}
            if trade_date:
                params['trade_date'] = trade_date.replace('-', '')
            if start_date:
                params['start_date'] = start_date.replace('-', '')
            if end_date:
                params['end_date'] = end_date.replace('-', '')
            if exchange_id:
                params['exchange_id'] = exchange_id

            df = await asyncio.to_thread(
                self.api.margin,
                **params
            )

            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取融资融券数据: {len(df)} 条")
                return df
            return None

        except Exception as e:
            self.logger.error(f"❌ Failed to obtain margin trading data: {e}")
            return None

    async def get_limit_list(
        self,
        trade_date: str,
        limit_type: str = None
    ) -> Optional[pd.DataFrame]:
        """
        Get price limit statistics

        Args:
            trade_date: transaction date (YYYYMMDD)
            limit_type: Price limit type (U daily limit, D Limit down, Z Fried board)

        Returns:
            DataFrame contains:
            - trade_date: transaction date
            - ts_code: Stock code
            - name: Stock name
            - limit: Price limit type (U/D/Z)
            - pct_chg: Increase or decrease
            - close: closing price
            - open_times: Open times
            - up_stat: Connected board statistics
        """
        if not self.is_available():
            return None

        try:
            params = {
                'trade_date': trade_date.replace('-', '')
            }
            if limit_type:
                params['limit_type'] = limit_type

            df = await asyncio.to_thread(
                self.api.limit_list_d,
                **params
            )

            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取涨跌停统计: {len(df)} 条")
                return df
            return None

        except Exception as e:
            self.logger.error(f"❌ 获取涨跌停统计失败: {e}")
            return None

    async def get_stk_limit(
        self,
        trade_date: str
    ) -> Optional[pd.DataFrame]:
        """
        Get daily price limit

        Args:
            trade_date: transaction date (YYYYMMDD)

        Returns:
            DataFrame Contains price limit information
        """
        if not self.is_available():
            return None

        try:
            df = await asyncio.to_thread(
                self.api.stk_limit,
                trade_date=trade_date.replace('-', '')
            )

            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取涨跌停价格: {len(df)} 条")
                return df
            return None

        except Exception as e:
            self.logger.error(f"❌ 获取涨跌停价格失败: {e}")
            return None

    async def get_daily_stats(
        self,
        trade_date: str
    ) -> Optional[Dict[str, Any]]:
        """
        Obtain daily market statistics (number of rising and falling stocks and distribution of rising and falling prices)

        Aggregation calculation through daily interface

        Args:
            trade_date: transaction date (YYYYMMDD)

        Returns:
            Dictionary containing statistics on the number of rising and falling stocks
        """
        if not self.is_available():
            return None

        try:
            trade_date_clean = trade_date.replace('-', '')

            # Get the rise and fall of all stocks on the day
            df = await asyncio.to_thread(
                self.api.daily,
                trade_date=trade_date_clean
            )

            if df is None or df.empty:
                return None

            # Statistics on the number of stocks rising and falling
            total = len(df)
            up_count = len(df[df['pct_chg'] > 0])
            down_count = len(df[df['pct_chg'] < 0])
            flat_count = len(df[df['pct_chg'] == 0])

            # Increase distribution
            up_gt5 = len(df[df['pct_chg'] >= 5])
            up_3_5 = len(df[(df['pct_chg'] >= 3) & (df['pct_chg'] < 5)])
            down_gt5 = len(df[df['pct_chg'] <= -5])
            down_3_5 = len(df[(df['pct_chg'] <= -3) & (df['pct_chg'] > -5)])

            stats = {
                'trade_date': trade_date_clean,
                'total': total,
                'up_count': up_count,
                'down_count': down_count,
                'flat_count': flat_count,
                'up_ratio': up_count / total * 100 if total > 0 else 0,
                'down_ratio': down_count / total * 100 if total > 0 else 0,
                'up_gt5': up_gt5,
                'up_3_5': up_3_5,
                'down_gt5': down_gt5,
                'down_3_5': down_3_5,
            }

            self.logger.info(f"✅ 获取每日市场统计: 涨{up_count}/跌{down_count}/平{flat_count}")
            return stats

        except Exception as e:
            self.logger.error(f"❌ Failed to get daily market statistics: {e}")
            return None

    async def get_pledge_detail(
        self,
        ts_code: str = None,
        ann_date: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> Optional[pd.DataFrame]:
        """
        Obtain equity pledge details

        Args:
            ts_code: Stock code (TS format, such as 600519.SH)
            ann_date: Announcement date (YYYYMMDD)
            start_date: Announcement start date (YYYYMMDD)
            end_date: Announcement end date (YYYYMMDD)

        Returns:
            DataFrame contains:
            - ts_code: TS Stock code
            - ann_date: Announcement date
            - holder_name: Shareholder name
            - pledge_amount: Pledge quantity (10,000 shares)
            - start_date: Staking start date
            - end_date: Staking end date
            - is_release: Has it been released?
            - release_date: Release date
            - pledgor: Pledger
            - holding_amount: Total number of shares held (10,000 shares)
            - pledged_amount: Total number of pledges (10,000 shares)
            - p_total_ratio: The proportion of this pledge to the total equity
            - h_total_ratio: Ratio of total shareholdings to total share capital
            - is_buyback: Whether to repurchase (0 no 1 yes)
        """
        if not self.is_available():
            return None

        try:
            params = {}
            if ts_code:
                params['ts_code'] = ts_code
            if ann_date:
                params['ann_date'] = ann_date.replace('-', '')
            if start_date:
                params['start_date'] = start_date.replace('-', '')
            if end_date:
                params['end_date'] = end_date.replace('-', '')

            df = await asyncio.to_thread(
                self.api.pledge_detail,
                **params
            )

            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取股权质押明细: {len(df)} 条 | ts_code={ts_code or 'all'}")
                return df
            return None

        except Exception as e:
            self.logger.error(f"❌ Failed to obtain equity pledge details: {e}")
            return None


    async def get_audit_opinion(
        self,
        ts_code: str = None,
        ann_date: str = None,
        start_date: str = None,
        end_date: str = None,
        period: str = None,
    ) -> Optional[pd.DataFrame]:
        """
        Obtain audit opinions of A-share companies (stk_audit)

        Args:
            ts_code: Stock code (TS format, such as 600519.SH)
            ann_date: Announcement date (YYYYMMDD)
            start_date: Announcement start date (YYYYMMDD)
            end_date: Announcement end date (YYYYMMDD)
            period: reporting period (YYYYMMDD)

        Returns:
            DataFrame contains:
            - ts_code: TS Stock code
            - ann_date: Announcement date
            - end_date: Reporting period end date
            - audit_result: Audit results
            - audit_fees: Total audit fees (yuan)
            - audit_sign: auditor
            - audit_company: Audit agency
        """
        if not self.is_available():
            return None

        try:
            params = {}
            if ts_code:
                params['ts_code'] = ts_code
            if ann_date:
                params['ann_date'] = ann_date.replace('-', '')
            if start_date:
                params['start_date'] = start_date.replace('-', '')
            if end_date:
                params['end_date'] = end_date.replace('-', '')
            if period:
                params['period'] = period.replace('-', '')

            df = await asyncio.to_thread(
                self.api.stk_audit,
                **params
            )

            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取审计意见: {len(df)} 条 | ts_code={ts_code or 'all'}")
                return df
            return None

        except Exception as e:
            self.logger.error(f"❌ 获取审计意见失败: {e}")
            return None

    async def get_disclosure_rating(
        self,
        ts_code: str = None,
        end_date: str = None,
    ) -> Optional[pd.DataFrame]:
        """
        Obtain exchange information disclosure evaluation results (disclosure_rating)

        Args:
            ts_code: Stock code (TS format, such as 600519.SH)
            end_date: reporting period (YYYYMMDD)

        Returns:
            DataFrame contains:
            - ts_code: TS Stock code
            - end_date: Assessment year
            - disclosure_result: Assessment results (A/B/C/D)
        """
        if not self.is_available():
            return None

        try:
            params = {}
            if ts_code:
                params['ts_code'] = ts_code
            if end_date:
                params['end_date'] = end_date.replace('-', '')

            df = await asyncio.to_thread(
                self.api.disclosure_rating,
                **params
            )

            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取信息披露评级: {len(df)} 条 | ts_code={ts_code or 'all'}")
                return df
            return None

        except Exception as e:
            self.logger.error(f"❌ Failed to obtain disclosure rating: {e}")
            return None

    async def get_equity_incentive(
        self,
        ts_code: str = None,
        ann_date: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> Optional[pd.DataFrame]:
        """
        Get equity incentive plan details (equity_incentive)

        Args:
            ts_code: Stock code (TS format, such as 600519.SH)
            ann_date: Announcement date (YYYYMMDD)
            start_date: Announcement start date (YYYYMMDD)
            end_date: Announcement end date (YYYYMMDD)

        Returns:
            DataFrame contains:
            - ts_code: TS Stock code
            - ann_date: Announcement date
            - inc_plan: Incentive package
            - grant_num: Number of shares granted (10,000 shares)
            - grant_price: award price
            - inc_duration: Incentive period (years)
            - inc_perf: Exercise conditions/performance requirements
            - stockholder_rt: Proportion of total equity
        """
        if not self.is_available():
            return None

        try:
            params = {}
            if ts_code:
                params['ts_code'] = ts_code
            if ann_date:
                params['ann_date'] = ann_date.replace('-', '')
            if start_date:
                params['start_date'] = start_date.replace('-', '')
            if end_date:
                params['end_date'] = end_date.replace('-', '')

            df = await asyncio.to_thread(
                self.api.equity_incentive,
                **params
            )

            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取股权激励: {len(df)} 条 | ts_code={ts_code or 'all'}")
                return df
            return None

        except Exception as e:
            self.logger.error(f"❌ 获取股权激励失败: {e}")
            return None

    async def get_management_penalties(
        self,
        ts_code: str = None,
        ann_date: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> Optional[pd.DataFrame]:
        """
        Get violation penalty records (stk_penalty)

        Args:
            ts_code: Stock code (TS format, such as 600519.SH)
            ann_date: Announcement date (YYYYMMDD)
            start_date: Announcement start date (YYYYMMDD)
            end_date: Announcement end date (YYYYMMDD)

        Returns:
            DataFrame contains:
            - ts_code: TS Stock code
            - ann_date: Announcement date
            - punish_type: Penalty type (warning/fine/market ban, etc.)
            - punish_object: Punishment target (company/individual)
            - punish_amount: Amount of penalty (10,000 yuan)
            - violat_type: Violation type
            - violate_content: Reason for violation
        """
        if not self.is_available():
            return None

        try:
            params = {}
            if ts_code:
                params['ts_code'] = ts_code
            if ann_date:
                params['ann_date'] = ann_date.replace('-', '')
            if start_date:
                params['start_date'] = start_date.replace('-', '')
            if end_date:
                params['end_date'] = end_date.replace('-', '')

            df = await asyncio.to_thread(
                self.api.stk_penalty,
                **params
            )

            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取违规处罚: {len(df)} 条 | ts_code={ts_code or 'all'}")
                return df
            return None

        except Exception as e:
            self.logger.error(f"❌ 获取违规处罚失败: {e}")
            return None


# Global provider instance
_tushare_provider = None
_tushare_provider_initialized = False

def get_tushare_provider() -> TushareProvider:
    """Get the global Tushare API Client provider instance."""
    global _tushare_provider, _tushare_provider_initialized
    if _tushare_provider is None:
        _tushare_provider = TushareProvider()

    _tushare_provider_initialized = _tushare_provider.is_available()
    return _tushare_provider
