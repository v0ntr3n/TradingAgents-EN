"""
Blocking utility functions related to Tushare:
- fetch_stock_basic_df: Get a list of stocks (make sure Tushare is connected)
- find_latest_trade_date: Detect the latest available trading day (YYYYMMDD)
- fetch_daily_basic_mv_map: Get daily basic indicator mapping (market cap/valuation/transaction) based on the trading day
"""
from __future__ import annotations
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

    logger.info(f"⏳ Waiting for Tushare to connect...")
    while not getattr(provider, "connected", False) and elapsed < max_wait_seconds:
        time.sleep(wait_interval)
        elapsed += wait_interval

    # Check connection status and API availability
    if not getattr(provider, "connected", False) or provider.api is None:
        logger.error(f"❌ Tushare 连接失败（等待 {max_wait_seconds}s 后超时）")
        logger.error(f"💡 Please check:")
        logger.error(f"   1. .env A valid TUSHARE_TOKEN")
        logger.error(f"   2. Tushare Token Not expired and have enough points")
        logger.error(f"   3. 网络连接正常")
        raise RuntimeError(
            f"Tushare not connected after waiting {max_wait_seconds}s. "
            "Check TUSHARE_TOKEN in .env and ensure it's valid."
        )

    logger.info(f"✅ Tushare Connected, start getting stock list...")

    # Directly call Tushare API to obtain DataFrame
    try:
        df = provider.api.stock_basic(
            list_status='L',
            fields='ts_code,symbol,name,area,industry,market,exchange,list_date,is_hs'
        )

        # 🔧 Enhanced error diagnosis
        if df is None:
            logger.error(f"❌ Tushare API Return None")
            logger.error(f"💡 Possible reasons:")
            logger.error(f"   1. Tushare Token Invalid or expired")
            logger.error(f"   2. API 积分不足")
            logger.error(f"   3. 网络连接问题")
            raise RuntimeError("Tushare API returned None. Check token validity and API credits.")

        if hasattr(df, 'empty') and df.empty:
            logger.error(f"❌ Tushare API Return empty DataFrame")
            logger.error(f"💡 Possible reasons:")
            logger.error(f"   1. list_status='L' Parameter may be incorrect")
            logger.error(f"   2. Tushare Data source is temporarily unavailable")
            logger.error(f"   3. API Call limits (please check points and call frequency)")
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
