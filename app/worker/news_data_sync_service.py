"""
News data synchronization service
Support news data synchronization and sentiment analysis from multiple data sources
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from app.services.news_data_service import get_news_data_service
from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
from tradingagents.dataflows.providers.china.akshare import get_akshare_provider
from tradingagents.dataflows.news.realtime_news import RealtimeNewsAggregator

logger = logging.getLogger(__name__)


@dataclass
class NewsSyncStats:
    """News synchronization statistics"""
    total_processed: int = 0
    successful_saves: int = 0
    failed_saves: int = 0
    duplicate_skipped: int = 0
    sources_used: List[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> float:
        """Synchronization time (seconds)"""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    @property
    def success_rate(self) -> float:
        """success rate"""
        if self.total_processed == 0:
            return 0.0
        return (self.successful_saves / self.total_processed) * 100


class NewsDataSyncService:
    """News data synchronization service"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._news_service = None
        self._tushare_provider = None
        self._akshare_provider = None
        self._realtime_aggregator = None
    
    async def _get_news_service(self):
        """Get news data service"""
        if self._news_service is None:
            self._news_service = await get_news_data_service()
        return self._news_service
    
    async def _get_tushare_provider(self):
        """Get Tushare Provider"""
        if self._tushare_provider is None:
            self._tushare_provider = get_tushare_provider()
            await self._tushare_provider.connect()
        return self._tushare_provider
    
    async def _get_tushare_provider(self):
        """Get Tushare Provider"""
        if self._tushare_provider is None:
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
            self._tushare_provider = get_tushare_provider()
            await self._tushare_provider.connect()
        return self._tushare_provider

    async def _get_akshare_provider(self):
        """Get AKShare provider"""
        if self._akshare_provider is None:
            self._akshare_provider = get_akshare_provider()
            await self._akshare_provider.connect()
        return self._akshare_provider
    
    async def _get_realtime_aggregator(self):
        """Get real-time news aggregator"""
        if self._realtime_aggregator is None:
            self._realtime_aggregator = RealtimeNewsAggregator()
        return self._realtime_aggregator
    
    async def sync_stock_news(
        self,
        symbol: str,
        data_sources: List[str] = None,
        hours_back: int = 24,
        max_news_per_source: int = 50
    ) -> NewsSyncStats:
        """
        Synchronize news data of a single stock
        
        Args:
            symbol: Stock code
            data_sources: List of data sources, all available sources are used by default
            hours_back: Lookback hours
            max_news_per_source: Maximum number of news per data source
            
        Returns:
            Sync statistics
        """
        stats = NewsSyncStats()
        
        try:
            self.logger.info(f"📰 Start syncing stock news: {symbol}")
            
            if data_sources is None:
                data_sources = ["tushare", "akshare", "realtime"]
            
            news_service = await self._get_news_service()
            all_news = []
            
            # 🔥 Optimization: Different data sources can be executed in parallel (because they use different APIs and do not affect each other)
            # The same data source is still serial internally (to avoid API current limiting)
            import asyncio
            
            tasks = []
            task_sources = []
            
            # Create concurrent tasks
            if "tushare" in data_sources:
                task = self._sync_tushare_news(symbol, hours_back, max_news_per_source)
                tasks.append(task)
                task_sources.append("tushare")
            
            if "akshare" in data_sources:
                task = self._sync_akshare_news(symbol, hours_back, max_news_per_source)
                tasks.append(task)
                task_sources.append("akshare")
            
            if "realtime" in data_sources:
                task = self._sync_realtime_news(symbol, hours_back, max_news_per_source)
                tasks.append(task)
                task_sources.append("realtime")
            
            # Execute news synchronization tasks for all data sources in parallel
            if tasks:
                self.logger.info(f"🚀 Start parallel synchronization {len(tasks)} News from data sources: {task_sources}")
                
                # Parallel execution using asyncio.gather
                news_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Processing results
                for i, (source, news_result) in enumerate(zip(task_sources, news_results)):
                    if isinstance(news_result, Exception):
                        self.logger.error(f"❌ {source} Failed to get news: {news_result}")
                    elif news_result:
                        all_news.extend(news_result)
                        stats.sources_used.append(source)
                        self.logger.info(f"✅ {source} News obtained successfully: {len(news_result)}Article")
            else:
                self.logger.warning("⚠️ No data source available for news synchronization")
            
            # Save news data
            if all_news:
                stats.total_processed = len(all_news)
                
                # Deduplication
                unique_news = self._deduplicate_news(all_news)
                stats.duplicate_skipped = len(all_news) - len(unique_news)
                
                # Save in batches
                saved_count = await news_service.save_news_data(
                    unique_news, "multi_source", "CN"
                )
                stats.successful_saves = saved_count
                stats.failed_saves = len(unique_news) - saved_count
                
                self.logger.info(f"💾 {symbol} News synchronization completed: {saved_count}Article saved successfully")
            
            stats.end_time = datetime.utcnow()
            return stats
            
        except Exception as e:
            self.logger.error(f"❌ Failed to sync stock news {symbol}: {e}")
            stats.end_time = datetime.utcnow()
            return stats
    
    async def _sync_tushare_news(
        self,
        symbol: str,
        hours_back: int,
        max_news: int
    ) -> List[Dict[str, Any]]:
        """Sync Tushare news"""
        try:
            provider = await self._get_tushare_provider()

            if not provider.is_available():
                self.logger.warning("⚠️ Tushare Provider is unavailable")
                return []

            # Get news data and pass hours_back parameter
            news_data = await provider.get_stock_news(
                symbol=symbol,
                limit=max_news,
                hours_back=hours_back
            )

            if news_data:
                # Standardized news data
                standardized_news = []
                for news in news_data:
                    standardized = self._standardize_tushare_news(news, symbol)
                    if standardized:
                        standardized_news.append(standardized)

                self.logger.info(f"✅ Tushare News obtained successfully: {len(standardized_news)}Article")
                return standardized_news
            else:
                self.logger.debug("⚠️ Tushare No news data returned")
                return []

        except Exception as e:
            # Detailed error handling
            if any(keyword in str(e).lower() for keyword in ['Permissions', 'permission', 'unauthorized']):
                self.logger.warning(f"⚠️ Tushare The news interface requires separate permissions.: {e}")
            elif "Points" in str(e) or "point" in str(e).lower():
                self.logger.warning(f"⚠️ Tushare Not enough points: {e}")
            else:
                self.logger.error(f"❌ Tushare News sync failed: {e}")
            return []
    
    async def _sync_akshare_news(
        self, 
        symbol: str, 
        hours_back: int, 
        max_news: int
    ) -> List[Dict[str, Any]]:
        """Sync AKShare News"""
        try:
            provider = await self._get_akshare_provider()
            
            if not provider.is_available():
                return []
            
            # Get news data
            news_data = await provider.get_stock_news(symbol, limit=max_news)
            
            if news_data:
                # Standardized news data
                standardized_news = []
                for news in news_data:
                    standardized = self._standardize_akshare_news(news, symbol)
                    if standardized:
                        standardized_news.append(standardized)
                
                return standardized_news
            
            return []
            
        except Exception as e:
            self.logger.error(f"❌ AKShare News sync failed: {e}")
            return []
    
    async def _sync_realtime_news(
        self, 
        symbol: str, 
        hours_back: int, 
        max_news: int
    ) -> List[Dict[str, Any]]:
        """Sync real-time news"""
        try:
            aggregator = await self._get_realtime_aggregator()
            
            # Get real-time news
            news_items = aggregator.get_realtime_stock_news(
                symbol, hours_back, max_news
            )
            
            if news_items:
                # Standardized news data
                standardized_news = []
                for news_item in news_items:
                    standardized = self._standardize_realtime_news(news_item, symbol)
                    if standardized:
                        standardized_news.append(standardized)
                
                return standardized_news
            
            return []
            
        except Exception as e:
            self.logger.error(f"❌ Real-time news synchronization failed: {e}")
            return []
    
    def _standardize_tushare_news(self, news: Dict[str, Any], symbol: str) -> Optional[Dict[str, Any]]:
        """Standardize Tushare news data"""
        try:
            return {
                "symbol": symbol,
                "title": news.get("title", ""),
                "content": news.get("content", ""),
                "summary": news.get("summary", ""),
                "url": news.get("url", ""),
                "source": news.get("source", "Tushare"),
                "author": news.get("author", ""),
                "publish_time": news.get("publish_time"),
                "category": self._classify_news_category(news.get("title", "")),
                "sentiment": self._analyze_sentiment(news.get("title", "") + " " + news.get("content", "")),
                "importance": self._assess_importance(news.get("title", "")),
                "keywords": self._extract_keywords(news.get("title", "") + " " + news.get("content", "")),
                "data_source": "tushare"
            }
        except Exception as e:
            self.logger.error(f"❌ Standardizing Tushare news failed: {e}")
            return None
    
    def _standardize_akshare_news(self, news: Dict[str, Any], symbol: str) -> Optional[Dict[str, Any]]:
        """Standardize AKShare news data"""
        try:
            return {
                "symbol": symbol,
                "title": news.get("title", ""),
                "content": news.get("content", ""),
                "summary": news.get("summary", ""),
                "url": news.get("url", ""),
                "source": news.get("source", "AKShare"),
                "author": news.get("author", ""),
                "publish_time": news.get("publish_time"),
                "category": self._classify_news_category(news.get("title", "")),
                "sentiment": self._analyze_sentiment(news.get("title", "") + " " + news.get("content", "")),
                "importance": self._assess_importance(news.get("title", "")),
                "keywords": self._extract_keywords(news.get("title", "") + " " + news.get("content", "")),
                "data_source": "akshare"
            }
        except Exception as e:
            self.logger.error(f"❌ Standardizing AKShare news fails: {e}")
            return None
    
    def _standardize_realtime_news(self, news_item, symbol: str) -> Optional[Dict[str, Any]]:
        """Standardized real-time news data"""
        try:
            return {
                "symbol": symbol,
                "title": news_item.title,
                "content": news_item.content,
                "summary": news_item.content[:200] + "..." if len(news_item.content) > 200 else news_item.content,
                "url": news_item.url,
                "source": news_item.source,
                "author": "",
                "publish_time": news_item.publish_time,
                "category": self._classify_news_category(news_item.title),
                "sentiment": self._analyze_sentiment(news_item.title + " " + news_item.content),
                "importance": self._assess_importance(news_item.title),
                "keywords": self._extract_keywords(news_item.title + " " + news_item.content),
                "data_source": "realtime"
            }
        except Exception as e:
            self.logger.error(f"❌ Standardized real-time news fails: {e}")
            return None
    
    def _classify_news_category(self, title: str) -> str:
        """Classified News Categories"""
        title_lower = title.lower()
        
        if any(word in title_lower for word in ["annual report", "quarterly report", "performance", "financial report", "Announcement"]):
            return "company_announcement"
        elif any(word in title_lower for word in ["policy", "central bank", "supervision", "regulations"]):
            return "policy_news"
        elif any(word in title_lower for word in ["market", "Quotes", "Index", "plate"]):
            return "market_news"
        elif any(word in title_lower for word in ["research report", "analysis", "Rating", "Recommended"]):
            return "research_report"
        else:
            return "general"
    
    def _analyze_sentiment(self, text: str) -> str:
        """Analyze sentiment"""
        text_lower = text.lower()
        
        positive_words = ["growth", "rise", "good", "Profit", "success", "breakthrough", "innovation", "Excellent"]
        negative_words = ["fall", "Loss", "risk", "question", "difficult", "decline", "reduce", "warning"]
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        else:
            return "neutral"
    
    def _assess_importance(self, title: str) -> str:
        """Assess importance"""
        title_lower = title.lower()
        
        high_importance_words = ["significant", "urgent", "sudden", "annual report", "performance", "Reorganization", "acquisition"]
        medium_importance_words = ["Announcement", "Notification", "change", "adjust", "plan"]
        
        if any(word in title_lower for word in high_importance_words):
            return "high"
        elif any(word in title_lower for word in medium_importance_words):
            return "medium"
        else:
            return "low"
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords"""
        # Simple keyword extraction, more complex NLP technology can be used in practical applications
        keywords = []
        
        common_keywords = [
            "performance", "annual report", "quarterly report", "growth", "profit", "Revenue", "stock price", "investment",
            "market", "Industry", "policy", "supervision", "risk", "opportunity", "innovation", "develop"
        ]
        
        for keyword in common_keywords:
            if keyword in text:
                keywords.append(keyword)
        
        return keywords[:10]  # Returns up to 10 keywords
    
    def _deduplicate_news(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate news"""
        seen = set()
        unique_news = []
        
        for news in news_list:
            # Use title and URL as deduplication identifiers
            key = (news.get("title", ""), news.get("url", ""))
            if key not in seen:
                seen.add(key)
                unique_news.append(news)
        
        return unique_news
    
    async def sync_market_news(
        self,
        data_sources: List[str] = None,
        hours_back: int = 24,
        max_news_per_source: int = 100
    ) -> NewsSyncStats:
        """
        Synchronous market news
        
        Args:
            data_sources: Data source list
            hours_back: Lookback hours
            max_news_per_source: Maximum number of news per data source
            
        Returns:
            Sync statistics
        """
        stats = NewsSyncStats()
        
        try:
            self.logger.info("📰 Start synchronizing market news...")
            
            if data_sources is None:
                data_sources = ["realtime"]
            
            news_service = await self._get_news_service()
            all_news = []
            
            # Live market news
            if "realtime" in data_sources:
                try:
                    aggregator = await self._get_realtime_aggregator()
                    
                    # Get market news (without specifying a stock code)
                    news_items = aggregator.get_realtime_stock_news(
                        None, hours_back, max_news_per_source
                    )
                    
                    if news_items:
                        for news_item in news_items:
                            standardized = self._standardize_realtime_news(news_item, None)
                            if standardized:
                                all_news.append(standardized)
                        
                        stats.sources_used.append("realtime")
                        self.logger.info(f"✅ Market news for success: {len(all_news)}Article")
                        
                except Exception as e:
                    self.logger.error(f"❌ Failed to obtain market news: {e}")
            
            # Save news data
            if all_news:
                stats.total_processed = len(all_news)
                
                # Deduplication
                unique_news = self._deduplicate_news(all_news)
                stats.duplicate_skipped = len(all_news) - len(unique_news)
                
                # Save in batches
                saved_count = await news_service.save_news_data(
                    unique_news, "market_news", "CN"
                )
                stats.successful_saves = saved_count
                stats.failed_saves = len(unique_news) - saved_count
                
                self.logger.info(f"💾 Market news is synchronized: {saved_count}Article saved successfully")
            
            stats.end_time = datetime.utcnow()
            return stats
            
        except Exception as e:
            self.logger.error(f"❌ Failed to synchronize market news: {e}")
            stats.end_time = datetime.utcnow()
            return stats


# Global service instance
_sync_service_instance = None

async def get_news_data_sync_service() -> NewsDataSyncService:
    """Get news data synchronization service instance"""
    global _sync_service_instance
    if _sync_service_instance is None:
        _sync_service_instance = NewsDataSyncService()
        logger.info("✅ News data synchronization service initialized successfully")
    return _sync_service_instance
