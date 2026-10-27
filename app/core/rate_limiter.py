"""
rate limiter
Used to control the frequency of API calls to avoid exceeding the current limit of the data source.
"""
import asyncio
import time
import logging
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Sliding window rate limiter
    
    Use sliding window algorithm to precisely control API call frequency
    """
    
    def __init__(self, max_calls: int, time_window: float, name: str = "RateLimiter"):
        """
        Initialize rate limiter
        
        Args:
            max_calls: Maximum number of calls within the time window
            time_window: Time window size (seconds)
            name: Limiter name (for logging)
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.name = name
        self.calls = deque()  # Store call timestamp
        self.lock = asyncio.Lock()  # Ensure thread safety
        
        # Statistics
        self.total_calls = 0
        self.total_waits = 0
        self.total_wait_time = 0.0
        
        logger.info(f"🔧 {self.name} initialization: {max_calls}times/{time_window}seconds")
    
    async def acquire(self):
        """
        Get calling permission
        If the rate limit is exceeded, it waits until it can be called
        """
        async with self.lock:
            now = time.time()
            
            # Remove old call records outside the time window
            while self.calls and self.calls[0] <= now - self.time_window:
                self.calls.popleft()
            
            # If the number of calls within the current window has reached the upper limit, you need to wait.
            if len(self.calls) >= self.max_calls:
                # Calculate the waiting time
                oldest_call = self.calls[0]
                wait_time = oldest_call + self.time_window - now + 0.01  # add a little buffer
                
                if wait_time > 0:
                    self.total_waits += 1
                    self.total_wait_time += wait_time
                    
                    logger.debug(f"⏳ {self.name} Rate limit reached, wait {wait_time:.2f}seconds")
                    await asyncio.sleep(wait_time)
                    
                    # Retrieve the current time
                    now = time.time()
                    
                    # Clean old records again
                    while self.calls and self.calls[0] <= now - self.time_window:
                        self.calls.popleft()
            
            # Record this call
            self.calls.append(now)
            self.total_calls += 1
    
    def get_stats(self) -> dict:
        """Get statistics"""
        return {
            "name": self.name,
            "max_calls": self.max_calls,
            "time_window": self.time_window,
            "current_calls": len(self.calls),
            "total_calls": self.total_calls,
            "total_waits": self.total_waits,
            "total_wait_time": self.total_wait_time,
            "avg_wait_time": self.total_wait_time / self.total_waits if self.total_waits > 0 else 0
        }
    
    def reset_stats(self):
        """Reset statistics"""
        self.total_calls = 0
        self.total_waits = 0
        self.total_wait_time = 0.0
        logger.info(f"🔄 {self.name} Statistics have been reset")


class TushareRateLimiter(RateLimiter):
    """
    Tushare Dedicated rate limiter
    
    Automatically adjust the current limiting strategy based on Tushare s points level
    """
    
    # Tushare Current limiting configuration corresponding to points level
    TIER_LIMITS = {
        "free": {"max_calls": 100, "time_window": 60},      # free user: 100 times/minute
        "basic": {"max_calls": 200, "time_window": 60},     # basic user: 200 times/minute
        "standard": {"max_calls": 400, "time_window": 60},  # Standard user: 400 times/minute
        "premium": {"max_calls": 600, "time_window": 60},   # advanced user: 600 times/minute
        "vip": {"max_calls": 800, "time_window": 60},       # VIP User: 800 times/minute
    }
    
    def __init__(self, tier: str = "standard", safety_margin: float = 0.8):
        """
        Initialize Tushare rate limiter
        
        Args:
            tier: Points level (free/basic/standard/premium/vip)
            safety_margin: Margin of safety (0-1), the actual limit is a percentage of the theoretical limit
        """
        if tier not in self.TIER_LIMITS:
            logger.warning(f"⚠️ Unknown Tushare points level: {tier}, Use default value 'standard'")
            tier = "standard"
        
        limits = self.TIER_LIMITS[tier]
        
        # Application safety margin
        max_calls = int(limits["max_calls"] * safety_margin)
        time_window = limits["time_window"]
        
        super().__init__(
            max_calls=max_calls,
            time_window=time_window,
            name=f"TushareRateLimiter({tier})"
        )
        
        self.tier = tier
        self.safety_margin = safety_margin
        
        logger.info(f"✅ Tushare Rate limiter configured: {tier}Level, "
                   f"{max_calls}times/{time_window}seconds (margin of safety: {safety_margin*100:.0f}%)")


class AKShareRateLimiter(RateLimiter):
    """
    AKShare Dedicated rate limiter
    
    AKShare There are no clear current limiting rules, and a conservative current limiting strategy is used.
    """
    
    def __init__(self, max_calls: int = 60, time_window: float = 60):
        """
        Initialize AKShare rate limiter
        
        Args:
            max_calls: Maximum number of calls within the time window (default 60 times/minute)
            time_window: Time window size (seconds)
        """
        super().__init__(
            max_calls=max_calls,
            time_window=time_window,
            name="AKShareRateLimiter"
        )


class BaoStockRateLimiter(RateLimiter):
    """
    BaoStock Dedicated rate limiter
    
    BaoStock There are no clear current limiting rules, and a conservative current limiting strategy is used.
    """
    
    def __init__(self, max_calls: int = 100, time_window: float = 60):
        """
        Initialize BaoStock rate limiter
        
        Args:
            max_calls: Maximum number of calls within the time window (default 100 times/minute)
            time_window: Time window size (seconds)
        """
        super().__init__(
            max_calls=max_calls,
            time_window=time_window,
            name="BaoStockRateLimiter"
        )


# Global rate limiter instance
_tushare_limiter: Optional[TushareRateLimiter] = None
_akshare_limiter: Optional[AKShareRateLimiter] = None
_baostock_limiter: Optional[BaoStockRateLimiter] = None


def get_tushare_rate_limiter(tier: str = "standard", safety_margin: float = 0.8) -> TushareRateLimiter:
    """Get Tushare rate limiter (singleton)"""
    global _tushare_limiter
    if _tushare_limiter is None:
        _tushare_limiter = TushareRateLimiter(tier=tier, safety_margin=safety_margin)
    return _tushare_limiter


def get_akshare_rate_limiter() -> AKShareRateLimiter:
    """Get AKShare rate limiter (singleton)"""
    global _akshare_limiter
    if _akshare_limiter is None:
        _akshare_limiter = AKShareRateLimiter()
    return _akshare_limiter


def get_baostock_rate_limiter() -> BaoStockRateLimiter:
    """Get BaoStock rate limiter (singleton)"""
    global _baostock_limiter
    if _baostock_limiter is None:
        _baostock_limiter = BaoStockRateLimiter()
    return _baostock_limiter


def reset_all_limiters():
    """Reset all rate limiters"""
    global _tushare_limiter, _akshare_limiter, _baostock_limiter
    _tushare_limiter = None
    _akshare_limiter = None
    _baostock_limiter = None
    logger.info("🔄 All rate limiters have been reset")

