#!/usr/bin/env python3
"""
Unified News Analysis Tool
Integrate news acquisition logic from different markets such as A-shares, Hong Kong stocks, and US stocks into one tool function
Let large models only need to call one tool to obtain news data for all types of stocks

⚠️⚠️⚠️ DEPRECATED - Expired 8 days ⚠️⚠️⚠️
====================================
This tool has been migrated to the new tool system:
- new location: core/tools/implementations/news/stock_news.py
- Migration date: 2025-12-15
- Original planned removal date: 2026-06-15
- current date: 2026-06-23 (Expired)

Please use the new tool system:
    from core.tools.implementations.news import get_stock_news_unified

Or via the tool registry:
    from core.tools import get_tool
    tool = get_tool("get_stock_news_unified")

🔴 Urgent: There are still 11 files referencing this module, please migrate as soon as possible!
====================================
"""

import logging
import warnings
from datetime import datetime
import re

# 🔴 Issue deprecation warning (expired)
warnings.warn(
    "tradingagents.tools.unified_news_tool is DEPRECATED and EXPIRED "
    "(planned removal: 2026-06-15, now 2026-06-23). "
    "Please use core.tools.implementations.news.stock_news instead. "
    "11 files still reference this module - migration required before removal!",
    DeprecationWarning,
    stacklevel=2
)

logger = logging.getLogger(__name__)

class UnifiedNewsAnalyzer:
    """Unified news analyzer, integrating all news acquisition logic"""
    
    def __init__(self, toolkit):
        """Initialize unified news analyzer
        
        Args:
            toolkit: A toolkit containing various news acquisition tools
        """
        self.toolkit = toolkit
        
    def get_stock_news_unified(self, stock_code: str, max_news: int = 10, model_info: str = "") -> str:
        """
        Unified news acquisition interface
        Automatically identify stock types based on stock codes and obtain corresponding news
        
        Args:
            stock_code: Stock code
            max_news: Maximum number of news
            model_info: Currently used model information for special processing
            
        Returns:
            str: Formatted news content
        """
        logger.info(f"[unified news tool] Start getting {stock_code} news, models: {model_info}")
        logger.info(f"[unified news tool] 🤖 Current model information: {model_info}")
        
        # Identify stock type
        stock_type = self._identify_stock_type(stock_code)
        logger.info(f"[unified news tool] Stock type: {stock_type}")
        
        # Call the corresponding acquisition method according to the stock type
        if stock_type == "A股":
            result = self._get_a_share_news(stock_code, max_news, model_info)
        elif stock_type == "港股":
            result = self._get_hk_share_news(stock_code, max_news, model_info)
        elif stock_type == "美股":
            result = self._get_us_share_news(stock_code, max_news, model_info)
        else:
            # A-share logic is used by default
            result = self._get_a_share_news(stock_code, max_news, model_info)
        
        # 🔍 Add detailed results debug log
        logger.info(f"[统一新闻工具] 📊 新闻获取完成，结果长度: {len(result)} 字符")
        logger.info(f"[unified news tool] 📋 Return results preview (first 1000 characters): {result[:1000]}")
        
        # Log a warning if the result is empty or too short
        if not result or len(result.strip()) < 50:
            logger.warning(f"[unified news tool] ⚠️ The return result is abnormally short or empty!")
            logger.warning(f"[unified news tool] 📝 Full result content: '{result}'")
        
        return result
    
    def _identify_stock_type(self, stock_code: str) -> str:
        """识别股票类型"""
        stock_code = stock_code.upper().strip()
        
        # A stock judgment
        if re.match(r'^(00|30|60|68)\d{4}$', stock_code):
            return "A股"
        elif re.match(r'^(SZ|SH)\d{6}$', stock_code):
            return "A股"
        
        # Hong Kong stock judgment
        elif re.match(r'^\d{4,5}\.HK$', stock_code):
            return "港股"
        elif re.match(r'^\d{4,5}$', stock_code) and len(stock_code) <= 5:
            return "港股"
        
        # U.S. stock market judgment
        elif re.match(r'^[A-Z]{1,5}$', stock_code):
            return "美股"
        elif '.' in stock_code and not stock_code.endswith('.HK'):
            return "美股"
        
        # By default, it is processed as A shares
        else:
            return "A股"

    def _get_news_from_database(self, stock_code: str, max_news: int = 10) -> str:
        """
        Get news from database

        Args:
            stock_code: Stock code
            max_news: Maximum number of news

        Returns:
            str: Formatted news content, if there is no news, an empty string is returned
        """
        try:
            from tradingagents.dataflows.cache.app_adapter import get_mongodb_client
            from datetime import timedelta

            # 🔧 Make sure max_news is an integer (prevents passing in floating point numbers)
            max_news = int(max_news)

            client = get_mongodb_client()
            if not client:
                logger.warning(f"[unified news tool] Unable to connect to MongoDB")
                return ""

            db = client.get_database('tradingagents')
            collection = db.stock_news

            # Standardized stock symbol (remove suffix)
            clean_code = stock_code.replace('.SH', '').replace('.SZ', '').replace('.SS', '')\
                                   .replace('.XSHE', '').replace('.XSHG', '').replace('.HK', '')

            # Query the news of the last 30 days (expand the time range)
            thirty_days_ago = datetime.now() - timedelta(days=30)

            # Try multiple query methods (using symbol fields)
            query_list = [
                {'symbol': clean_code, 'publish_time': {'$gte': thirty_days_ago}},
                {'symbol': stock_code, 'publish_time': {'$gte': thirty_days_ago}},
                {'symbols': clean_code, 'publish_time': {'$gte': thirty_days_ago}},
                # If there is no news in the last 30 days, query all news (no time limit)
                {'symbol': clean_code},
                {'symbols': clean_code},
            ]

            news_items = []
            for query in query_list:
                cursor = collection.find(query).sort('publish_time', -1).limit(max_news)
                news_items = list(cursor)
                if news_items:
                    logger.info(f"[统一新闻工具] 📊 使用查询 {query} 找到 {len(news_items)} 条新闻")
                    break

            if not news_items:
                logger.info(f"[统一新闻工具] 数据库中没有找到 {stock_code} 的新闻")
                return ""

            # Format news
            report = f"# {stock_code} 最新新闻 (数据库缓存)\n\n"
            report += f"📅 查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            report += f"📊 新闻数量: {len(news_items)} 条\n\n"

            for i, news in enumerate(news_items, 1):
                title = news.get('title', '无标题')
                content = news.get('content', '') or news.get('summary', '')
                source = news.get('source', '未知来源')
                publish_time = news.get('publish_time', datetime.now())
                sentiment = news.get('sentiment', 'neutral')

                # Emotion icons
                sentiment_icon = {
                    'positive': '📈',
                    'negative': '📉',
                    'neutral': '➖'
                }.get(sentiment, '➖')

                report += f"## {i}. {sentiment_icon} {title}\n\n"
                report += f"**来源**: {source} | **时间**: {publish_time.strftime('%Y-%m-%d %H:%M') if isinstance(publish_time, datetime) else publish_time}\n"
                report += f"**情绪**: {sentiment}\n\n"

                if content:
                    # Limit content length
                    content_preview = content[:500] + '...' if len(content) > 500 else content
                    report += f"{content_preview}\n\n"

                report += "---\n\n"

            logger.info(f"[统一新闻工具] ✅ 成功从数据库获取并格式化 {len(news_items)} 条新闻")
            return report

        except Exception as e:
            logger.error(f"[unified news tool] Failed to get news from database: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ""

    def _sync_news_from_akshare(self, stock_code: str, max_news: int = 10) -> bool:
        """
        Synchronize news from AKShare to database (synchronization method)
        Use a synchronized database client and event loop in a new thread to avoid event loop conflicts

        Args:
            stock_code: Stock code
            max_news: Maximum number of news

        Returns:
            bool: Whether synchronization is successful
        """
        try:
            import asyncio
            import concurrent.futures

            # Standardized stock symbol (remove suffix)
            clean_code = stock_code.replace('.SH', '').replace('.SZ', '').replace('.SS', '')\
                                   .replace('.XSHE', '').replace('.XSHG', '').replace('.HK', '')

            logger.info(f"[统一新闻工具] 🔄 开始同步 {clean_code} 的新闻...")

            # 🔥 Run in a new thread, using a synchronous database client
            def run_sync_in_new_thread():
                """Create a new event loop in a new thread and run the sync task"""
                # Create a new event loop
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)

                try:
                    # Define asynchronous news retrieval task
                    async def get_news_task():
                        try:
                            # Dynamically import AKShare provider (correct import path)
                            from tradingagents.dataflows.providers.china.akshare import AKShareProvider

                            # Create provider instance
                            provider = AKShareProvider()

                            # Call provider to get news
                            news_data = await provider.get_stock_news(
                                symbol=clean_code,
                                limit=max_news
                            )

                            # API Current limiting: sleep after success
                            await asyncio.sleep(0.2)

                            return news_data

                        except Exception as e:
                            logger.error(f"[unified news tool] ❌ Failed to get news: {e}")
                            import traceback
                            logger.error(traceback.format_exc())

                            # Also sleep after failure to avoid"avalanche of failure"
                            # Sleep longer on failure to give the API server a chance to recover
                            await asyncio.sleep(1.0)

                            return None

                    # Get news in new event loop
                    news_data = new_loop.run_until_complete(get_news_task())

                    if not news_data:
                        logger.warning(f"[unified news tool] ⚠️ News data not obtained")
                        return False

                    logger.info(f"[统一新闻工具] 📥 获取到 {len(news_data)} 条新闻")

                    # 🔥 Save to database using synchronous method (not relying on event loop)
                    from app.services.news_data_service import NewsDataService

                    news_service = NewsDataService()
                    saved_count = news_service.save_news_data_sync(
                        news_data=news_data,
                        data_source="akshare",
                        market="CN"
                    )

                    logger.info(f"[统一新闻工具] ✅ 同步成功: {saved_count} 条新闻")
                    return saved_count > 0

                finally:
                    # Clean up the event loop
                    new_loop.close()

            # Execute in thread pool
            logger.info(f"[unified news tool] Run synchronized tasks in a new thread to avoid event loop conflicts")
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_sync_in_new_thread)
                result = future.result(timeout=30)  # 30 seconds timeout
                return result

        except concurrent.futures.TimeoutError:
            logger.error(f"[unified news tool] ❌ Sync news timeout (30 seconds)")
            return False
        except Exception as e:
            logger.error(f"[unified news tool] ❌ News synchronization failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _get_a_share_news(self, stock_code: str, max_news: int, model_info: str = "") -> str:
        """获取A股新闻"""
        logger.info(f"[统一新闻工具] 获取A股 {stock_code} 新闻")

        # Get current date
        curr_date = datetime.now().strftime("%Y-%m-%d")

        # priority 0: Get news from database (highest priority)
        try:
            logger.info(f"[统一新闻工具] 🔍 优先从数据库获取 {stock_code} 的新闻...")
            db_news = self._get_news_from_database(stock_code, max_news)
            if db_news:
                logger.info(f"[统一新闻工具] ✅ 数据库新闻获取成功: {len(db_news)} 字符")
                return self._format_news_result(db_news, "数据库缓存", model_info)
            else:
                logger.info(f"[unified news tool] ⚠️ Not in database {stock_code} news, try to sync...")

                # 🔥 When there is no data in the database, call the synchronization service to synchronize news
                try:
                    logger.info(f"[统一新闻工具] 📡 调用同步服务同步 {stock_code} 的新闻...")
                    synced_news = self._sync_news_from_akshare(stock_code, max_news)

                    if synced_news:
                        logger.info(f"[unified news tool] ✅ Synchronization successful, re-obtain from database...")
                        # Get again from database
                        db_news = self._get_news_from_database(stock_code, max_news)
                        if db_news:
                            logger.info(f"[统一新闻工具] ✅ 同步后数据库新闻获取成功: {len(db_news)} 字符")
                            return self._format_news_result(db_news, "数据库缓存(新同步)", model_info)
                    else:
                        logger.warning(f"[unified news tool] ⚠️ Sync service did not return news data")

                except Exception as sync_error:
                    logger.warning(f"[unified news tool] ⚠️ Synchronization service call failed: {sync_error}")

                logger.info(f"[unified news tool] ⚠️ There is still no data after synchronization, try other data sources....")
        except Exception as e:
            logger.warning(f"[unified news tool] Failed to obtain database news: {e}")

        # priority 1: Oriental Fortune real-time news
        try:
            if hasattr(self.toolkit, 'get_realtime_stock_news'):
                logger.info(f"[unified news tool] Try Oriental Fortune Live News...")
                # The correct way to call the LangChain tool:.invoke()Methods and dictionary parameters
                result = self.toolkit.get_realtime_stock_news.invoke({"ticker": stock_code, "curr_date": curr_date})
                
                # 🔍 Detailed records of the content returned by Oriental Fortune
                logger.info(f"[统一新闻工具] 📊 东方财富返回内容长度: {len(result) if result else 0} 字符")
                logger.info(f"[unified news tool] 📋 Oriental Fortune returns to content preview (first 500 characters): {result[:500] if result else 'None'}")
                
                if result and len(result.strip()) > 100:
                    logger.info(f"[统一新闻工具] ✅ 东方财富新闻获取成功: {len(result)} 字符")
                    return self._format_news_result(result, "东方财富实时新闻", model_info)
                else:
                    logger.warning(f"[unified news tool] ⚠️ Oriental Fortune news content is too short or empty")
        except Exception as e:
            logger.warning(f"[unified news tool] Failed to obtain Oriental Fortune News: {e}")
        
        # priority 2: Google News (Chinese search)
        try:
            if hasattr(self.toolkit, 'get_google_news'):
                logger.info(f"[unified news tool] Try Google News...")
                query = f"{stock_code} 股票 新闻 财报 业绩"
                # The correct way to call the LangChain tool:.invoke()Methods and dictionary parameters
                result = self.toolkit.get_google_news.invoke({"query": query, "curr_date": curr_date})
                if result and len(result.strip()) > 50:
                    logger.info(f"[统一新闻工具] ✅ Google新闻获取成功: {len(result)} 字符")
                    return self._format_news_result(result, "Google新闻", model_info)
        except Exception as e:
            logger.warning(f"[unified news tool] Google Failed to get news: {e}")
        
        # priority 3: OpenAI global news
        try:
            if hasattr(self.toolkit, 'get_global_news_openai'):
                logger.info(f"[unified news tool] Try OpenAI Global News...")
                # The correct way to call the LangChain tool:.invoke()Methods and dictionary parameters
                result = self.toolkit.get_global_news_openai.invoke({"curr_date": curr_date})
                if result and len(result.strip()) > 50:
                    logger.info(f"[统一新闻工具] ✅ OpenAI新闻获取成功: {len(result)} 字符")
                    return self._format_news_result(result, "OpenAI全球新闻", model_info)
        except Exception as e:
            logger.warning(f"[unified news tool] OpenAI Failed to get news: {e}")
        
        return "❌ Unable to obtain A-share news data, all news sources are unavailable"
    
    def _get_hk_share_news(self, stock_code: str, max_news: int, model_info: str = "") -> str:
        """获取港股新闻"""
        logger.info(f"[统一新闻工具] 获取港股 {stock_code} 新闻")
        
        # Get current date
        curr_date = datetime.now().strftime("%Y-%m-%d")
        
        # priority 1: Google News (Hong Kong stock search)
        try:
            if hasattr(self.toolkit, 'get_google_news'):
                logger.info(f"[unified news tool] Try Google Hong Kong stock news...")
                query = f"{stock_code} 港股 香港股票 新闻"
                # The correct way to call the LangChain tool:.invoke()Methods and dictionary parameters
                result = self.toolkit.get_google_news.invoke({"query": query, "curr_date": curr_date})
                if result and len(result.strip()) > 50:
                    logger.info(f"[统一新闻工具] ✅ Google港股新闻获取成功: {len(result)} 字符")
                    return self._format_news_result(result, "Google港股新闻", model_info)
        except Exception as e:
            logger.warning(f"[unified news tool] Google Failed to obtain Hong Kong stock news: {e}")
        
        # priority 2: OpenAI global news
        try:
            if hasattr(self.toolkit, 'get_global_news_openai'):
                logger.info(f"[unified news tool] Try OpenAI Hong Kong Stock News...")
                # The correct way to call the LangChain tool:.invoke()Methods and dictionary parameters
                result = self.toolkit.get_global_news_openai.invoke({"curr_date": curr_date})
                if result and len(result.strip()) > 50:
                    logger.info(f"[统一新闻工具] ✅ OpenAI港股新闻获取成功: {len(result)} 字符")
                    return self._format_news_result(result, "OpenAI港股新闻", model_info)
        except Exception as e:
            logger.warning(f"[unified news tool] OpenAI Failed to obtain Hong Kong stock news: {e}")
        
        # priority 3: Real-time news (if Hong Kong stocks are supported)
        try:
            if hasattr(self.toolkit, 'get_realtime_stock_news'):
                logger.info(f"[unified news tool] Try real-time Hong Kong stock news...")
                # The correct way to call the LangChain tool:.invoke()Methods and dictionary parameters
                result = self.toolkit.get_realtime_stock_news.invoke({"ticker": stock_code, "curr_date": curr_date})
                if result and len(result.strip()) > 100:
                    logger.info(f"[统一新闻工具] ✅ 实时港股新闻获取成功: {len(result)} 字符")
                    return self._format_news_result(result, "实时港股新闻", model_info)
        except Exception as e:
            logger.warning(f"[unified news tool] Failed to obtain real-time Hong Kong stock news: {e}")
        
        return "❌ Unable to obtain Hong Kong stock news data, all news sources are unavailable"
    
    def _get_us_share_news(self, stock_code: str, max_news: int, model_info: str = "") -> str:
        """获取美股新闻"""
        logger.info(f"[统一新闻工具] 获取美股 {stock_code} 新闻")
        
        # Get current date
        curr_date = datetime.now().strftime("%Y-%m-%d")
        
        # priority 1: OpenAI global news
        try:
            if hasattr(self.toolkit, 'get_global_news_openai'):
                logger.info(f"[unified news tool] Try OpenAI US Stock News...")
                # The correct way to call the LangChain tool:.invoke()Methods and dictionary parameters
                result = self.toolkit.get_global_news_openai.invoke({"curr_date": curr_date})
                if result and len(result.strip()) > 50:
                    logger.info(f"[统一新闻工具] ✅ OpenAI美股新闻获取成功: {len(result)} 字符")
                    return self._format_news_result(result, "OpenAI美股新闻", model_info)
        except Exception as e:
            logger.warning(f"[unified news tool] OpenAI Failed to obtain US stock news: {e}")
        
        # priority 2: Google News (search in English)
        try:
            if hasattr(self.toolkit, 'get_google_news'):
                logger.info(f"[unified news tool] Try Google US stock news...")
                query = f"{stock_code} stock news earnings financial"
                # The correct way to call the LangChain tool:.invoke()Methods and dictionary parameters
                result = self.toolkit.get_google_news.invoke({"query": query, "curr_date": curr_date})
                if result and len(result.strip()) > 50:
                    logger.info(f"[统一新闻工具] ✅ Google美股新闻获取成功: {len(result)} 字符")
                    return self._format_news_result(result, "Google美股新闻", model_info)
        except Exception as e:
            logger.warning(f"[unified news tool] Google Failed to obtain US stock news: {e}")
        
        # priority 3: FinnHub News (if available)
        try:
            if hasattr(self.toolkit, 'get_finnhub_news'):
                logger.info(f"[unified news tool] Try FinnHub US Stock News...")
                # The correct way to call the LangChain tool:.invoke()Methods and dictionary parameters
                result = self.toolkit.get_finnhub_news.invoke({"symbol": stock_code, "max_results": min(max_news, 50)})
                if result and len(result.strip()) > 50:
                    logger.info(f"[统一新闻工具] ✅ FinnHub美股新闻获取成功: {len(result)} 字符")
                    return self._format_news_result(result, "FinnHub美股新闻", model_info)
        except Exception as e:
            logger.warning(f"[unified news tool] FinnHub Failed to obtain US stock news: {e}")
        
        return "❌ Unable to obtain US stock news data, all news sources are unavailable"
    
    def _format_news_result(self, news_content: str, source: str, model_info: str = "") -> str:
        """格式化新闻结果"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 🔍 Add debug log: print original news content
        logger.info(f"[unified news tool] 📋 Original news content preview (first 500 characters): {news_content[:500]}")
        logger.info(f"[统一新闻工具] 📊 原始内容长度: {len(news_content)} 字符")
        
        # Check whether it is a Google/Gemini model
        is_google_model = any(keyword in model_info.lower() for keyword in ['google', 'gemini', 'gemma'])
        original_length = len(news_content)
        google_control_applied = False
        
        # 🔍 Add Google model detection log
        if is_google_model:
            logger.info(f"[unified news tool] 🤖 Google model detected, special handling enabled")
        
        # Special length control for Google models
        if is_google_model and len(news_content) > 5000:  # Lower the threshold to 5000 characters
            logger.warning(f"[unified news tool] 🔧 Google model detected, news content is too long({len(news_content)}character), perform length control...")
            
            # Stricter length control strategy
            lines = news_content.split('\n')
            important_lines = []
            char_count = 0
            target_length = 3000  # Target length is set to 3000 characters
            
            # First round: Prioritize important lines containing keywords
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Check whether important keywords are included
                important_keywords = ['股票', '公司', '财报', '业绩', '涨跌', '价格', '市值', '营收', '利润', 
                                    '增长', '下跌', '上涨', '盈利', '亏损', '投资', '分析', '预期', '公告']
                
                is_important = any(keyword in line for keyword in important_keywords)
                
                if is_important and char_count + len(line) < target_length:
                    important_lines.append(line)
                    char_count += len(line)
                elif not is_important and char_count + len(line) < target_length * 0.7:  # Non-important content is more strictly restricted
                    important_lines.append(line)
                    char_count += len(line)
                
                # If target length has been reached, stop adding
                if char_count >= target_length:
                    break
            
            # If the extracted important content is still too long, further truncate it
            if important_lines:
                processed_content = '\n'.join(important_lines)
                if len(processed_content) > target_length:
                    processed_content = processed_content[:target_length] + "...(内容已智能截断)"
                
                news_content = processed_content
                google_control_applied = True
                logger.info(f"[统一新闻工具] ✅ Google模型智能长度控制完成，从{original_length}字符压缩至{len(news_content)}字符")
            else:
                # If there are no important lines, truncate them directly to the target length.
                news_content = news_content[:target_length] + "...(内容已强制截断)"
                google_control_applied = True
                logger.info(f"[统一新闻工具] ⚠️ Google模型强制截断至{target_length}字符")
        
        # Calculate the length of the final formatted result to ensure that the total length is reasonable
        base_format_length = 300  # Approximate length of formatted template
        if is_google_model and (len(news_content) + base_format_length) > 4000:
            # If it is still too long after formatting, further compress the news content
            max_content_length = 3500
            if len(news_content) > max_content_length:
                news_content = news_content[:max_content_length] + "...(已优化长度)"
                google_control_applied = True
                logger.info(f"[统一新闻工具] 🔧 Google模型最终长度优化，内容长度: {len(news_content)}字符")
        
        formatted_result = f"""
=== 📰 新闻数据来源: {source} ===
获取时间: {timestamp}
数据长度: {len(news_content)} 字符
{f"模型类型: {model_info}" if model_info else ""}
{f"🔧 Google模型长度控制已应用 (原长度: {original_length} 字符)" if google_control_applied else ""}

=== 📋 新闻内容 ===
{news_content}

=== ✅ 数据状态 ===
状态: 成功获取
来源: {source}
时间戳: {timestamp}
"""
        return formatted_result.strip()


def create_unified_news_tool(toolkit):
    """创建统一新闻工具函数"""
    analyzer = UnifiedNewsAnalyzer(toolkit)
    
    def get_stock_news_unified(stock_code: str, max_news: int = 100, model_info: str = ""):
        """
        Unified news acquisition tool
        
        Args:
            stock_code (str): Stock code (Supports A shares such as 000001, Hong Kong stocks such as 0700.HK, and US stocks such as AAPL)
            max_news (int): Maximum number of news, default 100
            model_info (str): Currently used model information for special processing
        
        Returns:
            str: Formatted news content
        """
        if not stock_code:
            return "❌ Error: No ticker provided"
        
        return analyzer.get_stock_news_unified(stock_code, max_news, model_info)
    
    # Set tool properties
    get_stock_news_unified.name = "get_stock_news_unified"
    get_stock_news_unified.description = """
Unified news acquisition tool - automatically obtain news from the corresponding market based on the stock code

Function:
- Automatically identify stock types (A shares/Hong Kong stocks/US stocks)
- Choose the best news source based on stock type
- A shares: Prioritize Oriental Wealth -> Google Chinese -> OpenAI
- Hong Kong stocks: Priority Google -> OpenAI -> real time news
- US stocks: Priority OpenAI -> Google English -> FinnHub
- Return formatted news content
- Support special length control for Google models
"""
    
    return get_stock_news_unified