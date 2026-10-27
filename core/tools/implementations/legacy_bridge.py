"""
Legacy Tools Bridge Module
Automatically register legacy tools from tradingagents.agents.utils.agent_utils to the new system.
"""
import logging
from typing import Annotated, Optional
from core.tools.base import register_tool
from tradingagents.agents.utils.agent_utils import Toolkit

logger = logging.getLogger(__name__)

def _invoke_legacy_tool(tool_func, **kwargs):
    """通用桥接调用逻辑"""
    try:
        # LangChain @tool Decorated objects usually have an invoke method
        if hasattr(tool_func, "invoke"):
            return tool_func.invoke(kwargs)
        # If it is an ordinary function, call it directly
        return tool_func(**kwargs)
    except Exception as e:
        logger.error(f"调用旧版工具失败 {tool_func}: {e}")
        return f"Error executing legacy tool: {str(e)}"

# ==============================================================================
# News (News)
# ==============================================================================

@register_tool(
    tool_id="get_reddit_news_legacy",
    name="Reddit global news (Legacy)",
    description="Get global news aggregation on Reddit (legacy interface)",
    category="news",
    is_online=True
)
def get_reddit_news_bridge(curr_date: str) -> str:
    """Reddit Global news aggregation (legacy interface).

    Args:
        curr_date: Current date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_reddit_news, curr_date=curr_date)

@register_tool(
    tool_id="get_finnhub_news_legacy",
    name="Finnhub financial news (Legacy)",
    description="Get news about a specific stock from Finnhub (legacy interface)",
    category="news",
    is_online=True
)
def get_finnhub_news_bridge(ticker: str, start_date: str, end_date: str) -> str:
    """Get news for a specific stock from Finnhub (legacy interface).

    Args:
        ticker: Stock code (e.g. ``AAPL``) 
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_finnhub_news, ticker=ticker, start_date=start_date, end_date=end_date)

@register_tool(
    tool_id="get_google_news_legacy",
    name="Google News search (Legacy)",
    description="Search news for specific keywords through Google News (old interface)",
    category="news",
    is_online=True
)
def get_google_news_bridge(query: str, curr_date: str) -> str:
    """Search news for specific keywords through Google News (old interface).

    Args:
        query: Search keywords
        curr_date: Current date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_google_news, query=query, curr_date=curr_date)

@register_tool(
    tool_id="get_realtime_stock_news_legacy",
    name="Live stock news (Legacy)",
    description="Get real-time news analysis of stocks (old version interface)",
    category="news",
    is_online=True
)
def get_realtime_stock_news_bridge(ticker: str, curr_date: str) -> str:
    """Get real-time news analysis of stocks (legacy interface).

    Args:
        ticker: Stock code (e.g. ``AAPL``) 
        curr_date: Current date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_realtime_stock_news, ticker=ticker, curr_date=curr_date)

@register_tool(
    tool_id="get_stock_news_openai_legacy",
    name="OpenAI Stock news analysis (Legacy)",
    description="Obtain and analyze stock news using the OpenAI interface (legacy interface)",
    category="news",
    is_online=True,
    timeout_tier="heavy",
)
def get_stock_news_openai_bridge(ticker: str, curr_date: str) -> str:
    """Get and analyze stock news using the OpenAI interface (legacy interface).

    Args:
        ticker: Stock code (e.g. ``AAPL``) 
        curr_date: Current date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_stock_news_openai, ticker=ticker, curr_date=curr_date)

@register_tool(
    tool_id="get_global_news_openai_legacy",
    name="OpenAI Macro News Analysis (Legacy)",
    description="Obtain and analyze macroeconomic news using the OpenAI interface (legacy interface)",
    category="news",
    is_online=True,
    timeout_tier="heavy",
)
def get_global_news_openai_bridge(curr_date: str) -> str:
    """Get and analyze macroeconomic news using the OpenAI interface (legacy interface).

    Args:
        curr_date: Current date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_global_news_openai, curr_date=curr_date)

# ==============================================================================
# social-emotional (Social)
# ==============================================================================

@register_tool(
    tool_id="get_reddit_stock_info_legacy",
    name="Reddit stock discussion (Legacy)",
    description="Get discussion information about a specific stock on Reddit (legacy interface)",
    category="social",
    is_online=True
)
def get_reddit_stock_info_bridge(ticker: str, curr_date: str) -> str:
    """Get discussion information about a specific stock on Reddit (legacy interface).

    Args:
        ticker: Stock code (e.g. ``AAPL``) 
        curr_date: Current date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_reddit_stock_info, ticker=ticker, curr_date=curr_date)

@register_tool(
    tool_id="get_chinese_social_sentiment_legacy",
    name="Chinese social sentiment (Legacy)",
    description="Get stock sentiment from Chinese social media (Xueqiu, Stock Bar, etc.) (old version interface)",
    category="social",
    is_online=True
)
def get_chinese_social_sentiment_bridge(ticker: str, curr_date: str) -> str:
    """Get stock sentiment from Chinese social media (Snowball, Stock Bar, etc.) (old version interface).

    Args:
        ticker: Stock code (e.g. ``000001`` or ``AAPL``) 
        curr_date: Current date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_chinese_social_sentiment, ticker=ticker, curr_date=curr_date)

# ==============================================================================
# Market conditions (Market)
# ==============================================================================

@register_tool(
    tool_id="get_china_market_overview_legacy",
    name="China market overview (Legacy)",
    description="Get an overview of major Chinese stock market indexes (old version interface)",
    category="market",
    is_online=True
)
def get_china_market_overview_bridge(curr_date: str) -> str:
    """Get an overview of China s major stock market indexes (old version interface).

    Args:
        curr_date: Current date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_china_market_overview, curr_date=curr_date)

# ==============================================================================
# Technical analysis (Technical)
# ==============================================================================

@register_tool(
    tool_id="get_stockstats_indicators_report_legacy",
    name="Technical indicator report (Stockstats/Legacy)",
    description="Generate analysis reports for specific technical indicators (old version interface)",
    category="technical",
    is_online=False,
    when_to_use="Only for compatibility with legacy workflows. New projects should use get_technical_indicators or get_technical_factor_bundle_tool.",
    when_not_to_use="New projects/analyses should not use this legacy interface; data accuracy may not be as good as with newer versions of the tool.",
    tool_role_hint="fallback",
    related_tools=["get_technical_indicators", "get_technical_factor_bundle_tool"],
    capability_tags=["legacy", "technical_analysis", "deprecated"],
)
def get_stockstats_indicators_report_bridge(symbol: str, indicator: str, curr_date: str, look_back_days: int = 30) -> str:
    """Generate analysis reports for specific technical indicators (old version interface, offline).

    Args:
        symbol: Underlying code (stock code/index code)
        indicator: Technical indicator name (such as ``MACD``, ``RSI``, ``KDJ``) 
        curr_date: Current date (YYYY-MM-DD)
        look_back_days: Number of days to look back, default 30

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_stockstats_indicators_report, symbol=symbol, indicator=indicator, curr_date=curr_date, look_back_days=look_back_days)

@register_tool(
    tool_id="get_stockstats_indicators_report_online_legacy",
    name="Real-time technical indicator reporting (Stockstats/Online/Legacy)",
    description="Generate real-time analysis reports of specific technical indicators (old version interface)",
    category="technical",
    is_online=True,
    when_to_use="Only for compatibility with legacy workflows. New projects should use get_technical_indicators or get_technical_factor_bundle_tool.",
    when_not_to_use="New projects/new analyzes should not use this legacy interface.",
    tool_role_hint="fallback",
    related_tools=["get_technical_indicators", "get_technical_factor_bundle_tool"],
    capability_tags=["legacy", "technical_analysis", "deprecated"],
)
def get_stockstats_indicators_report_online_bridge(symbol: str, indicator: str, curr_date: str, look_back_days: int = 30) -> str:
    """Generate real-time analysis reports of specific technical indicators (old version interface, online).

    Args:
        symbol: Underlying code (stock code/index code)
        indicator: Technical indicator name (such as ``MACD``, ``RSI``, ``KDJ``) 
        curr_date: Current date (YYYY-MM-DD)
        look_back_days: Number of days to look back, default 30

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_stockstats_indicators_report_online, symbol=symbol, indicator=indicator, curr_date=curr_date, look_back_days=look_back_days)

@register_tool(
    tool_id="get_yfin_data_legacy",
    name="Yahoo Finance data (Legacy)",
    description="Get stock price data from Yahoo Finance (legacy interface)",
    category="market",
    is_online=False
)
def get_yfin_data_bridge(symbol: str, start_date: str, end_date: str) -> str:
    """Get stock price data from Yahoo Finance (legacy interface, offline/cached).

    Args:
        symbol: target code (e.g. ``AAPL``) 
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_YFin_data, symbol=symbol, start_date=start_date, end_date=end_date)

@register_tool(
    tool_id="get_yfin_data_online_legacy",
    name="Yahoo Finance real time data (Legacy)",
    description="Get real-time stock price data from Yahoo Finance (legacy interface)",
    category="market",
    is_online=True
)
def get_yfin_data_online_bridge(symbol: str, start_date: str, end_date: str) -> str:
    """Get real-time stock price data from Yahoo Finance (legacy interface, online).

    Args:
        symbol: target code (e.g. ``AAPL``) 
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_YFin_data_online, symbol=symbol, start_date=start_date, end_date=end_date)

# ==============================================================================
# Fundamentals (Fundamentals)
# ==============================================================================

@register_tool(
    tool_id="get_finnhub_company_insider_sentiment_legacy",
    name="insider sentiment (Finnhub/Legacy)",
    description="Get the trading sentiment of company insiders (old version interface)",
    category="fundamentals",
    is_online=True
)
def get_finnhub_company_insider_sentiment_bridge(ticker: str, curr_date: str) -> str:
    """Get trading sentiment of company insiders (legacy interface).

    Args:
        ticker: Stock code (e.g. ``AAPL``) 
        curr_date: Current date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_finnhub_company_insider_sentiment, ticker=ticker, curr_date=curr_date)

@register_tool(
    tool_id="get_finnhub_company_insider_transactions_legacy",
    name="insider trading (Finnhub/Legacy)",
    description="Obtain specific transaction records of company insiders (old version interface)",
    category="fundamentals",
    is_online=True
)
def get_finnhub_company_insider_transactions_bridge(ticker: str, curr_date: str) -> str:
    """Obtain specific transaction records of company insiders (old version interface).

    Args:
        ticker: Stock code (e.g. ``AAPL``) 
        curr_date: Current date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_finnhub_company_insider_transactions, ticker=ticker, curr_date=curr_date)

@register_tool(
    tool_id="get_simfin_income_stmt_legacy",
    name="income statement (SimFin/Legacy)",
    description="Get company income statement data (old version interface)",
    category="fundamentals",
    is_online=False
)
def get_simfin_income_stmt_bridge(ticker: str, freq: str, curr_date: str) -> str:
    """Get company income statement data (old version interface).

    Args:
        ticker: Stock code (e.g. ``AAPL``) 
        freq: Frequency of financial reporting (e.g. ``annual``, ``quarterly``) 
        curr_date: Current date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_simfin_income_stmt, ticker=ticker, freq=freq, curr_date=curr_date)

@register_tool(
    tool_id="get_simfin_balance_sheet_legacy",
    name="balance sheet (SimFin/Legacy)",
    description="Get company balance sheet data (old version interface)",
    category="fundamentals",
    is_online=False
)
def get_simfin_balance_sheet_bridge(ticker: str, freq: str, curr_date: str) -> str:
    """Get company balance sheet data (old version interface).

    Args:
        ticker: Stock code (e.g. ``AAPL``) 
        freq: Frequency of financial reporting (e.g. ``annual``, ``quarterly``) 
        curr_date: Current date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_simfin_balance_sheet, ticker=ticker, freq=freq, curr_date=curr_date)

@register_tool(
    tool_id="get_simfin_cashflow_legacy",
    name="cash flow statement (SimFin/Legacy)",
    description="Get company cash flow statement data (old version interface)",
    category="fundamentals",
    is_online=False
)
def get_simfin_cashflow_bridge(ticker: str, freq: str, curr_date: str) -> str:
    """Get company cash flow statement data (old version interface).

    Args:
        ticker: Stock code (e.g. ``AAPL``) 
        freq: Frequency of financial reporting (e.g. ``annual``, ``quarterly``) 
        curr_date: Current date (YYYY-MM-DD)

    Returns:
        str: Text/JSON string returned by legacy tools; returned on failure
            ``"Error executing legacy tool: <error message>"``
    """
    return _invoke_legacy_tool(Toolkit.get_simfin_cashflow, ticker=ticker, freq=freq, curr_date=curr_date)

logger.info("✅ All legacy tool bridges loaded (Legacy Bridge Loaded)")
