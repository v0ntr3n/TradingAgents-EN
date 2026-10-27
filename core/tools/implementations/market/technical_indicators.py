"""
Unified Technical Indicators Tool

Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call the corresponding data sources to obtain data.
Then use stockstats to calculate technical indicators.
"""

import logging
import re
import pandas as pd
from typing import Annotated, List, Union
from langchain_core.tools import tool
from datetime import datetime, timedelta

from core.tools.base import register_tool
from tradingagents.utils.stock_utils import StockUtils

logger = logging.getLogger(__name__)

@tool
@register_tool(
    tool_id="get_technical_indicators",
    name="统一技术指标分析",
    description="Get various technical indicators of stocks (MACD, RSI, KDJ, BOLL etc.), supports A shares/Hong Kong stocks/US stocks",
    category="market",
    is_online=True,
    auto_register=True,
    capability_tags=["technical_indicators", "technical_analysis", "macd", "rsi", "kdj", "boll", "momentum"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["technical_indicator_analysis", "trend_analysis", "momentum_analysis", "overbought_oversold_detection"],
    related_tools=["get_stock_market_data_unified", "get_stock_fundamentals_unified", "get_technical_factor_bundle_tool", "get_crossover_signals", "get_candlestick_patterns"],
)
def get_technical_indicators(
    ticker: Annotated[str, "Stock code (supports A shares, Hong Kong stocks, and US stocks)"],
    indicators: Annotated[str, "List of technical indicators, separated by commas, such as 'macd,rsi_14,boll,kdj'"],
    start_date: Annotated[str, "Start date, format: YYYY-MM-DD. Usually the year before the analysis date to ensure there is enough data to calculate the indicator"] = None,
    end_date: Annotated[str, "End date, format: YYYY-MM-DD. Usually the date of analysis"] = None
) -> str:
    """
    Get a unified technical indicator analysis report
    
    Args:
        ticker: Stock code
        indicators: Indicator list string, such as "macd,rsi,kdj"
        start_date: start date (By default, it will be automatically calculated as 365 days before end_date)
        end_date: end date (Default is today)
        
    Returns:
        str: Formatted technical indicator reports
    """
    # 1. initialization date
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    if not start_date:
        # The default lookback is 365 days to ensure that long-term indicators such as MA250 are available
        start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=365)
        start_date = start_dt.strftime("%Y-%m-%d")

    # 2. Standardized stock code
    original_ticker = ticker
    ticker = re.sub(r'\.(SZ|SH|BJ|sz|sh|bj)$', '', ticker.strip())
    
    logger.info(f"📈 [Technical indicators] Analyze stocks: {ticker} ({start_date} -> {end_date})")
    
    try:
        # 3. Identify the market
        market_info = StockUtils.get_market_info(ticker)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']
        is_us = market_info['is_us']
        
        df = None
        
        # 4. Get raw data (DataFrame)
        if is_china:
            from tradingagents.dataflows.providers.china.tushare import TushareProvider
            from tradingagents.dataflows.providers.china.akshare import AKShareProvider
            import asyncio
            
            # Helper to run async code in sync tool
            def run_async(coro):
                try:
                    return asyncio.run(coro)
                except RuntimeError:
                    # Loop already running, try to use it
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import nest_asyncio
                        nest_asyncio.apply()
                        return asyncio.run(coro)
                    return loop.run_until_complete(coro)

            # Try first Tushare
            try:
                provider = TushareProvider()
                # TushareProvider needs async call
                df = run_async(provider.get_historical_data(ticker, start_date, end_date))
                
                if df is not None and not df.empty:
                    # Rename columns for stockstats
                    # Tushare: ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
                    df = df.rename(columns={
                        'trade_date': 'date',
                        'vol': 'volume'
                    })
            except Exception as e:
                logger.warning(f"Tushare Failed to get data: {e}")
            
            # downgrade to AKShare
            if df is None or df.empty:
                try:
                    provider = AKShareProvider()
                    # AKShareProvider needs async call
                    df = run_async(provider.get_historical_data(ticker, start_date, end_date))
                    # AKShareProvider.get_historical_data already standardizes columns
                except Exception as e:
                    logger.warning(f"AKShare Failed to get data: {e}")

        elif is_hk:
            from tradingagents.dataflows.providers.hk.improved_hk import ImprovedHKStockProvider
            try:
                provider = ImprovedHKStockProvider()
                df = provider.get_daily_data(ticker, start_date, end_date)
            except Exception as e:
                logger.warning(f"港股数据获取失败: {e}")
                
        elif is_us:
            from tradingagents.dataflows.providers.us.optimized import OptimizedUSProvider
            try:
                provider = OptimizedUSProvider()
                df = provider.get_daily_data(ticker, start_date, end_date)
            except Exception as e:
                logger.warning(f"美股数据获取失败: {e}")

        # 5. Validate data
        if df is None or df.empty:
            return f"❌ 无法获取股票 {ticker} 的历史数据，无法计算技术指标。"
            
        # 6. Calculate indicators (Use stockstats)
        from stockstats import wrap
        
        # Make sure column names comply with stockstats requirements (open, high, low, close, volume)
        # Our get_daily_data should already have normalized column names, but double check just to be safe
        df.columns = [c.lower() for c in df.columns]
        
        # stockstats Requires Date column as index or column? 
        # wrap() usually accepted DataFrame
        stock = wrap(df)
        
        indicator_list = [i.strip() for i in indicators.split(',')]
        
        # Extended abbreviation indicator
        expanded_list = []
        for ind in indicator_list:
            if ind.lower() == 'kdj':
                expanded_list.extend(['kdjk', 'kdjd', 'kdjj'])
            else:
                expanded_list.append(ind)
        indicator_list = expanded_list
        
        report_lines = [f"## {original_ticker} 技术指标分析", f"日期范围: {start_date} 至 {end_date}", ""]
        
        # Get the most recent data (last row)
        latest_date = df.index[-1] if isinstance(df.index, pd.DatetimeIndex) else df['date'].iloc[-1]
        report_lines.append(f"### 最新数据 ({latest_date})")
        report_lines.append(f"收盘价: {stock['close'].iloc[-1]:.2f}")
        
        for ind in indicator_list:
            try:
                # Calculate indicators
                series = stock[ind]
                val = series.iloc[-1]
                
                # Formatted output
                val_str = f"{val:.4f}" if isinstance(val, (int, float)) else str(val)
                
                # Add simple trend judgment (Based on changes in the last two days)
                trend = ""
                if len(series) >= 2:
                    prev_val = series.iloc[-2]
                    if isinstance(val, (int, float)) and isinstance(prev_val, (int, float)):
                        if val > prev_val: trend = "↑"
                        elif val < prev_val: trend = "↓"
                        else: trend = "-"
                
                report_lines.append(f"- **{ind}**: {val_str} {trend}")
                
                # For some indicators, additional information is provided
                if 'rsi' in ind:
                    status = "中性"
                    if val > 70: status = "超买 ⚠️"
                    elif val < 30: status = "超卖 💎"
                    report_lines.append(f"  - 状态: {status}")
                elif 'macd' in ind and ind == 'macd':
                    # MACD contains macd, macds (signal), macdh (hist)
                    macds = stock['macds'].iloc[-1]
                    macdh = stock['macdh'].iloc[-1]
                    report_lines.append(f"  - Signal: {macds:.4f}")
                    report_lines.append(f"  - Hist: {macdh:.4f}")
                    if macdh > 0 and stock['macdh'].iloc[-2] <= 0:
                        report_lines.append(f"  - signal: Golden Cross (positive kinetic energy signal)📈")
                    elif macdh < 0 and stock['macdh'].iloc[-2] >= 0:
                        report_lines.append(f"  - signal: Death Cross (negative kinetic energy signal)📉")

            except Exception as e:
                report_lines.append(f"- {ind}: 计算失败 ({e})")
        
        return "\n".join(report_lines)

    except Exception as e:
        logger.error(f"技术指标计算失败: {e}", exc_info=True)
        return f"❌ Technical indicator calculation error occurred: {str(e)}"
