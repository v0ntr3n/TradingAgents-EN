#!/usr/bin/env python3
"""
Stock data pre-acquisition and verification module
Used to verify the existence of a stock before starting the analysis process, and to pre-fetch and cache the necessary data
"""

import re
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('stock_validator')


class StockDataPreparationResult:
    """Stock data prefetch result class"""

    def __init__(self, is_valid: bool, stock_code: str, market_type: str = "",
                 stock_name: str = "", error_message: str = "", suggestion: str = "",
                 has_historical_data: bool = False, has_basic_info: bool = False,
                 data_period_days: int = 0, cache_status: str = ""):
        self.is_valid = is_valid
        self.stock_code = stock_code
        self.market_type = market_type
        self.stock_name = stock_name
        self.error_message = error_message
        self.suggestion = suggestion
        self.has_historical_data = has_historical_data
        self.has_basic_info = has_basic_info
        self.data_period_days = data_period_days
        self.cache_status = cache_status

    def to_dict(self) -> Dict:
        """Convert to dictionary format"""
        return {
            'is_valid': self.is_valid,
            'stock_code': self.stock_code,
            'market_type': self.market_type,
            'stock_name': self.stock_name,
            'error_message': self.error_message,
            'suggestion': self.suggestion,
            'has_historical_data': self.has_historical_data,
            'has_basic_info': self.has_basic_info,
            'data_period_days': self.data_period_days,
            'cache_status': self.cache_status
        }


# Stay backwards compatible
StockValidationResult = StockDataPreparationResult


class StockDataPreparer:
    """Stock data prefetch and validator"""

    def __init__(self, default_period_days: int = 30):
        self.timeout_seconds = 15  # Data acquisition timeout
        self.default_period_days = default_period_days  # Default historical data duration (days)
    
    def prepare_stock_data(self, stock_code: str, market_type: str = "auto",
                          period_days: int = None, analysis_date: str = None) -> StockDataPreparationResult:
        """
        Prefetch and validate stock data

        Args:
            stock_code: Stock code
            market_type: market type ("A shares", "Hong Kong stocks", "US stocks", "auto")
            period_days: Historical data duration (days), by default the value when the class is initialized is used
            analysis_date: Analysis date, default is today

        Returns:
            StockDataPreparationResult: Data preparation results
        """
        if period_days is None:
            period_days = self.default_period_days

        if analysis_date is None:
            analysis_date = datetime.now().strftime('%Y-%m-%d')

        logger.info(f"📊 [Data preparation] Start preparing stock data: {stock_code} (market: {market_type}, duration: {period_days}day)")

        # 1. Basic format validation
        format_result = self._validate_format(stock_code, market_type)
        if not format_result.is_valid:
            return format_result

        # 2. Automatic detection of market types
        if market_type == "auto":
            market_type = self._detect_market_type(stock_code)
            logger.debug(f"📊 [Data preparation] Automatic detection of market types: {market_type}")

        # 3. Prefetch data and validate
        return self._prepare_data_by_market(stock_code, market_type, period_days, analysis_date)
    
    def _validate_format(self, stock_code: str, market_type: str) -> StockDataPreparationResult:
        """Validate ticker format"""
        stock_code = stock_code.strip()
        
        if not stock_code:
            return StockDataPreparationResult(
                is_valid=False,
                stock_code=stock_code,
                error_message="Stock code cannot be empty",
                suggestion="Please enter a valid stock code"
            )

        if len(stock_code) > 10:
            return StockDataPreparationResult(
                is_valid=False,
                stock_code=stock_code,
                error_message="Stock code length cannot exceed 10 characters",
                suggestion="Please check the ticker format"
            )
        
        # Validate format based on market type
        if market_type == "A shares":
            if not re.match(r'^\d{6}$', stock_code):
                return StockDataPreparationResult(
                    is_valid=False,
                    stock_code=stock_code,
                    market_type="A shares",
                    error_message="A The stock code format is wrong, it should be 6 digits",
                    suggestion="Please enter the 6-digit A-share code, such as: 000001,600519"
                )
        elif market_type == "Hong Kong stocks":
            stock_code_upper = stock_code.upper()
            hk_format = re.match(r'^\d{4,5}\.HK$', stock_code_upper)
            digit_format = re.match(r'^\d{4,5}$', stock_code)

            if not (hk_format or digit_format):
                return StockDataPreparationResult(
                    is_valid=False,
                    stock_code=stock_code,
                    market_type="Hong Kong stocks",
                    error_message="Hong Kong stock code format error",
                    suggestion="Please enter 4-5 digits in .HK format (eg: 0700.HK) or 4-5 digits (eg: 0700)"
                )
        elif market_type == "US stocks":
            if not re.match(r'^[A-Z]{1,5}$', stock_code.upper()):
                return StockDataPreparationResult(
                    is_valid=False,
                    stock_code=stock_code,
                    market_type="US stocks",
                    error_message="The format of the US stock code is wrong, it should be 1-5 letters",
                    suggestion="Please enter the US stock code with 1-5 characters, such as: AAPL,TSLA"
                )
        
        return StockDataPreparationResult(
            is_valid=True,
            stock_code=stock_code,
            market_type=market_type
        )
    
    def _detect_market_type(self, stock_code: str) -> str:
        """Automatic detection of market types"""
        stock_code = stock_code.strip().upper()
        
        # A Share: 6 digits
        if re.match(r'^\d{6}$', stock_code):
            return "A shares"
        
        # Hong Kong stocks: 4-5 digits.HK or pure 4-5 digits
        if re.match(r'^\d{4,5}\.HK$', stock_code) or re.match(r'^\d{4,5}$', stock_code):
            return "Hong Kong stocks"
        
        # US stocks: 1-5 letters
        if re.match(r'^[A-Z]{1,5}$', stock_code):
            return "US stocks"
        
        return "unknown"

    def _get_hk_network_limitation_suggestion(self) -> str:
        """Get detailed advice on Hong Kong stock network restrictions"""
        suggestions = [
            "🌐 Hong Kong stock data acquisition is restricted by network API, which is a common temporary problem",
            "",
            "💡 Solution:",
            "1. Wait 5-10 minutes and try again (API restrictions are usually lifted automatically)",
            "2. Check whether the network connection is stable",
            "3. If it is a well-known Hong Kong stock (such as Tencent 0700.HK, Alibaba 9988.HK), the code format is usually correct",
            "4. You can try using other time periods for analysis",
            "",
            "📋 Common Hong Kong stock code formats:",
            "• Tencent Holdings:0700.HK",
            "• Alibaba:9988.HK",
            "• Meituan:3690.HK",
            "• Xiaomi Group:1810.HK",
            "",
            "⏰ It is recommended to try again later or contact technical support for help"
        ]
        return "\n".join(suggestions)

    def _extract_hk_stock_name(self, stock_info, stock_code: str) -> str:
        """Extract stock names from Hong Kong stock information, supporting multiple formats"""
        if not stock_info:
            return "unknown"

        # Handling different types of return values
        if isinstance(stock_info, dict):
            # If it's a dictionary, try to extract names from common fields
            name_fields = ['name', 'longName', 'shortName', 'companyName', 'Company name', 'Stock name']
            for field in name_fields:
                if field in stock_info and stock_info[field]:
                    name = str(stock_info[field]).strip()
                    if name and name != "unknown":
                        return name

            # If the dictionary contains valid information but no name field, use the ticker
            if len(stock_info) > 0:
                return stock_code
            return "unknown"

        # Convert to string processing
        stock_info_str = str(stock_info)

        # method 1: standard format "Company name: XXX"
        if "Company name:" in stock_info_str:
            lines = stock_info_str.split('\n')
            for line in lines:
                if "Company name:" in line:
                    name = line.split(':')[1].strip()
                    if name and name != "unknown":
                        return name

        # method 2: Yahoo Finance Format detection
        # Log display: "✅ Yahoo Finance Successfully obtained Hong Kong stock information: 0700.HK -> TENCENT"
        if "Yahoo Finance Successfully obtained Hong Kong stock information" in stock_info_str:
            # Extract names from logs
            if " -> " in stock_info_str:
                parts = stock_info_str.split(" -> ")
                if len(parts) > 1:
                    name = parts[-1].strip()
                    if name and name != "unknown":
                        return name

        # method 3: Check if common company name keywords are included
        company_indicators = [
            "Limited", "Ltd", "Corporation", "Corp", "Inc", "Group",
            "Holdings", "Company", "Co", "Group", "holding", "Ltd."
        ]

        lines = stock_info_str.split('\n')
        for line in lines:
            line = line.strip()
            if any(indicator in line for indicator in company_indicators):
                # Try to extract company name
                if ":" in line:
                    potential_name = line.split(':')[-1].strip()
                    if potential_name and len(potential_name) > 2:
                        return potential_name
                elif len(line) > 2 and len(line) < 100:  # Reasonable company name length
                    return line

        # method 4: If the information looks valid but the name cannot be resolved, use the ticker
        if len(stock_info_str) > 50 and "❌" not in stock_info_str:
            # Message looks valid but name cannot be resolved, using code as name
            return stock_code

        return "unknown"

    def _prepare_data_by_market(self, stock_code: str, market_type: str,
                               period_days: int, analysis_date: str) -> StockDataPreparationResult:
        """Prefetch data based on market type"""
        logger.debug(f"📊 [Data preparation] Start with{market_type}stocks{stock_code}Prepare data")

        try:
            if market_type == "A shares":
                return self._prepare_china_stock_data(stock_code, period_days, analysis_date)
            elif market_type == "Hong Kong stocks":
                return self._prepare_hk_stock_data(stock_code, period_days, analysis_date)
            elif market_type == "US stocks":
                return self._prepare_us_stock_data(stock_code, period_days, analysis_date)
            else:
                return StockDataPreparationResult(
                    is_valid=False,
                    stock_code=stock_code,
                    market_type=market_type,
                    error_message=f"Unsupported market type: {market_type}",
                    suggestion="Please select the supported market type: A-shares, Hong Kong stocks, US stocks"
                )
        except Exception as e:
            logger.error(f"❌ [Data preparation] Data preparation exception: {e}")
            return StockDataPreparationResult(
                is_valid=False,
                stock_code=stock_code,
                market_type=market_type,
                error_message=f"An error occurred during data preparation: {str(e)}",
                suggestion="Please check your network connection or try again later"
            )

    async def _prepare_data_by_market_async(self, stock_code: str, market_type: str,
                                           period_days: int, analysis_date: str) -> StockDataPreparationResult:
        """Prefetch data based on market type (asynchronous version)"""
        logger.debug(f"📊 [Data preparation-asynchronous] Start with{market_type}stocks{stock_code}Prepare data")

        try:
            if market_type == "A shares":
                return await self._prepare_china_stock_data_async(stock_code, period_days, analysis_date)
            elif market_type == "Hong Kong stocks":
                return self._prepare_hk_stock_data(stock_code, period_days, analysis_date)
            elif market_type == "US stocks":
                return self._prepare_us_stock_data(stock_code, period_days, analysis_date)
            else:
                return StockDataPreparationResult(
                    is_valid=False,
                    stock_code=stock_code,
                    market_type=market_type,
                    error_message=f"Unsupported market type: {market_type}",
                    suggestion="Please select the supported market type: A-shares, Hong Kong stocks, US stocks"
                )
        except Exception as e:
            logger.error(f"❌ [Data preparation-asynchronous] Data preparation exception: {e}")
            return StockDataPreparationResult(
                is_valid=False,
                stock_code=stock_code,
                market_type=market_type,
                error_message=f"An error occurred during data preparation: {str(e)}",
                suggestion="Please check your network connection or try again later"
            )

    def _prepare_china_stock_data(self, stock_code: str, period_days: int,
                                 analysis_date: str) -> StockDataPreparationResult:
        """Pre-obtain A-share data, including database checking and automatic synchronization"""
        logger.info(f"📊 [A stock data] Start preparing{stock_code}data (duration: {period_days}day)")

        # Calculate date range (use extended date range, consistent with get_china_stock_data_unified)
        end_date = datetime.strptime(analysis_date, '%Y-%m-%d')

        # Get the configured lookback days (consistent with get_china_stock_data_unified)
        from app.core.config import settings
        lookback_days = getattr(settings, 'MARKET_ANALYST_LOOKBACK_DAYS', 365)

        # Use extended date ranges for data inspection and synchronization
        extended_start_date = end_date - timedelta(days=lookback_days)
        extended_start_date_str = extended_start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        logger.info(f"📅 [A stock data] actual data range: {extended_start_date_str} Arrive {end_date_str} ({lookback_days}day)")

        has_historical_data = False
        has_basic_info = False
        stock_name = "unknown"
        cache_status = ""
        data_synced = False

        try:
            # 1. Check if the data in the database exists and is up to date
            logger.debug(f"📊 [A stock data] Check the database{stock_code}data...")
            db_check_result = self._check_database_data(stock_code, extended_start_date_str, end_date_str)

            # 2. Automatically trigger synchronization if data does not exist or is not up to date
            if not db_check_result["has_data"] or not db_check_result["is_latest"]:
                logger.warning(f"⚠️ [A stock data] Database data is incomplete: {db_check_result['message']}")
                logger.info(f"🔄 [A stock data] Automatically trigger data synchronization: {stock_code}")

                # Sync using extended date range
                sync_result = self._trigger_data_sync_sync(stock_code, extended_start_date_str, end_date_str)
                if sync_result["success"]:
                    logger.info(f"✅ [A stock data] Data synchronization successful: {sync_result['message']}")
                    data_synced = True
                    cache_status += "Data has been synchronized; "
                else:
                    logger.warning(f"⚠️ [A stock data] Data synchronization failed: {sync_result['message']}")
                    # Keep trying to get data from the API
            else:
                logger.info(f"✅ [A stock data] Database data check passed: {db_check_result['message']}")
                cache_status += "Database data latest; "

            # 3. Get basic information
            logger.debug(f"📊 [A stock data] get{stock_code}Basic information...")
            from tradingagents.dataflows.interface import get_china_stock_info_unified

            stock_info = get_china_stock_info_unified(stock_code)

            if stock_info and "❌" not in stock_info and "Failed to obtain" not in stock_info:
                # Parse stock names
                if "Stock name:" in stock_info:
                    lines = stock_info.split('\n')
                    for line in lines:
                        if "Stock name:" in line:
                            stock_name = line.split(':')[1].strip()
                            break

                # Check if it is a valid stock name
                if stock_name != "unknown" and not stock_name.startswith(f"stocks{stock_code}"):
                    has_basic_info = True
                    logger.info(f"✅ [A stock data] Basic information obtained successfully: {stock_code} - {stock_name}")
                    cache_status += "Basic information has been cached; "
                else:
                    logger.warning(f"⚠️ [A stock data] Basic information is invalid: {stock_code}")
                    return StockDataPreparationResult(
                        is_valid=False,
                        stock_code=stock_code,
                        market_type="A shares",
                        error_message=f"Stock code {stock_code} Does not exist or the information is invalid",
                        suggestion="Please check whether the stock code is correct or confirm whether the stock is listed"
                    )
            else:
                logger.warning(f"⚠️ [A stock data] Unable to obtain basic information: {stock_code}")
                return StockDataPreparationResult(
                    is_valid=False,
                    stock_code=stock_code,
                    market_type="A shares",
                    error_message=f"Unable to get stock {stock_code} basic information",
                    suggestion="Please check whether the stock code is correct or confirm whether the stock is listed"
                )

            # 4. Get historical data (using extended date range)
            logger.debug(f"📊 [A stock data] get{stock_code}historical data ({extended_start_date_str} Arrive {end_date_str})...")
            from tradingagents.dataflows.interface import get_china_stock_data_unified

            historical_data = get_china_stock_data_unified(stock_code, extended_start_date_str, end_date_str)

            if historical_data and "❌" not in historical_data and "Failed to obtain" not in historical_data:
                # Looser data validity checks
                data_indicators = [
                    "opening price", "closing price", "highest price", "lowest price", "Volume",
                    "open", "close", "high", "low", "volume",
                    "Date", "date", "time", "time"
                ]

                has_valid_data = (
                    len(historical_data) > 50 and  # Reduce length requirements
                    any(indicator in historical_data for indicator in data_indicators)
                )

                if has_valid_data:
                    has_historical_data = True
                    logger.info(f"✅ [A stock data] Historical data obtained successfully: {stock_code} ({lookback_days}day)")
                    cache_status += f"Historical data has been cached({lookback_days}day); "
                else:
                    logger.warning(f"⚠️ [A stock data] Historical data is invalid: {stock_code}")
                    logger.debug(f"🔍 [A stock data] Data content preview: {historical_data[:200]}...")
                    return StockDataPreparationResult(
                        is_valid=False,
                        stock_code=stock_code,
                        market_type="A shares",
                        stock_name=stock_name,
                        has_basic_info=has_basic_info,
                        error_message=f"stocks {stock_code} historical data is invalid or insufficient",
                        suggestion="The stock may be a newly listed stock or the data source is temporarily unavailable. Please try again later."
                    )
            else:
                logger.warning(f"⚠️ [A stock data] Unable to obtain historical data: {stock_code}")
                return StockDataPreparationResult(
                    is_valid=False,
                    stock_code=stock_code,
                    market_type="A shares",
                    stock_name=stock_name,
                    has_basic_info=has_basic_info,
                    error_message=f"Unable to get stock {stock_code} historical data",
                    suggestion="Please check the network connection or data source configuration or try again later"
                )

            # 5. Data preparation successful
            logger.info(f"🎉 [A stock data] Data preparation completed: {stock_code} - {stock_name}")
            return StockDataPreparationResult(
                is_valid=True,
                stock_code=stock_code,
                market_type="A shares",
                stock_name=stock_name,
                has_historical_data=has_historical_data,
                has_basic_info=has_basic_info,
                data_period_days=lookback_days,  # Use actual days of data
                cache_status=cache_status.rstrip('; ')
            )

        except Exception as e:
            logger.error(f"❌ [A stock data] Data preparation failed: {e}")
            import traceback
            logger.debug(f"detailed error: {traceback.format_exc()}")
            return StockDataPreparationResult(
                is_valid=False,
                stock_code=stock_code,
                market_type="A shares",
                stock_name=stock_name,
                has_basic_info=has_basic_info,
                has_historical_data=has_historical_data,
                error_message=f"Data preparation failed: {str(e)}",
                suggestion="Please check network connection or data source configuration"
            )

    async def _prepare_china_stock_data_async(self, stock_code: str, period_days: int,
                                             analysis_date: str) -> StockDataPreparationResult:
        """Pre-fetch A-share data (asynchronous version), including database check and automatic synchronization"""
        logger.info(f"📊 [A Share data - asynchronous] Start preparing{stock_code}data (duration: {period_days}day)")

        # Calculate date range
        end_date = datetime.strptime(analysis_date, '%Y-%m-%d')
        from app.core.config import settings
        lookback_days = getattr(settings, 'MARKET_ANALYST_LOOKBACK_DAYS', 365)
        extended_start_date = end_date - timedelta(days=lookback_days)
        extended_start_date_str = extended_start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        logger.info(f"📅 [A Share data - asynchronous] actual data range: {extended_start_date_str} Arrive {end_date_str} ({lookback_days}day)")

        has_historical_data = False
        has_basic_info = False
        stock_name = "unknown"
        cache_status = ""

        try:
            # 1. Check if the data in the database exists and is up to date
            logger.debug(f"📊 [A Share data - asynchronous] Check the database{stock_code}data...")
            db_check_result = self._check_database_data(stock_code, extended_start_date_str, end_date_str)

            # 2. Automatically trigger synchronization (using asynchronous methods) if the data does not exist or is not up to date
            if not db_check_result["has_data"] or not db_check_result["is_latest"]:
                logger.warning(f"⚠️ [A Share data - asynchronous] Database data is incomplete: {db_check_result['message']}")
                logger.info(f"🔄 [A Share data - asynchronous] Automatically trigger data synchronization: {stock_code}")

                # 🔥 Synchronize data using asynchronous methods
                sync_result = await self._trigger_data_sync_async(stock_code, extended_start_date_str, end_date_str)
                if sync_result["success"]:
                    logger.info(f"✅ [A Share data - asynchronous] Data synchronization successful: {sync_result['message']}")
                    cache_status += "Data has been synchronized; "
                else:
                    logger.warning(f"⚠️ [A Share data - asynchronous] Data synchronization failed: {sync_result['message']}")
            else:
                logger.info(f"✅ [A Share data - asynchronous] Database data check passed: {db_check_result['message']}")
                cache_status += "Database data latest; "

            # 3. Get basic information (synchronous operation)
            logger.debug(f"📊 [A Share data - asynchronous] get{stock_code}Basic information...")
            from tradingagents.dataflows.interface import get_china_stock_info_unified
            stock_info = get_china_stock_info_unified(stock_code)

            if stock_info and "❌" not in stock_info and "Failed to obtain" not in stock_info:
                if "Stock name:" in stock_info:
                    lines = stock_info.split('\n')
                    for line in lines:
                        if "Stock name:" in line:
                            stock_name = line.split(':')[1].strip()
                            break

                if stock_name != "unknown" and not stock_name.startswith(f"stocks{stock_code}"):
                    has_basic_info = True
                    logger.info(f"✅ [A Share data - asynchronous] Basic information obtained successfully: {stock_code} - {stock_name}")
                    cache_status += "Basic information has been cached; "

            # 4. Get historical data (synchronous operation)
            logger.debug(f"📊 [A Share data - asynchronous] get{stock_code}historical data...")
            from tradingagents.dataflows.interface import get_china_stock_data_unified
            historical_data = get_china_stock_data_unified(stock_code, extended_start_date_str, end_date_str)

            if historical_data and "❌" not in historical_data and "Failed to obtain" not in historical_data:
                data_indicators = ["opening price", "closing price", "highest price", "lowest price", "Volume"]
                has_valid_data = (
                    len(historical_data) > 50 and
                    any(indicator in historical_data for indicator in data_indicators)
                )

                if has_valid_data:
                    has_historical_data = True
                    logger.info(f"✅ [A Share data - asynchronous] Historical data obtained successfully: {stock_code}")
                    cache_status += f"Historical data has been cached({lookback_days}day); "
                else:
                    return StockDataPreparationResult(
                        is_valid=False,
                        stock_code=stock_code,
                        market_type="A shares",
                        stock_name=stock_name,
                        has_basic_info=has_basic_info,
                        error_message=f"stocks {stock_code} historical data is invalid or insufficient",
                        suggestion="The stock may be a newly listed stock or the data source is temporarily unavailable. Please try again later."
                    )
            else:
                return StockDataPreparationResult(
                    is_valid=False,
                    stock_code=stock_code,
                    market_type="A shares",
                    stock_name=stock_name,
                    has_basic_info=has_basic_info,
                    error_message=f"Unable to get stock {stock_code} historical data",
                    suggestion="Please check the network connection or data source configuration or try again later"
                )

            # 5. Data preparation successful
            logger.info(f"🎉 [A Share data - asynchronous] Data preparation completed: {stock_code} - {stock_name}")
            return StockDataPreparationResult(
                is_valid=True,
                stock_code=stock_code,
                market_type="A shares",
                stock_name=stock_name,
                has_historical_data=has_historical_data,
                has_basic_info=has_basic_info,
                data_period_days=lookback_days,
                cache_status=cache_status.rstrip('; ')
            )

        except Exception as e:
            logger.error(f"❌ [A Share data - asynchronous] Data preparation failed: {e}")
            import traceback
            logger.debug(f"detailed error: {traceback.format_exc()}")
            return StockDataPreparationResult(
                is_valid=False,
                stock_code=stock_code,
                market_type="A shares",
                stock_name=stock_name,
                has_basic_info=has_basic_info,
                has_historical_data=has_historical_data,
                error_message=f"Data preparation failed: {str(e)}",
                suggestion="Please check network connection or data source configuration"
            )

    def _check_database_data(self, stock_code: str, start_date: str, end_date: str) -> Dict:
        """
        Check if the data in the database exists and is up to date

        Returns:
            Dict: {
                "has_data": bool,  # Is there data
                "is_latest": bool,  # Is it the latest (including the latest trading day)
                "record_count": int,  # Number of records
                "latest_date": str,  # Latest data date
                "message": str  # Check result message
            }
        """
        try:
            from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

            adapter = get_mongodb_cache_adapter()
            if not adapter.use_app_cache or adapter.db is None:
                return {
                    "has_data": False,
                    "is_latest": False,
                    "record_count": 0,
                    "latest_date": None,
                    "message": "MongoDB Caching is not enabled"
                }

            # Query historical data in the database
            df = adapter.get_historical_data(stock_code, start_date, end_date)

            if df is None or df.empty:
                return {
                    "has_data": False,
                    "is_latest": False,
                    "record_count": 0,
                    "latest_date": None,
                    "message": "There is no data in the database"
                }

            # Check data volume
            record_count = len(df)

            # Get latest data date
            if 'trade_date' in df.columns:
                latest_date = df['trade_date'].max()
            elif 'date' in df.columns:
                latest_date = df['date'].max()
            else:
                latest_date = None

            # Check if the most recent trading day is included
            from datetime import datetime, timedelta
            today = datetime.now()

            # Get the most recent trading day (considering weekends)
            recent_trade_date = today
            for i in range(5):  # Look back up to 5 days
                check_date = today - timedelta(days=i)
                if check_date.weekday() < 5:  # Monday to Friday
                    recent_trade_date = check_date
                    break

            recent_trade_date_str = recent_trade_date.strftime('%Y-%m-%d')

            # Determine whether the data is up to date (allow 1 day delay)
            is_latest = False
            if latest_date:
                latest_date_str = str(latest_date)[:10]  # Get the first 10 characters YYYY-MM-DD
                latest_dt = datetime.strptime(latest_date_str, '%Y-%m-%d')
                days_diff = (recent_trade_date - latest_dt).days
                is_latest = days_diff <= 1  # Allow 1 day delay

            message = f"found{record_count}records, latest date: {latest_date}"
            if not is_latest:
                message += f" (Need to update to{recent_trade_date_str}) "

            return {
                "has_data": True,
                "is_latest": is_latest,
                "record_count": record_count,
                "latest_date": str(latest_date) if latest_date else None,
                "message": message
            }

        except Exception as e:
            logger.error(f"❌ [Data check] Checking database data failed: {e}")
            return {
                "has_data": False,
                "is_latest": False,
                "record_count": 0,
                "latest_date": None,
                "message": f"Check failed: {str(e)}"
            }

    def _trigger_data_sync_sync(self, stock_code: str, start_date: str, end_date: str) -> Dict:
        """
        Trigger data synchronization (sync wrapper)
        Calling an asynchronous synchronization method in a synchronization context

        🔥 Compatible asyncio.to_thread() Call:
        - if in asyncio.to_thread() Run in the created thread and create a new event loop
        - avoid "attached to a different loop" Error
        """
        import asyncio

        try:
            # 🔥 Detect if there is a running event loop
            # If so, it means we are asyncio.to_thread() In the created thread, a new event loop needs to be created
            try:
                running_loop = asyncio.get_running_loop()
                # There is a running loop, indicating that it cannot be used in an asynchronous context. run_until_complete
                # Create a new event loop to run in a new thread
                logger.info(f"🔍 [Data synchronization] A running event loop is detected and a new event loop is created")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(
                        self._trigger_data_sync_async(stock_code, start_date, end_date)
                    )
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
            except RuntimeError:
                # There is no running loop, it is safe to get or create an event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                # Call an asynchronous method
                return loop.run_until_complete(
                    self._trigger_data_sync_async(stock_code, start_date, end_date)
                )
        except Exception as e:
            logger.error(f"❌ [Data synchronization] Synchronization wrapper failed: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Sync failed: {str(e)}",
                "synced_records": 0,
                "data_source": None
            }

    @staticmethod
    @asynccontextmanager
    async def _get_independent_sync_service(data_source: str):
        """
        Get a separate sync service instance (using a separate database connection)
        Ensure connections are automatically closed after use to avoid conflicts with UnifiedThreadPoolSyncService
        
        Args:
            data_source: Data source name ("tushare" or "akshare")
        
        Yields:
            Sync service instance (AKShareSyncService or TushareSyncService)
        """
        mongo_client = None
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            from app.core.config import settings
            import asyncio
            
            # 🔥 Create an independent database connection (bound to the current event loop)
            current_loop = asyncio.get_running_loop()
            mongo_client = AsyncIOMotorClient(settings.MONGO_URI)
            db = mongo_client[settings.MONGO_DB]
            
            # 🔥 Create a temporary service instance
            if data_source == "tushare":
                from app.worker.tushare_sync_service import TushareSyncService
                service = TushareSyncService()
                # Initialize the service using a separate connection
                service.db = db
                # Initialize provider (Tushare needs to be connected)
                await service.initialize()
            elif data_source == "akshare":
                from app.worker.akshare_sync_service import AKShareSyncService
                service = AKShareSyncService()
                # Initialize the service using a separate connection
                service.db = db
                # Initialize historical data service and news data service
                from app.services.historical_data_service import HistoricalDataService
                from app.services.news_data_service import NewsDataService
                service.historical_service = HistoricalDataService()
                service.historical_service.db = db
                service.historical_service.collection = service.historical_service.db.stock_daily_quotes
                await service.historical_service._ensure_indexes()
                
                service.news_service = NewsDataService()
                service.news_service.db = db
                
                # Initialize the AKShare provider (use a global singleton to ensure the monkey patch takes effect)
                from tradingagents.dataflows.providers.china.akshare import get_akshare_provider
                service.provider = get_akshare_provider()
                
                # test connection
                if not await service.provider.test_connection():
                    raise RuntimeError("❌ AKShare Connection failed, unable to start synchronization service")
            else:
                raise ValueError(f"Unsupported data source: {data_source}")
            
            logger.debug(f"🔄 Create an independent synchronization service instance: {data_source}")
            yield service
            
        finally:
            # 🔥 Make sure the connection is closed
            if mongo_client:
                try:
                    mongo_client.close()
                    logger.debug(f"🔄 Temporary database connection closed: {data_source}")
                except Exception as e:
                    logger.warning(f"⚠️ Error closing temporary database connection: {e}")

    async def _trigger_data_sync_async(self, stock_code: str, start_date: str, end_date: str) -> Dict:
        """
        Trigger data synchronization (asynchronous version, according to the data source priority configured in the database)
        Synchronized content includes: historical data, financial data, real-time market conditions

        Returns:
            Dict: {
                "success": bool,
                "message": str,
                "synced_records": int,
                "data_source": str,  # Data source used
                "historical_records": int,  # Number of historical data records
                "financial_synced": bool,  # Whether financial data is synchronized successfully
                "realtime_synced": bool  # Is the real-time market synchronization successful?
            }
        """
        try:
            logger.info(f"🔄 [Data synchronization] Start syncing{stock_code}data (historical+Finance+real time)...")

            # 1. Get data source priority from database
            priority_order = self._get_data_source_priority_for_sync(stock_code)
            logger.info(f"📊 [Data synchronization] Data source priority: {priority_order}")

            # 2. Try synchronization by priority
            last_error = None
            for data_source in priority_order:
                try:
                    logger.info(f"🔄 [Data synchronization] Try using data source: {data_source}")

                    # BaoStock Single stock synchronization is not supported and skipped
                    if data_source == "baostock":
                        logger.warning(f"⚠️ [Data synchronization] BaoStock Single stock synchronization is not supported and skipped")
                        last_error = f"{data_source}: Single stock synchronization is not supported"
                        continue

                    # 🔥 Use a separate synchronization service instance (to avoid conflicts with UnifiedThreadPoolSyncService)
                    # 🔥 Use a context manager to ensure connections are automatically closed after use
                    async with self._get_independent_sync_service(data_source) as service:
                        # Initialization result statistics
                        historical_records = 0
                        financial_synced = False
                        realtime_synced = False

                        # 2.1 Synchronize historical data
                        logger.info(f"📊 [Data synchronization] Synchronize historical data...")
                        hist_result = await service.sync_historical_data(
                            symbols=[stock_code],
                            start_date=start_date,
                            end_date=end_date,
                            incremental=False  # Full synchronization
                        )

                        if hist_result.get("success_count", 0) > 0:
                            historical_records = hist_result.get("total_records", 0)
                            logger.info(f"✅ [Data synchronization] Historical data synchronization successful: {historical_records}Article")
                        else:
                            errors = hist_result.get("errors", [])
                            error_msg = errors[0].get("error", "unknown error") if errors else "Sync failed"
                            logger.warning(f"⚠️ [Data synchronization] Historical data synchronization failed: {error_msg}")

                        # 2.2 Sync financial data
                        logger.info(f"📊 [Data synchronization] Sync financial data...")
                        try:
                            fin_result = await service.sync_financial_data(
                                symbols=[stock_code],
                                limit=20  # Get the latest 20 financial reports (about 5 years)
                            )

                            if fin_result.get("success_count", 0) > 0:
                                financial_synced = True
                                logger.info(f"✅ [Data synchronization] Financial data synchronization successful")
                            else:
                                logger.warning(f"⚠️ [Data synchronization] Financial data synchronization failed")
                        except Exception as e:
                            logger.warning(f"⚠️ [Data synchronization] Financial data synchronization exception: {e}")

                        # 2.3 Synchronize real-time quotes
                        logger.info(f"📊 [Data synchronization] Synchronize real-time quotes...")
                        try:
                            # For individual stocks, AKShare is more suitable for obtaining real-time quotes
                            if data_source == "tushare":
                                # Tushare The real-time market interface has limitations, use it instead AKShare
                                # 🔥 Use a separate AKShare service instance
                                async with self._get_independent_sync_service("akshare") as realtime_service:
                                    rt_result = await realtime_service.sync_realtime_quotes(
                                        symbols=[stock_code],
                                        force=True  # Enforce execution, skip transaction time check
                                    )

                                    if rt_result.get("success_count", 0) > 0:
                                        realtime_synced = True
                                        logger.info(f"✅ [Data synchronization] Real-time market synchronization successful")
                                    else:
                                        logger.warning(f"⚠️ [Data synchronization] Real-time market synchronization failed")
                            else:
                                rt_result = await service.sync_realtime_quotes(
                                    symbols=[stock_code],
                                    force=True  # Enforce execution, skip transaction time check
                                )

                                if rt_result.get("success_count", 0) > 0:
                                    realtime_synced = True
                                    logger.info(f"✅ [Data synchronization] Real-time market synchronization successful")
                                else:
                                    logger.warning(f"⚠️ [Data synchronization] Real-time market synchronization failed")
                        except Exception as e:
                            logger.warning(f"⚠️ [Data synchronization] Real-time market synchronization abnormality: {e}")

                        # Check the synchronization results (at least historical data must be successful)
                        if historical_records > 0:
                            message = f"Use{data_source}Synchronization successful: history{historical_records}Article"
                            if financial_synced:
                                message += ", financial data✓"
                            if realtime_synced:
                                message += ", Real-time quotes✓"

                            logger.info(f"✅ [Data synchronization] {message}")
                            return {
                                "success": True,
                                "message": message,
                                "synced_records": historical_records,
                                "data_source": data_source,
                                "historical_records": historical_records,
                                "financial_synced": financial_synced,
                                "realtime_synced": realtime_synced
                            }
                        else:
                            last_error = f"{data_source}: Historical data synchronization failed"
                            logger.warning(f"⚠️ [Data synchronization] {data_source}Sync failed: Historical data is empty")
                            # Continue to try the next data source

                except Exception as e:
                    last_error = f"{data_source}: {str(e)}"
                    logger.warning(f"⚠️ [Data synchronization] {data_source}Synchronization exception: {e}")
                    import traceback
                    logger.debug(f"detailed error: {traceback.format_exc()}")
                    # Continue to try the next data source
                    continue

            # All data sources fail
            message = f"Synchronization of all data sources failed with final error: {last_error}"
            logger.error(f"❌ [Data synchronization] {message}")
            return {
                "success": False,
                "message": message,
                "synced_records": 0,
                "data_source": None,
                "historical_records": 0,
                "financial_synced": False,
                "realtime_synced": False
            }

        except Exception as e:
            logger.error(f"❌ [Data synchronization] Failed to synchronize data: {e}")
            import traceback
            logger.debug(f"detailed error: {traceback.format_exc()}")
            return {
                "success": False,
                "message": f"Sync failed: {str(e)}",
                "synced_records": 0,
                "data_source": None,
                "historical_records": 0,
                "financial_synced": False,
                "realtime_synced": False
            }

    def _get_data_source_priority_for_sync(self, stock_code: str) -> list:
        """
        Get data source priority (for synchronization)

        Returns:
            list: List of data sources, sorted by priority ['tushare', 'akshare', 'baostock']
        """
        try:
            from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

            adapter = get_mongodb_cache_adapter()
            if adapter.use_app_cache and adapter.db is not None:
                # Using MongoDB Adapter Methods to Get Priority
                priority_order = adapter._get_data_source_priority(stock_code)
                logger.info(f"✅ [Data source priority] Get from database: {priority_order}")
                return priority_order
            else:
                logger.warning(f"⚠️ [Data source priority] MongoDB Not enabled, uses default order")
                return ['tushare', 'akshare', 'baostock']

        except Exception as e:
            logger.error(f"❌ [Data source priority] Failed to obtain: {e}")
            # Return to default order
            return ['tushare', 'akshare', 'baostock']

    def _prepare_hk_stock_data(self, stock_code: str, period_days: int,
                              analysis_date: str) -> StockDataPreparationResult:
        """Pre-obtain Hong Kong stock data"""
        logger.info(f"📊 [Hong Kong stock data] Start preparing{stock_code}data (duration: {period_days}day)")

        # Standardized Hong Kong stock code format
        if not stock_code.upper().endswith('.HK'):
            # Remove leading 0s, then pad to 4 digits
            clean_code = stock_code.lstrip('0') or '0'  # If all are 0, keep one 0
            formatted_code = f"{clean_code.zfill(4)}.HK"
            logger.debug(f"🔍 [Hong Kong stock data] Code formatting: {stock_code} → {formatted_code}")
        else:
            formatted_code = stock_code.upper()

        # Calculate date range
        end_date = datetime.strptime(analysis_date, '%Y-%m-%d')
        start_date = end_date - timedelta(days=period_days)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        logger.debug(f"📅 [Hong Kong stock data] date range: {start_date_str} → {end_date_str}")

        has_historical_data = False
        has_basic_info = False
        stock_name = "unknown"
        cache_status = ""

        try:
            # 1. Get basic information
            logger.debug(f"📊 [Hong Kong stock data] get{formatted_code}Basic information...")
            from tradingagents.dataflows.interface import get_hk_stock_info_unified

            stock_info = get_hk_stock_info_unified(formatted_code)

            if stock_info and "❌" not in stock_info and "not found" not in stock_info:
                # Parse stock names - supports multiple formats
                stock_name = self._extract_hk_stock_name(stock_info, formatted_code)

                if stock_name and stock_name != "unknown":
                    has_basic_info = True
                    logger.info(f"✅ [Hong Kong stock data] Basic information obtained successfully: {formatted_code} - {stock_name}")
                    cache_status += "Basic information has been cached; "
                else:
                    logger.warning(f"⚠️ [Hong Kong stock data] Basic information is invalid: {formatted_code}")
                    logger.debug(f"🔍 [Hong Kong stock data] Information content: {stock_info[:200]}...")
                    return StockDataPreparationResult(
                        is_valid=False,
                        stock_code=formatted_code,
                        market_type="Hong Kong stocks",
                        error_message=f"Hong Kong stock code {formatted_code} Does not exist or the information is invalid",
                        suggestion="Please check whether the Hong Kong stock code is correct, the format is as follows:0700.HK"
                    )
            else:
                # Check if it is a network restriction issue
                network_error_indicators = [
                    "Too Many Requests", "Rate limited", "Connection aborted",
                    "Remote end closed connection", "network connection", "timeout", "Limit"
                ]

                is_network_issue = any(indicator in str(stock_info) for indicator in network_error_indicators)

                if is_network_issue:
                    logger.warning(f"🌐 [Hong Kong stock data] Impact of network restrictions: {formatted_code}")
                    return StockDataPreparationResult(
                        is_valid=False,
                        stock_code=formatted_code,
                        market_type="Hong Kong stocks",
                        error_message=f"Access to Hong Kong stock data is affected by network restrictions",
                        suggestion=self._get_hk_network_limitation_suggestion()
                    )
                else:
                    logger.warning(f"⚠️ [Hong Kong stock data] Unable to obtain basic information: {formatted_code}")
                    return StockDataPreparationResult(
                        is_valid=False,
                        stock_code=formatted_code,
                        market_type="Hong Kong stocks",
                        error_message=f"Hong Kong stock code {formatted_code} May not exist or the data source may be temporarily unavailable",
                        suggestion="Please check whether the Hong Kong stock code is correct, the format is: 0700.HK, or try again later"
                    )

            # 2. Get historical data
            logger.debug(f"📊 [Hong Kong stock data] get{formatted_code}historical data ({start_date_str} Arrive {end_date_str})...")
            from tradingagents.dataflows.interface import get_hk_stock_data_unified

            historical_data = get_hk_stock_data_unified(formatted_code, start_date_str, end_date_str)

            if historical_data and "❌" not in historical_data and "Failed to obtain" not in historical_data:
                # Looser data validity checks
                data_indicators = [
                    "opening price", "closing price", "highest price", "lowest price", "Volume",
                    "open", "close", "high", "low", "volume",
                    "Date", "date", "time", "time"
                ]

                has_valid_data = (
                    len(historical_data) > 50 and  # Reduce length requirements
                    any(indicator in historical_data for indicator in data_indicators)
                )

                if has_valid_data:
                    has_historical_data = True
                    logger.info(f"✅ [Hong Kong stock data] Historical data obtained successfully: {formatted_code} ({period_days}day)")
                    cache_status += f"Historical data has been cached({period_days}day); "
                else:
                    logger.warning(f"⚠️ [Hong Kong stock data] Historical data is invalid: {formatted_code}")
                    logger.debug(f"🔍 [Hong Kong stock data] Data content preview: {historical_data[:200]}...")
                    return StockDataPreparationResult(
                        is_valid=False,
                        stock_code=formatted_code,
                        market_type="Hong Kong stocks",
                        stock_name=stock_name,
                        has_basic_info=has_basic_info,
                        error_message=f"Hong Kong stocks {formatted_code} historical data is invalid or insufficient",
                        suggestion="The stock may be a newly listed stock or the data source is temporarily unavailable. Please try again later."
                    )
            else:
                # Check if it is a network restriction issue
                network_error_indicators = [
                    "Too Many Requests", "Rate limited", "Connection aborted",
                    "Remote end closed connection", "network connection", "timeout", "Limit"
                ]

                is_network_issue = any(indicator in str(historical_data) for indicator in network_error_indicators)

                if is_network_issue:
                    logger.warning(f"🌐 [Hong Kong stock data] Historical data acquisition is limited by the network: {formatted_code}")
                    return StockDataPreparationResult(
                        is_valid=False,
                        stock_code=formatted_code,
                        market_type="Hong Kong stocks",
                        stock_name=stock_name,
                        has_basic_info=has_basic_info,
                        error_message=f"Access to Hong Kong stock historical data is affected by network restrictions",
                        suggestion=self._get_hk_network_limitation_suggestion()
                    )
                else:
                    logger.warning(f"⚠️ [Hong Kong stock data] Unable to obtain historical data: {formatted_code}")
                    return StockDataPreparationResult(
                        is_valid=False,
                        stock_code=formatted_code,
                        market_type="Hong Kong stocks",
                        stock_name=stock_name,
                        has_basic_info=has_basic_info,
                        error_message=f"Unable to obtain Hong Kong stocks {formatted_code} historical data",
                        suggestion="The data source may be temporarily unavailable, please try again later or contact technical support"
                    )

            # 3. Data preparation successful
            logger.info(f"🎉 [Hong Kong stock data] Data preparation completed: {formatted_code} - {stock_name}")
            return StockDataPreparationResult(
                is_valid=True,
                stock_code=formatted_code,
                market_type="Hong Kong stocks",
                stock_name=stock_name,
                has_historical_data=has_historical_data,
                has_basic_info=has_basic_info,
                data_period_days=period_days,
                cache_status=cache_status.rstrip('; ')
            )

        except Exception as e:
            logger.error(f"❌ [Hong Kong stock data] Data preparation failed: {e}")
            return StockDataPreparationResult(
                is_valid=False,
                stock_code=formatted_code,
                market_type="Hong Kong stocks",
                stock_name=stock_name,
                has_basic_info=has_basic_info,
                has_historical_data=has_historical_data,
                error_message=f"Data preparation failed: {str(e)}",
                suggestion="Please check network connection or data source configuration"
            )

    def _prepare_us_stock_data(self, stock_code: str, period_days: int,
                              analysis_date: str) -> StockDataPreparationResult:
        """Pre-obtain US stock data"""
        logger.info(f"📊 [US stock data] Start preparing{stock_code}data (duration: {period_days}day)")

        # Standardized U.S. stock code format
        formatted_code = stock_code.upper()

        # Calculate date range
        end_date = datetime.strptime(analysis_date, '%Y-%m-%d')
        start_date = end_date - timedelta(days=period_days)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        logger.debug(f"📅 [US stock data] date range: {start_date_str} → {end_date_str}")

        has_historical_data = False
        has_basic_info = False
        stock_name = formatted_code  # U.S. stocks usually use codes as names
        cache_status = ""

        try:
            # 1. Obtain historical data (U.S. stocks usually directly verify the existence of stocks through historical data)
            logger.debug(f"📊 [US stock data] get{formatted_code}historical data ({start_date_str} Arrive {end_date_str})...")

            # Import US stock data provider (supports old and new paths)
            try:
                from tradingagents.dataflows.providers.us import OptimizedUSDataProvider
                provider = OptimizedUSDataProvider()
                historical_data = provider.get_stock_data(
                    formatted_code,
                    start_date_str,
                    end_date_str
                )
            except ImportError:
                from tradingagents.dataflows.providers.us.optimized import get_us_stock_data_cached
                historical_data = get_us_stock_data_cached(
                    formatted_code,
                    start_date_str,
                    end_date_str
                )

            if historical_data and "❌" not in historical_data and "Error" not in historical_data and "Unable to obtain" not in historical_data:
                # Looser data validity checks
                data_indicators = [
                    "opening price", "closing price", "highest price", "lowest price", "Volume",
                    "Open", "Close", "High", "Low", "Volume",
                    "Date", "Date", "time", "Time"
                ]

                has_valid_data = (
                    len(historical_data) > 50 and  # Reduce length requirements
                    any(indicator in historical_data for indicator in data_indicators)
                )

                if has_valid_data:
                    has_historical_data = True
                    has_basic_info = True  # U.S. stocks usually do not obtain basic information separately
                    logger.info(f"✅ [US stock data] Historical data obtained successfully: {formatted_code} ({period_days}day)")
                    cache_status = f"Historical data has been cached({period_days}day)"

                    # Data preparation successful
                    logger.info(f"🎉 [US stock data] Data preparation completed: {formatted_code}")
                    return StockDataPreparationResult(
                        is_valid=True,
                        stock_code=formatted_code,
                        market_type="US stocks",
                        stock_name=stock_name,
                        has_historical_data=has_historical_data,
                        has_basic_info=has_basic_info,
                        data_period_days=period_days,
                        cache_status=cache_status
                    )
                else:
                    logger.warning(f"⚠️ [US stock data] Historical data is invalid: {formatted_code}")
                    logger.debug(f"🔍 [US stock data] Data content preview: {historical_data[:200]}...")
                    return StockDataPreparationResult(
                        is_valid=False,
                        stock_code=formatted_code,
                        market_type="US stocks",
                        error_message=f"US stocks {formatted_code} historical data is invalid or insufficient",
                        suggestion="The stock may be a newly listed stock or the data source is temporarily unavailable. Please try again later."
                    )
            else:
                logger.warning(f"⚠️ [US stock data] Unable to obtain historical data: {formatted_code}")
                return StockDataPreparationResult(
                    is_valid=False,
                    stock_code=formatted_code,
                    market_type="US stocks",
                    error_message=f"US stock code {formatted_code} Data does not exist or cannot be obtained",
                    suggestion="Please check whether the US stock code is correct, such as: AAPL, TSLA,MSFT"
                )

        except Exception as e:
            logger.error(f"❌ [US stock data] Data preparation failed: {e}")
            return StockDataPreparationResult(
                is_valid=False,
                stock_code=formatted_code,
                market_type="US stocks",
                error_message=f"Data preparation failed: {str(e)}",
                suggestion="Please check network connection or data source configuration"
            )




# Global data preparer instance
_stock_preparer = None

def get_stock_preparer(default_period_days: int = 30) -> StockDataPreparer:
    """Get the stock data preparer instance (singleton mode)"""
    global _stock_preparer
    if _stock_preparer is None:
        _stock_preparer = StockDataPreparer(default_period_days)
    return _stock_preparer


def prepare_stock_data(stock_code: str, market_type: str = "auto",
                      period_days: int = None, analysis_date: str = None) -> StockDataPreparationResult:
    """
    Convenience functions: prefetching and validating stock data

    Args:
        stock_code: Stock code
        market_type: market type ("A shares", "Hong Kong stocks", "US stocks", "auto")
        period_days: Historical data duration (days), default 30 days
        analysis_date: Analysis date, default is today

    Returns:
        StockDataPreparationResult: Data preparation results
    """
    preparer = get_stock_preparer()
    return preparer.prepare_stock_data(stock_code, market_type, period_days, analysis_date)


def is_stock_data_ready(stock_code: str, market_type: str = "auto",
                       period_days: int = None, analysis_date: str = None) -> bool:
    """
    Convenience function: Check if stock data is ready

    Args:
        stock_code: Stock code
        market_type: market type ("A shares", "Hong Kong stocks", "US stocks", "auto")
        period_days: Historical data duration (days), default 30 days
        analysis_date: Analysis date, default is today

    Returns:
        bool: Is the data ready?
    """
    result = prepare_stock_data(stock_code, market_type, period_days, analysis_date)
    return result.is_valid


def get_stock_preparation_message(stock_code: str, market_type: str = "auto",
                                 period_days: int = None, analysis_date: str = None) -> str:
    """
    Convenience function: Get stock data preparation message

    Args:
        stock_code: Stock code
        market_type: market type ("A shares", "Hong Kong stocks", "US stocks", "auto")
        period_days: Historical data duration (days), default 30 days
        analysis_date: Analysis date, default is today

    Returns:
        str: data preparation message
    """
    result = prepare_stock_data(stock_code, market_type, period_days, analysis_date)

    if result.is_valid:
        return f"✅ Data preparation successful: {result.stock_code} ({result.market_type}) - {result.stock_name}\n📊 {result.cache_status}"
    else:
        return f"❌ Data preparation failed: {result.error_message}\n💡 Suggestions: {result.suggestion}"


async def prepare_stock_data_async(stock_code: str, market_type: str = "auto",
                                   period_days: int = None, analysis_date: str = None) -> StockDataPreparationResult:
    """
    Asynchronous version: prefetching and validating stock data

    🔥 Specifically used in FastAPI asynchronous context to avoid event loop conflicts

    Args:
        stock_code: Stock code
        market_type: market type ("A shares", "Hong Kong stocks", "US stocks", "auto")
        period_days: Historical data duration (days), default 30 days
        analysis_date: Analysis date, default is today

    Returns:
        StockDataPreparationResult: Data preparation results
    """
    preparer = get_stock_preparer()

    # Using an asynchronous version of an internal method
    if period_days is None:
        period_days = preparer.default_period_days

    if analysis_date is None:
        from datetime import datetime
        analysis_date = datetime.now().strftime('%Y-%m-%d')

    logger.info(f"📊 [Data preparation-asynchronous] Start preparing stock data: {stock_code} (market: {market_type}, duration: {period_days}day)")

    # 1. Basic format validation (synchronous operation)
    format_result = preparer._validate_format(stock_code, market_type)
    if not format_result.is_valid:
        return format_result

    # 2. Automatic detection of market types
    if market_type == "auto":
        market_type = preparer._detect_market_type(stock_code)
        logger.debug(f"📊 [Data preparation-asynchronous] Automatic detection of market types: {market_type}")

    # 3. Prefetch data and validate (use asynchronous version)
    return await preparer._prepare_data_by_market_async(stock_code, market_type, period_days, analysis_date)


# Maintaining backward-compatible aliases
StockValidator = StockDataPreparer
get_stock_validator = get_stock_preparer
validate_stock_exists = prepare_stock_data
is_stock_valid = is_stock_data_ready
get_stock_validation_message = get_stock_preparation_message
