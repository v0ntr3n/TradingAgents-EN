"""
Real-time valuation indicator calculation module
Calculate PE/PB and other indicators based on real-time market conditions and financial data
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def calculate_realtime_pe_pb(
    symbol: str,
    db_client=None
) -> Optional[Dict[str, Any]]:
    """
    Calculated dynamics based on real-time market conditions and Tushare TTM data PE/PB

    Calculation logic:
    1. Get Tushare s pe_ttm (based on yesterday s closing price) from stock_basic_info
    2. Reverse TTM net profit = Total market capitalization / pe_ttm
    3. Calculate real-time market capitalization using real-time stock prices
    4. Calculation Dynamics PE_TTM = Real-time market capitalization / TTM net profit

    Args:
        symbol: 6 stock code
        db_client: MongoDB Client (optional, for synchronous calls)

    Returns:
        {
            "pe": 22.5,              # Dynamic P/E ratio (based on TTM)
            "pb": 3.2,               # dynamic price-to-book ratio
            "pe_ttm": 23.1,          # Dynamic Price to Earnings Ratio (TTM)
            "price": 11.0,           # current price
            "market_cap": 110.5,     # Real-time market capitalization (100 million yuan)
            "ttm_net_profit": 4.8,   # TTM Net profit (100 million yuan, inferred from Tushare)
            "updated_at": "2025-10-14T10:30:00",
            "source": "realtime_calculated",
            "is_realtime": True
        }
        If calculation fails return None
    """
    try:
        # Get the database connection (make sure it is a sync client)
        if db_client is None:
            from tradingagents.config.database_manager import get_database_manager
            db_manager = get_database_manager()
            if not db_manager.is_mongodb_available():
                logger.debug("MongoDB Unavailable, cannot calculate real-time PE/PB")
                return None
            db_client = db_manager.get_mongodb_client()

        # Check if it is an asynchronous client (AsyncIOMotorClient)
        # If it is an asynchronous client, it needs to be converted to a synchronous client.
        client_type = type(db_client).__name__
        if 'AsyncIOMotorClient' in client_type or 'Motor' in client_type:
            # This is an asynchronous client, create a synchronous client
            from pymongo import MongoClient
            from app.core.config import settings
            logger.debug(f"检测到异步客户端 {client_type}，转换为同步客户端")
            db_client = MongoClient(settings.MONGO_URI)

        db = db_client['tradingagents']
        code6 = str(symbol).zfill(6)

        logger.info(f"🔍 [Real-time PE calculation] Start counting stocks {code6}")

        # 1. Get real-time quotes (market_quotes)
        quote = db.market_quotes.find_one({"code": code6})
        if not quote:
            logger.warning(f"⚠️ [实时PE计算-失败] 未找到股票 {code6} 的实时行情数据")
            return None

        realtime_price = quote.get("close")
        pre_close = quote.get("pre_close")  # Yesterday's closing price
        quote_updated_at = quote.get("updated_at", "N/A")

        if not realtime_price or realtime_price <= 0:
            logger.warning(f"⚠️ [实时PE计算-失败] 股票 {code6} 的实时价格无效: {realtime_price}")
            return None

        logger.info(f"   ✓ 实时股价: {realtime_price}元 (更新时间: {quote_updated_at})")
        logger.info(f"   ✓ 昨日收盘价: {pre_close}元")

        # 2. Get basic information (stock_basic_info) - Get Tushare's pe_ttm and market capitalization data
        # 🔥 Query the Tushare data source first (because only Tushare has pe_ttm, total_mv, total_share and other fields)
        logger.info(f"🔍 [MongoDB Query] Query conditions: code={code6}, source=tushare")
        basic_info = db.stock_basic_info.find_one({"code": code6, "source": "tushare"})

        if not basic_info:
            # 🔥 Diagnostics: See what data sources are in MongoDB
            all_sources = list(db.stock_basic_info.find({"code": code6}, {"source": 1, "_id": 0}))
            logger.warning(f"⚠️ [Dynamic PE calculation] Tushare data not found")
            logger.warning(f"   MongoDB The data source for this stock: {[s.get('source') for s in all_sources]}")

            # If there is no Tushare data, try querying other data sources
            basic_info = db.stock_basic_info.find_one({"code": code6})
            if not basic_info:
                logger.warning(f"⚠️ [动态PE计算-失败] 未找到股票 {code6} 的基础信息")
                logger.warning(f"   Suggestions: Run the Tushare data synchronization task to ensure that the stock_basic_info collection has Tushare data")
                return None
            else:
                logger.warning(f"⚠️ [Dynamic PE calculation] Use other data sources: {basic_info.get('source', 'unknown')}")
                # If it is not Tushare data, key fields may be missing and will be returned directly. None
                if basic_info.get('source') != 'tushare':
                    logger.warning(f"⚠️ [Dynamic PE calculation - failed] data source {basic_info.get('source')} Does not contain fields such as pe_ttm")
                    logger.warning(f"   可用字段: {list(basic_info.keys())}")
                    return None

        # Get Tushare's pe_ttm (based on yesterday's closing price)
        pe_ttm_tushare = basic_info.get("pe_ttm")
        pe_tushare = basic_info.get("pe")
        pb_tushare = basic_info.get("pb")
        total_mv_yi = basic_info.get("total_mv")  # Total market value (100 million yuan)
        total_share = basic_info.get("total_share")  # Total share capital (10,000 shares)
        basic_info_updated_at = basic_info.get("updated_at")  # Update time

        logger.info(f"   ✓ Tushare PE_TTM: {pe_ttm_tushare}倍")
        logger.info(f"   ✓ Tushare PE: {pe_tushare}倍")
        logger.info(f"   ✓ Tushare 总市值: {total_mv_yi}亿元")
        logger.info(f"   ✓ 总股本: {total_share}万股")
        logger.info(f"   ✓ stock_basic_info Update time: {basic_info_updated_at}")

        # 🔥 3. Determine whether market capitalization needs to be recalculated
        # If stock_basic_info is updated after today's close (15:00 after), indicating that the data is already up to date
        from datetime import datetime, time as dtime
        from zoneinfo import ZoneInfo

        need_recalculate = True
        if basic_info_updated_at:
            # Make sure the time has time zone information
            if isinstance(basic_info_updated_at, datetime):
                if basic_info_updated_at.tzinfo is None:
                    basic_info_updated_at = basic_info_updated_at.replace(tzinfo=ZoneInfo("Asia/Shanghai"))

                # Get today's date
                today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
                update_date = basic_info_updated_at.date()
                update_time = basic_info_updated_at.time()

                # If the update date is today and the update time is on 15:00 After that, it means that the data is the latest data after today's close.
                if update_date == today and update_time >= dtime(15, 0):
                    need_recalculate = False
                    logger.info(f"   💡 stock_basic_info Has been updated after today s close, directly using its data")

        if not need_recalculate:
            # Use stock_basic_info data directly, no need to recalculate
            logger.info(f"   ✓ Use the latest data from stock_basic_info (no need to recalculate)")

            result = {
                "pe": round(pe_tushare, 2) if pe_tushare else None,
                "pb": round(pb_tushare, 2) if pb_tushare else None,
                "pe_ttm": round(pe_ttm_tushare, 2) if pe_ttm_tushare else None,
                "price": round(realtime_price, 2),
                "market_cap": round(total_mv_yi, 2) if total_mv_yi else None,
                "updated_at": quote.get("updated_at"),
                "source": "stock_basic_info_latest",
                "is_realtime": False,
                "note": "Use stock_basic_info latest data after closing",
            }

            logger.info(f"✅ [动态PE计算-成功] 股票 {code6}: PE_TTM={result['pe_ttm']}倍, PB={result['pb']}倍 (来自stock_basic_info)")
            return result

        # 4. 🔥 Calculate the total share capital (need to determine whether the market value of stock_basic_info is yesterday's or today's)
        total_shares_wan = None
        yesterday_mv_yi = None

        # Option 1: Prioritize using total_share in stock_basic_info (if any)
        if total_share and total_share > 0:
            total_shares_wan = total_share
            logger.info(f"   ✓ 使用 stock_basic_info.total_share: {total_shares_wan:.2f}万股")

            # Calculate yesterday's market value = total share capital × Yesterday's closing price
            if pre_close and pre_close > 0:
                yesterday_mv_yi = (total_shares_wan * pre_close) / 10000
                logger.info(f"   ✓ 昨日市值: {total_shares_wan:.2f}万股 × {pre_close:.2f}元 / 10000 = {yesterday_mv_yi:.2f}亿元")
            elif total_mv_yi and total_mv_yi > 0:
                # If yesterday's closing price is not available, use the market capitalization of stock_basic_info (assumed to be yesterday's)
                yesterday_mv_yi = total_mv_yi
                logger.info(f"   ⚠️ market_quotes 中无 pre_close，使用 stock_basic_info 市值作为昨日市值: {yesterday_mv_yi:.2f}亿元")
            else:
                # There is neither pre_close nor total_mv_yi, so it cannot be calculated
                logger.warning(f"⚠️ [Dynamic PE calculation - failed] Unable to obtain yesterday s market value: pre_close={pre_close}, total_mv={total_mv_yi}")
                return None

        # Option 2: Use pre_close (yesterday's closing price) of market_quotes to reverse the equity
        elif pre_close and pre_close > 0 and total_mv_yi and total_mv_yi > 0:
            # 🔥 Key: Determine whether total_mv_yi is from yesterday or today
            # If stock_basic_info is updated before today's close, it means total_mv_yi is yesterday's market value
            # If the update time is after today's market close, it means that total_mv_yi is today's market value and needs to be reversed using realtime_price

            # Determine whether stock_basic_info is yesterday's data
            is_yesterday_data = True
            if basic_info_updated_at and isinstance(basic_info_updated_at, datetime):
                if basic_info_updated_at.tzinfo is None:
                    basic_info_updated_at = basic_info_updated_at.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
                today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
                update_date = basic_info_updated_at.date()
                update_time = basic_info_updated_at.time()
                # If the update date is today and the update time is on 15:00 After that, the description is today's data
                if update_date == today and update_time >= dtime(15, 0):
                    is_yesterday_data = False

            if is_yesterday_data:
                # total_mv_yi It is yesterday's market capitalization. Use pre_close to reverse the share capital.
                total_shares_wan = (total_mv_yi * 10000) / pre_close
                yesterday_mv_yi = total_mv_yi
                logger.info(f"   ✓ stock_basic_info 是昨天的数据，用 pre_close 反推总股本: {total_mv_yi:.2f}亿元 / {pre_close:.2f}元 = {total_shares_wan:.2f}万股")
            else:
                # total_mv_yi is today's market value, use realtime_price to infer the equity
                total_shares_wan = (total_mv_yi * 10000) / realtime_price
                yesterday_mv_yi = (total_shares_wan * pre_close) / 10000
                logger.info(f"   ✓ stock_basic_info 是今天的数据，用 realtime_price 反推总股本: {total_mv_yi:.2f}亿元 / {realtime_price:.2f}元 = {total_shares_wan:.2f}万股")
                logger.info(f"   ✓ 昨日市值: {total_shares_wan:.2f}万股 × {pre_close:.2f}元 / 10000 = {yesterday_mv_yi:.2f}亿元")

        # Option 3: Only total_mv_yi, no pre_close (market_quotes data is incomplete)
        elif total_mv_yi and total_mv_yi > 0:
            # Use realtime_price to infer equity, assuming total_mv_yi is yesterday's market value
            total_shares_wan = (total_mv_yi * 10000) / realtime_price
            yesterday_mv_yi = total_mv_yi
            logger.warning(f"   ⚠️ market_quotes There is no pre_close in it, assuming stock_basic_info.total_mv is yesterday s market value")
            logger.info(f"   ✓ 用 realtime_price 反推总股本: {total_mv_yi:.2f}亿元 / {realtime_price:.2f}元 = {total_shares_wan:.2f}万股")
            logger.info(f"   ✓ 昨日市值（假设）: {yesterday_mv_yi:.2f}亿元")

        # Option 4: If there are none, it cannot be calculated
        else:
            logger.warning(f"⚠️ [Dynamic PE calculation - failed] Unable to obtain total share capital data")
            logger.warning(f"   - total_share: {total_share}")
            logger.warning(f"   - pre_close: {pre_close}")
            logger.warning(f"   - total_mv: {total_mv_yi}")
            return None

        # 5. Reverse TTM net profit from Tushare pe_ttm (using yesterday's market value)

        if not pe_ttm_tushare or pe_ttm_tushare <= 0 or not yesterday_mv_yi or yesterday_mv_yi <= 0:
            logger.warning(f"⚠️ [Dynamic PE calculation - failed] Unable to infer TTM net profit: pe_ttm={pe_ttm_tushare}, yesterday_mv={yesterday_mv_yi}")
            logger.warning(f"   💡 Tips: May be a loss-making stock (PE is negative or empty)")
            return None

        # Reverse TTM net profit (100 million yuan)= Yesterday's market value / PE_TTM
        ttm_net_profit_yi = yesterday_mv_yi / pe_ttm_tushare
        logger.info(f"   ✓ 反推 TTM净利润: {yesterday_mv_yi:.2f}亿元 / {pe_ttm_tushare:.2f}倍 = {ttm_net_profit_yi:.2f}亿元")

        # 6. Calculate real-time market value (100 million yuan)= Total share capital (10,000 shares)× Real-time stock price (yuan)/ 10000
        realtime_mv_yi = (realtime_price * total_shares_wan) / 10000
        logger.info(f"   ✓ 实时市值: {realtime_price:.2f}元 × {total_shares_wan:.2f}万股 / 10000 = {realtime_mv_yi:.2f}亿元")

        # 7. Calculation Dynamics PE_TTM = Real-time market capitalization / TTM net profit
        dynamic_pe_ttm = realtime_mv_yi / ttm_net_profit_yi
        logger.info(f"   ✓ 动态PE_TTM计算: {realtime_mv_yi:.2f}亿元 / {ttm_net_profit_yi:.2f}亿元 = {dynamic_pe_ttm:.2f}倍")

        # 8. Get financial data (used to calculate PB)
        financial_data = db.stock_financial_data.find_one({"code": code6}, sort=[("report_period", -1)])
        pb = None
        total_equity_yi = None

        if financial_data:
            total_equity = financial_data.get("total_equity")  # Net assets (yuan)
            if total_equity and total_equity > 0:
                total_equity_yi = total_equity / 100000000  # Convert to 100 million yuan
                pb = realtime_mv_yi / total_equity_yi
                logger.info(f"   ✓ 动态PB计算: {realtime_mv_yi:.2f}亿元 / {total_equity_yi:.2f}亿元 = {pb:.2f}倍")
            else:
                logger.warning(f"   ⚠️ PB Calculation failed: Net worth is invalid ({total_equity})")
                # 🔥 Downgrade: Using Tushare PB
                if pb_tushare:
                    pb = pb_tushare
                    logger.info(f"   ✓ 降级使用 Tushare PB: {pb}倍")
        else:
            logger.warning(f"   ⚠️ Financial data not found and cannot be calculated PB")

        # 🔥 If PB remains None, use Tushare's PB as final downgrade
        if pb is None and pb_tushare:
            pb = pb_tushare
            logger.info(f"   ✓ 最终降级使用 Tushare PB: {pb}倍")

        # 9. Build return results
        result = {
            "pe": round(dynamic_pe_ttm, 2),  # Dynamic PE (based on TTM)
            "pb": round(pb, 2) if pb else None,
            "pe_ttm": round(dynamic_pe_ttm, 2),  # Dynamic PE_TTM
            "price": round(realtime_price, 2),
            "market_cap": round(realtime_mv_yi, 2),  # Real-time market capitalization (100 million yuan)
            "ttm_net_profit": round(ttm_net_profit_yi, 2),  # TTM Net profit (100 million yuan)
            "updated_at": quote.get("updated_at"),
            "source": "realtime_calculated_from_market_quotes",
            "is_realtime": True,
            "note": "Calculated based on market_quotes real-time stock price and pre_close",
            "total_shares": round(total_shares_wan, 2),  # Total share capital (10,000 shares)
            "yesterday_close": round(pre_close, 2) if pre_close else None,  # Yesterday's closing price (reference)
            "tushare_pe_ttm": round(pe_ttm_tushare, 2),  # Tushare PE_TTM (Reference)
            "tushare_pe": round(pe_tushare, 2) if pe_tushare else None,  # Tushare PE (Reference)
        }

        logger.info(f"✅ [动态PE计算-成功] 股票 {code6}: 动态PE_TTM={result['pe_ttm']}倍, PB={result['pb']}倍")
        return result
        
    except Exception as e:
        logger.error(f"计算股票 {symbol} 的实时PE/PB失败: {e}", exc_info=True)
        return None


def validate_pe_pb(pe: Optional[float], pb: Optional[float]) -> bool:
    """
    Verify whether PE/PB is within a reasonable range
    
    Args:
        pe: P/E ratio
        pb: price to book ratio
    
    Returns:
        bool: Is it reasonable?
    """
    # PE Reasonable range: -100 to 1000 (negative values are allowed because the PE of loss-making enterprises is negative)
    if pe is not None and (pe < -100 or pe > 1000):
        logger.warning(f"PE异常: {pe}")
        return False
    
    # PB Reasonable range: 0.1 to 100
    if pb is not None and (pb < 0.1 or pb > 100):
        logger.warning(f"PB异常: {pb}")
        return False
    
    return True


def get_pe_pb_with_fallback(
    symbol: str,
    db_client=None
) -> Dict[str, Any]:
    """
    Obtain PE/PB, intelligent downgrade strategy

    Strategy:
    1. Prioritize the use of dynamic PE (based on real-time stock prices + Tushare TTM net profit)
    2. If dynamic calculation fails, downgrade to Tushare static PE (based on yesterday s closing price)

    Advantages:
    - Dynamic PE can reflect real-time stock price changes
    - Use Tushare s official TTM net profit (reverse projection) to avoid single-quarter data errors
    - Accurate calculations and detailed logs

    Args:
        symbol: 6 stock code
        db_client: MongoDB Client (optional)

    Returns:
        {
            "pe": 22.5,              # P/E ratio
            "pb": 3.2,               # price to book ratio
            "pe_ttm": 23.1,          # Price to Earnings Ratio (TTM)
            "pb_mrq": 3.3,           # Price to Book Ratio (MRQ)
            "source": "realtime_calculated_from_tushare_ttm" | "daily_basic",
            "is_realtime": True | False,
            "updated_at": "2025-10-14T10:30:00",
            "ttm_net_profit": 4.8    # TTM Net profit (100 million yuan, only available when calculated dynamically)
        }
    """
    logger.info(f"🔄 [PE智能策略] 开始获取股票 {symbol} 的PE/PB")

    # Prepare database connection
    try:
        if db_client is None:
            from tradingagents.config.database_manager import get_database_manager
            db_manager = get_database_manager()
            if not db_manager.is_mongodb_available():
                logger.error("❌ [PE Smart Strategy - Failure] MongoDB Not available")
                return {}
            db_client = db_manager.get_mongodb_client()

        # Check if it is an asynchronous client
        client_type = type(db_client).__name__
        if 'AsyncIOMotorClient' in client_type or 'Motor' in client_type:
            from pymongo import MongoClient
            from app.core.config import settings
            logger.debug(f"检测到异步客户端 {client_type}，转换为同步客户端")
            db_client = MongoClient(settings.MONGO_URI)

    except Exception as e:
        logger.error(f"❌ [PE Smart Strategy - Failure] Database connection failed: {e}")
        return {}

    # 1. Prioritize the use of dynamic PE calculations (based on real-time stock prices + Tushare TTM) 
    logger.info("   → try solution 1: Dynamic PE calculation (real time stock price + Tushare TTM net profit)")
    logger.info("   💡 Description: Use real-time stock price and Tushare official TTM net profit to accurately reflect current valuation")

    realtime_metrics = calculate_realtime_pe_pb(symbol, db_client)
    if realtime_metrics:
        # Verify the plausibility of the data
        pe = realtime_metrics.get('pe')
        pb = realtime_metrics.get('pb')
        if validate_pe_pb(pe, pb):
            logger.info(f"✅ [PE Smart Strategies-Success] Use dynamics PE: PE={pe}, PB={pb}")
            logger.info(f"   └─ 数据来源: {realtime_metrics.get('source')}")
            logger.info(f"   └─ TTM净利润: {realtime_metrics.get('ttm_net_profit')}亿元 (从Tushare反推)")
            return realtime_metrics
        else:
            logger.warning(f"⚠️ [PE Smart Strategy-Scenario 1 Exception] Dynamic PE/PB exceeds reasonable range (PE={pe}, PB={pb})")

    # 2. Downgrade to Tushare static PE (based on yesterday's closing price)
    logger.info("   → try solution 2: Tushare static PE (Based on yesterday s closing price)")
    logger.info("   💡 Description: Use Tushare official PE_TTM, based on yesterday s closing price")

    try:
        db = db_client['tradingagents']
        code6 = str(symbol).zfill(6)

        # 🔥 Query Tushare data source first
        basic_info = db.stock_basic_info.find_one({"code": code6, "source": "tushare"})
        if not basic_info:
            # If there is no Tushare data, try querying other data sources
            basic_info = db.stock_basic_info.find_one({"code": code6})

        if basic_info:
            pe_static = basic_info.get("pe")
            pb_static = basic_info.get("pb")
            pe_ttm = basic_info.get("pe_ttm")
            pb_mrq = basic_info.get("pb_mrq")
            updated_at = basic_info.get("updated_at", "N/A")

            if pe_ttm or pe_static or pb_static:
                logger.info(f"✅ [PE Smart Strategies-Success] Use Tushare static PE: PE={pe_static}, PE_TTM={pe_ttm}, PB={pb_static}")
                logger.info(f"   └─ Data source: stock_basic_info (Update time: {updated_at})")

                return {
                    "pe": pe_static,
                    "pb": pb_static,
                    "pe_ttm": pe_ttm,
                    "pb_mrq": pb_mrq,
                    "source": "daily_basic",
                    "is_realtime": False,
                    "updated_at": updated_at,
                    "note": "Use Tushare s data from the latest trading day (based on TTM)"
                }

        logger.warning("⚠️ [PE Smart Strategy-Scenario 2 failed] Tushare Static data is not available")

    except Exception as e:
        logger.warning(f"⚠️ [PE Smart Strategy-Scenario 2 Exception] {e}")

    logger.error(f"❌ [PE智能策略-全部失败] 无法获取股票 {symbol} 的PE/PB")
    return {}

