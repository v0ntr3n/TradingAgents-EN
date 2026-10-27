"""
TradingAgents-CN v2.1.0 FastAPI Backend
Main application entry

Copyright (c) 2024-2026 hsliuping. All rights reserved.
All rights reserved (c) 2024-2026 hsliuping. All rights reserved.

This software is proprietary and confidential. Unauthorized copying, distribution,
or use of this software, via any medium, is strictly prohibited.
The Software is proprietary and confidential. Unauthorized copying, distribution or use of this software through any medium is strictly prohibited.

For commercial licensing, please contact: hsliup@163.com
For commercial licensing inquiries, please contact:hsliup@163.com
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
import logging
import time
from datetime import datetime
from contextlib import asynccontextmanager
import asyncio
from pathlib import Path

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.logging_config import setup_logging
from app.router_registry import register_routers
from app.services.basics_sync_service import get_basics_sync_service
from app.services.multi_source_basics_sync_service import MultiSourceBasicsSyncService
from app.services.scheduler_service import set_scheduler_instance
from app.worker.tushare_sync_service import (
    run_tushare_realtime_quotes_hourly,
    run_tushare_basic_info_sync,
    # run_tushare_quotes_sync,  # 🔥 Disabled, managed by run_tushare_realtime_quotes_hourly
    run_tushare_historical_sync,
    run_tushare_financial_sync,
    run_tushare_status_check
)
from app.worker.akshare_sync_service import (
    run_akshare_basic_info_sync,
    run_akshare_quotes_sync,
    run_akshare_historical_sync,
    run_akshare_financial_sync,
    run_akshare_status_check
)
from app.worker.baostock_sync_service import (
    run_baostock_basic_info_sync,
    run_baostock_daily_quotes_sync,
    run_baostock_historical_sync,
    run_baostock_status_check
)
from app.worker.etf_sync_service import run_etf_sync
from app.worker.favorites_sync_task import run_favorites_data_sync
# Hong Kong stocks and US stocks are now available on demand.+Cache mode, no need for scheduled synchronization tasks anymore
# from app.worker.hk_sync_service import ...
# from app.worker.us_sync_service import ...
from app.middleware.operation_log_middleware import OperationLogMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.services.quotes_ingestion_service import QuotesIngestionService


def get_version() -> str:
    """Read version number from VERSION file"""
    try:
        version_file = Path(__file__).parent.parent / "VERSION"
        if version_file.exists():
            return version_file.read_text(encoding='utf-8').strip()
    except Exception:
        pass
    return "2.1.0"  # Default version number


def get_build_info() -> dict:
    """Read build information from BUILD_INFO file"""
    try:
        build_info_file = Path(__file__).parent.parent / "BUILD_INFO"
        if build_info_file.exists():
            import json
            return json.loads(build_info_file.read_text(encoding='utf-8'))
    except Exception as e:
        logging.debug(f"Failed to read BUILD_INFO: {e}")
    return {}




async def _print_config_summary(logger):
    """Show configuration summary"""
    try:
        logger.info("=" * 70)
        logger.info("📋 TradingAgents-CN Configuration Summary")
        logger.info("=" * 70)

        # .env File path information
        import os
        from pathlib import Path

        current_dir = Path.cwd()
        logger.info(f"📁 Current working directory: {current_dir}")

        # Supports specifying different .env files through the DOTENV_FILE environment variable (such as .env.jdyun for JD Cloud mode)
        env_filename = os.getenv("DOTENV_FILE", ".env")
        logger.info(f"📄 Environment file: {env_filename}")

        # Check possible .env file locations
        env_files_to_check = [
            current_dir / env_filename,
            current_dir / "app" / env_filename,
            Path(__file__).parent.parent / env_filename,  # Project root directory
        ]

        logger.info("🔍 Checking .env file locations:")
        env_file_found = False
        for env_file in env_files_to_check:
            if env_file.exists():
                logger.info(f"  ✅ Found: {env_file} (size: {env_file.stat().st_size} bytes)")
                env_file_found = True
                # Show the first few lines of the file (hide sensitive information)
                try:
                    with open(env_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()[:5]  # Read only the first 5 lines
                        logger.info(f"     Preview (first 5 lines):")
                        for i, line in enumerate(lines, 1):
                            # Hide lines containing sensitive information such as passwords, keys, etc.
                            if any(keyword in line.upper() for keyword in ['PASSWORD', 'SECRET', 'KEY', 'TOKEN']):
                                logger.info(f"       {i}: {line.split('=')[0]}=***")
                            else:
                                logger.info(f"       {i}: {line.strip()}")
                except Exception as e:
                    logger.warning(f"     Could not preview file: {e}")
            else:
                logger.info(f"  ❌ Not found: {env_file}")
        
        if not env_file_found:
            logger.warning("⚠️  No .env file found in checked locations")
        
        # Pydantic Settings Configuration loading status
        logger.info("⚙️  Pydantic Settings Configuration:")
        logger.info(f"  • Settings class: {settings.__class__.__name__}")
        logger.info(f"  • Config source: {getattr(settings.model_config, 'env_file', 'Not specified')}")
        logger.info(f"  • Encoding: {getattr(settings.model_config, 'env_file_encoding', 'Not specified')}")
        
        # Show the source of some key configuration values (environment variables vs default values)
        key_settings = ['HOST', 'PORT', 'DEBUG', 'MONGODB_HOST', 'REDIS_HOST']
        logger.info("  • Key settings sources:")
        for setting_name in key_settings:
            env_var_name = setting_name
            env_value = os.getenv(env_var_name)
            config_value = getattr(settings, setting_name, None)
            if env_value is not None:
                logger.info(f"    - {setting_name}: from environment variable ({config_value})")
            else:
                logger.info(f"    - {setting_name}: using default value ({config_value})")
        
        # environmental information
        env = "Production" if settings.is_production else "Development"
        logger.info(f"Environment: {env}")

        # Database connection
        logger.info(f"MongoDB: {settings.MONGODB_HOST}:{settings.MONGODB_PORT}/{settings.MONGODB_DATABASE}")
        logger.info(f"Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}")

        # Agent configuration
        import os
        if settings.PROXY_ENABLED and (settings.HTTP_PROXY or settings.HTTPS_PROXY):
            logger.info("Proxy Configuration:")
            logger.info(f"  🔧 PROXY_ENABLED: True")
            if settings.HTTP_PROXY:
                logger.info(f"  HTTP_PROXY: {settings.HTTP_PROXY}")
            if settings.HTTPS_PROXY:
                logger.info(f"  HTTPS_PROXY: {settings.HTTPS_PROXY}")
            if settings.NO_PROXY:
                # Only show the first 3 domain names
                no_proxy_list = settings.NO_PROXY.split(',')
                if len(no_proxy_list) <= 3:
                    logger.info(f"  NO_PROXY: {settings.NO_PROXY}")
                else:
                    logger.info(f"  NO_PROXY: {','.join(no_proxy_list[:3])}... ({len(no_proxy_list)} domains)")
            logger.info(f"  ✅ Proxy environment variables set successfully")
        else:
            if settings.PROXY_ENABLED:
                logger.info("Proxy: Enabled but not configured (no proxy address)")
            else:
                logger.info("Proxy: Disabled (direct connection)")

        # Check large model configuration
        try:
            from app.services.config_service import config_service
            config = await config_service.get_system_config()
            if config and config.llm_configs:
                enabled_llms = [llm for llm in config.llm_configs if llm.enabled]
                logger.info(f"Enabled LLMs: {len(enabled_llms)}")
                if enabled_llms:
                    for llm in enabled_llms[:3]:  # Only show first 3
                        logger.info(f"  • {llm.provider}: {llm.model_name}")
                    if len(enabled_llms) > 3:
                        logger.info(f"  • ... and {len(enabled_llms) - 3} more")
                else:
                    logger.warning("⚠️  No LLM enabled. Please configure at least one LLM in Web UI.")
            else:
                logger.warning("⚠️  No LLM configured. Please configure at least one LLM in Web UI.")
        except Exception as e:
            logger.warning(f"⚠️  Failed to check LLM configs: {e}")

        # Check data source configuration
        try:
            if config and config.data_source_configs:
                enabled_sources = [ds for ds in config.data_source_configs if ds.enabled]
                logger.info(f"Enabled Data Sources: {len(enabled_sources)}")
                if enabled_sources:
                    for ds in enabled_sources[:3]:  # Only show first 3
                        logger.info(f"  • {ds.type.value}: {ds.name}")
                    if len(enabled_sources) > 3:
                        logger.info(f"  • ... and {len(enabled_sources) - 3} more")
            else:
                logger.info("Data Sources: Using default (AKShare)")
        except Exception as e:
            logger.warning(f"⚠️  Failed to check data source configs: {e}")

        logger.info("=" * 70)
    except Exception as e:
        logger.error(f"Failed to print config summary: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    # Initialize on startup
    setup_logging()
    logger = logging.getLogger("app.main")

    # Verify startup configuration
    try:
        from app.core.startup_validator import validate_startup_config
        validate_startup_config()
    except Exception as e:
        logger.error(f"Configuration verification failed: {e}")
        raise

    await init_db()

    # Perform database migration
    try:
        from app.core.database import get_mongo_db as _get_db
        from migrations.runner import MigrationRunner

        _mig_db = _get_db()
        _runner = MigrationRunner(_mig_db)
        _results = await _runner.run_pending()
        if _results:
            _ok = sum(1 for r in _results if r["status"] == "success")
            _fail = sum(1 for r in _results if r["status"] == "failed")
            logger.info(f"📦 Database migration completed: {_ok} success, {_fail} failed")
        else:
            logger.info("📦 The database is already the latest version")
    except Exception as e:
        logger.error(f"❌ Database migration failed: {e}")
        # Migration failure does not prevent startup, but logs an error
        # If you need to force migration to start successfully, uncomment the next line:
        # raise

    # First boot: create an initial administrator based on ADMIN_DEFAULT_PASSWORD when the library is empty (the community version has no registration interface)
    try:
        from app.services.user_service import bootstrap_first_admin
        await bootstrap_first_admin()
    except Exception as e:
        logger.error(f"❌ Initial administrator boot exception: {e}")

    # Start bootstrapping for the first time: Import the minimum system configuration of the community version (idempotent, skip if the set is not empty)
    # Must be executed before ensure_system_prompt_templates, otherwise prompt_templates will be skipped by this package after it is occupied by the latter.
    try:
        from app.services.community_bootstrap_service import import_bootstrap_config
        await import_bootstrap_config()
    except Exception as e:
        logger.error(f"❌ Failed to import startup configuration (does not affect service startup): {e}", exc_info=True)

    # Initialize custom tools
    try:
        from app.core.database import get_mongo_db
        from core.tools.custom_tool import CustomToolDefinition, register_custom_tool
        
        db = get_mongo_db()
        cursor = db.custom_tools.find()
        async for doc in cursor:
            try:
                # Remove _id field to conform to Pydantic model
                if "_id" in doc:
                    del doc["_id"]
                definition = CustomToolDefinition(**doc)
                await register_custom_tool(definition)
                logger.info(f"✅ Loaded custom tool: {definition.id}")
            except Exception as e:
                logger.error(f"❌ Failed to load custom tool {doc.get('id')}: {e}")
                
        logger.info("Custom tools initialization completed")
    except Exception as e:
        logger.error(f"❌ Custom tools initialization failed: {e}")

    # Initialize Skill: Register the active/enabled Skill to ToolRegistry for the Agent to call when running
    try:
        from app.core.database import get_mongo_db
        from core.tools import get_tool_registry
        from core.tools.external_skill_loader import load_external_skills_to_registry
        from app.routers.skills import _register_skill_to_registry

        db = get_mongo_db()
        standard_count = 0
        async for doc in db.skills.find({"enabled": True}):
            await _register_skill_to_registry(doc)
            standard_count += 1
        external_count = await load_external_skills_to_registry(db, get_tool_registry())
        logger.info(f"✅ Skill Initialization completed, loaded {standard_count} a standard Skill,{external_count} AI generated Skill")

        # Initialize tool execution logger
        from core.tools.execution_logger import get_tool_execution_logger
        get_tool_execution_logger().set_db(db)
        logger.info("✅ Tool execution logger initialized")
    except Exception as e:
        logger.error(f"❌ Skill Initialization failed: {e}", exc_info=True)

    # Restore enabled MCP server tool to ToolRegistry
    # After the backend is restarted, the MCP tool will not be automatically registered and needs to be restored from the mcp_server_configs collection
    try:
        from app.pro.services.mcp_service import MCPService
        mcp_service = MCPService(db)
        await mcp_service.restore_enabled_servers()
        logger.info("✅ MCP Server tool recovery completed")
    except Exception as e:
        logger.error(f"❌ MCP Server tool recovery failed: {e}", exc_info=True)

    #  Configuration bridging: Write unified configuration into environment variables for use by TradingAgents core library
    try:
        from app.core.config_bridge import bridge_config_to_env
        bridge_config_to_env()
    except Exception as e:
        logger.warning(f"⚠️  Failed to configure bridge: {e}")
        logger.warning("⚠️  TradingAgents Will use the configuration in the .env file")

    # 🔧 JD Cloud Cooperation Edition: Initialize database configuration from environment variables when starting for the first time
    try:
        from app.services.jdyun_init import init_jdyun_config
        init_jdyun_config()
    except Exception as e:
        logger.warning(f"⚠️  JD Cloud configuration initialization failed: {e}")

    # Synchronization capability index during startup: After the tool metadata is changed, it can be incrementally written to the vector library after restarting.
    # Change to background asynchronous tasks to avoid Embedding model loading blocking project startup
    async def _sync_capability_index_background():
        """Background asynchronous synchronization capability index, non-blocking startup"""
        try:
            # Delay 5 seconds to allow uvicorn to fully start and listen on the port
            await asyncio.sleep(5)

            from app.core.database import get_mongo_db
            from app.services.capability_index_service import CapabilityIndexService

            result = await CapabilityIndexService(get_mongo_db()).ensure_index()
            logger.info(
                "✅ Ability index synchronization completed: %s %d/%d backend=%s",
                result.sync_mode,
                result.indexed_documents,
                result.total_documents,
                result.vector_backend,
            )

            # Send system notification to all administrators when index skipped
            if result.sync_mode.startswith("skipped_"):
                try:
                    from app.services.user_service import UserService
                    from app.services.notifications_service import get_notifications_service
                    from app.models.notification import NotificationCreate

                    user_svc = UserService()
                    users = await user_svc.list_users(limit=100)
                    notif_svc = get_notifications_service()

                    skip_reason = "Embedding API Not available" if "embedding" in result.sync_mode else "Not configured Embedding"
                    for u in users:
                        await notif_svc.create_and_publish(NotificationCreate(
                            user_id=u.id,
                            type="system",
                            title="Capability index not built",
                            content=f"Capability index building skipped on system startup ({skip_reason}) . Please configure a valid Embedding API Key in the system settings first, and then -> Manually rebuild the index in Tools Capability Indexing.",
                            source="capability_index",
                            severity="warning",
                        ))
                    logger.info("📢 Capability index skip notification sent to %d users", len(users))
                except Exception as ne:
                    logger.warning(f"⚠️ Failed to send capability index notification: {ne}")
        except Exception as e:
            logger.error(f"❌ Capability index synchronization failed: {e}", exc_info=True)

    # Create background tasks without blocking startup
    asyncio.create_task(_sync_capability_index_background())
    logger.info("📋 Capability index synchronization has started in the background")

    # Synchronize the user manual vector index during startup: it will be automatically rebuilt after restarting after the manual content is changed.
    # Allow the use of question and answer robots to retrieve answers based on vector semantics"How to do analysis"and other natural language problems
    async def _sync_user_manual_index_background():
        """Asynchronously builds user manual vector index in the background without blocking startup"""
        try:
            from core.knowledge.user_manual_manager import UserManualManager
            from app.core.database import get_mongo_db

            manager = UserManualManager(db=get_mongo_db())
            if not manager.available:
                logger.warning(
                    "⚠️ [User manual index] Vector library/Embedding is not available, skip building."
                    "Using the Q&A bot will fall back to keyword matching mode."
                )
                return

            # Delay 3 seconds to allow uvicorn to fully start and listen on the port
            await asyncio.sleep(3)

            # Perform synchronized indexing in a separate thread to avoid blocking the event loop
            # ensure_indexed Is a synchronous method (including a large number of embedding requests),
            # Calling it directly in the coroutine will block the uvicorn listening port
            result = await asyncio.to_thread(manager.ensure_indexed, force=False)
            if result["rebuilt"]:
                logger.info(
                    "✅ User manual index construction completed: %d slices, source %d manuals, signed=%s",
                    result["sections_count"],
                    result["manuals_count"],
                    result["signature"][:8],
                )
            elif result["skipped"]:
                logger.info(
                    "📋 User manual index skips rebuild (signature consistent), existing %d slices",
                    result["sections_count"],
                )
            else:
                logger.warning(
                    "⚠️ User manual index build failed: %s",
                    result.get("error", "unknown reason"),
                )
        except Exception as e:
            logger.error(f"❌ User manual index synchronization failed: {e}", exc_info=True)

    asyncio.create_task(_sync_user_manual_index_background())
    logger.info("📖 User manual index synchronization has started in the background")

    # The default prompt word template of the synchronization system during startup: write the fallback prompt word in the code into the database for unified management
    try:
        from app.services.system_prompt_seed_service import ensure_system_prompt_templates
        await ensure_system_prompt_templates()
        logger.info("✅ System default prompt word template synchronization completed")
    except Exception as e:
        logger.error(f"❌ System default prompt word template synchronization failed: {e}", exc_info=True)

    # Apply dynamic settings (log_level, enable_monitoring) from ConfigProvider
    try:
        from app.services.config_provider import provider as config_provider  # local import to avoid early DB init issues
        eff = await config_provider.get_effective_system_settings()
        desired_level = str(eff.get("log_level", "INFO")).upper()
        setup_logging(log_level=desired_level)
        for name in ("webapi", "worker", "uvicorn", "fastapi"):
            logging.getLogger(name).setLevel(desired_level)
        try:
            from app.middleware.operation_log_middleware import set_operation_log_enabled
            set_operation_log_enabled(bool(eff.get("enable_monitoring", True)))
        except Exception:
            pass
    except Exception as e:
        logging.getLogger("webapi").warning(f"Failed to apply dynamic settings: {e}")

    # Initialize the workflow registry
    try:
        from app.services.workflow_registry import initialize_builtin_workflows
        initialize_builtin_workflows()
        logger.info("✅ Workflow registry initialization completed")
    except Exception as e:
        logger.error(f"❌ Workflow registry initialization failed: {e}")

    # Show configuration summary
    logger.info("⏳ Start displaying configuration summary")
    await _print_config_summary(logger)
    logger.info("✅ Configuration summary display completed")

    # 🔥 Start the thread pool Worker (process queue tasks within the Backend process)
    try:
        logger.info("⏳ Start the thread pool Worker")
        from app.services.thread_worker import start_thread_worker
        max_workers = getattr(settings, 'WORKER_MAX_CONCURRENT', 3)
        await asyncio.wait_for(start_thread_worker(max_workers=max_workers), timeout=20.0)
        logger.info(f"✅ Thread pool Worker started (max_workers={max_workers})")
        logger.info("✅ Thread pool Worker startup phase completed")
    except Exception as e:
        logger.error(f"❌ Thread pool Worker failed to start: {e}", exc_info=True)
        # Does not prevent Backend from starting, but the queue tasks will not be processed

    logger.info("TradingAgents FastAPI backend started")

    # Initialize the transaction calendar cache (determine today/the latest real transaction day for JIT data freshness judgment)
    try:
        from app.services.trading_calendar_service import get_trading_calendar_service
        await get_trading_calendar_service().warm_up()
    except Exception as e:
        logger.warning(f"⚠️ Trading calendar cache initialization failed (does not affect startup): {e}")

    # Startup period: If it is necessary to supplement the closing snapshot of the previous trading day during the market close
    if settings.QUOTES_BACKFILL_ON_STARTUP:
        try:
            qi = QuotesIngestionService()
            await qi.ensure_indexes()
            await qi.backfill_last_close_snapshot_if_needed()
        except Exception as e:
            logger.warning(f"Startup backfill failed (ignored): {e}")

    # Start daily scheduled tasks: configurable
    scheduler: AsyncIOScheduler | None = None
    try:
        from croniter import croniter
    except Exception:
        croniter = None  # optional dependencies
    try:
        # 🔥 Configure APScheduler: concurrent execution of the same task is not allowed
        # max_instances=1 Ensure that only one instance of the same task can be executed at the same time
        # If the task is executing, new triggers will be skipped
        from apscheduler.executors.asyncio import AsyncIOExecutor
        
        # Create an asynchronous executor
        executors = {
            'default': AsyncIOExecutor()
        }
        
        # Configure job_defaults: concurrent execution of the same task is not allowed
        job_defaults = {
            'coalesce': True,  # Merge missed tasks (skip new triggers if task is executing)
            'max_instances': 1,  # Maximum 1 instance of the same task (concurrency is not allowed)
            'misfire_grace_time': 30  # It can still be executed within 30 seconds after the execution time is missed.
        }
        
        scheduler = AsyncIOScheduler(
            timezone=settings.TIMEZONE,
            executors=executors,
            job_defaults=job_defaults
        )

        # Use multiple data source synchronization services (support automatic switching)
        multi_source_service = MultiSourceBasicsSyncService()

        # 🔥 Read data source priority configuration from database (instead of hardcoding)
        # Exclude caching layers such as local/mongodb and only use real API data sources
        async def get_preferred_sources_from_db():
            """Read enabled API data source priority from database"""
            try:
                from app.core.data_source_priority import get_enabled_data_sources_async
                all_sources = await get_enabled_data_sources_async("a_shares")
                # Exclude the caching layer and keep only the real API data source
                api_sources = [s for s in all_sources if s not in ("local", "mongodb", "local_file")]
                # The basic stock information synchronization during the startup period does not use QMT as the preferred source to avoid the QMT full market list from slowing down the startup.
                filtered_sources = [s for s in api_sources if s != "qmt"]
                if api_sources:
                    logger.info(f"📊 Stock basic information synchronization original data source priority (from database): {' > '.join(api_sources)}")
                    if filtered_sources != api_sources:
                        logger.info(f"🧹 Stock basic information synchronization has excluded QMT preferred priority, actual order: {' > '.join(filtered_sources)}")
                    return filtered_sources or None
                else:
                    logger.warning("⚠️ There is no API data source enabled in the database, using the default configuration")
                    return None
            except Exception as e:
                logger.error(f"❌ Failed to read data source priority: {e}, Use default configuration")
                return None

        # Try once immediately after startup (without blocking)
        async def run_sync_with_sources():
            preferred_sources = await get_preferred_sources_from_db()
            await multi_source_service.run_full_sync(force=False, preferred_sources=preferred_sources)

        asyncio.create_task(run_sync_with_sources())

        # Configure Scheduling: Use CRON First, Second HH:MM
        # 🔥 Scheduled tasks also need to read the latest data source priority from the database
        async def scheduled_sync_with_db_priority():
            """Scheduled task: read the latest data source priority from the database each time it is executed"""
            preferred_sources = await get_preferred_sources_from_db()
            await multi_source_service.run_full_sync(force=False, preferred_sources=preferred_sources)

        if settings.SYNC_STOCK_BASICS_ENABLED:
            if settings.SYNC_STOCK_BASICS_CRON:
                # If cron expression is provided
                scheduler.add_job(
                    scheduled_sync_with_db_priority,
                    CronTrigger.from_crontab(settings.SYNC_STOCK_BASICS_CRON, timezone=settings.TIMEZONE),
                    id="basics_sync_service",
                    name="Basic stock information synchronization (multiple data sources)"
                )
                logger.info(f"📅 Stock basics sync scheduled by CRON: {settings.SYNC_STOCK_BASICS_CRON} ({settings.TIMEZONE})")
            else:
                hh, mm = (settings.SYNC_STOCK_BASICS_TIME or "06:30").split(":")
                scheduler.add_job(
                    scheduled_sync_with_db_priority,
                    CronTrigger(hour=int(hh), minute=int(mm), timezone=settings.TIMEZONE),
                    id="basics_sync_service",
                    name="Basic stock information synchronization (multiple data sources)"
                )
                logger.info(f"📅 Stock basics sync scheduled daily at {settings.SYNC_STOCK_BASICS_TIME} ({settings.TIMEZONE})")

        # Real-time market warehousing task (every N seconds), internal self-determination of trading period
        if settings.QUOTES_INGEST_ENABLED:
            quotes_ingestion = QuotesIngestionService()
            await quotes_ingestion.ensure_indexes()
            scheduler.add_job(
                quotes_ingestion.run_once,  # coroutine function; AsyncIOScheduler will await it
                IntervalTrigger(seconds=settings.QUOTES_INGEST_INTERVAL_SECONDS, timezone=settings.TIMEZONE),
                id="quotes_ingestion_service",
                name="Real-time market quotation warehousing service"
            )
            logger.info(f"⏱ The real-time market quotation warehousing task has been started: every {settings.QUOTES_INGEST_INTERVAL_SECONDS}s")

        # Tushare Unified data synchronization task configuration
        logger.info("🔄 Configure Tushare unified data synchronization task...")

        # Basic information synchronization tasks
        scheduler.add_job(
            run_tushare_basic_info_sync,
            CronTrigger.from_crontab(settings.TUSHARE_BASIC_INFO_SYNC_CRON, timezone=settings.TIMEZONE),
            id="tushare_basic_info_sync",
            name="Basic stock information synchronization (Tushare)",
            kwargs={"force_update": False}
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_BASIC_INFO_SYNC_ENABLED):
            scheduler.pause_job("tushare_basic_info_sync")
            logger.info(f"⏸️ Tushare Basic information synchronization has been added but suspended: {settings.TUSHARE_BASIC_INFO_SYNC_CRON}")
        else:
            logger.info(f"📅 Tushare Basic information synchronization has been configured: {settings.TUSHARE_BASIC_INFO_SYNC_CRON}")

        # 🔥 The old real-time market synchronization tasks have been disabled and are managed by run_tushare_realtime_quotes_hourly
        # Avoid conflict with the scheduled task of 31 minutes per hour (free users can only call it once per hour)
        # scheduler.add_job(
        #     run_tushare_quotes_sync,
        #     CronTrigger.from_crontab(settings.TUSHARE_QUOTES_SYNC_CRON, timezone=settings.TIMEZONE),
        #     id="tushare_quotes_sync",
        #     name="Real-time market synchronization (Tushare)"
        # )
        logger.info(f"⏸️ Tushare The real-time market synchronization task has been disabled and is managed by a scheduled task at 31 minutes every hour.")

        # Tushare Real-time market synchronization task every hour (free users can only call it once per hour)
        scheduler.add_job(
            run_tushare_realtime_quotes_hourly,
            CronTrigger.from_crontab(settings.TUSHARE_REALTIME_QUOTES_HOURLY_CRON, timezone=settings.TIMEZONE),
            id="tushare_realtime_quotes_hourly",
            name="Real-time market synchronization every hour (Tushare, free users 31 minutes per hour)"
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_REALTIME_QUOTES_HOURLY_ENABLED):
            scheduler.pause_job("tushare_realtime_quotes_hourly")
            logger.info(f"⏸️ Tushare Hourly synchronization of real-time quotes has been added but suspended: {settings.TUSHARE_REALTIME_QUOTES_HOURLY_CRON}")
        else:
            logger.info(f"📈 Tushare Hourly synchronization of real-time quotes has been configured: {settings.TUSHARE_REALTIME_QUOTES_HOURLY_CRON} (Executed at 31 minutes every hour,15:00 Automatically save to historical data)")

        # Historical data synchronization task
        scheduler.add_job(
            run_tushare_historical_sync,
            CronTrigger.from_crontab(settings.TUSHARE_HISTORICAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="tushare_historical_sync",
            name="Historical data synchronization (Tushare)",
            kwargs={"incremental": True}
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_HISTORICAL_SYNC_ENABLED):
            scheduler.pause_job("tushare_historical_sync")
            logger.info(f"⏸️ Tushare Historical data sync added but paused: {settings.TUSHARE_HISTORICAL_SYNC_CRON}")
        else:
            logger.info(f"📊 Tushare Historical data synchronization is configured: {settings.TUSHARE_HISTORICAL_SYNC_CRON}")

        # Financial data synchronization tasks
        scheduler.add_job(
            run_tushare_financial_sync,
            CronTrigger.from_crontab(settings.TUSHARE_FINANCIAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="tushare_financial_sync",
            name="Financial data synchronization (Tushare)"
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_FINANCIAL_SYNC_ENABLED):
            scheduler.pause_job("tushare_financial_sync")
            logger.info(f"⏸️ Tushare Financial data sync added but paused: {settings.TUSHARE_FINANCIAL_SYNC_CRON}")
        else:
            logger.info(f"💰 Tushare Financial data synchronization configured: {settings.TUSHARE_FINANCIAL_SYNC_CRON}")

        # status check task
        scheduler.add_job(
            run_tushare_status_check,
            CronTrigger.from_crontab(settings.TUSHARE_STATUS_CHECK_CRON, timezone=settings.TIMEZONE),
            id="tushare_status_check",
            name="Data source status check (Tushare)"
        )
        if not (settings.TUSHARE_UNIFIED_ENABLED and settings.TUSHARE_STATUS_CHECK_ENABLED):
            scheduler.pause_job("tushare_status_check")
            logger.info(f"⏸️ Tushare Status check added but paused: {settings.TUSHARE_STATUS_CHECK_CRON}")
        else:
            logger.info(f"🔍 Tushare Status check configured: {settings.TUSHARE_STATUS_CHECK_CRON}")

        # AKShare Unified data synchronization task configuration
        logger.info("🔄 Configure AKShare unified data synchronization task...")

        # Basic information synchronization tasks
        scheduler.add_job(
            run_akshare_basic_info_sync,
            CronTrigger.from_crontab(settings.AKSHARE_BASIC_INFO_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_basic_info_sync",
            name="Basic stock information synchronization (AKShare)",
            kwargs={"force_update": False}
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_BASIC_INFO_SYNC_ENABLED):
            scheduler.pause_job("akshare_basic_info_sync")
            logger.info(f"⏸️ AKShare Basic information synchronization has been added but suspended: {settings.AKSHARE_BASIC_INFO_SYNC_CRON}")
        else:
            logger.info(f"📅 AKShare Basic information synchronization has been configured: {settings.AKSHARE_BASIC_INFO_SYNC_CRON}")

        # Real-time market synchronization tasks
        scheduler.add_job(
            run_akshare_quotes_sync,
            CronTrigger.from_crontab(settings.AKSHARE_QUOTES_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_quotes_sync",
            name="Real-time market synchronization (AKShare)"
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_QUOTES_SYNC_ENABLED):
            scheduler.pause_job("akshare_quotes_sync")
            logger.info(f"⏸️ AKShare Quote synchronization has been added but suspended: {settings.AKSHARE_QUOTES_SYNC_CRON}")
        else:
            logger.info(f"📈 AKShare Quote synchronization has been configured: {settings.AKSHARE_QUOTES_SYNC_CRON}")

        # Historical data synchronization task
        scheduler.add_job(
            run_akshare_historical_sync,
            CronTrigger.from_crontab(settings.AKSHARE_HISTORICAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_historical_sync",
            name="Historical data synchronization (AKShare)",
            kwargs={"incremental": True}
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_HISTORICAL_SYNC_ENABLED):
            scheduler.pause_job("akshare_historical_sync")
            logger.info(f"⏸️ AKShare Historical data sync added but paused: {settings.AKSHARE_HISTORICAL_SYNC_CRON}")
        else:
            logger.info(f"📊 AKShare Historical data synchronization is configured: {settings.AKSHARE_HISTORICAL_SYNC_CRON}")

        # Financial data synchronization tasks
        scheduler.add_job(
            run_akshare_financial_sync,
            CronTrigger.from_crontab(settings.AKSHARE_FINANCIAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="akshare_financial_sync",
            name="Financial data synchronization (AKShare)"
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_FINANCIAL_SYNC_ENABLED):
            scheduler.pause_job("akshare_financial_sync")
            logger.info(f"⏸️ AKShare Financial data sync added but paused: {settings.AKSHARE_FINANCIAL_SYNC_CRON}")
        else:
            logger.info(f"💰 AKShare Financial data synchronization configured: {settings.AKSHARE_FINANCIAL_SYNC_CRON}")

        # status check task
        scheduler.add_job(
            run_akshare_status_check,
            CronTrigger.from_crontab(settings.AKSHARE_STATUS_CHECK_CRON, timezone=settings.TIMEZONE),
            id="akshare_status_check",
            name="Data source status check (AKShare)"
        )
        if not (settings.AKSHARE_UNIFIED_ENABLED and settings.AKSHARE_STATUS_CHECK_ENABLED):
            scheduler.pause_job("akshare_status_check")
            logger.info(f"⏸️ AKShare Status check added but paused: {settings.AKSHARE_STATUS_CHECK_CRON}")
        else:
            logger.info(f"🔍 AKShare Status check configured: {settings.AKSHARE_STATUS_CHECK_CRON}")

        # BaoStock Unified data synchronization task configuration
        logger.info("🔄 Configure BaoStock unified data synchronization task...")

        # Basic information synchronization tasks
        scheduler.add_job(
            run_baostock_basic_info_sync,
            CronTrigger.from_crontab(settings.BAOSTOCK_BASIC_INFO_SYNC_CRON, timezone=settings.TIMEZONE),
            id="baostock_basic_info_sync",
            name="Basic stock information synchronization (BaoStock)"
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_BASIC_INFO_SYNC_ENABLED):
            scheduler.pause_job("baostock_basic_info_sync")
            logger.info(f"⏸️ BaoStock Basic information synchronization has been added but suspended: {settings.BAOSTOCK_BASIC_INFO_SYNC_CRON}")
        else:
            logger.info(f"📋 BaoStock Basic information synchronization has been configured: {settings.BAOSTOCK_BASIC_INFO_SYNC_CRON}")

        # Daily K-line synchronization task (note: BaoStock does not support real-time market conditions)
        scheduler.add_job(
            run_baostock_daily_quotes_sync,
            CronTrigger.from_crontab(settings.BAOSTOCK_DAILY_QUOTES_SYNC_CRON, timezone=settings.TIMEZONE),
            id="baostock_daily_quotes_sync",
            name="Daily K-line data synchronization (BaoStock)"
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_DAILY_QUOTES_SYNC_ENABLED):
            scheduler.pause_job("baostock_daily_quotes_sync")
            logger.info(f"⏸️ BaoStock Daily K-line synchronization has been added but suspended: {settings.BAOSTOCK_DAILY_QUOTES_SYNC_CRON}")
        else:
            logger.info(f"📈 BaoStock Daily K-line synchronization has been configured: {settings.BAOSTOCK_DAILY_QUOTES_SYNC_CRON} (Note: BaoStock does not support real-time quotes)")

        # Historical data synchronization task
        scheduler.add_job(
            run_baostock_historical_sync,
            CronTrigger.from_crontab(settings.BAOSTOCK_HISTORICAL_SYNC_CRON, timezone=settings.TIMEZONE),
            id="baostock_historical_sync",
            name="Historical data synchronization (BaoStock)"
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_HISTORICAL_SYNC_ENABLED):
            scheduler.pause_job("baostock_historical_sync")
            logger.info(f"⏸️ BaoStock Historical data sync added but paused: {settings.BAOSTOCK_HISTORICAL_SYNC_CRON}")
        else:
            logger.info(f"📊 BaoStock Historical data synchronization is configured: {settings.BAOSTOCK_HISTORICAL_SYNC_CRON}")

        # status check task
        scheduler.add_job(
            run_baostock_status_check,
            CronTrigger.from_crontab(settings.BAOSTOCK_STATUS_CHECK_CRON, timezone=settings.TIMEZONE),
            id="baostock_status_check",
            name="Data source status check (BaoStock)"
        )
        if not (settings.BAOSTOCK_UNIFIED_ENABLED and settings.BAOSTOCK_STATUS_CHECK_ENABLED):
            scheduler.pause_job("baostock_status_check")
            logger.info(f"⏸️ BaoStock Status check added but paused: {settings.BAOSTOCK_STATUS_CHECK_CRON}")
        else:
            logger.info(f"🔍 BaoStock Status check configured: {settings.BAOSTOCK_STATUS_CHECK_CRON}")

        # ETF Data synchronization task configuration
        logger.info("🔄 Configure ETF data synchronization task...")

        scheduler.add_job(
            run_etf_sync,
            CronTrigger.from_crontab(settings.ETF_SYNC_CRON, timezone=settings.TIMEZONE),
            id="etf_sync",
            name="ETF Data synchronization",
            kwargs={"force_update": False, "days": settings.ETF_SYNC_DAYS, "job_id": "etf_sync"}
        )
        if not settings.ETF_SYNC_ENABLED:
            scheduler.pause_job("etf_sync")
            logger.info(f"⏸️ ETF Data sync added but paused: {settings.ETF_SYNC_CRON}")
        else:
            logger.info(
                f"📅 ETF Data synchronization is configured: {settings.ETF_SYNC_CRON}, "
                f"The first full quantity will be filled, and subsequent increments will be synchronized according to the latest warehousing date;"
                f"The forced lookback window is {settings.ETF_SYNC_DAYS} day"
            )

        # Stock watch list A-share data synchronization task configuration
        logger.info("🔄 Configure stock watch list A-share data synchronization task...")
        
        scheduler.add_job(
            run_favorites_data_sync,
            CronTrigger.from_crontab(settings.FAVORITES_DATA_SYNC_CRON, timezone=settings.TIMEZONE),
            id="favorites_data_sync",
            name="Stock watch list A-share data synchronization (historical data+financial data)"
        )
        if not settings.FAVORITES_DATA_SYNC_ENABLED:
            scheduler.pause_job("favorites_data_sync")
            logger.info(f"⏸️ Stock watch list A-share data synchronization has been added but suspended: {settings.FAVORITES_DATA_SYNC_CRON}")
        else:
            logger.info(f"⭐ Stock watch list A-share data synchronization has been configured: {settings.FAVORITES_DATA_SYNC_CRON} (historical data+financial data)")

        # News data synchronization task configuration (use AKShare to synchronize all stock news)
        logger.info("🔄 Configure news data synchronization task...")

        from app.worker.akshare_sync_service import get_akshare_sync_service

        async def run_news_sync():
            """Run News Sync Task - Sync Stock Watchlist News using AKShare"""
            try:
                logger.info("📰 Start news data sync (AKShare - stock watchlist only)...")
                service = await get_akshare_sync_service()
                # 🔥 Set the correct job_id to ensure progress updates and status markers use the correct task ID
                service._current_job_id = "news_sync"
                result = await service.sync_news_data(
                    symbols=None,  # None + favorites_only=True Indicates that only the stock watch list is synchronized
                    max_news_per_stock=settings.NEWS_SYNC_MAX_PER_SOURCE,
                    favorites_only=True  # Sync stock watchlist only
                )
                logger.info(
                    f"✅ News synchronization completed: "
                    f"Process{result['total_processed']}Only stock watch list, "
                    f"success{result['success_count']}only, "
                    f"failed{result['error_count']}only, "
                    f"Total number of news{result['news_count']}Article, "
                    f"Time consuming{(datetime.utcnow() - result['start_time']).total_seconds():.2f}seconds"
                )
            except Exception as e:
                logger.error(f"❌ News sync failed: {e}", exc_info=True)

        # ==================== Hong Kong stock/U.S. stock data configuration ====================
        # Hong Kong stocks and US stocks are obtained on demand+Cache mode, no longer configure scheduled synchronization tasks
        logger.info("🇭🇰 Hong Kong stock data is obtained on demand+cache mode")
        logger.info("🇺🇸 U.S. stock data is obtained on demand+cache mode")

        scheduler.add_job(
            run_news_sync,
            CronTrigger.from_crontab(settings.NEWS_SYNC_CRON, timezone=settings.TIMEZONE),
            id="news_sync",
            name="News data synchronization (AKShare - stock watchlist only)"
        )
        if not settings.NEWS_SYNC_ENABLED:
            scheduler.pause_job("news_sync")
            logger.info(f"⏸️ News data sync added but paused: {settings.NEWS_SYNC_CRON}")
        else:
            logger.info(f"📰 News data sync configured (stock watchlist only): {settings.NEWS_SYNC_CRON}")

        # ==================== Stock watch list timing analysis configuration ====================
        from app.worker.watchlist_analysis_task import run_watchlist_analysis
        scheduler.add_job(
            run_watchlist_analysis,
            CronTrigger.from_crontab(settings.WATCHLIST_ANALYSIS_CRON, timezone=settings.TIMEZONE),
            id="watchlist_analysis",
            name="Stock watch list timing analysis"
        )
        if not settings.WATCHLIST_ANALYSIS_ENABLED:
            scheduler.pause_job("watchlist_analysis")
            logger.info(f"⏸️ Stock watchlist scheduled analysis added but paused: {settings.WATCHLIST_ANALYSIS_CRON}")
        else:
            logger.info(f"📊 Stock watch list scheduled analysis has been configured: {settings.WATCHLIST_ANALYSIS_CRON}")

        # ==================== Trading calendar cache refresh task ====================
        # daily 18:30 Refresh once: Tushare daily_basic data is usually released after the market closes (15:00) 
        # approx. 1~3 It was only stably put into storage within hours.18:30 Only then can the data of the day be obtained reliably.
        # Started by warm_up() After completing the initialization, this task is responsible for the update after the closing of the day.
        async def _refresh_trading_calendar():
            try:
                from app.services.trading_calendar_service import get_trading_calendar_service
                await get_trading_calendar_service().warm_up()
                logger.info("🗓️ [TradingCalendar] The trading calendar cache has been flushed (18:30 timing)")
            except Exception as _e:
                logger.warning(f"⚠️ [TradingCalendar] Scheduled refresh failed (does not affect operation): {_e}")

        scheduler.add_job(
            _refresh_trading_calendar,
            CronTrigger(hour=18, minute=30, timezone=settings.TIMEZONE),
            id="trading_calendar_refresh",
            name="Trading calendar cache refresh (daily 18:30) "
        )
        logger.info("🗓️ The transaction calendar cache refresh task is configured (daily 18:30 execution)")

        # v3.5.0 Item 4 / v3.6.0 Item 6: HITL pending confirmation operation expiration cleanup (performed every 30 minutes)
        async def _expire_stale_hitl_operations():
            try:
                from app.core.database import get_mongo_db
                from core.hitl.checkpoint_store import HITLCheckpointService
                db = get_mongo_db()
                if db is not None:
                    svc = HITLCheckpointService(db)
                    cleaned = await svc.expire_stale()
                    if cleaned:
                        logger.info(f"[HITL·Timing] Cleaned {cleaned} Waiting for confirmation operation")
            except Exception as _e:
                logger.warning(f"[HITL·Timing] Expired cleanup failed: {_e}")

        scheduler.add_job(
            _expire_stale_hitl_operations,
            IntervalTrigger(minutes=30, timezone=settings.TIMEZONE),
            id="hitl_expire_stale",
            name="HITL Pending operation expiration cleanup (every 30 minutes)"
        )
        logger.info("🔄 HITL Pending operation expiration cleanup configured (every 30 minutes)")

        # v3.6.0: Skill Audit expiration cleanup (performed every 30 minutes)
        async def _expire_stale_skill_reviews():
            try:
                from app.core.database import get_mongo_db
                from app.pro.services.skill_review_service import SkillReviewService
                db = get_mongo_db()
                if db is not None:
                    svc = SkillReviewService(db=db)
                    cleaned = await svc.expire_stale_reviews()
                    if cleaned:
                        logger.info(f"[SkillReview·Timing] Expired {cleaned} Skill records pending review")
            except Exception as _e:
                logger.warning(f"[SkillReview·Timing] Expired cleanup failed: {_e}")

        scheduler.add_job(
            _expire_stale_skill_reviews,
            IntervalTrigger(minutes=30, timezone=settings.TIMEZONE),
            id="skill_review_expire_stale",
            name="Skill Review expiration cleanup (every 30 minutes)"
        )
        logger.info("🔄 Skill Audit expiration cleanup configured (every 30 minutes)")

        scheduler.start()

        # Set up the scheduler instance into the service so that the API can manage tasks
        set_scheduler_instance(scheduler)
        logger.info("✅ Scheduler service initialized")
        
        # 🔥 Detect pending tasks caused by service restarts
        try:
            from app.services.scheduler_service import get_scheduler_service
            scheduler_service = get_scheduler_service()  # Synchronous function, not required await
            await scheduler_service.check_suspended_tasks_on_startup()
        except Exception as e:
            logger.warning(f"⚠️ Failed to detect pending tasks (does not affect startup): {e}")
    except Exception as e:
        logger.error(f"❌ Scheduler startup failed: {e}", exc_info=True)
        raise  # Throws an exception, preventing the application from starting

    try:
        yield
    finally:
        # Clean up on shutdown

        # 🔥 Turn off the unified thread pool synchronization service
        try:
            from app.worker.unified_thread_pool_sync_service import get_unified_thread_pool_sync_service
            unified_sync_service = await get_unified_thread_pool_sync_service()
            unified_sync_service.shutdown(timeout=30.0)
            logger.info("🛑 The unified thread pool synchronization service has stopped")
        except Exception as e:
            logger.warning(f"Unified thread pool synchronization service shutdown error: {e}")

        # 🔥 Stop the thread pool of the financial data synchronization service
        try:
            from app.worker.financial_data_sync_service import get_financial_sync_service
            financial_sync_service = await get_financial_sync_service()
            if financial_sync_service is not None:
                financial_sync_service.shutdown(timeout=30.0)
                logger.info("🛑 Financial data synchronization service thread pool has stopped")
        except Exception as e:
            logger.warning(f"Financial Data Sync Service Stop Error: {e}")

        # 🔥 Stop thread pool Worker
        try:
            from app.services.thread_worker import stop_thread_worker
            await stop_thread_worker()
            logger.info("🛑 Thread pool worker stopped")
        except Exception as e:
            logger.warning(f"Thread Pool Worker Stop Error: {e}")

        if scheduler:
            try:
                # Wait for the executing task to finish to avoid the database/event loop being closed while the job is still accessing the Motor.
                scheduler.shutdown(wait=True)
                logger.info("🛑 Scheduler stopped")
            except Exception as e:
                logger.warning(f"Scheduler shutdown error: {e}")

        try:
            stop_gain_alert_service.stop()
        except Exception as e:
            logger.warning(f"StopGainAlertService cleanup error: {e}")

        # Close UserService MongoDB connection
        try:
            from app.services.user_service import user_service
            user_service.close()
        except Exception as e:
            logger.warning(f"UserService cleanup error: {e}")

        await close_db()
        logger.info("TradingAgents FastAPI backend stopped")


# Create FastAPI application
app = FastAPI(
    title="TradingAgents-CN API",
    description="Stock Analysis and Batch Queuing System API",
    version=get_version(),
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
    redirect_slashes=False,
)

# security middleware
if not settings.DEBUG:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS
    )

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Session Middleware (Cookie authentication for web front-end)
# Note: Must be added after CORS middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.JWT_SECRET,  # use the same key
    session_cookie="tradingagents_session",  # Cookie Name
    max_age=3600,  # 1 hour expires
    same_site="lax",  # CSRF protect
    https_only=False if settings.DEBUG else True,  # Production environment use HTTPS
)

# Operation log middleware
app.add_middleware(OperationLogMiddleware)


# Request log middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    # Skip health checks and logging of static file requests
    if request.url.path in ["/health", "/favicon.ico"] or request.url.path.startswith("/static"):
        response = await call_next(request)
        return response

    # Use webapi logger to log requests
    logger = logging.getLogger("webapi")
    
    # For the license/status interface, record more detailed information
    if request.url.path == "/api/license/status":
        auth_header = request.headers.get("authorization", "None")
        # 🔥 Securely access the session (may not exist or SessionMiddleware is not installed)
        session_id = "None"
        try:
            if "session" in request.scope:
                session_id = request.session.get("user_id", "None")
        except (AssertionError, AttributeError, KeyError):
            session_id = "None"
        logger.info(f"🔄 {request.method} {request.url.path} - Start processing (Authorization: {auth_header[:20] if len(auth_header) > 20 else auth_header}..., Session: {session_id})")
    else:
        logger.info(f"🔄 {request.method} {request.url.path} - Start processing")

    response = await call_next(request)
    process_time = time.time() - start_time

    # Logging request completed
    status_emoji = "✅" if response.status_code < 400 else "❌"
    if request.url.path == "/api/license/status":
        logger.info(f"{status_emoji} {request.method} {request.url.path} - Status: {response.status_code} - Time consuming: {process_time:.3f}s (If it is 404, it may be that the route does not match or the authentication fails.)")
    else:
        logger.info(f"{status_emoji} {request.method} {request.url.path} - Status: {response.status_code} - Time consuming: {process_time:.3f}s")

    return response


# Global exception handling
# Request ID/Trace-ID middleware (needs to be the outermost layer, placed after functional middleware)
from app.middleware.request_id import RequestIDMiddleware
app.add_middleware(RequestIDMiddleware)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal server error occurred",
                "request_id": getattr(request.state, "request_id", None)
            }
        }
    )


# Test endpoint - verify that the middleware is working
@app.get("/api/test-log")
async def test_log():
    """Test whether the logging middleware is working"""
    print("🧪 The test endpoint is called - this message should appear in the console")
    return {"message": "Test successful", "timestamp": time.time()}


# =============================================================================
# Route registration
# v3.6.0 Community version open source separation (M1 convergence transformation): all route registration converges to app/router_registry.py,
# COMMUNITY_ROUTERS Separate from PRO_ROUTERS, the PRO_ROUTERS segment will be removed entirely when the community version is released.
# see docs/05-design/v3.0/v3.6.0-community-edition-separation-plan.md §7.1
# =============================================================================
register_routers(app)

logger = logging.getLogger("app.main")


@app.get("/api/system/info", tags=["system"])
async def get_system_info():
    """Get system version information"""
    version = get_version()
    build_info = get_build_info()

    # If BUILD_INFO exists, use the information in it
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

    # Otherwise, only the major version number is returned
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
    """Root path, return API information"""
    print("🏠 The root path is accessed")
    return {
        "name": "TradingAgents-CN API",
        "version": get_version(),
        "status": "running",
        "docs_url": "/docs" if settings.DEBUG else None
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
        reload_dirs=["app"] if settings.DEBUG else None,
        reload_excludes=[
            "__pycache__",
            "*.pyc",
            "*.pyo",
            "*.pyd",
            ".git",
            ".pytest_cache",
            "*.log",
            "*.tmp"
        ] if settings.DEBUG else None,
        reload_includes=["*.py"] if settings.DEBUG else None
    )
