"""TradingAgents-CN FastAPI Backend main application entry."""
from __future__ import annotations

import json
import logging
from pathlib import Path
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

from app.core.config import settings
from app.core.lifecycle import application_lifespan as lifespan, print_config_summary as _print_config_summary
from app.middleware.operation_log_middleware import OperationLogMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.router_registry import register_routers

logger = logging.getLogger("app.main")


def get_version() -> str:
    """Read version number from VERSION file."""
    try:
        version_file = Path(__file__).parent.parent / "VERSION"
        if version_file.exists():
            return version_file.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return "2.1.0"


def get_build_info() -> dict:
    """Read build information from BUILD_INFO file."""
    try:
        build_info_file = Path(__file__).parent.parent / "BUILD_INFO"
        if build_info_file.exists():
            return json.loads(build_info_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.debug("Failed to read BUILD_INFO: %s", exc)
    return {}


app = FastAPI(
    title="TradingAgents-CN API",
    description="Stock Analysis and Batch Queuing System API",
    version=get_version(),
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
    redirect_slashes=False,
)

if not settings.DEBUG:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.JWT_SECRET,
    session_cookie="tradingagents_session",
    max_age=3600,
    same_site="lax",
    https_only=False if settings.DEBUG else True,
)

app.add_middleware(OperationLogMiddleware)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log HTTP request start, status code, and latency."""
    start_time = time.time()
    if request.url.path in ["/health", "/favicon.ico"] or request.url.path.startswith("/static"):
        return await call_next(request)

    web_logger = logging.getLogger("webapi")
    web_logger.info("Processing %s %s", request.method, request.url.path)
    response = await call_next(request)
    process_time = time.time() - start_time
    web_logger.info(
        "Completed %s %s status=%s duration=%.3fs",
        request.method,
        request.url.path,
        response.status_code,
        process_time,
    )
    return response


app.add_middleware(RequestIDMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Return structured JSON 500 response on unhandled exceptions."""
    logging.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal server error occurred",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.get("/api/test-log")
async def test_log():
    """Verify that logging middleware is active."""
    return {"message": "Test successful", "timestamp": time.time()}


register_routers(app)


@app.get("/api/system/info", tags=["system"])
async def get_system_info():
    """Return application version and build metadata."""
    version = get_version()
    build_info = get_build_info()
    if build_info:
        return {
            "version": build_info.get("version", version),
            "full_version": build_info.get("full_version", version),
            "build_timestamp": build_info.get("build_timestamp"),
            "build_date": build_info.get("build_date"),
            "build_unix": build_info.get("build_unix"),
            "git_commit": build_info.get("git_commit"),
            "build_type": build_info.get("build_type"),
        }
    return {
        "version": version,
        "full_version": version,
        "build_timestamp": None,
        "build_date": None,
        "build_unix": None,
        "git_commit": None,
        "build_type": None,
    }


@app.get("/")
async def root():
    """Return root API health metadata."""
    return {
        "name": "TradingAgents-CN API",
        "version": get_version(),
        "status": "running",
        "docs_url": "/docs" if settings.DEBUG else None,
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
    )
