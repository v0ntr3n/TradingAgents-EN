"""
Alpha Vantage Fundamental data provider

Provides company fundamental data, including:
- Company Profile
- Financial statements (balance sheet, cash flow statement, income statement)
- Valuation indicators

Refer to the original TradingAgents implementation
"""

from typing import Annotated
import json
from datetime import datetime

from .alpha_vantage_common import _make_api_request, format_response_as_string

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')


def get_fundamentals(
    ticker: Annotated[str, "Ticker symbol of the company"],
    curr_date: Annotated[str, "Current date (not used for Alpha Vantage)"] = None
) -> str:
    """
    Obtain comprehensive fundamental data of the company
    
    Include financial ratios and key indicators such as:
    - Market capitalization, PE, PB, ROE and other valuation indicators
    - Financial indicators such as revenue, profit, EPS, etc.
    - Industry, sector and other company information
    
    Args:
        ticker: Stock code
        curr_date: Current date (Alpha Vantage does not use this parameter)
        
    Returns:
        Formatted company profile data string
        
    Example:
        >>> fundamentals = get_fundamentals("AAPL")
    """
    try:
        logger.info(f"📊 [Alpha Vantage] Get fundamental data: {ticker}")
        
        # Build request parameters
        params = {
            "symbol": ticker.upper(),
        }
        
        # Make an API request
        data = _make_api_request("OVERVIEW", params)
        
        # Formatted response
        if isinstance(data, dict) and data:
            # Extract key indicators
            result = f"# Company Overview: {ticker.upper()}\n"
            result += f"# Retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            # Basic information
            result += "## Basic Information\n"
            result += f"**Name**: {data.get('Name', 'N/A')}\n"
            result += f"**Symbol**: {data.get('Symbol', 'N/A')}\n"
            result += f"**Exchange**: {data.get('Exchange', 'N/A')}\n"
            result += f"**Currency**: {data.get('Currency', 'N/A')}\n"
            result += f"**Country**: {data.get('Country', 'N/A')}\n"
            result += f"**Sector**: {data.get('Sector', 'N/A')}\n"
            result += f"**Industry**: {data.get('Industry', 'N/A')}\n\n"
            
            # Company description
            description = data.get('Description', 'N/A')
            if len(description) > 500:
                description = description[:500] + "..."
            result += f"**Description**: {description}\n\n"
            
            # Valuation indicators
            result += "## Valuation Metrics\n"
            result += f"**Market Cap**: ${data.get('MarketCapitalization', 'N/A')}\n"
            result += f"**PE Ratio**: {data.get('PERatio', 'N/A')}\n"
            result += f"**PEG Ratio**: {data.get('PEGRatio', 'N/A')}\n"
            result += f"**Price to Book**: {data.get('PriceToBookRatio', 'N/A')}\n"
            result += f"**Price to Sales**: {data.get('PriceToSalesRatioTTM', 'N/A')}\n"
            result += f"**EV to Revenue**: {data.get('EVToRevenue', 'N/A')}\n"
            result += f"**EV to EBITDA**: {data.get('EVToEBITDA', 'N/A')}\n\n"
            
            # financial indicators
            result += "## Financial Metrics\n"
            result += f"**Revenue TTM**: ${data.get('RevenueTTM', 'N/A')}\n"
            result += f"**Gross Profit TTM**: ${data.get('GrossProfitTTM', 'N/A')}\n"
            result += f"**EBITDA**: ${data.get('EBITDA', 'N/A')}\n"
            result += f"**Net Income TTM**: ${data.get('NetIncomeTTM', 'N/A')}\n"
            result += f"**EPS**: ${data.get('EPS', 'N/A')}\n"
            result += f"**Diluted EPS TTM**: ${data.get('DilutedEPSTTM', 'N/A')}\n\n"
            
            # Profitability
            result += "## Profitability\n"
            result += f"**Profit Margin**: {data.get('ProfitMargin', 'N/A')}\n"
            result += f"**Operating Margin TTM**: {data.get('OperatingMarginTTM', 'N/A')}\n"
            result += f"**Return on Assets TTM**: {data.get('ReturnOnAssetsTTM', 'N/A')}\n"
            result += f"**Return on Equity TTM**: {data.get('ReturnOnEquityTTM', 'N/A')}\n\n"
            
            # dividend information
            result += "## Dividend Information\n"
            result += f"**Dividend Per Share**: ${data.get('DividendPerShare', 'N/A')}\n"
            result += f"**Dividend Yield**: {data.get('DividendYield', 'N/A')}\n"
            result += f"**Dividend Date**: {data.get('DividendDate', 'N/A')}\n"
            result += f"**Ex-Dividend Date**: {data.get('ExDividendDate', 'N/A')}\n\n"
            
            # stock information
            result += "## Stock Information\n"
            result += f"**52 Week High**: ${data.get('52WeekHigh', 'N/A')}\n"
            result += f"**52 Week Low**: ${data.get('52WeekLow', 'N/A')}\n"
            result += f"**50 Day MA**: ${data.get('50DayMovingAverage', 'N/A')}\n"
            result += f"**200 Day MA**: ${data.get('200DayMovingAverage', 'N/A')}\n"
            result += f"**Shares Outstanding**: {data.get('SharesOutstanding', 'N/A')}\n"
            result += f"**Beta**: {data.get('Beta', 'N/A')}\n\n"
            
            # financial health
            result += "## Financial Health\n"
            result += f"**Book Value**: ${data.get('BookValue', 'N/A')}\n"
            result += f"**Debt to Equity**: {data.get('DebtToEquity', 'N/A')}\n"
            result += f"**Current Ratio**: {data.get('CurrentRatio', 'N/A')}\n"
            result += f"**Quick Ratio**: {data.get('QuickRatio', 'N/A')}\n\n"
            
            # Analyst price target
            result += "## Analyst Targets\n"
            result += f"**Analyst Target Price**: ${data.get('AnalystTargetPrice', 'N/A')}\n"
            result += f"**Analyst Rating Strong Buy**: {data.get('AnalystRatingStrongBuy', 'N/A')}\n"
            result += f"**Analyst Rating Buy**: {data.get('AnalystRatingBuy', 'N/A')}\n"
            result += f"**Analyst Rating Hold**: {data.get('AnalystRatingHold', 'N/A')}\n"
            result += f"**Analyst Rating Sell**: {data.get('AnalystRatingSell', 'N/A')}\n"
            result += f"**Analyst Rating Strong Sell**: {data.get('AnalystRatingStrongSell', 'N/A')}\n\n"
            
            logger.info(f"✅ [Alpha Vantage] Successfully obtained fundamental data: {ticker}")
            return result
        else:
            return format_response_as_string(data, f"Fundamentals for {ticker}")
            
    except Exception as e:
        logger.error(f"❌ [Alpha Vantage] Failed to obtain fundamental data {ticker}: {e}")
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


def get_balance_sheet(
    ticker: Annotated[str, "Ticker symbol of the company"],
    freq: Annotated[str, "Reporting frequency: annual/quarterly (not used)"] = "quarterly",
    curr_date: Annotated[str, "Current date (not used)"] = None
) -> str:
    """
    Get balance sheet data
    
    Args:
        ticker: Stock code
        freq: Report frequency (Alpha Vantage returns all data)
        curr_date: Current date (not used)
        
    Returns:
        Formatted balance sheet data string
    """
    try:
        logger.info(f"📊 [Alpha Vantage] Get balance sheet: {ticker}")
        
        params = {"symbol": ticker.upper()}
        data = _make_api_request("BALANCE_SHEET", params)
        
        return format_response_as_string(data, f"Balance Sheet for {ticker}")
        
    except Exception as e:
        logger.error(f"❌ [Alpha Vantage] Failed to get balance sheet {ticker}: {e}")
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


def get_cashflow(
    ticker: Annotated[str, "Ticker symbol of the company"],
    freq: Annotated[str, "Reporting frequency: annual/quarterly (not used)"] = "quarterly",
    curr_date: Annotated[str, "Current date (not used)"] = None
) -> str:
    """
    Get cash flow statement data
    
    Args:
        ticker: Stock code
        freq: Report frequency (Alpha Vantage returns all data)
        curr_date: Current date (not used)
        
    Returns:
        Formatted cash flow statement data string
    """
    try:
        logger.info(f"📊 [Alpha Vantage] Get cash flow statement: {ticker}")
        
        params = {"symbol": ticker.upper()}
        data = _make_api_request("CASH_FLOW", params)
        
        return format_response_as_string(data, f"Cash Flow for {ticker}")
        
    except Exception as e:
        logger.error(f"❌ [Alpha Vantage] Failed to obtain cash flow statement {ticker}: {e}")
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


def get_income_statement(
    ticker: Annotated[str, "Ticker symbol of the company"],
    freq: Annotated[str, "Reporting frequency: annual/quarterly (not used)"] = "quarterly",
    curr_date: Annotated[str, "Current date (not used)"] = None
) -> str:
    """
    Get income statement data
    
    Args:
        ticker: Stock code
        freq: Report frequency (Alpha Vantage returns all data)
        curr_date: Current date (not used)
        
    Returns:
        Formatted income statement data string
    """
    try:
        logger.info(f"📊 [Alpha Vantage] Get income statement: {ticker}")
        
        params = {"symbol": ticker.upper()}
        data = _make_api_request("INCOME_STATEMENT", params)
        
        return format_response_as_string(data, f"Income Statement for {ticker}")
        
    except Exception as e:
        logger.error(f"❌ [Alpha Vantage] Failed to obtain income statement {ticker}: {e}")
        return f"Error retrieving income statement for {ticker}: {str(e)}"

