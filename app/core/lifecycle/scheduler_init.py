"""APScheduler job registration and startup/shutdown lifecycle management."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

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
