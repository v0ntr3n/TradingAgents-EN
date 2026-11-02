from __future__ import annotations
import sys as _sys
__path__ = []
_self_mod = _sys.modules[__name__]
for _sub in ['auth_guard', 'error_handler', 'operation_log_middleware', 'rate_limit', 'request_id']:
    _sys.modules[f"app.middleware.{_sub}"] = _self_mod
    setattr(_self_mod, _sub, _self_mod)

# === auth_guard.py ===
"""
Global authentication guard middleware
Protect all /api routes and allow only whitelisted paths.
"""

import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

PUBLIC_PATH_PREFIXES = (
    "/api/health",
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/register",
    "/api/gateway/",
    "/api/system/info",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/static",
)

PUBLIC_EXACT_PATHS = frozenset({
    "/",
    "/health",
    "/favicon.ico",
})


class AuthGuardMiddleware(BaseHTTPMiddleware):
    """
    Global authentication guard — Intercept all unauthenticated /api requests.

    Endpoints that have been protected (using Depends(get_current_user)) not affected,
    This middleware provides cover for routes that are missing Depends.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path

        if path in PUBLIC_EXACT_PATHS:
            return await call_next(request)

        for prefix in PUBLIC_PATH_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        if not path.startswith("/api"):
            return await call_next(request)

        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        # --- JWT ---
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1]
            try:
                from app.services.auth_service import AuthService
                token_data = AuthService.verify_token(token)
            except Exception:
                logger.warning(
                    "AuthGuard JWT Verification exception: method=%s path=%s",
                    request.method,
                    path,
                    exc_info=True,
                )
            else:
                if token_data:
                    return await call_next(request)
                logger.info(
                    "AuthGuard JWT Verification failed: method=%s path=%s token_prefix=%s",
                    request.method,
                    path,
                    token[:12],
                )
        elif auth_header:
            logger.info(
                "AuthGuard Received non Bearer Authorization: method=%s path=%s prefix=%s",
                request.method,
                path,
                auth_header[:24],
            )

        # --- Session cookie ---
        try:
            user_id = request.session.get("user_id") if "session" in request.scope else None
            if user_id:
                return await call_next(request)
        except Exception:
            logger.warning(
                "AuthGuard Exception reading session cookie: method=%s path=%s",
                request.method,
                path,
                exc_info=True,
            )

        logger.warning(
            "AuthGuard Intercept unauthenticated requests: method=%s path=%s has_authorization=%s has_session=%s",
            request.method,
            path,
            bool(auth_header),
            bool(request.session.get("user_id")) if "session" in request.scope else False,
        )
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Authentication required",
                }
            },
        )

# === error_handler.py ===
"""
Error handling middleware
"""

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import logging
import traceback
from typing import Callable

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Global error handling middleware"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            return await self.handle_error(request, exc)
    
    async def handle_error(self, request: Request, exc: Exception) -> JSONResponse:
        """Handle exceptions and return standardized error responses"""
        
        # Get request ID
        request_id = getattr(request.state, "request_id", "unknown")
        
        # Record error log
        logger.error(
            f"Request exception - ID: {request_id}, "
            f"path: {request.url.path}, "
            f"method: {request.method}, "
            f"Abnormal: {str(exc)}",
            exc_info=True
        )
        
        # Return different error responses based on exception type
        if isinstance(exc, ValueError):
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": str(exc),
                        "request_id": request_id
                    }
                }
            )
        
        elif isinstance(exc, PermissionError):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "PERMISSION_DENIED",
                        "message": "Insufficient permissions",
                        "request_id": request_id
                    }
                }
            )
        
        elif isinstance(exc, FileNotFoundError):
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "RESOURCE_NOT_FOUND",
                        "message": "The requested resource does not exist",
                        "request_id": request_id
                    }
                }
            )
        
        else:
            # Unknown exception
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "Internal server error, please try again later",
                        "request_id": request_id
                    }
                }
            )

# === operation_log_middleware.py ===
"""
Operation logging middleware
Automatically record users API operation logs
"""

import time
import json
import logging
from typing import Optional, Dict, Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.operation_log_service import log_operation
from app.models.operation_log import ActionType

logger = logging.getLogger("webapi")

# Global switch: whether to enable operation logging (can be dynamically controlled by system settings)
OPLOG_ENABLED: bool = True

def set_operation_log_enabled(flag: bool) -> None:
    global OPLOG_ENABLED
    OPLOG_ENABLED = bool(flag)



class OperationLogMiddleware(BaseHTTPMiddleware):
    """Operation logging middleware"""

    def __init__(self, app, skip_paths: Optional[list] = None):
        super().__init__(app)
        # Skip logging path
        self.skip_paths = skip_paths or [
            "/health",
            "/healthz",
            "/readyz",
            "/favicon.ico",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/stream/",  # SSE Stream not logged
            "/api/system/logs/",  # The operation log API itself does not log
        ]

        # Path to operation type mapping
        self.path_action_mapping = {
            "/api/analysis/": ActionType.STOCK_ANALYSIS,
            "/api/screening/": ActionType.SCREENING,
            "/api/config/": ActionType.CONFIG_MANAGEMENT,
            "/api/system/database/": ActionType.DATABASE_OPERATION,
            "/api/auth/login": ActionType.USER_LOGIN,
            "/api/auth/logout": ActionType.USER_LOGOUT,
            "/api/auth/change-password": ActionType.USER_MANAGEMENT,  # 🔧 Add change password operation type
            "/api/reports/": ActionType.REPORT_GENERATION,
        }

    async def dispatch(self, request: Request, call_next):
        # Check if records need to be skipped
        if self._should_skip_logging(request):
            return await call_next(request)

        # Recording start time
        start_time = time.time()

        # Get request information
        method = request.method
        path = request.url.path
        ip_address = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")

        # Get user information (if authenticated)
        user_info = await self._get_user_info(request)

        # Handle request
        response = await call_next(request)

        # Calculation time
        duration_ms = int((time.time() - start_time) * 1000)

        # Asynchronous operation log recording
        if user_info:
            try:
                await self._log_operation(
                    user_info=user_info,
                    method=method,
                    path=path,
                    response=response,
                    duration_ms=duration_ms,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    request=request
                )
            except Exception as e:
                logger.error(f"Failed to record operation log: {e}")

        return response

    def _should_skip_logging(self, request: Request) -> bool:
        """Determine whether logging should be skipped"""
        # Skip directly when closing globally
        if not OPLOG_ENABLED:
            return True

        path = request.url.path

        # Check skip path
        for skip_path in self.skip_paths:
            if path.startswith(skip_path):
                return True

        # Only log API requests
        if not path.startswith("/api/"):
            return True

        # Only log specific HTTP methods
        if request.method not in ["POST", "PUT", "DELETE", "PATCH"]:
            return True

        return False

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        # Check proxy header
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Use direct connection IP
        if request.client:
            return request.client.host

        return "unknown"

    async def _get_user_info(self, request: Request) -> Optional[Dict[str, Any]]:
        """Get user information"""
        try:
            # Get user information from request status (set by authentication middleware)
            if hasattr(request.state, "user"):
                return request.state.user

            # Try to parse user information from Authorization header
            auth_header = request.headers.get("authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1]

                # Authentication using AuthService token
                from app.services.auth_service import AuthService
                token_data = AuthService.verify_token(token)

                if token_data:
                    # Return user information (the open source version only has admin users)
                    return {
                        "id": "admin",
                        "username": "admin",
                        "name": "Administrator",
                        "is_admin": True,
                        "roles": ["admin"]
                    }

            return None
        except Exception as e:
            logger.debug(f"Failed to obtain user information: {e}")
            return None

    def _get_action_type(self, path: str) -> str:
        """Get operation type based on path"""
        for path_prefix, action_type in self.path_action_mapping.items():
            if path.startswith(path_prefix):
                return action_type

        return ActionType.SYSTEM_SETTINGS  # Default type

    def _get_action_description(self, method: str, path: str, request: Request) -> str:
        """Generate operation description"""
        # Basic description
        action_map = {
            "POST": "Create",
            "PUT": "update",
            "PATCH": "Modify",
            "DELETE": "Delete"
        }

        action_verb = action_map.get(method, method)

        # Generate a more specific description based on the path
        if "/analysis/" in path:
            if "single" in path:
                return f"{action_verb}Single stock analysis tasks"
            elif "batch" in path:
                return f"{action_verb}Batch analysis tasks"
            else:
                return f"{action_verb}Analysis tasks"

        elif "/screening/" in path:
            return f"{action_verb}stock screen"

        elif "/config/" in path:
            if "llm" in path:
                return f"{action_verb}Large model configuration"
            elif "datasource" in path:
                return f"{action_verb}Data source configuration"
            else:
                return f"{action_verb}System configuration"

        elif "/database/" in path:
            if "backup" in path:
                return f"{action_verb}Database backup"
            elif "cleanup" in path:
                return f"{action_verb}Database cleaning"
            else:
                return f"{action_verb}Database operations"

        elif "/auth/" in path:
            if "login" in path:
                return "User login"
            elif "logout" in path:
                return "User logout"
            elif "change-password" in path:
                return "Change password"
            else:
                return f"{action_verb}Authentication operation"

        else:
            return f"{action_verb} {path}"

    async def _log_operation(
        self,
        user_info: Dict[str, Any],
        method: str,
        path: str,
        response: Response,
        duration_ms: int,
        ip_address: str,
        user_agent: str,
        request: Request
    ):
        """Record operation log"""
        try:
            # Determine whether the operation is successful
            success = 200 <= response.status_code < 400

            # Get operation type and description
            action_type = self._get_action_type(path)
            action = self._get_action_description(method, path, request)

            # Build details
            details = {
                "method": method,
                "path": path,
                "status_code": response.status_code,
                "query_params": dict(request.query_params) if request.query_params else None,
            }

            # Get the error message (if any)
            error_message = None
            if not success:
                error_message = f"HTTP {response.status_code}"

            # Record operation log
            await log_operation(
                user_id=user_info.get("id", ""),
                username=user_info.get("username", "unknown"),
                action_type=action_type,
                action=action,
                details=details,
                success=success,
                error_message=error_message,
                duration_ms=duration_ms,
                ip_address=ip_address,
                user_agent=user_agent,
                session_id=user_info.get("session_id")
            )

        except Exception as e:
            logger.error(f"Failed to record operation log: {e}")


# Convenient function: manually record operation logs
async def manual_log_operation(
    request: Request,
    user_info: Dict[str, Any],
    action_type: str,
    action: str,
    details: Optional[Dict[str, Any]] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None
):
    """Manually record operation logs"""
    try:
        ip_address = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")

        await log_operation(
            user_id=user_info.get("id", ""),
            username=user_info.get("username", "unknown"),
            action_type=action_type,
            action=action,
            details=details,
            success=success,
            error_message=error_message,
            duration_ms=duration_ms,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=user_info.get("session_id")
        )
    except Exception as e:
        logger.error(f"Manual operation log recording failed: {e}")

# === rate_limit.py ===
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
                        "message": "The request is too frequent, please try again later.",
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

# === request_id.py ===
"""
Request ID/Trace-ID middleware
- Generate a unique ID (trace_id) for each request and write request.state and response headers
- Write trace_id into the contextvars of logging so that all logs are automatically brought out
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import uuid
import time
import logging
from typing import Callable

from app.core.logging_context import trace_id_var

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Request ID and log middleware (trace_id)"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID/trace_id
        trace_id = str(uuid.uuid4())
        request.state.request_id = trace_id  # Compatible with existing field names
        request.state.trace_id = trace_id

        # Write trace_id contextvars
        token = trace_id_var.set(trace_id)

        # Record request start time
        start_time = time.time()

        # Log request information
        logger.info(
            f"Request to start - trace_id: {trace_id}, "
            f"method: {request.method}, path: {request.url.path}, "
            f"client: {request.client.host if request.client else 'unknown'}"
        )

        try:
            # Handle request
            response = await call_next(request)

            # Calculate processing time
            process_time = time.time() - start_time

            # Add response header
            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Request-ID"] = trace_id  # Compatible
            response.headers["X-Process-Time"] = f"{process_time:.3f}"

            # Record request completion information
            logger.info(
                f"Request completed - trace_id: {trace_id}, status code: {response.status_code}, processing time: {process_time:.3f}s"
            )

            return response

        except Exception as exc:
            # Calculate processing time
            process_time = time.time() - start_time

            # Record request exception information
            logger.error(
                f"Request exception - trace_id: {trace_id}, processing time: {process_time:.3f}s, Abnormal: {str(exc)}"
            )
            raise

        finally:
            # Clean up the contextvar to avoid leaking it to subsequent requests
            try:
                trace_id_var.reset(token)
            except Exception:
                pass

# === __init__.py ===
"""
middleware module
"""