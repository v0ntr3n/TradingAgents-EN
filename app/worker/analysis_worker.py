"""
Analyze task worker process
Consume analysis tasks in the queue and call TradingAgents for stock analysis
"""

import asyncio
import logging
import signal
import sys
import uuid
import traceback
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

# Add project root directory to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.services.queue_service import get_queue_service
from app.services.analysis_service import get_analysis_service
from app.core.database import init_database, close_database
from app.core.config import settings
from app.models.analysis import AnalysisTask, AnalysisParameters, AnalysisStatus
from app.services.config_provider import provider as config_provider
from app.services.queue import DEFAULT_USER_CONCURRENT_LIMIT, GLOBAL_CONCURRENT_LIMIT, VISIBILITY_TIMEOUT_SECONDS
from app.core.jdyun import is_jdyun_mode, get_jdyun_worker_max_concurrent, get_jdyun_stock_interval_seconds

logger = logging.getLogger(__name__)


async def jit_sync_stock_data(stock_code: str, parameters_dict: Dict[str, Any]) -> Any:
    """JIT Data synchronization: Actively pull the latest market data before analysis and save it to MongoDB.

    This function is an independent function at the module level and can be called jointly by AnalysisWorker and ThreadWorker.
    Avoid code duplication and ensure that both worker paths can trigger JIT synchronization.

    Only returned if all API data sources failed (network exception/returned empty data) is_valid=False, 
    Even if the data is stale, analysis is allowed to continue (with warnings) as long as any data source succeeds.

    Args:
        stock_code: Stock code (e.g. "600519") 
        parameters_dict: Task parameter dictionary (need to include fields such as market_type)

    Returns:
        DataValidationResult
    """
    import pandas as pd
    from app.services.data_validation_service import DataValidationResult
    from tradingagents.utils.stock_utils import StockUtils, SecurityType

    if not stock_code:
        return DataValidationResult(
            is_valid=False,
            message="Stock symbol missing in task parameters",
            missing_data=["symbol"],
            details={"error": "Stock code missing"}
        )

    # Extract market type from parameter
    market_type = parameters_dict.get("market_type", "cn")
    market_type_map = {
        "A shares": "cn", "Hong Kong stocks": "hk", "US stocks": "us",
        "cn": "cn", "hk": "hk", "us": "us"
    }
    market_type = market_type_map.get(market_type, "cn")

    # ETF/FUND Use an independent data link and should not apply JIT hard verification of individual stock quotes
    sec_type = StockUtils.identify_security_type(stock_code)
    if parameters_dict.get("market_type") == "ETF" or sec_type == SecurityType.FUND:
        logger.info(f"ℹ️ {stock_code} Identified as ETF/FUND, skips JIT verification of stock quotes, and uses ETF dedicated data link")
        return DataValidationResult(
            is_valid=True,
            message="ETF/FUND Securities, skip stock quote JIT verification, use ETF dedicated data link",
            missing_data=[],
            details={
                "symbol": stock_code,
                "market_type": parameters_dict.get("market_type", market_type),
                "security_type": sec_type.value if hasattr(sec_type, "value") else str(sec_type),
                "skipped": True,
                "reason": "etf_specialized_data_path"
            }
        )

    # Currently we only actively pull A-shares (HK/US can be expanded later)
    if market_type != "cn":
        logger.info(f"ℹ️ The market type is {market_type}, Skip active data pull, use existing data")
        return DataValidationResult(
            is_valid=True,
            message=f"Non-A-share market ({market_type}) , Skip active data pull",
            missing_data=[],  # Skip checking, nothing missing
            details={"symbol": stock_code, "market_type": market_type, "skipped": True}
        )

    # Get the daily market prices for the last 60 calendar days (enough to cover the latest trading day)
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')

    # Get list of enabled data sources by priority (read from database configuration)
    # Note: The caller (_trigger_jit_sync_in_thread) will initialize a separate asynchronous MongoDB connection in a new thread
    from app.core.data_source_priority import get_enabled_data_sources_async
    all_sources = await get_enabled_data_sources_async("a_shares")

    # Keep only real API data sources (excluding local cache classes)
    api_sources = [s for s in all_sources if s not in ("local", "mongodb", "local_file")]
    if not api_sources:
        api_sources = ["tushare", "akshare", "baostock"]  # Default order

    logger.info(f"📡 Data preparation: Data sources will be tried in order of priority {api_sources}, get {stock_code} Latest Quotes ({start_date} → {end_date})")

    # Data source name → provider Get the mapping of the function
    def _get_provider(source_name: str):
        if source_name == "tushare":
            from tradingagents.dataflows.providers.china.tushare import get_tushare_provider
            return get_tushare_provider()
        elif source_name == "akshare":
            from tradingagents.dataflows.providers.china.akshare import get_akshare_provider
            return get_akshare_provider()
        elif source_name == "baostock":
            from tradingagents.dataflows.providers.china.baostock import get_baostock_provider
            return get_baostock_provider()
        return None

    from app.services.historical_data_service import HistoricalDataService
    from app.core.database import get_mongo_db

    # Get the real last trading day (from Redis cached trading calendar service)
    # If Redis is unavailable, fall back to the current day
    last_trade_date: Optional[str] = None
    try:
        from app.services.trading_calendar_service import get_trading_calendar_service
        last_trade_date = await get_trading_calendar_service().get_last_trade_date()
        logger.info(f"📅 [JIT] Last trading day (from trading calendar cache): {last_trade_date}")
    except Exception as _cal_err:
        logger.warning(f"⚠️ [JIT] Unable to obtain transaction calendar, relaxed verification will be used (fallback to 3 working day rule): {_cal_err}")

    def _is_data_fresh(df: "pd.DataFrame") -> tuple:
        """Checks whether the DataFrame s latest trade_date covers the most recent trading day.
        Returns: (is_fresh: bool, latest_date_str: str)
        - If last_trade_date (Redis cache) can be obtained: accurate comparison, data >= Only the most recent trading day is considered fresh
        - Otherwise, it will fall back to the relaxed rule of tolerating up to 3 natural working days behind 
        """
        try:
            date_col = None
            for col in ("trade_date", "date", "Date"):
                if col in df.columns:
                    date_col = col
                    break
            if date_col is None:
                return True, "unknown"  # Date column not found, let go

            latest_raw = df[date_col].max()
            if pd.isna(latest_raw):
                return True, "unknown"

            latest_dt = pd.to_datetime(str(latest_raw)).date()
            latest_str = latest_dt.strftime('%Y-%m-%d')

            # Accurate judgment: whether the data has covered the most recent trading day
            if last_trade_date:
                from datetime import date as date_type
                last_td = pd.to_datetime(last_trade_date).date()
                is_fresh = latest_dt >= last_td
                if not is_fresh:
                    logger.debug(
                        f"[JIT] Data obsolescence judgment (accurate): latest date of data={latest_str}, Last trading day={last_trade_date}"
                    )
                return is_fresh, latest_str

            # Fallback: Simple natural working day count (does not take into account holidays)
            MAX_STALE_DAYS = 3
            today = datetime.now().date()
            missed = 0
            cur = latest_dt
            while cur < today:
                if cur.weekday() < 5:
                    missed += 1
                cur += timedelta(days=1)
            return missed <= MAX_STALE_DAYS, latest_str

        except Exception:
            return True, "unknown"  # Release when the check fails and does not affect the main process

    # Record the results of each data source so that when all are stale, the latest one can be selected
    best_result: dict = {}   # {"source": ..., "saved_count": ..., "latest_date": ...}
    last_error: str = ""

    for source_name in api_sources:
        try:
            provider = _get_provider(source_name)
            if provider is None:
                logger.warning(f"⚠️ data source {source_name} Not available (provider not found), skipped")
                continue

            hist_data = await provider.get_historical_data(stock_code, start_date, end_date, "daily")

            if hist_data is not None and not hist_data.empty:
                is_fresh, latest_date_str = _is_data_fresh(hist_data)

                # Save to MongoDB (no matter whether it is fresh or not, persist it first to avoid data loss)
                db = get_mongo_db()
                hist_service = HistoricalDataService()
                hist_service.db = db
                hist_service.collection = db.stock_daily_quotes
                await hist_service._ensure_indexes()

                saved_count = await hist_service.save_historical_data(
                    symbol=stock_code,
                    data=hist_data,
                    data_source=source_name,
                    market="CN",
                    period="daily"
                )

                if is_fresh:
                    logger.info(
                        f"✅ Data preparation is complete:{stock_code} Already from {source_name} sync {saved_count} Latest daily quotes"
                        f" (latest date: {latest_date_str}) "
                    )
                    return DataValidationResult(
                        is_valid=True,
                        message=f"Data preparation was successful and has been obtained from {source_name} sync {saved_count} Latest quotes (latest date: {latest_date_str}) ",
                        missing_data=[],  # The data is complete and no missing items
                        details={"symbol": stock_code, "fetched_records": saved_count, "source": source_name, "latest_date": latest_date_str}
                    )
                else:
                    logger.warning(
                        f"⚠️ Data preparation:{source_name} The returned data is stale (latest date: {latest_date_str}) , "
                        f"Saved but continue trying next data source"
                    )
                    # Record the best candidate (as of latest date)
                    if not best_result or latest_date_str > best_result.get("latest_date", ""):
                        best_result = {
                            "source": source_name,
                            "saved_count": saved_count,
                            "latest_date": latest_date_str
                        }
                    last_error = f"{source_name} Data is stale (latest: {latest_date_str}) "
            else:
                last_error = f"{source_name} Return empty data"
                logger.warning(f"⚠️ Data preparation:{source_name} Not returned {stock_code} For market data, try the next data source")

        except Exception as e:
            last_error = f"{source_name} Exception:{e}"
            logger.warning(f"⚠️ Data preparation:{source_name} get {stock_code} failed ({e}) , Try next data source")

    # All data sources have been tried. If at least one source returns (stale) data, pass the analysis but log a warning
    if best_result:
        logger.warning(
            f"⚠️ Data preparation: All data sources return stale data, use the latest available data"
            f" (Source: {best_result['source']}, latest date: {best_result['latest_date']}) "
        )
        return DataValidationResult(
            is_valid=True,
            message=(
                f"Data preparation complete (data may be stale): latest available data from {best_result['source']}, "
                f"latest date {best_result['latest_date']}, has exceeded {MAX_STALE_DAYS} working days"
            ),
            missing_data=[],  # There is data, but it may be out of date
            details={"symbol": stock_code, "best_source": best_result["source"],
                     "latest_date": best_result["latest_date"], "data_stale": True}
        )

    # All data sources failed
    logger.error(f"❌ Data preparation failed: all data sources {api_sources} None can be obtained {stock_code} The market data, the final error:{last_error}")
    return DataValidationResult(
        is_valid=False,
        message=(
            f"All data sources ({', '.join(api_sources)}) None returned {stock_code} market data,"
            f"Unable to perform analysis. Please check the network connection or data source configuration. Final error:{last_error}"
        ),
        missing_data=["historical_quotes"],
        details={"symbol": stock_code, "tried_sources": api_sources, "last_error": last_error}
    )


# 🔥 Import status update function (for exit log)
def _update_worker_state(**kwargs):
    """Update Worker state (safe call, will not fail)"""
    try:
        from app.worker.__main__ import update_worker_state
        update_worker_state(**kwargs)
    except Exception:
        pass  # Ignore import or call errors


class AnalysisWorker:
    """Analysis task Worker class"""

    def __init__(self, worker_id: Optional[str] = None):
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.queue_service = None
        self.running = False
        self.current_task = None
        
        # 🔥 Concurrency control: Use Semaphore to limit the number of tasks executed simultaneously
        self.max_concurrent_tasks = 3  # The default number of concurrency will be in start() Read from configuration in
        self.semaphore = None  # in start() Medium initialization
        self.running_tasks = set()  # Track running tasks

        # Configuration parameters (can be overridden by system settings)
        self.heartbeat_interval = int(getattr(settings, 'WORKER_HEARTBEAT_INTERVAL', 30))
        self.max_retries = int(getattr(settings, 'QUEUE_MAX_RETRIES', 3))
        self.poll_interval = float(getattr(settings, 'QUEUE_POLL_INTERVAL_SECONDS', 1))  # Queue polling interval (seconds)
        self.cleanup_interval = float(getattr(settings, 'QUEUE_CLEANUP_INTERVAL_SECONDS', 60))

        # Close flag (to prevent repeated printing)
        self._shutdown_initiated = False

        # Register signal handler
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Signal processor, graceful shutdown"""
        if self._shutdown_initiated:
            # Has started to shut down, force quit
            logger.warning("⚠️ force quit Worker...")
            sys.exit(1)

        logger.info(f"signal received {signum}, ready to close Worker...")
        self._shutdown_initiated = True
        self.running = False

        # Cancel all running tasks
        for task in self.running_tasks:
            if not task.done():
                task.cancel()

    async def start(self):
        """start Worker"""
        try:
            logger.info(f"🚀 Start analysis Worker: {self.worker_id}")

            # Initialize database connection (Redis life cycle has been managed by the database layer)
            await init_database()
            
            # 🔥 Configuration bridging: Write unified configuration into environment variables for use by TradingAgents core library
            # This must be performed before other initialization, because subsequent LLM, data sources, etc. will need to read configuration from environment variables
            try:
                from app.core.config_bridge import bridge_config_to_env
                bridge_config_to_env()
                logger.info("✅ Configuring the bridge is complete")
            except Exception as e:
                logger.warning(f"⚠️ Failed to configure bridge: {e}")
                logger.warning("⚠️ TradingAgents Will use the configuration in the .env file")
            
            # 🔥 Initialize the Agent registry (importing the adapters module will trigger automatic registration)
            try:
                logger.info("🔄 Start loading the Agent adapter module...")
                import core.agents.adapters  # This will trigger automatic registration of all Agents
                from core.agents.registry import get_registry
                registry = get_registry()
                agent_count = len(registry.list_all())
                logger.info(f"✅ Agent The registry has been initialized, total {agent_count} a Agent")
            except Exception as e:
                logger.error(f"❌ Agent Registry initialization failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Does not prevent workers from starting, but logs errors
            
            # 🔥 Initialize the tool registry (must be initialized before executing the task to ensure that the tool is available)
            try:
                # 1. Explicitly import the tool implementation module to trigger @register_tool Decorator
                logger.info("🔄 Start loading tool implementation module...")
                try:
                    # Import the __init__.py of the tool implementation module, which will trigger automatic registration of all tools
                    import core.tools.implementations
                    logger.info("✅ Tool implementation module has been imported")
                except Exception as e:
                    logger.warning(f"⚠️ Import tool implementation module failed: {e}")
                
                # 2. Create a ToolRegistry instance (all tool modules will be loaded automatically)
                from core.tools.registry import ToolRegistry
                registry = ToolRegistry()
                tool_count = len(registry.list_all())
                logger.info(f"✅ The tool registry has been initialized with a total of {tool_count} tools")
                
                # 3. Verify that key tools are loaded
                critical_tools = [
                    "get_stock_market_data_unified",
                    "get_stock_fundamentals_unified",
                    "get_stock_news_unified",
                    "get_stock_sentiment_unified",
                    "get_index_data",
                    "get_market_breadth",
                    "get_market_environment",
                    "identify_market_cycle",
                    "get_sector_data",
                    "get_fund_flow_data",
                    "get_peer_comparison",
                ]
                missing_tools = []
                for tool_id in critical_tools:
                    has_metadata = registry.has_tool(tool_id)
                    has_function = registry.get_function(tool_id) is not None
                    if not has_metadata:
                        missing_tools.append(f"{tool_id} (No metadata)")
                    elif not has_function:
                        missing_tools.append(f"{tool_id} (No function implementation)")
                
                if missing_tools:
                    logger.warning(f"⚠️ The following key tools are not loading correctly: {missing_tools}")
                    # Try loading these tools manually
                    from core.tools.loader import get_tool_loader
                    loader = get_tool_loader()
                    for tool_info in missing_tools:
                        tool_id = tool_info.split(" ")[0]  # Extraction tool ID
                        logger.info(f"🔄 Try reloading the tool: {tool_id}")
                        loader.load_tool(tool_id)
                    
                    # revalidate
                    still_missing = []
                    for tool_id in critical_tools:
                        if not registry.has_tool(tool_id) or registry.get_function(tool_id) is None:
                            still_missing.append(tool_id)
                    if still_missing:
                        logger.error(f"❌ The following tools are still missing after reloading: {still_missing}")
                    else:
                        logger.info("✅ All critical tools have been successfully reloaded")
                else:
                    logger.info("✅ All key tools have been loaded correctly")
            except Exception as e:
                logger.error(f"❌ Tool registry initialization failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Does not prevent workers from starting, but logs errors
            
            # 🔥 Initialize custom tools (load user-defined tools from the database)
            try:
                from app.core.database import get_mongo_db
                from core.tools.custom_tool import CustomToolDefinition, register_custom_tool
                
                db = get_mongo_db()
                cursor = db.custom_tools.find()
                custom_tool_count = 0
                async for doc in cursor:
                    try:
                        # Remove _id field to conform to Pydantic model
                        if "_id" in doc:
                            del doc["_id"]
                        definition = CustomToolDefinition(**doc)
                        await register_custom_tool(definition)
                        custom_tool_count += 1
                        logger.info(f"✅ Load custom tools: {definition.id}")
                    except Exception as e:
                        logger.error(f"❌ Failed to load custom tool {doc.get('id')}: {e}")
                
                if custom_tool_count > 0:
                    logger.info(f"✅ Custom tool initialization completed and loaded in total {custom_tool_count} tools")
                else:
                    logger.info("✅ Custom tool initialization completed (no custom tool)")
            except Exception as e:
                logger.warning(f"⚠️ Custom tool initialization failed: {e}")
                # Does not prevent workers from starting, but logs warnings

            # 🔥 Initialize Skills (load enabled executable Skills from database)
            try:
                from core.skills.models import SkillMetadata
                from core.skills.executor import SkillExecutor
                from core.tools.registry import get_tool_registry

                skill_registry = get_tool_registry()
                cursor = db.skills.find({"enabled": True})
                skill_count = 0
                async for doc in cursor:
                    try:
                        impl = doc.get("implementation")
                        params = doc.get("parameters", [])
                        if not impl or not params:
                            continue  # Skip knowledge-based Skills (no execution implementation)

                        if "_id" in doc:
                            del doc["_id"]
                        skill = SkillMetadata(**doc)
                        wrapper = SkillExecutor.create_sync_wrapper(skill)
                        tool_id = skill.name.replace("-", "_")
                        skill_registry.register_function(
                            tool_id=tool_id,
                            func=wrapper,
                            name=skill.description[:50],
                            category=skill.category,
                            description=skill.description,
                            is_online=True,
                            override=True,
                        )
                        skill_count += 1
                        logger.info(f"✅ Load Skill: {skill.name} (tool_id={tool_id})")
                    except Exception as e:
                        logger.error(f"❌ Failed to load skill {doc.get('name')}: {e}")

                if skill_count > 0:
                    logger.info(f"✅ Skills Initialization completed, total loading {skill_count} executable Skill")
                else:
                    logger.info("✅ Skills Initialization completed (no executable Skill)")
            except Exception as e:
                logger.warning(f"⚠️ Skills Initialization failed: {e}")
                # Does not prevent workers from starting, but logs warnings

            # 🔥 Initialize the workflow registry (must be initialized before executing the task)
            from app.services.workflow_registry import initialize_builtin_workflows
            initialize_builtin_workflows()
            logger.info("✅ Workflow registry initialized")

            # Read system settings (ENV first → DB) 
            try:
                effective_settings = await config_provider.get_effective_system_settings()
                
                # 🔥 Apply dynamic log level settings (consistent with API processes)
                try:
                    desired_level = str(effective_settings.get("log_level", "INFO")).upper()
                    logging.getLogger().setLevel(desired_level)
                    # Set the level of critical loggers
                    for name in ("worker", "webapi", "core", "tradingagents"):
                        logging.getLogger(name).setLevel(desired_level)
                    logger.info(f"✅ The log level has been set to: {desired_level}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to set log level: {e}")
            except Exception:
                effective_settings = {}

            # Get queue service
            self.queue_service = get_queue_service()

            self.running = True

            # Apply queue concurrency/timeout configuration + Worker/Polling parameters
            try:
                # 🔥 Worker Concurrency number configuration (read from system settings, default 3)
                self.max_concurrent_tasks = int(effective_settings.get("worker_max_concurrent_tasks", 3))
                # 🔧 JD Cloud Mode: Reduce the number of worker concurrencies and avoid LLM speed limit (429)
                if is_jdyun_mode():
                    jdyun_max = get_jdyun_worker_max_concurrent()
                    if self.max_concurrent_tasks > jdyun_max:
                        logger.info(f"🔧 [Jingdong cloud model] Worker Number of concurrencies {self.max_concurrent_tasks} → {jdyun_max} (avoid LLM rate limiting)")
                        self.max_concurrent_tasks = jdyun_max
                # initialization Semaphore
                self.semaphore = asyncio.Semaphore(self.max_concurrent_tasks)
                logger.info(f"🔧 Worker The number of concurrency is set to: {self.max_concurrent_tasks}")

                self.queue_service.user_concurrent_limit = int(effective_settings.get("max_concurrent_tasks", DEFAULT_USER_CONCURRENT_LIMIT))
                self.queue_service.global_concurrent_limit = int(effective_settings.get("max_concurrent_tasks", GLOBAL_CONCURRENT_LIMIT))
                # 🔧 JD Cloud Mode: Reduce user/global concurrency limits and avoid LLM speed limits (429)
                if is_jdyun_mode():
                    jdyun_max = get_jdyun_worker_max_concurrent()
                    if self.queue_service.user_concurrent_limit > jdyun_max:
                        logger.info(f"🔧 [Jingdong cloud model] User concurrency limit {self.queue_service.user_concurrent_limit} → {jdyun_max}")
                        self.queue_service.user_concurrent_limit = jdyun_max
                    if self.queue_service.global_concurrent_limit > jdyun_max:
                        logger.info(f"🔧 [Jingdong cloud model] Global concurrency limit {self.queue_service.global_concurrent_limit} → {jdyun_max}")
                        self.queue_service.global_concurrent_limit = jdyun_max
                self.queue_service.visibility_timeout = int(effective_settings.get("default_analysis_timeout", VISIBILITY_TIMEOUT_SECONDS))
                # Worker intervals
                self.heartbeat_interval = int(effective_settings.get("worker_heartbeat_interval_seconds", self.heartbeat_interval))
                self.poll_interval = float(effective_settings.get("queue_poll_interval_seconds", self.poll_interval))
                self.cleanup_interval = float(effective_settings.get("queue_cleanup_interval_seconds", self.cleanup_interval))
            except Exception:
                # If configuration reading fails, use default values
                self.max_concurrent_tasks = 3
                # 🔧 JD Cloud Model: Concurrency reduction logic is also applied under abnormal circumstances
                if is_jdyun_mode():
                    jdyun_max = get_jdyun_worker_max_concurrent()
                    if self.max_concurrent_tasks > jdyun_max:
                        logger.info(f"🔧 [Jingdong cloud model] Abnormal recovery Worker concurrency number {self.max_concurrent_tasks} → {jdyun_max}")
                        self.max_concurrent_tasks = jdyun_max
                self.semaphore = asyncio.Semaphore(self.max_concurrent_tasks)
                logger.warning(f"⚠️ Use the default worker concurrency number: {self.max_concurrent_tasks}")
            # 🔥 Worker Resume stuck tasks on startup (after process restart)
            await self._recover_stuck_tasks()
            
            # Start heartbeat task
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # Start a cleanup task
            cleanup_task = asyncio.create_task(self._cleanup_loop())

            # Main working cycle
            await self._work_loop()

            # Cancel background task
            heartbeat_task.cancel()
            cleanup_task.cancel()

            try:
                await heartbeat_task
                await cleanup_task
            except asyncio.CancelledError:
                pass

        except Exception as e:
            # 🔥 Record detailed startup failure information and re-throw the exception
            logger.error(f"❌ Worker Startup failed: {e}")
            logger.error(traceback.format_exc())
            self.running = False
            # 🔥 Rethrow the exception to let the caller know that the startup failed
            raise
        finally:
            await self._cleanup()

    async def _work_loop(self):
        """Main work loop - supports concurrent execution of multiple tasks"""
        logger.info(f"✅ Worker {self.worker_id} start working (Maximum number of concurrencies: {self.max_concurrent_tasks})")

        while self.running:
            try:
                # 🔥 Check the current number of concurrencies. If the upper limit is not reached, continue to obtain tasks.
                current_concurrent = len(self.running_tasks)
                if current_concurrent < self.max_concurrent_tasks:
                    # Get tasks from queue
                    task_data = await self.queue_service.dequeue_task(self.worker_id)

                    if task_data:
                        # 🔥 Use create_task to execute tasks concurrently without blocking the main loop
                        task_coro = self._process_task_with_semaphore(task_data)
                        task = asyncio.create_task(task_coro)
                        self.running_tasks.add(task)

                        # 🔥 Add an exception callback to ensure that the task can be removed from the collection when there is an exception
                        def remove_task(task_future):
                            """Removed from the collection when task is completed or abnormal"""
                            try:
                                self.running_tasks.discard(task_future)
                                # If there is an exception in the task, logs will be recorded but the Worker process will not be affected.
                                if task_future.exception():
                                    logger.error(f"❌ Task execution exception: {task_future.exception()}")
                            except Exception as e:
                                logger.error(f"❌ Error while removing task: {e}")

                        task.add_done_callback(remove_task)

                        logger.debug(f"📊 Current number of concurrent tasks: {len(self.running_tasks)}/{self.max_concurrent_tasks}")
                    else:
                        # No tasks, short sleep
                        await asyncio.sleep(self.poll_interval)
                else:
                    # The concurrency limit has been reached, please wait for a while and check again.
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                # Upon receiving the cancellation signal, exit the loop immediately
                logger.info("🛑 Work cycle receives cancellation signal")
                break

            except Exception as e:
                # 🔥 Work loop exceptions should not cause the Worker process to exit
                logger.error(f"❌ Abnormal work cycle: {e}")
                logger.error(traceback.format_exc())
                logger.info("🔄 Worker Will continue to run, waiting for the next cycle...")
                await asyncio.sleep(5)  # After an exception, wait 5 seconds before continuing.

        # 🔥 Wait for all running tasks to complete
        if self.running_tasks:
            logger.info(f"⏳ wait {len(self.running_tasks)} tasks completed...")
            await asyncio.gather(*self.running_tasks, return_exceptions=True)

        logger.info(f"🔄 Worker {self.worker_id} End of work cycle")

    async def _process_task_with_semaphore(self, task_data: Dict[str, Any]):
        """Task processing wrapper to control concurrency using Semaphore"""
        task_id = task_data.get("id", "unknown")
        try:
            async with self.semaphore:  # 🔥 Concurrency control: Up to max_concurrent_tasks tasks can be executed simultaneously
                await self._process_task(task_data)
                # 🔧 Jingdong Cloud Mode: Add intervals after task completion to avoid continuous intensive LLM calls triggering rate limits (429)
                if is_jdyun_mode():
                    interval = get_jdyun_stock_interval_seconds()
                    if interval > 0:
                        logger.info(f"⏳ [Jingdong cloud model] Task {task_id} done, waiting {interval}s Then continue to the next task (avoiding LLM speed limit)")
                        await asyncio.sleep(interval)
        except Exception as e:
            # 🔥 Ensure that task-level exceptions do not cause the Worker process to crash
            logger.error(f"❌ Task handling wrapper catches exception: {task_id} - {e}")
            logger.error(traceback.format_exc())

            # 🔥 Update Worker status: Task exception
            try:
                from app.worker.__main__ import get_worker_state
                state = get_worker_state()
                _update_worker_state(
                    error_count=state.get("error_count", 0) + 1,
                    last_error=f"wrapper exception {task_id}: {str(e)[:200]}",
                    status="error_recovered"
                )
            except Exception:
                pass
            
            # Attempt to update task status to failed
            try:
                from app.services.queue_service import get_queue_service
                queue_service = get_queue_service()
                await queue_service.ack_task(task_id, success=False)
            except Exception as ack_error:
                logger.error(f"❌ Error confirming failed task: {task_id} - {ack_error}")
            
            # If it is a v2 engine task, try to update the task status
            try:
                parameters_dict = task_data.get("parameters", {})
                if isinstance(parameters_dict, str):
                    import json
                    parameters_dict = json.loads(parameters_dict)
                
                engine_type = parameters_dict.get("engine", "legacy")
                if engine_type == "v2":
                    from app.services.task_analysis_service import get_task_analysis_service
                    from app.models.analysis import AnalysisStatus
                    from app.utils.timezone import now_tz
                    
                    task_service = get_task_analysis_service()
                    task = await task_service.get_task(task_id)
                    if task:
                        task.status = AnalysisStatus.FAILED
                        task.error_message = f"Task processing exception: {str(e)}"
                        task.completed_at = now_tz()
                        await task_service._update_task(task)
            except Exception as update_error:
                logger.error(f"❌ An error occurred while updating task status: {task_id} - {update_error}")
            
            # The exception has been handled and will not be rethrown, ensuring that the Worker process continues to run.
    
    async def _process_task(self, task_data: Dict[str, Any]):
        """Work on a single task"""
        task_id = task_data.get("id")
        stock_code = task_data.get("symbol")
        user_id = task_data.get("user")

        logger.info(f"📊 Start working on a task: {task_id} - {stock_code} (Current concurrency: {len(self.running_tasks)}/{self.max_concurrent_tasks})")

        self.current_task = task_id
        success = False

        # 🔥 Update Worker status: Start processing tasks
        _update_worker_state(
            last_task_id=task_id,
            last_task_time=datetime.now().isoformat(),
            status=f"processing:{stock_code}"
        )

        try:
            # Parse task parameters
            parameters_dict = task_data.get("parameters", {})
            if isinstance(parameters_dict, str):
                import json
                parameters_dict = json.loads(parameters_dict)

            # Check engine type (default uses v2 engine)
            engine_type = parameters_dict.get("engine", "v2")

            task_service = None
            task = None

            # v2 The task advances the status before data preparation to avoid the front end staying in pending/initialization for a long time.
            if engine_type == "v2":
                from app.services.task_analysis_service import get_task_analysis_service
                from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
                from app.utils.timezone import now_tz

                task_service = get_task_analysis_service()
                task = await task_service.get_task(task_id)
                if not task:
                    raise ValueError(f"Task does not exist: {task_id}")

                memory_manager = get_memory_state_manager()
                memory_task = await memory_manager.get_task(task_id)
                if not memory_task:
                    logger.info(f"📝 [Worker] The task is not in memory, create the memory state first: {task_id}")
                    await memory_manager.create_task(
                        task_id=task_id,
                        user_id=user_id,
                        stock_code=stock_code,
                        parameters=parameters_dict,
                        stock_name=None
                    )
                    logger.info(f"✅ [Worker] The task has been created to the memory state manager: {task_id}")

                task.status = AnalysisStatus.PROCESSING
                if not task.started_at:
                    task.started_at = now_tz()
                task.progress = max(task.progress or 0, 1)
                task.current_step = "Data preparation"
                task.message = "Preparing data for analysis..."
                await task_service._update_task(task)

                await memory_manager.update_task_status(
                    task_id=task_id,
                    status=TaskStatus.RUNNING,
                    progress=task.progress,
                    message=task.message,
                    current_step="data_preparation",
                    current_step_name="Data preparation",
                    current_step_description=task.message
                )
            
            # Data verification: Check whether the stock data exists and is fresh (to prevent analysis of stale data)
            validation_result = await self._validate_task_data(stock_code, parameters_dict)
            if not validation_result.is_valid:
                error_message = validation_result.message
                logger.warning(f"⚠️ Task {task_id} Data verification failed: {error_message}")

                # Update task status is failed
                engine_type_check = parameters_dict.get("engine", "v2")
                if engine_type_check in ("v2", "unified"):
                    try:
                        from app.services.task_analysis_service import get_task_analysis_service
                        from app.utils.timezone import now_tz
                        task_service_tmp = get_task_analysis_service()
                        task_tmp = await task_service_tmp.get_task(task_id)
                        if task_tmp:
                            task_tmp.status = AnalysisStatus.FAILED
                            task_tmp.error_message = error_message
                            task_tmp.completed_at = now_tz()
                            await task_service_tmp._update_task(task_tmp)
                    except Exception as upd_err:
                        logger.error(f"❌ An error occurred when updating task status after data verification failed.: {upd_err}")

                # Throw an exception and let the upper layer handle it uniformly (logging, releasing current_task, etc.)
                raise ValueError(error_message)

            if engine_type == "v2":
                # v2 Engine: Use unified task service
                logger.info(f"🔧 [Worker] Use v2 engine to perform tasks: {task_id}")
                from app.services.memory_state_manager import get_memory_state_manager
                
                # 🔥 Key: Make sure the task exists in the memory state manager (Worker process and API process are separate)
                memory_manager = get_memory_state_manager()
                try:
                    # Try to get the task, create it if it doesn't exist
                    memory_task = await memory_manager.get_task(task_id)
                    if not memory_task:
                        logger.info(f"📝 [Worker] Task is not in memory, create memory state: {task_id}")
                        await memory_manager.create_task(
                            task_id=task_id,
                            user_id=user_id,
                            stock_code=stock_code,
                            parameters=parameters_dict,
                            stock_name=None
                        )
                        logger.info(f"✅ [Worker] The task has been created to the memory state manager: {task_id}")
                except Exception as e:
                    logger.warning(f"⚠️ [Worker] Check/create memory task failed: {e}, Continue execution")
                
                # perform tasks
                await task_service.execute_task(task, progress_callback=self._progress_callback)
                success = True
                logger.info(f"✅ [v2 engine] Mission accomplished: {task_id}")
                
            elif engine_type == "unified":
                # unified Engine: Using Unified Analytics Services
                logger.info(f"🔧 [Worker] Perform tasks using the unified engine: {task_id}")
                from app.services.unified_analysis_service import get_unified_analysis_service
                from app.models.analysis import SingleAnalysisRequest
                
                unified_service = get_unified_analysis_service()
                
                # build SingleAnalysisRequest
                single_req = SingleAnalysisRequest(
                    symbol=stock_code,
                    stock_code=stock_code,
                    parameters=AnalysisParameters(**parameters_dict) if parameters_dict else None
                )
                
                # Perform analysis
                await unified_service.execute_analysis_for_ab_test(
                    task_id=task_id,
                    user_id=user_id,
                    request=single_req
                )
                success = True
                logger.info(f"✅ [unified engine] Mission accomplished: {task_id}")
                
            else:
                # legacy Engine: Use old analysis service
                logger.info(f"🔧 [Worker] Use legacy engine to perform tasks: {task_id}")
                parameters = AnalysisParameters(**parameters_dict)

                task = AnalysisTask(
                    task_id=task_id,
                    user_id=user_id,
                    symbol=stock_code,  # Use symbol field (required)
                    stock_code=stock_code,  # Keep stock_code field (compatible)
                    batch_id=task_data.get("batch_id"),
                    parameters=parameters
                )

                # Perform analysis
                result = await get_analysis_service().execute_analysis_task(
                    task,
                    progress_callback=self._progress_callback
                )

                success = True
                logger.info(f"✅ [legacy engine] Mission accomplished: {task_id} - Time consuming: {result.execution_time:.2f}seconds")

        except Exception as e:
            logger.error(f"❌ Task execution failed: {task_id} - {e}")
            logger.error(traceback.format_exc())

            # 🔥 Update Worker status: Task failed
            try:
                from app.worker.__main__ import get_worker_state
                state = get_worker_state()
                _update_worker_state(
                    error_count=state.get("error_count", 0) + 1,
                    last_error=f"{task_id}: {str(e)[:200]}"
                )
            except Exception:
                pass

        finally:
            # Confirm task completion
            try:
                await self.queue_service.ack_task(task_id, success)
            except Exception as e:
                logger.error(f"Confirm task failed: {task_id} - {e}")

            # 🔥 Update Worker status: Task completed
            try:
                from app.worker.__main__ import get_worker_state
                state = get_worker_state()
                if success:
                    _update_worker_state(
                        task_count=state.get("task_count", 0) + 1,
                        status="idle"
                    )
                else:
                    _update_worker_state(status="idle")
            except Exception:
                pass

            self.current_task = None

    async def _validate_task_data(
        self,
        stock_code: str,
        parameters_dict: Dict[str, Any]
    ) -> 'DataValidationResult':
        """Data preparation phase: delegated to module-level jit_sync_stock_data function execution."""
        return await jit_sync_stock_data(stock_code, parameters_dict)
    
    def _progress_callback(self, progress: int, message: str, **kwargs):
        """Progress callback function
        
        Args:
            progress: progress percentage (0-100)
            message: progress message
            **kwargs: Additional parameters (such as step_name, etc.)
        """
        step_name = kwargs.get("step_name", "")
        if step_name:
            logger.debug(f"Task progress {self.current_task}: {progress}% - {step_name} - {message}")
        else:
            logger.debug(f"Task progress {self.current_task}: {progress}% - {message}")

    async def _heartbeat_loop(self):
        """heartbeat cycle"""
        while self.running:
            try:
                await self._send_heartbeat()
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Abnormal heartbeat: {e}")
                await asyncio.sleep(5)

    async def _send_heartbeat(self):
        """Send heartbeat"""
        try:
            from app.core.redis_client import get_redis_service
            redis_service = get_redis_service()

            heartbeat_data = {
                "worker_id": self.worker_id,
                "timestamp": datetime.utcnow().isoformat(),
                "current_task": self.current_task,
                "status": "active" if self.running else "stopping"
            }

            heartbeat_key = f"worker:{self.worker_id}:heartbeat"
            await redis_service.set_json(heartbeat_key, heartbeat_data, ttl=self.heartbeat_interval * 2)

        except Exception as e:
            logger.error(f"Failed to send heartbeat: {e}")

    async def _cleanup_loop(self):
        """Regularly clean up the cycle of expired tasks"""
        while self.running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                if self.queue_service:
                    await self.queue_service.cleanup_expired_tasks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Failed to clean up expired tasks: {e}")
                await asyncio.sleep(5)

    async def _recover_stuck_tasks(self):
        """Worker Handle unfinished tasks at startup (after process restart)

        New policy: Do not automatically resume tasks, but mark them as"hang"status, allowing the user to decide whether to continue

        Check two situations:
        1. Redis Queue marked as"processing"task
        2. The status in the database is"processing"or"pending"task
        """
        try:
            logger.info("🔍 Worker Startup: Check for unfinished tasks...")

            # 1. Clean up the processing tasks in the Redis queue (without requeuing)
            if self.queue_service:
                # Clear the processing collection
                processing_tasks = await self.queue_service.r.smembers("queue:processing")
                if processing_tasks:
                    logger.info(f"📋 discover {len(processing_tasks)} Redis processing tasks will be cleaned up...")
                    await self.queue_service.r.delete("queue:processing")

                    # Clear user processing count
                    user_keys = await self.queue_service.r.keys("queue:user:*:processing")
                    if user_keys:
                        await self.queue_service.r.delete(*user_keys)

            # 2. Check the database for outstanding tasks
            from app.core.database import get_mongo_db_sync
            from app.models.analysis import AnalysisStatus

            db = get_mongo_db_sync()
            collection = db["unified_analysis_tasks"]

            # Find all"processing"or"pending"status tasks
            unfinished_tasks = collection.find({
                "status": {"$in": [
                    AnalysisStatus.PROCESSING.value,
                    AnalysisStatus.PENDING.value
                ]}
            })

            suspended_count = 0
            user_notifications = {}  # User ID -> task list

            for task_doc in unfinished_tasks:
                task_id = task_doc.get("task_id")
                user_id = task_doc.get("user_id")
                symbol = task_doc.get("symbol", "unknown")

                if not task_id:
                    continue

                try:
                    # Mark as pending
                    logger.info(f"⏸️ Mark task as pending: {task_id} ({symbol})")
                    collection.update_one(
                        {"task_id": task_id},
                        {
                            "$set": {
                                "status": AnalysisStatus.SUSPENDED.value,
                                "error_message": "The service restarted and the task was suspended. Please resume or cancel the task manually.",
                                "suspended_at": datetime.utcnow()
                            }
                        }
                    )

                    # Remove from Redis queue (if exists)
                    if self.queue_service:
                        await self.queue_service.r.lrem("queue:ready", 0, task_id)
                        await self.queue_service.r.delete(f"queue:task:{task_id}")

                    suspended_count += 1

                    # Collect user notification information
                    if user_id:
                        if user_id not in user_notifications:
                            user_notifications[user_id] = []
                        user_notifications[user_id].append({
                            "task_id": task_id,
                            "symbol": symbol,
                            "created_at": task_doc.get("created_at")
                        })

                except Exception as e:
                    logger.error(f"Mark task as pending failed: {task_id} - {e}")

            # Send notification to user
            if user_notifications:
                await self._send_suspended_task_notifications(user_notifications)

            if suspended_count > 0:
                logger.warning(f"⏸️ Already {suspended_count} unfinished tasks marked as pending")
                logger.info(f"💡 Users can manually resume or cancel these tasks in the task list")
            else:
                logger.info("✅ No unfinished tasks found")

        except Exception as e:
            logger.error(f"Failed to process unfinished tasks: {e}")
            logger.error(traceback.format_exc())

    async def _send_suspended_task_notifications(self, user_notifications: Dict[str, List[Dict]]):
        """Send pending task notifications to users"""
        try:
            from app.core.database import get_mongo_db_sync

            db = get_mongo_db_sync()
            notifications_collection = db["notifications"]

            for user_id, tasks in user_notifications.items():
                task_count = len(tasks)
                task_list = "\n".join([
                    f"- {task['symbol']} (Task ID: {task['task_id'][:8]}...)"
                    for task in tasks[:5]  # Display up to 5
                ])

                if task_count > 5:
                    task_list += f"\n... Also {task_count - 5} tasks"

                notification = {
                    "user_id": user_id,
                    "type": "system",
                    "title": "Service restart notification",
                    "message": f"detected {task_count} Unfinished analysis tasks have been suspended:\n\n{task_list}\n\n Please review the task list and decide whether to continue the analysis.",
                    "level": "warning",
                    "read": False,
                    "created_at": datetime.utcnow(),
                    "data": {
                        "suspended_tasks": [task["task_id"] for task in tasks]
                    }
                }

                notifications_collection.insert_one(notification)
                logger.info(f"📧 Pending task notification sent to user: {user_id} ({task_count} tasks)")

        except Exception as e:
            logger.error(f"Failed to send pending task notification: {e}")

    async def _cleanup(self):
        """Clean up resources"""
        logger.info(f"🧹 Clean up worker resources: {self.worker_id}")

        # Wait for all running tasks to complete (up to 10 seconds)
        if self.running_tasks:
            logger.info(f"⏳ wait {len(self.running_tasks)} tasks completed...")
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.running_tasks, return_exceptions=True),
                    timeout=10.0
                )
                logger.info("✅ All tasks completed")
            except asyncio.TimeoutError:
                logger.warning("⚠️ Wait for the task to time out and force the remaining tasks to be cancelled.")
                for task in self.running_tasks:
                    if not task.done():
                        task.cancel()
            except Exception as e:
                logger.error(f"Error while waiting for task to complete: {e}")

        try:
            # Clear heartbeat records
            from app.core.redis_client import get_redis_service
            redis_service = get_redis_service()
            heartbeat_key = f"worker:{self.worker_id}:heartbeat"
            await redis_service.redis.delete(heartbeat_key)
        except Exception as e:
            logger.error(f"Failed to clear heartbeat records: {e}")

        try:
            # Close database connection
            await close_database()
        except Exception as e:
            logger.error(f"Failed to close database connection: {e}")


async def main():
    """main function"""
    # Setup log
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create and start Worker
    worker = AnalysisWorker()

    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("⏹️  Received interrupt signal, shutting down...")
    except Exception as e:
        # 🔥 Logging detailed exception information, including stack trace
        logger.error(f"❌ Worker Abnormal exit: {e}")
        logger.error(traceback.format_exc())
        # Make sure to clean up resources
        try:
            await worker._cleanup()
        except Exception as cleanup_error:
            logger.error(f"❌ Worker An error occurred while cleaning up resources: {cleanup_error}")
        sys.exit(1)
    finally:
        # Make sure workers clean up resources correctly
        try:
            await worker._cleanup()
        except Exception as cleanup_error:
            logger.error(f"❌ Worker An error occurred while cleaning up resources: {cleanup_error}")

    logger.info("✅ Worker Safely exited")


if __name__ == "__main__":
    asyncio.run(main())
