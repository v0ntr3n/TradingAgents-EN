# gets data/stats

import yfinance as yf
from typing import Annotated, Callable, Any, Optional
from pandas import DataFrame
import pandas as pd
from functools import wraps
from datetime import datetime
from dateutil.relativedelta import relativedelta
import os

from tradingagents.utils.dataflow_utils import save_output, SavePathType, decorate_all_methods

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')

# Import cache manager (lazy import, avoid circular dependencies)
_cache_module = None
CACHE_AVAILABLE = True

def get_cache():
    """延迟导入缓存管理器"""
    global _cache_module, CACHE_AVAILABLE
    if _cache_module is None:
        try:
            from ...cache import get_cache as _get_cache
            _cache_module = _get_cache
            CACHE_AVAILABLE = True
        except ImportError as e:
            CACHE_AVAILABLE = False
            logger.debug(f"Cache manager is not available (using direct API call): {e}")
            return None
    return _cache_module() if _cache_module else None


def init_ticker(func: Callable) -> Callable:
    """Decorator to initialize yf.Ticker and pass it to the function."""

    @wraps(func)
    def wrapper(symbol: Annotated[str, "ticker symbol"], *args, **kwargs) -> Any:
        ticker = yf.Ticker(symbol)
        return func(ticker, *args, **kwargs)

    return wrapper


@decorate_all_methods(init_ticker)
class YFinanceUtils:

    def get_stock_data(
        symbol: Annotated[str, "ticker symbol"],
        start_date: Annotated[
            str, "start date for retrieving stock price data, YYYY-mm-dd"
        ],
        end_date: Annotated[
            str, "end date for retrieving stock price data, YYYY-mm-dd"
        ],
        save_path: SavePathType = None,
    ) -> DataFrame:
        """retrieve stock price data for designated ticker symbol"""
        ticker = symbol
        # add one day to the end_date so that the data range is inclusive
        end_date = pd.to_datetime(end_date) + pd.DateOffset(days=1)
        end_date = end_date.strftime("%Y-%m-%d")
        stock_data = ticker.history(start=start_date, end=end_date)
        # save_output(stock_data, f"Stock data for {ticker.ticker}", save_path)
        return stock_data

    def get_stock_info(
        symbol: Annotated[str, "ticker symbol"],
    ) -> dict:
        """Fetches and returns latest stock information."""
        ticker = symbol
        stock_info = ticker.info
        return stock_info

    def get_company_info(
        symbol: Annotated[str, "ticker symbol"],
        save_path: Optional[str] = None,
    ) -> DataFrame:
        """Fetches and returns company information as a DataFrame."""
        ticker = symbol
        info = ticker.info
        company_info = {
            "Company Name": info.get("shortName", "N/A"),
            "Industry": info.get("industry", "N/A"),
            "Sector": info.get("sector", "N/A"),
            "Country": info.get("country", "N/A"),
            "Website": info.get("website", "N/A"),
        }
        company_info_df = DataFrame([company_info])
        if save_path:
            company_info_df.to_csv(save_path)
            logger.info(f"Company info for {ticker.ticker} saved to {save_path}")
        return company_info_df

    def get_stock_dividends(
        symbol: Annotated[str, "ticker symbol"],
        save_path: Optional[str] = None,
    ) -> DataFrame:
        """Fetches and returns the latest dividends data as a DataFrame."""
        ticker = symbol
        dividends = ticker.dividends
        if save_path:
            dividends.to_csv(save_path)
            logger.info(f"Dividends for {ticker.ticker} saved to {save_path}")
        return dividends

    def get_income_stmt(symbol: Annotated[str, "ticker symbol"]) -> DataFrame:
        """Fetches and returns the latest income statement of the company as a DataFrame."""
        ticker = symbol
        income_stmt = ticker.financials
        return income_stmt

    def get_balance_sheet(symbol: Annotated[str, "ticker symbol"]) -> DataFrame:
        """Fetches and returns the latest balance sheet of the company as a DataFrame."""
        ticker = symbol
        balance_sheet = ticker.balance_sheet
        return balance_sheet

    def get_cash_flow(symbol: Annotated[str, "ticker symbol"]) -> DataFrame:
        """Fetches and returns the latest cash flow statement of the company as a DataFrame."""
        ticker = symbol
        cash_flow = ticker.cashflow
        return cash_flow

    def get_analyst_recommendations(symbol: Annotated[str, "ticker symbol"]) -> tuple:
        """Fetches the latest analyst recommendations and returns the most common recommendation and its count."""
        ticker = symbol
        recommendations = ticker.recommendations
        if recommendations.empty:
            return None, 0  # No recommendations available

        # Assuming 'period' column exists and needs to be excluded
        row_0 = recommendations.iloc[0, 1:]  # Exclude 'period' column if necessary

        # Find the maximum voting result
        max_votes = row_0.max()
        majority_voting_result = row_0[row_0 == max_votes].index.tolist()

        return majority_voting_result[0], max_votes


# ==================== Technical indicator related functions ====================

def get_stock_data_with_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Gets stock data (OHLCV) and returns a CSV format string

    Refer to the get_YFin_data_online implementation of the original TradingAgents
    """
    try:
        # Validate date format
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")

        # Create ticker object
        ticker = yf.Ticker(symbol.upper())

        # Get historical data
        data = ticker.history(start=start_date, end=end_date)

        # Check if the data is empty
        if data.empty:
            return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

        # Remove time zone information
        if data.index.tz is not None:
            data.index = data.index.tz_localize(None)

        # Numeric columns retain 2 decimal places
        numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
        for col in numeric_columns:
            if col in data.columns:
                data[col] = data[col].round(2)

        # Convert to CSV string
        csv_string = data.to_csv()

        # Add header information
        header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
        header += f"# Total records: {len(data)}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        logger.error(f"❌ [yfinance] Failed to get stock data {symbol}: {e}")
        return f"Error retrieving stock data for {symbol}: {str(e)}"


def get_technical_indicator(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to calculate"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 60,
) -> str:
    """
    Get technical indicator data (calculated using stockstats library)

    Refer to the get_stock_stats_indicators_window implementation of the original TradingAgents

    Supported indicators:
    - close_50_sma: 50 daily simple moving average
    - close_200_sma: 200 daily simple moving average
    - close_10_ema: 10 daily exponential moving average
    - macd: MACD indicator
    - macds: MACD signal line
    - macdh: MACD bar chart
    - rsi: relative strength indicator
    - boll: Bollinger Bands Middle Track
    - boll_ub: Bollinger Bands track
    - boll_lb: Bollinger Bands Lower Track
    - atr: average true volatility
    - vwma: Volume Weighted Moving Average
    - mfi: money flow indicator
    """
    try:
        from stockstats import wrap

        # Indicator description
        indicator_descriptions = {
            "close_50_sma": (
                "50 SMA: Medium-term trend indicator."
                "Purpose: Identify trend direction as dynamic support/resistance levels."
                "Tip: lags the price and is recommended to be used in conjunction with fast indicators."
            ),
            "close_200_sma": (
                "200 SMA: Long term trend benchmark."
                "Purpose: Confirm the overall market trend and identify golden cross/death cross."
                "Tip: Slow response, suitable for strategic trend confirmation."
            ),
            "close_10_ema": (
                "10 EMA: Short-term response average."
                "Purpose: Capture rapid momentum changes and potential entry points."
                "Tip: Noise is easily generated in volatile markets."
            ),
            "macd": (
                "MACD: Momentum is calculated from the EMA difference."
                "Purpose: Look for crossovers and divergences as trend change signals."
                "Tip: Confirmation from other indicators is needed in low volatility or sideways markets."
            ),
            "macds": (
                "MACD signal line: MACD The line s EMA is smoothed."
                "Purpose: Crossing with the MACD line triggers a trading signal."
                "Tip: Should be used as part of a broader strategy."
            ),
            "macdh": (
                "MACD bar chart: MACD The difference between the line and the signal line."
                "Use: Visualize momentum strength and detect divergences early."
                "Tip: Can be volatile and require additional filtering in fast markets."
            ),
            "rsi": (
                "RSI: Momentum is measured to mark overbought/oversold conditions."
                "Purpose: Apply 70/30 threshold and observe divergence for signal reversal."
                "Tip: In a strong trend, RSI may maintain extreme values and needs to be combined with trend analysis."
            ),
            "boll": (
                "Bollinger Bands Middle Track: 20 The Japanese SMA serves as the Bollinger Band benchmark."
                "Purpose: As a dynamic benchmark for price movements."
                "Tip: Combine the upper and lower rails to effectively find breakthroughs or reversals."
            ),
            "boll_ub": (
                "Bollinger Bands track: Typically 2 standard deviations above the mid-rail."
                "Purpose: Signals potential overbought conditions and breakout areas."
                "Tip: Other tools are needed to confirm that prices may move along a track in a strong trend."
            ),
            "boll_lb": (
                "Bollinger Bands Lower Track: Typically 2 standard deviations below the mid-rail."
                "Purpose: Indicates potential oversold conditions."
                "Tip: Use additional analysis to avoid false reversal signals."
            ),
            "atr": (
                "ATR: Average true amplitude measures volatility."
                "Purpose: Set stop loss level and adjust position size according to current market fluctuations."
                "Tip: This is a reactive indicator and should be used as part of a broader risk management strategy."
            ),
            "vwma": (
                "VWMA: Volume weighted moving average."
                "Purpose: Confirm trends by integrating price and volume data."
                "Tip: Pay attention to the deviation caused by the surge in trading volume and use it in conjunction with other trading volume analysis."
            ),
            "mfi": (
                "MFI: A money flow indicator that uses price and volume to measure buying and selling pressure."
                "Purpose: Identify overbought(>80)or oversold(<20)status, confirming trend or reversal strength."
                "Tip: Used in conjunction with RSI or MACD as a confirmation signal, price divergence from the MFI may signal a reversal."
            ),
        }

        if indicator not in indicator_descriptions:
            supported = ", ".join(indicator_descriptions.keys())
            return f"❌ 不支持的指标 '{indicator}'。支持的指标: {supported}"

        # Calculate date range
        curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_date_dt = curr_date_dt - relativedelta(days=look_back_days + 365)  # Obtain one more year of data for calculation
        start_date = start_date_dt.strftime("%Y-%m-%d")

        # Get stock data
        logger.info(f"📊 [yfinance] 获取 {symbol} 技术指标 {indicator}，日期范围: {start_date} 至 {curr_date}")
        ticker = yf.Ticker(symbol.upper())
        data = ticker.history(start=start_date, end=curr_date)

        if data.empty:
            return f"❌ 未找到 {symbol} 的数据"

        # Reset index with date as column
        data = data.reset_index()
        data['Date'] = pd.to_datetime(data['Date']).dt.strftime('%Y-%m-%d')

        # Calculate metrics using stockstats
        df = wrap(data)
        df[indicator]  # Trigger calculation

        # Generate results for a specified date range
        result_lines = []
        check_date = curr_date_dt
        end_date = curr_date_dt - relativedelta(days=look_back_days)

        while check_date >= end_date:
            date_str = check_date.strftime('%Y-%m-%d')

            # Find the metric value for this date
            matching_rows = df[df['Date'] == date_str]

            if not matching_rows.empty:
                value = matching_rows.iloc[0][indicator]
                if pd.isna(value):
                    result_lines.append(f"{date_str}: N/A")
                else:
                    result_lines.append(f"{date_str}: {value:.4f}")
            else:
                result_lines.append(f"{date_str}: N/A: Not a trading day (weekend or holiday)")

            check_date = check_date - relativedelta(days=1)

        # Build result string
        result = f"## {indicator} values from {end_date.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        result += "\n".join(result_lines)
        result += "\n\n" + indicator_descriptions[indicator]

        return result

    except ImportError:
        return "❌ Requires the stockstats library to be installed: pip install stockstats"
    except Exception as e:
        logger.error(f"❌ [yfinance] Failed to calculate technical indicators {symbol}/{indicator}: {e}")
        return f"Error calculating indicator {indicator} for {symbol}: {str(e)}"
