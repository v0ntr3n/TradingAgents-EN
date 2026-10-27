from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage, AIMessage
from typing import List
from typing import Annotated
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import RemoveMessage
from langchain_core.tools import tool
from datetime import date, timedelta, datetime
import functools
import pandas as pd
import os
from dateutil.relativedelta import relativedelta
from langchain_openai import ChatOpenAI
import tradingagents.dataflows.interface as interface
from tradingagents.default_config import DEFAULT_CONFIG
from langchain_core.messages import HumanMessage

# Import the unified logging system and tool log decorator
from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_tool_call, log_analysis_step

# Import log module
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]
        
        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        
        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")
        
        return {"messages": removal_operations + [placeholder]}
    
    return delete_messages


class Toolkit:
    _config = DEFAULT_CONFIG.copy()

    @classmethod
    def update_config(cls, config):
        """Update the class-level configuration."""
        cls._config.update(config)

    @property
    def config(self):
        """Access the configuration."""
        return self._config

    def __init__(self, config=None):
        if config:
            self.update_config(config)

    @staticmethod
    @tool
    def get_reddit_news(
        curr_date: Annotated[str, "Date you want to get news for in yyyy-mm-dd format"],
    ) -> str:
        """
        Retrieve global news from Reddit within a specified time frame.
        Args:
            curr_date (str): Date you want to get news for in yyyy-mm-dd format
        Returns:
            str: A formatted dataframe containing the latest global news from Reddit in the specified time frame.
        """
        
        global_news_result = interface.get_reddit_global_news(curr_date, 7, 5)

        return global_news_result

    @staticmethod
    @tool
    def get_finnhub_news(
        ticker: Annotated[
            str,
            "Search query of a company, e.g. 'AAPL, TSM, etc.",
        ],
        start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
        end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    ):
        """
        Retrieve the latest news about a given stock from Finnhub within a date range
        Args:
            ticker (str): Ticker of a company. e.g. AAPL, TSM
            start_date (str): Start date in yyyy-mm-dd format
            end_date (str): End date in yyyy-mm-dd format
        Returns:
            str: A formatted dataframe containing news about the company within the date range from start_date to end_date
        """

        end_date_str = end_date

        end_date = datetime.strptime(end_date, "%Y-%m-%d")
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
        look_back_days = (end_date - start_date).days

        finnhub_news_result = interface.get_finnhub_news(
            ticker, end_date_str, look_back_days
        )

        return finnhub_news_result

    @staticmethod
    @tool
    def get_reddit_stock_info(
        ticker: Annotated[
            str,
            "Ticker of a company. e.g. AAPL, TSM",
        ],
        curr_date: Annotated[str, "Current date you want to get news for"],
    ) -> str:
        """
        Retrieve the latest news about a given stock from Reddit, given the current date.
        Args:
            ticker (str): Ticker of a company. e.g. AAPL, TSM
            curr_date (str): current date in yyyy-mm-dd format to get news for
        Returns:
            str: A formatted dataframe containing the latest news about the company on the given date
        """

        stock_news_results = interface.get_reddit_company_news(ticker, curr_date, 7, 5)

        return stock_news_results

    @staticmethod
    @tool
    def get_chinese_social_sentiment(
        ticker: Annotated[str, "Ticker of a company. e.g. AAPL, TSM"],
        curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    ) -> str:
        """
        Get sentiment analysis and discussion about specific stocks on Chinese social media and financial platforms.
        Integrate data from local Chinese platforms such as Snowball, Oriental Fortune Stock Bar, and Sina Finance.
        Args:
            ticker (str): Stock code, such as AAPL, TSM
            curr_date (str): The current date in the format yyyy-mm-dd
        Returns:
            str: Formatted report including Chinese investor sentiment analysis, discussion intensity, and key points
        """
        try:
            # Data from multiple Chinese platforms can be integrated here
            chinese_sentiment_results = interface.get_chinese_social_sentiment(ticker, curr_date)
            return chinese_sentiment_results
        except Exception as e:
            # If the Chinese platform data acquisition fails, fall back to the original Reddit data
            return interface.get_reddit_company_news(ticker, curr_date, 7, 5)

    @staticmethod
    # @tool  # Removed: please use get_stock_fundamentals_unified or get_stock_market_data_unified
    def get_china_stock_data(
        stock_code: Annotated[str, "Chinese stock code, such as 000001(Ping An Bank), 600519(Kweichow Moutai)"],
        start_date: Annotated[str, "start date, format yyyy-mm-dd"],
        end_date: Annotated[str, "end date, format yyyy-mm-dd"],
    ) -> str:
        """
        Get real-time and historical data on China A-shares, and provide professional stock data through high-quality data sources such as Tushare.
        Supports comprehensive data such as real-time market conditions, historical K-lines, and technical indicators, and automatically uses the best data sources.
        Args:
            stock_code (str): Chinese stock code, such as 000001(Ping An Bank), 600519(Kweichow Moutai)
            start_date (str): start date, format yyyy-mm-dd
            end_date (str): end date, format yyyy-mm-dd
        Returns:
            str: Complete stock analysis report including real-time market conditions, historical data, and technical indicators
        """
        try:
            logger.debug(f"📊 [DEBUG] ===== agent_utils.get_china_stock_data Start calling =====")
            logger.debug(f"📊 [DEBUG] parameters: stock_code={stock_code}, start_date={start_date}, end_date={end_date}")

            from tradingagents.dataflows.interface import get_china_stock_data_unified
            logger.debug(f"📊 [DEBUG] Successfully imported unified data source interface")

            logger.debug(f"📊 [DEBUG] Calling the unified data source interface...")
            result = get_china_stock_data_unified(stock_code, start_date, end_date)

            logger.debug(f"📊 [DEBUG] Unified data source interface call completed")
            logger.debug(f"📊 [DEBUG] Return result type: {type(result)}")
            logger.debug(f"📊 [DEBUG] Return result length: {len(result) if result else 0}")
            logger.debug(f"📊 [DEBUG] Return the first 200 characters of the result: {str(result)[:200]}...")
            logger.debug(f"📊 [DEBUG] ===== agent_utils.get_china_stock_data end of call =====")

            return result
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"❌ [DEBUG] ===== agent_utils.get_china_stock_data Abnormal =====")
            logger.error(f"❌ [DEBUG] Error type: {type(e).__name__}")
            logger.error(f"❌ [DEBUG] error message: {str(e)}")
            logger.error(f"❌ [DEBUG] Detailed stack:")
            print(error_details)
            logger.error(f"❌ [DEBUG] ===== Exception handling ends =====")
            return f"中国股票数据获取失败: {str(e)}。请检查网络连接或稍后重试。"

    @staticmethod
    @tool
    def get_china_market_overview(
        curr_date: Annotated[str, "current date, format yyyy-mm-dd"],
    ) -> str:
        """
        Get a comprehensive overview of the Chinese stock market, including real-time quotes from major indices.
        Covers major indices such as Shanghai Composite Index, Shenzhen Composite Component Index, GEM Index, and Science and Technology Innovation 50 Index.
        Args:
            curr_date (str): current date, format yyyy-mm-dd
        Returns:
            str: Market overview report containing real-time quotes of major indices
        """
        try:
            # Get major index data using Tushare
            from tradingagents.dataflows.providers.china.tushare import get_tushare_adapter

            adapter = get_tushare_adapter()


            # Get major index information using Tushare
            # This can be expanded to obtain specific index data
            return f"""# 中国股市概览 - {curr_date}

## 📊 主要指数
- 上证指数: 数据获取中...
- 深证成指: 数据获取中...
- 创业板指: 数据获取中...
- 科创50: 数据获取中...

## 💡 说明
市场概览功能正在从TDX迁移到Tushare，完整功能即将推出。
当前可以使用股票数据获取功能分析个股。

数据来源: Tushare专业数据源
更新时间: {curr_date}
"""

        except Exception as e:
            return f"中国市场概览获取失败: {str(e)}。正在从TDX迁移到Tushare数据源。"

    @staticmethod
    @tool
    def get_YFin_data(
        symbol: Annotated[str, "ticker symbol of the company"],
        start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
        end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    ) -> str:
        """
        Retrieve the stock price data for a given ticker symbol from Yahoo Finance.
        Args:
            symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
            start_date (str): Start date in yyyy-mm-dd format
            end_date (str): End date in yyyy-mm-dd format
        Returns:
            str: A formatted dataframe containing the stock price data for the specified ticker symbol in the specified date range.
        """

        result_data = interface.get_YFin_data(symbol, start_date, end_date)

        return result_data

    @staticmethod
    @tool
    def get_YFin_data_online(
        symbol: Annotated[str, "ticker symbol of the company"],
        start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
        end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    ) -> str:
        """
        Retrieve the stock price data for a given ticker symbol from Yahoo Finance.
        Args:
            symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
            start_date (str): Start date in yyyy-mm-dd format
            end_date (str): End date in yyyy-mm-dd format
        Returns:
            str: A formatted dataframe containing the stock price data for the specified ticker symbol in the specified date range.
        """

        result_data = interface.get_YFin_data_online(symbol, start_date, end_date)

        return result_data

    @staticmethod
    @tool
    def get_stockstats_indicators_report(
        symbol: Annotated[str, "ticker symbol of the company"],
        indicator: Annotated[
            str, "technical indicator to get the analysis and report of"
        ],
        curr_date: Annotated[
            str, "The current trading date you are trading on, YYYY-mm-dd"
        ],
        look_back_days: Annotated[int, "how many days to look back"] = 30,
    ) -> str:
        """
        Retrieve stock stats indicators for a given ticker symbol and indicator.
        Args:
            symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
            indicator (str): Technical indicator to get the analysis and report of
            curr_date (str): The current trading date you are trading on, YYYY-mm-dd
            look_back_days (int): How many days to look back, default is 30
        Returns:
            str: A formatted dataframe containing the stock stats indicators for the specified ticker symbol and indicator.
        """

        result_stockstats = interface.get_stock_stats_indicators_window(
            symbol, indicator, curr_date, look_back_days, False
        )

        return result_stockstats

    @staticmethod
    @tool
    def get_stockstats_indicators_report_online(
        symbol: Annotated[str, "ticker symbol of the company"],
        indicator: Annotated[
            str, "technical indicator to get the analysis and report of"
        ],
        curr_date: Annotated[
            str, "The current trading date you are trading on, YYYY-mm-dd"
        ],
        look_back_days: Annotated[int, "how many days to look back"] = 30,
    ) -> str:
        """
        Retrieve stock stats indicators for a given ticker symbol and indicator.
        Args:
            symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
            indicator (str): Technical indicator to get the analysis and report of
            curr_date (str): The current trading date you are trading on, YYYY-mm-dd
            look_back_days (int): How many days to look back, default is 30
        Returns:
            str: A formatted dataframe containing the stock stats indicators for the specified ticker symbol and indicator.
        """

        result_stockstats = interface.get_stock_stats_indicators_window(
            symbol, indicator, curr_date, look_back_days, True
        )

        return result_stockstats

    @staticmethod
    @tool
    def get_finnhub_company_insider_sentiment(
        ticker: Annotated[str, "ticker symbol for the company"],
        curr_date: Annotated[
            str,
            "current date of you are trading at, yyyy-mm-dd",
        ],
    ):
        """
        Retrieve insider sentiment information about a company (retrieved from public SEC information) for the past 30 days
        Args:
            ticker (str): ticker symbol of the company
            curr_date (str): current date you are trading at, yyyy-mm-dd
        Returns:
            str: a report of the sentiment in the past 30 days starting at curr_date
        """

        data_sentiment = interface.get_finnhub_company_insider_sentiment(
            ticker, curr_date, 30
        )

        return data_sentiment

    @staticmethod
    @tool
    def get_finnhub_company_insider_transactions(
        ticker: Annotated[str, "ticker symbol"],
        curr_date: Annotated[
            str,
            "current date you are trading at, yyyy-mm-dd",
        ],
    ):
        """
        Retrieve insider transaction information about a company (retrieved from public SEC information) for the past 30 days
        Args:
            ticker (str): ticker symbol of the company
            curr_date (str): current date you are trading at, yyyy-mm-dd
        Returns:
            str: a report of the company's insider transactions/trading information in the past 30 days
        """

        data_trans = interface.get_finnhub_company_insider_transactions(
            ticker, curr_date, 30
        )

        return data_trans

    @staticmethod
    @tool
    def get_simfin_balance_sheet(
        ticker: Annotated[str, "ticker symbol"],
        freq: Annotated[
            str,
            "reporting frequency of the company's financial history: annual/quarterly",
        ],
        curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
    ):
        """
        Retrieve the most recent balance sheet of a company
        Args:
            ticker (str): ticker symbol of the company
            freq (str): reporting frequency of the company's financial history: annual / quarterly
            curr_date (str): current date you are trading at, yyyy-mm-dd
        Returns:
            str: a report of the company's most recent balance sheet
        """

        data_balance_sheet = interface.get_simfin_balance_sheet(ticker, freq, curr_date)

        return data_balance_sheet

    @staticmethod
    @tool
    def get_simfin_cashflow(
        ticker: Annotated[str, "ticker symbol"],
        freq: Annotated[
            str,
            "reporting frequency of the company's financial history: annual/quarterly",
        ],
        curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
    ):
        """
        Retrieve the most recent cash flow statement of a company
        Args:
            ticker (str): ticker symbol of the company
            freq (str): reporting frequency of the company's financial history: annual / quarterly
            curr_date (str): current date you are trading at, yyyy-mm-dd
        Returns:
                str: a report of the company's most recent cash flow statement
        """

        data_cashflow = interface.get_simfin_cashflow(ticker, freq, curr_date)

        return data_cashflow

    @staticmethod
    @tool
    def get_simfin_income_stmt(
        ticker: Annotated[str, "ticker symbol"],
        freq: Annotated[
            str,
            "reporting frequency of the company's financial history: annual/quarterly",
        ],
        curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
    ):
        """
        Retrieve the most recent income statement of a company
        Args:
            ticker (str): ticker symbol of the company
            freq (str): reporting frequency of the company's financial history: annual / quarterly
            curr_date (str): current date you are trading at, yyyy-mm-dd
        Returns:
                str: a report of the company's most recent income statement
        """

        data_income_stmt = interface.get_simfin_income_statements(
            ticker, freq, curr_date
        )

        return data_income_stmt

    @staticmethod
    @tool
    def get_google_news(
        query: Annotated[str, "Query to search with"],
        curr_date: Annotated[str, "Curr date in yyyy-mm-dd format"],
    ):
        """
        Retrieve the latest news from Google News based on a query and date range.
        Args:
            query (str): Query to search with
            curr_date (str): Current date in yyyy-mm-dd format
            look_back_days (int): How many days to look back
        Returns:
            str: A formatted string containing the latest news from Google News based on the query and date range.
        """

        google_news_results = interface.get_google_news(query, curr_date, 7)

        return google_news_results

    @staticmethod
    @tool
    def get_realtime_stock_news(
        ticker: Annotated[str, "Ticker of a company. e.g. AAPL, TSM"],
        curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    ) -> str:
        """
        Get real-time news analysis of stocks and solve the lag problem of traditional news sources.
        Integrate multiple professional financial APIs to provide the latest news within 15-30 minutes.
        Supports multiple news source polling mechanisms, giving priority to real-time news aggregators and automatically trying alternative news sources if they fail.
        For A-shares and Hong Kong stocks, Chinese financial news sources (such as Oriental Fortune) will be used first.
        
        Args:
            ticker (str): Stock code, such as AAPL, TSM, 600036.SH
            curr_date (str): The current date in the format yyyy-mm-dd
        Returns:
            str: Formatted reports including real-time news analysis, urgency assessment, and timeliness statements
        """
        from tradingagents.dataflows.realtime_news_utils import get_realtime_stock_news
        return get_realtime_stock_news(ticker, curr_date, hours_back=6)

    @staticmethod
    @tool
    def get_stock_news_openai(
        ticker: Annotated[str, "the company's ticker"],
        curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    ):
        """
        Retrieve the latest news about a given stock by using OpenAI's news API.
        Args:
            ticker (str): Ticker of a company. e.g. AAPL, TSM
            curr_date (str): Current date in yyyy-mm-dd format
        Returns:
            str: A formatted string containing the latest news about the company on the given date.
        """

        openai_news_results = interface.get_stock_news_openai(ticker, curr_date)

        return openai_news_results

    @staticmethod
    @tool
    def get_global_news_openai(
        curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    ):
        """
        Retrieve the latest macroeconomics news on a given date using OpenAI's macroeconomics news API.
        Args:
            curr_date (str): Current date in yyyy-mm-dd format
        Returns:
            str: A formatted string containing the latest macroeconomic news on the given date.
        """

        openai_news_results = interface.get_global_news_openai(curr_date)

        return openai_news_results

    @staticmethod
    # @tool  # Removed: Please use get_stock_fundamentals_unified
    def get_fundamentals_openai(
        ticker: Annotated[str, "the company's ticker"],
        curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    ):
        """
        Retrieve the latest fundamental information about a given stock on a given date by using OpenAI's news API.
        Args:
            ticker (str): Ticker of a company. e.g. AAPL, TSM
            curr_date (str): Current date in yyyy-mm-dd format
        Returns:
            str: A formatted string containing the latest fundamental information about the company on the given date.
        """
        logger.debug(f"📊 [DEBUG] get_fundamentals_openai called: ticker={ticker}, date={curr_date}")

        # Check if it is a Chinese stock
        import re
        if re.match(r'^\d{6}$', str(ticker)):
            logger.debug(f"📊 [DEBUG] China A share code detected: {ticker}")
            # Use unified interface to obtain Chinese stock names
            try:
                from tradingagents.dataflows.interface import get_china_stock_info_unified
                stock_info = get_china_stock_info_unified(ticker)

                # Parse stock names
                if "股票名称:" in stock_info:
                    company_name = stock_info.split("股票名称:")[1].split("\n")[0].strip()
                else:
                    company_name = f"股票代码{ticker}"

                logger.debug(f"📊 [DEBUG] Chinese stock name mapping: {ticker} -> {company_name}")
            except Exception as e:
                logger.error(f"⚠️ [DEBUG] Failed to obtain stock name from unified interface: {e}")
                company_name = f"股票代码{ticker}"

            # Modify query to include correct company name
            modified_query = f"{company_name}({ticker})"
            logger.debug(f"📊 [DEBUG] Modified query: {modified_query}")
        else:
            logger.debug(f"📊 [DEBUG] Non-Chinese stocks detected: {ticker}")
            modified_query = ticker

        try:
            openai_fundamentals_results = interface.get_fundamentals_openai(
                modified_query, curr_date
            )
            logger.debug(f"📊 [DEBUG] OpenAI Fundamental analysis result length: {len(openai_fundamentals_results) if openai_fundamentals_results else 0}")
            return openai_fundamentals_results
        except Exception as e:
            logger.error(f"❌ [DEBUG] OpenAI Fundamental analysis failed: {str(e)}")
            return f"基本面分析失败: {str(e)}"

    @staticmethod
    # @tool  # Removed: Please use get_stock_fundamentals_unified
    def get_china_fundamentals(
        ticker: Annotated[str, "China A-share stock code, such as 600036"],
        curr_date: Annotated[str, "The current date in the format yyyy-mm-dd"],
    ):
        """
        Obtain fundamental information on Chinese A-share stocks using the Chinese stock data source.
        Args:
            ticker (str): China A-share stock code, such as 600036, 000001
            curr_date (str): The current date in the format yyyy-mm-dd
        Returns:
            str: Formatted string containing stock fundamental information
        """
        logger.debug(f"📊 [DEBUG] get_china_fundamentals called: ticker={ticker}, date={curr_date}")

        # Check if it is a Chinese stock
        import re
        if not re.match(r'^\d{6}$', str(ticker)):
            return f"Error:{ticker} Not a valid China A share code format"

        try:
            # Use the unified data source interface to obtain stock data (default is Tushare, supports alternative data sources)
            from tradingagents.dataflows.interface import get_china_stock_data_unified
            logger.debug(f"📊 [DEBUG] 正在获取 {ticker} 的股票数据...")

            # Get the last 30 days of data for fundamental analysis
            from datetime import datetime, timedelta
            # Handles date strings that may contain time (e.g. "2026-01-14 00:00:00") 
            curr_date_clean = curr_date.split()[0] if ' ' in curr_date else curr_date
            end_date = datetime.strptime(curr_date_clean, '%Y-%m-%d')
            start_date = end_date - timedelta(days=30)

            stock_data = get_china_stock_data_unified(
                ticker,
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d')
            )

            logger.debug(f"📊 [DEBUG] Stock data acquisition completed, length: {len(stock_data) if stock_data else 0}")

            if not stock_data or "获取失败" in stock_data or "❌" in stock_data:
                return f"无法获取股票 {ticker} 的基本面数据：{stock_data}"

            # Calling true fundamental analysis
            from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

            # Create analyzer instance
            analyzer = OptimizedChinaDataProvider()

            # Generate true fundamental analysis reports
            fundamentals_report = analyzer._generate_fundamentals_report(ticker, stock_data)

            logger.debug(f"📊 [DEBUG] China fundamental analysis report is generated")
            logger.debug(f"📊 [DEBUG] get_china_fundamentals Result length: {len(fundamentals_report)}")

            return fundamentals_report

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"❌ [DEBUG] get_china_fundamentals failed:")
            logger.error(f"❌ [DEBUG] Error: {str(e)}")
            logger.error(f"❌ [DEBUG] stack: {error_details}")
            return f"中国股票基本面分析失败: {str(e)}"

    @staticmethod
    # @tool  # Removed: please use get_stock_fundamentals_unified or get_stock_market_data_unified
    def get_hk_stock_data_unified(
        symbol: Annotated[str, "Hong Kong stock code, such as: 0700.HK, 9988.HK, etc."],
        start_date: Annotated[str, "Start date, format:YYYY-MM-DD"],
        end_date: Annotated[str, "End date, format:YYYY-MM-DD"]
    ) -> str:
        """
        A unified interface for obtaining Hong Kong stock data, priority is given to AKShare data source, and backup is used.Yahoo Finance

        Args:
            symbol: Hong Kong stock code (Such as: 0700.HK)
            start_date: start date (YYYY-MM-DD)
            end_date: end date (YYYY-MM-DD)

        Returns:
            str: Formatted Hong Kong stock data
        """
        logger.debug(f"🇭🇰 [DEBUG] get_hk_stock_data_unified called: symbol={symbol}, start_date={start_date}, end_date={end_date}")

        try:
            from tradingagents.dataflows.interface import get_hk_stock_data_unified

            result = get_hk_stock_data_unified(symbol, start_date, end_date)

            logger.debug(f"🇭🇰 [DEBUG] Hong Kong stock data acquisition completed, length: {len(result) if result else 0}")

            return result

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"❌ [DEBUG] get_hk_stock_data_unified failed:")
            logger.error(f"❌ [DEBUG] Error: {str(e)}")
            logger.error(f"❌ [DEBUG] stack: {error_details}")
            return f"港股数据获取失败: {str(e)}"

    @staticmethod
    @tool
    @log_tool_call(tool_name="get_stock_fundamentals_unified", log_args=True)
    def get_stock_fundamentals_unified(
        ticker: Annotated[str, "Stock code (supports A shares, Hong Kong stocks, and US stocks)"],
        start_date: Annotated[str, "Start date, format:YYYY-MM-DD"] = None,
        end_date: Annotated[str, "End date, format:YYYY-MM-DD"] = None,
        curr_date: Annotated[str, "Current date, format:YYYY-MM-DD"] = None
    ) -> str:
        """
        Unified stock fundamental analysis tool
        Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call the corresponding data sources
        Support data acquisition strategies based on analysis level

        Args:
            ticker: Stock code (such as: 000001, 0700.HK, AAPL)
            start_date: Start date (optional, format: YYYY-MM-DD)
            end_date: End date (optional, format: YYYY-MM-DD)
            curr_date: Current date (optional, format: YYYY-MM-DD)

        Returns:
            str: Fundamental Analysis Data and Reports
        """
        logger.info(f"📊 [Unified fundamental tools] Analyze stocks: {ticker}")

        # 🔧 Get analysis level configuration, support level-based data acquisition strategy
        research_depth = Toolkit._config.get('research_depth', '标准')
        logger.info(f"🔧 [level of analysis] Current analysis level: {research_depth}")
        
        # Mapping of numerical grades to Chinese grades
        numeric_to_chinese = {
            1: "快速",
            2: "基础", 
            3: "标准",
            4: "深度",
            5: "全面"
        }
        
        # Standardization Research Depth: Support Numeric Input
        if isinstance(research_depth, (int, float)):
            research_depth = int(research_depth)
            if research_depth in numeric_to_chinese:
                chinese_depth = numeric_to_chinese[research_depth]
                logger.info(f"🔢 [等级转换] 数字等级 {research_depth} → 中文等级 '{chinese_depth}'")
                research_depth = chinese_depth
            else:
                logger.warning(f"⚠️ 无效的数字等级: {research_depth}，使用默认标准分析")
                research_depth = "标准"
        elif isinstance(research_depth, str):
            # If it is a number in string form, convert it to an integer
            if research_depth.isdigit():
                numeric_level = int(research_depth)
                if numeric_level in numeric_to_chinese:
                    chinese_depth = numeric_to_chinese[numeric_level]
                    logger.info(f"🔢 [等级转换] 字符串数字 '{research_depth}' → 中文等级 '{chinese_depth}'")
                    research_depth = chinese_depth
                else:
                    logger.warning(f"⚠️ Invalid string numeric level: {research_depth}, Analyze using default criteria")
                    research_depth = "标准"
            # If you are already at Chinese level, use it directly
            elif research_depth in ["快速", "基础", "标准", "深度", "全面"]:
                logger.info(f"📝 [Level confirmation] Use Chinese level: '{research_depth}'")
            else:
                logger.warning(f"⚠️ 未知的研究深度: {research_depth}，使用默认标准分析")
                research_depth = "标准"
        else:
            logger.warning(f"⚠️ Invalid research depth type: {type(research_depth)}, Analyze using default criteria")
            research_depth = "标准"
        
        # Adjust data acquisition strategies based on level of analysis
        # 🔧 Correct the mapping relationship: data_depth should be consistent with research_depth
        if research_depth == "快速":
            # Quick analysis: obtain basic data and reduce data source calls
            data_depth = "basic"
            logger.info(f"🔧 [level of analysis] Quick analysis mode: Obtain basic data")
        elif research_depth == "基础":
            # Basic Analysis: Obtaining Standard Data
            data_depth = "standard"
            logger.info(f"🔧 [level of analysis] Basic analysis mode: obtaining standard data")
        elif research_depth == "标准":
            # Standard analysis: Get standard data (not full!)
            data_depth = "standard"
            logger.info(f"🔧 [level of analysis] Standard Analysis Mode: Obtaining Standard Data")
        elif research_depth == "深度":
            # In-depth analysis: Get complete data
            data_depth = "full"
            logger.info(f"🔧 [level of analysis] Deep Analysis Mode: Get Complete Data")
        elif research_depth == "全面":
            # Comprehensive analysis: Get the most comprehensive data from all available data sources
            data_depth = "comprehensive"
            logger.info(f"🔧 [level of analysis] Comprehensive analysis mode: obtain the most comprehensive data")
        else:
            # Use standard analysis by default
            data_depth = "standard"
            logger.info(f"🔧 [level of analysis] Unknown level, use standard analysis mode")

        # Add detailed ticker tracking logs
        logger.info(f"🔍 [股票代码追踪] 统一基本面工具接收到的原始股票代码: '{ticker}' (类型: {type(ticker)})")
        logger.info(f"🔍 [Stock symbol tracking] Stock symbol length: {len(str(ticker))}")
        logger.info(f"🔍 [Stock symbol tracking] ticker character: {list(str(ticker))}")

        # Save the original ticker for comparison
        original_ticker = ticker

        try:
            from tradingagents.utils.stock_utils import StockUtils
            from datetime import datetime, timedelta

            # Automatically identify stock types
            market_info = StockUtils.get_market_info(ticker)
            is_china = market_info['is_china']
            is_hk = market_info['is_hk']
            is_us = market_info['is_us']

            logger.info(f"🔍 [Stock symbol tracking] StockUtils.get_market_info Returned market information: {market_info}")
            logger.info(f"📊 [Unified fundamental tools] Stock type: {market_info['market_name']}")
            logger.info(f"📊 [Unified fundamental tools] Currency: {market_info['currency_name']} ({market_info['currency_symbol']})")

            # Check if the ticker has changed during processing
            if str(ticker) != str(original_ticker):
                logger.warning(f"🔍 [股票代码追踪] 警告：股票代码发生了变化！原始: '{original_ticker}' -> 当前: '{ticker}'")

            # Set default date
            if not curr_date:
                curr_date = datetime.now().strftime('%Y-%m-%d')
        
            # Fundamental analysis optimization: no need for a large amount of historical data, only current prices and financial data
            # Set different number of analysis modules based on data depth level, not historical data range
            # 🔧 Correct mapping relationship: analysis_modules should be consistent with data_depth
            if data_depth == "basic":  # Quick Analysis: Basic Modules
                analysis_modules = "basic"
                logger.info(f"📊 [fundamental strategy] Quick analysis mode: Obtain basic financial indicators")
            elif data_depth == "standard":  # Basic/Standard Analysis: Standard Modules
                analysis_modules = "standard"
                logger.info(f"📊 [fundamental strategy] Standard Analysis Mode: Get Standard Financial Analysis")
            elif data_depth == "full":  # In-Depth Analysis: Complete Module
                analysis_modules = "full"
                logger.info(f"📊 [fundamental strategy] In-Depth Analysis Mode: Get complete fundamental analysis")
            elif data_depth == "comprehensive":  # Comprehensive Analysis: Comprehensive Module
                analysis_modules = "comprehensive"
                logger.info(f"📊 [fundamental strategy] Comprehensive Analysis Mode: Get comprehensive fundamental analysis")
            else:
                analysis_modules = "standard"  # Default standard analysis
                logger.info(f"📊 [fundamental strategy] Default mode: Get standard fundamental analysis")
            
            # Fundamental analysis strategy:
            # 1. Get 10 days of data (guaranteed to get data, handle weekends/holidays)
            # 2. Only use the last 2 days of data to participate in the analysis (only the current price)
            days_to_fetch = 10  # Fixed acquisition of 10 days of data
            days_to_analyze = 2  # Only analyze the last 2 days

            logger.info(f"📅 [基本面策略] 获取{days_to_fetch}天数据，分析最近{days_to_analyze}天")

            if not start_date:
                start_date = (datetime.now() - timedelta(days=days_to_fetch)).strftime('%Y-%m-%d')

            if not end_date:
                end_date = curr_date

            result_data = []

            if is_china:
                # China A-shares: Fundamental Analysis Optimization Strategy - Get only the necessary current price and fundamental data
                logger.info(f"🇨🇳 [Unified fundamental tools] Processing A-share data, data depth: {data_depth}...")
                logger.info(f"🔍 [Stock symbol tracking] Enter the A-share processing branch,ticker: '{ticker}'")
                logger.info(f"💡 [Optimization strategy] Fundamental analysis only obtains current prices and financial data, but does not obtain historical daily data.")

                # Optimization strategy: Fundamental analysis does not require a large amount of historical daily data
                # Only obtain current stock price information (last 1-2 days is sufficient) and fundamental financial data
                try:
                    # Get the latest stock price information (only the last 1-2 days of data are required)
                    from datetime import datetime, timedelta
                    recent_end_date = curr_date
                    recent_start_date = (datetime.strptime(curr_date, '%Y-%m-%d') - timedelta(days=2)).strftime('%Y-%m-%d')

                    from tradingagents.dataflows.interface import get_china_stock_data_unified
                    logger.info(f"🔍 [Stock symbol tracking] Call get_china_stock_data_unified (only get the latest price), pass in parameters: ticker='{ticker}', start_date='{recent_start_date}', end_date='{recent_end_date}'")
                    current_price_data = get_china_stock_data_unified(ticker, recent_start_date, recent_end_date)

                    # 🔍 Debugging: Print the first 500 characters of the returned data
                    logger.info(f"🔍 [Fundamental tool debugging] A Stock price data return length: {len(current_price_data)}")
                    logger.info(f"🔍 [Fundamental tool debugging] A The first 500 characters of stock price data:\n{current_price_data[:500]}")

                    result_data.append(f"## A股当前价格信息\n{current_price_data}")
                except Exception as e:
                    logger.error(f"❌ [Fundamental tool debugging] A Failed to obtain stock price data: {e}")
                    result_data.append(f"## A Stock current price information\n Failed to obtain: {e}")
                    current_price_data = ""

                try:
                    # Obtain fundamental financial data (this is the core of fundamental analysis)
                    from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider
                    analyzer = OptimizedChinaDataProvider()
                    logger.info(f"🔍 [Stock symbol tracking] Call OptimizedChinaDataProvider._generate_fundamentals_report, passing in parameters: ticker='{ticker}', analysis_modules='{analysis_modules}'")

                    # Passing analysis module parameters to fundamental analysis methods
                    fundamentals_data = analyzer._generate_fundamentals_report(ticker, current_price_data, analysis_modules)

                    # 🔍 Debugging: Print the first 500 characters of the returned data
                    logger.info(f"🔍 [Fundamental tool debugging] A Stock fundamental data return length: {len(fundamentals_data)}")
                    logger.info(f"🔍 [Fundamental tool debugging] A The first 500 characters of stock fundamental data:\n{fundamentals_data[:500]}")

                    result_data.append(f"## A股基本面财务数据\n{fundamentals_data}")
                except Exception as e:
                    logger.error(f"❌ [Fundamental tool debugging] A Failed to obtain stock fundamental data: {e}")
                    result_data.append(f"## A Stock Fundamentals Financial Data\n Failed to obtain: {e}")

            elif is_hk:
                # Hong Kong stocks: Use AKShare data source to support multiple backup plans
                logger.info(f"🇭🇰 [Unified fundamental tools] Processing Hong Kong stock data, data depth: {data_depth}...")

                hk_data_success = False

                # 🔥 Unified strategy: Get complete data at all levels
                # Reason: The prompt words are unified. If the data is incomplete, it will cause LLM to analyze based on non-existent data (illusion)
                logger.info(f"🔍 [Hong Kong stock fundamentals] Unified strategy: get complete data (ignore data_depth parameter)")

                # Main data sources:AKShare
                try:
                    from tradingagents.dataflows.interface import get_hk_stock_data_unified
                    hk_data = get_hk_stock_data_unified(ticker, start_date, end_date)

                    # 🔍 Debugging: Print the first 500 characters of the returned data
                    logger.info(f"🔍 [Fundamental tool debugging] Hong Kong stock data return length: {len(hk_data)}")
                    logger.info(f"🔍 [Fundamental tool debugging] The first 500 characters of Hong Kong stock data:\n{hk_data[:500]}")

                    # Check data quality
                    if hk_data and len(hk_data) > 100 and "❌" not in hk_data:
                        result_data.append(f"## 港股数据\n{hk_data}")
                        hk_data_success = True
                        logger.info(f"✅ [Unified fundamental tools] The main data source of Hong Kong stocks is successful")
                    else:
                        logger.warning(f"⚠️ [Unified fundamental tools] The quality of Hong Kong stock market s main data sources is poor")

                except Exception as e:
                    logger.error(f"❌ [Fundamental tool debugging] Failed to obtain Hong Kong stock data: {e}")

                # Alternate Plan: Basic Hong Kong Stock Information
                if not hk_data_success:
                    try:
                        from tradingagents.dataflows.interface import get_hk_stock_info_unified
                        hk_info = get_hk_stock_info_unified(ticker)

                        basic_info = f"""## 港股基础信息

**股票代码**: {ticker}
**股票名称**: {hk_info.get('name', f'港股{ticker}')}
**交易货币**: 港币 (HK$)
**交易所**: 香港交易所 (HKG)
**数据源**: {hk_info.get('source', '基础信息')}

⚠️ 注意：详细的价格和财务数据暂时无法获取，建议稍后重试或使用其他数据源。

**基本面分析建议**：
- 建议查看公司最新财报
- 关注港股市场整体走势
- 考虑汇率因素对投资的影响
"""
                        result_data.append(basic_info)
                        logger.info(f"✅ [Unified fundamental tools] Hong Kong stock backup information successful")

                    except Exception as e2:
                        # final alternative
                        fallback_info = f"""## Hong Kong stock information (backup)

**Stock code**: {ticker}
**Stock type**: Hong Kong stocks
**trading currency**: Hong Kong dollar (HK$)
**exchange**: Hong Kong Exchange (HKG)

❌ Problem retrieving data: {str(e2)}

**Suggestions**: 
- Please try again later
- or use other data sources
- Check if the stock code format is correct
"""
                        result_data.append(fallback_info)
                        logger.error(f"❌ [Unified fundamental tools] All data sources for Hong Kong stocks failed: {e2}")

            else:
                # US stocks: using OpenAI/Finnhub data sources
                logger.info(f"🇺🇸 [Unified fundamental tools] Processing US stock data...")

                # 🔥 Unified strategy: Get complete data at all levels
                # Reason: The prompt words are unified. If the data is incomplete, it will cause LLM to analyze based on non-existent data (illusion)
                logger.info(f"🔍 [US stock fundamentals] Unified strategy: get complete data (ignore data_depth parameter)")

                try:
                    from tradingagents.dataflows.interface import get_fundamentals_openai
                    us_data = get_fundamentals_openai(ticker, curr_date)
                    result_data.append(f"## 美股基本面数据\n{us_data}")
                    logger.info(f"✅ [Unified fundamental tools] US stock data obtained successfully")
                except Exception as e:
                    result_data.append(f"## U.S. stock fundamentals data\n Failed to obtain: {e}")
                    logger.error(f"❌ [Unified fundamental tools] Failed to obtain US stock data: {e}")

            # Combine all data
            combined_result = f"""# {ticker} 基本面分析数据

**股票类型**: {market_info['market_name']}
**货币**: {market_info['currency_name']} ({market_info['currency_symbol']})
**分析日期**: {curr_date}
**数据深度级别**: {data_depth}

{chr(10).join(result_data)}

---
*数据来源: 根据股票类型自动选择最适合的数据源*
"""

            # Add detailed data acquisition log
            logger.info(f"📊 [Unified fundamental tools] ===== Summary of data acquisition completion =====")
            logger.info(f"📊 [Unified fundamental tools] Stock code: {ticker}")
            logger.info(f"📊 [Unified fundamental tools] Stock type: {market_info['market_name']}")
            logger.info(f"📊 [Unified fundamental tools] Data depth level: {data_depth}")
            logger.info(f"📊 [Unified fundamental tools] Number of data modules obtained: {len(result_data)}")
            logger.info(f"📊 [统一基本面工具] 总数据长度: {len(combined_result)} 字符")
            
            # Record details of each data module
            for i, data_section in enumerate(result_data, 1):
                section_lines = data_section.split('\n')
                section_title = section_lines[0] if section_lines else "未知模块"
                section_length = len(data_section)
                logger.info(f"📊 [统一基本面工具] 数据模块 {i}: {section_title} ({section_length} 字符)")
                
                # If the data contains error information, mark it specifically
                if "获取失败" in data_section or "❌" in data_section:
                    logger.warning(f"⚠️ [统一基本面工具] 数据模块 {i} 包含错误信息")
                else:
                    logger.info(f"✅ [统一基本面工具] 数据模块 {i} 获取成功")
            
            # Record specific acquisition strategies based on data depth levels
            if data_depth in ["basic", "standard"]:
                logger.info(f"📊 [Unified fundamental tools] Basic/Standard Level Strategies: Get only core price data and basic information")
            elif data_depth in ["full", "detailed", "comprehensive"]:
                logger.info(f"📊 [Unified fundamental tools] Complete/Detailed/Comprehensive level strategies: Get price data + fundamental data")
            else:
                logger.info(f"📊 [Unified fundamental tools] Default policy: Get complete data")
            
            logger.info(f"📊 [Unified fundamental tools] ===== End of data acquisition summary =====")
            
            return combined_result

        except Exception as e:
            error_msg = f"Unified fundamental analysis tool execution failed: {str(e)}"
            logger.error(f"❌ [统一基本面工具] {error_msg}")
            return error_msg

    @staticmethod
    @tool
    @log_tool_call(tool_name="get_stock_market_data_unified", log_args=True)
    def get_stock_market_data_unified(
        ticker: Annotated[str, "Stock code (supports A shares, Hong Kong stocks, and US stocks)"],
        start_date: Annotated[str, "Start date, format: YYYY-MM-DD. Note: The system automatically expands to the configured number of lookback days (usually 365 days), you only need to pass the analysis date"],
        end_date: Annotated[str, "End date, format: YYYY-MM-DD. Usually the same as start_date, just pass the current analysis date"]
    ) -> str:
        """
        Unified stock market data tool
        Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call the corresponding data sources to obtain price and technical indicator data

        ⚠️ Important: The system automatically extends the date range to the configured number of lookback days (usually 365 days) to ensure there is sufficient historical data for technical indicator calculations.
        You only need to pass the current analysis date as start_date and end_date, no need to manually calculate the historical date range.

        Args:
            ticker: Stock code (such as: 000001, 0700.HK, AAPL)
            start_date: Start date (format: YYYY-MM-DD). Just pass the current analysis date and the system will automatically expand it.
            end_date: End date (format: YYYY-MM-DD). Just pass the current analysis date

        Returns:
            str: Market data and technical analysis reports

        Example:
            If the analysis date is 2025-11-09, pass:
            - ticker: "00700.HK"
            - start_date: "2025-11-09"
            - end_date: "2025-11-09"
            The system will automatically obtain 365 days of historical data from 2024-11-09 to 2025-11-09
        """
        import re

        # Standardized A-share code: remove the .SZ/.SH/.BJ suffix (the front and back ends use pure 6-digit numbers uniformly)
        original_ticker = ticker
        ticker = re.sub(r'\.(SZ|SH|BJ|sz|sh|bj)$', '', ticker.strip())
        if original_ticker != ticker:
            logger.info(f"📈 [unified market tools] Standardized stock code: {original_ticker} -> {ticker}")

        logger.info(f"📈 [unified market tools] Analyze stocks: {ticker}")

        try:
            from tradingagents.utils.stock_utils import StockUtils

            # Automatically identify stock types
            market_info = StockUtils.get_market_info(ticker)
            is_china = market_info['is_china']
            is_hk = market_info['is_hk']
            is_us = market_info['is_us']

            logger.info(f"📈 [unified market tools] Stock type: {market_info['market_name']}")
            logger.info(f"📈 [unified market tools] Currency: {market_info['currency_name']} ({market_info['currency_symbol']}")

            result_data = []

            if is_china:
                # China A Shares: Using China Stock Data Sources
                logger.info(f"🇨🇳 [unified market tools] Process A-share market data...")

                try:
                    from tradingagents.dataflows.interface import get_china_stock_data_unified
                    stock_data = get_china_stock_data_unified(ticker, start_date, end_date)

                    # 🔍 Debugging: Print the first 500 characters of the returned data
                    logger.info(f"🔍 [Market tool debugging] A Stock data return length: {len(stock_data)}")
                    logger.info(f"🔍 [Market tool debugging] A The first 500 characters of stock data:\n{stock_data[:500]}")

                    result_data.append(f"## A股市场数据\n{stock_data}")
                except Exception as e:
                    logger.error(f"❌ [Market tool debugging] A Failed to obtain stock data: {e}")
                    result_data.append(f"## A stock market data\n Failed to obtain: {e}")

            elif is_hk:
                # Hong Kong stocks: using AKShare data source
                logger.info(f"🇭🇰 [unified market tools] Process Hong Kong stock market data...")

                try:
                    from tradingagents.dataflows.interface import get_hk_stock_data_unified
                    hk_data = get_hk_stock_data_unified(ticker, start_date, end_date)

                    # 🔍 Debugging: Print the first 500 characters of the returned data
                    logger.info(f"🔍 [Market tool debugging] Hong Kong stock data return length: {len(hk_data)}")
                    logger.info(f"🔍 [Market tool debugging] The first 500 characters of Hong Kong stock data:\n{hk_data[:500]}")

                    result_data.append(f"## 港股市场数据\n{hk_data}")
                except Exception as e:
                    logger.error(f"❌ [Market tool debugging] Failed to obtain Hong Kong stock data: {e}")
                    result_data.append(f"## Hong Kong stock market data\n Failed to obtain: {e}")

            else:
                # US stocks: Prioritize the use of FINNHUB API data sources
                logger.info(f"🇺🇸 [unified market tools] Process U.S. stock market data...")

                try:
                    from tradingagents.dataflows.providers.us.optimized import get_us_stock_data_cached
                    us_data = get_us_stock_data_cached(ticker, start_date, end_date)
                    result_data.append(f"## 美股市场数据\n{us_data}")
                except Exception as e:
                    result_data.append(f"## US stock market data\n Failed to obtain: {e}")

            # Combine all data
            combined_result = f"""# {ticker} 市场数据分析

**股票类型**: {market_info['market_name']}
**货币**: {market_info['currency_name']} ({market_info['currency_symbol']})
**分析期间**: {start_date} 至 {end_date}

{chr(10).join(result_data)}

---
*数据来源: 根据股票类型自动选择最适合的数据源*
"""

            logger.info(f"📈 [unified market tools] Data acquisition completed, total length: {len(combined_result)}")
            return combined_result

        except Exception as e:
            error_msg = f"Unified market data tool execution failed: {str(e)}"
            logger.error(f"❌ [统一市场工具] {error_msg}")
            return error_msg

    @staticmethod
    @tool
    @log_tool_call(tool_name="get_stock_news_unified", log_args=True)
    def get_stock_news_unified(
        ticker: Annotated[str, "Stock code (supports A shares, Hong Kong stocks, and US stocks)"],
        curr_date: Annotated[str, "Current date, format:YYYY-MM-DD"]
    ) -> str:
        """
        Unified stock news tool
        Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call corresponding news data sources

        Args:
            ticker: Stock code (such as: 000001, 0700.HK, AAPL)
            curr_date: Current date (format: YYYY-MM-DD)

        Returns:
            str: News analysis report
        """
        logger.info(f"📰 [unified news tool] Analyze stocks: {ticker}")

        try:
            from tradingagents.utils.stock_utils import StockUtils
            from datetime import datetime, timedelta

            # Automatically identify stock types
            market_info = StockUtils.get_market_info(ticker)
            is_china = market_info['is_china']
            is_hk = market_info['is_hk']
            is_us = market_info['is_us']

            logger.info(f"📰 [unified news tool] Stock type: {market_info['market_name']}")

            # Calculate date range for news query
            end_date = datetime.strptime(curr_date, '%Y-%m-%d')
            start_date = end_date - timedelta(days=7)
            start_date_str = start_date.strftime('%Y-%m-%d')

            result_data = []

            if is_china or is_hk:
                # China A-shares and Hong Kong stocks: Use AKShare Oriental Fortune News and Google News (Chinese search)
                logger.info(f"🇨🇳🇭🇰 [unified news tool] Processing Chinese News...")

                # 1. Try to get AKShare Oriental Wealth News
                try:
                    # Handle stock symbols
                    clean_ticker = ticker.replace('.SH', '').replace('.SZ', '').replace('.SS', '')\
                                   .replace('.HK', '').replace('.XSHE', '').replace('.XSHG', '')
                    
                    logger.info(f"🇨🇳🇭🇰 [unified news tool] Try to get Oriental Fortune News: {clean_ticker}")

                    # Get news via AKShare Provider
                    from tradingagents.dataflows.providers.china.akshare import AKShareProvider

                    provider = AKShareProvider()

                    # Get Oriental Fortune News
                    news_df = provider.get_stock_news_sync(symbol=clean_ticker)

                    if news_df is not None and not news_df.empty:
                        # Formatted Oriental Fortune News
                        em_news_items = []
                        for _, row in news_df.iterrows():
                            # AKShare Returned field name
                            news_title = row.get('新闻标题', '') or row.get('标题', '')
                            news_time = row.get('发布时间', '') or row.get('时间', '')
                            news_url = row.get('新闻链接', '') or row.get('链接', '')

                            news_item = f"- **{news_title}** [{news_time}]({news_url})"
                            em_news_items.append(news_item)
                        
                        # Add to results
                        if em_news_items:
                            em_news_text = "\n".join(em_news_items)
                            result_data.append(f"## 东方财富新闻\n{em_news_text}")
                            logger.info(f"🇨🇳🇭🇰 [统一新闻工具] 成功获取{len(em_news_items)}条东方财富新闻")
                except Exception as em_e:
                    logger.error(f"❌ [unified news tool] Failed to obtain Oriental Fortune News: {em_e}")
                    result_data.append(f"## Oriental Fortune News\n Failed to obtain: {em_e}")

                # 2. Get Google News as a supplement
                try:
                    # Get the Chinese name of the company for search
                    if is_china:
                        # A Use stock code search to add more Chinese keywords
                        clean_ticker = ticker.replace('.SH', '').replace('.SZ', '').replace('.SS', '')\
                                       .replace('.XSHE', '').replace('.XSHG', '')
                        search_query = f"{clean_ticker} 股票 公司 财报 新闻"
                        logger.info(f"🇨🇳 [unified news tool] A Stock Google News search keywords: {search_query}")
                    else:
                        # Hong Kong stocks use code search
                        search_query = f"{ticker} 港股"
                        logger.info(f"🇭🇰 [unified news tool] Hong Kong stocks Google news search keywords: {search_query}")

                    from tradingagents.dataflows.interface import get_google_news
                    news_data = get_google_news(search_query, curr_date)
                    result_data.append(f"## Google新闻\n{news_data}")
                    logger.info(f"🇨🇳🇭🇰 [unified news tool] Successfully obtained Google News")
                except Exception as google_e:
                    logger.error(f"❌ [unified news tool] Google Failed to get news: {google_e}")
                    result_data.append(f"## Google News\n Failed to obtain: {google_e}")

            else:
                # US Stocks: Use Finnhub News
                logger.info(f"🇺🇸 [unified news tool] Handle US stock news...")

                try:
                    from tradingagents.dataflows.interface import get_finnhub_news
                    news_data = get_finnhub_news(ticker, start_date_str, curr_date)
                    result_data.append(f"## 美股新闻\n{news_data}")
                except Exception as e:
                    result_data.append(f"## US stock news\n Failed to obtain: {e}")

            # Combine all data
            combined_result = f"""# {ticker} 新闻分析

**股票类型**: {market_info['market_name']}
**分析日期**: {curr_date}
**新闻时间范围**: {start_date_str} 至 {curr_date}

{chr(10).join(result_data)}

---
*数据来源: 根据股票类型自动选择最适合的新闻源*
"""

            logger.info(f"📰 [unified news tool] Data acquisition completed, total length: {len(combined_result)}")
            return combined_result

        except Exception as e:
            error_msg = f"统一新闻工具执行失败: {str(e)}"
            logger.error(f"❌ [统一新闻工具] {error_msg}")
            return error_msg

    @staticmethod
    @tool
    @log_tool_call(tool_name="get_stock_news_headlines_unified", log_args=True)
    def get_stock_news_headlines_unified(
        ticker: Annotated[str, "Stock code (supports A shares, Hong Kong stocks, and US stocks)"],
        curr_date: Annotated[str, "Current date, format:YYYY-MM-DD"],
        limit: Annotated[int, "Number of title candidates returned, default 12"] = 12,
    ) -> str:
        """Legacy Toolkit bridge to the unified stock news headline tool."""
        try:
            from core.tools.implementations.news.stock_news import (
                get_stock_news_headlines_unified as core_headlines_tool,
            )

            if hasattr(core_headlines_tool, "invoke"):
                return core_headlines_tool.invoke(
                    {"ticker": ticker, "curr_date": curr_date, "limit": limit}
                )
            return core_headlines_tool(ticker=ticker, curr_date=curr_date, limit=limit)
        except Exception as e:
            error_msg = f"Unified news headline tool execution failed: {str(e)}"
            logger.error(f"❌ [Unified News Title Tool/Toolkit Bridge] {error_msg}")
            return error_msg

    @staticmethod
    @tool
    @log_tool_call(tool_name="get_stock_news_details_unified", log_args=True)
    def get_stock_news_details_unified(
        ticker: Annotated[str, "Stock code (supports A shares, Hong Kong stocks, and US stocks)"],
        curr_date: Annotated[str, "Current date, format:YYYY-MM-DD"],
        news_ids: Annotated[str, "To view detailed news_id, use commas to separate multiple ID"],
    ) -> str:
        """Legacy Toolkit bridge for unified stock news breakdown tool."""
        try:
            from core.tools.implementations.news.stock_news import (
                get_stock_news_details_unified as core_details_tool,
            )

            if hasattr(core_details_tool, "invoke"):
                return core_details_tool.invoke(
                    {"ticker": ticker, "curr_date": curr_date, "news_ids": news_ids}
                )
            return core_details_tool(ticker=ticker, curr_date=curr_date, news_ids=news_ids)
        except Exception as e:
            error_msg = f"Unified news detail tool execution failed: {str(e)}"
            logger.error(f"❌ [Unified News Detail Tool/Toolkit Bridge] {error_msg}")
            return error_msg

    @staticmethod
    @tool
    @log_tool_call(tool_name="get_stock_sentiment_unified", log_args=True)
    def get_stock_sentiment_unified(
        ticker: Annotated[str, "Stock code (supports A shares, Hong Kong stocks, and US stocks)"],
        curr_date: Annotated[str, "Current date, format:YYYY-MM-DD"]
    ) -> str:
        """
        Unified stock sentiment analysis tool
        Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call the corresponding sentiment data sources

        Args:
            ticker: Stock code (such as: 000001, 0700.HK, AAPL)
            curr_date: Current date (format: YYYY-MM-DD)

        Returns:
            str: Sentiment Analysis Report
        """
        logger.info(f"😊 [Unifying Emotion Tools] Analyze stocks: {ticker}")

        try:
            from tradingagents.utils.stock_utils import StockUtils

            # Automatically identify stock types
            market_info = StockUtils.get_market_info(ticker)
            is_china = market_info['is_china']
            is_hk = market_info['is_hk']
            is_us = market_info['is_us']

            logger.info(f"😊 [Unifying Emotion Tools] Stock type: {market_info['market_name']}")

            result_data = []

            if is_china or is_hk:
                # China A-shares and Hong Kong stocks: using social media sentiment analysis
                logger.info(f"🇨🇳🇭🇰 [Unifying Emotion Tools] Dealing with Chinese market sentiment...")

                try:
                    # Can integrate Chinese social media sentiments such as Weibo, Snowball, Oriental Fortune, etc.
                    # Currently using basic sentiment analysis
                    sentiment_summary = f"""
## Chinese market sentiment analysis

**stocks**: {ticker} ({market_info['market_name']})
**Analysis date**: {curr_date}

### Market sentiment overview
- Since Chinese social media sentiment data sources are not yet fully integrated, basic analysis is currently provided.
- It is recommended to pay attention to the discussion popularity on Snowball, Oriental Fortune, Tonghuashun and other platforms
- The Hong Kong stock market also needs to pay attention to the sentiment of Hong Kong s local financial media

### sentiment indicator
- overall mood: Neutral
- Discussion popularity: To be analyzed
- investor confidence: To be evaluated

*Note: The complete Chinese social media sentiment analysis function is under development*
"""
                    result_data.append(sentiment_summary)
                except Exception as e:
                    result_data.append(f"## Chinese market sentiment\n Failed to obtain: {e}")

            else:
                # US Stocks: Using Reddit Sentiment Analysis
                logger.info(f"🇺🇸 [Unifying Emotion Tools] Dealing with U.S. stock market sentiment...")

                try:
                    from tradingagents.dataflows.interface import get_reddit_sentiment

                    sentiment_data = get_reddit_sentiment(ticker, curr_date)
                    result_data.append(f"## US Stocks Reddit Sentiment\n{sentiment_data}")
                except Exception as e:
                    result_data.append(f"## US Stocks Reddit Sentiment\n Failed to obtain: {e}")

            # Combine all data
            combined_result = f"""# {ticker} 情绪分析

**股票类型**: {market_info['market_name']}
**分析日期**: {curr_date}

{chr(10).join(result_data)}

---
*数据来源: 根据股票类型自动选择最适合的情绪数据源*
"""

            logger.info(f"😊 [Unifying Emotion Tools] Data acquisition completed, total length: {len(combined_result)}")
            return combined_result

        except Exception as e:
            error_msg = f"Unified sentiment analysis tool execution failed: {str(e)}"
            logger.error(f"❌ [统一情绪工具] {error_msg}")
            return error_msg
