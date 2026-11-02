"""Database initialization, migration, and shutdown helpers for FastAPI lifespan."""
from __future__ import annotations

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
