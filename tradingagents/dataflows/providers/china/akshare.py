"""
AKShare unified data provider
A unified data synchronization solution based on AKShare SDK, providing a standardized data interface
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Union
import pandas as pd

from ..base_provider import BaseStockDataProvider

logger = logging.getLogger(__name__)


class AKShareNetworkError(RuntimeError):
    """AKShare Transient failure at the network layer."""


class AKShareProvider(BaseStockDataProvider):
    """
    AKShare unified data provider
    
    Provides a standardized stock data interface, supporting:
    - Obtain basic stock information
    - Historical market data
    - Real-time market data
    - financial data
    - Hong Kong stock data support
    """
    
    def __init__(self):
        super().__init__("AKShare")
        self.ak = None
        self.connected = False
        self._stock_list_cache = None  # Cache the stock list to avoid repeated retrieval
        self._cache_time = None  # Cache time
        self._event_loop_closed = False  # 🔥 Event loop shutdown flag (used to detect Ctrl+C exit)
        self._initialize_akshare()
    
    def _initialize_akshare(self):
        """初始化AKShare连接"""
        try:
            import akshare as ak
            import requests
            import time

            # Try importing curl_cffi and use it if available to bypass anti-crawler
            try:
                from curl_cffi import requests as curl_requests
                use_curl_cffi = True
                logger.info("🔧 curl_cffi detected, will be used to emulate real browser TLS fingerprint")
            except ImportError:
                use_curl_cffi = False
                logger.warning("⚠️ curl_cffi If not installed, standard requests will be used (may be intercepted by anti-crawlers)")
                logger.warning("   Recommended installation: pip install curl-cffi")

            # Fix AKShare bug: set default headers for requests and add request delay
            # AKShare of stock_news_em()The function does not set the necessary headers, causing the API to return an empty response.
            if not hasattr(requests, '_akshare_headers_patched'):
                original_get = requests.get
                last_request_time = {'time': 0}  # Use a dictionary for modification in closures

                def patched_get(url, **kwargs):
                    """
                    Wrap the requests.get method to automatically add necessary headers and request delays
                    Repair AKShare stock_news_em()The problem of function missing headers
                    If available, use curl_cffi to simulate real browser TLS fingerprinting
                    """
                    # Add request delay to avoid being banned by anti-crawlers
                    # Add delay only to requests from Oriental Fortune Network
                    if 'eastmoney.com' in url:
                        current_time = time.time()
                        time_since_last_request = current_time - last_request_time['time']
                        if time_since_last_request < 0.5:  # At least 0.5 seconds apart
                            time.sleep(0.5 - time_since_last_request)
                        last_request_time['time'] = time.time()

                    # If it is a request from Oriental Fortune Network and curl_cffi is available, use it to bypass the anti-crawler
                    if use_curl_cffi and 'eastmoney.com' in url:
                        try:
                            # Using curl_cffi to emulate Chrome 120's TLS fingerprint
                            # Note: When using impersonate, do not pass custom headers and let curl_cffi set them automatically
                            curl_kwargs = {
                                'timeout': kwargs.get('timeout', 10),
                                'impersonate': "chrome120"  # Simulation Chrome 120
                            }

                            # Only pass non-headers parameters
                            if 'params' in kwargs:
                                curl_kwargs['params'] = kwargs['params']
                            # Do not pass headers and let impersonate set them automatically
                            if 'data' in kwargs:
                                curl_kwargs['data'] = kwargs['data']
                            if 'json' in kwargs:
                                curl_kwargs['json'] = kwargs['json']

                            response = curl_requests.get(url, **curl_kwargs)
                            # curl_cffi The response object is already compatible with requests.Response
                            return response
                        except Exception as e:
                            # curl_cffi Failure, fallback to standard requests
                            error_msg = str(e)
                            # Ignore verbose logs for TLS library errors and 400 errors (this is a known issue with Docker environments)
                            if 'invalid library' not in error_msg and '400' not in error_msg:
                                logger.warning(f"⚠️ curl_cffi Request failed, fallback to standard requests: {e}")

                    # Standard requests request (non-Eastern Fortune Network, or curl_cffi is unavailable/failed)
                    # Set browser request headers
                    if 'headers' not in kwargs or kwargs['headers'] is None:
                        kwargs['headers'] = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                            'Accept-Encoding': 'gzip, deflate, br',
                            'Referer': 'https://www.eastmoney.com/',
                            'Connection': 'keep-alive',
                        }
                    elif isinstance(kwargs['headers'], dict):
                        # If headers already exist, make sure to include the necessary fields
                        if 'User-Agent' not in kwargs['headers']:
                            kwargs['headers']['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                        if 'Referer' not in kwargs['headers']:
                            kwargs['headers']['Referer'] = 'https://www.eastmoney.com/'
                        if 'Accept' not in kwargs['headers']:
                            kwargs['headers']['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
                        if 'Accept-Language' not in kwargs['headers']:
                            kwargs['headers']['Accept-Language'] = 'zh-CN,zh;q=0.9,en;q=0.8'

                    # Add retry mechanism (up to 3 times)
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            return original_get(url, **kwargs)
                        except Exception as e:
                            # Check if it is an SSL error
                            error_str = str(e)
                            is_ssl_error = ('SSL' in error_str or 'ssl' in error_str or
                                          'UNEXPECTED_EOF_WHILE_READING' in error_str)

                            if is_ssl_error and attempt < max_retries - 1:
                                # SSL Error, wait and try again
                                wait_time = 0.5 * (attempt + 1)  # Increment wait time
                                time.sleep(wait_time)
                                continue
                            else:
                                # Non-SSL error or the maximum number of retries has been reached, throw directly
                                raise

                # Application patch
                requests.get = patched_get
                requests._akshare_headers_patched = True

                if use_curl_cffi:
                    logger.info("🔧 The headers problem of AKShare has been fixed, using curl_cffi to simulate a real browser (Chrome 120)")
                else:
                    logger.info("🔧 Fixed AKShare headers issue and added request delay (0.5 seconds)")

            self.ak = ak
            self.connected = True

            # Configure timeouts and retries
            self._configure_timeout()

            logger.info("✅ AKShare Connection successful")
        except ImportError as e:
            logger.error(f"❌ AKShare Not installed: {e}")
            self.connected = False
        except Exception as e:
            logger.error(f"❌ AKShare Initialization failed: {e}")
            self.connected = False

    def _get_stock_news_direct(self, symbol: str, limit: int = 10) -> Optional[pd.DataFrame]:
        """
        Directly call Oriental Fortune News API (bypassing AKShare)
        Use curl_cffi to simulate a real browser, suitable for Docker environment

        Args:
            symbol: Stock code
            limit: Return quantity limit

        Returns:
            News DataFrame or None
        """
        try:
            from curl_cffi import requests as curl_requests
            import json
            import time
            import os

            # Standardized stock code
            symbol_6 = symbol.zfill(6)

            # Build request parameters
            url = "https://search-api-web.eastmoney.com/search/jsonp"
            param = {
                "uid": "",
                "keyword": symbol_6,
                "type": ["cmsArticleWebOld"],
                "client": "web",
                "clientType": "web",
                "clientVersion": "curr",
                "param": {
                    "cmsArticleWebOld": {
                        "searchScope": "default",
                        "sort": "default",
                        "pageIndex": 1,
                        "pageSize": limit,
                        "preTag": "",
                        "postTag": ""
                    }
                }
            }

            params = {
                "cb": f"jQuery{int(time.time() * 1000)}",
                "param": json.dumps(param),
                "_": str(int(time.time() * 1000))
            }

            # Use curl_cffi to send requests
            response = curl_requests.get(
                url,
                params=params,
                timeout=10,
                impersonate="chrome120"
            )

            if response.status_code != 200:
                self.logger.error(f"❌ {symbol} Oriental Fortune Network API returns error: {response.status_code}")
                return None

            # Parse JSONP response
            text = response.text
            if text.startswith("jQuery"):
                text = text[text.find("(")+1:text.rfind(")")]

            data = json.loads(text)

            # Check return data
            if "result" not in data or "cmsArticleWebOld" not in data["result"]:
                self.logger.error(f"❌ {symbol} Oriental Fortune Network API returns data structure exception")
                return None

            articles = data["result"]["cmsArticleWebOld"]

            if not articles:
                self.logger.warning(f"⚠️ {symbol} 未获取到新闻")
                return None

            # Convert to DataFrame (compatible with AKShare format)
            news_data = []
            for article in articles:
                news_data.append({
                    "新闻标题": article.get("title", ""),
                    "新闻内容": article.get("content", ""),
                    "发布时间": article.get("date", ""),
                    "新闻链接": article.get("url", ""),
                    "关键词": article.get("keywords", ""),
                    "新闻来源": article.get("source", "东方财富网"),
                    "新闻类型": article.get("type", "")
                })

            df = pd.DataFrame(news_data)
            self.logger.info(f"✅ {symbol} 直接调用 API 获取新闻成功: {len(df)} 条")
            return df

        except Exception as e:
            self.logger.error(f"❌ {symbol} 直接调用 API 失败: {e}")
            return None

    def _configure_timeout(self):
        """Configure AKShare s timeout settings"""
        try:
            import socket
            socket.setdefaulttimeout(60)  # 60 seconds timeout
            logger.info("🔧 AKShare Timeout configuration completed: 60 seconds")
        except Exception as e:
            logger.warning(f"⚠️ AKShare Timeout configuration failed: {e}")
    
    async def connect(self) -> bool:
        """Connect to AKShare data source"""
        return await self.test_connection()

    async def test_connection(self) -> bool:
        """测试AKShare连接"""
        if not self.connected:
            return False

        # AKShare It is a library based on web crawlers and does not require traditional"connect"test
        # As long as the library has been successfully imported, it is considered available.
        # The actual network request will be made when the specific call is made, and has its own error handling
        logger.info("✅ AKShare Connection test successful (library loaded)")
        return True
    
    def get_stock_list_sync(self) -> Optional[pd.DataFrame]:
        """获取股票列表（同步版本）"""
        if not self.connected:
            return None

        try:
            logger.info("📋 Get AKShare stock list (synchronized)...")
            stock_df = self.ak.stock_info_a_code_name()

            if stock_df is None or stock_df.empty:
                logger.warning("⚠️ AKShare Stock list is empty")
                return None

            logger.info(f"✅ AKShare股票列表获取成功: {len(stock_df)}只股票")
            return stock_df

        except Exception as e:
            logger.error(f"❌ AKShare Failed to get stock list: {e}")
            return None

    async def get_stock_list(self) -> List[Dict[str, Any]]:
        """
        Get a list of stocks

        Returns:
            List of stocks with ticker and name
        """
        if not self.connected:
            return []

        try:
            logger.info("📋 Get AKShare stock list...")

            # Use the thread pool to asynchronously obtain the stock list and add timeout protection
            def fetch_stock_list():
                return self.ak.stock_info_a_code_name()

            stock_df = await asyncio.to_thread(fetch_stock_list)

            if stock_df is None or stock_df.empty:
                logger.warning("⚠️ AKShare Stock list is empty")
                return []

            # Convert to standard format
            stock_list = []
            for _, row in stock_df.iterrows():
                stock_list.append({
                    "code": str(row.get("code", "")),
                    "name": str(row.get("name", "")),
                    "source": "akshare"
                })

            logger.info(f"✅ AKShare股票列表获取成功: {len(stock_list)}只股票")
            return stock_list

        except Exception as e:
            logger.error(f"❌ AKShare Failed to get stock list: {e}")
            return []

    async def get_stock_basic_info_for_single_sync(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Get the basic information needed for single stock synchronization.

        Single-strand sync allows low-frequency combination of multiple AKShare interfaces in exchange for more stable field coverage;
        Batch synchronization still maintains the existing logic to avoid high-frequency stock-by-stock requests triggering source site current limiting.
        """
        if not self.connected:
            return None

        code = str(code).strip().zfill(6)
        board = self._determine_board(code)
        exchange_name = self._determine_market(code)
        basic_info = {
            "code": code,
            "name": f"股票{code}",
            "area": "未知",
            "industry": "未知",
            "market": board,
            "sse": exchange_name,
            "list_date": "",
            "full_symbol": self._get_full_symbol(code),
            "market_info": self._get_market_info(code),
            "data_source": "akshare",
            "last_sync": datetime.now(timezone.utc),
            "sync_status": "degraded",
            "sec": "stock_cn",
        }

        source_hits: List[str] = []
        errors: List[str] = []

        for source_name, fetcher in (
            ("cninfo_profile", self._get_single_stock_profile_info),
            ("exchange_listing", self._get_single_stock_listing_info),
            ("xq_spot", self._get_single_stock_spot_info),
        ):
            try:
                source_data = await fetcher(code)
            except Exception as e:
                logger.warning(f"⚠️ {code} 单股基础信息接口 {source_name} 调用失败: {e}")
                errors.append(f"{source_name}: {e}")
                continue

            if not source_data:
                continue

            self._merge_single_stock_basic_info(basic_info, source_data)
            source_hits.append(source_name)

        detail_failure = None
        detail_symbol = self._get_akshare_cn_symbol(code)
        if self._needs_single_sync_detail_fallback(basic_info):
            detail_info = await self._get_stock_info_detail(code)
            if detail_info and not detail_info.get("_detail_fetch_failed"):
                self._merge_single_stock_basic_info(basic_info, detail_info)
                source_hits.append("eastmoney_detail")
            else:
                detail_failure = (detail_info or {}).get("_detail_fetch_error") or "AKShare The individual stock details interface did not return valid data"
                detail_symbol = (detail_info or {}).get("_detail_symbol", detail_symbol)
                errors.append(detail_failure)

        if self._has_single_sync_basic_info(basic_info):
            basic_info["sync_status"] = "success"
            logger.info(
                f"✅ {code} Single stock basic information obtained successfully: Source={','.join(source_hits) if source_hits else 'unknown'}"
            )
            return basic_info

        basic_info["sync_status"] = "degraded"
        basic_info["detail_fetch_error"] = detail_failure or "; ".join(errors) or "AKShare The single stock basic information interface did not return valid data."
        basic_info["detail_fetch_symbol"] = detail_symbol
        logger.warning(
            f"⚠️ {code} Failed to obtain basic information of single stock, downgrade result has been returned: {basic_info['detail_fetch_error']}"
        )
        return basic_info
    
    async def get_stock_basic_info(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Get basic stock information
        
        Args:
            code: Stock code
            
        Returns:
            Standardized basic stock information
        """
        if not self.connected:
            return None
        
        try:
            logger.debug(f"📊 获取{code}基础信息...")
            
            # Get basic stock information
            stock_info = await self._get_stock_info_detail(code)
            
            if not stock_info:
                logger.warning(f"⚠️ 未找到{code}的基础信息")
                return None
            
            detail_fetch_failed = bool(stock_info.get("_detail_fetch_failed"))

            # Convert to standardized dictionary
            basic_info = {
                "code": code,
                "name": stock_info.get("name", f"股票{code}"),
                "area": stock_info.get("area", "未知"),
                "industry": stock_info.get("industry", "未知"),
                "market": self._determine_market(code),
                "list_date": stock_info.get("list_date", ""),
                # extension fields
                "full_symbol": self._get_full_symbol(code),
                "market_info": self._get_market_info(code),
                "data_source": "akshare",
                "last_sync": datetime.now(timezone.utc),
                "sync_status": "degraded" if detail_fetch_failed else "success"
            }

            if detail_fetch_failed:
                basic_info["detail_fetch_error"] = stock_info.get("_detail_fetch_error")
                basic_info["detail_fetch_symbol"] = stock_info.get("_detail_symbol")
                logger.warning(f"⚠️ {code} Only the downgrade synchronization of basic information is completed, and the detailed information interface is not available.")
            
            logger.debug(f"✅ {code}基础信息获取成功")
            return basic_info
            
        except Exception as e:
            logger.error(f"❌ 获取{code}基础信息失败: {e}")
            return None

    async def _get_single_stock_listing_info(self, code: str) -> Dict[str, Any]:
        """Extract single stock basic fields from the exchange stock list interface."""

        def fetch_listing_data() -> Optional[pd.DataFrame]:
            if code.startswith("68"):
                return self.ak.stock_info_sh_name_code(symbol="科创板")
            if code.startswith(("60", "90")):
                return self.ak.stock_info_sh_name_code(symbol="主板A股")
            if code.startswith(("00", "30", "20")):
                return self.ak.stock_info_sz_name_code(symbol="A股列表")
            if code.startswith(("8", "4")):
                return self.ak.stock_info_bj_name_code()
            return None

        listing_df = await asyncio.to_thread(fetch_listing_data)
        if listing_df is None or listing_df.empty:
            return {}

        code_column = next(
            (column for column in ("A股代码", "证券代码", "B股代码") if column in listing_df.columns),
            None,
        )
        if not code_column:
            return {}

        listing_df = listing_df.copy()
        listing_df[code_column] = listing_df[code_column].map(self._normalize_security_code)
        matched = listing_df[listing_df[code_column] == code]
        if matched.empty:
            return {}

        row = matched.iloc[0]
        listing_info: Dict[str, Any] = {"market": self._determine_board(code)}

        name_column = next(
            (column for column in ("A股简称", "证券简称", "B股简称") if column in matched.columns),
            None,
        )
        if name_column:
            name = self._safe_str(row.get(name_column))
            if name:
                listing_info["name"] = name

        industry = self._safe_str(row.get("所属行业")) if "所属行业" in matched.columns else ""
        if industry:
            listing_info["industry"] = industry

        list_date = self._normalize_basic_date(row.get("A股上市日期", row.get("上市日期")))
        if list_date:
            listing_info["list_date"] = list_date

        board = self._safe_str(row.get("板块")) if "板块" in matched.columns else ""
        if board:
            listing_info["market"] = board

        area = self._safe_str(row.get("地区")) if "地区" in matched.columns else ""
        if area:
            listing_info["area"] = area

        return listing_info

    async def _get_single_stock_profile_info(self, code: str) -> Dict[str, Any]:
        """Extracts the underlying single stock fields from the CNInfo Company Profile interface."""

        def fetch_profile_data() -> pd.DataFrame:
            return self.ak.stock_profile_cninfo(symbol=code)

        profile_df = await asyncio.to_thread(fetch_profile_data)
        if profile_df is None or profile_df.empty:
            return {}

        row = profile_df.iloc[0]
        profile_info: Dict[str, Any] = {}

        name = self._safe_str(row.get("A股简称") or row.get("公司名称"))
        if name:
            profile_info["name"] = name

        company_name = self._safe_str(row.get("公司名称"))
        if company_name:
            profile_info["company_name"] = company_name

        industry = self._safe_str(row.get("所属行业"))
        if industry:
            profile_info["industry"] = industry

        list_date = self._normalize_basic_date(row.get("上市日期"))
        if list_date:
            profile_info["list_date"] = list_date

        established_date = self._normalize_basic_date(row.get("成立日期"))
        if established_date:
            profile_info["established_date"] = established_date

        market_label = self._safe_str(row.get("所属市场"))
        normalized_exchange = self._normalize_exchange_name(market_label)
        if normalized_exchange:
            profile_info["sse"] = normalized_exchange

        board = self._extract_board_from_market_label(market_label)
        if board:
            profile_info["market"] = board

        main_business = self._safe_str(row.get("主营业务"))
        if main_business:
            profile_info["main_business"] = main_business

        business_scope = self._safe_str(row.get("经营范围"))
        if business_scope:
            profile_info["business_scope"] = business_scope

        company_profile = self._safe_str(row.get("机构简介"))
        if company_profile:
            profile_info["company_profile"] = company_profile

        return profile_info

    async def _get_single_stock_spot_info(self, code: str) -> Dict[str, Any]:
        """Extract the single stock valuation field from the Snowball real-time market interface."""

        def fetch_spot_data() -> pd.DataFrame:
            return self.ak.stock_individual_spot_xq(symbol=self._get_xueqiu_symbol(code))

        spot_df = await asyncio.to_thread(fetch_spot_data)
        if spot_df is None or spot_df.empty:
            return {}

        spot_map = {
            self._safe_str(row.get("item")): row.get("value")
            for _, row in spot_df.iterrows()
            if self._safe_str(row.get("item"))
        }
        spot_info: Dict[str, Any] = {}

        name = self._safe_str(spot_map.get("名称"))
        if name:
            spot_info["name"] = name

        exchange_name = self._normalize_exchange_name(spot_map.get("交易所"))
        if exchange_name:
            spot_info["sse"] = exchange_name

        total_mv = self._convert_market_cap_to_yi(spot_map.get("资产净值/总市值"))
        if total_mv is not None:
            spot_info["total_mv"] = total_mv

        circ_mv = self._convert_market_cap_to_yi(spot_map.get("流通值"))
        if circ_mv is not None:
            spot_info["circ_mv"] = circ_mv

        pe = self._safe_optional_float(spot_map.get("市盈率(动)"))
        if pe is not None:
            spot_info["pe"] = pe

        pe_static = self._safe_optional_float(spot_map.get("市盈率(静)"))
        if pe_static is not None:
            spot_info["pe_static"] = pe_static

        pe_ttm = self._safe_optional_float(spot_map.get("市盈率(TTM)"))
        if pe_ttm is not None:
            spot_info["pe_ttm"] = pe_ttm

        pb = self._safe_optional_float(spot_map.get("市净率"))
        if pb is not None:
            spot_info["pb"] = pb

        ps = self._safe_optional_float(spot_map.get("市销率"))
        if ps is not None:
            spot_info["ps"] = ps

        turnover_rate = self._safe_optional_float(spot_map.get("周转率"))
        if turnover_rate is not None:
            spot_info["turnover_rate"] = turnover_rate

        total_share = self._safe_optional_float(spot_map.get("基金份额/总股本"))
        if total_share is not None:
            spot_info["total_share"] = total_share

        float_share = self._safe_optional_float(spot_map.get("流通股"))
        if float_share is not None:
            spot_info["float_share"] = float_share

        close = self._safe_optional_float(spot_map.get("现价"))
        if close is not None:
            spot_info["close"] = close

        return spot_info

    def _merge_single_stock_basic_info(self, target: Dict[str, Any], incoming: Dict[str, Any]) -> None:
        """Merge source fields into single stock underlying information results."""
        code = target.get("code", "")
        default_name = f"股票{code}"

        for key, value in incoming.items():
            if value is None:
                continue

            if isinstance(value, str):
                value = value.strip()
                if not value or value.lower() in {"none", "nan", "nat", "null", "-", "--"}:
                    continue

            current_value = target.get(key)

            if key == "name":
                if current_value in (None, "", default_name):
                    target[key] = value
                continue

            if key == "market":
                if current_value in (None, "", "未知", self._determine_board(code)):
                    target[key] = value
                continue

            if key == "sse":
                if current_value in (None, "", "未知", self._determine_market(code)):
                    target[key] = value
                continue

            if key in {"industry", "area", "list_date", "company_name", "main_business", "business_scope", "company_profile", "established_date"}:
                if current_value in (None, "", "未知"):
                    target[key] = value
                continue

            if current_value in (None, "", 0, 0.0):
                target[key] = value

    def _has_single_sync_basic_info(self, basic_info: Dict[str, Any]) -> bool:
        """Determine whether single stock synchronization has obtained enough basic fields."""
        code = basic_info.get("code", "")
        name = basic_info.get("name")
        industry = basic_info.get("industry")
        list_date = basic_info.get("list_date")

        name_ok = name not in (None, "", f"股票{code}")
        industry_ok = industry not in (None, "", "未知")
        list_date_ok = bool(list_date)
        valuation_ok = any(
            basic_info.get(field) not in (None, "", 0, 0.0)
            for field in ("total_mv", "circ_mv", "pe", "pb", "pe_ttm", "ps")
        )
        return name_ok and (industry_ok or list_date_ok or valuation_ok)

    def _needs_single_sync_detail_fallback(self, basic_info: Dict[str, Any]) -> bool:
        """To determine whether a single stock is synchronized, it is necessary to call Dongcai individual stock details for details."""
        code = basic_info.get("code", "")
        return (
            basic_info.get("name") in (None, "", f"股票{code}")
            or basic_info.get("industry") in (None, "", "未知")
            or not basic_info.get("list_date")
        )
    
    async def _get_stock_list_cached(self):
        """Get cached stock list (avoid duplicate retrieval)"""
        from datetime import datetime, timedelta

        # If the cache exists and has not expired (1 hour), return directly
        if self._stock_list_cache is not None and self._cache_time is not None:
            if datetime.now() - self._cache_time < timedelta(hours=1):
                return self._stock_list_cache

        # Otherwise get it again
        def fetch_stock_list():
            try:
                # 🔥 Try using stock_info_a_code_name() Get a list of stocks
                result = self.ak.stock_info_a_code_name()
                return result
            except Exception as e:
                error_msg = str(e)
                # 🔥 If it is an Excel format error, try specifying the engine
                if "Excel file format cannot be determined" in error_msg or "engine manually" in error_msg:
                    logger.warning(f"⚠️ Excel Format recognition failed, trying to specify the engine: {e}")
                    try:
                        # Try using the openpyxl engine
                        import pandas as pd
                        # Call again, but this time we need to intercept the pandas read_excel call
                        # Due to the internal call of AKShare, we cannot directly specify the engine
                        # So the warning is recorded here first, without affecting the main process.
                        logger.warning(f"⚠️ Excel format problems cannot be automatically repaired and stock list acquisition fails, but other functions are not affected.")
                        return None
                    except Exception as e2:
                        logger.error(f"❌ Attempt to repair Excel format failed: {e2}")
                        return None
                else:
                    # Other errors are thrown directly
                    raise

        try:
            stock_list = await asyncio.to_thread(fetch_stock_list)
            if stock_list is not None and not stock_list.empty:
                self._stock_list_cache = stock_list
                self._cache_time = datetime.now()
                logger.info(f"✅ 股票列表缓存更新: {len(stock_list)} 只股票")
                return stock_list
            else:
                logger.warning(f"⚠️ The stock list is empty, it may be a problem with the interface return format.")
        except Exception as e:
            logger.error(f"❌ 获取股票列表失败: {e}")
            # 🔥 Even if the acquisition of the stock list fails, other functions will not be affected, and it will just return None
            # The caller should be able to handle the None case (the default stock name will be used)

        return None

    async def _get_stock_info_detail(self, code: str) -> Dict[str, Any]:
        """
        Get stock details
        
        🔥 Optimization: Directly call the individual stock information interface without obtaining the entire stock list.
        The stock code and name should already be in the database
        """
        try:
            akshare_symbol = self._get_akshare_cn_symbol(code)

            # 🔥 Directly obtain detailed information on individual stocks (including detailed information on industries, regions, etc.)
            def fetch_individual_info():
                return self.ak.stock_individual_info_em(symbol=akshare_symbol)

            try:
                stock_info = await asyncio.to_thread(fetch_individual_info)

                if stock_info is not None and not stock_info.empty:
                    # parse information
                    info = {"code": code, "_detail_symbol": akshare_symbol}

                    # Extract stock name
                    name_row = stock_info[stock_info['item'] == '股票简称']
                    if not name_row.empty:
                        info['name'] = str(name_row['value'].iloc[0])

                    # Extract industry information
                    industry_row = stock_info[stock_info['item'] == '所属行业']
                    if not industry_row.empty:
                        info['industry'] = str(industry_row['value'].iloc[0])

                    # Extract region information
                    area_row = stock_info[stock_info['item'] == '所属地区']
                    if not area_row.empty:
                        info['area'] = str(area_row['value'].iloc[0])

                    # Extract listing date
                    list_date_row = stock_info[stock_info['item'] == '上市时间']
                    if not list_date_row.empty:
                        info['list_date'] = str(list_date_row['value'].iloc[0])

                    logger.debug(f"✅ 成功获取{code}的详细信息: {info.get('name', 'N/A')}")
                    return info
            except Exception as e:
                logger.warning(f"⚠️ 获取{code}个股详细信息失败: {e}")

            # 🔥 If the acquisition fails, return basic information (using the default name)
            # Note: In actual use, the stock name should be obtained from the database, this is only used as a final fallback
            logger.debug(f"⚠️ 无法获取{code}的详细信息，使用默认信息")
            return {
                "code": code,
                "name": f"股票{code}",
                "industry": "未知",
                "area": "未知",
                "_detail_fetch_failed": True,
                "_detail_fetch_error": "AKShare The network of the individual stock details interface is abnormal, and the basic information has been used",
                "_detail_symbol": akshare_symbol,
            }

        except Exception as e:
            logger.error(f"❌ 获取{code}详细信息失败: {e}")
            return {
                "code": code,
                "name": f"股票{code}",
                "industry": "未知",
                "area": "未知",
                "_detail_fetch_failed": True,
                "_detail_fetch_error": str(e),
                "_detail_symbol": self._get_akshare_cn_symbol(code),
            }
    
    def _determine_market(self, code: str) -> str:
        """根据股票代码判断市场"""
        if code.startswith(('60', '68')):
            return "上海证券交易所"
        elif code.startswith(('00', '30')):
            return "深圳证券交易所"
        elif code.startswith('8'):
            return "北京证券交易所"
        else:
            return "未知市场"
    
    def _get_full_symbol(self, code: str) -> str:
        """
        Get the full ticker

        Args:
            code: 6 stock code

        Returns:
            Full normalized code, or original code if unrecognized (make sure not empty)
        """
        # Make sure code is not empty
        if not code:
            return ""

        # normalize to string
        code = str(code).strip()

        # Determine the exchange based on the code prefix
        if code.startswith(('60', '68', '90')):  # Shanghai Stock Exchange (added B shares starting with 90)
            return f"{code}.SS"
        elif code.startswith(('00', '30', '20')):  # Shenzhen Stock Exchange (added B shares starting with 20)
            return f"{code}.SZ"
        elif code.startswith(('8', '4', '92')):  # Beijing Stock Exchange (8/4 old number segment, 920 is the unified number segment from 2025-10)
            return f"{code}.BJ"
        else:
            # Unrecognized code, return original code (make sure it is not empty)
            return code if code else ""
    
    def _get_market_info(self, code: str) -> Dict[str, Any]:
        """获取市场信息"""
        if code.startswith(('60', '68')):
            return {
                "market_type": "CN",
                "exchange": "SSE",
                "exchange_name": "上海证券交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }
        elif code.startswith(('00', '30')):
            return {
                "market_type": "CN",
                "exchange": "SZSE", 
                "exchange_name": "深圳证券交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }
        elif code.startswith(('8', '4', '92')):
            return {
                "market_type": "CN",
                "exchange": "BSE",
                "exchange_name": "北京证券交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }
        else:
            return {
                "market_type": "CN",
                "exchange": "UNKNOWN",
                "exchange_name": "未知交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }
    
    async def _get_all_market_spot_data(self) -> Optional[pd.DataFrame]:
        """
        Get market-wide snapshot data (internal method)
        
        Returns:
            Market-wide snapshot DataFrame, returned on failure None
        """
        if not self.connected:
            return None
        
        # Retry logic
        max_retries = 2
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                # Give priority to using the Sina Finance interface (more stable and less likely to be blocked)
                def fetch_spot_data_sina():
                    import time
                    time.sleep(0.3)  # Add delay to avoid frequency throttling
                    return self.ak.stock_zh_a_spot()

                try:
                    spot_df = await asyncio.to_thread(fetch_spot_data_sina)
                    logger.debug("✅ Use Sina Finance interface to obtain full market data")
                    return spot_df
                except Exception as e:
                    logger.warning(f"⚠️ 新浪财经接口失败: {e}，尝试东方财富接口...")
                    # Return to Oriental Wealth Interface
                    def fetch_spot_data_em():
                        import time
                        time.sleep(0.5)
                        return self.ak.stock_zh_a_spot_em()
                    spot_df = await asyncio.to_thread(fetch_spot_data_em)
                    logger.debug("✅ Use the Oriental Wealth Interface to obtain full market data")
                    return spot_df

            except Exception as e:
                logger.warning(f"⚠️ Failed to obtain market-wide snapshot (try {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"❌ Failed to obtain a market-wide snapshot. The maximum number of retries has been reached.: {e}")
                    return None
        
        return None
    
    async def get_batch_stock_quotes(self, codes: List[str], return_all: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Get real-time stock quotes in batches (optimized version: get a snapshot of the entire market at once)

        Prioritize using the Sina Finance interface (more stable), and fall back to the Oriental Wealth interface in case of failure

        Args:
            codes: Stock code list
            return_all: If True, returns full market data (ignoring the codes parameter)

        Returns:
            Mapping dictionary from stock code to market data
        """
        if not self.connected:
            return {}

        # Retry logic
        max_retries = 2
        retry_delay = 1  # seconds

        for attempt in range(max_retries):
            try:
                if return_all:
                    logger.debug(f"📊 Get real-time market information... (try {attempt + 1}/{max_retries})")
                else:
                    logger.debug(f"📊 批量获取 {len(codes)} 只股票的实时行情... (尝试 {attempt + 1}/{max_retries})")

                # Get a market-wide snapshot using internal methods
                spot_df = await self._get_all_market_spot_data()
                
                if spot_df is None or spot_df.empty:
                    logger.warning("⚠️ 全市场快照为空")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    return {}

                # 🔥 Prepare time-related variables in advance (to avoid scope problems)
                if return_all:
                    cn_tz = timezone(timedelta(hours=8))
                    now_cn = datetime.now(cn_tz)
                    trade_date_str = now_cn.strftime("%Y-%m-%d")
                    updated_at_str = now_cn.isoformat()
                    last_sync_utc = datetime.now(timezone.utc)
                
                # Build a code-to-quote mapping
                quotes_map = {}
                
                if return_all:
                    # 🔥 Return to full market data
                    codes_set = set()  # Empty set, matches all stocks
                    code_mapping = {}  # Empty map, matches all stocks
                else:
                    codes_set = set(codes)
                    # Build code mapping table (supports prefixed code matching)
                    # For example:sh600000 -> 600000, sz000001 -> 000001
                    code_mapping = {}
                    for code in codes:
                        code_mapping[code] = code  # original code
                        # Add possible prefix variations
                        for prefix in ['sh', 'sz', 'bj']:
                            code_mapping[f"{prefix}{code}"] = code

                for _, row in spot_df.iterrows():
                    raw_code = str(row.get("代码", ""))

                    # Try matching code (supports prefix and without prefix)
                    matched_code = None
                    if return_all:
                        # Return the whole market data and use it directly after cleaning the code.
                        matched_code = raw_code.replace("sh", "").replace("sz", "").replace("bj", "")
                    elif raw_code in code_mapping:
                        matched_code = code_mapping[raw_code]
                    elif raw_code in codes_set:
                        matched_code = raw_code

                    if matched_code:
                        quotes_data = {
                            "name": str(row.get("名称", f"股票{matched_code}")),
                            "price": self._safe_float(row.get("最新价", 0)),
                            "change": self._safe_float(row.get("涨跌额", 0)),
                            "change_percent": self._safe_float(row.get("涨跌幅", 0)),
                            "volume": self._safe_int(row.get("成交量", 0)),
                            "amount": self._safe_float(row.get("成交额", 0)),
                            "open": self._safe_float(row.get("今开", 0)),
                            "high": self._safe_float(row.get("最高", 0)),
                            "low": self._safe_float(row.get("最低", 0)),
                            "pre_close": self._safe_float(row.get("昨收", 0)),
                            # 🔥 New: Financial indicator fields
                            "turnover_rate": self._safe_float(row.get("换手率", None)),  # Turnover rate (%)
                            "volume_ratio": self._safe_float(row.get("量比", None)),  # Quantity ratio
                            "pe": self._safe_float(row.get("市盈率-动态", None)),  # Dynamic P/E Ratio
                            "pb": self._safe_float(row.get("市净率", None)),  # price to book ratio
                            "total_mv": self._safe_float(row.get("总市值", None)),  # Total market value (yuan)
                            "circ_mv": self._safe_float(row.get("流通市值", None)),  # Circulation market value (yuan)
                        }

                        # Convert to standardized dictionary (using matched codes)
                        quote_dict = {
                            "code": matched_code,
                            "symbol": matched_code,
                            "name": quotes_data.get("name", f"股票{matched_code}"),
                            "price": float(quotes_data.get("price", 0)),
                            "change": float(quotes_data.get("change", 0)),
                            "change_percent": float(quotes_data.get("change_percent", 0)),
                            "volume": int(quotes_data.get("volume", 0)),
                            "amount": float(quotes_data.get("amount", 0)),
                            "pre_close": float(quotes_data.get("pre_close", 0)),
                            # 🔥 New: Financial indicator fields
                            "turnover_rate": quotes_data.get("turnover_rate"),  # Turnover rate (%)
                            "volume_ratio": quotes_data.get("volume_ratio"),  # Quantity ratio
                            "pe": quotes_data.get("pe"),  # Dynamic P/E Ratio
                            "pe_ttm": quotes_data.get("pe"),  # TTM P/E ratio (same as dynamic P/E ratio)
                            "pb": quotes_data.get("pb"),  # price to book ratio
                            "total_mv": quotes_data.get("total_mv") / 1e8 if quotes_data.get("total_mv") else None,  # Total market capitalization (converted to 100 million yuan)
                            "circ_mv": quotes_data.get("circ_mv") / 1e8 if quotes_data.get("circ_mv") else None,  # Circulation market capitalization (converted into 100 million yuan)
                            # extension fields
                            "full_symbol": self._get_full_symbol(matched_code),
                            "market_info": self._get_market_info(matched_code),
                            "data_source": "akshare",
                            "last_sync": last_sync_utc if return_all else datetime.now(timezone.utc),
                            "sync_status": "success"
                        }
                        
                        # 🔥 Field name processing: decide which field name to use based on the return_all parameter
                        if return_all:
                            # When returning full market data, use open/high/low (consistent with the single stock interface)
                            quote_dict["open"] = float(quotes_data.get("open", 0))
                            quote_dict["high"] = float(quotes_data.get("high", 0))
                            quote_dict["low"] = float(quotes_data.get("low", 0))
                            quote_dict["close"] = quote_dict["price"]  # close Field
                            quote_dict["current_price"] = quote_dict["price"]  # current_price Field
                            quote_dict["pct_chg"] = quote_dict["change_percent"]  # pct_chg Field
                            quote_dict["trade_date"] = trade_date_str
                            quote_dict["updated_at"] = updated_at_str
                        else:
                            # When obtaining in batches, use open_price/high_price/low_price (to maintain compatibility)
                            quote_dict["open_price"] = float(quotes_data.get("open", 0))
                            quote_dict["high_price"] = float(quotes_data.get("high", 0))
                            quote_dict["low_price"] = float(quotes_data.get("low", 0))
                        
                        quotes_map[matched_code] = quote_dict

                if return_all:
                    found_count = len(quotes_map)
                    logger.debug(f"✅ 全市场数据获取完成: 共 {found_count} 只股票")
                else:
                    found_count = len(quotes_map)
                    missing_count = len(codes) - found_count
                    logger.debug(f"✅ 批量获取完成: 找到 {found_count} 只, 未找到 {missing_count} 只")

                    # Record stocks not found
                    if missing_count > 0:
                        missing_codes = codes_set - set(quotes_map.keys())
                        if missing_count <= 10:
                            logger.debug(f"⚠️ 未找到行情的股票: {list(missing_codes)}")
                        else:
                            logger.debug(f"⚠️ 未找到行情的股票: {list(missing_codes)[:10]}... (共{missing_count}只)")

                return quotes_map

            except Exception as e:
                logger.warning(f"⚠️ Failed to obtain real-time quotes in batches (try {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"❌ Failed to obtain real-time market information in batches. The maximum number of retries has been reached.: {e}")
                    return {}

    async def get_stock_quotes(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time quotes for individual stocks

        🔥 Strategy: Use the stock_bid_ask_em interface to obtain real-time quotes for a single stock
        - Advantages: Only obtain single stock data, fast, no waste of resources
        - Applicable scenario: Manual synchronization of a single stock

        Args:
            code: Stock code

        Returns:
            Standardized market data
        """
        if not self.connected:
            return None

        # 🔥 Add a retry mechanism to handle network connection errors
        max_retries = 3
        retry_delay = 1.0  # Initial delay 1 second
        
        for attempt in range(max_retries):
            try:
                logger.info(f"📈 使用 stock_bid_ask_em 接口获取 {code} 实时行情... (尝试 {attempt + 1}/{max_retries})")

                # 🔥 Use the stock_bid_ask_em interface to obtain real-time quotes of a single stock
                def fetch_bid_ask():
                    return self.ak.stock_bid_ask_em(symbol=code)

                bid_ask_df = await asyncio.to_thread(fetch_bid_ask)

                # 🔥 Print raw return data
                logger.info(f"📊 stock_bid_ask_em Return data type: {type(bid_ask_df)}")
                if bid_ask_df is not None:
                    logger.info(f"📊 DataFrame shape: {bid_ask_df.shape}")
                    logger.info(f"📊 DataFrame columns: {list(bid_ask_df.columns)}")
                    logger.info(f"📊 DataFrame complete data:\n{bid_ask_df.to_string()}")

                if bid_ask_df is None or bid_ask_df.empty:
                    logger.warning(f"⚠️ 未找到{code}的行情数据")
                    return None

                # Convert DataFrame to Dictionary
                data_dict = dict(zip(bid_ask_df['item'], bid_ask_df['value']))
                logger.info(f"📊 转换后的字典: {data_dict}")

                # Convert to standardized dictionary
                # 🔥 Note: The field name must be consistent with the query field in app/routers/stocks.py
                # The front-end query uses high/low/open, not high_price/low_price/open_price

                # 🔥 Get the current date (UTC+8) 
                cn_tz = timezone(timedelta(hours=8))
                now_cn = datetime.now(cn_tz)
                trade_date = now_cn.strftime("%Y-%m-%d")  # Format:2025-11-05

                # 🔥 Volume unit conversion: lots → shares (1 lot = 100 shares)
                volume_in_lots = self._safe_int(data_dict.get("总手", 0))  # Unit: hand
                volume_in_shares = volume_in_lots * 100  # Unit: Share

                quotes = {
                    "code": code,
                    "symbol": code,
                    "name": f"股票{code}",  # stock_bid_ask_em Does not return stock name
                    "price": self._safe_float(data_dict.get("最新", 0)),
                    "close": self._safe_float(data_dict.get("最新", 0)),  # 🔥 close field (same as price)
                    "current_price": self._safe_float(data_dict.get("最新", 0)),  # 🔥 current_price Fields (compatible with old data)
                    "change": self._safe_float(data_dict.get("涨跌", 0)),
                    "change_percent": self._safe_float(data_dict.get("涨幅", 0)),
                    "pct_chg": self._safe_float(data_dict.get("涨幅", 0)),  # 🔥 pct_chg Fields (compatible with old data)
                    "volume": volume_in_shares,  # 🔥 Unit: Share (converted)
                    "amount": self._safe_float(data_dict.get("金额", 0)),  # Unit: Yuan
                    "open": self._safe_float(data_dict.get("今开", 0)),  # 🔥 Use open instead open_price
                    "high": self._safe_float(data_dict.get("最高", 0)),  # 🔥 Use high instead high_price
                    "low": self._safe_float(data_dict.get("最低", 0)),  # 🔥 Use low instead low_price
                    "pre_close": self._safe_float(data_dict.get("昨收", 0)),
                    # 🔥 New: Financial indicator fields
                    "turnover_rate": self._safe_float(data_dict.get("换手", 0)),  # Turnover rate (%)
                    "volume_ratio": self._safe_float(data_dict.get("量比", 0)),  # Quantity ratio
                    "pe": None,  # stock_bid_ask_em Does not return P/E ratio
                    "pe_ttm": None,
                    "pb": None,  # stock_bid_ask_em Does not return price-to-book ratio
                    "total_mv": None,  # stock_bid_ask_em Does not return total market capitalization
                    "circ_mv": None,  # stock_bid_ask_em Does not return circulating market value
                    # 🔥 New: transaction date and update time
                    "trade_date": trade_date,  # Transaction date (format: 2025-11-05)
                    "updated_at": now_cn.isoformat(),  # Update time (ISO format, with time zone)
                    # extension fields
                    "full_symbol": self._get_full_symbol(code),
                    "market_info": self._get_market_info(code),
                    "data_source": "akshare",
                    "last_sync": datetime.now(timezone.utc),
                    "sync_status": "success"
                }

                logger.info(f"✅ {code} 实时行情获取成功: 最新价={quotes['price']}, 涨跌幅={quotes['change_percent']}%, 成交量={quotes['volume']}, 成交额={quotes['amount']}")
                return quotes

            except Exception as e:
                error_str = str(e)
                error_type = type(e).__name__
                
                # 🔥 Check if it is a network connection error (retryable error)
                is_connection_error = (
                    'Connection' in error_type or
                    'RemoteDisconnected' in error_type or
                    'Connection aborted' in error_str or
                    'Empty reply from server' in error_str or
                    'Remote end closed connection' in error_str or
                    'ProtocolError' in error_type
                )
                
                if is_connection_error and attempt < max_retries - 1:
                    # Network connection error, please wait and try again.
                    wait_time = retry_delay * (attempt + 1)  # Incremental wait time:1s, 2s, 3s
                    logger.warning(f"⚠️ 获取{code}实时行情连接失败 (尝试 {attempt + 1}/{max_retries}): {error_str}")
                    logger.info(f"⏳ 等待 {wait_time:.1f} 秒后重试...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Non-connection error or maximum retries reached
                    if attempt >= max_retries - 1:
                        logger.error(f"❌ 获取{code}实时行情失败，已达最大重试次数 ({max_retries}): {e}")
                        # 🔥 Fall back to the batch interface to obtain full market data (to avoid wasting interface calls)
                        logger.info(f"🔄 Try using the batch interface to obtain real-time market information (including {code}) ...")
                        try:
                            # 🔥 Use the get_batch_stock_quotes method to set return_all=True Get full market data
                            all_quotes_map = await self.get_batch_stock_quotes([code], return_all=True)
                            
                            if not all_quotes_map:
                                logger.warning("⚠️ 批量接口返回空数据")
                                return None
                            
                            # Find target stocks
                            target_quotes = None
                            for clean_code, quotes_data in all_quotes_map.items():
                                if clean_code == code:
                                    target_quotes = quotes_data.copy()
                                    break
                            
                            if target_quotes:
                                # 🔥 Unified field names: The batch interface returns open_price/high_price/low_price, which needs to be converted to open/high/low
                                if 'open_price' in target_quotes:
                                    target_quotes['open'] = target_quotes.pop('open_price')
                                if 'high_price' in target_quotes:
                                    target_quotes['high'] = target_quotes.pop('high_price')
                                if 'low_price' in target_quotes:
                                    target_quotes['low'] = target_quotes.pop('low_price')
                                
                                # 🔥 Make sure the close field exists (same as price)
                                if 'close' not in target_quotes and 'price' in target_quotes:
                                    target_quotes['close'] = target_quotes['price']
                                # 🔥 Make sure current_price field exists (compatible with old data)
                                if 'current_price' not in target_quotes and 'price' in target_quotes:
                                    target_quotes['current_price'] = target_quotes['price']
                                # 🔥 Ensure pct_chg field exists (compatible with old data)
                                if 'pct_chg' not in target_quotes and 'change_percent' in target_quotes:
                                    target_quotes['pct_chg'] = target_quotes['change_percent']
                                
                                # 🔥 Unify field names for all market data
                                for clean_code, quotes_data in all_quotes_map.items():
                                    if 'open_price' in quotes_data:
                                        quotes_data['open'] = quotes_data.pop('open_price')
                                    if 'high_price' in quotes_data:
                                        quotes_data['high'] = quotes_data.pop('high_price')
                                    if 'low_price' in quotes_data:
                                        quotes_data['low'] = quotes_data.pop('low_price')
                                    if 'close' not in quotes_data and 'price' in quotes_data:
                                        quotes_data['close'] = quotes_data['price']
                                    if 'current_price' not in quotes_data and 'price' in quotes_data:
                                        quotes_data['current_price'] = quotes_data['price']
                                    if 'pct_chg' not in quotes_data and 'change_percent' in quotes_data:
                                        quotes_data['pct_chg'] = quotes_data['change_percent']
                                    
                                    # Add transaction date and update time if not already available
                                    if 'trade_date' not in quotes_data:
                                        cn_tz = timezone(timedelta(hours=8))
                                        now_cn = datetime.now(cn_tz)
                                        quotes_data['trade_date'] = now_cn.strftime("%Y-%m-%d")
                                        quotes_data['updated_at'] = now_cn.isoformat()
                                
                                # 🔥 Add a special tag to indicate that this is obtained through the batch interface and contains full market data
                                target_quotes['_batch_data'] = all_quotes_map  # Contains full market data
                                target_quotes['_from_batch'] = True  # Mark source
                                
                                logger.info(f"✅ 通过批量接口成功获取 {code} 实时行情: 最新价={target_quotes.get('price')}, 涨跌幅={target_quotes.get('change_percent')}%")
                                logger.info(f"📊 批量接口同时获取到 {len(all_quotes_map)} 只股票的行情数据，将批量更新到数据库")
                                return target_quotes
                            else:
                                logger.warning(f"⚠️ 批量接口中未找到 {code} 的行情数据")
                                return None
                        except Exception as fallback_error:
                            logger.error(f"❌ 批量接口获取 {code} 实时行情也失败: {fallback_error}", exc_info=True)
                            return None
                    else:
                        logger.error(f"❌ 获取{code}实时行情失败: {e}", exc_info=True)
                        return None
        
        return None
    
    async def _get_realtime_quotes_data(self, code: str) -> Dict[str, Any]:
        """获取实时行情数据"""
        try:
            # method 1: Get real-time A-share quotes
            def fetch_spot_data():
                return self.ak.stock_zh_a_spot_em()

            try:
                spot_df = await asyncio.to_thread(fetch_spot_data)

                if spot_df is not None and not spot_df.empty:
                    # Find corresponding stocks
                    stock_data = spot_df[spot_df['代码'] == code]

                    if not stock_data.empty:
                        row = stock_data.iloc[0]

                        # Analyze market data
                        return {
                            "name": str(row.get("名称", f"股票{code}")),
                            "price": self._safe_float(row.get("最新价", 0)),
                            "change": self._safe_float(row.get("涨跌额", 0)),
                            "change_percent": self._safe_float(row.get("涨跌幅", 0)),
                            "volume": self._safe_int(row.get("成交量", 0)),
                            "amount": self._safe_float(row.get("成交额", 0)),
                            "open": self._safe_float(row.get("今开", 0)),
                            "high": self._safe_float(row.get("最高", 0)),
                            "low": self._safe_float(row.get("最低", 0)),
                            "pre_close": self._safe_float(row.get("昨收", 0)),
                            # 🔥 New: Financial indicator fields
                            "turnover_rate": self._safe_float(row.get("换手率", None)),  # Turnover rate (%)
                            "volume_ratio": self._safe_float(row.get("量比", None)),  # Quantity ratio
                            "pe": self._safe_float(row.get("市盈率-动态", None)),  # Dynamic P/E Ratio
                            "pb": self._safe_float(row.get("市净率", None)),  # price to book ratio
                            "total_mv": self._safe_float(row.get("总市值", None)),  # Total market value (yuan)
                            "circ_mv": self._safe_float(row.get("流通市值", None)),  # Circulation market value (yuan)
                        }
            except Exception as e:
                logger.debug(f"获取{code}A股实时行情失败: {e}")

            # method 2: Try to get real-time data of a single stock
            def fetch_individual_spot():
                return self.ak.stock_zh_a_hist(symbol=code, period="daily", adjust="")

            try:
                hist_df = await asyncio.to_thread(fetch_individual_spot)
                if hist_df is not None and not hist_df.empty:
                    # Take the latest day's data as the current market price
                    latest_row = hist_df.iloc[-1]
                    return {
                        "name": f"股票{code}",
                        "price": self._safe_float(latest_row.get("收盘", 0)),
                        "change": 0,  # Historical data cannot calculate the increase or decrease.
                        "change_percent": self._safe_float(latest_row.get("涨跌幅", 0)),
                        "volume": self._safe_int(latest_row.get("成交量", 0)),
                        "amount": self._safe_float(latest_row.get("成交额", 0)),
                        "open": self._safe_float(latest_row.get("开盘", 0)),
                        "high": self._safe_float(latest_row.get("最高", 0)),
                        "low": self._safe_float(latest_row.get("最低", 0)),
                        "pre_close": self._safe_float(latest_row.get("收盘", 0))
                    }
            except Exception as e:
                logger.debug(f"获取{code}历史数据作为行情失败: {e}")

            return {}

        except Exception as e:
            logger.debug(f"获取{code}实时行情数据失败: {e}")
            return {}
    
    def _safe_float(self, value: Any) -> float:
        """安全转换为浮点数"""
        try:
            if pd.isna(value) or value is None:
                return 0.0
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    
    def _safe_int(self, value: Any) -> int:
        """安全转换为整数"""
        try:
            if pd.isna(value) or value is None:
                return 0
            return int(float(value))
        except (ValueError, TypeError):
            return 0
    
    def _safe_str(self, value: Any) -> str:
        """安全转换为字符串"""
        try:
            if pd.isna(value) or value is None:
                return ""
            return str(value)
        except:
            return ""

    def _safe_optional_float(self, value: Any) -> Optional[float]:
        """Safe conversion to nullable floating point number."""
        try:
            if value is None or pd.isna(value):
                return None
            if isinstance(value, str):
                text = value.strip().replace(",", "")
                if not text or text.lower() in {"none", "nan", "nat", "null", "-", "--"}:
                    return None
                return float(text)
            return float(value)
        except (ValueError, TypeError):
            return None

    def _convert_market_cap_to_yi(self, value: Any) -> Optional[float]:
        """Convert market capitalization in yuan units to 100 million yuan."""
        numeric_value = self._safe_optional_float(value)
        if numeric_value is None:
            return None
        return numeric_value / 100000000

    def _normalize_security_code(self, value: Any) -> str:
        """Normalize security symbols from different sources into a 6-digit string."""
        text = self._safe_str(value).strip()
        if not text:
            return ""
        if "." in text:
            text = text.split(".", 1)[0]
        digits_only = "".join(character for character in text if character.isdigit())
        if digits_only:
            return digits_only.zfill(6)
        return text

    def _normalize_basic_date(self, value: Any) -> str:
        """Format date values from different sources into YYYY-MM-DD."""
        if value is None or pd.isna(value):
            return ""

        if isinstance(value, (datetime, pd.Timestamp)):
            return pd.Timestamp(value).strftime("%Y-%m-%d")

        if isinstance(value, (int, float)):
            number = int(value)
            if number <= 0:
                return ""
            if number >= 100000000000:
                return datetime.fromtimestamp(number / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            if number >= 1000000000:
                return datetime.fromtimestamp(number, tz=timezone.utc).strftime("%Y-%m-%d")
            if len(str(number)) == 8:
                text = str(number)
                return f"{text[:4]}-{text[4:6]}-{text[6:]}"

        text = self._safe_str(value).strip()
        if not text or text.lower() in {"none", "nan", "nat", "null", "-", "--"}:
            return ""
        if text.isdigit() and len(text) == 8:
            return f"{text[:4]}-{text[4:6]}-{text[6:]}"

        normalized = pd.to_datetime(text, errors="coerce")
        if pd.isna(normalized):
            return ""
        return normalized.strftime("%Y-%m-%d")

    def _normalize_exchange_name(self, value: Any) -> str:
        """Unify exchange identifiers from different sources into Chinese exchange names."""
        text = self._safe_str(value).strip().upper()
        if not text:
            return ""
        if text in {"SZ", "SZSE"} or "深交所" in text or "深圳" in text:
            return "深圳证券交易所"
        if text in {"SH", "SSE", "SS"} or "上交所" in text or "上海" in text:
            return "上海证券交易所"
        if text in {"BJ", "BSE"} or "北交所" in text or "北京" in text:
            return "北京证券交易所"
        return self._safe_str(value).strip()

    def _extract_board_from_market_label(self, value: Any) -> str:
        """Extract sector labels from market descriptions."""
        text = self._safe_str(value).strip()
        if not text:
            return ""
        if "科创板" in text:
            return "科创板"
        if "创业板" in text:
            return "创业板"
        if "中小板" in text:
            return "中小板"
        if "北交所" in text or "北京" in text:
            return "北交所"
        if "主板" in text or "深交所" in text or "上交所" in text:
            return "主板"
        return ""

    def _determine_board(self, code: str) -> str:
        """Infer sectors based on stock symbols."""
        code = str(code).strip()
        if code.startswith("68"):
            return "科创板"
        if code.startswith("30"):
            return "创业板"
        if code.startswith("002"):
            return "中小板"
        if code.startswith(("8", "4", "90")):
            return "北交所"
        if code.startswith(("60", "00")):
            return "主板"
        return "未知"

    def _get_xueqiu_symbol(self, code: str) -> str:
        """Generate stock symbols used by the Snowball interface."""
        code = str(code).strip()
        if code.startswith(("60", "68", "90")):
            return f"SH{code}"
        if code.startswith(("00", "30", "20")):
            return f"SZ{code}"
        if code.startswith(("8", "4")):
            return f"BJ{code}"
        return code

    def _get_akshare_cn_symbol(self, code: str) -> str:
        """Generate sh/sz/bj prefix codes for some A-share interfaces of AKShare."""
        code = str(code).strip()
        if code.startswith(('60', '68', '90')):
            return f"sh{code}"
        if code.startswith(('00', '30', '20')):
            return f"sz{code}"
        if code.startswith(('8', '4')):
            return f"bj{code}"
        return code

    async def _get_historical_data_tx_fallback(
        self,
        code: str,
        start_date: str,
        end_date: str,
        period: str = "daily"
    ) -> Optional[pd.DataFrame]:
        """Use Tencent s historical interface as a backup of AK s daily historical data."""
        if period != "daily":
            return None

        symbol = self._get_akshare_cn_symbol(code)

        def fetch_historical_data():
            return self.ak.stock_zh_a_hist_tx(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )

        hist_df = await asyncio.to_thread(fetch_historical_data)
        if hist_df is None or hist_df.empty:
            return None

        hist_df = hist_df.copy()
        if 'date' in hist_df.columns:
            hist_df['date'] = pd.to_datetime(hist_df['date'], errors='coerce')
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            hist_df = hist_df[(hist_df['date'] >= start_dt) & (hist_df['date'] <= end_dt)]

        if hist_df.empty:
            return None

        if 'pre_close' not in hist_df.columns and 'close' in hist_df.columns and 'date' in hist_df.columns:
            hist_df = hist_df.sort_values('date').reset_index(drop=True)
            hist_df['pre_close'] = hist_df['close'].shift(1)

        return hist_df

    async def _get_historical_data_sina_fallback(
        self,
        code: str,
        start_date: str,
        end_date: str,
        period: str = "daily"
    ) -> Optional[pd.DataFrame]:
        """Use the Sina historical interface as a backup of AK daily historical data."""
        if period != "daily":
            return None

        symbol = self._get_akshare_cn_symbol(code)

        def fetch_historical_data():
            return self.ak.stock_zh_a_daily(
                symbol=symbol,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"
            )

        hist_df = await asyncio.to_thread(fetch_historical_data)
        if hist_df is None or hist_df.empty:
            return None

        hist_df = hist_df.copy()
        if 'date' in hist_df.columns:
            hist_df['date'] = pd.to_datetime(hist_df['date'], errors='coerce')
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            hist_df = hist_df[(hist_df['date'] >= start_dt) & (hist_df['date'] <= end_dt)]

        if hist_df.empty:
            return None

        if 'pre_close' not in hist_df.columns and 'close' in hist_df.columns and 'date' in hist_df.columns:
            hist_df = hist_df.sort_values('date').reset_index(drop=True)
            hist_df['pre_close'] = hist_df['close'].shift(1)

        return hist_df

    async def get_historical_data(
        self,
        code: str,
        start_date: str,
        end_date: str,
        period: str = "daily"
    ) -> Optional[pd.DataFrame]:
        """
        Get historical market data

        Args:
            code: Stock code
            start_date: start date (YYYY-MM-DD)
            end_date: end date (YYYY-MM-DD)
            period: cycle (daily, weekly, monthly)

        Returns:
            Historical market data DataFrame
        """
        if not self.connected:
            return None

        try:
            logger.debug(f"📊 获取{code}历史数据: {start_date} 到 {end_date}")

            # Convert periodic format
            period_map = {
                "daily": "daily",
                "weekly": "weekly",
                "monthly": "monthly"
            }
            ak_period = period_map.get(period, "daily")

            # Format date
            start_date_formatted = start_date.replace('-', '')
            end_date_formatted = end_date.replace('-', '')

            # Check the time span, if it is more than 2 years, get it in batches
            from datetime import datetime, timedelta
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            days_diff = (end_dt - start_dt).days

            # If the time span exceeds 2 years (730 days), obtain it in batches
            if days_diff > 730:
                logger.info(f"⚠️ {code} 时间跨度过大({days_diff}天)，分批获取数据...")
                return await self._get_historical_data_in_batches(
                    code, start_date, end_date, period
                )

            primary_error = None

            # Get historical data (with retry)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    def fetch_historical_data():
                        return self.ak.stock_zh_a_hist(
                            symbol=code,
                            period=ak_period,
                            start_date=start_date_formatted,
                            end_date=end_date_formatted,
                            adjust="qfq"  # Former restoration of rights
                        )

                    hist_df = await asyncio.to_thread(fetch_historical_data)

                    if hist_df is None or hist_df.empty:
                        logger.warning(f"⚠️ {code}历史数据为空")
                        return None

                    # Standardized column names
                    hist_df = self._standardize_historical_columns(hist_df, code)

                    logger.debug(f"✅ {code}历史数据获取成功: {len(hist_df)}条记录")
                    return hist_df

                except RuntimeError as runtime_error:
                    # 🔥 Detect event loop closing error (Ctrl+C when exiting)
                    if "shutdown" in str(runtime_error).lower() or "closed" in str(runtime_error).lower():
                        logger.warning(f"⚠️ [AKShare API call] The event loop has been closed and stopped getting data: {code}")
                        self._event_loop_closed = True
                        return None
                    # Other RuntimeError, keep trying again
                    primary_error = runtime_error
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2
                        logger.warning(f"⚠️ {code} 第{attempt + 1}次尝试失败（RuntimeError），{wait_time}秒后重试: {runtime_error}")
                        await asyncio.sleep(wait_time)
                    else:
                        raise
                except Exception as retry_error:
                    primary_error = retry_error
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 2  # 2 seconds, 4 seconds, 6 seconds
                        logger.warning(f"⚠️ {code} 第{attempt + 1}次尝试失败，{wait_time}秒后重试: {retry_error}")
                        await asyncio.sleep(wait_time)
                    else:
                        raise

        except Exception as e:
            error_msg = str(e)
            # 🔥 Detecting event loop shutdown errors
            if "shutdown" in error_msg.lower() or "event loop is closed" in error_msg.lower():
                logger.warning(f"⚠️ [AKShare] 事件循环已关闭，停止获取 {code} 的历史数据")
                self._event_loop_closed = True
                return None
            elif "Connection aborted" in error_msg or "RemoteDisconnected" in error_msg:
                logger.warning(f"⚠️ {code} Dongcai history interface network abnormality, try to fall back to Sina/Tencent history interface")
                fallback_strategies = [
                    ("新浪", self._get_historical_data_sina_fallback),
                    ("腾讯", self._get_historical_data_tx_fallback),
                ]
                for fallback_name, fallback_loader in fallback_strategies:
                    try:
                        fallback_df = await fallback_loader(code, start_date, end_date, period)
                        if fallback_df is not None and not fallback_df.empty:
                            logger.info(f"✅ {code} {fallback_name}历史接口回退成功: {len(fallback_df)}条记录")
                            fallback_df = self._standardize_historical_columns(fallback_df, code)
                            return fallback_df
                    except Exception as fallback_error:
                        logger.warning(f"⚠️ {code} {fallback_name}历史接口回退失败: {fallback_error}")

                message = f"{code} The network connection is interrupted. It is recommended to try again later or reduce the time range."
                logger.error(f"❌ {message}")
                raise AKShareNetworkError(message) from (primary_error or e)
            else:
                logger.error(f"❌ 获取{code}历史数据失败: {e}")
            return None

    async def _get_historical_data_in_batches(
        self,
        code: str,
        start_date: str,
        end_date: str,
        period: str = "daily"
    ) -> Optional[pd.DataFrame]:
        """
        Obtain historical data in batches (for situations where the time span is too large)

        Args:
            code: Stock code
            start_date: start date (YYYY-MM-DD)
            end_date: end date (YYYY-MM-DD)
            period: cycle

        Returns:
            Combined historical data DataFrame
        """
        from datetime import datetime, timedelta
        import pandas as pd

        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')

            # Get 1 year of data for each batch
            batch_size_days = 365
            all_data = []

            current_start = start_dt
            while current_start < end_dt:
                current_end = min(current_start + timedelta(days=batch_size_days), end_dt)

                batch_start_str = current_start.strftime('%Y-%m-%d')
                batch_end_str = current_end.strftime('%Y-%m-%d')

                logger.debug(f"📊 {code} 分批获取: {batch_start_str} 到 {batch_end_str}")

                # Recursive call (batching will not be triggered again because of the time span<730 days)
                batch_df = await self.get_historical_data(
                    code, batch_start_str, batch_end_str, period
                )

                if batch_df is not None and not batch_df.empty:
                    all_data.append(batch_df)

                # Sleep between batches to avoid requesting too quickly
                await asyncio.sleep(1.0)

                current_start = current_end + timedelta(days=1)

            # Merge all batch data
            if all_data:
                merged_df = pd.concat(all_data, ignore_index=True)
                # Remove duplicates and sort
                merged_df = merged_df.drop_duplicates(subset=['date']).sort_values('date')
                logger.info(f"✅ {code} 分批获取完成: 共{len(merged_df)}条记录")
                return merged_df
            else:
                logger.warning(f"⚠️ {code} 分批获取未获得任何数据")
                return None

        except Exception as e:
            if isinstance(e, AKShareNetworkError):
                raise
            logger.error(f"❌ {code} 分批获取失败: {e}")
            return None

    def _standardize_historical_columns(self, df: pd.DataFrame, code: str) -> pd.DataFrame:
        """标准化历史数据列名"""
        try:
            # Standardized column name mapping
            column_mapping = {
                '日期': 'date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount',
                '振幅': 'amplitude',
                '涨跌幅': 'change_percent',
                '涨跌额': 'change',
                '换手率': 'turnover'
            }

            # Rename columns
            df = df.rename(columns=column_mapping)

            # Add standard fields
            df['code'] = code
            df['full_symbol'] = self._get_full_symbol(code)

            # Ensure date format
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])

            # Data type conversion
            numeric_columns = ['open', 'close', 'high', 'low', 'volume', 'amount']
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            return df

        except Exception as e:
            logger.error(f"标准化{code}历史数据列名失败: {e}")
            return df

    async def get_financial_data(self, code: str) -> Dict[str, Any]:
        """
        Get financial data

        Args:
            code: Stock code

        Returns:
            Financial Data Dictionary
        """
        if not self.connected:
            return {}

        try:
            logger.debug(f"💰 获取{code}财务数据...")

            financial_data = {}

            # 1. Get key financial indicators
            try:
                def fetch_financial_abstract():
                    return self.ak.stock_financial_abstract(symbol=code)

                main_indicators = await asyncio.to_thread(fetch_financial_abstract)
                if main_indicators is not None and not main_indicators.empty:
                    financial_data['main_indicators'] = main_indicators.to_dict('records')
                    logger.debug(f"✅ {code}主要财务指标获取成功")
            except Exception as e:
                logger.debug(f"获取{code}主要财务指标失败: {e}")

            # 2. Get balance sheet
            try:
                def fetch_balance_sheet():
                    return self.ak.stock_balance_sheet_by_report_em(symbol=code)

                balance_sheet = await asyncio.to_thread(fetch_balance_sheet)
                if balance_sheet is not None and not balance_sheet.empty:
                    financial_data['balance_sheet'] = balance_sheet.to_dict('records')
                    logger.debug(f"✅ {code}资产负债表获取成功")
            except Exception as e:
                logger.debug(f"获取{code}资产负债表失败: {e}")

            # 3. Get income statement
            try:
                def fetch_income_statement():
                    return self.ak.stock_profit_sheet_by_report_em(symbol=code)

                income_statement = await asyncio.to_thread(fetch_income_statement)
                if income_statement is not None and not income_statement.empty:
                    financial_data['income_statement'] = income_statement.to_dict('records')
                    logger.debug(f"✅ {code}利润表获取成功")
            except Exception as e:
                logger.debug(f"获取{code}利润表失败: {e}")

            # 4. Get cash flow statement
            try:
                def fetch_cash_flow():
                    return self.ak.stock_cash_flow_sheet_by_report_em(symbol=code)

                cash_flow = await asyncio.to_thread(fetch_cash_flow)
                if cash_flow is not None and not cash_flow.empty:
                    financial_data['cash_flow'] = cash_flow.to_dict('records')
                    logger.debug(f"✅ {code}现金流量表获取成功")
            except Exception as e:
                logger.debug(f"获取{code}现金流量表失败: {e}")

            if financial_data:
                logger.debug(f"✅ {code}财务数据获取完成: {len(financial_data)}个数据集")
            else:
                logger.warning(f"⚠️ {code}未获取到任何财务数据")

            return financial_data

        except Exception as e:
            logger.error(f"❌ 获取{code}财务数据失败: {e}")
            return {}

    async def get_market_status(self) -> Dict[str, Any]:
        """
        Get market status information

        Returns:
            market status information
        """
        try:
            # AKShare No direct market status API, returns basic information
            now = datetime.now()

            # Simple trading time judgment
            is_trading_time = (
                now.weekday() < 5 and  # working day
                ((9 <= now.hour < 12) or (13 <= now.hour < 15))  # trading hours
            )

            return {
                "market_status": "open" if is_trading_time else "closed",
                "current_time": now.isoformat(),
                "data_source": "akshare",
                "trading_day": now.weekday() < 5
            }

        except Exception as e:
            logger.error(f"❌ 获取市场状态失败: {e}")
            return {
                "market_status": "unknown",
                "current_time": datetime.now().isoformat(),
                "data_source": "akshare",
                "error": str(e)
            }

    def get_stock_news_sync(self, symbol: str = None, limit: int = 10) -> Optional[pd.DataFrame]:
        """
        Get stock news (synchronized version, return original DataFrame)

        Args:
            symbol: Stock code, get market news when None
            limit: Return quantity limit

        Returns:
            News DataFrame or None
        """
        if not self.is_available():
            return None

        try:
            import akshare as ak
            import json
            import time

            if symbol:
                # Get individual stock news
                self.logger.debug(f"📰 Get AKShare stock news: {symbol}")

                # Standardized stock code
                symbol_6 = symbol.zfill(6)

                # Get Oriental Fortune stock news and add a retry mechanism
                max_retries = 3
                retry_delay = 1  # seconds
                news_df = None

                for attempt in range(max_retries):
                    try:
                        news_df = ak.stock_news_em(symbol=symbol_6)
                        break  # If successful, jump out of the retry loop
                    except json.JSONDecodeError as e:
                        if attempt < max_retries - 1:
                            self.logger.warning(f"⚠️ {symbol} 第{attempt+1}次获取新闻失败(JSON解析错误)，{retry_delay}秒后重试...")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # exponential backoff
                        else:
                            self.logger.error(f"❌ {symbol} Failed to get news(JSON Parse error): {e}")
                            return None
                    except Exception as e:
                        if attempt < max_retries - 1:
                            self.logger.warning(f"⚠️ {symbol} 第{attempt+1}次获取新闻失败: {e}，{retry_delay}秒后重试...")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            raise

                if news_df is not None and not news_df.empty:
                    self.logger.info(f"✅ {symbol} AKShare新闻获取成功: {len(news_df)} 条")
                    return news_df.head(limit) if limit else news_df
                else:
                    self.logger.warning(f"⚠️ {symbol} AKShare news data not obtained")
                    return None
            else:
                # Get market news
                self.logger.debug("📰 Get AKShare market news")
                news_df = ak.news_cctv()

                if news_df is not None and not news_df.empty:
                    self.logger.info(f"✅ AKShare市场新闻获取成功: {len(news_df)} 条")
                    return news_df.head(limit) if limit else news_df
                else:
                    self.logger.warning("⚠️ AKShare market news data not obtained")
                    return None

        except Exception as e:
            self.logger.error(f"❌ AKShare Failed to get news: {e}")
            return None

    async def get_stock_news(self, symbol: str = None, limit: int = 10) -> Optional[List[Dict[str, Any]]]:
        """
        Get stock news (asynchronous version, returns a structured list)

        Args:
            symbol: Stock code, get market news when None
            limit: Return quantity limit

        Returns:
            News list
        """
        if not self.is_available():
            return None

        try:
            import akshare as ak
            import json
            import os

            if symbol:
                # Get individual stock news
                self.logger.debug(f"📰 Get AKShare stock news: {symbol}")

                # Standardized stock code
                symbol_6 = symbol.zfill(6)

                # Detect whether you are in a Docker environment
                is_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER') == 'true'

                # Get Oriental Fortune stock news and add a retry mechanism
                max_retries = 3
                retry_delay = 1  # seconds
                news_df = None

                # If in a Docker environment, try using curl_cffi to call directly API
                if is_docker:
                    try:
                        from curl_cffi import requests as curl_requests
                        self.logger.debug(f"🐳 Detect Docker environment, use curl_cffi to call directly API")
                        news_df = await asyncio.to_thread(
                            self._get_stock_news_direct,
                            symbol=symbol_6,
                            limit=limit
                        )
                        if news_df is not None and not news_df.empty:
                            self.logger.info(f"✅ {symbol} Docker The environment directly calls the API successfully")
                        else:
                            self.logger.warning(f"⚠️ {symbol} Docker The environment fails to directly call the API and falls back to AKShare")
                            news_df = None  # Fallback to AKShare
                    except ImportError:
                        self.logger.warning(f"⚠️ curl_cffi Not installed, fallback to AKShare")
                        news_df = None
                    except Exception as e:
                        self.logger.warning(f"⚠️ {symbol} Docker The environment directly calls the API exception.: {e}, Fallback to AKShare")
                        news_df = None

                # If the direct call fails or is not in the Docker environment, use AKShare
                if news_df is None:
                    for attempt in range(max_retries):
                        try:
                            news_df = await asyncio.to_thread(
                                ak.stock_news_em,
                                symbol=symbol_6
                            )
                            break  # If successful, jump out of the retry loop
                        except json.JSONDecodeError as e:
                            if attempt < max_retries - 1:
                                self.logger.warning(f"⚠️ {symbol} 第{attempt+1}次获取新闻失败(JSON解析错误)，{retry_delay}秒后重试...")
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2  # exponential backoff
                            else:
                                self.logger.error(f"❌ {symbol} Failed to get news(JSON Parse error): {e}")
                                return []
                        except KeyError as e:
                            # Oriental Fortune Network interface changes or anti-crawler interception, the returned field structure changes
                            if str(e) == "'cmsArticleWebOld'":
                                self.logger.error(f"❌ {symbol} AKShare News interface returns data structure exception: missing 'cmsArticleWebOld' Field")
                                self.logger.error(f"   This is usually because:1) Anti-crawler interception 2) Interface changes 3) network problems")
                                self.logger.error(f"   Suggestion: Check if the AKShare version is up to date (Current requirements >=1.17.86)")
                                # Return an empty list to avoid program crashes
                                return []
                            else:
                                if attempt < max_retries - 1:
                                    self.logger.warning(f"⚠️ {symbol} 第{attempt+1}次获取新闻失败(字段错误): {e}，{retry_delay}秒后重试...")
                                    await asyncio.sleep(retry_delay)
                                    retry_delay *= 2
                                else:
                                    self.logger.error(f"❌ {symbol} Failed to get news(Field error): {e}")
                                    return []
                        except Exception as e:
                            if attempt < max_retries - 1:
                                self.logger.warning(f"⚠️ {symbol} 第{attempt+1}次获取新闻失败: {e}，{retry_delay}秒后重试...")
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2
                            else:
                                raise

                if news_df is not None and not news_df.empty:
                    news_list = []

                    for _, row in news_df.head(limit).iterrows():
                        title = str(row.get('新闻标题', '') or row.get('标题', ''))
                        content = str(row.get('新闻内容', '') or row.get('内容', ''))
                        summary = str(row.get('新闻摘要', '') or row.get('摘要', ''))

                        news_item = {
                            "symbol": symbol,
                            "title": title,
                            "content": content,
                            "summary": summary,
                            "url": str(row.get('新闻链接', '') or row.get('链接', '')),
                            "source": str(row.get('文章来源', '') or row.get('来源', '') or '东方财富'),
                            "author": str(row.get('作者', '') or ''),
                            "publish_time": self._parse_news_time(row.get('发布时间', '') or row.get('时间', '')),
                            "category": self._classify_news(content, title),
                            "sentiment": self._analyze_news_sentiment(content, title),
                            "sentiment_score": self._calculate_sentiment_score(content, title),
                            "keywords": self._extract_keywords(content, title),
                            "importance": self._assess_news_importance(content, title),
                            "data_source": "akshare"
                        }

                        # Filter news with empty titles
                        if news_item["title"]:
                            news_list.append(news_item)

                    self.logger.info(f"✅ {symbol} AKShare新闻获取成功: {len(news_list)} 条")
                    return news_list
                else:
                    self.logger.warning(f"⚠️ {symbol} AKShare news data not obtained")
                    return []
            else:
                # Get market news
                self.logger.debug("📰 Get AKShare market news")

                try:
                    # Get financial news
                    news_df = await asyncio.to_thread(
                        ak.news_cctv,
                        limit=limit
                    )

                    if news_df is not None and not news_df.empty:
                        news_list = []

                        for _, row in news_df.iterrows():
                            title = str(row.get('title', '') or row.get('标题', ''))
                            content = str(row.get('content', '') or row.get('内容', ''))
                            summary = str(row.get('brief', '') or row.get('摘要', ''))

                            news_item = {
                                "title": title,
                                "content": content,
                                "summary": summary,
                                "url": str(row.get('url', '') or row.get('链接', '')),
                                "source": str(row.get('source', '') or row.get('来源', '') or 'CCTV财经'),
                                "author": str(row.get('author', '') or ''),
                                "publish_time": self._parse_news_time(row.get('time', '') or row.get('时间', '')),
                                "category": self._classify_news(content, title),
                                "sentiment": self._analyze_news_sentiment(content, title),
                                "sentiment_score": self._calculate_sentiment_score(content, title),
                                "keywords": self._extract_keywords(content, title),
                                "importance": self._assess_news_importance(content, title),
                                "data_source": "akshare"
                            }

                            if news_item["title"]:
                                news_list.append(news_item)

                        self.logger.info(f"✅ AKShare市场新闻获取成功: {len(news_list)} 条")
                        return news_list

                except Exception as e:
                    self.logger.debug(f"CCTV新闻获取失败: {e}")

                return []

        except Exception as e:
            self.logger.error(f"❌ Failed to get AKShare news symbol={symbol}: {e}")
            return None

    def _parse_news_time(self, time_str: str) -> Optional[datetime]:
        """解析新闻时间"""
        if not time_str:
            return datetime.utcnow()

        try:
            # Try multiple time formats
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
                "%Y/%m/%d %H:%M:%S",
                "%Y/%m/%d %H:%M",
                "%Y/%m/%d",
                "%m-%d %H:%M",
                "%m/%d %H:%M"
            ]

            for fmt in formats:
                try:
                    parsed_time = datetime.strptime(str(time_str), fmt)

                    # If there is only month and day, add the year
                    if fmt in ["%m-%d %H:%M", "%m/%d %H:%M"]:
                        current_year = datetime.now().year
                        parsed_time = parsed_time.replace(year=current_year)

                    return parsed_time
                except ValueError:
                    continue

            # If all else fails, return the current time
            self.logger.debug(f"⚠️ 无法解析新闻时间: {time_str}")
            return datetime.utcnow()

        except Exception as e:
            self.logger.debug(f"解析新闻时间异常: {e}")
            return datetime.utcnow()

    def _analyze_news_sentiment(self, content: str, title: str) -> str:
        """
        Analyze news sentiment

        Args:
            content: News content
            title: News headline

        Returns:
            emotion type: positive/negative/neutral
        """
        text = f"{title} {content}".lower()

        # Positive keywords
        positive_keywords = [
            '利好', '上涨', '增长', '盈利', '突破', '创新高', '买入', '推荐',
            '看好', '乐观', '强势', '大涨', '飙升', '暴涨', '涨停', '涨幅',
            '业绩增长', '营收增长', '净利润增长', '扭亏为盈', '超预期',
            '获批', '中标', '签约', '合作', '并购', '重组', '分红', '回购'
        ]

        # negative keywords
        negative_keywords = [
            '利空', '下跌', '亏损', '风险', '暴跌', '卖出', '警告', '下调',
            '看空', '悲观', '弱势', '大跌', '跳水', '暴跌', '跌停', '跌幅',
            '业绩下滑', '营收下降', '净利润下降', '亏损', '低于预期',
            '被查', '违规', '处罚', '诉讼', '退市', '停牌', '商誉减值'
        ]

        positive_count = sum(1 for keyword in positive_keywords if keyword in text)
        negative_count = sum(1 for keyword in negative_keywords if keyword in text)

        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        else:
            return 'neutral'

    def _calculate_sentiment_score(self, content: str, title: str) -> float:
        """
        Calculate sentiment score

        Args:
            content: News content
            title: News headline

        Returns:
            sentiment score: -1.0 Arrive 1.0
        """
        text = f"{title} {content}".lower()

        # Positive keyword weight
        positive_keywords = {
            '涨停': 1.0, '暴涨': 0.9, '大涨': 0.8, '飙升': 0.8,
            '创新高': 0.7, '突破': 0.6, '上涨': 0.5, '增长': 0.4,
            '利好': 0.6, '看好': 0.5, '推荐': 0.5, '买入': 0.6
        }

        # Negative keyword weight
        negative_keywords = {
            '跌停': -1.0, '暴跌': -0.9, '大跌': -0.8, '跳水': -0.8,
            '创新低': -0.7, '破位': -0.6, '下跌': -0.5, '下滑': -0.4,
            '利空': -0.6, '看空': -0.5, '卖出': -0.6, '警告': -0.5
        }

        score = 0.0

        # Calculate positivity score
        for keyword, weight in positive_keywords.items():
            if keyword in text:
                score += weight

        # Calculate negativity score
        for keyword, weight in negative_keywords.items():
            if keyword in text:
                score += weight

        # normalized to [-1.0, 1.0]
        return max(-1.0, min(1.0, score / 3.0))

    def _extract_keywords(self, content: str, title: str) -> List[str]:
        """
        Extract keywords

        Args:
            content: News content
            title: News headline

        Returns:
            keyword list
        """
        text = f"{title} {content}"

        # Common financial keywords
        common_keywords = [
            '股票', '公司', '市场', '投资', '业绩', '财报', '政策', '行业',
            '分析', '预测', '涨停', '跌停', '上涨', '下跌', '盈利', '亏损',
            '并购', '重组', '分红', '回购', '增持', '减持', '融资', 'IPO',
            '监管', '央行', '利率', '汇率', 'GDP', '通胀', '经济', '贸易',
            '科技', '互联网', '新能源', '医药', '房地产', '金融', '制造业'
        ]

        keywords = []
        for keyword in common_keywords:
            if keyword in text:
                keywords.append(keyword)

        return keywords[:10]  # Returns up to 10 keywords

    def _assess_news_importance(self, content: str, title: str) -> str:
        """
        Assess news importance

        Args:
            content: News content
            title: News headline

        Returns:
            importance level: high/medium/low
        """
        text = f"{title} {content}".lower()

        # High importance keywords
        high_importance_keywords = [
            '业绩', '财报', '年报', '季报', '重大', '公告', '监管', '政策',
            '并购', '重组', '退市', '停牌', '涨停', '跌停', '暴涨', '暴跌',
            '央行', '证监会', '交易所', '违规', '处罚', '立案', '调查'
        ]

        # Medium importance keywords
        medium_importance_keywords = [
            '分析', '预测', '观点', '建议', '行业', '市场', '趋势', '机会',
            '研报', '评级', '目标价', '增持', '减持', '买入', '卖出',
            '合作', '签约', '中标', '获批', '分红', '回购'
        ]

        # Check high importance
        if any(keyword in text for keyword in high_importance_keywords):
            return 'high'

        # Check for medium importance
        if any(keyword in text for keyword in medium_importance_keywords):
            return 'medium'

        return 'low'

    def _classify_news(self, content: str, title: str) -> str:
        """
        Classified News

        Args:
            content: News content
            title: News headline

        Returns:
            News category
        """
        text = f"{title} {content}".lower()

        # company announcement
        if any(keyword in text for keyword in ['公告', '业绩', '财报', '年报', '季报']):
            return 'company_announcement'

        # policy news
        if any(keyword in text for keyword in ['政策', '监管', '央行', '证监会', '国务院']):
            return 'policy_news'

        # Industry news
        if any(keyword in text for keyword in ['行业', '板块', '产业', '领域']):
            return 'industry_news'

        # market news
        if any(keyword in text for keyword in ['市场', '指数', '大盘', '沪指', '深成指']):
            return 'market_news'

        # research report
        if any(keyword in text for keyword in ['研报', '分析', '评级', '目标价', '机构']):
            return 'research_report'

        return 'general'

    def is_event_loop_closed(self) -> bool:
        """
        Check if the event loop has been closed

        Returns:
            bool: Returns True if the event loop has been closed, otherwise False
        """
        return self._event_loop_closed

    async def get_pledge_detail(
        self,
        symbol: str = None,
        date: str = None,
    ) -> Optional[pd.DataFrame]:
        """
        Obtain detailed data on equity pledge

        Args:
            symbol: Stock code (6 digits, such as 600519)
            date: Query date (YYYYMMDD), Used for pledge ratio statistics

        Returns:
            DataFrame Contains pledge details
        """
        if not self.is_available():
            return None

        try:
            import akshare as ak

            if symbol:
                normalized = self._normalize_security_code(symbol)
                market_prefix = "sh" if normalized.startswith('6') else "sz"
                ak_symbol = f"{market_prefix}{normalized}"

                try:
                    df = await asyncio.to_thread(
                        ak.stock_gpzy_detail_em,
                        symbol=ak_symbol
                    )
                except AttributeError:
                    try:
                        df = await asyncio.to_thread(
                            ak.stock_pledge_detail,
                            symbol=normalized
                        )
                    except Exception:
                        df = None

                if df is not None and not df.empty:
                    self.logger.info(f"✅ 获取股权质押明细: {len(df)} 条 | symbol={symbol}")
                    return df
                return None
            else:
                if date:
                    date_clean = date.replace('-', '')
                    try:
                        df = await asyncio.to_thread(
                            ak.stock_gpzy_pledge_ratio_em,
                            date=date_clean
                        )
                        if df is not None and not df.empty:
                            self.logger.info(f"✅ 获取全市场质押比例: {len(df)} 条 | date={date_clean}")
                            return df
                    except Exception:
                        pass
                return None

        except Exception as e:
            self.logger.error(f"❌ Failed to obtain equity pledge details: {e}")
            return None


# Global provider instance
_akshare_provider = None


def get_akshare_provider() -> AKShareProvider:
    """Get the global AKShare provider instance"""
    global _akshare_provider
    if _akshare_provider is None:
        _akshare_provider = AKShareProvider()
    return _akshare_provider
