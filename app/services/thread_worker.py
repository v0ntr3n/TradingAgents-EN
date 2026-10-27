"""
Thread pool task processor
Use ThreadPoolExecutor to process queue tasks within the Backend process
"""

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any
from datetime import datetime

from app.core.database import get_mongo_db, get_redis_client
from app.services.queue_service import QueueService
from app.services.task_analysis_service import TaskAnalysisService
from app.models.analysis import UnifiedAnalysisTask, AnalysisTaskType, AnalysisStatus
from tradingagents.utils.stock_utils import StockUtils, SecurityType

logger = logging.getLogger(__name__)


class ThreadWorker:
    """线程池任务处理器"""
    
    def __init__(self, max_workers: int = 3):
        """
        Initialize thread pool Worker
        
        Args:
            max_workers: Maximum number of concurrent threads (default 3)
        """
        self.max_workers = max_workers
        self.executor: Optional[ThreadPoolExecutor] = None
        self.running = False
        self.worker_id = f"thread-worker-{threading.get_ident()}"
        self.queue_service: Optional[QueueService] = None
        self.task_service: Optional[TaskAnalysisService] = None
        self._loop_task: Optional[asyncio.Task] = None
        self._gap_resolution_poll_interval_seconds = 2.0
        self._gap_resolution_last_poll_at = 0.0
        
        logger.info(f"🔧 ThreadWorker initialization: max_workers={max_workers}")
    
    async def start(self):
        """启动线程池 Worker"""
        if self.running:
            logger.warning("ThreadWorker Already running")
            return
        
        logger.info("=" * 60)
        logger.info("🚀 Start thread pool Worker...")
        logger.info(f"   最大并发数: {self.max_workers}")
        logger.info(f"   Worker ID: {self.worker_id}")
        logger.info("=" * 60)
        
        # Initialize service
        logger.info("⏳ [ThreadWorker] Initialize the Redis client agent")
        redis = get_redis_client()
        logger.info("✅ [ThreadWorker] Redis Client agent initialization completed")
        logger.info("⏳ [ThreadWorker] initialization QueueService")
        self.queue_service = QueueService(redis)
        logger.info("✅ [ThreadWorker] QueueService Initialization completed")
        logger.info("⏳ [ThreadWorker] initialization TaskAnalysisService")
        self.task_service = TaskAnalysisService()
        logger.info("✅ [ThreadWorker] TaskAnalysisService Initialization completed")
        
        # Create thread pool
        logger.info("⏳ [ThreadWorker] Create a thread pool executor")
        self.executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="analysis-worker"
        )
        logger.info("✅ [ThreadWorker] The thread pool executor is created")
        
        self.running = True
        
        # Start queue listening loop
        logger.info("⏳ [ThreadWorker] Start queue listening loop")
        self._loop_task = asyncio.create_task(self._queue_loop())
        
        logger.info("✅ Thread pool Worker started successfully")
    
    async def stop(self):
        """停止线程池 Worker"""
        if not self.running:
            return
        
        logger.info("🛑 Stop thread pool Worker...")
        self.running = False
        
        # Cancel queue loop
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        
        # Close thread pool
        if self.executor:
            logger.info("   等待线程池任务完成...")
            self.executor.shutdown(wait=True, cancel_futures=False)
            logger.info("   线程池已关闭")
        
        logger.info("✅ Thread pool worker stopped")
    
    async def _queue_loop(self):
        """队列监听循环"""
        logger.info("📡 队列监听循环启动")

        while self.running:
            try:
                now_ts = time.time()
                if now_ts - self._gap_resolution_last_poll_at >= self._gap_resolution_poll_interval_seconds:
                    await self._tick_gap_resolution_jobs()
                    self._gap_resolution_last_poll_at = now_ts

                # Get tasks from queue
                task_data = await self.queue_service.dequeue_task(self.worker_id)

                if not task_data:
                    # The queue is empty, please wait for a while
                    await asyncio.sleep(1)
                    continue

                # Submit tasks to the thread pool (without waiting for completion)
                task_id = task_data.get("id")
                logger.info(f"📊 收到任务: {task_id}, 提交到线程池...")

                # 🔥 Process tasks directly in the current event loop (without using the thread pool)
                # Because the task itself is I/O intensive, asyncio already provides concurrency capabilities
                asyncio.create_task(self._process_task_async(task_data))

            except asyncio.CancelledError:
                logger.info("队列循环被取消")
                break
            except Exception as e:
                logger.error(f"队列循环错误: {e}", exc_info=True)
                await asyncio.sleep(1)

        logger.info("📡 队列监听循环结束")

    async def _tick_gap_resolution_jobs(self):
        """Poll and advance the Agent workshop gap filling asynchronous job."""
        try:
            from core.tools.implementations.agent_builder.nanobot_agent_builder_tools import (
                process_agent_workshop_gap_resolution_jobs_once,
            )
        except ImportError:
            # The community version does not have the Agent workshop module (manifest excludes app/models/agent_workshop, etc.).
            # Silently disable polling after a one-time prompt to avoid WARNINGs every tick.
            if not getattr(type(self), "_gap_job_unavailable_logged", False):
                type(self)._gap_job_unavailable_logged = True
                logger.info(
                    "[GapJob] Agent Workshop module is unavailable (community edition), gap filling polling is disabled"
                )
            return

        try:
            result = await process_agent_workshop_gap_resolution_jobs_once(
                limit=1,
                worker_id=self.worker_id,
            )
            status = str((result or {}).get("status") or "").strip().lower()
            processed = int((result or {}).get("processed") or 0)
            attempted = int((result or {}).get("attempted") or 0)
            claim_skipped = int((result or {}).get("claim_skipped") or 0)
            active_jobs = int((result or {}).get("active_jobs") or 0)

            if status != "ok":
                logger.debug("[GapJob][Tick] status=%s err=%s", status, result.get("message", ""))
                return

            if processed > 0 or attempted > 0:
                logger.info(
                    "[GapJob][Tick] worker_id=%s active_jobs=%s processed=%s attempted=%s claim_skipped=%s",
                    self.worker_id,
                    active_jobs,
                    processed,
                    attempted,
                    claim_skipped,
                )
        except Exception as exc:
            logger.warning("[GapJob][Tick] worker_id=%s err=%s", self.worker_id, exc)
    


    async def _process_task_async(self, task_data: Dict[str, Any]):
        """
        Asynchronous processing tasks

        Args:
            task_data: mission data
        """
        task_id = task_data.get("id")
        stock_code = task_data.get("symbol")
        user_id = task_data.get("user")

        logger.info(f"🔧 开始处理任务: {task_id} - {stock_code}")

        success = False

        try:
            # Parse task parameters
            # 🔥 Fix:queue_service.get_task() Parse params and store them in the parameters field
            parameters_dict = task_data.get("parameters", {})
            if not parameters_dict:
                # Compatible with older versions: if parameters does not exist, try to read from params
                parameters_dict = task_data.get("params", {})
                if isinstance(parameters_dict, str):
                    import json
                    parameters_dict = json.loads(parameters_dict)

            # 🔍 Debugging: Print parameter content
            logger.info(f"🔍 [DEBUG] Task parameters: {parameters_dict}")

            # Check engine type (default uses v2 engine)
            engine_type = parameters_dict.get("engine", "v2")

            existing_task = None
            if engine_type == "v2":
                existing_task = await self.task_service.get_task(task_id)
                if existing_task:
                    from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
                    from app.utils.timezone import now_tz

                    memory_manager = get_memory_state_manager()
                    memory_task = await memory_manager.get_task(task_id)
                    if not memory_task:
                        await memory_manager.create_task(
                            task_id=task_id,
                            user_id=user_id,
                            stock_code=stock_code,
                            parameters=parameters_dict,
                            stock_name=None,
                        )

                    existing_task.status = AnalysisStatus.PROCESSING
                    if not existing_task.started_at:
                        existing_task.started_at = now_tz()
                    existing_task.progress = max(existing_task.progress or 0, 1)
                    existing_task.current_step = "数据准备"
                    existing_task.message = "Preparing data for analysis..."
                    await self.task_service._update_task(existing_task)

                    await memory_manager.update_task_status(
                        task_id=task_id,
                        status=TaskStatus.RUNNING,
                        progress=existing_task.progress,
                        message=existing_task.message,
                        current_step="data_preparation",
                        current_step_name="数据准备",
                        current_step_description=existing_task.message
                    )

            # 📡 JIT Data synchronization: proactively pull the latest market data before analysis to ensure that stale data is not used
            try:
                from app.worker.analysis_worker import jit_sync_stock_data
                jit_result = await jit_sync_stock_data(stock_code, parameters_dict)
                if not jit_result.is_valid:
                    logger.error(f"❌ [ThreadWorker] JIT Data synchronization failed: {jit_result.message}")
                    raise ValueError(f"数据准备失败: {jit_result.message}")
                logger.info(f"✅ [ThreadWorker] JIT Data synchronization completed: {jit_result.message}")
            except ValueError:
                raise
            except Exception as jit_err:
                logger.warning(f"⚠️ [ThreadWorker] JIT Data synchronization exception (continue analysis): {jit_err}")

            logger.info(f"🔧 使用 {engine_type} 引擎执行任务: {task_id}")

            if engine_type == "v2":
                # Using v2.0 Unified Task Engine
                from bson import ObjectId

                if existing_task:
                    # The task already exists, execute it directly
                    logger.info(f"📋 The task already exists, execute it directly: {task_id} (task_type={existing_task.task_type})")
                    await self.task_service.execute_task(existing_task)
                else:
                    # The task does not exist, create and execute
                    sec_type = StockUtils.identify_security_type(stock_code)
                    requested_market = parameters_dict.get("market_type")
                    if requested_market == "ETF" or sec_type == SecurityType.FUND:
                        inferred_task_type = AnalysisTaskType.ETF_ANALYSIS
                        parameters_dict.setdefault("selected_analysts", ["etf", "market", "news"])
                        logger.info(f"📋 The task does not exist. Rebuild the task according to the ETF process.: {task_id}")
                    else:
                        inferred_task_type = AnalysisTaskType.STOCK_ANALYSIS
                        logger.info(f"📋 The task does not exist. Rebuild the task according to the stock process.: {task_id}")

                    await self.task_service.create_and_execute_task(
                        user_id=ObjectId(user_id) if user_id else ObjectId(),
                        task_type=inferred_task_type,
                        task_params={
                            "symbol": stock_code,
                            "stock_code": stock_code,
                            **parameters_dict
                        },
                        engine_type="v2",
                        task_id=task_id  # 🔥 Pass the task_id parameter directly
                    )

                logger.info(f"✅ [v2 engine] Mission accomplished: {task_id}")

            elif engine_type == "unified":
                # Use unified analytics services
                from app.services.unified_analysis_service import UnifiedAnalysisService

                unified_service = UnifiedAnalysisService()
                await unified_service.analyze_stock(
                    stock_code=stock_code,
                    user_id=user_id,
                    task_id=task_id,
                    **parameters_dict
                )
                logger.info(f"✅ [unified engine] Mission accomplished: {task_id}")

            else:
                # The legacy engine has been retired — Refusal to execute
                logger.error(
                    f"❌ [ThreadWorker] Refuse to execute legacy engine tasks: task_id={task_id}, engine={engine_type}"
                )
                raise RuntimeError(
                    "[Deactivated] thread_worker reject engine=%s task,"
                    "Please change the queue parameter engine to 'v2'. "
                    "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md" % engine_type
                )
                # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
                # Use legacy engine
                from app.services.simple_analysis_service import SimpleAnalysisService
                from app.models.analysis import SingleAnalysisRequest, AnalysisParameters

                # 🔥 Constructs an AnalysisParameters object from a dictionary of parameters
                params = AnalysisParameters(**parameters_dict) if parameters_dict else AnalysisParameters()

                # 🔥 Construct a SingleAnalysisRequest object
                request = SingleAnalysisRequest(
                    symbol=stock_code,
                    stock_code=stock_code,
                    parameters=params
                )

                simple_service = SimpleAnalysisService()
                await simple_service.execute_analysis_background(
                    task_id=task_id,
                    user_id=user_id,
                    request=request
                )
                logger.info(f"✅ [legacy engine] Mission accomplished: {task_id}")

            success = True

        except Exception as e:
            logger.error(f"❌ 任务执行失败: {task_id} - {e}", exc_info=True)
            success = False

        finally:
            # Confirm task completion (either success or failure)
            try:
                await self.queue_service.ack_task(task_id, success)
                logger.info(f"✅ 任务已确认: {task_id} (成功: {success})")
            except Exception as e:
                logger.error(f"❌ 确认任务失败: {task_id} - {e}")


# Global ThreadWorker instance
_thread_worker: Optional[ThreadWorker] = None


async def start_thread_worker(max_workers: int = 3):
    """Start global thread pool Worker"""
    global _thread_worker

    if _thread_worker is not None:
        logger.warning("ThreadWorker Already started")
        return

    _thread_worker = ThreadWorker(max_workers=max_workers)
    await _thread_worker.start()


async def stop_thread_worker():
    """Stop the global thread pool Worker"""
    global _thread_worker

    if _thread_worker is None:
        return

    await _thread_worker.stop()
    _thread_worker = None


def get_thread_worker() -> Optional[ThreadWorker]:
    """Get the global thread pool Worker instance"""
    return _thread_worker

