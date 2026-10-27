"""
Task Analysis Services

Analysis task management service based on UnifiedAnalysisTask model
Provide a unified task creation, execution, and query interface
"""

from typing import Dict, Any, Optional, List, Callable, Union
import logging
import uuid
import asyncio
import inspect
from datetime import datetime

from app.models.analysis import (
    UnifiedAnalysisTask,
    AnalysisTaskType,
    AnalysisStatus
)
from app.models.user import PyObjectId
from app.services.unified_analysis_engine import UnifiedAnalysisEngine
from app.services.workflow_registry import AnalysisWorkflowRegistry
from app.core.database import get_mongo_db
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)

ETF_CODE_PREFIXES = ("50", "51", "52", "56", "58", "15", "16", "18")


def _is_cn_etf_symbol(code: Optional[str]) -> bool:
    code_str = str(code or "").strip()
    return len(code_str) == 6 and code_str.isdigit() and code_str.startswith(ETF_CODE_PREFIXES)


def _normalize_memory_market(symbol: str, raw_market: Optional[str] = None) -> str:
    normalized_market = str(raw_market or "").strip().lower()
    if normalized_market in {"cn", "a股", "a_shares", "china", "china_a", "ashare"}:
        return "cn"
    if normalized_market in {"hk", "港股", "hongkong", "hong_kong"}:
        return "hk"
    if normalized_market in {"us", "美股", "usa", "united_states"}:
        return "us"

    try:
        from tradingagents.utils.stock_utils import StockMarket, StockUtils

        market = StockUtils.identify_stock_market(symbol)
        mapping = {
            StockMarket.CHINA_A: "cn",
            StockMarket.HONG_KONG: "hk",
            StockMarket.US: "us",
            StockMarket.UNKNOWN: "cn",
        }
        return mapping.get(market, "cn")
    except Exception:
        return "cn"


class TaskCancelledException(Exception):
    """任务被取消异常"""
    pass


class TaskAnalysisService:
    """Task Analysis Services
    
    Analysis task management based on UnifiedAnalysisTask model
    
    Usage example:
        service = TaskAnalysisService()
        
        # Create and execute tasks
        task = await service.create_and_execute_task(
            user_id=user_id,
            task_type=AnalysisTaskType.STOCK_ANALYSIS,
            task_params={"symbol": "000858", "market_type": "cn"}
        )
        
        # Query tasks
        task = await service.get_task(task_id)
        
        # Query all tasks of the user
        tasks = await service.list_user_tasks(user_id)
    """
    
    def __init__(self):
        """初始化服务"""
        self.engine = UnifiedAnalysisEngine()
        self.db = get_mongo_db()
        self.collection = self.db.unified_analysis_tasks
        self.logger = logger
    
    async def create_task(
        self,
        user_id: PyObjectId,
        task_type: AnalysisTaskType,
        task_params: Dict[str, Any],
        engine_type: str = "auto",
        preference_type: str = "neutral",
        workflow_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        task_id: Optional[str] = None  # 🔥 Support incoming task_id
    ) -> UnifiedAnalysisTask:
        """Create analysis tasks

        Args:
            user_id: User ID
            task_type: Task type
            task_params: Task parameters
            engine_type: Engine type (auto/workflow/legacy/llm)
            preference_type: Analyze preferences (aggressive/neutral/conservative)
            workflow_id: Workflow ID (optional)
            batch_id: Batch ID (optional)
            task_id: Task ID (optional, automatically generated if not provided)

        Returns:
            Created task object
        """
        # Generate task ID if not provided
        if task_id is None:
            task_id = str(uuid.uuid4())
        
        # Create task object
        task = UnifiedAnalysisTask(
            task_id=task_id,
            user_id=user_id,
            task_type=task_type,
            task_params=task_params,
            engine_type=engine_type,
            preference_type=preference_type,
            workflow_id=workflow_id,
            batch_id=batch_id,
            status=AnalysisStatus.PENDING,
            created_at=now_tz()
        )
        
        # Save to database
        await self._save_task(task)
        
        self.logger.info(f"✅ 创建任务: {task_id} (类型: {task_type})")
        
        return task
    
    async def execute_task(
        self,
        task_or_id: Union[UnifiedAnalysisTask, str],
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> UnifiedAnalysisTask:
        """Perform analysis tasks

        Args:
            task_or_id: task object or task ID
            progress_callback: Progress callback function

        Returns:
            Updated task object
        """
        # If the task_id is passed in, get the task object first
        if isinstance(task_or_id, str):
            task = await self.get_task(task_or_id)
            if not task:
                raise ValueError(f"任务不存在: {task_or_id}")
        else:
            task = task_or_id

        self.logger.info(f"🚀 执行任务: {task.task_id}")

        from app.services.memory_state_manager import get_memory_state_manager

        memory_manager = get_memory_state_manager()
        memory_task = await memory_manager.get_task(task.task_id)
        if not memory_task:
            task_params = task.task_params or {}
            await memory_manager.create_task(
                task_id=task.task_id,
                user_id=str(task.user_id),
                stock_code=str(task_params.get("symbol") or task_params.get("stock_code") or ""),
                parameters=task_params,
                stock_name=None,
            )

        # Create a wrapped progress callback that updates the database and memory
        async def wrapped_progress_callback(progress: int, message: str, **kwargs):
            """Wrapped progress callback: update task progress and save to database and memory"""
            # � New: Check if task was canceled
            if await self._is_task_cancelled(task.task_id):
                self.logger.warning(f"⚠️ 任务已被取消: {task.task_id}")
                raise TaskCancelledException(f"任务 {task.task_id} 已被用户取消")

            # �🔑 Key: extract step_name (short name) from kwargs
            step_name = kwargs.get("step_name", "")

            # Update task object
            task.progress = progress
            task.current_step = step_name or message  # ✅ Use step_name instead message
            task.message = message  # ✅ Save detailed description to message field

            # Save to database
            await self._update_task(task)

            # 🔑 Key: Update memory status at the same time
            from app.services.memory_state_manager import TaskStatus
            await memory_manager.update_task_status(
                task_id=task.task_id,
                status=TaskStatus.RUNNING,
                progress=progress,
                message=message,
                current_step=step_name or message,
                current_step_name=step_name,  # 🔑 Pass step name
                current_step_description=message  # 🔑 Transfer step description
            )

            # Call the original callback (if any)
            if progress_callback:
                if asyncio.iscoroutinefunction(progress_callback):
                    await progress_callback(progress, message, **kwargs)
                else:
                    progress_callback(progress, message, **kwargs)

        try:
            # 🔥🔥🔥 Data verification is disabled (the function is not perfect)
            # Reason: The historical data synchronization function is not completed, and the verification will prevent normal analysis.
            # To restore, uncomment the following:
            # if task.task_type == AnalysisTaskType.STOCK_ANALYSIS:
            #     validation_result = await self._validate_task_data(task)
            #     if not validation_result.is_valid:
            #         # Data verification failed, update task status and return
            #         task.status = AnalysisStatus.FAILED
            #         task.error_message = validation_result.message
            #         task.completed_at = now_tz()
            #         await self._update_task(task)
            #
            #         # Update memory status
            #         from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
            #         memory_manager = get_memory_state_manager()
            #         await memory_manager.update_task_status(
            #             task_id=task.task_id,
            #             status=TaskStatus.FAILED,
            #             progress=0,
            #             message=validation_result.message,
            #             current_step="data_validation",
            #             current_step_name="Data verification",
            #             current_step_description=validation_result.message
            #         )
            #
            #         self.logger.warning(f"⚠️ Task {task.task_id} Data verification failed: {validation_result.message}")
            #         raise ValueError(validation_result.message)

            # Update task status to Processing
            task.status = AnalysisStatus.PROCESSING
            task.started_at = now_tz()
            task.progress = 0
            await self._update_task(task)

            # 🔑 Key: Update memory status at the same time
            from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
            memory_manager = get_memory_state_manager()
            await memory_manager.update_task_status(
                task_id=task.task_id,
                status=TaskStatus.RUNNING,
                progress=0,
                message="开始分析...",
                current_step="initialization",
                current_step_name="初始化",  # 🔑 Pass step name
                current_step_description="开始分析..."  # 🔑 Transfer step description
            )

            # Execute the task (the engine will update the status of the task object)
            result = await self.engine.execute_task(task, wrapped_progress_callback)

            # 🔑 Key: Format the result data to ensure it contains all fields required by the front end
            formatted_result = self._format_analysis_result(result, task)
            task.result = formatted_result

            # 🔑 Key: Set task completion time and execution time
            task.completed_at = now_tz()
            task.progress = 100  # Make sure the progress is 100
            if task.started_at:
                task.execution_time = (task.completed_at - task.started_at).total_seconds()
                self.logger.info(f"📊 任务执行时间: {task.execution_time:.2f}s")
            else:
                self.logger.warning(f"⚠️ The task does not have started_at and cannot be calculated execution_time")

            # 🔥 Save to analysis_reports collection (compatible with legacy API)
            # Note: You must save before updating the task in order to get the correct analysis_id
            saved_analysis_id = None
            if task.task_type in (AnalysisTaskType.STOCK_ANALYSIS, AnalysisTaskType.ETF_ANALYSIS):
                saved_analysis_id = await self._save_to_analysis_reports(task, formatted_result)
                # 🔑 Key: Update analysis_id in result to the saved true value ID
                if saved_analysis_id and task.result:
                    task.result["analysis_id"] = saved_analysis_id
                    self.logger.info(f"✅ Updated in task results analysis_id: {saved_analysis_id}")

            # 🧠 Objectized stock memory: only writes after real stock analysis is completed to avoid free text pollution.
            if task.task_type == AnalysisTaskType.STOCK_ANALYSIS:
                try:
                    await asyncio.wait_for(
                        self._store_stock_object_memory(task, formatted_result),
                        timeout=20,
                    )
                except asyncio.TimeoutError:
                    self.logger.warning(f"⚠️ Objectized stock memory write timeout(ignore): {task.task_id}")
                except Exception as memory_err:
                    self.logger.warning(f"⚠️ Objectized stock memory write failed(ignore): {memory_err}")

            # 🔑🔑🔑 Key fix: Persist the results first and update the memory status to COMPLETED,
            # Then perform slow operations (notifications, emails, user portraits, writing back research topics).
            # Avoid front-end detection progress=100 Race condition where data is not yet ready when /result is requested immediately after.
            task.status = AnalysisStatus.COMPLETED
            await self._update_task(task)

            # 🔑 Key: Update the memory status to complete (front-end polling relies on this status)
            from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
            memory_manager = get_memory_state_manager()
            await memory_manager.update_task_status(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="分析完成",
                current_step="completed",
                current_step_name="已完成",
                current_step_description="分析完成",
                result_data=task.result
            )

            self.logger.info(f"✅ Task results are persisted and marked complete: {task.task_id}")

            # ---- The following are non-critical post-processing operations. Even if they fail, they will not affect the results obtained by the front end. ----
            if task.task_type in (AnalysisTaskType.STOCK_ANALYSIS, AnalysisTaskType.ETF_ANALYSIS):
                _symbol = (task.task_params or {}).get("symbol", "")
                _stock_name = formatted_result.get("stock_name") or formatted_result.get("stock_symbol") or _symbol
                # The stock_name in the results is often just the code itself, and the database is checked back to complete the Chinese name (such as Kweichow Moutai)
                if _symbol and _stock_name == _symbol:
                    try:
                        from app.services.simple_analysis_service import _get_cached_security_name
                        _stock_name = _get_cached_security_name(_symbol) or _stock_name
                    except Exception as name_err:
                        self.logger.debug(f"Failed to complete stock name(ignore): {name_err}")
                _name_label = f"{_stock_name}({_symbol})" if _stock_name and _stock_name != _symbol else _symbol
                _summary = formatted_result.get("summary") or formatted_result.get("executive_summary") or ""
                if _summary and len(_summary) > 80:
                    _summary = _summary[:80] + "…"

                # 📢 Unified notification: bell on the site + IM Callback (QQ, etc.)+ User configuration channels (Feishu/DingTalk, etc.)
                try:
                    from app.services.notifications_service import get_notifications_service
                    from app.models.notification import NotificationCreate
                    _notif_meta: Dict[str, Any] = {}
                    _im_channel = (task.task_params or {}).get("_im_channel")
                    if _im_channel:
                        _notif_meta["_im_channel"] = _im_channel
                    await get_notifications_service().create_and_publish(NotificationCreate(
                        user_id=str(task.user_id),
                        type="analysis",
                        title=f"✅ {_name_label} 分析完成",
                        content=_summary or "The analysis is complete, click to view the full report.",
                        link="/tasks/unified",
                        source="task_analysis",
                        severity="success",
                        metadata=_notif_meta,
                    ))
                except Exception as notif_err:
                    self.logger.warning(f"⚠️ Failed to send unified notification(ignore): {notif_err}")

                # 📧 Send email notification (including PDF attachment, keep independent path)
                try:
                    await self._send_analysis_email_notification(task, formatted_result)
                except Exception as email_err:
                    self.logger.warning(f"⚠️ Failed to send email notification(ignore): {email_err}")

                # 🧠 Update user portrait (recently_analyzed)
                try:
                    from app.services.intelligent_assistant_service import update_user_profile_with_analysis
                    _conclusion = (
                        formatted_result.get("investment_rating")
                        or formatted_result.get("comprehensive_conclusion")
                        or formatted_result.get("rating")
                        or ""
                    )
                    if isinstance(_conclusion, dict):
                        _conclusion = _conclusion.get("rating") or _conclusion.get("label") or str(_conclusion)
                    _conclusion = str(_conclusion)[:20]
                    await update_user_profile_with_analysis(
                        db=self.db,
                        user_id=str(task.user_id),
                        symbol=_symbol,
                        name=_stock_name,
                        conclusion=_conclusion,
                        task_id=str(task.task_id),
                    )
                except Exception as profile_err:
                    self.logger.warning(f"⚠️ Failed to update user portrait(ignore): {profile_err}")

                # 🔗 Automatically hang the completed report back to the current research topic; if there is no topic, enter"Report storage"
                try:
                    from app.services.intelligent_assistant_service import write_report_back_to_assistant_thread

                    preferred_thread_id = ((task.task_params or {}).get("_assistant_thread_id") or "").strip() or None
                    report_summary = (
                        formatted_result.get("summary")
                        or formatted_result.get("executive_summary")
                        or formatted_result.get("recommendation")
                        or ""
                    )
                    writeback_message = (
                        f"【分析报告已归档】{_stock_name}({_symbol})\n"
                        f"Task ID: {task.task_id}\n"
                        f"Summary: {(report_summary or 'The analysis is complete and can be viewed in the associated report.')[:300]}"
                    )
                    await write_report_back_to_assistant_thread(
                        db=self.db,
                        user_id=str(task.user_id),
                        preferred_thread_id=preferred_thread_id,
                        report_ref={
                            "ref_type": "stock_report",
                            "report_key": str(task.task_id),
                            "source_collection": "unified_analysis_tasks",
                            "title": f"{_stock_name}({_symbol}) 分析报告",
                            "symbol": _symbol,
                            "summary": (report_summary or "")[:400],
                            "status": "completed",
                            "task_id": str(task.task_id),
                            "analysis_id": saved_analysis_id,
                            "created_at": task.completed_at or now_tz(),
                        },
                        summary_message=writeback_message,
                    )
                except Exception as writeback_err:
                    self.logger.warning(f"⚠️ Failed to write back research topic(ignore): {writeback_err}")

            # Growth extraction is executed in the background to avoid blocking the completion time of the main task.
            self._schedule_growth_extraction(
                task_id=task.task_id,
                raw_result=result,
                formatted_result=formatted_result,
                analysis_id=saved_analysis_id,
            )

            self.logger.info(f"✅ 任务完成: {task.task_id}")

        except TaskCancelledException as e:
            # 🔥 Processing task cancellation
            self.logger.warning(f"⚠️ 任务被取消: {task.task_id} - {e}")
            task.status = AnalysisStatus.CANCELLED
            task.completed_at = now_tz()
            task.error_message = str(e)
            if task.started_at:
                task.execution_time = (task.completed_at - task.started_at).total_seconds()
            await self._update_task(task)

            # 🔑 Key: Update memory status at the same time
            from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
            memory_manager = get_memory_state_manager()
            await memory_manager.update_task_status(
                task_id=task.task_id,
                status=TaskStatus.CANCELLED,
                progress=task.progress,
                message="任务已被用户取消",
                current_step="cancelled"
            )

            self.logger.info(f"🚫 任务已取消: {task.task_id}")

        except Exception as e:
            # 🔥 Handling gracefully: distinguishing between cancellation and failure
            if isinstance(e, TaskCancelledException):
                # Task cancellation has been handled in the except TaskCancelledException block above
                # This shouldn't be reached, but it's better to be on the safe side.
                self.logger.warning(f"⚠️ Unhandled cancellation exception caught: {task.task_id}")
                raise

            # Other exceptions are real failures
            task.status = AnalysisStatus.FAILED
            task.error_message = str(e)
            task.completed_at = now_tz()

            # Save to database
            await self._update_task(task)

            # 🔑 Key: Update memory status to failed
            from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
            memory_manager = get_memory_state_manager()
            await memory_manager.update_task_status(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                progress=task.progress,
                message=f"分析失败: {str(e)}",
                current_step_name="失败",  # 🔑 Pass step name
                current_step_description=f"分析失败: {str(e)}",  # 🔑 Transfer step description
                error_message=str(e)
            )

            self.logger.error(f"❌ 任务失败: {task.task_id} - {e}")
            raise

        return task
    
    async def create_and_execute_task(
        self,
        user_id: PyObjectId,
        task_type: AnalysisTaskType,
        task_params: Dict[str, Any],
        engine_type: str = "auto",
        preference_type: str = "neutral",
        workflow_id: Optional[str] = None,
        task_id: Optional[str] = None,  # 🔥 Support incoming task_id
        progress_callback: Optional[Callable] = None
    ) -> UnifiedAnalysisTask:
        """Create and execute tasks (one step at a time)

        Args:
            user_id: User ID
            task_type: Task type
            task_params: Task parameters
            engine_type: Engine type
            preference_type: Analyze preferences
            workflow_id: Workflow ID
            task_id: Task ID (optional, automatically generated if not provided)
            progress_callback: Progress callback

        Returns:
            Completed task object
        """
        # Create task
        task = await self.create_task(
            user_id=user_id,
            task_type=task_type,
            task_params=task_params,
            engine_type=engine_type,
            preference_type=preference_type,
            workflow_id=workflow_id,
            task_id=task_id  # 🔥 pass on task_id
        )
        
        # perform tasks
        task = await self.execute_task(task, progress_callback)

        return task

    async def get_task(self, task_id: str) -> Optional[UnifiedAnalysisTask]:
        """Get tasks

        Args:
            task_id: Task ID

        Returns:
            Task object, returned if it does not exist None
        """
        doc = await self.collection.find_one({"task_id": task_id})
        if not doc:
            return None

        return UnifiedAnalysisTask(**doc)

    async def list_user_tasks(
        self,
        user_id: PyObjectId,
        task_type: Optional[AnalysisTaskType] = None,
        status: Optional[AnalysisStatus] = None,
        symbol: Optional[str] = None,
        limit: int = 999999,
        skip: int = 0
    ) -> List[UnifiedAnalysisTask]:
        """List user s tasks

        Args:
            user_id: User ID
            task_type: Task type filtering (optional)
            status: Status filtering (optional)
            symbol: Stock code filtering (optional, matches symbol/code/stock_code in task_params)
            limit: Return quantity limit (default returns all)
            skip: skip quantity

        Returns:
            task list
        """
        self.logger.info(f"📋 查询用户任务列表 - user_id: {user_id} (类型: {type(user_id)})")
        self.logger.info(f"📋 Query conditions - task_type: {task_type}, status: {status}, symbol: {symbol}, limit: {limit}, skip: {skip}")

        query: Dict[str, Any] = {"user_id": user_id}

        if task_type:
            query["task_type"] = task_type

        if status:
            query["status"] = status

        if symbol:
            # Matches in task_params symbol / code / stock_code
            symbol_upper = symbol.upper()
            symbol_lower = symbol.lower()
            query["$or"] = [
                {"task_params.symbol": symbol},
                {"task_params.symbol": symbol_upper},
                {"task_params.symbol": symbol_lower},
                {"task_params.code": symbol},
                {"task_params.code": symbol_upper},
                {"task_params.code": symbol_lower},
                {"task_params.stock_code": symbol},
                {"task_params.stock_code": symbol_upper},
                {"task_params.stock_code": symbol_lower},
            ]

        self.logger.info(f"📋 MongoDB查询: {query}")

        # Check the total first
        total = await self.collection.count_documents(query)
        self.logger.info(f"📋 匹配的任务总数: {total}")

        # Debugging: Check all tasks in the database
        all_tasks_count = await self.collection.count_documents({})
        self.logger.debug(f"📊 Total number of all tasks in the database: {all_tasks_count}")

        # Debugging: Statistics by task_type
        task_type_stats = await self.collection.aggregate([
            {"$group": {"_id": "$task_type", "count": {"$sum": 1}}}
        ]).to_list(None)
        self.logger.debug(f"📊 Statistics by task_type: {task_type_stats}")

        # Debugging: Find all position_analysis tasks
        position_tasks = await self.collection.find({"task_type": "position_analysis"}).to_list(None)
        self.logger.debug(f"📊 position_analysis total number of tasks: {len(position_tasks)}")
        if position_tasks:
            for task in position_tasks[:3]:
                self.logger.debug(f"  - task_id: {task.get('task_id')}, user_id: {task.get('user_id')} (类型: {type(task.get('user_id'))}), created_at: {task.get('created_at')}")

        # Debugging: View all tasks sorted by created_at in reverse order
        all_sorted = await self.collection.find({}).sort("created_at", -1).limit(20).to_list(20)
        self.logger.debug(f"📊 Top 20 tasks in reverse order by created_at:")
        for i, task in enumerate(all_sorted):
            self.logger.debug(f"  {i+1}. task_id: {task.get('task_id')}, task_type: {task.get('task_type')}, user_id: {task.get('user_id')} (类型: {type(task.get('user_id'))}), created_at: {task.get('created_at')}")

        # Debugging: List user_id and task_type
        if all_tasks_count > 0:
            all_docs = await self.collection.find({}).limit(10).to_list(10)
            self.logger.debug(f"📊 Top 10 tasks in database:")
            for doc in all_docs:
                self.logger.debug(f"  - task_id: {doc.get('task_id')}, user_id: {doc.get('user_id')} (类型: {type(doc.get('user_id'))}), task_type: {doc.get('task_type')}, status: {doc.get('status')}")

        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)

        tasks = []
        async for doc in cursor:
            tasks.append(UnifiedAnalysisTask(**doc))

        self.logger.info(f"📋 返回任务数量: {len(tasks)}")
        return tasks

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel task

        Args:
            task_id: Task ID

        Returns:
            Is the cancellation successful?
        """
        result = await self.collection.update_one(
            {"task_id": task_id, "status": {"$in": [AnalysisStatus.PENDING, AnalysisStatus.PROCESSING, AnalysisStatus.SUSPENDED]}},
            {"$set": {"status": AnalysisStatus.CANCELLED, "completed_at": now_tz()}}
        )

        if result.modified_count > 0:
            self.logger.info(f"✅ 任务已取消: {task_id}")
        else:
            self.logger.warning(f"⚠️ Task cannot be canceled (may be completed or does not exist): {task_id}")

        return result.modified_count > 0

    async def resume_task(self, task_id: str) -> bool:
        """Resume a suspended task

        Args:
            task_id: Task ID

        Returns:
            Is the recovery successful?
        """
        from app.services.queue_service import get_queue_service

        # Get tasks
        task = await self.get_task(task_id)
        if not task:
            self.logger.warning(f"⚠️ 任务不存在: {task_id}")
            return False

        if task.status != AnalysisStatus.SUSPENDED:
            self.logger.warning(f"⚠️ 任务状态不是挂起，无法恢复: {task_id} (当前状态: {task.status})")
            return False

        # Update task status to pending
        result = await self.collection.update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "status": AnalysisStatus.PENDING,
                    "error_message": None,
                    "progress": 0
                },
                "$unset": {
                    "suspended_at": ""
                }
            }
        )

        if result.modified_count > 0:
            # rejoin queue
            try:
                queue_service = get_queue_service()
                await queue_service.enqueue_task(
                    user_id=str(task.user_id),
                    symbol=task.task_params.get("symbol", ""),
                    params=task.task_params,
                    task_id=task_id
                )
                self.logger.info(f"✅ Task has been resumed and requeued: {task_id}")
                return True
            except Exception as e:
                self.logger.error(f"❌ Task recovery failed (failed to join the queue): {task_id} - {e}")
                # rollback status
                await self.collection.update_one(
                    {"task_id": task_id},
                    {"$set": {"status": AnalysisStatus.SUSPENDED}}
                )
                return False
        else:
            self.logger.warning(f"⚠️ Task recovery failed (database update failed): {task_id}")
            return False

    async def _is_task_cancelled(self, task_id: str) -> bool:
        """Check if the task has been canceled

        Args:
            task_id: Task ID

        Returns:
            Has it been cancelled?
        """
        task_doc = await self.collection.find_one(
            {"task_id": task_id},
            {"status": 1}
        )

        if not task_doc:
            return False

        return task_doc.get("status") == AnalysisStatus.CANCELLED

    async def _save_task(self, task: UnifiedAnalysisTask) -> None:
        """Save task to database

        Args:
            task: Task object
        """
        doc = task.model_dump(by_alias=True, mode='python')

        # Make sure user_id is of type ObjectId, not a string
        if 'user_id' in doc and isinstance(doc['user_id'], str):
            from bson import ObjectId
            doc['user_id'] = ObjectId(doc['user_id'])
            self.logger.debug(f"🔄 Convert user_id from string to ObjectId: {doc['user_id']}")

        self.logger.debug(f"💾 保存任务文档: user_id={doc.get('user_id')} (类型: {type(doc.get('user_id'))})")

        await self.collection.insert_one(doc)
        self.logger.debug(f"💾 任务已保存: {task.task_id}")

    def _format_analysis_result(self, raw_result: Dict[str, Any], task: UnifiedAnalysisTask) -> Dict[str, Any]:
        """Format analysis results to ensure all fields required by the front end are included

        Args:
            raw_result: Raw results returned by the workflow engine
            task: Task object

        Returns:
            Formatted result
        """
        import uuid
        from datetime import datetime
        import json
        import re

        # 🔑 Key: Extract structured decisions from action_advice first (v2.0 engine)
        # action_advice is the output of ActionAdvisorV2 and contains research observations and reasoning
        # final_trade_decision is the output of RiskManagerV2 and contains the complete risk assessment report (should not be used for reasoning)
        action_advice = raw_result.get("action_advice", "")
        final_trade_decision = raw_result.get("final_trade_decision", "")
        final_decision = raw_result.get("final_decision", {})
        
        self.logger.info(f"🔍 [TaskAnalysisService] ========== Extract decision information ==========")
        self.logger.info(f"🔍 [TaskAnalysisService] action_advice 类型: {type(action_advice)}, 长度: {len(str(action_advice)) if action_advice else 0}")
        self.logger.info(f"🔍 [TaskAnalysisService] final_trade_decision 类型: {type(final_trade_decision)}, 长度: {len(str(final_trade_decision)) if final_trade_decision else 0}")
        self.logger.info(f"🔍 [TaskAnalysisService] final_decision 类型: {type(final_decision)}, 字段: {list(final_decision.keys()) if isinstance(final_decision, dict) else 'N/A'}")

        decision_dict = None
        
        # 1. Prefer extracting from final_decision if present
        if isinstance(final_decision, dict) and final_decision:
            decision_dict = self._format_decision_dict(final_decision)
            self.logger.info(f"✅ [TaskAnalysisService] Extract decision from final_decision: action={decision_dict.get('action')}, target_price={decision_dict.get('target_price')}")
        
        # 2. If final_decision does not exist, try to extract it from action_advice
        if not decision_dict and action_advice:
            if isinstance(action_advice, dict):
                decision_dict = self._format_decision_dict(action_advice)
                self.logger.info(f"✅ [TaskAnalysisService] from action_advice (dictionary) Extract decisions: action={decision_dict.get('action')}, target_price={decision_dict.get('target_price')}, risk_score={decision_dict.get('risk_score')}")
            elif isinstance(action_advice, str) and action_advice.strip():
                # Try to parse JSON format action_advice
                import json
                try:
                    if "{" in action_advice or "```json" in action_advice:
                        json_str = action_advice
                        if "```json" in json_str:
                            json_start = json_str.find("```json") + 7
                            json_end = json_str.find("```", json_start)
                            if json_end > json_start:
                                json_str = json_str[json_start:json_end].strip()
                        if json_str.strip().startswith("{"):
                            action_advice_json = json.loads(json_str)
                            decision_dict = self._format_decision_dict(action_advice_json)
                            self.logger.info(f"✅ [TaskAnalysisService] from action_advice (JSON) Extract decisions: action={decision_dict.get('action')}, target_price={decision_dict.get('target_price')}, risk_score={decision_dict.get('risk_score')}")
                except Exception as e:
                    self.logger.warning(f"⚠️ [TaskAnalysisService] Parsing action_advice JSON failed: {e}")
                    # Downgrade: extract from text
                    decision_dict = self._extract_decision_from_text(action_advice)
                    self.logger.info(f"✅ [TaskAnalysisService] from action_advice (text) Extract decisions: action={decision_dict.get('action')}, target_price={decision_dict.get('target_price')}, risk_score={decision_dict.get('risk_score')}")
        
        # 🔥 If risk_score is not present in decision_dict, try to extract it from investment_plan
        if decision_dict and decision_dict.get('risk_score') is None:
            investment_plan = raw_result.get("investment_plan", {})
            if isinstance(investment_plan, dict):
                plan_risk_score = investment_plan.get("risk_score")
                if plan_risk_score is not None:
                    # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                    if isinstance(plan_risk_score, (int, float)) and plan_risk_score > 1:
                        plan_risk_score = plan_risk_score / 100.0
                    decision_dict['risk_score'] = plan_risk_score
                    self.logger.info(f"✅ [TaskAnalysisService] Extracted from investment_plan risk_score: {plan_risk_score}")
            elif isinstance(investment_plan, str):
                # If it is a string, try to parse JSON
                try:
                    import json
                    import re
                    if "```json" in investment_plan:
                        json_match = re.search(r'```json\s*(.*?)\s*```', investment_plan, re.DOTALL)
                        if json_match:
                            plan_json = json.loads(json_match.group(1))
                            plan_risk_score = plan_json.get("risk_score")
                            if plan_risk_score is not None:
                                # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                                if isinstance(plan_risk_score, (int, float)) and plan_risk_score > 1:
                                    plan_risk_score = plan_risk_score / 100.0
                                decision_dict['risk_score'] = plan_risk_score
                                self.logger.info(f"✅ [TaskAnalysisService] from investment_plan (JSON text) Extract risk_score: {plan_risk_score}")
                except Exception:
                    pass
        
        # 🔥 Prioritize extraction from final_trade_decision (final assessment result of risk assessor) risk_score
        # This is the final assessment from Risk Assessor (RiskManagerV2) and should be the most authoritative source of risk scores
        # 🔥🔥🔥 Note: risk_score is now in the final_trade_decision dictionary (added by risk_manager_v2.py)
        risk_score = None
        
        # Prefer extracting from final_trade_decision (if it is a dictionary)
        if isinstance(final_trade_decision, dict):
            risk_score = final_trade_decision.get("risk_score")
            if risk_score is not None:
                # Make sure risk_score is a float in the range 0-1
                if isinstance(risk_score, (int, float)):
                    if risk_score > 1:
                        risk_score = risk_score / 100.0
                    risk_score = float(risk_score)
                    self.logger.info(f"✅✅✅ [TaskAnalysisService] from final_trade_decision (risk assessor assessment) Extract risk_score: {risk_score}")
        
        # If not in final_trade_decision, try to extract from risk_debate_state.judge_decision (alternative)
        if risk_score is None:
            risk_debate_state = raw_result.get("risk_debate_state", {})
            if isinstance(risk_debate_state, dict):
                judge_decision_str = risk_debate_state.get("judge_decision", "")
                if judge_decision_str and isinstance(judge_decision_str, str):
                    try:
                        # Try to extract from JSON code block
                        json_match = re.search(r'```json\s*(.*?)\s*```', judge_decision_str, re.DOTALL)
                        if json_match:
                            judge_json = json.loads(json_match.group(1))
                            risk_score = judge_json.get("risk_score")
                            if risk_score is not None:
                                if isinstance(risk_score, (int, float)):
                                    if risk_score > 1:
                                        risk_score = risk_score / 100.0
                                    risk_score = float(risk_score)
                                self.logger.info(f"✅✅✅ [TaskAnalysisService] from risk_debate_state.judge_decision (JSON) Extract risk_score: {risk_score}")
                        elif judge_decision_str.strip().startswith("{"):
                            # Try to parse directly JSON
                            judge_json = json.loads(judge_decision_str)
                            risk_score = judge_json.get("risk_score")
                            if risk_score is not None:
                                if isinstance(risk_score, (int, float)):
                                    if risk_score > 1:
                                        risk_score = risk_score / 100.0
                                    risk_score = float(risk_score)
                                self.logger.info(f"✅✅✅ [TaskAnalysisService] from risk_debate_state.judge_decision (direct JSON) Extract risk_score: {risk_score}")
                    except (json.JSONDecodeError, Exception) as e:
                        self.logger.warning(f"⚠️ [TaskAnalysisService] Parsing risk_debate_state.judge_decision JSON failed: {e}")
        
        # If still not available, extract from risk_assessment
        if risk_score is None:
            risk_assessment = raw_result.get("risk_assessment", {})
            if isinstance(risk_assessment, dict):
                risk_score = risk_assessment.get("risk_score")
                if risk_score is not None:
                    self.logger.info(f"✅ [TaskAnalysisService] from risk_assessment (risk assessor assessment) Extract risk_score: {risk_score}")
            elif isinstance(risk_assessment, str):
                # If it is a string, try to parse JSON
                try:
                    if "```json" in risk_assessment:
                        json_match = re.search(r'```json\s*(.*?)\s*```', risk_assessment, re.DOTALL)
                        if json_match:
                            risk_json = json.loads(json_match.group(1))
                            risk_score = risk_json.get("risk_score")
                            if risk_score is not None:
                                self.logger.info(f"✅ [TaskAnalysisService] from risk_assessment (JSON text) Extract risk_score: {risk_score}")
                except Exception as e:
                    self.logger.warning(f"⚠️ [TaskAnalysisService] Parsing JSON from risk_assessment failed: {e}")
        
        # 3. If action_advice is not available, it will be extracted from final_trade_decision
        # 🔥 Important update: final_trade_decision is now a structured dictionary generated by RiskManagerV2, containing the complete reasoning
        if not decision_dict:
            if isinstance(final_trade_decision, dict):
                # 🔥 New logic: final_trade_decision is a comprehensive decision generated by RiskManagerV2, containing reasoning
                ftd_reasoning = final_trade_decision.get("reasoning", "")
                ftd_summary = final_trade_decision.get("summary", "")

                # If reasoning is available, use it; if not, use summary
                reasoning_to_use = ftd_reasoning if ftd_reasoning else ftd_summary
                if not reasoning_to_use:
                    reasoning_to_use = "暂无分析推理"

                # 🔥 Extract price_analysis_range (price range)
                price_analysis_range = final_trade_decision.get("price_analysis_range")
                # 🔥 Debug log: record the original value and type of price_analysis_range
                if price_analysis_range is not None:
                    self.logger.info(f"✅ [TaskAnalysisService] 从 final_trade_decision 提取 price_analysis_range: {price_analysis_range} (类型: {type(price_analysis_range)})")
                    # Make sure price_analysis_range is in array format
                    if isinstance(price_analysis_range, (list, tuple)):
                        if len(price_analysis_range) == 2:
                            self.logger.info(f"✅ [TaskAnalysisService] price_analysis_range is a valid interval format: [{price_analysis_range[0]}, {price_analysis_range[1]}]")
                        else:
                            self.logger.warning(f"⚠️ [TaskAnalysisService] price_analysis_range The array length is not 2: {price_analysis_range}")
                    elif isinstance(price_analysis_range, (int, float)):
                        self.logger.warning(f"⚠️ [TaskAnalysisService] price_analysis_range is a single value {price_analysis_range}, It should be in array format!")
                    else:
                        self.logger.warning(f"⚠️ [TaskAnalysisService] price_analysis_range Incorrect format: {type(price_analysis_range)} = {price_analysis_range}")
                
                # 🔥🔥🔥 Key: Extract risk_score from final_trade_decision (now risk_score has been added to the final_trade_decision dictionary)
                if risk_score is None:
                    risk_score = final_trade_decision.get("risk_score")
                    if risk_score is not None:
                        # Make sure risk_score is a float in the range 0-1
                        if isinstance(risk_score, (int, float)):
                            if risk_score > 1:
                                risk_score = risk_score / 100.0
                            risk_score = float(risk_score)
                        self.logger.info(f"✅✅✅ [TaskAnalysisService] Extracted from final_trade_decision risk_score: {risk_score}")
                
                # 🔥 If still not there, try to get it from investment_plan (as a safety net, but this is not a risk assessor's assessment)
                if risk_score is None:
                    investment_plan = raw_result.get("investment_plan", {})
                    if isinstance(investment_plan, dict):
                        plan_risk_score = investment_plan.get("risk_score")
                        if plan_risk_score is not None:
                            # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                            if isinstance(plan_risk_score, (int, float)) and plan_risk_score > 1:
                                plan_risk_score = plan_risk_score / 100.0
                            risk_score = plan_risk_score
                            self.logger.warning(f"⚠️ [TaskAnalysisService] from investment_plan (Assessment by research integrator, not risk assessor) Extract risk_score: {risk_score}")
                    elif isinstance(investment_plan, str):
                        # If it is a string, try to parse JSON
                        try:
                            import json
                            import re
                            if "```json" in investment_plan:
                                json_match = re.search(r'```json\s*(.*?)\s*```', investment_plan, re.DOTALL)
                                if json_match:
                                    plan_json = json.loads(json_match.group(1))
                                    plan_risk_score = plan_json.get("risk_score")
                                    if plan_risk_score is not None:
                                        # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                                        if isinstance(plan_risk_score, (int, float)) and plan_risk_score > 1:
                                            plan_risk_score = plan_risk_score / 100.0
                                        risk_score = plan_risk_score
                                        self.logger.warning(f"⚠️ [TaskAnalysisService] from investment_plan (JSON Text, Research Integrator Assessment, Non-Risk Assessor) Extract risk_score: {risk_score}")
                        except Exception as e:
                            self.logger.warning(f"⚠️ [TaskAnalysisService] Failed to extract risk_score from investment_plan: {e}")
                
                # If still not available, use default value
                if risk_score is None:
                    risk_score = 0.5
                    self.logger.warning(f"⚠️ [TaskAnalysisService] risk_score not found, using default value 0.5")
                
                decision_dict = {
                    "action": final_trade_decision.get("action") or final_trade_decision.get("analysis_view", "中性"),
                    "target_price": final_trade_decision.get("target_price"),
                    "price_analysis_range": price_analysis_range,  # 🔥 New: price range
                    "stop_loss": final_trade_decision.get("stop_loss") or final_trade_decision.get("risk_control_reference"),
                    "position_ratio": final_trade_decision.get("position_ratio") or final_trade_decision.get("risk_exposure_ratio", "5%"),
                    "confidence": final_trade_decision.get("confidence", 50),
                    "risk_score": risk_score,  # 🔥 Fix: use extracted risk_score instead of default
                    "reasoning": reasoning_to_use,  # 🔥 Synthesis generated using RiskManagerV2 reasoning
                    "summary": ftd_summary,
                    "risk_warning": final_trade_decision.get("risk_warning", "")
                }
                self.logger.info(f"✅ [TaskAnalysisService] from final_trade_decision (dictionary) Extract decisions: action={decision_dict.get('action')}, target_price={decision_dict.get('target_price')}, risk_score={decision_dict.get('risk_score')}, reasoning length={len(reasoning_to_use)}")
            elif isinstance(final_trade_decision, str) and final_trade_decision.strip():
                # If it is a string, extract all fields (including reasoning)
                temp_dict = self._extract_decision_from_text(final_trade_decision)
                decision_dict = {
                    "action": temp_dict.get("action", "中性"),
                    "target_price": temp_dict.get("target_price"),
                    "price_analysis_range": temp_dict.get("price_analysis_range"),  # 🔥 New: price range
                    "confidence": temp_dict.get("confidence", 0.5),
                    "risk_score": temp_dict.get("risk_score", 0.5),
                    "reasoning": temp_dict.get("reasoning", "暂无分析推理")
                }
                self.logger.info(f"✅ [TaskAnalysisService] from final_trade_decision (text) Extract decisions: action={decision_dict.get('action')}, target_price={decision_dict.get('target_price')}, risk_score={decision_dict.get('risk_score')}, reasoning length={len(decision_dict.get('reasoning', ''))}")
        
        # 🔥 If there is no risk_score in decision_dict, it will be extracted from final_trade_decision or risk_assessment (risk assessor assessment) first.
        if decision_dict and decision_dict.get('risk_score') is None:
            # 🔥🔥🔥 Highest priority: extracted from final_trade_decision (if it is a dictionary and contains risk_score)
            if isinstance(final_trade_decision, dict):
                ftd_risk_score = final_trade_decision.get("risk_score")
                if ftd_risk_score is not None:
                    # Make sure risk_score is a float in the range 0-1
                    if isinstance(ftd_risk_score, (int, float)):
                        if ftd_risk_score > 1:
                            ftd_risk_score = ftd_risk_score / 100.0
                        decision_dict['risk_score'] = float(ftd_risk_score)
                        self.logger.info(f"✅✅✅ [TaskAnalysisService] Assign risk_score in final_trade_decision to decision_dict: {decision_dict['risk_score']}")
            # Second: use the risk_score extracted earlier (from risk_assessment)
            if decision_dict.get('risk_score') is None and risk_score is not None:
                decision_dict['risk_score'] = risk_score
                self.logger.info(f"✅ [TaskAnalysisService] Assign risk_score in risk_assessment to decision_dict: {risk_score}")
            # Finally: Extract from investment_plan (as a safety net)
            if decision_dict.get('risk_score') is None:
                # If you haven't already, try extracting it from investment_plan (as a fallback, but this is not a risk assessor's assessment)
                investment_plan = raw_result.get("investment_plan", {})
                if isinstance(investment_plan, dict):
                    plan_risk_score = investment_plan.get("risk_score")
                    if plan_risk_score is not None:
                        # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                        if isinstance(plan_risk_score, (int, float)) and plan_risk_score > 1:
                            plan_risk_score = plan_risk_score / 100.0
                        decision_dict['risk_score'] = plan_risk_score
                        self.logger.warning(f"⚠️ [TaskAnalysisService] from investment_plan (Assessment by research integrator, not risk assessor) Extract risk_score: {plan_risk_score}")
                elif isinstance(investment_plan, str):
                    # If it is a string, try to parse JSON
                    try:
                        import json
                        import re
                        if "```json" in investment_plan:
                            json_match = re.search(r'```json\s*(.*?)\s*```', investment_plan, re.DOTALL)
                            if json_match:
                                plan_json = json.loads(json_match.group(1))
                                plan_risk_score = plan_json.get("risk_score")
                                if plan_risk_score is not None:
                                    # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                                    if isinstance(plan_risk_score, (int, float)) and plan_risk_score > 1:
                                        plan_risk_score = plan_risk_score / 100.0
                                    decision_dict['risk_score'] = plan_risk_score
                                    self.logger.warning(f"⚠️ [TaskAnalysisService] from investment_plan (JSON Text, Research Integrator Assessment, Non-Risk Assessor) Extract risk_score: {plan_risk_score}")
                    except Exception as e:
                        self.logger.warning(f"⚠️ [TaskAnalysisService] Failed to extract risk_score from investment_plan: {e}")
        
        # 4. If neither, use default value
        if not decision_dict:
            decision_dict = {
                "action": "中性",
                "target_price": None,
                "price_analysis_range": None,  # 🔥 New: price range
                "confidence": 0.5,
                "risk_score": 0.5,
                "reasoning": "暂无分析推理"
            }
            self.logger.warning(f"⚠️ [TaskAnalysisService] Decision information not found, use default decision")
        
        self.logger.info(f"🔍 [TaskAnalysisService] 最终 decision_dict.reasoning 长度: {len(decision_dict.get('reasoning', ''))}, 内容: {decision_dict.get('reasoning', '')[:200]}")

        # 🔥 Import JSON conversion function (import inside the function to avoid circular dependencies)
        from app.utils.report_formatter import _convert_json_to_markdown
        import json
        import re

        # 🔥 Critical fix: if decision_dict.reasoning is "No analytical reasoning yet", Try to extract from risk_assessment or investment_plan
        # ⚠️ NOTE: This must be done before fetching the report as fetching the report converts the JSON to Markdown
        if decision_dict and decision_dict.get('reasoning') == "暂无分析推理":
            self.logger.info(f"🔍 [TaskAnalysisService] reasoning Empty, try to extract from risk_assessment or investment_plan")

            # 1. Prioritize extraction from risk_assessment (comprehensive risk assessment reasoning)
            risk_assessment_raw = raw_result.get("risk_assessment", "")
            self.logger.info(f"🔍 [TaskAnalysisService] risk_assessment_raw 类型: {type(risk_assessment_raw)}, 长度: {len(str(risk_assessment_raw)) if risk_assessment_raw else 0}")
            if risk_assessment_raw:
                try:
                    # 🔥 Fix: If it is a dictionary, extract the content field first
                    if isinstance(risk_assessment_raw, dict):
                        risk_assessment_str = risk_assessment_raw.get("content", "")
                        self.logger.info(f"🔍 [TaskAnalysisService] risk_assessment Is a dictionary, extract the content field, length: {len(risk_assessment_str) if risk_assessment_str else 0}")
                    else:
                        risk_assessment_str = str(risk_assessment_raw)

                    json_obj = None

                    # 1. Try to extract JSON code block
                    if "```json" in risk_assessment_str:
                        json_match = re.search(r'```json\s*(.*?)\s*```', risk_assessment_str, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(1).strip()
                            json_obj = json.loads(json_str)
                    # 2. Try to parse directly JSON
                    elif risk_assessment_str.strip().startswith("{"):
                        json_obj = json.loads(risk_assessment_str)

                    # If parsing is successful, extract reasoning
                    if json_obj and isinstance(json_obj, dict):
                        reasoning = json_obj.get("reasoning", "")
                        self.logger.info(f"🔍 [TaskAnalysisService] risk_assessment JSON Parsed successfully, reasoning length: {len(reasoning) if reasoning else 0}")
                        if reasoning and len(reasoning.strip()) > 10:
                            decision_dict['reasoning'] = reasoning.strip()
                            self.logger.info(f"✅ [TaskAnalysisService] 从 risk_assessment 提取 reasoning: {len(reasoning.strip())}字符")
                        else:
                            self.logger.warning(f"⚠️ [TaskAnalysisService] risk_assessment reasoning in is empty or too short")
                    else:
                        self.logger.warning(f"⚠️ [TaskAnalysisService] risk_assessment It is not a dictionary or empty after parsing")
                except Exception as e:
                    self.logger.warning(f"⚠️ [TaskAnalysisService] Failed to extract reasoning from risk_assessment: {e}")
            else:
                self.logger.warning(f"⚠️ [TaskAnalysisService] risk_assessment_raw is empty")

            # 2. If risk_assessment does not have reasoning, it is extracted from investment_plan
            if decision_dict.get('reasoning') == "暂无分析推理":
                self.logger.info(f"🔍 [TaskAnalysisService] risk_assessment Without reasoning, try to extract from investment_plan")
                investment_plan_raw = raw_result.get("investment_plan", "")
            self.logger.info(f"🔍 [TaskAnalysisService] investment_plan_raw 类型: {type(investment_plan_raw)}, 长度: {len(str(investment_plan_raw)) if investment_plan_raw else 0}")
            if investment_plan_raw:
                try:
                    # 🔥 Fix: If it is a dictionary, extract the content field first
                    if isinstance(investment_plan_raw, dict):
                        investment_plan_str = investment_plan_raw.get("content", "")
                        self.logger.info(f"🔍 [TaskAnalysisService] investment_plan Is a dictionary, extract the content field, length: {len(investment_plan_str) if investment_plan_str else 0}")
                    else:
                        investment_plan_str = str(investment_plan_raw)

                    json_obj = None

                    # 1. Try to extract JSON code block
                    if "```json" in investment_plan_str:
                        json_match = re.search(r'```json\s*(.*?)\s*```', investment_plan_str, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(1).strip()
                            json_obj = json.loads(json_str)
                    # 2. Try to parse directly JSON
                    elif investment_plan_str.strip().startswith("{"):
                        json_obj = json.loads(investment_plan_str)
                    
                    # If parsing is successful, extract reasoning
                    if json_obj and isinstance(json_obj, dict):
                        reasoning = json_obj.get("reasoning", "")
                        self.logger.info(f"🔍 [TaskAnalysisService] investment_plan JSON Parsed successfully, reasoning length: {len(reasoning) if reasoning else 0}")
                        if reasoning and len(reasoning.strip()) > 10:
                            decision_dict['reasoning'] = reasoning.strip()
                            self.logger.info(f"✅ [TaskAnalysisService] 从 investment_plan 提取 reasoning: {len(reasoning.strip())}字符")
                        else:
                            self.logger.warning(f"⚠️ [TaskAnalysisService] investment_plan reasoning in is empty or too short")
                    else:
                        self.logger.warning(f"⚠️ [TaskAnalysisService] investment_plan It is not a dictionary or empty after parsing")
                except Exception as e:
                    self.logger.warning(f"⚠️ [TaskAnalysisService] Failed to extract reasoning from investment_plan: {e}")
            else:
                self.logger.warning(f"⚠️ [TaskAnalysisService] investment_plan_raw is empty")
            
            # 🔥 If investment_plan has no reasoning, try to extract from final_trade_decision (as an alternative)
            if decision_dict.get('reasoning') == "暂无分析推理" and final_trade_decision:
                self.logger.info(f"🔍 [TaskAnalysisService] investment_plan Without reasoning, try to extract from final_trade_decision")
                try:
                    final_trade_str = str(final_trade_decision)
                    json_obj = None
                    
                    # 1. Try to extract JSON code block
                    if "```json" in final_trade_str:
                        json_match = re.search(r'```json\s*(.*?)\s*```', final_trade_str, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(1).strip()
                            json_obj = json.loads(json_str)
                    # 2. Try to parse directly JSON
                    elif final_trade_str.strip().startswith("{"):
                        json_obj = json.loads(final_trade_str)
                    
                    # If the parsing is successful, extract reasoning (although final_trade_decision is a risk assessment, its reasoning can be used as the basis for analysis)
                    if json_obj and isinstance(json_obj, dict):
                        reasoning = json_obj.get("reasoning", "")
                        self.logger.info(f"🔍 [TaskAnalysisService] final_trade_decision JSON Parsed successfully, reasoning length: {len(reasoning) if reasoning else 0}")
                        if reasoning and len(reasoning.strip()) > 10:
                            decision_dict['reasoning'] = reasoning.strip()
                            self.logger.info(f"✅ [TaskAnalysisService] 从 final_trade_decision 提取 reasoning (备选): {len(reasoning.strip())}字符")
                        else:
                            self.logger.warning(f"⚠️ [TaskAnalysisService] final_trade_decision reasoning in is empty or too short")
                    else:
                        self.logger.warning(f"⚠️ [TaskAnalysisService] final_trade_decision It is not a dictionary or empty after parsing")
                except Exception as e:
                    self.logger.warning(f"⚠️ [TaskAnalysisService] Failed to extract reasoning from final_trade_decision: {e}")
            else:
                if not final_trade_decision:
                    self.logger.warning(f"⚠️ [TaskAnalysisService] final_trade_decision Empty and cannot be extracted reasoning")
        
        # 🔥 Record the final reasoning again (after extraction)
        self.logger.info(f"🔍 [TaskAnalysisService] 提取后 decision_dict.reasoning 长度: {len(decision_dict.get('reasoning', ''))}, 内容: {decision_dict.get('reasoning', '')[:200]}")

        # Withdraw investment plan
        investment_plan = raw_result.get("trader_investment_plan") or raw_result.get("investment_plan", "")
        if isinstance(investment_plan, dict):
            investment_plan_text = investment_plan.get("content", str(investment_plan))
        else:
            investment_plan_text = str(investment_plan) if investment_plan else ""

        # 🔑 Key: Build the reports dictionary (exactly the old way)
        reports = {}
        
        # 🔑 Helper function for extracting text (consistent with old process)
        def _extract_text(v, field_name: str = ""):
            """从各种格式中提取文本内容"""
            if isinstance(v, str):
                return v
            if isinstance(v, dict):
                # 🔥 Special processing: final_trade_decision If it is a dictionary and has a content field, content (formatted Markdown) is returned directly
                if field_name == "final_trade_decision" and v.get("content"):
                    content = v.get("content")
                    if isinstance(content, str) and content.strip():
                        return content
                # 🔥 If final_trade_decision does not have a content field but has an action field, convert it to a JSON string
                # In this way, subsequent _convert_json_to_markdown can be processed correctly
                if field_name == "final_trade_decision" and v.get("action"):
                    import json
                    return json.dumps(v, ensure_ascii=False, indent=2)
                # Try to extract text field from dictionary
                for k in ("content", "markdown", "text", "message", "report"):
                    x = v.get(k)
                    if isinstance(x, str) and x.strip():
                        return x
            return ""

        # 🔑 Step 1: Dynamically extract report fields from structured_reports generated by the engine
        # engine Filtered by show_in_reports, reused directly here, no hard-coded list is maintained.
        structured_reports = raw_result.get("structured_reports", {})
        if structured_reports and isinstance(structured_reports, dict):
            for field, entry in structured_reports.items():
                if isinstance(entry, dict) and entry.get("success") and entry.get("content"):
                    content = entry["content"]
                    if isinstance(content, str) and len(content.strip()) > 5:
                        reports[field] = content.strip()
                        self.logger.info(f"📊 [REPORTS] 从 structured_reports 提取: {field} - 长度: {len(content.strip())}")
        else:
            # Fallback: Extract fields in report_manifest from raw_result top level
            manifest = raw_result.get("report_manifest", [])
            if manifest:
                for m in manifest:
                    field = m.get("field")
                    if field and field not in reports:
                        content = _extract_text(raw_result.get(field), field)
                        if content and isinstance(content, str) and len(content.strip()) > 5:
                            reports[field] = content.strip()
                            self.logger.info(f"📊 [REPORTS] 从 manifest 提取: {field} - 长度: {len(content.strip())}")

        # 🔑 Step 2: Handle research team debate status (dictionary type) - split into independent sub-reports (consistent with old process)
        # 🔥 Note: If the top level already has bull_report/bear_report, the top level one will be used first; otherwise, it will be extracted from investment_debate_state
        investment_debate = raw_result.get("investment_debate_state", {})
        if investment_debate and isinstance(investment_debate, dict):
            # 1. Long researcher report (extracted from investment_debate_state if not available at the top level)
            if "bull_researcher" not in reports:
                bull_history = _extract_text(investment_debate.get("bull_history", ""))
                if bull_history and len(bull_history.strip()) > 5:
                    reports["bull_researcher"] = bull_history.strip()
                    self.logger.info(f"📊 [REPORTS] Extract report: bull_researcher (from investment_debate_state.bull_history) - length: {len(bull_history.strip())}")

            # 2. Short researcher report (only extracted from investment_debate_state if the top level is not available)
            if "bear_researcher" not in reports:
                bear_history = _extract_text(investment_debate.get("bear_history", ""))
                if bear_history and len(bear_history.strip()) > 5:
                    reports["bear_researcher"] = bear_history.strip()
                    self.logger.info(f"📊 [REPORTS] Extract report: bear_researcher (from investment_debate_state.bear_history) - length: {len(bear_history.strip())}")

            # 3. Research Integrator Analysis Report
            judge_decision = _extract_text(investment_debate.get("judge_decision", ""))
            if judge_decision and len(judge_decision.strip()) > 5:
                # 🔥 New: If in JSON format, convert to Markdown
                markdown_content = _convert_json_to_markdown(judge_decision.strip(), "investment")
                reports["research_team_decision"] = markdown_content
                self.logger.info(f"📊 [REPORTS] Extract report: research_team_decision - length: {len(markdown_content)} (Converted JSON->Markdown)")

        # 🔑 Step 3: Handle risk management team debate status (dictionary type) - split into independent sub-reports (consistent with old process)
        # 🔥 Also check if the top level has risky_opinion, safe_opinion, neutral_opinion etc fields
        risk_debate = raw_result.get("risk_debate_state", {})
        
        # 🔥 Alternative field mapping (v2.0 workflow may store reports at the top level)
        risk_alternative_fields = {
            "risky_analyst": ["risky_opinion", "risky_history"],
            "safe_analyst": ["safe_opinion", "safe_history"],
            "neutral_analyst": ["neutral_opinion", "neutral_history"],
        }
        
        # Extract from the top level first
        for report_key, alt_fields in risk_alternative_fields.items():
            if report_key not in reports:
                for alt_field in alt_fields:
                    content_raw = raw_result.get(alt_field, "")
                    content = _extract_text(content_raw)
                    if content and isinstance(content, str) and len(content.strip()) > 5:
                        reports[report_key] = content.strip()
                        self.logger.info(f"📊 [REPORTS] 提取报告: {report_key} (来自顶层 {alt_field}) - 长度: {len(content.strip())}")
                        break
        
        # Then extract from risk_debate_state (if the top level doesn't have one)
        if risk_debate and isinstance(risk_debate, dict):
            # 1. High Resilience Scenario Analyst Report
            if "risky_analyst" not in reports:
                risky_history = _extract_text(risk_debate.get("risky_history", ""))
                if risky_history and len(risky_history.strip()) > 5:
                    reports["risky_analyst"] = risky_history.strip()
                    self.logger.info(f"📊 [REPORTS] Extract report: risky_analyst (from risk_debate_state.risky_history) - length: {len(risky_history.strip())}")

            # 2. Defense Scenario Analyst Report
            if "safe_analyst" not in reports:
                safe_history = _extract_text(risk_debate.get("safe_history", ""))
                if safe_history and len(safe_history.strip()) > 5:
                    reports["safe_analyst"] = safe_history.strip()
                    self.logger.info(f"📊 [REPORTS] Extract report: safe_analyst (from risk_debate_state.safe_history) - length: {len(safe_history.strip())}")

            # 3. Neutral analyst report
            if "neutral_analyst" not in reports:
                neutral_history = _extract_text(risk_debate.get("neutral_history", ""))
                if neutral_history and len(neutral_history.strip()) > 5:
                    reports["neutral_analyst"] = neutral_history.strip()
                    self.logger.info(f"📊 [REPORTS] Extract report: neutral_analyst (from risk_debate_state.neutral_history) - length: {len(neutral_history.strip())}")

            # 4. Risk Assessor Decision Report
            judge_decision = _extract_text(risk_debate.get("judge_decision", ""))
            if judge_decision and len(judge_decision.strip()) > 5:
                # 🔥 New: If in JSON format, convert to Markdown
                markdown_content = _convert_json_to_markdown(judge_decision.strip(), "risk")
                reports["risk_management_decision"] = markdown_content
                self.logger.info(f"📊 [REPORTS] Extract report: risk_management_decision - length: {len(markdown_content)} (Converted JSON->Markdown)")

        # 🔥 Generate summaries and recommendations (consistent with old engine)
        # summary (Analysis overview): Prioritize extracting the complete summary from the investment_plan or final_trade_decision returned by LLM, without intercepting
        # recommendation (Analytical view): generated based on action, price_range and short inference summary
        # decision.reasoning (Analysis basis): extracted from decision_dict.reasoning (should not be extracted from final_trade_decision)
        
        self.logger.info(f"🔍 [TaskAnalysisService] ========== Generate summary and recommendation ==========")
        
        # 1. Generate summary (analysis overview)- 🔥🔥🔥 Highest priority: Extract the complete investment_plan from the LLM return summary
        summary = ""
        
        # 1.1 Preferentially extract the complete summary
        investment_plan_raw = raw_result.get("investment_plan", "")
        if investment_plan_raw:
            try:
                # If it is a dictionary, get it directly summary
                if isinstance(investment_plan_raw, dict):
                    plan_summary = investment_plan_raw.get("summary", "")
                    if plan_summary and isinstance(plan_summary, str) and len(plan_summary.strip()) > 10:
                        summary = plan_summary.strip()
                        self.logger.info(f"✅✅✅ [TaskAnalysisService] 从 investment_plan (字典) 提取完整 summary: {len(summary)}字符")
                # If it is a string, try to parse JSON
                elif isinstance(investment_plan_raw, str):
                    investment_plan_str = investment_plan_raw.strip()
                    json_obj = None
                    # Try to extract JSON code block
                    if "```json" in investment_plan_str:
                        json_match = re.search(r'```json\s*(.*?)\s*```', investment_plan_str, re.DOTALL)
                        if json_match:
                            json_obj = json.loads(json_match.group(1))
                    # Try to parse directly JSON
                    elif investment_plan_str.startswith("{"):
                        json_obj = json.loads(investment_plan_str)
                    
                    # If parsing is successful, extract summary
                    if json_obj and isinstance(json_obj, dict):
                        plan_summary = json_obj.get("summary", "")
                        if plan_summary and isinstance(plan_summary, str) and len(plan_summary.strip()) > 10:
                            summary = plan_summary.strip()
                            self.logger.info(f"✅✅✅ [TaskAnalysisService] 从 investment_plan (JSON字符串) 提取完整 summary: {len(summary)}字符")
            except (json.JSONDecodeError, Exception) as e:
                self.logger.warning(f"⚠️ [TaskAnalysisService] Failed to extract summary from investment_plan: {e}")
        
        # 1.2 If not present in investment_plan, extract the complete summary
        if not summary:
            if isinstance(final_trade_decision, dict):
                ftd_summary = final_trade_decision.get("summary", "")
                if ftd_summary and isinstance(ftd_summary, str) and len(ftd_summary.strip()) > 10:
                    summary = ftd_summary.strip()
                    self.logger.info(f"✅✅✅ [TaskAnalysisService] 从 final_trade_decision (字典) 提取完整 summary: {len(summary)}字符")
        
        # 1.3 If it still doesn't exist, extract it from final_trade_decision in reports (do not intercept, use the complete content)
        if not summary:
            if reports.get("final_trade_decision"):
                final_trade_content = reports["final_trade_decision"]
                if isinstance(final_trade_content, str) and len(final_trade_content.strip()) > 50:
                    # 🔥 No truncation, use full content (remove Markdown tags)
                    summary = final_trade_content.replace('#', '').replace('*', '').strip()
                    self.logger.info(f"✅ [TaskAnalysisService] 从 reports.final_trade_decision 提取完整 summary: {len(summary)}字符")
        
        # 1.4 If still not available, extract from other reports (without interception)
        if not summary:
            for report_name in ['trader_investment_plan', 'research_team_decision', 'market_report']:
                if report_name in reports:
                    content = reports[report_name]
                    if isinstance(content, str) and len(content.strip()) > 100:
                        # 🔥 No truncation, use full content (remove Markdown tags)
                        summary = content.replace('#', '').replace('*', '').strip()
                        self.logger.info(f"✅ [TaskAnalysisService] 从 {report_name} 提取完整 summary: {len(summary)}字符")
                        break
        
        # 1.5 Last resort
        if not summary:
            summary = f"对{task.task_params.get('symbol', '股票')}的分析已完成，请查看详细报告。"
            self.logger.warning(f"⚠️ [TaskAnalysisService] Use backup summary")
        
        # 4. Generate recommendations (analysis opinions) - based on action, price_range and short reasoning summary
        # 🔥 Compliance modification: use new terms, format decision_dict first to ensure action is a compliant term
        temp_formatted_decision = self._format_decision_dict(decision_dict)
        action = temp_formatted_decision.get('action', '中性')
        target_price = temp_formatted_decision.get('target_price')
        reasoning = temp_formatted_decision.get('reasoning', '')

        # Build recommendations (excluding specific prices and research observations)
        recommendation_parts = []

        # Contains only analytical opinions and does not include specific prices
        if action and action != '中性':
            recommendation_parts.append(f"Analysis point of view:{action}")

        # 🔥 If reasoning is short (<100 characters) before adding it to the recommendation to avoid duplication
        if reasoning and len(reasoning) < 100 and reasoning != "暂无分析推理":
            recommendation_parts.append(f"Analysis basis:{reasoning}")
        elif reasoning and reasoning != "暂无分析推理":
            # If reasoning is longer, only the first 50 characters are extracted
            short_reasoning = reasoning[:50] + "..." if len(reasoning) > 50 else reasoning
            recommendation_parts.append(f"Analysis basis:{short_reasoning}")

        recommendation = "；".join(recommendation_parts) if recommendation_parts else "Please refer to the detailed analysis report."

        if not recommendation or recommendation == "Analytical opinion: Neutral":
            recommendation = "Please refer to the detailed analysis report."
            self.logger.warning(f"⚠️ [TaskAnalysisService] Use backup recommendation")
        
        self.logger.info(f"🔍 [TaskAnalysisService] summary 长度: {len(summary)}, 内容: {summary[:200]}")
        self.logger.info(f"🔍 [TaskAnalysisService] recommendation 长度: {len(recommendation)}, 内容: {recommendation[:200]}")
        self.logger.info(f"🔍 [TaskAnalysisService] decision.reasoning 长度: {len(reasoning)}, 内容: {reasoning[:200]}")

        # Calculate risk level (based on risk_score)
        risk_score = decision_dict.get("risk_score", 0.5)
        if risk_score < 0.3:
            risk_level = "低"
        elif risk_score < 0.6:
            risk_level = "中等"
        else:
            risk_level = "高"

        # 🔑 Get model information
        quick_model = task.task_params.get("quick_analysis_model", "Unknown")
        deep_model = task.task_params.get("deep_analysis_model", "Unknown")
        model_info = f"{quick_model}/{deep_model}"

        # 🔥 Extract key points (from reasoning or summary)
        key_points = []
        if reasoning and reasoning != "暂无分析推理":
            # Try to extract key points from reasoning (split by rows)
            lines = [line.strip() for line in reasoning.split('\n') if line.strip()]
            # Filter out lines that are too short (<10 characters) and the title line (ending with#beginning)
            key_points = [
                line for line in lines
                if len(line) >= 10 and not line.startswith('#') and not line.startswith('*')
            ][:5]  # Take up to 5 key points
            self.logger.info(f"✅ [TaskAnalysisService] 从 reasoning 提取 {len(key_points)} 个关键要点")

        # If reasoning has no key points, try to extract them from summary
        if not key_points and summary:
            lines = [line.strip() for line in summary.split('\n') if line.strip()]
            key_points = [
                line for line in lines
                if len(line) >= 10 and not line.startswith('#') and not line.startswith('*')
            ][:5]
            self.logger.info(f"✅ [TaskAnalysisService] 从 summary 提取 {len(key_points)} 个关键要点")

        # 🔥 Filter out key points containing JSON field names or sensitive terms
        filtered_key_points = []
        for kp in key_points:
            # Skip lines containing JSON field names
            if any(field in kp for field in ['"analysis_view"', '"action"', '"confidence"', '"target_price"', '```json', '```']):
                continue
            # Skip lines containing sensitive terms
            if any(term in kp for term in ['买入', '卖出', '目标价', '止损', '止盈', '仓位']):
                continue
            filtered_key_points.append(kp)

        key_points = filtered_key_points[:5]  # Keep up to 5
        self.logger.info(f"✅ [TaskAnalysisService] 过滤后保留 {len(key_points)} 个关键要点")

        # 🔥🔥🔥 Final check: Make sure decision_dict contains risk_score extracted from final_trade_decision (highest priority)
        if decision_dict and decision_dict.get('risk_score') is None:
            # Try extracting from final_trade_decision again
            if isinstance(final_trade_decision, dict):
                ftd_risk_score = final_trade_decision.get("risk_score")
                if ftd_risk_score is not None:
                    # Make sure risk_score is a float in the range 0-1
                    if isinstance(ftd_risk_score, (int, float)):
                        if ftd_risk_score > 1:
                            ftd_risk_score = ftd_risk_score / 100.0
                        decision_dict['risk_score'] = float(ftd_risk_score)
                        self.logger.info(f"✅✅✅ [TaskAnalysisService] Final check: assign risk_score in final_trade_decision to decision_dict: {decision_dict['risk_score']}")

        # 🔥 Format decision_dict (map old terms to compliant terms)
        formatted_decision = self._format_decision_dict(decision_dict)
        self.logger.info(f"🔍 [TaskAnalysisService] decision Format: {decision_dict.get('action')} -> {formatted_decision.get('action')}")
        self.logger.info(f"🔍 [TaskAnalysisService] decision.risk_score = {formatted_decision.get('risk_score')}")

        # Build formatted results (basic fields, excluding state and detailed_analysis)
        formatted_result = {
            "analysis_id": str(uuid.uuid4()),
            "stock_symbol": task.task_params.get("symbol") or task.task_params.get("stock_code"),
            "stock_code": task.task_params.get("stock_code") or task.task_params.get("symbol"),
            "analysis_date": task.task_params.get("analysis_date") or datetime.now().strftime("%Y-%m-%d"),
            "summary": summary or "分析完成",
            "recommendation": recommendation or "请查看详细报告",
            "confidence_score": formatted_decision.get("confidence", 0.5),
            "risk_level": risk_level,
            "key_points": key_points,  # 🔥 Key takeaways (extracted from reasoning or summary)
            "execution_time": task.execution_time or 0,
            "tokens_used": raw_result.get("tokens_used", 0),
            "analysts": task.task_params.get("selected_analysts", []),
            "research_depth": task.task_params.get("research_depth", "快速"),
            "reports": reports,
            "decision": formatted_decision,
            "model_info": model_info,
            "quick_model": quick_model,
            "deep_model": deep_model,
        }

        # Transparently transmit the report_manifest (customized workflow output description) generated by the workflow engine
        if raw_result.get("report_manifest"):
            formatted_result["report_manifest"] = raw_result["report_manifest"]

        # 🔥 Debug log: print the complete contents of the decision object
        self.logger.info(f"✅ 格式化结果完成: {len(reports)} 个报告")
        self.logger.info(f"🔍 [TaskAnalysisService] decision Object complete content: {formatted_decision}")
        self.logger.info(f"🔍 [TaskAnalysisService] decision.price_analysis_range = {formatted_decision.get('price_analysis_range')}")
        self.logger.info(f"🔍 [TaskAnalysisService] decision.risk_score = {formatted_decision.get('risk_score')}")
        return formatted_result

    def _format_decision_dict(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Format decision dictionary

        Args:
            decision: original decision dictionary

        Returns:
            Formatted decision dictionary
        """
        # Handle validation price (history field target_price is for compatibility only)
        target_price = decision.get('target_price')
        if target_price is not None and target_price != 'N/A':
            try:
                if isinstance(target_price, str):
                    # Remove currency symbols and spaces
                    clean_price = target_price.replace('$', '').replace('¥', '').replace('￥', '').strip()
                    target_price = float(clean_price) if clean_price and clean_price != 'None' else None
                elif isinstance(target_price, (int, float)):
                    target_price = float(target_price)
                else:
                    target_price = None
            except (ValueError, TypeError):
                target_price = None
        else:
            target_price = None

        # 🔥 Compliance modification: Convert English/old operational recommendations to Chinese compliance terminology (research conclusion tendency)
        action_translation = {
            'BUY': '乐观',
            'SELL': '审慎',
            'HOLD': '中性',
            'buy': '乐观',
            'sell': '审慎',
            'hold': '中性',
            '买入': '乐观',  # Compatible with old data
            '卖出': '审慎',
            '持有': '中性',
            '看涨': '乐观',  # Compatible with old data
            '看跌': '审慎',
        }
        action = decision.get('action', '中性')
        chinese_action = action_translation.get(action, action)

        # 🔥 Important: reasoning should be extracted from decision. If decision does not have reasoning, use the default value.
        # should not be extracted from final_trade_decision as final_trade_decision will be used to generate summary
        reasoning = decision.get('reasoning', '') or decision.get('rationale', '')
        if not reasoning:
            reasoning = '暂无分析推理'
        
        self.logger.info(f"🔍 [TaskAnalysisService._format_decision_dict] decision Field: {list(decision.keys())}")
        self.logger.info(f"🔍 [TaskAnalysisService._format_decision_dict] reasoning 长度: {len(reasoning)}, 内容: {reasoning[:200]}")

        # 🔥 Make sure confidence is a decimal between 0-1 (expected by the front end)
        confidence = float(decision.get('confidence', 0.5))
        if confidence > 1:
            # If LLM returns an integer from 0 to 100, convert it to a decimal from 0 to 1
            confidence = confidence / 100.0

        # 🔥 Make sure risk_score is a decimal between 0-1 (expected by the front end)
        risk_score = decision.get('risk_score')
        if risk_score is not None:
            risk_score = float(risk_score)
            if risk_score > 1:
                risk_score = risk_score / 100.0
        else:
            risk_score = 0.5  # Default value
            self.logger.warning(f"⚠️ [TaskAnalysisService._format_decision_dict] decision There is no risk_score in , the default value is used 0.5")

        # 🔥 Compliance modification: return price_analysis_range (price range) instead of target_price (specific price)
        # Extract price_analysis_range if present
        price_analysis_range = decision.get('price_analysis_range')
        
        # 🔥 Make sure price_analysis_range remains in array format and does not convert to a single value
        if price_analysis_range is not None:
            # If it's a list/array, leave it as is
            if isinstance(price_analysis_range, (list, tuple)):
                # Make sure it is a valid range format [min, max]
                if len(price_analysis_range) == 2:
                    price_analysis_range = [float(price_analysis_range[0]), float(price_analysis_range[1])]
                    self.logger.info(f"✅ [TaskAnalysisService._format_decision_dict] price_analysis_range is an array: {price_analysis_range}")
                else:
                    self.logger.warning(f"⚠️ [TaskAnalysisService._format_decision_dict] price_analysis_range The array length is not 2: {price_analysis_range}")
                    price_analysis_range = None
            # If it is a single number, convert it to array format (generate a reasonable interval based on the value)
            elif isinstance(price_analysis_range, (int, float)):
                single_value = float(price_analysis_range)
                # 🔥 Improvement: Generate a reasonable price range based on a single value (±5%) 
                # This avoids front-end display '-', Instead, it shows a reasonable price range
                price_range_pct = 0.05  # 5% The fluctuation range of
                min_price = single_value * (1 - price_range_pct)
                max_price = single_value * (1 + price_range_pct)
                price_analysis_range = [round(min_price, 2), round(max_price, 2)]
                self.logger.info(f"✅ [TaskAnalysisService._format_decision_dict] price_analysis_range is a single value {single_value}, converted to interval: {price_analysis_range}")
            else:
                self.logger.warning(f"⚠️ [TaskAnalysisService._format_decision_dict] price_analysis_range Incorrect format: {type(price_analysis_range)} = {price_analysis_range}")
                price_analysis_range = None
        
        if not price_analysis_range:
            self.logger.warning(f"⚠️ [TaskAnalysisService._format_decision_dict] decision There is no valid price_analysis_range in the frontend will display '-'")
        
        # 🔥 Debug log: record returned fields
        self.logger.info(f"🔍 [TaskAnalysisService._format_decision_dict] 返回字段: action={chinese_action}, price_analysis_range={price_analysis_range} (类型: {type(price_analysis_range)}), risk_score={risk_score}, confidence={confidence}")
        
        return {
            'action': chinese_action,
            'analysis_view': chinese_action,  # 🔥 Compatible fields
            'confidence': confidence,
            'risk_score': risk_score,
            'target_price': None,  # 🔥 No specific price provided (compliance requirement)
            'price_analysis_range': price_analysis_range,  # 🔥 Price range (compliance)
            'reasoning': reasoning
        }

    def _extract_decision_from_text(self, text: str) -> Dict[str, Any]:
        """Extract decision information from text

        Args:
            text: decision text

        Returns:
            decision dictionary
        """
        import re

        # Extract actions (unified use of compliance research conclusion tendency terms)
        action = '中性'  # Default
        if re.search(r'(strong)?buy|Recommended to buy|long|BUY|STRONG_BUY|bullish|optimistic', text, re.IGNORECASE):
            action = '乐观'
        elif re.search(r'(strong)?sell|Recommended to sell|bearish|Reduce holdings|SELL|STRONG_SELL|Bearish|Prudence', text, re.IGNORECASE):
            action = '审慎'
        elif re.search(r'hold|wait and see|wait|HOLD|Neutral', text, re.IGNORECASE):
            action = '中性'

        # Extract target price
        target_price = None
        price_patterns = [
            r'target price[person]?[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',  # target price: 45.50
            r'\*\*target price[person]?\*\*[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',  # **target price**: 45.50
            r'target[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',         # target: 45.50
            r'price[: :]?\s*[¥\$]?(\d+(?:\.\d+)?)',         # price: 45.50
            r'[¥\$](\d+(?:\.\d+)?)',                      # ¥45.50 or $190
            r'(\d+(?:\.\d+)?)Yuan',                         # 45.50 Yuan
        ]

        for pattern in price_patterns:
            price_match = re.search(pattern, text)
            if price_match:
                try:
                    target_price = float(price_match.group(1))
                    break
                except ValueError:
                    continue

        # Extract confidence
        confidence = 0.7  # Default
        confidence_match = re.search(r'Confidence[: :]?\s*(\d+(?:\.\d+)?)', text)
        if confidence_match:
            try:
                confidence = float(confidence_match.group(1))
                if confidence > 1:  # If it is in percentage form
                    confidence = confidence / 100
            except ValueError:
                pass

        # Extract risk score
        risk_score = 0.5  # Default
        risk_match = re.search(r'risk[Rating score][: :]?\s*(\d+(?:\.\d+)?)', text)
        if risk_match:
            try:
                risk_score = float(risk_match.group(1))
                if risk_score > 1:  # If it is in percentage form
                    risk_score = risk_score / 100
            except ValueError:
                pass

        # 🔥 Extract research basis (preferably extract from JSON, otherwise extract text summary)
        # Note: If text is final_trade_decision (risk assessment report), it should not be used as reasoning
        # Only a brief summary of reasoning is extracted here
        
        # 🔍 Debugging: First print the original text content to see what is inside (complete content, not truncated)
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] ========== Original text content (complete) ==========")
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Text length: {len(text)}")
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] full text content:\n{text}")
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Does it contain ```json: {'```json' in text}")
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Does it contain ```: {'```' in text}")
        
        reasoning = ""
        
        # 1. First try to extract from JSON code block reasoning
        import json
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if not json_match:
            # Try the code block without json tag
            json_match = re.search(r'```\s*(\{.*?\})\s*```', text, re.DOTALL)
        
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] JSON Code block matching results: {json_match is not None}")
        if json_match:
            json_content = json_match.group(1)
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] JSON code block length: {len(json_content)}")
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] JSON Complete content of code block:\n{json_content}")
        
        # 🔥 Fields extracted from JSON
        price_analysis_range_from_json = None
        risk_score_from_json = None
        confidence_from_json = None
        
        if json_match:
            try:
                json_str = json_match.group(1)
                self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Trying to parse JSON, length: {len(json_str)}")
                json_obj = json.loads(json_str)
                self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] JSON 解析成功，类型: {type(json_obj)}, 字段: {list(json_obj.keys()) if isinstance(json_obj, dict) else 'N/A'}")
                # Extract reasoning fields from JSON
                if isinstance(json_obj, dict):
                    # 🔥 Extract price_analysis_range (price range)
                    price_analysis_range_from_json = json_obj.get('price_analysis_range')
                    if price_analysis_range_from_json:
                        self.logger.info(f"✅ [TaskAnalysisService._extract_decision_from_text] Extract from JSON price_analysis_range: {price_analysis_range_from_json}")
                    
                    # 🔥 Extract risk_score (risk score)
                    risk_score_from_json = json_obj.get('risk_score')
                    if risk_score_from_json is not None:
                        # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                        if isinstance(risk_score_from_json, (int, float)) and risk_score_from_json > 1:
                            risk_score_from_json = risk_score_from_json / 100.0
                        self.logger.info(f"✅ [TaskAnalysisService._extract_decision_from_text] Extract from JSON risk_score: {risk_score_from_json}")
                    
                    # 🔥 Extract confidence
                    confidence_from_json = json_obj.get('confidence')
                    if confidence_from_json is not None:
                        # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                        if isinstance(confidence_from_json, (int, float)) and confidence_from_json > 1:
                            confidence_from_json = confidence_from_json / 100.0
                        self.logger.info(f"✅ [TaskAnalysisService._extract_decision_from_text] Extract from JSON confidence: {confidence_from_json}")
                    
                    # 🔥 Extract the final_trade_decision nested object if it exists
                    final_trade_decision = json_obj.get('final_trade_decision', {})
                    if isinstance(final_trade_decision, dict):
                        # If there is no price_analysis_range in the outer layer, try to get it from final_trade_decision
                        if not price_analysis_range_from_json:
                            price_analysis_range_from_json = final_trade_decision.get('price_analysis_range')
                        # If the outer layer does not have risk_score, try to get it from final_trade_decision
                        if risk_score_from_json is None:
                            risk_score_from_json = final_trade_decision.get('risk_score')
                        # If there is no confidence in the outer layer, try to get it from final_trade_decision
                        if confidence_from_json is None:
                            confidence_from_json = final_trade_decision.get('confidence')
                    
                    json_reasoning = json_obj.get('reasoning', '')
                    self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] JSON length of reasoning in: {len(json_reasoning) if json_reasoning else 0}")
                    self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] JSON full content of reasoning in:\n{json_reasoning if json_reasoning else 'N/A'}")
                    if json_reasoning and isinstance(json_reasoning, str) and len(json_reasoning.strip()) > 0:
                        # If reasoning is long, just take the first 100 characters as summary
                        if len(json_reasoning) > 100:
                            reasoning = json_reasoning[:100].strip() + "..."
                        else:
                            reasoning = json_reasoning.strip()
                        self.logger.info(f"✅ [TaskAnalysisService._extract_decision_from_text] 从 JSON 提取 reasoning: {len(reasoning)}字符")
                    else:
                        self.logger.warning(f"⚠️ [TaskAnalysisService._extract_decision_from_text] JSON reasoning in is empty or not a string")
            except (json.JSONDecodeError, Exception) as e:
                self.logger.warning(f"⚠️ [TaskAnalysisService._extract_decision_from_text] JSON Parsing failed: {e}")
                import traceback
                self.logger.warning(f"⚠️ [TaskAnalysisService._extract_decision_from_text] JSON Parse failure details:\n{traceback.format_exc()}")
        
        # 2. If not extracted from JSON, try to extract a short summary from the text
        if not reasoning:
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] JSON Extraction failed, trying to extract from text")
            # Remove Markdown tags and code block tags
            clean_text = re.sub(r'```json.*?```', '', text, flags=re.DOTALL)
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Remove ```json length after code block: {len(clean_text)}")
            clean_text = re.sub(r'```.*?```', '', clean_text, flags=re.DOTALL)
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Length after removing all code blocks: {len(clean_text)}")
            clean_text = clean_text.replace('#', '').replace('*', '').replace('`', '').strip()
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Length after removing Markdown tags: {len(clean_text)}")
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] Cleaned text complete content:\n{clean_text}")
            
            # Extract the first 100 characters as a summary (shorter than the previous 150 characters to avoid including too much content)
            if len(clean_text) > 100:
                reasoning = clean_text[:100].strip() + "..."
            else:
                reasoning = clean_text.strip()
            
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] 从文本提取 reasoning: {len(reasoning)}字符")
            self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] reasoning full content extracted from text:\n{reasoning}")
        
        # 3. If still not available, use default value
        if not reasoning or len(reasoning.strip()) < 10:
            reasoning = "Please refer to the detailed analysis report."
            self.logger.warning(f"⚠️ [TaskAnalysisService._extract_decision_from_text] reasoning Empty or too short, use default value")
        
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] ========== eventually reasoning ==========")
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] 最终 reasoning 长度: {len(reasoning)}字符")
        self.logger.info(f"🔍 [TaskAnalysisService._extract_decision_from_text] final reasoning full content:\n{reasoning}")

        # 🔥 Use the value extracted from JSON if present
        final_confidence = confidence_from_json if confidence_from_json is not None else confidence
        final_risk_score = risk_score_from_json if risk_score_from_json is not None else risk_score
        
        return {
            'action': action,
            'target_price': target_price,
            'price_analysis_range': price_analysis_range_from_json,  # 🔥 New: price range
            'confidence': final_confidence,  # 🔥 Use values extracted from JSON
            'risk_score': final_risk_score,  # 🔥 Use values extracted from JSON
            'reasoning': reasoning
        }

    async def _update_task(self, task: UnifiedAnalysisTask) -> None:
        """Update tasks to database

        Args:
            task: Task object
        """
        doc = task.model_dump(by_alias=True, exclude={"_id"}, mode='python')

        # Make sure user_id is of type ObjectId, not a string
        if 'user_id' in doc and isinstance(doc['user_id'], str):
            from bson import ObjectId
            doc['user_id'] = ObjectId(doc['user_id'])

        await self.collection.update_one(
            {"task_id": task.task_id},
            {"$set": doc}
        )
        self.logger.debug(f"💾 任务已更新: {task.task_id}")

    def _schedule_growth_extraction(
        self,
        task_id: str,
        raw_result: Dict[str, Any],
        formatted_result: Dict[str, Any],
        analysis_id: Optional[str],
    ) -> None:
        """Asynchronous scheduling of growth extraction to avoid blocking the main link of the task."""
        try:
            asyncio.create_task(
                self._extract_growth_in_background(
                    task_id=task_id,
                    raw_result=raw_result,
                    formatted_result=formatted_result,
                    analysis_id=analysis_id,
                )
            )
        except Exception as exc:
            self.logger.warning(f"⚠️ Scheduling growth extraction task failed(ignore): {exc}")

    async def _extract_growth_in_background(
        self,
        task_id: str,
        raw_result: Dict[str, Any],
        formatted_result: Dict[str, Any],
        analysis_id: Optional[str],
    ) -> None:
        """The background extracts the growth products and writes back the task, which does not affect the completion time of the main task."""
        try:
            task = await self.get_task(task_id)
            if not task:
                self.logger.warning(f"⚠️ Background growth extraction skipped: task does not exist {task_id}")
                return

            from app.services.workflow_growth_service import get_workflow_growth_service

            growth_context = await get_workflow_growth_service().process_completed_task(
                task=task,
                raw_result=raw_result,
                formatted_result=formatted_result,
                analysis_id=analysis_id,
            )

            update_fields: Dict[str, Any] = {
                "growth_context": growth_context.model_dump(mode="python"),
                "updated_at": now_tz(),
            }
            if task.result is not None:
                update_fields["result.growth_context"] = growth_context.model_dump(mode="json")

            await self.collection.update_one(
                {"task_id": task_id},
                {"$set": update_fields}
            )
            self.logger.info(f"✅ 后台成长提取完成: {task_id}")
        except Exception as exc:
            self.logger.warning(f"⚠️ Background growth extraction failed(ignore): {task_id} - {exc}")

    async def _save_to_analysis_reports(self, task: UnifiedAnalysisTask, result: Dict[str, Any]) -> Optional[str]:
        """Save analysis results to the analysis_reports collection (compatible with legacy API)

        Use unified report saving tool functions

        Args:
            task: Task object
            result: Formatted analysis results
        """
        try:
            from app.utils.report_saver import save_analysis_report

            stock_code = task.task_params.get("symbol") or task.task_params.get("stock_code", "")
            market_type = task.task_params.get("market_type", "A股")

            # Parse stock name if not in result
            stock_name = result.get("stock_name", "")
            if not stock_name:
                stock_name = await self._resolve_stock_name(stock_code)

            # 🔑 Get model information
            quick_model = task.task_params.get("quick_analysis_model") or result.get("quick_model", "Unknown")
            deep_model = task.task_params.get("deep_analysis_model") or result.get("deep_model", "Unknown")
            model_info = result.get("model_info") or f"{quick_model}/{deep_model}"

            # 🔑 Extract analyst list from report
            def _get_analysts_from_reports(reports_dict: Dict[str, Any]) -> List[str]:
                """Dynamically generate analyst list based on actual saved reports"""
                analysts = []
                fundamentals_analyst_id = (
                    "etf_analyst" if task.task_type == AnalysisTaskType.ETF_ANALYSIS else "fundamentals_analyst"
                )
                analyst_mapping = {
                    "index_report": "index_analyst",
                    "sector_report": "sector_analyst",
                    "market_report": "market_analyst",
                    "sentiment_report": "sentiment_analyst",
                    "news_report": "news_analyst",
                    "fundamentals_report": fundamentals_analyst_id,
                    "bull_researcher": "bull_researcher",
                    "bear_researcher": "bear_researcher",
                    "risky_analyst": "risky_analyst",
                    "safe_analyst": "safe_analyst",
                    "neutral_analyst": "neutral_analyst",
                }
                for report_key, analyst_id in analyst_mapping.items():
                    if report_key in reports_dict and reports_dict[report_key]:
                        analysts.append(analyst_id)
                return analysts

            reports_dict = result.get("reports", {})
            analysts_list = _get_analysts_from_reports(reports_dict) or result.get("analysts", [])

            # 🔑 Extract recommendations and confidence_score
            decision = result.get("decision", {})
            recommendation = result.get("recommendation", "")
            if not recommendation and decision.get("action"):
                # 🔥 Compliance Modification: Use"analysis point of view"substitute"investment advice", No specific price included
                recommendation = f"Analysis point of view:{decision.get('action')}; "
                if decision.get("reasoning"):
                    reasoning = decision.get("reasoning", "")[:200]
                    recommendation += f"Analysis basis:{reasoning}"

            confidence_score = result.get("confidence_score", 0.0)
            if confidence_score == 0.0 and decision.get("confidence"):
                confidence_score = decision.get("confidence", 0.0)

            risk_level = result.get("risk_level", "中等")
            if risk_level == "中等" and decision.get("risk_score") is not None:
                risk_score = decision.get("risk_score", 0.5)
                if risk_score < 0.3:
                    risk_level = "低"
                elif risk_score < 0.6:
                    risk_level = "中等"
                else:
                    risk_level = "高"

            # 🔥 Use unified report saving function
            analysis_id = await save_analysis_report(
                db=self.db,
                stock_symbol=stock_code,
                stock_name=stock_name,
                market_type=market_type,
                model_info=model_info,
                reports=reports_dict,
                decision=decision,
                recommendation=recommendation,
                confidence_score=confidence_score,
                risk_level=risk_level,
                summary=result.get("summary", ""),
                key_points=result.get("key_points", []),
                task_id=task.task_id,
                execution_time=task.execution_time or 0,
                tokens_used=result.get("tokens_used", 0),
                analysts=analysts_list,
                research_depth=result.get("research_depth", task.task_params.get("research_depth", "标准")),
                analysis_date=result.get("analysis_date"),
                source="api",
                engine="v2" if task.engine_type in ["auto", "workflow"] else (task.engine_type or "v2"),
                user_id=str(task.user_id) if task.user_id else None,
                performance_metrics=result.get("performance_metrics", {}),
                task_type=str(task.task_type),
            )

            self.logger.info(f"✅ Analysis results have been saved to analysis_reports: analysis_id={analysis_id}, task_id={task.task_id}")
            return analysis_id  # 🔑 Return to the saved analysis_id

        except Exception as e:
            self.logger.error(f"❌ Saving to analysis_reports failed: {e}", exc_info=True)
            return None  # 🔑 Return when saving fails None

    async def _store_stock_object_memory(self, task: UnifiedAnalysisTask, result: Dict[str, Any]) -> None:
        """Write stock analysis results from background tasks to objectized long-term memory."""
        symbol = str((task.task_params or {}).get("symbol") or (task.task_params or {}).get("stock_code") or "").strip().upper()
        if not symbol or _is_cn_etf_symbol(symbol):
            return

        summary = str(result.get("summary") or result.get("executive_summary") or "").strip()
        recommendation = str(result.get("recommendation") or "").strip()
        if not summary and not recommendation:
            return

        from core.memory.service import get_memory_service

        svc = get_memory_service(self.db)
        analysis_date = str(
            result.get("analysis_date")
            or (task.task_params or {}).get("analysis_date")
            or now_tz().strftime("%Y-%m-%d")
        ).strip()
        evidence = [
            str(item or "").strip()
            for item in (result.get("key_points") or [])[:5]
            if str(item or "").strip()
        ]
        memory_result = await svc.store_stock_analysis(
            user_id=str(task.user_id or ""),
            symbol=symbol,
            market=_normalize_memory_market(symbol, (task.task_params or {}).get("market_type")),
            summary=summary or recommendation,
            recommendation=recommendation,
            analysis_date=analysis_date,
            task_id=str(task.task_id),
            agent_id="workflow_analyst",
            session_id=str(task.task_id),
            evidence=evidence,
            next_checks=[recommendation] if recommendation else None,
        )
        self.logger.info(
            "[mem0] Objectized stock memory writing results — user=%s symbol=%s task=%s facts=%d success=%s error=%s",
            str(task.user_id or ""),
            symbol,
            str(task.task_id),
            memory_result.facts_extracted,
            memory_result.success,
            memory_result.error or "",
        )
    
    async def _find_one_compatible(self, collection, query: Dict[str, Any], projection: Optional[Dict[str, Any]] = None):
        """Compatible with find_one calls of synchronous/asynchronous Mongo collections."""
        result = collection.find_one(query, projection)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _resolve_stock_name(self, stock_code: str) -> str:
        """Parse stock names
        
        Args:
            stock_code: Stock code
            
        Returns:
            Stock name, returns default value if parsing fails
        """
        if not stock_code:
            return ""
        
        try:
            code_str = str(stock_code).strip().zfill(6)

            if self.db is not None:
                if _is_cn_etf_symbol(code_str):
                    etf_doc = await self._find_one_compatible(
                        self.db.etf_basic_info,
                        {"code": code_str},
                        {"name": 1, "fund_name": 1, "etf_name": 1, "_id": 0}
                    )
                    if etf_doc:
                        etf_name = etf_doc.get("name") or etf_doc.get("fund_name") or etf_doc.get("etf_name")
                        if etf_name:
                            return etf_name

                stock_doc = await self._find_one_compatible(
                    self.db.stock_basic_info,
                    {"$or": [{"code": code_str}, {"symbol": code_str}]},
                    {"name": 1, "stock_name": 1, "_id": 0}
                )
                if stock_doc:
                    stock_name = stock_doc.get("name") or stock_doc.get("stock_name")
                    if stock_name:
                        return stock_name

            # Prioritize trying to get structured data from data_source_manager
            try:
                from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
                info_dict = get_info_dict(stock_code)
                if info_dict and isinstance(info_dict, dict) and info_dict.get('name'):
                    return info_dict['name']
            except Exception:
                pass
            
            # Downgrade: try using get_stock_basic_info
            try:
                from tradingagents.dataflows.data_source_manager import get_stock_basic_info
                info_str = get_stock_basic_info(stock_code)
                
                if info_str and isinstance(info_str, str) and "股票名称:" in info_str:
                    stock_name = info_str.split("股票名称:")[1].split("\n")[0].strip()
                    if stock_name:
                        return stock_name
                elif info_str and isinstance(info_str, dict) and info_str.get("name"):
                    return info_str["name"]
            except Exception:
                pass
                
        except Exception as e:
            self.logger.warning(f"⚠️ 解析股票名称失败: {stock_code} - {e}")
        
        return f"{'ETF' if _is_cn_etf_symbol(stock_code) else 'stocks'}{stock_code}"
    
    async def _validate_task_data(self, task: UnifiedAnalysisTask) -> 'DataValidationResult':
        """
        Verify data integrity required for tasks
        
        Args:
            task: Analyze task objects
            
        Returns:
            DataValidationResult: Verification result
        """
        from app.services.data_validation_service import get_data_validation_service
        
        # Extract necessary information from task parameters
        task_params = task.task_params or {}
        symbol = task_params.get("symbol") or task_params.get("stock_code", "")
        analysis_date = task_params.get("analysis_date")
        market_type = task_params.get("market_type", "cn")
        
        # If market_type is "A shares" Wait for Chinese, convert to English
        market_type_map = {
            "A股": "cn",
            "港股": "hk",
            "美股": "us",
            "cn": "cn",
            "hk": "hk",
            "us": "us"
        }
        market_type = market_type_map.get(market_type, "cn")
        
        # If no analysis date is specified, the current date is used
        if not analysis_date:
            from datetime import datetime
            analysis_date = datetime.now().strftime('%Y-%m-%d')
        
        if not symbol:
            from app.services.data_validation_service import DataValidationResult
            return DataValidationResult(
                is_valid=False,
                message="Stock symbol (symbol or stock_code) missing from task parameters",
                missing_data=["symbol"],
                details={"error": "股票代码缺失"}
            )
        
        # Call the data verification service
        validation_service = get_data_validation_service()
        result = await validation_service.validate_stock_data(
            symbol=symbol,
            analysis_date=analysis_date,
            market_type=market_type,
            check_basic_info=True,
            check_historical_data=True,
            check_financial_data=False,  # Financial data optional
            check_realtime_quotes=False,  # Real-time quotes optional
            historical_days=365  # By default, historical data of the past 1 year is checked.
        )
        
        return result

    async def get_task_statistics(self, user_id: PyObjectId) -> Dict[str, Any]:
        """Get user task statistics

        Args:
            user_id: User ID

        Returns:
            Statistics Dictionary
        """
        self.logger.info(f"📊 获取任务统计 - user_id: {user_id} (类型: {type(user_id)})")

        # Check the total number of tasks first
        total_count = await self.collection.count_documents({"user_id": user_id})
        self.logger.info(f"📊 用户任务总数: {total_count}")

        # If there is no task, empty statistics will be returned directly.
        if total_count == 0:
            self.logger.warning(f"⚠️ 用户 {user_id} 没有任务")
            # Print some debugging information
            all_tasks = await self.collection.find().limit(5).to_list(5)
            self.logger.info(f"📋 数据库中的任务示例:")
            for task in all_tasks:
                self.logger.info(f"  - task_id: {task.get('task_id')}, user_id: {task.get('user_id')} (类型: {type(task.get('user_id'))})")

        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1}
            }}
        ]

        cursor = self.collection.aggregate(pipeline)

        stats = {
            "total": 0,
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0
        }

        async for doc in cursor:
            status = doc["_id"]
            count = doc["count"]
            self.logger.info(f"📊 状态统计: {status} = {count}")
            stats[status] = count
            stats["total"] += count

        self.logger.info(f"📊 最终统计结果: {stats}")
        return stats
    
    async def _send_analysis_email_notification(
        self,
        task: UnifiedAnalysisTask,
        formatted_result: Dict[str, Any]
    ) -> None:
        """Send analysis completion email notification
        
        Args:
            task: Task object
            formatted_result: Formatted analysis results
        """
        from app.services.email_service import get_email_service
        from app.models.email import EmailType
        
        try:
            email_service = get_email_service()
            
            # Extract stock information from task parameters
            stock_code = task.task_params.get("symbol") or task.task_params.get("stock_code", "")
            stock_name = formatted_result.get("stock_name") or formatted_result.get("stock_symbol") or stock_code
            analysis_date = formatted_result.get("analysis_date", "")
            
            # Extract analysis information from formatted results
            summary = formatted_result.get("summary", "")
            recommendation = formatted_result.get("recommendation", "")
            confidence_score = formatted_result.get("confidence_score", 0)
            risk_level = formatted_result.get("risk_level", "中等")
            
            # Extract key points (from reasoning or other fields)
            key_points = formatted_result.get("key_points", [])
            if not key_points:
                # Try to extract key points from decision.reasoning
                decision = formatted_result.get("decision", {})
                reasoning = decision.get("reasoning", "")
                if reasoning and reasoning != "暂无分析推理":
                    # Simple extraction: split by periods, take the first 3 items
                    sentences = [s.strip() for s in reasoning.split("。") if s.strip()]
                    key_points = sentences[:3]
            
            # Generate PDF attachment (optional)
            attachments = None
            try:
                from app.utils.report_exporter import ReportExporter
                from app.utils.report_formatter import extract_reports_from_state
                
                report_exporter = ReportExporter()
                if report_exporter.weasyprint_available or report_exporter.pdfkit_available:
                    reports = formatted_result.get("reports", {})
                    if not reports:
                        state = formatted_result.get("state", {})
                        reports = extract_reports_from_state(state)
                    
                    if reports:
                        # Build report document
                        report_doc = {
                            "stock_symbol": stock_code,
                            "stock_name": stock_name,
                            "analysis_date": analysis_date,
                            "recommendation": recommendation,
                            "confidence_score": confidence_score,
                            "risk_level": risk_level,
                            "reports": reports,
                            "decision": formatted_result.get("decision", {})
                        }
                        
                        pdf_content = report_exporter.generate_pdf_report(report_doc)
                        if pdf_content:
                            filename = f"{stock_code}_{analysis_date}_分析报告.pdf"
                            attachments = [(filename, pdf_content, "application/pdf")]
                            self.logger.info(f"📄 PDF report generated: {filename} ({len(pdf_content)} bytes)")
            except Exception as pdf_err:
                self.logger.warning(f"⚠️ PDF Build failed(Email will be sent without attachments): {pdf_err}")
            
            # Send email
            await email_service.send_analysis_email(
                user_id=str(task.user_id),
                email_type=EmailType.SINGLE_ANALYSIS,
                template_name="single_analysis",
                template_data={
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "analysis_date": analysis_date,
                    "summary": summary,
                    "recommendation": recommendation,
                    "confidence_score": confidence_score,
                    "risk_level": risk_level,
                    "key_points": key_points,
                    "detail_url": f"{stock_code}"
                },
                reference_id=task.task_id,
                attachments=attachments  # Comes with PDF report
            )
            self.logger.info(f"📧 Attempted to send analysis completion email: {task.task_id}")
        except Exception as e:
            # Failure to send the email should not affect task completion, only a warning will be logged
            self.logger.warning(f"⚠️ Failed to send email notification(ignore): {e}", exc_info=True)
            raise  # Rethrow the exception to let the caller know the failure (but does not affect the task status)


# Singleton instance
_task_service: Optional[TaskAnalysisService] = None


def get_task_analysis_service() -> TaskAnalysisService:
    """获取任务分析服务单例"""
    global _task_service
    if _task_service is None:
        _task_service = TaskAnalysisService()
    return _task_service

