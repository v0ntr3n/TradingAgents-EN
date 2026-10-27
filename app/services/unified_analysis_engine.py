"""
Unified analytics engine

Provides a unified task execution interface and supports multiple execution engines:
- workflow: Workflow engine (recommended)
- legacy: old engine TradingAgentsGraph
- llm: Direct LLM call
"""

from typing import Dict, Any, Optional, Callable
import logging
from datetime import datetime

from app.models.analysis import UnifiedAnalysisTask, AnalysisTaskType, AnalysisStatus
from app.services.workflow_registry import AnalysisWorkflowRegistry
from app.utils.timezone import now_tz
from core.workflow.default_workflow_provider import get_default_workflow_provider

logger = logging.getLogger(__name__)


class UnifiedAnalysisEngine:
    """Unified analytics engine
    
    Responsible for executing various types of analysis tasks and automatically selecting the appropriate execution engine
    
    Usage example:
        engine = UnifiedAnalysisEngine()
        result = await engine.execute_task(task, progress_callback)
    """
    
    def __init__(self):
        """初始化引擎"""
        self.logger = logger

    def _workflow_exists(self, workflow_id: Optional[str]) -> bool:
        """Check if the workflow exists in the system provisioning, database, or file system."""
        if not workflow_id:
            return False

        provider = get_default_workflow_provider()
        if provider.get_system_workflow(workflow_id) is not None:
            return True

        from core.api.workflow_api import WorkflowAPI

        try:
            return WorkflowAPI().get(workflow_id) is not None
        except Exception as exc:
            self.logger.warning(f"⚠️ Failed to verify workflow existence: workflow_id={workflow_id}, error={exc}")
            return False

    def _workflow_type_for_task(self, task_type: AnalysisTaskType, task_params: dict = None) -> str:
        """Map task types to workflow types."""
        # If there is a task_category tag, it is used first (general research tasks use STOCK_ANALYSIS as the carrier but are actually of general type)
        if task_params and task_params.get("task_category") == "general":
            return "general"
        mapping = {
            AnalysisTaskType.STOCK_ANALYSIS: "stock_analysis",
            AnalysisTaskType.ETF_ANALYSIS: "etf_analysis",
            AnalysisTaskType.POSITION_ANALYSIS: "position_analysis",
            AnalysisTaskType.TRADE_REVIEW: "trade_review",
        }
        return mapping.get(task_type, task_type.value if hasattr(task_type, "value") else str(task_type))

    def _resolve_workflow_id(self, task: UnifiedAnalysisTask, config) -> str:
        """Resolve the workflow ID that should be used for this task.

        Priority:
        1. The workflow_id specified explicitly by the task (e.g. /api/workflows/{id}/execute incoming)
        2. My analysis flow (the default workflow set by the user for the current task_type)
        3. Registry default configuration
        4. System hardcoded defaults
        """
        task_type = task.task_type
        if isinstance(task_type, str):
            task_type = AnalysisTaskType(task_type)

        workflow_type = self._workflow_type_for_task(task_type, task.task_params)

        # Priority 1: Task explicitly specified workflow_id
        explicit_workflow_id = task.workflow_id or task.task_params.get("workflow_id")
        if explicit_workflow_id:
            if self._workflow_exists(explicit_workflow_id):
                self.logger.info(f"📋 Workflow selection: Explicitly specified using tasks workflow_id={explicit_workflow_id}")
                return explicit_workflow_id
            self.logger.warning(
                f"⚠️ The workflow explicitly specified by the task does not exist and will fall back to my analysis flow configuration: workflow_id={explicit_workflow_id}"
            )

        # Priority 2: My Analysis Flow (the default workflow set by the user for the current task_type)
        if task_type in (
            AnalysisTaskType.STOCK_ANALYSIS,
            AnalysisTaskType.ETF_ANALYSIS,
            AnalysisTaskType.POSITION_ANALYSIS,
            AnalysisTaskType.TRADE_REVIEW,
        ):
            try:
                workflow_provider = get_default_workflow_provider()
                active_workflow_id = workflow_provider.get_active_workflow_id(workflow_type)
                if active_workflow_id:
                    if self._workflow_exists(active_workflow_id):
                        self.logger.info(f"📋 Workflow selection: Use my analytics flow configuration type={workflow_type}, workflow_id={active_workflow_id}")
                        return active_workflow_id
                    try:
                        workflow_provider.load_workflow(active_workflow_id)
                    except Exception as exc:
                        self.logger.warning(
                            f"⚠️ 我的分析流配置 {active_workflow_id} 无效: {exc}"
                        )
                    else:
                        self.logger.info(f"📋 Workflow selection: Use my analytics flow configuration type={workflow_type}, workflow_id={active_workflow_id}")
                        return active_workflow_id
                    self.logger.warning(
                        f"⚠️ My analysis flow configuration does not exist and will fall back to registry defaults: workflow_id={active_workflow_id}"
                    )
            except Exception as exc:
                self.logger.warning(f"⚠️ Failed to get my analytics flow configuration: {exc}")

        # Priority 3: Registry default configuration
        if self._workflow_exists(config.workflow_id):
            self.logger.info(f"📋 Workflow selection: Use registry default workflow_id={config.workflow_id}")
            return config.workflow_id

        # Priority 4: System hard-coded defaults
        fallback_workflow_id = get_default_workflow_provider().get_default_workflow_id_for_type(workflow_type)
        self.logger.warning(
            f"⚠️ All configurations are invalid and fall back to the system default workflow.: type={workflow_type}, workflow_id={fallback_workflow_id}"
        )
        return fallback_workflow_id


    async def execute_task(
        self,
        task: UnifiedAnalysisTask,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> Dict[str, Any]:
        """Perform analysis tasks
        
        Args:
            task: Unified analysis task objects
            progress_callback: Progress callback function callback(progress: int, message: str)
            
        Returns:
            Analysis result dictionary
            
        Raises:
            ValueError: The task type is not registered or the parameters are invalid
            RuntimeError: Execution failed
        """
        self.logger.info(f"🚀 开始执行任务: {task.task_id} (类型: {task.task_type})")
        
        # 1. Get process configuration
        # Make sure task_type is an enum type (probably a string when loading from database)
        task_type = task.task_type
        if isinstance(task_type, str):
            try:
                task_type = AnalysisTaskType(task_type)
            except ValueError:
                raise ValueError(f"无效的任务类型: {task_type}")
        
        config = AnalysisWorkflowRegistry.get_config(task_type)
        if not config:
            raise ValueError(f"未注册的任务类型: {task_type}")
        
        # 2. Validation parameters
        is_valid, error_msg = AnalysisWorkflowRegistry.validate_params(
            task.task_type,
            task.task_params
        )
        if not is_valid:
            raise ValueError(f"任务参数无效: {error_msg}")
        
        # 3. Select execution engine
        engine_type = self._select_engine(task.engine_type, config.default_engine)
        self.logger.info(f"📌 选择执行引擎: {engine_type}")
        
        # 4. Update task status
        task.status = AnalysisStatus.PROCESSING
        task.started_at = now_tz()
        task.current_step = f"使用 {engine_type} 引擎执行"
        task.progress = 5

        # Notify progress
        if progress_callback:
            await self._call_progress_callback(progress_callback, 5, f"开始使用 {engine_type} 引擎执行")

        # 5. Perform analysis
        try:
            if engine_type == "workflow":
                result = await self._execute_via_workflow(task, config, progress_callback)
            elif engine_type == "legacy":
                result = await self._execute_via_legacy(task, config, progress_callback)
            elif engine_type == "llm":
                result = await self._execute_via_llm(task, config, progress_callback)
            else:
                raise ValueError(f"不支持的引擎类型: {engine_type}")

            # 6. Update task status
            task.status = AnalysisStatus.COMPLETED
            task.completed_at = now_tz()
            task.result = result
            task.progress = 100

            if task.started_at:
                task.execution_time = (task.completed_at - task.started_at).total_seconds()

            # Notify progress
            if progress_callback:
                await self._call_progress_callback(progress_callback, 100, "任务执行完成")

            self.logger.info(f"✅ 任务执行成功: {task.task_id} (耗时: {task.execution_time:.2f}秒)")

            return result

        except Exception as e:
            # 🔥 Graceful handling: check if it is a cancellation exception
            from app.services.task_analysis_service import TaskCancelledException

            if isinstance(e, TaskCancelledException):
                # Task cancellation is a normal operation and is not recorded as an error
                self.logger.info(f"🚫 任务已取消: {task.task_id}")
                # Just rethrow it and let the upper layer handle it
                raise

            # Other exceptions are real failures
            task.status = AnalysisStatus.FAILED
            task.completed_at = now_tz()
            task.error_message = str(e)

            if task.started_at:
                task.execution_time = (task.completed_at - task.started_at).total_seconds()

            self.logger.error(f"❌ 任务执行失败: {task.task_id} - {e}")
            raise RuntimeError(f"任务执行失败: {e}") from e
    
    async def _build_llm_config(
        self,
        quick_model: Optional[str],
        deep_model: Optional[str]
    ) -> Dict[str, Any]:
        """Get the complete LLM configuration from the database based on the model name

        Args:
            quick_model: Quickly analyze model names
            deep_model: In-depth analysis model name

        Returns:
            Complete configuration including provider, api_key, backend_url, etc.
        """
        if not quick_model and not deep_model:
            return {}

        from app.core.database import get_mongo_db

        db = get_mongo_db()

        # Get system configuration
        config_doc = await db.system_configs.find_one(
            {"is_active": True},
            sort=[("version", -1)]
        )

        if not config_doc or "llm_configs" not in config_doc:
            self.logger.warning("There is no LLM configuration in the database")
            return {}

        llm_configs = config_doc["llm_configs"]

        # Find matching model configurations
        target_model = quick_model or deep_model
        model_config = None

        for cfg in llm_configs:
            if cfg.get("model_name") == target_model and cfg.get("enabled", True):
                model_config = cfg
                break

        if not model_config:
            self.logger.warning(f"未找到模型配置: {target_model}")
            return {}

        # Get factory configuration
        provider_name = model_config.get("provider", "")
        provider_doc = await db.llm_providers.find_one({"name": provider_name})

        # 🔥 Determine API Key (Priority: Model Configuration > Factory configuration > environment variables)
        api_key = None
        model_api_key = model_config.get("api_key", "")
        if model_api_key and model_api_key.strip() and model_api_key != "your-api-key" and not model_api_key.startswith("sk-xxx"):
            api_key = model_api_key
            self.logger.info(f"✅ [LLM Configuration] Configured using models API Key")
        elif provider_doc:
            provider_api_key = provider_doc.get("api_key", "")
            if provider_api_key and provider_api_key.strip() and provider_api_key != "your-api-key" and not provider_api_key.startswith("sk-xxx"):
                api_key = provider_api_key
                self.logger.info(f"✅ [LLM Configuration] Use factory configured API Key")
        
        backend_url = model_config.get("api_base", "")
        if provider_doc and not backend_url:
            backend_url = provider_doc.get("default_base_url", "")

        # If the database does not have an API Key, try to get it from the environment variable
        if not api_key:
            import os
            env_key_map = {
                "openai": "OPENAI_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
                "dashscope": "DASHSCOPE_API_KEY",
                "google": "GOOGLE_API_KEY",
                "zhipu": "ZHIPU_API_KEY",
                "siliconflow": "SILICONFLOW_API_KEY",
            }
            env_name = env_key_map.get(provider_name.lower())
            if env_name:
                api_key = os.getenv(env_name)

        # 🔥 Get quick model configuration
        quick_model_config = None
        if quick_model:
            for cfg in llm_configs:
                if cfg.get("model_name") == quick_model and cfg.get("enabled", True):
                    quick_model_config = cfg
                    break
        
        # 🔥 Get depth model configuration
        deep_model_config = None
        if deep_model and deep_model != quick_model:
            for cfg in llm_configs:
                if cfg.get("model_name") == deep_model and cfg.get("enabled", True):
                    deep_model_config = cfg
                    break
        
        # If deep model configuration does not exist, use quick model configuration
        if not deep_model_config:
            deep_model_config = quick_model_config or model_config
        
        # Get the provider and api_key of the depth model (if different)
        deep_provider_name = provider_name
        deep_api_key = api_key
        deep_backend_url = backend_url
        
        if deep_model_config and deep_model_config != quick_model_config:
            deep_provider_name = deep_model_config.get("provider", provider_name)
            # 🔥 Determine the API Key of the depth model (Priority: Model Configuration > Factory configuration > environment variables)
            deep_model_api_key = deep_model_config.get("api_key", "")
            if deep_model_api_key and deep_model_api_key.strip() and deep_model_api_key != "your-api-key" and not deep_model_api_key.startswith("sk-xxx"):
                deep_api_key = deep_model_api_key
                self.logger.info(f"✅ [LLM Configuration] The depth model uses the model configuration API Key")
            elif deep_provider_name != provider_name:
                deep_provider_doc = await db.llm_providers.find_one({"name": deep_provider_name})
                if deep_provider_doc:
                    deep_provider_api_key = deep_provider_doc.get("api_key", "")
                    if deep_provider_api_key and deep_provider_api_key.strip() and deep_provider_api_key != "your-api-key" and not deep_provider_api_key.startswith("sk-xxx"):
                        deep_api_key = deep_provider_api_key
                        self.logger.info(f"✅ [LLM Configuration] The depth model uses the factory configured API Key")
                    deep_backend_url = deep_model_config.get("api_base", "") or deep_provider_doc.get("default_base_url", "")
            if not deep_api_key or deep_api_key.startswith("sk-xxx"):
                        import os
                        env_key_map = {
                            "openai": "OPENAI_API_KEY",
                            "deepseek": "DEEPSEEK_API_KEY",
                            "dashscope": "DASHSCOPE_API_KEY",
                            "google": "GOOGLE_API_KEY",
                            "zhipu": "ZHIPU_API_KEY",
                            "siliconflow": "SILICONFLOW_API_KEY",
                        }
                        env_name = env_key_map.get(deep_provider_name.lower())
                        if env_name:
                            deep_api_key = os.getenv(env_name) or deep_api_key
            else:
                deep_backend_url = deep_model_config.get("api_base", "") or backend_url
        
        result = {
            "llm_provider": provider_name,
            "quick_think_llm": quick_model or target_model,
            "deep_think_llm": deep_model or target_model,
            "backend_url": backend_url,
            "api_key": api_key,
            "quick_api_key": api_key,
            "deep_api_key": deep_api_key,
            "quick_temperature": (quick_model_config or model_config).get("temperature", 0.1),
            "quick_max_tokens": (quick_model_config or model_config).get("max_tokens", 2000),
            "quick_timeout": (quick_model_config or model_config).get("timeout", 60),
            "deep_temperature": deep_model_config.get("temperature", 0.1) if deep_model_config else (quick_model_config or model_config).get("temperature", 0.1),
            "deep_max_tokens": deep_model_config.get("max_tokens", 4000) if deep_model_config else (quick_model_config or model_config).get("max_tokens", 4000),
            "deep_timeout": deep_model_config.get("timeout", 120) if deep_model_config else (quick_model_config or model_config).get("timeout", 120),
            "deep_backend_url": deep_backend_url,  # 🔥 Always returns the depth model's backend_url
        }
        
        # If the deep model and fast model use different providers, add the provider information of the deep model
        if deep_provider_name != provider_name:
            result["deep_llm_provider"] = deep_provider_name

        self.logger.info(f"Get model configuration from database: provider={provider_name}, quick={quick_model}, deep={deep_model}")
        self.logger.info(f"  quick: temperature={result['quick_temperature']}, max_tokens={result['quick_max_tokens']}, timeout={result['quick_timeout']}")
        self.logger.info(f"  deep: temperature={result['deep_temperature']}, max_tokens={result['deep_max_tokens']}, timeout={result['deep_timeout']}")

        return result

    async def _call_progress_callback(
        self,
        callback: Optional[Callable],
        progress: int,
        message: str,
        **kwargs
    ):
        """Call progress callback (supports synchronous and asynchronous)"""
        if callback:
            import asyncio
            if asyncio.iscoroutinefunction(callback):
                await callback(progress, message, **kwargs)
            else:
                callback(progress, message, **kwargs)

    def _select_engine(self, requested_engine: str, default_engine: str) -> str:
        """Select execution engine

        Args:
            requested_engine: Requested engine type (auto/workflow/legacy/llm)
            default_engine: Default engine type

        Returns:
            Actual engine type used

        Raises:
            RuntimeError: When legacy engine is requested (deactivated)
        """
        # v3.0 The legacy engine has been deactivated
        if requested_engine == "legacy":
            raise RuntimeError(
                "[Deactivated] UnifiedAnalysisEngine._select_engine Reject legacy engines,"
                "Please use workflow or auto instead."
                "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
            )
        if requested_engine == "auto":
            # Defense: If the registry default engine is changed to legacy, force the change to workflow
            if default_engine == "legacy":
                self.logger.warning(
                    "⚠️ The default engine of the registry is legacy, which has been forcibly changed to workflow (legacy has been deactivated)"
                )
                return "workflow"
            return default_engine
        return requested_engine

    async def _inject_memory_facts(self, workflow_inputs: Dict[str, Any]) -> None:
        """Query the unexpired fact memory for this stock and inject workflow input (failure does not affect analysis).

        Fact memory source: intelligent assistant networking tool extraction (assistant_memory_facts collection),
        Match stock codes by symbol / related_terms and only take valid_until unexpired records.
        The injected text includes the collection date and source for the debate session (bull/bear) and risk assessment session.
         (risk_manager) As a reference for traceable materials (see consumer side) core/agents/base.py
        Fact memory injection whitelist).
        """
        try:
            ticker_val = str(workflow_inputs.get("ticker") or "").strip()
            if not ticker_val:
                return
            from datetime import datetime as _dt
            from app.core.database import get_mongo_db
            db = get_mongo_db()
            now_iso = _dt.now().isoformat(timespec="seconds")
            cursor = (
                db["assistant_memory_facts"]
                .find(
                    {
                        "valid_until": {"$gte": now_iso},
                        "$or": [
                            {"symbol": ticker_val},
                            {"related_terms": ticker_val},
                        ],
                    }
                )
                .sort("fetched_at", -1)
                .limit(8)
            )
            docs = [doc async for doc in cursor]
            if not docs:
                return
            blocks = [
                " [External fact memory] The following facts come from real data that the intelligent assistant has previously obtained and verified through networking tools."
                " (Contains collection date and source, and has passed timeliness verification). It can be used as part of the reference material for this analysis."
                "The date of collection must be marked when citing; if it is inconsistent with the latest data obtained in this analysis, this data shall prevail."
            ]
            for i, doc in enumerate(docs, 1):
                fetched = str(doc.get("fetched_at", ""))[:16].replace("T", " ")
                blocks.append(
                    f"--- 事实 {i} | 采集于 {fetched} | 来源 {doc.get('tool_id', '')} | "
                    f"Topic:{doc.get('topic', '')} ---\n{str(doc.get('content', ''))[:1000]}"
                )
            workflow_inputs["memory_facts_summary"] = "\n\n".join(blocks)
            self.logger.info(
                "🧠 [factual memory injection] ticker=%s %d external fact memories have been injected",
                ticker_val, len(docs),
            )
        except Exception as e:
            self.logger.warning(f"⚠️ [factual memory injection] Failure (does not affect analysis): {e}")

    async def _execute_via_workflow(
        self,
        task: UnifiedAnalysisTask,
        config,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Execute via workflow engine

        Args:
            task: Task object
            config: Workflow configuration
            progress_callback: Progress callback

        Returns:
            Execution result
        """
        workflow_id = self._resolve_workflow_id(task, config)
        self.logger.info(f"🔄 使用工作流引擎执行: {workflow_id}")

        # Import workflow API
        from core.api.workflow_api import WorkflowAPI

        workflow_api = WorkflowAPI()

        # Save a reference to the main event loop (before calling asyncio.to_thread)
        import asyncio
        main_loop = asyncio.get_running_loop()

        # Create a wrapped progress callback that updates the task object
        # Note: This callback will be called in the thread of the workflow engine (because of the use of asyncio.to_thread)
        # Therefore, you cannot call the asynchronous function directly, you need to use asyncio.run_coroutine_threadsafe
        def wrapped_progress_callback(progress: int, message: str, **kwargs):
            """Wrapped progress callback: updates the task object and calls the original callback"""
            # 🔑 Key: extract step_name (short name) from kwargs
            step_name = kwargs.get("step_name", "")

            # Update the task object (this is thread-safe since only object properties are modified)
            task.progress = progress
            task.current_step = step_name or message  # ✅ Use step_name instead message
            task.message = message  # ✅ Save detailed description to message field

            self.logger.debug(f"📊 进度更新: {progress}% - {step_name} - {message}")

            # Call the original callback (the original callback checks for the cancellation flag)
            if progress_callback:
                if asyncio.iscoroutinefunction(progress_callback):
                    # If it is an asynchronous callback, it needs to be run in the main event loop
                    try:
                        # Using a saved main event loop reference
                        future = asyncio.run_coroutine_threadsafe(
                            progress_callback(progress, message, **kwargs),
                            main_loop
                        )
                        # 🔥 Key: Wait for the callback to complete so it can be captured TaskCancelledException
                        try:
                            future.result(timeout=5)  # Wait up to 5 seconds
                        except Exception as callback_error:
                            # If the callback throws an exception (such as TaskCancelledException), propagate upward
                            self.logger.warning(f"⚠️ 进度回调执行异常: {callback_error}")
                            raise callback_error
                    except Exception as e:
                        self.logger.warning(f"⚠️ 进度回调调度失败: {e}")
                        raise  # Propagate exceptions upward
                else:
                    # Synchronous callbacks can be called directly
                    try:
                        progress_callback(progress, message, **kwargs)
                    except Exception as e:
                        self.logger.warning(f"⚠️ 进度回调执行失败: {e}")
                        raise  # Propagate exceptions upward
        
        # Prepare workflow input
        workflow_inputs = task.task_params.copy()

        # 🔑 Create an AgentContext and add it to the workflow input (used to obtain user-configured prompt words)
        from tradingagents.agents.utils.agent_context import AgentContext

        agent_context = AgentContext(
            user_id=str(task.user_id),
            preference_id=task.preference_type,  # Preference type for using tasks
            session_id=None,
            request_id=None,
            is_debug_mode=bool(task.task_params.get("debug_mode", False)),
            debug_template_id=task.task_params.get("debug_template_id"),
            workflow_id=workflow_id,
        )

        # Add AgentContext to workflow input
        workflow_inputs["context"] = agent_context

        # Parameter mapping: map symbol/code/stock_code to ticker (workflow engine uses ticker)
        # ⚠️ The field names used by different services are inconsistent:
        #   - stock_analysis use symbol
        #   - trade_review use code
        #   - portfolio_analysis use stock_code
        # Unified mapping to ticker to avoid agents reporting "Missing required parameters: ticker"
        if "ticker" not in workflow_inputs or not workflow_inputs.get("ticker"):
            for key in ("symbol", "code", "stock_code"):
                val = workflow_inputs.get(key)
                if val:
                    workflow_inputs["ticker"] = val
                    self.logger.debug(f"📋 参数映射: {key} → ticker = {val}")
                    break

        # 🧠 External fact memory injection: Query the unexpired fact memory related to the stock (intelligent assistant network extraction),
        # Write memory_facts_summary for debate session (bull/bear) and risk assessment session (risk_manager)
        # As a reference for analysis materials (for consumers, see the fact memory injection whitelist in core/agents/base.py).
        await self._inject_memory_facts(workflow_inputs)

        # 🆕 Read the input_config of the workflow and supplement the missing parameters according to the field definitions
        try:
            from app.core.database import get_mongo_db
            db = get_mongo_db()
            wf_doc = await db.workflows.find_one({"_id": workflow_id}, {"input_config": 1, "workflow_type": 1})
            if wf_doc and wf_doc.get("input_config"):
                fields = wf_doc["input_config"].get("fields", [])
                for field in fields:
                    fname = field.get("name")
                    if fname and fname not in workflow_inputs and fname not in ("context",):
                        default_val = field.get("default")
                        if default_val is not None:
                            workflow_inputs[fname] = default_val
                            self.logger.debug(f"📋 Supplement parameters from input_config: {fname}={default_val}")
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to read input_config, using hardcoded defaults: {e}")

        # General cover parameters (when input_config does not exist or the corresponding field is not defined)
        from datetime import datetime
        # 🔑 Note: setdefault cannot be used because API requests may be passed in analysis_date=None, 
        # setdefault Keys that already exist but have a value of None will not be overwritten, causing the downstream Agent to report an error.
        if not workflow_inputs.get("analysis_date"):
            workflow_inputs["analysis_date"] = datetime.now().strftime("%Y-%m-%d")
        workflow_inputs.setdefault("research_depth", "标准")
        workflow_inputs.setdefault("lookback_days", 30)
        workflow_inputs.setdefault("max_debate_rounds", 3)

        self.logger.info(f"📦 Workflow input parameters: ticker={workflow_inputs.get('ticker')}, "
                        f"analysis_date={workflow_inputs.get('analysis_date')}, "
                        f"research_depth={workflow_inputs.get('research_depth')}, "
                        f"selected_analysts={workflow_inputs.get('selected_analysts')}, "
                        f"user_id={agent_context.user_id}, "
                        f"preference_id={agent_context.preference_id}")

        # Prepare legacy configuration (LLM configuration, etc.)
        legacy_config = {
            "preference_type": task.preference_type,
        }

        if workflow_inputs.get("debug_mode"):
            if workflow_inputs.get("debug_llm_provider"):
                legacy_config["llm_provider"] = workflow_inputs["debug_llm_provider"]
            if workflow_inputs.get("debug_llm_backend_url"):
                legacy_config["backend_url"] = workflow_inputs["debug_llm_backend_url"]
            if workflow_inputs.get("debug_llm_api_key"):
                legacy_config["quick_api_key"] = workflow_inputs["debug_llm_api_key"]
                legacy_config["deep_api_key"] = workflow_inputs["debug_llm_api_key"]
            if workflow_inputs.get("debug_llm_temperature") is not None or workflow_inputs.get("debug_llm_max_tokens") is not None:
                debug_model_config = {
                    "temperature": workflow_inputs.get("debug_llm_temperature"),
                    "max_tokens": workflow_inputs.get("debug_llm_max_tokens"),
                    "timeout": 300 if str(workflow_inputs.get("debug_llm_provider", "")).lower() == "ollama" else 180,
                }
                legacy_config["quick_model_config"] = debug_model_config
                legacy_config["deep_model_config"] = debug_model_config

        # 🔑 Key: Extract selected_analysts from task parameters (for dynamic cropping workflow)
        if "selected_analysts" in workflow_inputs:
            legacy_config["selected_analysts"] = workflow_inputs["selected_analysts"]
            self.logger.info(f"🎯 选中的分析师: {workflow_inputs['selected_analysts']}")

        # 🧠 A1b: Depth gear → Thinking budget (passed to builder, merged with DB explicit configuration, only injected into Volcano Ark inference model)
        try:
            from app.services.simple_analysis_service import RESEARCH_DEPTH_REASONING_EFFORT
            _depth_key = str(workflow_inputs.get("research_depth") or "标准").strip()
            legacy_config["depth_reasoning_effort"] = RESEARCH_DEPTH_REASONING_EFFORT.get(_depth_key, "medium")
            self.logger.info(
                f"🧠 [reasoning_effort] 档位={_depth_key} → 思考预算默认={legacy_config['depth_reasoning_effort']}"
                f" (DB Explicit configuration takes precedence, only Volcano Ark inference model injection)"
            )
        except ImportError:
            pass

        # Extracts the LLM configuration from the task parameters; if not specified, the default value is read from the database system configuration
        quick_model = workflow_inputs.get("quick_analysis_model")
        deep_model = workflow_inputs.get("deep_analysis_model")

        if not quick_model or not deep_model:
            # Read system default model from database
            try:
                from app.core.database import get_mongo_db as _get_db
                _db = _get_db()
                _cfg = await _db.system_configs.find_one(
                    {"is_active": True}, sort=[("version", -1)]
                )
                if _cfg:
                    _default_models = _cfg.get("default_models") or {}
                    _sys_settings = _cfg.get("system_settings") or {}
                    if not quick_model:
                        quick_model = (
                            _default_models.get("quick_analysis_model")
                            or _sys_settings.get("quick_analysis_model")
                        )
                    if not deep_model:
                        deep_model = (
                            _default_models.get("deep_analysis_model")
                            or _sys_settings.get("deep_analysis_model")
                        )
                    self.logger.info(
                        f"📋 Read default model from system configuration: quick={quick_model}, deep={deep_model}"
                    )
            except Exception as _e:
                self.logger.warning(f"⚠️ Failed to read system default model: {_e}")

        if quick_model:
            legacy_config["quick_think_llm"] = quick_model
        if deep_model:
            legacy_config["deep_think_llm"] = deep_model

        # Always call _build_llm_config to get the full LLM configuration (api_key / backend_url etc.) from the database
        if quick_model or deep_model:
            full_config = await self._build_llm_config(quick_model, deep_model)
            legacy_config.update(full_config)

            if workflow_inputs.get("debug_mode"):
                if workflow_inputs.get("debug_llm_provider"):
                    legacy_config["llm_provider"] = workflow_inputs["debug_llm_provider"]
                if workflow_inputs.get("debug_llm_backend_url"):
                    legacy_config["backend_url"] = workflow_inputs["debug_llm_backend_url"]
                if workflow_inputs.get("debug_llm_api_key"):
                    legacy_config["quick_api_key"] = workflow_inputs["debug_llm_api_key"]
                    legacy_config["deep_api_key"] = workflow_inputs["debug_llm_api_key"]
                if workflow_inputs.get("debug_llm_temperature") is not None or workflow_inputs.get("debug_llm_max_tokens") is not None:
                    debug_model_config = {
                        "temperature": workflow_inputs.get("debug_llm_temperature"),
                        "max_tokens": workflow_inputs.get("debug_llm_max_tokens"),
                        "timeout": 300 if str(workflow_inputs.get("debug_llm_provider", "")).lower() == "ollama" else 180,
                    }
                    legacy_config["quick_model_config"] = debug_model_config
                    legacy_config["deep_model_config"] = debug_model_config

        self.logger.info(f"🔧 LLM Configuration: quick={legacy_config.get('quick_think_llm')}, "
                        f"deep={legacy_config.get('deep_think_llm')}, "
                        f"provider={legacy_config.get('llm_provider')}")

        # Execute the workflow (WorkflowAPI.execute is a synchronous method and needs to run in a thread)
        import asyncio

        # 🔑 Execution trace is turned on once: if the task input specifies enable_trace=true, Temporarily enable globally
        # Note: Thread local variables cannot be used because the analyst executes in a parallel sub-thread and cannot read the mark of the main thread.
        def _execute_with_trace_context():
            from app.core.config import settings
            old_value = settings.AGENT_EXECUTION_TRACE_ENABLED
            if task.task_params.get("enable_trace"):
                settings.AGENT_EXECUTION_TRACE_ENABLED = True
            try:
                return workflow_api.execute(
                    workflow_id=workflow_id,
                    inputs=workflow_inputs,
                    legacy_config=legacy_config,
                    progress_callback=wrapped_progress_callback,
                    task_id=task.task_id,
                )
            finally:
                settings.AGENT_EXECUTION_TRACE_ENABLED = old_value

        result = await asyncio.to_thread(_execute_with_trace_context)

        # Check execution results
        if not result.get("success"):
            error_msg = result.get("error", "工作流执行失败")
            raise RuntimeError(error_msg)

        return result.get("result", {})

    async def _execute_via_legacy(
        self,
        task: UnifiedAnalysisTask,
        config,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Execution via old engine (TradingAgentsGraph)— Deactivated

        v3.0 The old legacy engine has been deactivated and all entrances have been blocked.
        See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md

        Args:
            task: Task object
            config: Workflow configuration
            progress_callback: Progress callback

        Returns:
            Execution result

        Raises:
            RuntimeError: always throws (method deactivated)
        """
        raise RuntimeError(
            "[Deactivated] UnifiedAnalysisEngine._execute_via_legacy deactivated,"
            "Task %s should be executed using the workflow engine instead."
            "See details docs/99-archive/deprecated-features/legacy-agents-deprecation.md"
            % getattr(task, "task_id", "<unknown>")
        )
        # pragma: no cover - The following original code is retained but not executed in preparation for v4.0 deletion
        self.logger.info(f"🔄 Execute using old engine: TradingAgentsGraph")

        # Only supports stock analysis tasks
        if task.task_type != AnalysisTaskType.STOCK_ANALYSIS:
            raise ValueError(f"The old engine only supports stock analysis tasks, the current task type: {task.task_type}")

        # Import old engine
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        # Prepare parameters
        symbol = task.task_params.get("symbol")
        analysis_date = task.task_params.get("analysis_date")

        if not symbol:
            raise ValueError("Missing required parameter: symbol")

        # Create engine instance
        graph = TradingAgentsGraph(debug=False)

        # Perform analysis
        self.logger.info(f"📊 分析股票: {symbol} (日期: {analysis_date or '最新'})")

        # Call propagate method
        state, decision = graph.propagate(symbol, analysis_date)

        # Conversion result format
        result = {
            "engine": "legacy",
            "symbol": symbol,
            "analysis_date": analysis_date,
            "decision": decision,
            "state": state,
            "source": "TradingAgentsGraph"
        }

        return result

    async def _execute_via_llm(
        self,
        task: UnifiedAnalysisTask,
        config,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Executed via direct LLM call

        Args:
            task: Task object
            config: Workflow configuration
            progress_callback: Progress callback

        Returns:
            Execution result
        """
        self.logger.info(f"🔄 Use LLM to call execution directly")

        # Import LLM Manager
        from core.llm.llm_manager import LLMManager

        llm_manager = LLMManager()

        # Build prompt words based on task type
        prompt = self._build_prompt_for_task(task)

        # call LLM
        self.logger.info(f"💬 调用 LLM: {task.preference_type} 偏好")

        response = await llm_manager.generate(
            prompt=prompt,
            preference_type=task.preference_type,
            temperature=0.7
        )

        # Conversion result format
        result = {
            "engine": "llm",
            "task_type": task.task_type.value,
            "response": response,
            "source": "LLM直接调用"
        }

        return result

    def _build_prompt_for_task(self, task: UnifiedAnalysisTask) -> str:
        """Build prompt words for tasks

        Args:
            task: Task object

        Returns:
            Prompt word string
        """
        # Construct different prompt words based on task type
        if task.task_type == AnalysisTaskType.PORTFOLIO_HEALTH:
            return self._build_portfolio_health_prompt(task.task_params)
        elif task.task_type == AnalysisTaskType.RISK_ASSESSMENT:
            return self._build_risk_assessment_prompt(task.task_params)
        elif task.task_type == AnalysisTaskType.MARKET_OVERVIEW:
            return self._build_market_overview_prompt(task.task_params)
        else:
            # universal prompt word
            return f"""请分析以下任务：

任务类型: {task.task_type.value}
任务参数: {task.task_params}

请提供详细的分析结果。"""

    def _build_portfolio_health_prompt(self, params: Dict[str, Any]) -> str:
        """构建组合健康度分析提示词"""
        return f"""Please analyze the health of your portfolio.

Analysis points:
1. Position concentration analysis
2. Risk diversification
3. Income stability
4. Fund usage efficiency
5. overall health score

parameters: {params}

Please provide a detailed research report."""

    def _build_risk_assessment_prompt(self, params: Dict[str, Any]) -> str:
        """构建风险评估提示词"""
        return f"""Please conduct a risk assessment analysis.

Assessment Dimensions:
1. market risk
2. individual stock risk
3. Liquidity risk
4. concentration risk
5. Comprehensive risk rating

parameters: {params}

Please provide a detailed risk assessment report."""

    def _build_market_overview_prompt(self, params: Dict[str, Any]) -> str:
        """构建市场概览提示词"""
        return f"""Please provide a market overview analysis.

Analysis content:
1. overall market trend
2. Sector performance
3. Fund flow
4. market sentiment
5. Research conclusion

parameters: {params}

Please provide a detailed market research report."""

