"""
Alpha Vantage news data provider

Provide high-quality market news and sentiment analysis data

Refer to the original TradingAgents implementation
"""

from typing import Annotated, Dict, Any
import json
from datetime import datetime

from .alpha_vantage_common import _make_api_request, format_datetime_for_api, format_response_as_string

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')


def get_news(
    ticker: Annotated[str, "Stock symbol for news articles"],
    start_date: Annotated[str, "Start date for news search, YYYY-MM-DD"],
    end_date: Annotated[str, "End date for news search, YYYY-MM-DD"]
) -> str:
    """
    Get stock-related news and sentiment analysis data
    
    Returns real-time and historical market news and sentiment data from major global news outlets.
    Covers topics such as stocks, cryptocurrencies, foreign exchange, and fiscal policy, M&A, IPOs, and more.
    
    Args:
        ticker: Stock code
        start_date: start date, format YYYY-MM-DD
        end_date: end date, format YYYY-MM-DD
        
    Returns:
        Formatted news data string (JSON format)
        
    Example:
        >>> news = get_news("AAPL", "2024-01-01", "2024-01-31")
    """
    try:
        logger.info(f"📰 [Alpha Vantage] 获取新闻: {ticker}, {start_date} 至 {end_date}")
        
        # Build request parameters
        params = {
            "tickers": ticker.upper(),
            "time_from": format_datetime_for_api(start_date),
            "time_to": format_datetime_for_api(end_date),
            "sort": "LATEST",
            "limit": "50",  # Returns up to 50 news items
        }
        
        # Make an API request
        data = _make_api_request("NEWS_SENTIMENT", params)
        
        # Formatted response
        if isinstance(data, dict):
            # Extract key information
            feed = data.get("feed", [])
            
            if not feed:
                return f"# No news found for {ticker} between {start_date} and {end_date}\n"
            
            # Build formatted output
            result = f"# News and Sentiment for {ticker.upper()}\n"
            result += f"# Period: {start_date} to {end_date}\n"
            result += f"# Total articles: {len(feed)}\n"
            result += f"# Retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            # add every news
            for idx, article in enumerate(feed, 1):
                result += f"## Article {idx}\n"
                result += f"**Title**: {article.get('title', 'N/A')}\n"
                result += f"**Source**: {article.get('source', 'N/A')}\n"
                result += f"**Published**: {article.get('time_published', 'N/A')}\n"
                result += f"**URL**: {article.get('url', 'N/A')}\n"
                
                # sentiment analysis
                sentiment = article.get('overall_sentiment_label', 'N/A')
                sentiment_score = article.get('overall_sentiment_score', 'N/A')
                result += f"**Sentiment**: {sentiment} (Score: {sentiment_score})\n"
                
                # Summary
                summary = article.get('summary', 'N/A')
                if len(summary) > 200:
                    summary = summary[:200] + "..."
                result += f"**Summary**: {summary}\n"
                
                # Related stock sentiment
                ticker_sentiment = article.get('ticker_sentiment', [])
                for ts in ticker_sentiment:
                    if ts.get('ticker', '').upper() == ticker.upper():
                        result += f"**Ticker Sentiment**: {ts.get('ticker_sentiment_label', 'N/A')} "
                        result += f"(Score: {ts.get('ticker_sentiment_score', 'N/A')}, "
                        result += f"Relevance: {ts.get('relevance_score', 'N/A')})\n"
                        break
                
                result += "\n---\n\n"
            
            logger.info(f"✅ [Alpha Vantage] 成功获取 {len(feed)} 条新闻")
            return result
        else:
            return format_response_as_string(data, f"News for {ticker}")
            
    except Exception as e:
        logger.error(f"❌ [Alpha Vantage] Failed to get news {ticker}: {e}")
        return f"Error retrieving news for {ticker}: {str(e)}"


def get_insider_transactions(
    symbol: Annotated[str, "Ticker symbol, e.g., IBM"]
) -> str:
    """
    Get insider trading data
    
    Returns latest and historical insider transaction data for key stakeholders (founders, executives, board members, etc.).
    
    Args:
        symbol: Stock code
        
    Returns:
        Formatted insider trading data string (JSON format)
        
    Example:
        >>> transactions = get_insider_transactions("AAPL")
    """
    try:
        logger.info(f"👔 [Alpha Vantage] Get Insider Transactions: {symbol}")
        
        # Build request parameters
        params = {
            "symbol": symbol.upper(),
        }
        
        # Make an API request
        data = _make_api_request("INSIDER_TRANSACTIONS", params)
        
        # Formatted response
        if isinstance(data, dict):
            transactions = data.get("data", [])
            
            if not transactions:
                return f"# No insider transactions found for {symbol}\n"
            
            # Build formatted output
            result = f"# Insider Transactions for {symbol.upper()}\n"
            result += f"# Total transactions: {len(transactions)}\n"
            result += f"# Retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            # Add every transaction
            for idx, txn in enumerate(transactions[:20], 1):  # Limit display to the first 20 transactions
                result += f"## Transaction {idx}\n"
                result += f"**Insider**: {txn.get('insider_name', 'N/A')}\n"
                result += f"**Title**: {txn.get('insider_title', 'N/A')}\n"
                result += f"**Transaction Type**: {txn.get('transaction_type', 'N/A')}\n"
                result += f"**Date**: {txn.get('transaction_date', 'N/A')}\n"
                result += f"**Shares**: {txn.get('shares_traded', 'N/A')}\n"
                result += f"**Price**: ${txn.get('price_per_share', 'N/A')}\n"
                result += f"**Value**: ${txn.get('transaction_value', 'N/A')}\n"
                result += f"**Shares Owned After**: {txn.get('shares_owned_after_transaction', 'N/A')}\n"
                result += "\n---\n\n"
            
            logger.info(f"✅ [Alpha Vantage] 成功获取 {len(transactions)} 笔内部人交易")
            return result
        else:
            return format_response_as_string(data, f"Insider Transactions for {symbol}")
            
    except Exception as e:
        logger.error(f"❌ [Alpha Vantage] Failed to get insider transactions {symbol}: {e}")
        return f"Error retrieving insider transactions for {symbol}: {str(e)}"


def get_market_news(
    topics: Annotated[str, "News topics, e.g., 'technology,earnings'"] = None,
    start_date: Annotated[str, "Start date, YYYY-MM-DD"] = None,
    end_date: Annotated[str, "End date, YYYY-MM-DD"] = None,
    limit: Annotated[int, "Number of articles to return"] = 50
) -> str:
    """
    Get overall market news (not limited to specific stocks)
    
    Args:
        topics: News topics, multiple topics separated by commas (optional)
        start_date: Start date (optional)
        end_date: end date (optional)
        limit: Returns the number of articles, default 50
        
    Returns:
        Formatted news data string
        
    Example:
        >>> news = get_market_news(topics="technology,earnings", limit=20)
    """
    try:
        logger.info(f"📰 [Alpha Vantage] Get market news: topics={topics}")
        
        # Build request parameters
        params = {
            "sort": "LATEST",
            "limit": str(limit),
        }
        
        if topics:
            params["topics"] = topics
        
        if start_date:
            params["time_from"] = format_datetime_for_api(start_date)
        
        if end_date:
            params["time_to"] = format_datetime_for_api(end_date)
        
        # Make an API request
        data = _make_api_request("NEWS_SENTIMENT", params)
        
        # Formatted response (similar to get_news)
        if isinstance(data, dict):
            feed = data.get("feed", [])
            
            if not feed:
                return "# No market news found\n"
            
            result = f"# Market News\n"
            if topics:
                result += f"# Topics: {topics}\n"
            if start_date and end_date:
                result += f"# Period: {start_date} to {end_date}\n"
            result += f"# Total articles: {len(feed)}\n"
            result += f"# Retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            for idx, article in enumerate(feed, 1):
                result += f"## Article {idx}\n"
                result += f"**Title**: {article.get('title', 'N/A')}\n"
                result += f"**Source**: {article.get('source', 'N/A')}\n"
                result += f"**Published**: {article.get('time_published', 'N/A')}\n"
                result += f"**Sentiment**: {article.get('overall_sentiment_label', 'N/A')} "
                result += f"(Score: {article.get('overall_sentiment_score', 'N/A')})\n"
                
                summary = article.get('summary', 'N/A')
                if len(summary) > 200:
                    summary = summary[:200] + "..."
                result += f"**Summary**: {summary}\n\n"
                result += "---\n\n"
            
            logger.info(f"✅ [Alpha Vantage] 成功获取 {len(feed)} 条市场新闻")
            return result
        else:
            return format_response_as_string(data, "Market News")
            
    except Exception as e:
        logger.error(f"❌ [Alpha Vantage] Failed to get market news: {e}")
        return f"Error retrieving market news: {str(e)}"

