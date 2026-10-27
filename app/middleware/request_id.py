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
