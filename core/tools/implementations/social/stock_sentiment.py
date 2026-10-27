"""
Unified Stock Sentiment Analysis Tool

Automatically identify stock types (A shares, Hong Kong stocks, US stocks) and call the corresponding sentiment data sources
Prioritize the use of social media data uploaded by users
"""

import logging
from typing import Annotated
from datetime import datetime, timedelta
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="get_stock_sentiment_unified",
    name="统一股票情绪分析",
    description=(
        "Get stock market sentiment and social media sentiment, supporting A shares, Hong Kong stocks, and US stocks."
        "Here s emotions/signals Refers to news, social media and market sentiment, not technical buying and selling signals, financial risk signals, announcements of risk events or Agent capability gaps."
    ),
    category="social",
    is_online=True,
    auto_register=True,
    capability_tags=["stock_sentiment", "sentiment", "market_sentiment", "social_media_sentiment", "public_opinion", "social", "event_driven"],
    tool_role_hint="specialized",
    output_shape="markdown",
    preferred_for=["sentiment_analysis", "social_media_monitoring", "market_sentiment_assessment"],
    when_to_use="Use it when you need to analyze market public opinion, social media sentiment, investor sentiment and the impact of sentiment.",
    when_not_to_use="It is not used for the identification of announcement events such as technical indicator cross signals, financial statement anomalies, cash flow risks, regulatory penalties/litigation, etc. or for fundamental valuation.",
)
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
            # China A-shares and Hong Kong stocks: give priority to social media data uploaded by users
            logger.info(f"🇨🇳🇭🇰 [Unifying Emotion Tools] Dealing with Chinese market sentiment...")

            # 🔥 Prioritize query of social media data uploaded by users (using synchronization method)
            user_uploaded_data = None
            try:
                logger.info(f"🔍 [Unifying Emotion Tools] Start querying social media data in the database...")
                from app.core.database import get_mongo_db_sync
                
                # Clean code suffix
                clean_ticker = ticker
                for suffix in ['.SH', '.SZ', '.SS', '.HK', '.XSHE', '.XSHG']:
                    clean_ticker = clean_ticker.replace(suffix, '')
                
                # Query the database using synchronous mode
                db = get_mongo_db_sync()
                collection = db.social_media_messages
                
                # Query the social media data of the last 7 days
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(days=7)
                
                query = {
                    "symbol": clean_ticker,
                    "publish_time": {
                        "$gte": start_time,
                        "$lte": end_time
                    }
                }
                
                # Synchronous query
                logger.info(f"🔍 [Unifying Emotion Tools] Query database: collection=social_media_messages, symbol={clean_ticker}, time_range=Last 7 days")
                logger.debug(f"🔍 [Unifying Emotion Tools] Query condition details: {query}")
                cursor = collection.find(query).sort("publish_time", -1).limit(100)
                user_messages = list(cursor)
                logger.info(f"📊 [统一情绪工具] 数据库查询完成: 找到 {len(user_messages)} 条消息")
                
                if user_messages and len(user_messages) > 0:
                    logger.info(f"✅ [Unifying Emotion Tools] found {len(user_messages)} Start analyzing social media data uploaded by users...")
                    user_uploaded_data = user_messages
                    
                    # 🔥 Detailed analysis of social media data uploaded by users
                    sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
                    platform_counts = {}
                    recent_messages = []
                    keyword_counts = {}
                    hashtag_counts = {}
                    total_engagement = {"views": 0, "likes": 0, "shares": 0, "comments": 0}
                    high_influence_messages = []
                    
                    for msg in user_messages:
                        sentiment = msg.get("sentiment", "neutral")
                        sentiment_counts[sentiment] += 1
                        
                        platform = msg.get("platform", "unknown")
                        platform_counts[platform] = platform_counts.get(platform, 0) + 1
                        
                        # Statistical keywords
                        keywords = msg.get("keywords", [])
                        if isinstance(keywords, list):
                            for kw in keywords:
                                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
                        
                        # statistics hashtag
                        hashtags = msg.get("hashtags", [])
                        if isinstance(hashtags, list):
                            for tag in hashtags:
                                hashtag_counts[tag] = hashtag_counts.get(tag, 0) + 1
                        
                        # Statistical interaction data
                        engagement = msg.get("engagement", {})
                        if isinstance(engagement, dict):
                            total_engagement["views"] += engagement.get("views", 0)
                            total_engagement["likes"] += engagement.get("likes", 0)
                            total_engagement["shares"] += engagement.get("shares", 0)
                            total_engagement["comments"] += engagement.get("comments", 0)
                        
                        # Collect high-impact messages (impact score>50 or high interaction rate)
                        author = msg.get("author", {})
                        influence_score = author.get("influence_score", 0) if isinstance(author, dict) else 0
                        engagement_rate = engagement.get("engagement_rate", 0) if isinstance(engagement, dict) else 0
                        
                        if influence_score > 50 or engagement_rate > 5.0:
                            if len(high_influence_messages) < 3:
                                high_influence_messages.append({
                                    "content": msg.get("content", "")[:150] + "..." if len(msg.get("content", "")) > 150 else msg.get("content", ""),
                                    "platform": platform,
                                    "sentiment": sentiment,
                                    "influence_score": influence_score,
                                    "engagement_rate": engagement_rate,
                                    "author": author.get("author_name", "未知") if isinstance(author, dict) else "未知"
                                })
                        
                        # Collect a summary of recent news (prioritizing high impact)
                        content = msg.get("content", "")
                        if content and len(recent_messages) < 10:
                            recent_messages.append({
                                "content": content[:100] + "..." if len(content) > 100 else content,
                                "platform": platform,
                                "sentiment": sentiment,
                                "publish_time": msg.get("publish_time", ""),
                                "influence_score": influence_score
                            })
                    
                    # Sort recent news by influence
                    recent_messages.sort(key=lambda x: x.get("influence_score", 0), reverse=True)
                    recent_messages = recent_messages[:5]  # Only keep the first 5 items
                    
                    # Calculate sentiment score
                    total = sum(sentiment_counts.values())
                    if total > 0:
                        sentiment_score_val = (sentiment_counts["positive"] - sentiment_counts["negative"]) / total
                        if sentiment_score_val > 0.1:
                            sentiment_score = "偏多"
                        elif sentiment_score_val < -0.1:
                            sentiment_score = "偏空"
                        else:
                            sentiment_score = "中性"
                    else:
                        sentiment_score = "中性"
                    
                    # Build detailed reports
                    platform_summary = ", ".join([f"{k}({v})" for k, v in sorted(platform_counts.items(), key=lambda x: x[1], reverse=True)[:5]])
                    
                    # Popular keywords
                    top_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                    keywords_summary = ", ".join([f"{k}({v})" for k, v in top_keywords]) if top_keywords else "无"
                    
                    # hot topics
                    top_hashtags = sorted(hashtag_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                    hashtags_summary = ", ".join([f"#{k}({v})" for k, v in top_hashtags]) if top_hashtags else "无"
                    
                    # Interactive data summary
                    total_interactions = sum(total_engagement.values())
                    engagement_summary = f"总浏览量:{total_engagement['views']}, 点赞:{total_engagement['likes']}, 转发:{total_engagement['shares']}, 评论:{total_engagement['comments']}"
                    
                    # high impact message
                    high_influence_summary = ""
                    if high_influence_messages:
                        # Build a list of high-impact messages (avoid using backslashes in f-strings)
                        influence_lines = []
                        for m in high_influence_messages:
                            line = f"- [{m['platform']}] [{m['sentiment']}] 作者:{m['author']} (影响力:{m['influence_score']:.1f}, 互动率:{m['engagement_rate']:.2f}%)"
                            content_line = f"  {m['content']}"
                            influence_lines.append(f"{line}\n{content_line}")
                        high_influence_summary = f"""
### High Impact Messages (Impact Score>50 or interaction rate>5%) 
{chr(10).join(influence_lines)}
"""
                    
                    sentiment_summary = f"""## 社媒情绪分析（用户上传数据）
**股票**: {ticker}
**数据来源**: 用户上传的社媒内容
**数据量**: 共 {len(user_messages)} 条消息（最近7天）
**情绪评级**: {sentiment_score} (正向:{sentiment_counts['positive']}, 中性:{sentiment_counts['neutral']}, 负向:{sentiment_counts['negative']})
**平台分布**: {platform_summary}
**热门关键词**: {keywords_summary}
**热门话题**: {hashtags_summary}
**互动数据**: {engagement_summary}（总互动:{total_interactions}）

### 最近社媒消息摘要（按影响力排序）
{chr(10).join([f"- [{m['platform']}] [{m['sentiment']}] (影响力:{m.get('influence_score', 0):.1f}) {m['content']}" for m in recent_messages])}
{high_influence_summary}

*基于用户上传的社媒数据，数据质量更高，分析更准确*
"""
                    result_data.append(sentiment_summary)
                    
            except Exception as e:
                logger.warning(f"⚠️ [Unifying Emotion Tools] Failed to query user uploaded social media data: {e}", exc_info=True)
                logger.info(f"🔍 [Unifying Emotion Tools] query parameters: symbol={clean_ticker}, start_time={start_time}, end_time={end_time}")
                # Continue to use alternative data sources
            
            # If there is no user-uploaded data or insufficient data, use an alternate data source
            if not user_uploaded_data or len(user_uploaded_data) < 5:
                if user_uploaded_data:
                    logger.info(f"📰 [Unifying Emotion Tools] Insufficient data uploaded by user ({len(user_uploaded_data)}Article < 5 bars), using an alternate data source (news)...")
                else:
                    logger.info(f"📰 [Unifying Emotion Tools] The social media data uploaded by the user was not found (the database query returned 0 items or the query failed), and an alternate data source (news) was used....")
                try:
                    # Try using AKShareProvider to get news for sentiment analysis
                    from tradingagents.dataflows.providers.china.akshare import AKShareProvider
                    ak_provider = AKShareProvider()
                    
                    # Clean code suffix
                    clean_ticker = ticker
                    for suffix in ['.SH', '.SZ', '.SS', '.HK', '.XSHE', '.XSHG']:
                        clean_ticker = clean_ticker.replace(suffix, '')
                    
                    # Get news (Prefer _get_stock_news_direct if the public interface is not available)
                    if hasattr(ak_provider, 'get_stock_news_sync'):
                        news_df = ak_provider.get_stock_news_sync(symbol=clean_ticker)
                    else:
                        news_df = ak_provider._get_stock_news_direct(symbol=clean_ticker)
                    
                    if news_df is not None and not news_df.empty:
                        # Simple analysis
                        news_titles = []
                        # Compatible with different column names
                        col_map = {'新闻标题': 'title', '标题': 'title', 'title': 'title'}
                        
                        for col in news_df.columns:
                            if col in col_map:
                                news_titles = news_df[col].tolist()
                                break
                        
                        if not news_titles and not news_df.empty:
                             # If the header column is not found, try the first column
                             news_titles = news_df.iloc[:, 0].astype(str).tolist()

                        # Keyword statistics
                        pos_words = ['上涨', '利好', '增长', '突破', '买入', '增持', '大涨', '新高', '预增']
                        neg_words = ['下跌', '利空', '减少', '跌破', '卖出', '减持', '大跌', '新低', '亏损']
                        
                        pos_count = 0
                        neg_count = 0
                        
                        recent_titles = news_titles[:10] # View only the last 10 items
                        
                        for title in recent_titles:
                            if not isinstance(title, str): continue
                            for w in pos_words:
                                if w in title: pos_count += 1
                            for w in neg_words:
                                if w in title: neg_count += 1
                                
                        sentiment_score = "中性"
                        if pos_count > neg_count: sentiment_score = "偏多"
                        if neg_count > pos_count: sentiment_score = "偏空"
                        
                        news_summary = f"""## 新闻情绪分析（备用数据源）
**股票**: {ticker}
**情绪评级**: {sentiment_score} (正向词:{pos_count}, 负向词:{neg_count})

### 最近新闻摘要
{chr(10).join(['- ' + str(t) for t in recent_titles[:5]])}

*基于最近 {len(recent_titles)} 条新闻标题分析*
"""
                        result_data.append(news_summary)
                    else:
                        if not user_uploaded_data:
                            result_data.append(f"## Chinese market sentiment\n There is currently no relevant data (it is recommended to upload social media data)")
                            
                except Exception as e:
                    logger.error(f"中文情绪分析失败: {e}")
                    if not user_uploaded_data:
                        result_data.append(f"## Chinese market sentiment\n Analysis failed: {e}, It is recommended to upload social media data")

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

