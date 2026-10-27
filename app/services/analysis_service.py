"""
Stock Analysis Services
Wrap existing TradingAgents analysis functions into API services
"""

import asyncio
import uuid
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
import sys

# Add project root directory to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Initialize TradingAgents log system
from tradingagents.utils.logging_init import init_logging
init_logging()

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from app.services.simple_analysis_service import create_analysis_config, get_provider_by_model_name
from app.models.analysis import (
    AnalysisParameters, AnalysisResult, AnalysisTask, AnalysisBatch,
    AnalysisStatus, BatchStatus, SingleAnalysisRequest, BatchAnalysisRequest
)
from app.models.user import PyObjectId
from bson import ObjectId
from app.core.database import get_mongo_db
from app.core.redis_client import get_redis_service, RedisKeys
from app.services.queue_service import QueueService
from app.core.database import get_redis_client
from app.services.redis_progress_tracker import RedisProgressTracker
from app.services.config_provider import provider as config_provider
from app.services.queue import DEFAULT_USER_CONCURRENT_LIMIT, GLOBAL_CONCURRENT_LIMIT, VISIBILITY_TIMEOUT_SECONDS
from app.services.usage_statistics_service import UsageStatisticsService
from app.models.config import UsageRecord

import logging
logger = logging.getLogger(__name__)


class AnalysisService:
    """股票分析服务类"""

    def __init__(self):
        # Get the Redis client
        redis_client = get_redis_client()
        self.queue_service = QueueService(redis_client)
        # Initialize usage statistics service
        self.usage_service = UsageStatisticsService()
        self._trading_graph_cache = {}
        # Progress tracker cache
        self._progress_trackers: Dict[str, RedisProgressTracker] = {}

    def _convert_user_id(self, user_id: str) -> PyObjectId:
        """Convert string user ID to PyObjectId"""
        try:
            logger.info(f"🔄 开始转换用户ID: {user_id} (类型: {type(user_id)})")

            # If you are an admin user, use a fixed ObjectId
            if user_id == "admin":
                # Use fixed ObjectId as admin user ID
                admin_object_id = ObjectId("507f1f77bcf86cd799439011")
                logger.info(f"🔄 Convert admin user ID: {user_id} -> {admin_object_id}")
                return PyObjectId(admin_object_id)
            else:
                # Try converting the string to ObjectId
                object_id = ObjectId(user_id)
                logger.info(f"🔄 转换用户ID: {user_id} -> {object_id}")
                return PyObjectId(object_id)
        except Exception as e:
            logger.error(f"❌ 用户ID转换失败: {user_id} -> {e}")
            # If the conversion fails, generate a new ObjectId
            new_object_id = ObjectId()
            logger.warning(f"⚠️ 生成新的用户ID: {new_object_id}")
            return PyObjectId(new_object_id)

    def _get_user_risk_preference(self, user_id: str) -> str:
        """Get the user s risk preference settings

        Args:
            user_id: User ID

        Returns:
            risk appetite: 'conservative'(conservative) / 'neutral'(Neutral) / 'aggressive'(Radical)
            Return by default 'neutral'
        """
        try:
            db = get_mongo_db()
            users_collection = db["users"]

            # Query user
            user = users_collection.find_one({"_id": ObjectId(user_id)})
            if user and "preferences" in user:
                risk_pref = user["preferences"].get("risk_preference", "neutral")
                logger.info(f"📊 获取用户 {user_id} 的风险偏好: {risk_pref}")
                return risk_pref

            logger.info(f"📊 用户 {user_id} 未设置风险偏好，使用默认值: neutral")
            return "neutral"
        except Exception as e:
            logger.warning(f"⚠️ Failed to obtain user risk preference: {e}, Use default value: neutral")
            return "neutral"
    
    def _get_trading_graph(self, config: Dict[str, Any]) -> TradingAgentsGraph:
        """Get or create a TradingAgents graph instance (with cache)— Deactivated

        v3.0 The old TradingAgentsGraph engine has been retired.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] AnalysisService._get_trading_graph deactivated,"
            "TradingAgentsGraph No longer instantiated."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        config_key = json.dumps(config, sort_keys=True)

        if config_key not in self._trading_graph_cache:
            # Use the complete configuration directly and no longer merge DEFAULT_CONFIG (because create_analysis_config has already been processed)
            # This is consistent with the way single strand analysis services and web directories
            self._trading_graph_cache[config_key] = TradingAgentsGraph(
                selected_analysts=config.get("selected_analysts", ["market", "fundamentals"]),
                debug=config.get("debug", False),
                config=config
            )

            logger.info(f"Create a new TradingAgents instance: {config.get('llm_provider', 'default')}")

        return self._trading_graph_cache[config_key]

    def _execute_analysis_sync_with_progress(self, task: AnalysisTask, progress_tracker: RedisProgressTracker) -> AnalysisResult:
        """Execute analysis tasks synchronously (run in thread pool, with progress tracking)— Deactivated

        v3.0 The legacy engine has been retired.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] AnalysisService._execute_analysis_sync_with_progress deactivated,"
            "task_id=%s The v2 engine should be used instead."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
            % getattr(task, "task_id", "<unknown>")
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        try:
            # Reinitialize the logging system in a thread
            from tradingagents.utils.logging_init import init_logging, get_logger
            init_logging()
            thread_logger = get_logger('analysis_thread')

            thread_logger.info(f"🔄 [thread pool] Start an analysis task: {task.task_id} - {task.symbol}")
            logger.info(f"🔄 [thread pool] Start an analysis task: {task.task_id} - {task.symbol}")

            # environmental inspection
            progress_tracker.update_progress("🔧 检查环境配置")

            # Create a complete configuration using standard configuration functions
            from app.core.unified_config import unified_config

            quick_model = getattr(task.parameters, 'quick_analysis_model', None) or unified_config.get_quick_analysis_model()
            deep_model = getattr(task.parameters, 'deep_analysis_model', None) or unified_config.get_deep_analysis_model()

            # 🔧 Read the model's complete configuration parameters from the MongoDB database (instead of from a JSON file)
            quick_model_config = None
            deep_model_config = None

            try:
                from pymongo import MongoClient
                from app.core.config import settings

                # Using the synchronous MongoDB client
                client = MongoClient(settings.MONGO_URI)
                db = client[settings.MONGO_DB]
                collection = db.system_configs

                # Query the latest active configuration
                doc = collection.find_one({"is_active": True}, sort=[("version", -1)])

                if doc and "llm_configs" in doc:
                    llm_configs = doc["llm_configs"]
                    logger.info(f"✅ 从 MongoDB 读取到 {len(llm_configs)} 个模型配置")

                    for llm_config in llm_configs:
                        if llm_config.get("model_name") == quick_model:
                            quick_model_config = {
                                "max_tokens": llm_config.get("max_tokens", 4000),
                                "temperature": llm_config.get("temperature", 0.7),
                                "timeout": llm_config.get("timeout", 180),
                                "retry_times": llm_config.get("retry_times", 3),
                                "api_base": llm_config.get("api_base")
                            }
                            if llm_config.get("reasoning_effort"):
                                quick_model_config["reasoning_effort"] = llm_config["reasoning_effort"]
                            logger.info(f"✅ 读取快速模型配置: {quick_model}")
                            logger.info(f"   max_tokens={quick_model_config['max_tokens']}, temperature={quick_model_config['temperature']}")
                            logger.info(f"   timeout={quick_model_config['timeout']}, retry_times={quick_model_config['retry_times']}")
                            logger.info(f"   api_base={quick_model_config['api_base']}")

                        if llm_config.get("model_name") == deep_model:
                            deep_model_config = {
                                "max_tokens": llm_config.get("max_tokens", 4000),
                                "temperature": llm_config.get("temperature", 0.7),
                                "timeout": llm_config.get("timeout", 180),
                                "retry_times": llm_config.get("retry_times", 3),
                                "api_base": llm_config.get("api_base")
                            }
                            if llm_config.get("reasoning_effort"):
                                deep_model_config["reasoning_effort"] = llm_config["reasoning_effort"]
                            logger.info(f"✅ 读取深度模型配置: {deep_model} - {deep_model_config}")
                else:
                    logger.warning("⚠️ MongoDB No system configuration found, default parameters will be used")
            except Exception as e:
                logger.warning(f"⚠️ Failed to read model configuration from MongoDB: {e}, Default parameters will be used")

            # cost estimate
            progress_tracker.update_progress("💰 预估分析成本")

            # Dynamically find suppliers based on model name (synchronized versions)
            llm_provider = "dashscope"  # Used by default dashscope

            # Parameter configuration
            progress_tracker.update_progress("⚙️ 配置分析参数")

            # Create a complete configuration using standard configuration functions
            from app.services.simple_analysis_service import create_analysis_config
            config = create_analysis_config(
                research_depth=task.parameters.research_depth,
                selected_analysts=task.parameters.selected_analysts or ["market", "fundamentals"],
                quick_model=quick_model,
                deep_model=deep_model,
                llm_provider=llm_provider,
                market_type=getattr(task.parameters, 'market_type', "A股"),
                quick_model_config=quick_model_config,  # Pass model configuration
                deep_model_config=deep_model_config     # Pass model configuration
            )

            # Start the engine
            progress_tracker.update_progress("🚀 初始化AI分析引擎")

            # Get TradingAgents instance
            trading_graph = self._get_trading_graph(config)

            # Perform analysis
            from datetime import timezone
            start_time = datetime.now(timezone.utc)
            analysis_date = task.parameters.analysis_date or datetime.now().strftime("%Y-%m-%d")

            # Create a progress callback function
            def progress_callback(message: str):
                progress_tracker.update_progress(message)

            # Call existing analysis methods (synchronous calls, passing progress callbacks)
            from tradingagents.agents.utils.agent_context import AgentContext
            # Obtain user risk preference and inject it into AgentContext
            risk_preference = self._get_user_risk_preference(str(task.user_id))
            ctx = AgentContext(user_id=str(task.user_id), preference_id=risk_preference)
            logger.info(f"[diagnose] inject AgentContext task_id={task.task_id} user_id={task.user_id} symbol={task.symbol} date={analysis_date} risk_preference={risk_preference}")
            _, decision = trading_graph.propagate(task.symbol, analysis_date, progress_callback, task_id=task.task_id, agent_context=ctx.__dict__)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Generate report
            progress_tracker.update_progress("📊 生成研究报告")

            # Extract model information from decisions
            model_info = decision.get('model_info', 'Unknown') if isinstance(decision, dict) else 'Unknown'

            # Build results
            result = AnalysisResult(
                analysis_id=str(uuid.uuid4()),
                summary=decision.get("summary", ""),
                recommendation=decision.get("recommendation", ""),
                confidence_score=decision.get("confidence_score", 0.0),
                risk_level=decision.get("risk_level", "中等"),
                key_points=decision.get("key_points", []),
                detailed_analysis=decision,
                execution_time=execution_time,
                tokens_used=decision.get("tokens_used", 0),
                model_info=model_info  # 🔥 Add model information fields
            )

            logger.info(f"✅ [线程池] 分析任务完成: {task.task_id} - 耗时{execution_time:.2f}秒")
            return result

        except Exception as e:
            logger.error(f"❌ [thread pool] Failed to execute analysis task: {task.task_id} - {e}")
            raise

    def _execute_analysis_sync(self, task: AnalysisTask) -> AnalysisResult:
        """Execute analysis tasks synchronously (running in a thread pool)— Deactivated

        v3.0 The legacy engine has been retired.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] AnalysisService._execute_analysis_sync deactivated,"
            "task_id=%s The v2 engine should be used instead."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
            % getattr(task, "task_id", "<unknown>")
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        try:
            logger.info(f"🔄 [thread pool] Start an analysis task: {task.task_id} - {task.symbol}")

            # Create a complete configuration using standard configuration functions
            from app.core.unified_config import unified_config

            quick_model = getattr(task.parameters, 'quick_analysis_model', None) or unified_config.get_quick_analysis_model()
            deep_model = getattr(task.parameters, 'deep_analysis_model', None) or unified_config.get_deep_analysis_model()

            # 🔧 Read the model's complete configuration parameters from the MongoDB database (instead of from a JSON file)
            quick_model_config = None
            deep_model_config = None

            try:
                from pymongo import MongoClient
                from app.core.config import settings

                # Using the synchronous MongoDB client
                client = MongoClient(settings.MONGO_URI)
                db = client[settings.MONGO_DB]
                collection = db.system_configs

                # Query the latest active configuration
                doc = collection.find_one({"is_active": True}, sort=[("version", -1)])

                if doc and "llm_configs" in doc:
                    llm_configs = doc["llm_configs"]
                    logger.info(f"✅ 从 MongoDB 读取到 {len(llm_configs)} 个模型配置")

                    for llm_config in llm_configs:
                        if llm_config.get("model_name") == quick_model:
                            quick_model_config = {
                                "max_tokens": llm_config.get("max_tokens", 4000),
                                "temperature": llm_config.get("temperature", 0.7),
                                "timeout": llm_config.get("timeout", 180),
                                "retry_times": llm_config.get("retry_times", 3),
                                "api_base": llm_config.get("api_base")
                            }
                            if llm_config.get("reasoning_effort"):
                                quick_model_config["reasoning_effort"] = llm_config["reasoning_effort"]
                            logger.info(f"✅ 读取快速模型配置: {quick_model}")
                            logger.info(f"   max_tokens={quick_model_config['max_tokens']}, temperature={quick_model_config['temperature']}")
                            logger.info(f"   timeout={quick_model_config['timeout']}, retry_times={quick_model_config['retry_times']}")
                            logger.info(f"   api_base={quick_model_config['api_base']}")

                        if llm_config.get("model_name") == deep_model:
                            deep_model_config = {
                                "max_tokens": llm_config.get("max_tokens", 4000),
                                "temperature": llm_config.get("temperature", 0.7),
                                "timeout": llm_config.get("timeout", 180),
                                "retry_times": llm_config.get("retry_times", 3),
                                "api_base": llm_config.get("api_base")
                            }
                            if llm_config.get("reasoning_effort"):
                                deep_model_config["reasoning_effort"] = llm_config["reasoning_effort"]
                            logger.info(f"✅ 读取深度模型配置: {deep_model} - {deep_model_config}")
                else:
                    logger.warning("⚠️ MongoDB No system configuration found, default parameters will be used")
            except Exception as e:
                logger.warning(f"⚠️ Failed to read model configuration from MongoDB: {e}, Default parameters will be used")

            # Dynamically find suppliers based on model name (synchronized versions)
            llm_provider = "dashscope"  # Used by default dashscope

            # Create a complete configuration using standard configuration functions
            from app.services.simple_analysis_service import create_analysis_config
            config = create_analysis_config(
                research_depth=task.parameters.research_depth,
                selected_analysts=task.parameters.selected_analysts or ["market", "fundamentals"],
                quick_model=quick_model,
                deep_model=deep_model,
                llm_provider=llm_provider,
                market_type=getattr(task.parameters, 'market_type', "A股"),
                quick_model_config=quick_model_config,  # Pass model configuration
                deep_model_config=deep_model_config     # Pass model configuration
            )

            # Get TradingAgents instance
            trading_graph = self._get_trading_graph(config)

            # Perform analysis
            from datetime import timezone
            start_time = datetime.now(timezone.utc)
            analysis_date = task.parameters.analysis_date or datetime.now().strftime("%Y-%m-%d")

            # Call an existing analysis method (synchronous call)
            from tradingagents.agents.utils.agent_context import AgentContext
            # Obtain user risk preference and inject it into AgentContext
            risk_preference = self._get_user_risk_preference(str(task.user_id))
            ctx = AgentContext(user_id=str(task.user_id), preference_id=risk_preference)
            logger.info(f"[diagnose] inject AgentContext task_id={task.task_id} user_id={task.user_id} symbol={task.symbol} date={analysis_date} risk_preference={risk_preference}")
            _, decision = trading_graph.propagate(task.symbol, analysis_date, agent_context=ctx.__dict__)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Extract model information from decisions
            model_info = decision.get('model_info', 'Unknown') if isinstance(decision, dict) else 'Unknown'

            # Build results
            result = AnalysisResult(
                analysis_id=str(uuid.uuid4()),
                summary=decision.get("summary", ""),
                recommendation=decision.get("recommendation", ""),
                confidence_score=decision.get("confidence_score", 0.0),
                risk_level=decision.get("risk_level", "中等"),
                key_points=decision.get("key_points", []),
                detailed_analysis=decision,
                execution_time=execution_time,
                tokens_used=decision.get("tokens_used", 0),
                model_info=model_info  # 🔥 Add model information fields
            )

            logger.info(f"✅ [线程池] 分析任务完成: {task.task_id} - 耗时{execution_time:.2f}秒")
            return result

        except Exception as e:
            logger.error(f"❌ [thread pool] Failed to execute analysis task: {task.task_id} - {e}")
            raise

    async def _execute_single_analysis_async(self, task: AnalysisTask):
        """Asynchronously execute single-strand analysis tasks (run in the background without blocking the main thread)"""
        progress_tracker = None
        try:
            logger.info(f"🔄 开始执行分析任务: {task.task_id} - {task.symbol}")

            # Create a progress tracker
            progress_tracker = RedisProgressTracker(
                task_id=task.task_id,
                analysts=task.parameters.selected_analysts or ["market", "fundamentals"],
                research_depth=task.parameters.research_depth or "标准",
                llm_provider="dashscope"
            )

            # Cache progress tracker
            self._progress_trackers[task.task_id] = progress_tracker

            # Initialization progress
            progress_tracker.update_progress("🚀 开始股票分析")
            await self._update_task_status_with_tracker(task.task_id, AnalysisStatus.PROCESSING, progress_tracker)

            # Perform analysis in a thread pool to avoid blocking the event loop
            import asyncio
            import concurrent.futures

            loop = asyncio.get_event_loop()

            # Run synchronized analysis code using a thread pool executor
            with concurrent.futures.ThreadPoolExecutor() as executor:
                result = await loop.run_in_executor(
                    executor,
                    self._execute_analysis_sync_with_progress,
                    task,
                    progress_tracker
                )

            # Mark complete
            progress_tracker.mark_completed("✅ 研究完成")
            await self._update_task_status_with_tracker(task.task_id, AnalysisStatus.COMPLETED, progress_tracker, result)

            # Record token usage
            try:
                # Get model information used
                quick_model = getattr(task.parameters, 'quick_analysis_model', None)
                deep_model = getattr(task.parameters, 'deep_analysis_model', None)

                # Prioritize using deep analysis models, if not then use fast analysis models
                model_name = deep_model or quick_model or "qwen-plus"

                # Determine supplier based on model name
                from app.services.simple_analysis_service import get_provider_by_model_name
                provider = get_provider_by_model_name(model_name)

                # Log usage
                await self._record_token_usage(task, result, provider, model_name)
            except Exception as e:
                logger.error(f"⚠️  Record token usage failure: {e}")

            logger.info(f"✅ 分析任务完成: {task.task_id}")

        except Exception as e:
            logger.error(f"❌ 分析任务失败: {task.task_id} - {e}")

            # Marking failed
            if progress_tracker:
                progress_tracker.mark_failed(str(e))
                await self._update_task_status_with_tracker(task.task_id, AnalysisStatus.FAILED, progress_tracker)
            else:
                await self._update_task_status(task.task_id, AnalysisStatus.FAILED, 0, str(e))
        finally:
            # Clean progress tracker cache
            if task.task_id in self._progress_trackers:
                del self._progress_trackers[task.task_id]

    async def submit_single_analysis(
        self,
        user_id: str,
        request: SingleAnalysisRequest
    ) -> Dict[str, Any]:
        """提交单股分析任务"""
        try:
            logger.info(f"📝 开始提交单股分析任务")
            logger.info(f"👤 用户ID: {user_id} (类型: {type(user_id)})")

            # Get stock code (Compatible with old fields)
            stock_symbol = request.get_symbol()
            logger.info(f"📊 股票代码: {stock_symbol}")
            logger.info(f"⚙️ 分析参数: {request.parameters}")

            # Generate tasks ID
            task_id = str(uuid.uuid4())
            logger.info(f"🆔 生成任务ID: {task_id}")

            # Convert users ID
            converted_user_id = self._convert_user_id(user_id)
            logger.info(f"🔄 转换后的用户ID: {converted_user_id} (类型: {type(converted_user_id)})")

            # Create analysis tasks
            logger.info(f"🏗️ Start creating AnalysisTask object...")

            # Read merged system settings (ENV first → DB) , For populating models with concurrency/timeout configuration
            try:
                effective_settings = await config_provider.get_effective_system_settings()
            except Exception:
                effective_settings = {}

            # Populate the model in analysis parameters (if not provided explicitly by the request)
            params = request.parameters or AnalysisParameters()
            if not getattr(params, 'quick_analysis_model', None):
                params.quick_analysis_model = effective_settings.get("quick_analysis_model", "qwen-turbo")
            if not getattr(params, 'deep_analysis_model', None):
                params.deep_analysis_model = effective_settings.get("deep_analysis_model", "qwen-max")

            # Apply system-level concurrency and visibility timeouts (if provided)
            try:
                self.queue_service.user_concurrent_limit = int(effective_settings.get("max_concurrent_tasks", DEFAULT_USER_CONCURRENT_LIMIT))
                self.queue_service.global_concurrent_limit = int(effective_settings.get("max_concurrent_tasks", GLOBAL_CONCURRENT_LIMIT))
                self.queue_service.visibility_timeout = int(effective_settings.get("default_analysis_timeout", VISIBILITY_TIMEOUT_SECONDS))
            except Exception:
                # Just use the default value
                pass

            task = AnalysisTask(
                task_id=task_id,
                user_id=converted_user_id,
                symbol=stock_symbol,
                stock_code=stock_symbol,  # Compatible fields
                parameters=params,
                status=AnalysisStatus.PENDING
            )
            logger.info(f"✅ AnalysisTask Object created successfully")

            # Save task to database
            logger.info(f"💾 Start saving tasks to the database...")
            db = get_mongo_db()
            task_dict = task.model_dump(by_alias=True)
            logger.info(f"📄 任务字典: {task_dict}")
            await db.analysis_tasks.insert_one(task_dict)
            logger.info(f"✅ 任务已保存到数据库")

            # 🔥 Single stock analysis: submitted to the queue and processed by the Worker process (consistent with batch analysis)
            logger.info(f"🚀 Start submitting tasks to the queue...")

            # Prepare queue parameters (pass analysis parameters directly, no nesting)
            queue_params = task.parameters.dict() if task.parameters else {}

            # Add task metadata
            queue_params.update({
                "task_id": task.task_id,
                "symbol": task.symbol,
                "stock_code": task.symbol,  # Compatible fields
                "user_id": str(task.user_id),
                "created_at": task.created_at.isoformat() if task.created_at else None
            })

            # Call queue service
            await self.queue_service.enqueue_task(
                user_id=str(converted_user_id),
                symbol=stock_symbol,
                params=queue_params,
                batch_id=None,  # Single stock analysis without batches ID
                task_id=task_id  # Use generated tasks ID
            )

            logger.info(f"✅ The task has been submitted to the queue, task ID: {task_id}")
            logger.info(f"🎉 Single stock analysis task submission completed: {task_id} - {stock_symbol}")

            return {
                "task_id": task_id,
                "symbol": stock_symbol,
                "stock_code": stock_symbol,  # Compatible fields
                "status": AnalysisStatus.PENDING,
                "message": "The task has been submitted to the queue and is waiting for processing by the Worker"
            }
            
        except Exception as e:
            logger.error(f"提交单股分析任务失败: {e}")
            raise
    
    async def submit_batch_analysis(
        self, 
        user_id: str, 
        request: BatchAnalysisRequest
    ) -> Dict[str, Any]:
        """提交批量分析任务"""
        try:
            # Generate batch ID
            batch_id = str(uuid.uuid4())
            
            # Convert users ID
            converted_user_id = self._convert_user_id(user_id)

            # Read system settings, populate model parameters and apply concurrency/timeout configuration
            try:
                effective_settings = await config_provider.get_effective_system_settings()
            except Exception:
                effective_settings = {}

            params = request.parameters or AnalysisParameters()
            if not getattr(params, 'quick_analysis_model', None):
                params.quick_analysis_model = effective_settings.get("quick_analysis_model", "qwen-turbo")
            if not getattr(params, 'deep_analysis_model', None):
                params.deep_analysis_model = effective_settings.get("deep_analysis_model", "qwen-max")

            try:
                self.queue_service.user_concurrent_limit = int(effective_settings.get("max_concurrent_tasks", DEFAULT_USER_CONCURRENT_LIMIT))
                self.queue_service.global_concurrent_limit = int(effective_settings.get("max_concurrent_tasks", GLOBAL_CONCURRENT_LIMIT))
                self.queue_service.visibility_timeout = int(effective_settings.get("default_analysis_timeout", VISIBILITY_TIMEOUT_SECONDS))
            except Exception:
                pass

            # Create batch records
            # Get a list of stock symbols (Compatible with old fields)
            stock_symbols = request.get_symbols()

            batch = AnalysisBatch(
                batch_id=batch_id,
                user_id=converted_user_id,
                title=request.title,
                description=request.description,
                total_tasks=len(stock_symbols),
                parameters=params,
                status=BatchStatus.PENDING
            )

            # Create task list
            tasks = []
            for symbol in stock_symbols:
                task_id = str(uuid.uuid4())
                task = AnalysisTask(
                    task_id=task_id,
                    batch_id=batch_id,
                    user_id=converted_user_id,
                    symbol=symbol,
                    stock_code=symbol,  # Compatible fields
                    parameters=batch.parameters,
                    status=AnalysisStatus.PENDING
                )
                tasks.append(task)
            
            # Save to database
            db = get_mongo_db()
            await db.analysis_batches.insert_one(batch.dict(by_alias=True))
            await db.analysis_tasks.insert_many([task.dict(by_alias=True) for task in tasks])
            
            # Submit task to queue
            for task in tasks:
                # Prepare queue parameters (pass analysis parameters directly, no nesting)
                queue_params = task.parameters.dict() if task.parameters else {}

                # Add task metadata
                queue_params.update({
                    "task_id": task.task_id,
                    "symbol": task.symbol,
                    "stock_code": task.symbol,  # Compatible fields
                    "user_id": str(task.user_id),
                    "batch_id": task.batch_id,
                    "created_at": task.created_at.isoformat() if task.created_at else None
                })

                # Call queue service
                await self.queue_service.enqueue_task(
                    user_id=str(converted_user_id),
                    symbol=task.symbol,
                    params=queue_params,
                    batch_id=task.batch_id
                )
            
            logger.info(f"批量分析任务已提交: {batch_id} - {len(tasks)}个股票")
            
            return {
                "batch_id": batch_id,
                "total_tasks": len(tasks),
                "status": BatchStatus.PENDING,
                "message": f"已提交{len(tasks)}个分析任务到队列"
            }
            
        except Exception as e:
            logger.error(f"提交批量分析任务失败: {e}")
            raise
    
    async def execute_analysis_task(
        self,
        task: AnalysisTask,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> AnalysisResult:
        """Perform a single analysis task — Deactivated

        v3.0 The legacy engine has been retired.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] AnalysisService.execute_analysis_task deactivated,"
            "task_id=%s Please use UnifiedAnalysisEngine.execute_task instead."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
            % getattr(task, "task_id", "<unknown>")
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        try:
            logger.info(f"开始执行分析任务: {task.task_id} - {task.symbol}")
            
            # Update task status
            await self._update_task_status(task.task_id, AnalysisStatus.PROCESSING, 0)
            
            if progress_callback:
                progress_callback(10, "初始化分析引擎...")
            
            # Create complete configurations using standard configuration functions - consistent with single stock analysis
            from app.core.unified_config import unified_config

            quick_model = getattr(task.parameters, 'quick_analysis_model', None) or unified_config.get_quick_analysis_model()
            deep_model = getattr(task.parameters, 'deep_analysis_model', None) or unified_config.get_deep_analysis_model()

            # 🔧 Read the complete configuration parameters of the model from the database
            quick_model_config = None
            deep_model_config = None
            llm_configs = unified_config.get_llm_configs()

            for llm_config in llm_configs:
                if llm_config.model_name == quick_model:
                    quick_model_config = {
                        "max_tokens": llm_config.max_tokens,
                        "temperature": llm_config.temperature,
                        "timeout": llm_config.timeout,
                        "retry_times": llm_config.retry_times,
                        "api_base": llm_config.api_base
                    }
                    if getattr(llm_config, "reasoning_effort", None):
                        quick_model_config["reasoning_effort"] = llm_config.reasoning_effort

                if llm_config.model_name == deep_model:
                    deep_model_config = {
                        "max_tokens": llm_config.max_tokens,
                        "temperature": llm_config.temperature,
                        "timeout": llm_config.timeout,
                        "retry_times": llm_config.retry_times,
                        "api_base": llm_config.api_base
                    }
                    if getattr(llm_config, "reasoning_effort", None):
                        deep_model_config["reasoning_effort"] = llm_config.reasoning_effort

            # Dynamically find suppliers based on model name
            llm_provider = await get_provider_by_model_name(quick_model)

            # Create a complete configuration using standard configuration functions
            config = create_analysis_config(
                research_depth=task.parameters.research_depth,
                selected_analysts=task.parameters.selected_analysts or ["market", "fundamentals"],
                quick_model=quick_model,
                deep_model=deep_model,
                llm_provider=llm_provider,
                market_type=getattr(task.parameters, 'market_type', "A股"),
                quick_model_config=quick_model_config,  # Pass model configuration
                deep_model_config=deep_model_config     # Pass model configuration
            )
            
            if progress_callback:
                progress_callback(30, "创建分析图...")
            
            # Get TradingAgents instance
            trading_graph = self._get_trading_graph(config)
            
            if progress_callback:
                progress_callback(50, "执行股票分析...")
            
            # Perform analysis
            start_time = datetime.utcnow()
            analysis_date = task.parameters.analysis_date or datetime.now().strftime("%Y-%m-%d")
            
            # Call existing analysis methods
            from tradingagents.agents.utils.agent_context import AgentContext
            # Obtain user risk preference and inject it into AgentContext
            risk_preference = self._get_user_risk_preference(str(task.user_id))
            ctx = AgentContext(user_id=str(task.user_id), preference_id=risk_preference)
            logger.info(f"[diagnose] inject AgentContext task_id={task.task_id} user_id={task.user_id} symbol={task.symbol} date={analysis_date} risk_preference={risk_preference}")
            _, decision = trading_graph.propagate(task.symbol, analysis_date, agent_context=ctx.__dict__)
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            if progress_callback:
                progress_callback(80, "处理分析结果...")

            # Extract model information from decisions
            model_info = decision.get('model_info', 'Unknown') if isinstance(decision, dict) else 'Unknown'

            # Build results
            result = AnalysisResult(
                analysis_id=str(uuid.uuid4()),
                summary=decision.get("summary", ""),
                recommendation=decision.get("recommendation", ""),
                confidence_score=decision.get("confidence_score", 0.0),
                risk_level=decision.get("risk_level", "中等"),
                key_points=decision.get("key_points", []),
                detailed_analysis=decision,
                execution_time=execution_time,
                tokens_used=decision.get("tokens_used", 0),
                model_info=model_info  # 🔥 Add model information fields
            )

            if progress_callback:
                progress_callback(100, "研究完成")

            # Update task status
            await self._update_task_status(task.task_id, AnalysisStatus.COMPLETED, 100, result)

            # Record token usage
            try:
                # Log usage
                await self._record_token_usage(task, result, llm_provider, deep_model or quick_model)
            except Exception as e:
                logger.error(f"⚠️  Record token usage failure: {e}")

            logger.info(f"分析任务完成: {task.task_id} - 耗时{execution_time:.2f}秒")

            return result
            
        except Exception as e:
            logger.error(f"执行分析任务失败: {task.task_id} - {e}")
            
            # Update task status is failed
            error_result = AnalysisResult(error_message=str(e))
            await self._update_task_status(task.task_id, AnalysisStatus.FAILED, 0, error_result)
            
            raise
    
    async def _update_task_status(
        self,
        task_id: str,
        status: AnalysisStatus,
        progress: int,
        result: Optional[AnalysisResult] = None,
    ) -> None:
        """Update task status (delegate to split utility function)"""
        try:
            from app.services.analysis.status_update_utils import perform_update_task_status
            await perform_update_task_status(task_id, status, progress, result)
        except Exception as e:
            logger.error(f"更新任务状态失败: {task_id} - {e}")

    async def _update_task_status_with_tracker(
        self,
        task_id: str,
        status: AnalysisStatus,
        progress_tracker: RedisProgressTracker,
        result: Optional[AnalysisResult] = None,
    ) -> None:
        """Update task status using progress tracker (delegate to split utility function)"""
        try:
            from app.services.analysis.status_update_utils import perform_update_task_status_with_tracker
            await perform_update_task_status_with_tracker(task_id, status, progress_tracker, result)
        except Exception as e:
            logger.error(f"更新任务状态失败: {task_id} - {e}")

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        try:
            # First check the in-memory progress tracker
            if task_id in self._progress_trackers:
                progress_tracker = self._progress_trackers[task_id]
                progress_data = progress_tracker.to_dict()

                # Get basic task information from the database
                db = get_mongo_db()
                task = await db.analysis_tasks.find_one({"task_id": task_id})

                if task:
                    # Merge database information and progress tracker information
                    return {
                        "task_id": task_id,
                        "user_id": task.get("user_id"),
                        "symbol": task.get("stock_symbol") or task.get("symbol"),
                        "stock_code": task.get("stock_symbol") or task.get("symbol"),  # Compatible fields
                        "status": progress_data["status"],
                        "progress": progress_data["progress"],
                        "current_step": progress_data["current_step"],
                        "message": progress_data["message"],
                        "elapsed_time": progress_data["elapsed_time"],
                        "remaining_time": progress_data["remaining_time"],
                        "estimated_total_time": progress_data.get("estimated_total_time", 0),
                        "steps": progress_data["steps"],
                        "start_time": progress_data["start_time"],
                        "end_time": None,
                        "last_update": progress_data["last_update"],
                        "parameters": task.get("parameters", {}),
                        "execution_time": None,
                        "tokens_used": None,
                        "result_data": task.get("result"),
                        "error_message": None
                    }

            # Get from Redis cache
            redis_service = get_redis_service()
            progress_key = RedisKeys.TASK_PROGRESS.format(task_id=task_id)
            cached_status = await redis_service.get_json(progress_key)

            if cached_status:
                return cached_status

            # Get from database
            db = get_mongo_db()
            task = await db.analysis_tasks.find_one({"task_id": task_id})

            if task:
                # Calculate elapsed time
                elapsed_time = 0
                remaining_time = 0
                estimated_total_time = 0

                if task.get("started_at"):
                    from datetime import datetime
                    start_time = task.get("started_at")
                    if task.get("completed_at"):
                        # Task completed
                        elapsed_time = (task.get("completed_at") - start_time).total_seconds()
                        estimated_total_time = elapsed_time  # The total time for completed tasks is the elapsed time
                        remaining_time = 0
                    else:
                        # Task in progress
                        elapsed_time = (datetime.utcnow() - start_time).total_seconds()

                        # Use the estimated duration of the task, or use the default (5 minutes) if not available
                        estimated_total_time = task.get("estimated_duration", 300)

                        # Estimated remaining = Estimated total time - elapsed time
                        remaining_time = max(0, estimated_total_time - elapsed_time)

                return {
                    "task_id": task_id,
                    "status": task.get("status"),
                    "progress": task.get("progress", 0),
                    "current_step": task.get("current_step", ""),
                    "message": task.get("message", ""),
                    "elapsed_time": elapsed_time,
                    "remaining_time": remaining_time,
                    "estimated_total_time": estimated_total_time,
                    "start_time": task.get("started_at").isoformat() if task.get("started_at") else None,
                    "updated_at": task.get("updated_at", "").isoformat() if task.get("updated_at") else None,
                    "result_data": task.get("result")
                }

            return None

        except Exception as e:
            logger.error(f"获取任务状态失败: {task_id} - {e}")
            return None
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        try:
            # Update task status
            await self._update_task_status(task_id, AnalysisStatus.CANCELLED, 0)
            
            # Remove from queue (if still in queue)
            await self.queue_service.remove_task(task_id)
            
            logger.info(f"任务已取消: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"取消任务失败: {task_id} - {e}")
            return False

    async def _record_token_usage(
        self,
        task: AnalysisTask,
        result: AnalysisResult,
        provider: str,
        model_name: str
    ):
        """Record token usage"""
        try:
            # Extract token usage information from the results
            # Note: Here you need to get the actual token usage from the LLM response
            # Currently using estimates
            input_tokens = result.tokens_used // 2 if result.tokens_used > 0 else 0
            output_tokens = result.tokens_used - input_tokens if result.tokens_used > 0 else 0

            # If there is no token usage information, use the default estimate
            if result.tokens_used == 0:
                # Estimate based on analysis type
                input_tokens = 2000  # Default input token
                output_tokens = 1000  # Default output token

            # Get model price configuration
            from app.services.config_service import config_service
            config = await config_service.get_system_config()

            # Find the corresponding LLM configuration
            llm_config = None
            if config and config.llm_configs:
                for cfg in config.llm_configs:
                    if cfg.provider == provider and cfg.model_name == model_name:
                        llm_config = cfg
                        break

            # Calculate cost
            cost = 0.0
            currency = "CNY"  # Default currency unit
            if llm_config:
                input_price = llm_config.input_price_per_1k or 0.0
                output_price = llm_config.output_price_per_1k or 0.0
                cost = (input_tokens / 1000 * input_price) + (output_tokens / 1000 * output_price)
                currency = llm_config.currency or "CNY"

            # Create usage record
            usage_record = UsageRecord(
                timestamp=datetime.now().isoformat(),
                provider=provider,
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                currency=currency,
                session_id=task.task_id,
                analysis_type="stock_analysis",
                stock_code=task.symbol
            )

            # Save to database
            success = await self.usage_service.add_usage_record(usage_record)

            if success:
                logger.info(f"💰 记录使用成本: {provider}/{model_name} - ¥{cost:.4f}")
            else:
                logger.warning(f"⚠️  记录使用成本失败")

        except Exception as e:
            logger.error(f"❌ Record token usage failure: {e}")


# Global Analysis Service Instance (Lazy Initialization)
analysis_service: Optional[AnalysisService] = None


def get_analysis_service() -> AnalysisService:
    """Get an Analysis Services instance (lazy initialization)"""
    global analysis_service
    if analysis_service is None:
        analysis_service = AnalysisService()
    return analysis_service
