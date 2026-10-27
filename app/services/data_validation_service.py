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
                    logger.info(f"✅ [Data verification] Analyze date data exists, set warning_flag=False")
                
                # 🔥 If within trading hours, no warning is forced (to prevent being overwritten by other logic)
                if is_in_trading_hours:
                    warning_flag = False
                    logger.info(f"✅ [Data verification] During trading hours, mandatory setting warning_flag=False")
                
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
                return False, f"财务数据不存在", {
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
                return True, f"实时行情存在", {
                    "exists": True,
                    "current_price": doc.get("close"),
                    "update_time": doc.get("update_time")
                }
            else:
                return False, f"实时行情不存在", {
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
