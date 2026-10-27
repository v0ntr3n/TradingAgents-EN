"""
Rate limiting middleware
Prevent API abuse and implement user-level and endpoint-level rate limiting
"""

from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import logging
from typing import Callable, Dict, Optional
from core.redis_client import get_redis_service, RedisKeys

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware"""
    
    def __init__(self, app, default_rate_limit: int = 100):
        super().__init__(app)
        self.default_rate_limit = default_rate_limit
        
        # Rate limiting configuration for different endpoints
        self.endpoint_limits = {
            "/api/analysis/single": 10,      # Single stock analysis: 10 times per minute
            "/api/analysis/batch": 5,        # Batch analysis: 5 times per minute
            "/api/screening/filter": 20,     # Stock screening: 20 times per minute
            "/api/auth/login": 5,            # Logins: 5 times per minute
            "/api/auth/register": 3,         # Registration: 3 times per minute
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip health checks and static resources
        if request.url.path.startswith(("/api/health", "/docs", "/redoc", "/openapi.json")):
            return await call_next(request)
        
        # Get user ID (if authenticated)
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            # For unauthenticated users, use IP address
            user_id = f"ip:{request.client.host}" if request.client else "unknown"
        
        # Check rate limits
        try:
            await self.check_rate_limit(user_id, request.url.path)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Rate limit check failed: {exc}")
            # If Redis is unavailable, allow the request to pass
        
        return await call_next(request)
    
    async def check_rate_limit(self, user_id: str, endpoint: str):
        """Check rate limits"""
        redis_service = get_redis_service()
        
        # Get the rate limit for an endpoint
        rate_limit = self.endpoint_limits.get(endpoint, self.default_rate_limit)
        
        # Build Redis key
        rate_key = RedisKeys.USER_RATE_LIMIT.format(
            user_id=user_id,
            endpoint=endpoint.replace("/", "_")
        )
        
        # Get the current count
        current_count = await redis_service.increment_with_ttl(rate_key, ttl=60)
        
        # Check if limit is exceeded
        if current_count > rate_limit:
            logger.warning(
                f"Rate Limit Trigger - User: {user_id}, "
                f"endpoint: {endpoint}, "
                f"current count: {current_count}, "
                f"Limit: {rate_limit}"
            )
            
            raise HTTPException(
                status_code=429,
                detail={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"The request is too frequent, please try again later.",
                        "rate_limit": rate_limit,
                        "current_count": current_count,
                        "reset_time": 60
                    }
                }
            )
        
        logger.debug(
            f"Rate limit check passed - user: {user_id}, "
            f"endpoint: {endpoint}, "
            f"current count: {current_count}/{rate_limit}"
        )


class QuotaMiddleware(BaseHTTPMiddleware):
    """Daily quota middleware"""
    
    def __init__(self, app, daily_quota: int = 1000):
        super().__init__(app)
        self.daily_quota = daily_quota
        
        # Endpoints that need to be counted towards the quota
        self.quota_endpoints = {
            "/api/analysis/single",
            "/api/analysis/batch",
            "/api/screening/filter"
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only check endpoints that require quotas
        if request.url.path not in self.quota_endpoints:
            return await call_next(request)
        
        # Get user ID
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            # Unauthenticated users are not subject to quota restrictions
            return await call_next(request)
        
        # Check daily quota
        try:
            await self.check_daily_quota(user_id)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Quota check failed: {exc}")
            # If Redis is unavailable, allow the request to pass
        
        return await call_next(request)
    
    async def check_daily_quota(self, user_id: str):
        """Check daily quota"""
        import datetime
        
        redis_service = get_redis_service()
        
        # Get today's date
        today = datetime.date.today().isoformat()
        
        # Build Redis key
        quota_key = RedisKeys.USER_DAILY_QUOTA.format(
            user_id=user_id,
            date=today
        )
        
        # Get today's usage
        current_usage = await redis_service.increment_with_ttl(quota_key, ttl=86400)  # 24 hours TTL
        
        # Check if quota is exceeded
        if current_usage > self.daily_quota:
            logger.warning(
                f"Daily Quota Exceeded - User: {user_id}, "
                f"Use today: {current_usage}, "
                f"Quota: {self.daily_quota}"
            )
            
            raise HTTPException(
                status_code=429,
                detail={
                    "error": {
                        "code": "DAILY_QUOTA_EXCEEDED",
                        "message": "Today s quota has been used up, please try again tomorrow",
                        "daily_quota": self.daily_quota,
                        "current_usage": current_usage,
                        "reset_date": today
                    }
                }
            )
        
        logger.debug(
            f"Quota check passed - user: {user_id}, "
            f"Use today: {current_usage}/{self.daily_quota}"
        )
