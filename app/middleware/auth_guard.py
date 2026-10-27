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
