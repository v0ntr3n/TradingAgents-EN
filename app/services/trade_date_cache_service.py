"""
Last transaction date caching service
Use Redis to cache the last valid transaction date of each data source to avoid frequent calls API
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Redis Key name
CACHE_KEY_PREFIX = "trade_date:latest"
CACHE_KEY_TUSHARE = f"{CACHE_KEY_PREFIX}:tushare"
CACHE_KEY_AKSHARE = f"{CACHE_KEY_PREFIX}:akshare"
CACHE_KEY_BAOSTOCK = f"{CACHE_KEY_PREFIX}:baostock"


class TradeDateCacheService:
    """最后交易日期缓存服务"""
    
    @property
    def redis(self):
        """Get the synchronous Redis client (for sync methods)."""
        try:
            from app.core.database import get_redis_sync_client

            return get_redis_sync_client()
        except Exception as e:
            logger.warning(f"⚠️  Synchronous Redis client initialization failed: {e}, Will directly call the API to get the transaction date", exc_info=True)
            return None
    
    @property
    def redis_async(self):
        """Get an asynchronous Redis client (for async methods)."""
        try:
            from app.core.database import get_redis_client

            return get_redis_client()
        except RuntimeError:
            logger.warning("Asynchronous Redis client is not initialized and asynchronous methods may not be available")
            return None
    
    def _is_today(self, date_str: str) -> bool:
        """判断日期字符串是否是今天"""
        try:
            cache_date = datetime.strptime(date_str, "%Y-%m-%d")
            today = datetime.now().date()
            return cache_date.date() == today
        except Exception:
            return False
    
    def get_cached_trade_date_sync(self, source: str) -> Optional[str]:
        """
        Get last transaction date from cache (sync version)
        
        Args:
            source: Data source name ('tushare', 'akshare', 'baostock')
            
        Returns:
            If the cache exists and was updated today, return the transaction date (YYYYMMDD format), otherwise return None
        """
        if not self.redis:
            return None
        
        try:
            cache_key = self._get_cache_key(source)
            cached_data = self.redis.get(cache_key)
            
            if cached_data:
                data = json.loads(cached_data)
                update_date = data.get("update_date")
                trade_date = data.get("trade_date")
                
                # Determine whether it was updated on the same day
                if self._is_today(update_date):
                    logger.debug(f"✅ [{source}] 从缓存获取最后交易日期: {trade_date} (更新于: {update_date})")
                    return trade_date
                else:
                    logger.debug(f"⚠️  [{source}] Cache has expired (updated on: {update_date}), Need to reacquire")
                    return None
            
            return None
        except Exception as e:
            logger.warning(f"⚠️  [{source}] 读取缓存失败: {e}")
            return None
    
    async def _get_cached_trade_date_async(self, source: str) -> Optional[str]:
        """异步获取缓存"""
        if not self.redis_async:
            return None
        
        try:
            cache_key = self._get_cache_key(source)
            cached_data = await self.redis_async.get(cache_key)
            
            if cached_data:
                data = json.loads(cached_data)
                update_date = data.get("update_date")
                trade_date = data.get("trade_date")
                
                # Determine whether it was updated on the same day
                if self._is_today(update_date):
                    logger.debug(f"✅ [{source}] 从缓存获取最后交易日期: {trade_date} (更新于: {update_date})")
                    return trade_date
                else:
                    logger.debug(f"⚠️  [{source}] Cache has expired (updated on: {update_date}), Need to reacquire")
                    return None
            
            return None
        except Exception as e:
            logger.warning(f"⚠️  [{source}] 读取缓存失败: {e}")
            return None
    
    async def get_cached_trade_date(self, source: str) -> Optional[str]:
        """
        Get last transaction date from cache (async version)
        
        Args:
            source: Data source name ('tushare', 'akshare', 'baostock')
            
        Returns:
            If the cache exists and was updated today, return the transaction date (YYYYMMDD format), otherwise return None
        """
        return await self._get_cached_trade_date_async(source)
    
    def set_cached_trade_date_sync(self, source: str, trade_date: str) -> bool:
        """
        Save last transaction date to cache (sync version)
        
        Args:
            source: Data source name ('tushare', 'akshare', 'baostock')
            trade_date: Transaction date (YYYYMMDD format)
            
        Returns:
            Is the save successful?
        """
        if not self.redis:
            return False
        
        try:
            cache_key = self._get_cache_key(source)
            today = datetime.now().strftime("%Y-%m-%d")
            
            data = {
                "trade_date": trade_date,
                "update_date": today,
                "source": source
            }
            
            # Save to Redis, set TTL to 7 days (prevent cache from persisting forever)
            self.redis.setex(
                cache_key,
                7 * 24 * 3600,  # 7 day TTL
                json.dumps(data, ensure_ascii=False)
            )
            
            logger.info(f"✅ [{source}] 已缓存最后交易日期: {trade_date} (更新于: {today})")
            return True
        except Exception as e:
            logger.warning(f"⚠️  [{source}] 保存缓存失败: {e}")
            return False
    
    async def _set_cached_trade_date_async(self, source: str, trade_date: str) -> bool:
        """异步保存缓存"""
        if not self.redis_async:
            return False
        
        try:
            cache_key = self._get_cache_key(source)
            today = datetime.now().strftime("%Y-%m-%d")
            
            data = {
                "trade_date": trade_date,
                "update_date": today,
                "source": source
            }
            
            # Save to Redis, set TTL to 7 days (prevent cache from persisting forever)
            await self.redis_async.setex(
                cache_key,
                7 * 24 * 3600,  # 7 day TTL
                json.dumps(data, ensure_ascii=False)
            )
            
            logger.info(f"✅ [{source}] 已缓存最后交易日期: {trade_date} (更新于: {today})")
            return True
        except Exception as e:
            logger.warning(f"⚠️  [{source}] 保存缓存失败: {e}")
            return False
    
    async def set_cached_trade_date(self, source: str, trade_date: str) -> bool:
        """
        Save last transaction date to cache (asynchronous version)
        
        Args:
            source: Data source name ('tushare', 'akshare', 'baostock')
            trade_date: Transaction date (YYYYMMDD format)
            
        Returns:
            Is the save successful?
        """
        return await self._set_cached_trade_date_async(source, trade_date)
    
    def _get_cache_key(self, source: str) -> str:
        """获取缓存键名"""
        key_map = {
            "tushare": CACHE_KEY_TUSHARE,
            "akshare": CACHE_KEY_AKSHARE,
            "baostock": CACHE_KEY_BAOSTOCK,
        }
        return key_map.get(source.lower(), f"{CACHE_KEY_PREFIX}:{source.lower()}")
    
    def clear_cache_sync(self, source: Optional[str] = None) -> bool:
        """
        Clear cache (sync version)
        
        Args:
            source: Data source name, if None clears all caches
            
        Returns:
            Is the clearing successful?
        """
        if not self.redis:
            return False
        
        try:
            if source:
                cache_key = self._get_cache_key(source)
                self.redis.delete(cache_key)
                logger.info(f"✅ [{source}] 缓存已清除")
            else:
                # Clear all transaction date cache
                keys = [CACHE_KEY_TUSHARE, CACHE_KEY_AKSHARE, CACHE_KEY_BAOSTOCK]
                for key in keys:
                    self.redis.delete(key)
                logger.info("✅ All transaction date cache cleared")
            return True
        except Exception as e:
            logger.warning(f"⚠️  清除缓存失败: {e}")
            return False
    
    async def _clear_cache_async(self, source: Optional[str] = None) -> bool:
        """异步清除缓存"""
        if not self.redis_async:
            return False
        
        try:
            if source:
                cache_key = self._get_cache_key(source)
                await self.redis_async.delete(cache_key)
                logger.info(f"✅ [{source}] 缓存已清除")
            else:
                # Clear all transaction date cache
                keys = [CACHE_KEY_TUSHARE, CACHE_KEY_AKSHARE, CACHE_KEY_BAOSTOCK]
                for key in keys:
                    await self.redis_async.delete(key)
                logger.info("✅ All transaction date cache cleared")
            return True
        except Exception as e:
            logger.warning(f"⚠️  清除缓存失败: {e}")
            return False
    
    async def clear_cache(self, source: Optional[str] = None) -> bool:
        """
        Clear cache (asynchronous version)
        
        Args:
            source: Data source name, if None clears all caches
            
        Returns:
            Is the clearing successful?
        """
        return await self._clear_cache_async(source)


# Singleton instance
_trade_date_cache_service: Optional[TradeDateCacheService] = None


def get_trade_date_cache_service() -> TradeDateCacheService:
    """获取交易日期缓存服务单例"""
    global _trade_date_cache_service
    if _trade_date_cache_service is None:
        _trade_date_cache_service = TradeDateCacheService()
    return _trade_date_cache_service
