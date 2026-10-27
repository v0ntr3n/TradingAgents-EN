#!/usr/bin/env python3
"""
Real-time news data acquisition tool
Solve the problem of news lag
"""

import requests
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from typing import List, Dict, Optional
import time
import os
from dataclasses import dataclass

# Import log module
from tradingagents.config.runtime_settings import get_timezone_name

from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')



@dataclass
class NewsItem:
    """新闻项目数据结构"""
    title: str
    content: str
    source: str
    publish_time: datetime
    url: str
    urgency: str  # high, medium, low
    relevance_score: float


class RealtimeNewsAggregator:
    """实时新闻聚合器"""

    def __init__(self):
        self.headers = {
            'User-Agent': 'TradingAgents-CN/1.0'
        }

        # API Key configuration
        self.finnhub_key = os.getenv('FINNHUB_API_KEY')
        self.alpha_vantage_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        self.newsapi_key = os.getenv('NEWSAPI_KEY')

    def get_realtime_stock_news(self, ticker: str, hours_back: int = 6, max_news: int = 10) -> List[NewsItem]:
        """
        Get real-time stock news
        Priority: Professional API > News API > search engine

        Args:
            ticker: Stock code
            hours_back: Lookback hours
            max_news: Maximum number of news, default 10
        """
        logger.info(f"[新闻聚合器] 开始获取 {ticker} 的实时新闻，回溯时间: {hours_back}小时")
        start_time = datetime.now(ZoneInfo(get_timezone_name()))
        all_news = []

        # 1. FinnHub real time news (highest priority)
        logger.info(f"[新闻聚合器] 尝试从 FinnHub 获取 {ticker} 的新闻")
        finnhub_start = datetime.now(ZoneInfo(get_timezone_name()))
        finnhub_news = self._get_finnhub_realtime_news(ticker, hours_back)
        finnhub_time = (datetime.now(ZoneInfo(get_timezone_name())) - finnhub_start).total_seconds()

        if finnhub_news:
            logger.info(f"[新闻聚合器] 成功从 FinnHub 获取 {len(finnhub_news)} 条新闻，耗时: {finnhub_time:.2f}秒")
        else:
            logger.info(f"[新闻聚合器] FinnHub 未返回新闻，耗时: {finnhub_time:.2f}秒")

        all_news.extend(finnhub_news)

        # 2. Alpha Vantage News
        logger.info(f"[新闻聚合器] 尝试从 Alpha Vantage 获取 {ticker} 的新闻")
        av_start = datetime.now(ZoneInfo(get_timezone_name()))
        av_news = self._get_alpha_vantage_news(ticker, hours_back)
        av_time = (datetime.now(ZoneInfo(get_timezone_name())) - av_start).total_seconds()

        if av_news:
            logger.info(f"[新闻聚合器] 成功从 Alpha Vantage 获取 {len(av_news)} 条新闻，耗时: {av_time:.2f}秒")
        else:
            logger.info(f"[新闻聚合器] Alpha Vantage 未返回新闻，耗时: {av_time:.2f}秒")

        all_news.extend(av_news)

        # 3. NewsAPI (If configured)
        if self.newsapi_key:
            logger.info(f"[新闻聚合器] 尝试从 NewsAPI 获取 {ticker} 的新闻")
            newsapi_start = datetime.now(ZoneInfo(get_timezone_name()))
            newsapi_news = self._get_newsapi_news(ticker, hours_back)
            newsapi_time = (datetime.now(ZoneInfo(get_timezone_name())) - newsapi_start).total_seconds()

            if newsapi_news:
                logger.info(f"[新闻聚合器] 成功从 NewsAPI 获取 {len(newsapi_news)} 条新闻，耗时: {newsapi_time:.2f}秒")
            else:
                logger.info(f"[新闻聚合器] NewsAPI 未返回新闻，耗时: {newsapi_time:.2f}秒")

            all_news.extend(newsapi_news)
        else:
            logger.info(f"[news aggregator] NewsAPI Key not configured, skip this news feed")

        # 4. Chinese financial news source
        logger.info(f"[新闻聚合器] 尝试获取 {ticker} 的中文财经新闻")
        chinese_start = datetime.now(ZoneInfo(get_timezone_name()))
        chinese_news = self._get_chinese_finance_news(ticker, hours_back)
        chinese_time = (datetime.now(ZoneInfo(get_timezone_name())) - chinese_start).total_seconds()

        if chinese_news:
            logger.info(f"[新闻聚合器] 成功获取 {len(chinese_news)} 条中文财经新闻，耗时: {chinese_time:.2f}秒")
        else:
            logger.info(f"[新闻聚合器] 未获取到中文财经新闻，耗时: {chinese_time:.2f}秒")

        all_news.extend(chinese_news)

        # Deduplication and sorting
        logger.info(f"[新闻聚合器] 开始对 {len(all_news)} 条新闻进行去重和排序")
        dedup_start = datetime.now(ZoneInfo(get_timezone_name()))
        unique_news = self._deduplicate_news(all_news)
        sorted_news = sorted(unique_news, key=lambda x: x.publish_time, reverse=True)
        dedup_time = (datetime.now(ZoneInfo(get_timezone_name())) - dedup_start).total_seconds()

        # Record deduplication results
        removed_count = len(all_news) - len(unique_news)
        logger.info(f"[新闻聚合器] 新闻去重完成，移除了 {removed_count} 条重复新闻，剩余 {len(sorted_news)} 条，耗时: {dedup_time:.2f}秒")

        # record overall situation
        total_time = (datetime.now(ZoneInfo(get_timezone_name())) - start_time).total_seconds()
        logger.info(f"[新闻聚合器] {ticker} 的新闻聚合完成，总共获取 {len(sorted_news)} 条新闻，总耗时: {total_time:.2f}秒")

        # Limit the number of news items to the latest max_news items
        if len(sorted_news) > max_news:
            original_count = len(sorted_news)
            sorted_news = sorted_news[:max_news]
            logger.info(f"[新闻聚合器] 📰 新闻数量限制: 从{original_count}条限制为{max_news}条最新新闻")

        # Record some examples of news headlines
        if sorted_news:
            sample_titles = [item.title for item in sorted_news[:3]]
            logger.info(f"[news aggregator] News headline example: {', '.join(sample_titles)}")

        return sorted_news

    def _get_finnhub_realtime_news(self, ticker: str, hours_back: int) -> List[NewsItem]:
        """Get FinnHub real-time news"""
        if not self.finnhub_key:
            return []

        try:
            # Calculation time range
            end_time = datetime.now(ZoneInfo(get_timezone_name()))
            start_time = end_time - timedelta(hours=hours_back)

            # FinnHub API call
            url = "https://finnhub.io/api/v1/company-news"
            params = {
                'symbol': ticker,
                'from': start_time.strftime('%Y-%m-%d'),
                'to': end_time.strftime('%Y-%m-%d'),
                'token': self.finnhub_key
            }

            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()

            news_data = response.json()
            news_items = []

            for item in news_data:
                # Check news timeliness
                publish_time = datetime.fromtimestamp(item.get('datetime', 0), tz=ZoneInfo(get_timezone_name()))
                if publish_time < start_time:
                    continue

                # Assess urgency
                urgency = self._assess_news_urgency(item.get('headline', ''), item.get('summary', ''))

                news_items.append(NewsItem(
                    title=item.get('headline', ''),
                    content=item.get('summary', ''),
                    source=item.get('source', 'FinnHub'),
                    publish_time=publish_time,
                    url=item.get('url', ''),
                    urgency=urgency,
                    relevance_score=self._calculate_relevance(item.get('headline', ''), ticker)
                ))

            return news_items

        except Exception as e:
            logger.error(f"FinnHub Failed to get news: {e}")
            return []

    def _get_alpha_vantage_news(self, ticker: str, hours_back: int) -> List[NewsItem]:
        """Get Alpha Vantage News"""
        if not self.alpha_vantage_key:
            return []

        try:
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'NEWS_SENTIMENT',
                'tickers': ticker,
                'apikey': self.alpha_vantage_key,
                'limit': 50
            }

            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()

            data = response.json()
            news_items = []

            if 'feed' in data:
                for item in data['feed']:
                    # parsing time
                    time_str = item.get('time_published', '')
                    try:
                        publish_time = datetime.strptime(time_str, '%Y%m%dT%H%M%S').replace(tzinfo=ZoneInfo(get_timezone_name()))
                    except:
                        continue

                    # Check timeliness
                    if publish_time < datetime.now(ZoneInfo(get_timezone_name())) - timedelta(hours=hours_back):
                        continue

                    urgency = self._assess_news_urgency(item.get('title', ''), item.get('summary', ''))

                    news_items.append(NewsItem(
                        title=item.get('title', ''),
                        content=item.get('summary', ''),
                        source=item.get('source', 'Alpha Vantage'),
                        publish_time=publish_time,
                        url=item.get('url', ''),
                        urgency=urgency,
                        relevance_score=self._calculate_relevance(item.get('title', ''), ticker)
                    ))

            return news_items

        except Exception as e:
            logger.error(f"Alpha Vantage Failed to get news: {e}")
            return []

    def _get_newsapi_news(self, ticker: str, hours_back: int) -> List[NewsItem]:
        """获取NewsAPI新闻"""
        try:
            # Build a search query
            company_names = {
                'AAPL': 'Apple',
                'TSLA': 'Tesla',
                'NVDA': 'NVIDIA',
                'MSFT': 'Microsoft',
                'GOOGL': 'Google'
            }

            query = f"{ticker} OR {company_names.get(ticker, ticker)}"

            url = "https://newsapi.org/v2/everything"
            params = {
                'q': query,
                'language': 'en',
                'sortBy': 'publishedAt',
                'from': (datetime.now(ZoneInfo(get_timezone_name())) - timedelta(hours=hours_back)).isoformat(),
                'apiKey': self.newsapi_key
            }

            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()

            data = response.json()
            news_items = []

            for item in data.get('articles', []):
                # parsing time
                time_str = item.get('publishedAt', '')
                try:
                    publish_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                except:
                    continue

                urgency = self._assess_news_urgency(item.get('title', ''), item.get('description', ''))

                news_items.append(NewsItem(
                    title=item.get('title', ''),
                    content=item.get('description', ''),
                    source=item.get('source', {}).get('name', 'NewsAPI'),
                    publish_time=publish_time,
                    url=item.get('url', ''),
                    urgency=urgency,
                    relevance_score=self._calculate_relevance(item.get('title', ''), ticker)
                ))

            return news_items

        except Exception as e:
            logger.error(f"NewsAPI Failed to get news: {e}")
            return []

    def _get_chinese_finance_news(self, ticker: str, hours_back: int) -> List[NewsItem]:
        """获取中文财经新闻"""
        # Integrate Chinese financial news API: Financial Associated Press, Oriental Fortune, etc.
        logger.info(f"[中文财经新闻] 开始获取 {ticker} 的中文财经新闻，回溯时间: {hours_back}小时")
        start_time = datetime.now(ZoneInfo(get_timezone_name()))

        try:
            news_items = []

            # 1. Try using AKShare to get Oriental Fortune stock news
            try:
                logger.info(f"[Chinese financial news] Try getting news via AKShare Provider")
                from tradingagents.dataflows.providers.china.akshare import AKShareProvider

                provider = AKShareProvider()

                # Handling ticker formats
                # If it is a US stock code, do not use Oriental Fortune News
                if '.' in ticker and any(suffix in ticker for suffix in ['.US', '.N', '.O', '.NYSE', '.NASDAQ']):
                    logger.info(f"[Chinese financial news] US stock code detected {ticker}, Skip Oriental Fortune News to get")
                else:
                    # Process A-share and Hong Kong stock codes
                    clean_ticker = ticker.replace('.SH', '').replace('.SZ', '').replace('.SS', '')\
                                    .replace('.HK', '').replace('.XSHE', '').replace('.XSHG', '')

                    # Get Oriental Fortune News
                    logger.info(f"[中文财经新闻] 开始获取 {clean_ticker} 的东方财富新闻")
                    em_start_time = datetime.now(ZoneInfo(get_timezone_name()))
                    news_df = provider.get_stock_news_sync(symbol=clean_ticker)

                    if not news_df.empty:
                        logger.info(f"[Chinese financial news] Oriental Fortune Returns {len(news_df)} news data, start processing")
                        processed_count = 0
                        skipped_count = 0
                        error_count = 0

                        # Convert to NewsItem format
                        for _, row in news_df.iterrows():
                            try:
                                # parsing time
                                time_str = row.get('时间', '')
                                if time_str:
                                    # Try parsing the time format, probably'2023-01-01 12:34:56'Format
                                    try:
                                        publish_time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=ZoneInfo(get_timezone_name()))
                                    except:
                                        # Try other possible formats
                                        try:
                                            publish_time = datetime.strptime(time_str, '%Y-%m-%d').replace(tzinfo=ZoneInfo(get_timezone_name()))
                                        except:
                                            logger.warning(f"[Chinese financial news] Unable to parse time format: {time_str}, Use current time")
                                            publish_time = datetime.now(ZoneInfo(get_timezone_name()))
                                else:
                                    logger.warning(f"[Chinese financial news] The news time is empty, use the current time")
                                    publish_time = datetime.now(ZoneInfo(get_timezone_name()))

                                # Check timeliness
                                if publish_time < datetime.now(ZoneInfo(get_timezone_name())) - timedelta(hours=hours_back):
                                    skipped_count += 1
                                    continue

                                # Assess urgency
                                title = row.get('标题', '')
                                content = row.get('内容', '')
                                urgency = self._assess_news_urgency(title, content)

                                news_items.append(NewsItem(
                                    title=title,
                                    content=content,
                                    source='东方财富',
                                    publish_time=publish_time,
                                    url=row.get('链接', ''),
                                    urgency=urgency,
                                    relevance_score=self._calculate_relevance(title, ticker)
                                ))
                                processed_count += 1
                            except Exception as item_e:
                                logger.error(f"[Chinese financial news] Failed to handle Oriental Fortune news project: {item_e}")
                                error_count += 1
                                continue

                        em_time = (datetime.now(ZoneInfo(get_timezone_name())) - em_start_time).total_seconds()
                        logger.info(f"[中文财经新闻] 东方财富新闻处理完成，成功: {processed_count}条，跳过: {skipped_count}条，错误: {error_count}条，耗时: {em_time:.2f}秒")
            except Exception as ak_e:
                logger.error(f"[Chinese financial news] Failed to obtain Oriental Fortune News: {ak_e}")

            # 2. Financial Associated Press RSS (if available)
            logger.info(f"[Chinese financial news] Start getting RSS news from Cailianshe")
            rss_start_time = datetime.now(ZoneInfo(get_timezone_name()))
            rss_sources = [
                "https://www.cls.cn/api/sw?app=CailianpressWeb&os=web&sv=7.7.5",
                # More RSS feeds can be added
            ]

            rss_success_count = 0
            rss_error_count = 0
            total_rss_items = 0

            for rss_url in rss_sources:
                try:
                    logger.info(f"[Chinese financial news] Try to parse RSS feed: {rss_url}")
                    rss_item_start = datetime.now(ZoneInfo(get_timezone_name()))
                    items = self._parse_rss_feed(rss_url, ticker, hours_back)
                    rss_item_time = (datetime.now(ZoneInfo(get_timezone_name())) - rss_item_start).total_seconds()

                    if items:
                        logger.info(f"[中文财经新闻] 成功从RSS源获取 {len(items)} 条新闻，耗时: {rss_item_time:.2f}秒")
                        news_items.extend(items)
                        total_rss_items += len(items)
                        rss_success_count += 1
                    else:
                        logger.info(f"[中文财经新闻] RSS源未返回相关新闻，耗时: {rss_item_time:.2f}秒")
                except Exception as rss_e:
                    logger.error(f"[Chinese financial news] Failed to parse RSS feed: {rss_e}")
                    rss_error_count += 1
                    continue

            # Record RSS Get Summary
            rss_total_time = (datetime.now(ZoneInfo(get_timezone_name())) - rss_start_time).total_seconds()
            logger.info(f"[中文财经新闻] RSS新闻获取完成，成功源: {rss_success_count}个，失败源: {rss_error_count}个，获取新闻: {total_rss_items}条，总耗时: {rss_total_time:.2f}秒")

            # Record Chinese financial news and get summary
            total_time = (datetime.now(ZoneInfo(get_timezone_name())) - start_time).total_seconds()
            logger.info(f"[中文财经新闻] {ticker} 的中文财经新闻获取完成，总共获取 {len(news_items)} 条新闻，总耗时: {total_time:.2f}秒")

            return news_items

        except Exception as e:
            logger.error(f"[Chinese financial news] Failed to obtain Chinese financial news: {e}")
            return []

    def _parse_rss_feed(self, rss_url: str, ticker: str, hours_back: int) -> List[NewsItem]:
        """解析RSS源"""
        logger.info(f"[RSS解析] 开始解析RSS源: {rss_url}，股票: {ticker}，回溯时间: {hours_back}小时")
        start_time = datetime.now(ZoneInfo(get_timezone_name()))

        try:
            # The actual implementation requires the use of the feedparser library
            # Here is a simplified implementation, which should be replaced with real RSS parsing logic in actual projects
            import feedparser

            logger.info(f"[RSS parse] Try to get RSS feed content")
            feed = feedparser.parse(rss_url)

            if not feed or not feed.entries:
                logger.warning(f"[RSS parse] RSS Source did not return valid content")
                return []

            logger.info(f"[RSS解析] 成功获取RSS源，包含 {len(feed.entries)} 条条目")
            news_items = []
            processed_count = 0
            skipped_count = 0

            for entry in feed.entries:
                try:
                    # parsing time
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        publish_time = datetime.fromtimestamp(time.mktime(entry.published_parsed), tz=ZoneInfo(get_timezone_name()))
                    else:
                        logger.warning(f"[RSS parse] Entry is missing publication time, use current time")
                        publish_time = datetime.now(ZoneInfo(get_timezone_name()))

                    # Check timeliness
                    if publish_time < datetime.now(ZoneInfo(get_timezone_name())) - timedelta(hours=hours_back):
                        skipped_count += 1
                        continue

                    title = entry.title if hasattr(entry, 'title') else ''
                    content = entry.description if hasattr(entry, 'description') else ''

                    # Check for dependencies
                    if ticker.lower() not in title.lower() and ticker.lower() not in content.lower():
                        skipped_count += 1
                        continue

                    # Assess urgency
                    urgency = self._assess_news_urgency(title, content)

                    news_items.append(NewsItem(
                        title=title,
                        content=content,
                        source='财联社',
                        publish_time=publish_time,
                        url=entry.link if hasattr(entry, 'link') else '',
                        urgency=urgency,
                        relevance_score=self._calculate_relevance(title, ticker)
                    ))
                    processed_count += 1
                except Exception as e:
                    logger.error(f"[RSS parse] Failed to process RSS entries: {e}")
                    continue

            total_time = (datetime.now(ZoneInfo(get_timezone_name())) - start_time).total_seconds()
            logger.info(f"[RSS解析] RSS源解析完成，成功: {processed_count}条，跳过: {skipped_count}条，耗时: {total_time:.2f}秒")
            return news_items
        except ImportError:
            logger.error(f"[RSS parse] feedparser The library is not installed and cannot parse RSS feeds")
            return []
        except Exception as e:
            logger.error(f"[RSS parse] Failed to parse RSS feed: {e}")
            return []

    def _assess_news_urgency(self, title: str, content: str) -> str:
        """评估新闻紧急程度"""
        text = (title + ' ' + content).lower()

        # High urgency keywords
        high_urgency_keywords = [
            'breaking', 'urgent', 'alert', 'emergency', 'halt', 'suspend',
            '突发', '紧急', '暂停', '停牌', '重大'
        ]

        # Medium urgency keywords
        medium_urgency_keywords = [
            'earnings', 'report', 'announce', 'launch', 'merger', 'acquisition',
            '财报', '发布', '宣布', '并购', '收购'
        ]

        # Check for high-urgency keywords
        for keyword in high_urgency_keywords:
            if keyword in text:
                logger.debug(f"[紧急度评估] 检测到高紧急度关键词 '{keyword}' 在新闻中: {title[:50]}...")
                return 'high'

        # Check for medium urgency keywords
        for keyword in medium_urgency_keywords:
            if keyword in text:
                logger.debug(f"[紧急度评估] 检测到中等紧急度关键词 '{keyword}' 在新闻中: {title[:50]}...")
                return 'medium'

        logger.debug(f"[Urgency assessment] Urgent keywords were not detected and evaluated as low urgency.: {title[:50]}...")
        return 'low'

    def _calculate_relevance(self, title: str, ticker: str) -> float:
        """计算新闻相关性分数"""
        text = title.lower()
        ticker_lower = ticker.lower()

        # Base correlation - the stock symbol appears directly in the title
        if ticker_lower in text:
            logger.debug(f"[相关性计算] 股票代码 {ticker} 直接出现在标题中，相关性评分: 1.0，标题: {title[:50]}...")
            return 1.0

        # Company name match
        company_names = {
            'aapl': ['apple', 'iphone', 'ipad', 'mac'],
            'tsla': ['tesla', 'elon musk', 'electric vehicle'],
            'nvda': ['nvidia', 'gpu', 'ai chip'],
            'msft': ['microsoft', 'windows', 'azure'],
            'googl': ['google', 'alphabet', 'search']
        }

        # Check company related keywords
        if ticker_lower in company_names:
            for name in company_names[ticker_lower]:
                if name in text:
                    logger.debug(f"[Correlation calculation] Company related keywords detected '{name}' In the title, the relevance score: 0.8, Title: {title[:50]}...")
                    return 0.8

        # Extract the purely numeric part of the stock symbol (for Chinese stocks)
        pure_code = ''.join(filter(str.isdigit, ticker))
        if pure_code and pure_code in text:
            logger.debug(f"[Correlation calculation] Stock code numeric part {pure_code} Appear in title, relevance score: 0.9, Title: {title[:50]}...")
            return 0.9

        logger.debug(f"[Correlation calculation] No clear correlation detected, default score used: 0.3, Title: {title[:50]}...")
        return 0.3  # Default correlation

    def _deduplicate_news(self, news_items: List[NewsItem]) -> List[NewsItem]:
        """去重新闻"""
        logger.info(f"[新闻去重] 开始对 {len(news_items)} 条新闻进行去重处理")
        start_time = datetime.now(ZoneInfo(get_timezone_name()))

        seen_titles = set()
        unique_news = []
        duplicate_count = 0
        short_title_count = 0

        for item in news_items:
            # Simple title deduplication
            title_key = item.title.lower().strip()

            # Check title length
            if len(title_key) <= 10:
                logger.debug(f"[News deduplication] Skip news with too short titles: '{item.title}', Source: {item.source}")
                short_title_count += 1
                continue

            # Check for duplicates
            if title_key in seen_titles:
                logger.debug(f"[News deduplication] Duplicate news detected: '{item.title[:50]}...', Source: {item.source}")
                duplicate_count += 1
                continue

            # Add to result set
            seen_titles.add(title_key)
            unique_news.append(item)

        # Record deduplication results
        time_taken = (datetime.now(ZoneInfo(get_timezone_name())) - start_time).total_seconds()
        logger.info(f"[News deduplication] Deduplication completed, original news: {len(news_items)}strips, after removing duplicates: {len(unique_news)}Article,")
        logger.info(f"[新闻去重] 去除重复: {duplicate_count}条，标题过短: {short_title_count}条，耗时: {time_taken:.2f}秒")

        return unique_news

    def format_news_report(self, news_items: List[NewsItem], ticker: str) -> str:
        """格式化新闻报告"""
        logger.info(f"[新闻报告] 开始为 {ticker} 生成新闻报告")
        start_time = datetime.now(ZoneInfo(get_timezone_name()))

        if not news_items:
            logger.warning(f"[新闻报告] 未获取到 {ticker} 的实时新闻数据")
            return f"未获取到{ticker}的实时新闻数据。"

        # Group by urgency
        high_urgency = [n for n in news_items if n.urgency == 'high']
        medium_urgency = [n for n in news_items if n.urgency == 'medium']
        low_urgency = [n for n in news_items if n.urgency == 'low']

        # Record news classification status
        logger.info(f"[新闻报告] {ticker} 新闻分类统计: 高紧急度 {len(high_urgency)}条, 中紧急度 {len(medium_urgency)}条, 低紧急度 {len(low_urgency)}条")

        # Record news source distribution
        news_sources = {}
        for item in news_items:
            source = item.source
            if source in news_sources:
                news_sources[source] += 1
            else:
                news_sources[source] = 1

        sources_info = ", ".join([f"{source}: {count}条" for source, count in news_sources.items()])
        logger.info(f"[新闻报告] {ticker} 新闻来源分布: {sources_info}")

        report = f"# {ticker} 实时新闻分析报告\n\n"
        report += f"📅 生成时间: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"📊 新闻总数: {len(news_items)}条\n\n"

        if high_urgency:
            report += "## 🚨 紧急新闻\n\n"
            for news in high_urgency[:3]:  # Display up to 3 items
                report += f"### {news.title}\n"
                report += f"**来源**: {news.source} | **时间**: {news.publish_time.strftime('%H:%M')}\n"
                report += f"{news.content}\n\n"

        if medium_urgency:
            report += "## 📢 重要新闻\n\n"
            for news in medium_urgency[:5]:  # Display up to 5 items
                report += f"### {news.title}\n"
                report += f"**来源**: {news.source} | **时间**: {news.publish_time.strftime('%H:%M')}\n"
                report += f"{news.content}\n\n"

        # Add timeliness description
        latest_news = max(news_items, key=lambda x: x.publish_time)
        time_diff = datetime.now(ZoneInfo(get_timezone_name())) - latest_news.publish_time

        report += f"\n## ⏰ 数据时效性\n"
        report += f"最新新闻发布于: {time_diff.total_seconds() / 60:.0f}分钟前\n"

        if time_diff.total_seconds() < 1800:  # 30 within minutes
            report += "🟢 Data timeliness: Excellent (30 within minutes)\n"
        elif time_diff.total_seconds() < 3600:  # 1 within hours
            report += "🟡 Data timeliness: good (1 within hours)\n"
        else:
            report += "🔴 Data timeliness: Average (more than 1 hour)\n"

        # Record report generation completion information
        end_time = datetime.now(ZoneInfo(get_timezone_name()))
        time_taken = (end_time - start_time).total_seconds()
        report_length = len(report)

        logger.info(f"[新闻报告] {ticker} 新闻报告生成完成，耗时: {time_taken:.2f}秒，报告长度: {report_length}字符")

        # Record timely information
        time_diff_minutes = time_diff.total_seconds() / 60
        logger.info(f"[新闻报告] {ticker} 新闻时效性: 最新新闻发布于 {time_diff_minutes:.1f}分钟前")

        return report


def get_realtime_stock_news(ticker: str, curr_date: str, hours_back: int = 6) -> str:
    """
    The main interface function for obtaining real-time stock news
    """
    logger.info(f"[news analysis] ========== Function entry ==========")
    logger.info(f"[news analysis] function: get_realtime_stock_news")
    logger.info(f"[news analysis] parameters: ticker={ticker}, curr_date={curr_date}, hours_back={hours_back}")
    logger.info(f"[新闻分析] 开始获取 {ticker} 的实时新闻，日期: {curr_date}, 回溯时间: {hours_back}小时")
    start_total_time = datetime.now(ZoneInfo(get_timezone_name()))
    logger.info(f"[新闻分析] 开始时间: {start_total_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

    # Determine stock type
    logger.info(f"[news analysis] ========== steps 1: Stock type judgment ==========")
    stock_type = "未知"
    is_china_stock = False
    logger.info(f"[news analysis] original ticker: {ticker}")

    if '.' in ticker:
        logger.info(f"[news analysis] It is detected that the ticker contains a period and performs suffix matching.")
        if any(suffix in ticker for suffix in ['.SH', '.SZ', '.SS', '.XSHE', '.XSHG']):
            stock_type = "A股"
            is_china_stock = True
            logger.info(f"[news analysis] Match to A-share suffix, stock type: {stock_type}")
        elif '.HK' in ticker:
            stock_type = "港股"
            logger.info(f"[news analysis] Match to Hong Kong stock suffix, stock type: {stock_type}")
        elif any(suffix in ticker for suffix in ['.US', '.N', '.O', '.NYSE', '.NASDAQ']):
            stock_type = "美股"
            logger.info(f"[news analysis] Match to US stock suffix, stock type: {stock_type}")
        else:
            logger.info(f"[news analysis] No known suffix was matched")
    else:
        logger.info(f"[news analysis] ticker Does not contain a dot, try to use StockUtils to determine")
        # Try using StockUtils to determine stock type
        try:
            from tradingagents.utils.stock_utils import StockUtils
            logger.info(f"[news analysis] Successfully imported StockUtils and started to determine the stock type")
            market_info = StockUtils.get_market_info(ticker)
            logger.info(f"[news analysis] StockUtils Return to market information: {market_info}")
            if market_info['is_china']:
                stock_type = "A股"
                is_china_stock = True
                logger.info(f"[news analysis] StockUtils Determined to be A shares")
            elif market_info['is_hk']:
                stock_type = "港股"
                logger.info(f"[news analysis] StockUtils Judged as Hong Kong stocks")
            elif market_info['is_us']:
                stock_type = "美股"
                logger.info(f"[news analysis] StockUtils Determined to be U.S. stocks")
        except Exception as e:
            logger.warning(f"[news analysis] Failed to use StockUtils to determine stock type: {e}")

    logger.info(f"[新闻分析] 最终判断结果 - 股票 {ticker} 类型: {stock_type}, 是否A股: {is_china_stock}")

    # For A-shares, give priority to Oriental Fortune News Source
    if is_china_stock:
        logger.info(f"[news analysis] ========== steps 2: A Shareholder side wealth news acquisition ==========")
        logger.info(f"[news analysis] A-share stocks detected {ticker}, Prioritize trying to use Oriental Fortune News Source")
        try:
            logger.info(f"[news analysis] Try getting news via AKShare Provider")
            from tradingagents.dataflows.providers.china.akshare import AKShareProvider

            provider = AKShareProvider()
            logger.info(f"[news analysis] Successfully created AKShare Provider instance")

            # Process A-share codes
            clean_ticker = ticker.replace('.SH', '').replace('.SZ', '').replace('.SS', '')\
                            .replace('.XSHE', '').replace('.XSHG', '')
            logger.info(f"[news analysis] original ticker: {ticker} -> After cleaning ticker: {clean_ticker}")

            logger.info(f"[news analysis] ready to call provider.get_stock_news_sync({clean_ticker})")
            logger.info(f"[新闻分析] 开始从东方财富获取 {clean_ticker} 的新闻数据")
            start_time = datetime.now(ZoneInfo(get_timezone_name()))
            logger.info(f"[news analysis] Oriental Fortune API call start time: {start_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

            news_df = provider.get_stock_news_sync(symbol=clean_ticker, limit=10)

            end_time = datetime.now(ZoneInfo(get_timezone_name()))
            time_taken = (end_time - start_time).total_seconds()
            logger.info(f"[news analysis] Oriental Fortune API call end time: {end_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
            logger.info(f"[新闻分析] 东方财富API调用耗时: {time_taken:.2f}秒")
            logger.info(f"[news analysis] Oriental Wealth API return data type: {type(news_df)}")

            if hasattr(news_df, 'empty'):
                logger.info(f"[news analysis] Oriental Fortune API returns DataFrame, whether it is empty: {news_df.empty}")
                if not news_df.empty:
                    logger.info(f"[news analysis] Oriental Wealth API returns DataFrame shape: {news_df.shape}")
                    logger.info(f"[news analysis] Oriental Wealth API returns DataFrame column name: {list(news_df.columns) if hasattr(news_df, 'columns') else 'No listing'}")
            else:
                logger.info(f"[news analysis] Oriental Wealth API returns data: {news_df}")

            if not news_df.empty:
                # Build a simple news report
                news_count = len(news_df)
                logger.info(f"[新闻分析] 成功获取 {news_count} 条东方财富新闻，耗时 {time_taken:.2f} 秒")

                report = f"# {ticker} 东方财富新闻报告\n\n"
                report += f"📅 生成时间: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}\n"
                report += f"📊 新闻总数: {news_count}条\n"
                report += f"🕒 获取耗时: {time_taken:.2f}秒\n\n"

                # Record some examples of news headlines
                sample_titles = [row.get('新闻标题', '无标题') for _, row in news_df.head(3).iterrows()]
                logger.info(f"[news analysis] News headline example: {', '.join(sample_titles)}")

                logger.info(f"[news analysis] Start building a news report")
                for idx, (_, row) in enumerate(news_df.iterrows()):
                    if idx < 3:  # Only record the first 3 details
                        logger.info(f"[新闻分析] 第{idx+1}条新闻: 标题={row.get('新闻标题', '无标题')}, 时间={row.get('发布时间', '无时间')}")
                    report += f"### {row.get('News headline', '')}\n"
                    report += f"📅 {row.get('Release time', '')}\n"
                    report += f"🔗 {row.get('News link', '')}\n\n"
                    report += f"{row.get('News content', 'No content')}\n\n"

                total_time_taken = (datetime.now(ZoneInfo(get_timezone_name())) - start_total_time).total_seconds()
                logger.info(f"[新闻分析] 成功生成 {ticker} 的新闻报告，总耗时 {total_time_taken:.2f} 秒，新闻来源: 东方财富")
                logger.info(f"[新闻分析] 报告长度: {len(report)} 字符")
                logger.info(f"[news analysis] ========== Oriental Fortune News is successfully obtained and the function is about to return ==========")
                return report
            else:
                logger.warning(f"[news analysis] Eastern wealth has not been obtained {ticker} news, time-consuming {time_taken:.2f} Second, try another news source")
        except Exception as e:
            logger.error(f"[news analysis] Failed to obtain Oriental Fortune News: {e}, Will try other news sources")
            logger.error(f"[新闻分析] 异常详情: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"[新闻分析] 异常堆栈: {traceback.format_exc()}")
    else:
        logger.info(f"[news analysis] ========== Skip A Shareholder Fang Wealth News Get ==========")
        logger.info(f"[新闻分析] 股票类型为 {stock_type}，不是A股，跳过东方财富新闻源")

    # If it is not A-shares or A-share news acquisition fails, use real-time news aggregator
    logger.info(f"[news analysis] ========== steps 3: real time news aggregator ==========")
    aggregator = RealtimeNewsAggregator()
    logger.info(f"[news analysis] Successfully created real-time news aggregator instance")
    try:
        logger.info(f"[新闻分析] 尝试使用实时新闻聚合器获取 {ticker} 的新闻")
        start_time = datetime.now(ZoneInfo(get_timezone_name()))
        logger.info(f"[news analysis] Aggregator call start time: {start_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

        # Get real-time news
        news_items = aggregator.get_realtime_stock_news(ticker, hours_back, max_news=10)

        end_time = datetime.now(ZoneInfo(get_timezone_name()))
        time_taken = (end_time - start_time).total_seconds()
        logger.info(f"[news analysis] Aggregator call end time: {end_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        logger.info(f"[新闻分析] 聚合器调用耗时: {time_taken:.2f}秒")
        logger.info(f"[news analysis] Aggregator return data type: {type(news_items)}")
        logger.info(f"[news analysis] Aggregator returns data: {news_items}")

        # If the news is successfully obtained
        if news_items and len(news_items) > 0:
            news_count = len(news_items)
            logger.info(f"[新闻分析] 实时新闻聚合器成功获取 {news_count} 条 {ticker} 的新闻，耗时 {time_taken:.2f} 秒")

            # Record some examples of news headlines
            sample_titles = [item.title for item in news_items[:3]]
            logger.info(f"[news analysis] News headline example: {', '.join(sample_titles)}")

            # Format reports
            logger.info(f"[news analysis] Start formatting news report")
            report = aggregator.format_news_report(news_items, ticker)
            logger.info(f"[新闻分析] 报告格式化完成，长度: {len(report)} 字符")

            total_time_taken = (datetime.now(ZoneInfo(get_timezone_name())) - start_total_time).total_seconds()
            logger.info(f"[新闻分析] 成功生成 {ticker} 的新闻报告，总耗时 {total_time_taken:.2f} 秒，新闻来源: 实时新闻聚合器")
            logger.info(f"[news analysis] ========== The real-time news aggregator is obtained successfully and the function is about to return ==========")
            return report
        else:
            logger.warning(f"[news analysis] Real-time news aggregator not getting {ticker} news, time-consuming {time_taken:.2f} seconds, try using an alternate news source")
            # If you don't get news, continue to try alternative solutions
    except Exception as e:
        logger.error(f"[news analysis] Failed to obtain real-time news aggregator: {e}, Will try alternate news sources")
        logger.error(f"[新闻分析] 异常详情: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"[新闻分析] 异常堆栈: {traceback.format_exc()}")
        # When an exception occurs, continue to try alternative solutions

    # backup plan 1: For Hong Kong stocks, give priority to trying to use Oriental Fortune News (A shares have been processed previously)
    if not is_china_stock and '.HK' in ticker:
        logger.info(f"[news analysis] Hong Kong stock code detected {ticker}, Try using Oriental Fortune News Source")
        try:
            from tradingagents.dataflows.providers.china.akshare import AKShareProvider

            provider = AKShareProvider()

            # Process Hong Kong stock codes
            clean_ticker = ticker.replace('.HK', '')

            logger.info(f"[新闻分析] 开始从东方财富获取港股 {clean_ticker} 的新闻数据")
            start_time = datetime.now(ZoneInfo(get_timezone_name()))
            news_df = provider.get_stock_news_sync(symbol=clean_ticker, limit=10)
            end_time = datetime.now(ZoneInfo(get_timezone_name()))
            time_taken = (end_time - start_time).total_seconds()

            if not news_df.empty:
                # Build a simple news report
                news_count = len(news_df)
                logger.info(f"[新闻分析] 成功获取 {news_count} 条东方财富港股新闻，耗时 {time_taken:.2f} 秒")

                report = f"# {ticker} 东方财富新闻报告\n\n"
                report += f"📅 生成时间: {datetime.now(ZoneInfo(get_timezone_name())).strftime('%Y-%m-%d %H:%M:%S')}\n"
                report += f"📊 新闻总数: {news_count}条\n"
                report += f"🕒 获取耗时: {time_taken:.2f}秒\n\n"

                # Record some examples of news headlines
                sample_titles = [row.get('新闻标题', '无标题') for _, row in news_df.head(3).iterrows()]
                logger.info(f"[news analysis] News headline example: {', '.join(sample_titles)}")

                for _, row in news_df.iterrows():
                    report += f"### {row.get('News headline', '')}\n"
                    report += f"📅 {row.get('Release time', '')}\n"
                    report += f"🔗 {row.get('News link', '')}\n\n"
                    report += f"{row.get('News content', 'No content')}\n\n"

                logger.info(f"[news analysis] Successfully generated Oriental Fortune news report, news source: Oriental Fortune")
                return report
            else:
                logger.warning(f"[news analysis] Eastern wealth has not been obtained {clean_ticker} news data, time-consuming {time_taken:.2f} seconds, try the next alternative")
        except Exception as e:
            logger.error(f"[news analysis] Failed to obtain Oriental Fortune News: {e}, Will try next alternative")

    # backup plan 2: Try Google News
    try:
        from tradingagents.dataflows.interface import get_google_news

        # Build search queries based on stock types
        if stock_type == "A股":
            # A Stocks use Chinese keywords
            clean_ticker = ticker.replace('.SH', '').replace('.SZ', '').replace('.SS', '')\
                           .replace('.XSHE', '').replace('.XSHG', '')
            search_query = f"{clean_ticker} 股票 公司 财报 新闻"
            logger.info(f"[news analysis] Start getting A-shares from Google {clean_ticker} Chinese news data, query: {search_query}")
        elif stock_type == "港股":
            # Hong Kong stocks use Chinese keywords
            clean_ticker = ticker.replace('.HK', '')
            search_query = f"{clean_ticker} 港股 公司"
            logger.info(f"[news analysis] Start getting Hong Kong stocks from Google {clean_ticker} News data, query: {search_query}")
        else:
            # US stocks use English keywords
            search_query = f"{ticker} stock news"
            logger.info(f"[news analysis] Start getting from Google {ticker} News data, query: {search_query}")

        start_time = datetime.now(ZoneInfo(get_timezone_name()))
        google_news = get_google_news(search_query, curr_date, 1)
        end_time = datetime.now(ZoneInfo(get_timezone_name()))
        time_taken = (end_time - start_time).total_seconds()

        if google_news and len(google_news.strip()) > 0:
            # Estimated number of news acquired
            news_lines = google_news.strip().split('\n')
            news_count = sum(1 for line in news_lines if line.startswith('###'))

            logger.info(f"[新闻分析] 成功获取 Google 新闻，估计 {news_count} 条新闻，耗时 {time_taken:.2f} 秒")

            # Record some examples of news headlines
            sample_titles = [line.replace('### ', '') for line in news_lines if line.startswith('### ')][:3]
            if sample_titles:
                logger.info(f"[news analysis] News headline example: {', '.join(sample_titles)}")

            logger.info(f"[news analysis] Successfully generated Google News report, news source: Google")
            return google_news
        else:
            logger.warning(f"[新闻分析] Google 新闻未获取到 {ticker} 的新闻数据，耗时 {time_taken:.2f} 秒")
    except Exception as e:
        logger.error(f"[news analysis] Google Failed to get news: {e}, All alternatives have been tried")

    # All methods fail and return error message
    total_time_taken = (datetime.now(ZoneInfo(get_timezone_name())) - start_total_time).total_seconds()
    logger.error(f"[新闻分析] {ticker} 的所有新闻获取方法均已失败，总耗时 {total_time_taken:.2f} 秒")

    # Log detailed failure information
    failure_details = {
        "股票代码": ticker,
        "股票类型": stock_type,
        "分析日期": curr_date,
        "回溯时间": f"{hours_back}小时",
        "总耗时": f"{total_time_taken:.2f}秒"
    }
    logger.error(f"[news analysis] News acquisition failure details: {failure_details}")

    return f"""
实时新闻获取失败 - {ticker}
分析日期: {curr_date}

❌ 错误信息: 所有可用的新闻源都未能获取到相关新闻

💡 备用建议:
1. 检查网络连接和API密钥配置
2. 使用基础新闻分析作为备选
3. 关注官方财经媒体的最新报道
4. 考虑使用专业金融终端获取实时新闻

注: 实时新闻获取依赖外部API服务的可用性。
"""
