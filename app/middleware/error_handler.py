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
