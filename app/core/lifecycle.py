from __future__ import annotations
import sys
__path__ = []

for _m in ['app.core.lifecycle.database_init', 'app.core.lifecycle.scheduler_init', 'app.core.lifecycle.seed_init']:
    sys.modules[_m] = sys.modules[__name__]


# --- database_init.py ---
"""Database initialization, migration, and shutdown helpers for FastAPI lifespan."""


import logging
from app.core.database import close_db, get_mongo_db, init_db

logger = logging.getLogger("app.main")


async def run_database_migrations() -> None:
    """Execute pending MongoDB schema migrations on startup."""
    try:
        from migrations.runner import MigrationRunner

        mig_db = get_mongo_db()
        runner = MigrationRunner(mig_db)
        results = await runner.run_pending()
        if results:
            ok_count = sum(1 for r in results if r["status"] == "success")
            fail_count = sum(1 for r in results if r["status"] == "failed")
            logger.info("Database migration completed: %d success, %d failed", ok_count, fail_count)
        else:
            logger.info("Database schema is up to date")
    except Exception as exc:
        logger.error("Database migration failed: %s", exc)


async def initialize_database_and_migrations() -> None:
    """Validate configuration, initialize database connections, and run migrations."""
    from app.core.startup_validator import validate_startup_config

    validate_startup_config()
    await init_db()
    await run_database_migrations()


async def shutdown_database_and_workers() -> None:
    """Gracefully stop background thread pools, user services, and database clients."""
    try:
        from app.worker.unified_thread_pool_sync_service import get_unified_thread_pool_sync_service

        unified_sync_service = await get_unified_thread_pool_sync_service()
        unified_sync_service.shutdown(timeout=30.0)
    except Exception as exc:
        logger.warning("Unified thread pool sync shutdown warning: %s", exc)

    try:
        from app.worker.financial_data_sync_service import get_financial_sync_service

        financial_sync_service = await get_financial_sync_service()
        if financial_sync_service is not None:
            financial_sync_service.shutdown(timeout=30.0)
    except Exception as exc:
        logger.warning("Financial data sync shutdown warning: %s", exc)

    try:
        from app.services.thread_worker import stop_thread_worker

        await stop_thread_worker()
    except Exception as exc:
        logger.warning("Thread worker shutdown warning: %s", exc)

    try:
        from app.services.user_service import user_service

        user_service.close()
    except Exception as exc:
        logger.warning("UserService shutdown warning: %s", exc)

    await close_db()


# --- scheduler_init.py ---
"""APScheduler job registration and startup/shutdown lifecycle management."""


import asyncio
import logging
from typing import Optional
try:
    from apscheduler.executors.asyncio import AsyncIOExecutor
except ImportError:
    class _DummySched:
        def __init__(self, *a, **kw): pass
        def add_job(self, *a, **kw): pass
        def start(self, *a, **kw): pass
        def shutdown(self, *a, **kw): pass
    BackgroundScheduler = AsyncIOScheduler = CronTrigger = IntervalTrigger = DateTrigger = Job = MemoryJobStore = _DummySched
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ImportError:
    class _DummySched:
        def __init__(self, *a, **kw): pass
        def add_job(self, *a, **kw): pass
        def start(self, *a, **kw): pass
        def shutdown(self, *a, **kw): pass
    BackgroundScheduler = AsyncIOScheduler = CronTrigger = IntervalTrigger = DateTrigger = Job = MemoryJobStore = _DummySched
try:
    from apscheduler.triggers.cron import CronTrigger
except ImportError:
    class _DummySched:
        def __init__(self, *a, **kw): pass
        def add_job(self, *a, **kw): pass
        def start(self, *a, **kw): pass
        def shutdown(self, *a, **kw): pass
    BackgroundScheduler = AsyncIOScheduler = CronTrigger = IntervalTrigger = DateTrigger = Job = MemoryJobStore = _DummySched
try:
    from apscheduler.triggers.interval import IntervalTrigger
except ImportError:
    class _DummySched:
        def __init__(self, *a, **kw): pass
        def add_job(self, *a, **kw): pass
        def start(self, *a, **kw): pass
        def shutdown(self, *a, **kw): pass
    BackgroundScheduler = AsyncIOScheduler = CronTrigger = IntervalTrigger = DateTrigger = Job = MemoryJobStore = _DummySched

from app.core.config import settings
from app.services.multi_source_basics_sync_service import MultiSourceBasicsSyncService
from app.services.quotes_ingestion_service import QuotesIngestionService
from app.services.scheduler_service import get_scheduler_service, set_scheduler_instance
from app.worker.akshare_sync_service import (
    run_akshare_basic_info_sync,
    run_akshare_financial_sync,
    run_akshare_historical_sync,
    run_akshare_quotes_sync,
    run_akshare_status_check,
)
from app.worker.baostock_sync_service import (
    run_baostock_basic_info_sync,
    run_baostock_daily_quotes_sync,
    run_baostock_historical_sync,
    run_baostock_status_check,
)
from app.worker.etf_sync_service import run_etf_sync
from app.worker.favorites_sync_task import run_favorites_data_sync
from app.worker.tushare_sync_service import (
    run_tushare_basic_info_sync,
    run_tushare_financial_sync,
    run_tushare_historical_sync,
    run_tushare_realtime_quotes_hourly,
    run_tushare_status_check,
)

logger = logging.getLogger("app.main")


def _add_cron_job_with_pause(
    scheduler: AsyncIOScheduler,
    func,
    cron_expr: str,
    job_id: str,
    name: str,
    enabled: bool,
    kwargs: Optional[dict] = None,
) -> None:
    """Register a cron job and pause it immediately if disabled."""
    scheduler.add_job(
        func,
        CronTrigger.from_crontab(cron_expr, timezone=settings.TIMEZONE),
        id=job_id,
        name=name,
        kwargs=kwargs or {},
    )
    if not enabled:
        scheduler.pause_job(job_id)


def _register_job_specs(scheduler: AsyncIOScheduler, specs: list[tuple]) -> None:
    """Register a sequence of (func, cron, id, name, enabled, kwargs) job specs."""
    for func, cron_expr, job_id, name, enabled, kwargs in specs:
        _add_cron_job_with_pause(scheduler, func, cron_expr, job_id, name, bool(enabled), kwargs)


def _register_provider_sync_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register Tushare, AKShare, BaoStock, ETF, and Favorites sync jobs."""
    specs = [
        (run_tushare_basic_info_sync, "TUSHARE_BASIC_INFO_SYNC_CRON", "tushare_basic_info_sync", "Basic stock information synchronization (Tushare)", ("TUSHARE_UNIFIED_ENABLED", "TUSHARE_BASIC_INFO_SYNC_ENABLED"), {"force_update": False}),
        (run_tushare_realtime_quotes_hourly, "TUSHARE_REALTIME_QUOTES_HOURLY_CRON", "tushare_realtime_quotes_hourly", "Real-time market synchronization every hour (Tushare)", ("TUSHARE_UNIFIED_ENABLED", "TUSHARE_REALTIME_QUOTES_HOURLY_ENABLED"), None),
        (run_tushare_historical_sync, "TUSHARE_HISTORICAL_SYNC_CRON", "tushare_historical_sync", "Historical data synchronization (Tushare)", ("TUSHARE_UNIFIED_ENABLED", "TUSHARE_HISTORICAL_SYNC_ENABLED"), {"incremental": True}),
        (run_tushare_financial_sync, "TUSHARE_FINANCIAL_SYNC_CRON", "tushare_financial_sync", "Financial data synchronization (Tushare)", ("TUSHARE_UNIFIED_ENABLED", "TUSHARE_FINANCIAL_SYNC_ENABLED"), None),
        (run_tushare_status_check, "TUSHARE_STATUS_CHECK_CRON", "tushare_status_check", "Data source status check (Tushare)", ("TUSHARE_UNIFIED_ENABLED", "TUSHARE_STATUS_CHECK_ENABLED"), None),
        (run_akshare_basic_info_sync, "AKSHARE_BASIC_INFO_SYNC_CRON", "akshare_basic_info_sync", "Basic stock information synchronization (AKShare)", ("AKSHARE_UNIFIED_ENABLED", "AKSHARE_BASIC_INFO_SYNC_ENABLED"), {"force_update": False}),
        (run_akshare_quotes_sync, "AKSHARE_QUOTES_SYNC_CRON", "akshare_quotes_sync", "Real-time market synchronization (AKShare)", ("AKSHARE_UNIFIED_ENABLED", "AKSHARE_QUOTES_SYNC_ENABLED"), None),
        (run_akshare_historical_sync, "AKSHARE_HISTORICAL_SYNC_CRON", "akshare_historical_sync", "Historical data synchronization (AKShare)", ("AKSHARE_UNIFIED_ENABLED", "AKSHARE_HISTORICAL_SYNC_ENABLED"), {"incremental": True}),
        (run_akshare_financial_sync, "AKSHARE_FINANCIAL_SYNC_CRON", "akshare_financial_sync", "Financial data synchronization (AKShare)", ("AKSHARE_UNIFIED_ENABLED", "AKSHARE_FINANCIAL_SYNC_ENABLED"), None),
        (run_akshare_status_check, "AKSHARE_STATUS_CHECK_CRON", "akshare_status_check", "Data source status check (AKShare)", ("AKSHARE_UNIFIED_ENABLED", "AKSHARE_STATUS_CHECK_ENABLED"), None),
        (run_baostock_basic_info_sync, "BAOSTOCK_BASIC_INFO_SYNC_CRON", "baostock_basic_info_sync", "Basic stock information synchronization (BaoStock)", ("BAOSTOCK_UNIFIED_ENABLED", "BAOSTOCK_BASIC_INFO_SYNC_ENABLED"), None),
        (run_baostock_daily_quotes_sync, "BAOSTOCK_DAILY_QUOTES_SYNC_CRON", "baostock_daily_quotes_sync", "Daily K-line data synchronization (BaoStock)", ("BAOSTOCK_UNIFIED_ENABLED", "BAOSTOCK_DAILY_QUOTES_SYNC_ENABLED"), None),
        (run_baostock_historical_sync, "BAOSTOCK_HISTORICAL_SYNC_CRON", "baostock_historical_sync", "Historical data synchronization (BaoStock)", ("BAOSTOCK_UNIFIED_ENABLED", "BAOSTOCK_HISTORICAL_SYNC_ENABLED"), None),
        (run_baostock_status_check, "BAOSTOCK_STATUS_CHECK_CRON", "baostock_status_check", "Data source status check (BaoStock)", ("BAOSTOCK_UNIFIED_ENABLED", "BAOSTOCK_STATUS_CHECK_ENABLED"), None),
        (run_etf_sync, "ETF_SYNC_CRON", "etf_sync", "ETF Data synchronization", ("ETF_SYNC_ENABLED",), {"force_update": False, "days": settings.ETF_SYNC_DAYS, "job_id": "etf_sync"}),
        (run_favorites_data_sync, "FAVORITES_DATA_SYNC_CRON", "favorites_data_sync", "Stock watch list A-share data synchronization", ("FAVORITES_DATA_SYNC_ENABLED",), None),
    ]
    resolved = [
        (fn, getattr(settings, cron_attr), jid, jname, all(getattr(settings, f, False) for f in flags), kw)
        for fn, cron_attr, jid, jname, flags, kw in specs
    ]
    _register_job_specs(scheduler, resolved)


async def _run_startup_warmups() -> None:
    """Warm up trading calendar and optional quotes backfill on startup."""
    try:
        from app.services.trading_calendar_service import get_trading_calendar_service

        await get_trading_calendar_service().warm_up()
    except Exception as exc:
        logger.warning("Trading calendar warm-up skipped: %s", exc)

    if settings.QUOTES_BACKFILL_ON_STARTUP:
        try:
            qi = QuotesIngestionService()
            await qi.ensure_indexes()
            await qi.backfill_last_close_snapshot_if_needed()
        except Exception as exc:
            logger.warning("Startup quotes backfill skipped: %s", exc)


async def initialize_and_start_scheduler() -> AsyncIOScheduler:
    """Create, populate, and start the application AsyncIOScheduler."""
    await _run_startup_warmups()
    scheduler = AsyncIOScheduler(
        timezone=settings.TIMEZONE,
        executors={"default": AsyncIOExecutor()},
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 30},
    )

    multi_source_service = MultiSourceBasicsSyncService()
    asyncio.create_task(multi_source_service.run_full_sync(force=False))

    if settings.QUOTES_INGEST_ENABLED:
        qi = QuotesIngestionService()
        await qi.ensure_indexes()
        scheduler.add_job(
            qi.run_once,
            IntervalTrigger(seconds=settings.QUOTES_INGEST_INTERVAL_SECONDS, timezone=settings.TIMEZONE),
            id="quotes_ingestion_service",
            name="Real-time market quotation warehousing service",
        )

    _register_provider_sync_jobs(scheduler)
    scheduler.start()
    set_scheduler_instance(scheduler)

    try:
        await get_scheduler_service().check_suspended_tasks_on_startup()
    except Exception as exc:
        logger.warning("Suspended task check warning: %s", exc)

    return scheduler


# --- seed_init.py ---
"""Seed initialization for admin users, prompt templates, tools, skills, and indexes."""


import asyncio
import logging
import os
from pathlib import Path
from app.core.config import settings
from app.core.database import get_mongo_db
from app.core.logging_config import setup_logging

logger = logging.getLogger("app.main")


async def print_config_summary(log: logging.Logger) -> None:
    """Log startup configuration summary without exposing credentials."""
    try:
        log.info("=" * 70)
        log.info("TradingAgents-CN Configuration Summary")
        current_dir = Path.cwd()
        env_filename = os.getenv("DOTENV_FILE", ".env")
        for env_file in (current_dir / env_filename, Path(__file__).resolve().parents[3] / env_filename):
            if env_file.exists():
                log.info("Found env file: %s (%d bytes)", env_file, env_file.stat().st_size)
        log.info("MongoDB: %s:%s/%s", settings.MONGODB_HOST, settings.MONGODB_PORT, settings.MONGODB_DATABASE)
        log.info("Redis: %s:%s/%s", settings.REDIS_HOST, settings.REDIS_PORT, settings.REDIS_DB)
        log.info("=" * 70)
    except Exception as exc:
        log.error("Failed to print config summary: %s", exc)


async def seed_admin_and_bootstrap() -> None:
    """Bootstrap initial administrator and community configuration."""
    try:
        from app.services.user_service import bootstrap_first_admin

        await bootstrap_first_admin()
    except Exception as exc:
        logger.error("Initial admin bootstrap error: %s", exc)

    try:
        from app.services.community_bootstrap_service import import_bootstrap_config

        await import_bootstrap_config()
    except Exception as exc:
        logger.error("Community bootstrap import error: %s", exc)


async def register_tools_skills_and_mcp() -> None:
    """Load custom tools, active skills, and MCP server tools into ToolRegistry."""
    db = get_mongo_db()
    try:
        from core.tools.custom_tool import CustomToolDefinition, register_custom_tool

        async for doc in db.custom_tools.find():
            doc.pop("_id", None)
            await register_custom_tool(CustomToolDefinition(**doc))
    except Exception as exc:
        logger.error("Custom tools initialization failed: %s", exc)

    try:
        from core.tools import get_tool_registry
        from core.tools.external_skill_loader import load_external_skills_to_registry
        from core.tools.execution_logger import get_tool_execution_logger
        from app.routers.skills import _register_skill_to_registry

        async for doc in db.skills.find({"enabled": True}):
            await _register_skill_to_registry(doc)
        await load_external_skills_to_registry(db, get_tool_registry())
        get_tool_execution_logger().set_db(db)
    except Exception as exc:
        logger.error("Skill initialization failed: %s", exc)

    try:
        from app.pro.services.mcp_service import MCPService

        await MCPService(db).restore_enabled_servers()
    except Exception as exc:
        logger.error("MCP server restoration failed: %s", exc)


async def sync_prompts_and_runtime_settings() -> None:
    """Bridge config to env, seed system prompt templates, and start worker pool."""
    try:
        from app.core.config_bridge import bridge_config_to_env

        bridge_config_to_env()
    except Exception as exc:
        logger.warning("Config bridge warning: %s", exc)

    try:
        from app.services.system_prompt_seed_service import ensure_system_prompt_templates

        await ensure_system_prompt_templates()
    except Exception as exc:
        logger.error("System prompt seed failed: %s", exc)

    try:
        from app.services.config_provider import provider as config_provider

        eff = await config_provider.get_effective_system_settings()
        desired_level = str(eff.get("log_level", "INFO")).upper()
        setup_logging(log_level=desired_level)
    except Exception as exc:
        logger.warning("Dynamic settings warning: %s", exc)

    try:
        from app.services.workflow_registry import initialize_builtin_workflows

        initialize_builtin_workflows()
    except Exception as exc:
        logger.error("Workflow registry init failed: %s", exc)

    await print_config_summary(logger)

    try:
        from app.services.thread_worker import start_thread_worker

        max_workers = getattr(settings, "WORKER_MAX_CONCURRENT", 3)
        await asyncio.wait_for(start_thread_worker(max_workers=max_workers), timeout=20.0)
    except Exception as exc:
        logger.error("Thread worker startup error: %s", exc)


# --- __init__.py ---
"""FastAPI lifespan coordinator delegating database, seed, and scheduler startup."""


from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from app.core.logging_config import setup_logging
# re-export: initialize_database_and_migrations, shutdown_database_and_workers
# re-export: initialize_and_start_scheduler
# re-export: print_config_summary, register_tools_skills_and_mcp, seed_admin_and_bootstrap, sync_prompts_and_runtime_settings

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
