"""FastAPI lifespan coordinator delegating database, seed, and scheduler startup."""
from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from app.core.logging_config import setup_logging
from .database_init import initialize_database_and_migrations, shutdown_database_and_workers
from .scheduler_init import initialize_and_start_scheduler
from .seed_init import (
    print_config_summary,
    register_tools_skills_and_mcp,
    seed_admin_and_bootstrap,
    sync_prompts_and_runtime_settings,
)

logger = logging.getLogger("app.main")


@asynccontextmanager
async def application_lifespan(app: FastAPI):
    """Manage FastAPI startup and shutdown lifecycle."""
    setup_logging()
    await initialize_database_and_migrations()
    await seed_admin_and_bootstrap()
    await register_tools_skills_and_mcp()
    await sync_prompts_and_runtime_settings()
    scheduler = await initialize_and_start_scheduler()
    try:
        yield
    finally:
        if scheduler is not None:
            try:
                scheduler.shutdown(wait=True)
            except Exception as exc:
                logger.warning("Scheduler shutdown warning: %s", exc)
        await shutdown_database_and_workers()


__all__ = [
    "application_lifespan",
    "initialize_database_and_migrations",
    "shutdown_database_and_workers",
    "initialize_and_start_scheduler",
    "print_config_summary",
    "register_tools_skills_and_mcp",
    "seed_admin_and_bootstrap",
    "sync_prompts_and_runtime_settings",
]
