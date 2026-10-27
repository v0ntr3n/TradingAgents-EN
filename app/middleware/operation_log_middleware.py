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
