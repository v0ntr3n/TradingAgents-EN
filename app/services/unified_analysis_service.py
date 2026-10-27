"""
Unified Analytics Services

Unify all analysis portals into WorkflowEngine + WorkflowBuilder
Support:
1. single stock analysis API
2. Batch analysis API
3. Front-end workflow debugging
4. Scheduled analysis tasks
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from app.utils.timezone import now_tz
from app.core.jdyun import is_jdyun_mode, get_jdyun_batch_max_concurrent

from app.models.analysis import (
    AnalysisParameters,
    AnalysisResult,
    AnalysisStatus,
    AnalysisTask,
    AnalysisTaskType,
    SingleAnalysisRequest,
    UnifiedAnalysisTask,
)
from app.services.memory_state_manager import (
    get_memory_state_manager,
    TaskStatus,
)
from core.workflow.default_workflow_provider import (
    DefaultWorkflowProvider,
    get_default_workflow_provider,
)
from core.workflow.engine import WorkflowEngine
from core.workflow.models import WorkflowDefinition

logger = logging.getLogger(__name__)

ETF_CODE_PREFIXES = ("50", "51", "52", "56", "58", "15", "16", "18")


def _is_cn_etf_symbol(code: Optional[str]) -> bool:
    code_str = str(code or "").strip()
    return len(code_str) == 6 and code_str.isdigit() and code_str.startswith(ETF_CODE_PREFIXES)


class UnifiedAnalysisService:
    """
    Unified Analytics Services

    All analysis portals are executed through this service, using WorkflowEngine as the execution engine.

    Usage:
        service = UnifiedAnalysisService()

        # single stock analysis
        result = await service.analyze(
            stock_code="000858",
            analysis_date="2024-01-15",
            progress_callback=lambda p, m, **kw: print(f"{p}% - {m}")
        )

        # Use specified workflow
        result = await service.analyze(
            stock_code="AAPL",
            workflow_id="my_custom_workflow",
        )
    """

    def __init__(self):
        self._workflow_provider = get_default_workflow_provider()
        self._db = None

    def _get_db(self):
        """获取数据库连接（懒加载）"""
        if self._db is None:
            try:
                from pymongo import MongoClient
                from app.core.config import settings
                client = MongoClient(settings.MONGO_URI)
                self._db = client[settings.MONGO_DB]
            except Exception as e:
                logger.warning(f"无法连接数据库: {e}")
        return self._db

    def _build_legacy_config(
        self,
        parameters: Optional[AnalysisParameters] = None,
    ) -> Dict[str, Any]:
        """
        Build legacy configuration (used by WorkflowBuilder to create Agent)

        Read LLM configuration from database and merge user parameters
        """
        config = {}

        # Get LLM configuration from database
        db = self._get_db()
        if db is not None:
            try:
                # Get active system configuration
                system_config = db.system_configs.find_one(
                    {"is_active": True},
                    sort=[("version", -1)]
                )
                if system_config:
                    config["llm_provider"] = system_config.get("llm_provider", "dashscope")
                    config["deep_think_llm"] = system_config.get("deep_think_llm", "qwen-plus")
                    config["quick_think_llm"] = system_config.get("quick_think_llm", "qwen-turbo")
            except Exception as e:
                logger.warning(f"从数据库获取配置失败: {e}")

        # Merge user parameters
        if parameters:
            if parameters.research_depth:
                # Keep research_depth as a string value for workflow inputs
                config["research_depth"] = parameters.research_depth
                # 🧠 A1b: Depth gear → Thinking budget (passed to builder, merged with DB explicit configuration, only injected into Volcano Ark inference model)
                config["depth_reasoning_effort"] = RESEARCH_DEPTH_REASONING_EFFORT.get(
                    str(parameters.research_depth).strip(), "medium"
                )

            if parameters.selected_analysts:
                config["selected_analysts"] = parameters.selected_analysts

            if parameters.market_type:
                config["market_type"] = parameters.market_type

        return config

    def _prepare_system_variables(
        self,
        stock_code: str,
        analysis_date: str
    ) -> Dict[str, Any]:
        """
        Prepare system variables (obtained uniformly at the beginning of the workflow)

        Get it from the database first, fast and not affected by API current limit

        Args:
            stock_code: Stock code
            analysis_date: Analysis date

        Returns:
            System variable dictionary
        """
        system_vars = {}

        try:
            from tradingagents.utils.stock_utils import StockUtils

            market_info = StockUtils.get_market_info(stock_code)
            is_china = market_info.get('is_china', False)

            # 1. Obtain basic stock information (company name, industry) from the database
            company_name = stock_code
            industry = "未知"

            if is_china:
                try:
                    db = self._get_db()
                    from tradingagents.utils.stock_utils import StockUtils as _SU
                    _is_fund = _SU.is_fund(stock_code)

                    # Preferably obtained from stock_basic_info; ETF downgraded to etf_basic_info
                    stock_info = db.stock_basic_info.find_one(
                        {"$or": [{"code": stock_code}, {"symbol": stock_code}]},
                        {"_id": 0, "name": 1, "industry": 1}
                    )

                    if not stock_info and _is_fund:
                        stock_info = db.etf_basic_info.find_one(
                            {"$or": [{"symbol": stock_code}, {"code": stock_code}]},
                            {"_id": 0, "name": 1, "industry": 1, "fund_type": 1}
                        )
                        if stock_info:
                            logger.info(f"📊 [System variables - database] Get fund information from etf_basic_info: {stock_code}")

                    if stock_info:
                        company_name = stock_info.get("name", stock_code)
                        industry = stock_info.get("industry", stock_info.get("fund_type", "未知"))
                        logger.info(f"📊 [系统变量-数据库] 公司名称: {company_name}, 行业: {industry}")
                    else:
                        logger.warning(f"⚠️ 数据库中未找到股票 {stock_code} 的基础信息")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to obtain basic stock information from database: {e}")

            system_vars["company_name"] = company_name
            system_vars["industry"] = industry

            # 2. Get current price from database
            current_price = "未知"

            if is_china:
                try:
                    db = self._get_db()
                    logger.info(f"🔍 [价格查询] 开始查询股票 {stock_code} 的价格...")

                    # Get the latest prices from market_quotes first
                    logger.info(f"🔍 [Price inquiry] steps 1: Query from market_quotes...")
                    quote = db.market_quotes.find_one(
                        {"$or": [{"code": stock_code}, {"symbol": stock_code}]},
                        {"_id": 0, "close": 1, "trade_date": 1},
                        sort=[("trade_date", -1)]  # Sort by date in descending order to get the latest data
                    )
                    logger.info(f"🔍 [Price inquiry] market_quotes Query results: {quote}")

                    if quote and quote.get("close"):
                        current_price = str(quote["close"])
                        logger.info(f"✅ [系统变量-数据库] 当前价格: ¥{current_price} (日期: {quote.get('trade_date', 'N/A')})")
                    else:
                        logger.info(f"🔍 [Price inquiry] market_quotes No data found, try steps 2...")
                        # For ETFs, try first etf_daily_quotes
                        from tradingagents.utils.stock_utils import StockUtils as _SU2
                        if _SU2.is_fund(stock_code):
                            logger.info(f"🔍 [Price inquiry] steps 2a: ETF, Query from etf_daily_quotes...")
                            etf_quote = db.etf_daily_quotes.find_one(
                                {"$or": [{"code": stock_code}, {"symbol": stock_code}, {"ts_code": {"$regex": f"^{stock_code}"}}]},
                                {"_id": 0, "close": 1, "trade_date": 1},
                                sort=[("trade_date", -1)]
                            )
                            logger.info(f"🔍 [Price inquiry] etf_daily_quotes Query results: {etf_quote}")
                            if etf_quote and etf_quote.get("close"):
                                current_price = str(etf_quote["close"])
                                logger.info(f"✅ [System variables - database] ETF current price: ¥{current_price}")
                        if current_price == "未知":
                            # Fallback to the current_price field of stock_basic_info
                            logger.info(f"🔍 [Price inquiry] steps 2b: Query from stock_basic_info...")
                            stock_info = db.stock_basic_info.find_one(
                                {"$or": [{"code": stock_code}, {"symbol": stock_code}]},
                                {"_id": 0, "current_price": 1}
                            )
                            logger.info(f"🔍 [Price inquiry] stock_basic_info Query results: {stock_info}")

                            if stock_info and stock_info.get("current_price"):
                                current_price = str(stock_info["current_price"])
                                logger.info(f"✅ [System variables - database] current price(Spare): ¥{current_price}")
                            else:
                                logger.warning(f"⚠️ 数据库中未找到股票 {stock_code} 的价格信息")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to get current price from database: {e}")
                    import traceback
                    traceback.print_exc()

            system_vars["current_price"] = current_price

            # 3. market information
            market_name = "A股" if is_china else "港股" if market_info.get('is_hk') else "美股"
            system_vars["market_name"] = market_name

            # 4. currency information
            if is_china:
                system_vars["currency_name"] = "人民币"
                system_vars["currency_symbol"] = "¥"
            elif market_info.get('is_hk'):
                system_vars["currency_name"] = "港币"
                system_vars["currency_symbol"] = "HK$"
            else:
                system_vars["currency_name"] = "美元"
                system_vars["currency_symbol"] = "$"

            # 5. date information
            from datetime import datetime, timedelta
            system_vars["current_date"] = analysis_date
            start_date = (datetime.strptime(analysis_date, '%Y-%m-%d') - timedelta(days=365)).strftime('%Y-%m-%d')
            system_vars["start_date"] = start_date

            # 6. 🆕 Industry/stock analysis dimension injection
            try:
                from app.services.analysis_profile_service import AnalysisProfileService

                # Query industry analysis dimensions
                if industry and industry != "未知":
                    industry_dims = AnalysisProfileService.get_industry_dimensions_sync(industry)
                    system_vars.update(industry_dims)

                # Query individual stock analysis dimensions (covering industry dimensions)
                stock_dims = AnalysisProfileService.get_stock_dimensions_sync(stock_code)
                system_vars.update(stock_dims)
            except Exception as e:
                logger.warning(f"⚠️ Failed to obtain analysis dimensions (does not affect the main process): {e}")

            logger.info(f"✅ [system variables] Ready to complete: {list(system_vars.keys())}")
            logger.info(f"   - company_name: {company_name}")
            logger.info(f"   - industry: {industry}")
            logger.info(f"   - current_price: {current_price}")
            logger.info(f"   - market_name: {market_name}")
            if system_vars.get("industry_dimensions"):
                logger.info(f"   - 🏭 Infused with industry analysis dimensions")
            if system_vars.get("stock_dimensions"):
                logger.info(f"   - 📊 Injected into individual stock analysis dimension")

        except Exception as e:
            logger.error(f"❌ 准备系统变量失败: {e}")
            import traceback
            traceback.print_exc()

        return system_vars

    def _build_workflow_inputs(
        self,
        stock_code: str,
        analysis_date: str,
        workflow: WorkflowDefinition,
        parameters: Optional[AnalysisParameters] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        research_depth = "标准"
        if parameters and getattr(parameters, "research_depth", None):
            research_depth = parameters.research_depth

        depth_mapping = {
            "快速": {"debate": 1, "risk": 1, "memory_enabled": False},  # 🔧 Quick analysis of disabled memories
            "基础": {"debate": 1, "risk": 1, "memory_enabled": True},
            "标准": {"debate": 1, "risk": 2, "memory_enabled": True},
            "深度": {"debate": 2, "risk": 2, "memory_enabled": True},
            "全面": {"debate": 3, "risk": 3, "memory_enabled": True},
        }
        depth_config = depth_mapping.get(research_depth, depth_mapping["标准"])

        # 🆕 Prepare system variables
        system_vars = self._prepare_system_variables(stock_code, analysis_date)

        inputs: Dict[str, Any] = {
            "ticker": stock_code,
            "company_of_interest": stock_code,
            "analysis_date": analysis_date,
            "trade_date": analysis_date,
            "research_depth": research_depth,
            "_max_debate_rounds": depth_config["debate"],
            "_max_risk_rounds": depth_config["risk"],
            "memory_enabled": depth_config["memory_enabled"],  # 🔧 Set memory switch according to analysis depth
            "messages": [],
            # 🆕 Process-specific prompt words: workflow_id is used by process+agent Get the corresponding prompt word template
            "workflow_id": workflow.id,
            # 🆕 Add system variables
            **system_vars,
        }

        # 🔥 Create AgentContext (supports user preferences, debugging mode and process-specific prompt words)
        from tradingagents.agents.utils.agent_context import AgentContext

        # Get user preferences
        preference_id = "neutral"
        if parameters and getattr(parameters, "preference_type", None):
            preference_id = parameters.preference_type

        # Check if it is debug mode (if there is template_id in parameters)
        is_debug_mode = False
        debug_template_id = None
        if parameters and getattr(parameters, "template_id", None):
            is_debug_mode = True
            debug_template_id = parameters.template_id

        # Create context (contains workflow_id for process+agent level prompt word loading)
        context = AgentContext(
            user_id=user_id,
            preference_id=preference_id,
            is_debug_mode=is_debug_mode,
            debug_template_id=debug_template_id,
            workflow_id=workflow.id,
        )

        inputs["context"] = context

        logger.info(
            f"🔍 [Workflow input] Create AgentContext: "
            f"user_id={user_id}, preference={preference_id}, "
            f"workflow_id={workflow.id}, debug_mode={is_debug_mode}, template_id={debug_template_id}"
        )

        if workflow.config:
            inputs.update({k: v for k, v in workflow.config.items() if k not in inputs})

        return inputs

    async def analyze(
        self,
        stock_code: str,
        analysis_date: Optional[str] = None,
        workflow_id: Optional[str] = None,
        parameters: Optional[AnalysisParameters] = None,
        progress_callback: Optional[Callable] = None,
        task_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Perform stock analysis

        Args:
            stock_code: Stock code
            analysis_date: Analysis date, default is today
            workflow_id: Workflow ID, None to use the active workflow
            parameters: Analysis parameters
            progress_callback: Progress callback function
            task_id: Task ID, used for progress tracking
            user_id: User ID (used to create AgentContext)

        Returns:
            Analysis result dictionary
        """
        # Generate tasks ID
        task_id = task_id or str(uuid.uuid4())

        # Set default date
        if not analysis_date:
            analysis_date = datetime.now().strftime("%Y-%m-%d")

        logger.info(f"开始分析: {stock_code} @ {analysis_date}, workflow={workflow_id}")

        try:
            # 1. Load workflow
            workflow = self._workflow_provider.load_workflow(workflow_id)
            logger.info(f"已加载工作流: {workflow.id} - {workflow.name}")

            # 2. Build configuration
            legacy_config = self._build_legacy_config(parameters)

            # 3. Create engine
            engine = WorkflowEngine(
                legacy_config=legacy_config,
                task_id=task_id,
            )

            # 4. Load and compile the workflow
            engine.load(workflow)

            # 5. ready to enter
            inputs = self._build_workflow_inputs(
                stock_code=stock_code,
                analysis_date=analysis_date,
                workflow=workflow,
                parameters=parameters,
                user_id=user_id,
            )

            # 5.5 Inject approved growth memory (Memory Recall)
            if user_id and inputs.get("memory_enabled", False):
                try:
                    from app.services.workflow_growth_service import get_workflow_growth_service
                    growth_svc = get_workflow_growth_service()
                    recall_text = await growth_svc.build_recall_context(
                        user_id=user_id,
                        ticker=stock_code,
                        workflow_id=workflow.id,
                    )
                    if recall_text:
                        inputs["growth_memory_recall"] = recall_text
                        logger.info(f"📝 注入成长记忆召回: {len(recall_text)} 字符")
                except Exception as e:
                    logger.warning(f"⚠️ Growth memory recall failed (does not affect analysis): {e}")

            # 5.6 mem0: Recall the user's historical analysis memory of the stock
            if user_id:
                try:
                    mem0_block = await _recall_analysis_memory(
                        self._get_db(), user_id, stock_code,
                    )
                    if mem0_block:
                        existing = inputs.get("growth_memory_recall", "")
                        inputs["growth_memory_recall"] = (
                            f"{existing}\n\n{mem0_block}" if existing else mem0_block
                        )
                        logger.info(f"📝 注入 mem0 分析记忆: {len(mem0_block)} 字符")
                except Exception as e:
                    logger.debug(f"[mem0] Analysis memory recall failed (ignored): {e}")

            # 6. Execute workflow
            result = await engine.execute_async(
                inputs=inputs,
                progress_callback=progress_callback,
            )

            logger.info(f"分析完成: {stock_code}, task_id={task_id}")

            # 7. Format results
            return self._format_result(result, stock_code, analysis_date, task_id, parameters)

        except Exception as e:
            logger.error(f"分析失败: {stock_code}, error={e}")
            return {
                "success": False,
                "task_id": task_id,
                "stock_code": stock_code,
                "error": str(e),
            }

    def analyze_sync(
        self,
        stock_code: str,
        analysis_date: Optional[str] = None,
        workflow_id: Optional[str] = None,
        parameters: Optional[AnalysisParameters] = None,
        progress_callback: Optional[Callable] = None,
        task_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous execution of stock analysis

        Used to execute in the thread pool to avoid blocking the event loop
        """
        task_id = task_id or str(uuid.uuid4())

        if not analysis_date:
            analysis_date = datetime.now().strftime("%Y-%m-%d")

        logger.info(f"[同步] 开始分析: {stock_code} @ {analysis_date}")

        try:
            # 1. Load workflow
            workflow = self._workflow_provider.load_workflow(workflow_id)

            # 2. Build configuration
            legacy_config = self._build_legacy_config(parameters)

            # 3. Create engine
            engine = WorkflowEngine(
                legacy_config=legacy_config,
                task_id=task_id,
            )

            # 4. Load and compile the workflow
            engine.load(workflow)

            # 5. ready to enter
            inputs = self._build_workflow_inputs(
                stock_code=stock_code,
                analysis_date=analysis_date,
                workflow=workflow,
                parameters=parameters,
                user_id=user_id,
            )

            # 5.5 Inject approved growth memory (synchronized path)
            if user_id and inputs.get("memory_enabled", False):
                try:
                    from app.services.workflow_growth_service import build_recall_context_sync
                    recall_text = build_recall_context_sync(
                        user_id=user_id,
                        ticker=stock_code,
                        workflow_id=workflow.id,
                    )
                    if recall_text:
                        inputs["growth_memory_recall"] = recall_text
                        logger.info(f"📝 [同步] 注入成长记忆召回: {len(recall_text)} 字符")
                except Exception as e:
                    logger.warning(f"⚠️ [sync] Growth memory recall failed (does not affect analysis): {e}")

            # 6. Synchronous execution
            result = engine.execute(
                inputs=inputs,
                progress_callback=progress_callback,
            )

            logger.info(f"[同步] 分析完成: {stock_code}")
            return self._format_result(result, stock_code, analysis_date, task_id, parameters)

        except Exception as e:
            logger.error(f"[同步] 分析失败: {stock_code}, error={e}")
            return {
                "success": False,
                "task_id": task_id,
                "stock_code": stock_code,
                "error": str(e),
            }

    def _format_result(
        self,
        raw_result: Dict[str, Any],
        stock_code: str,
        analysis_date: str,
        task_id: str,
        parameters: Optional[AnalysisParameters] = None,
    ) -> Dict[str, Any]:
        """
        Formatting analysis results - using public tools consistent with SimpleAnalysisService

        Includes all report types:
        - Basic report:market_report, sentiment_report, news_report, fundamentals_report
        - Trading plan:investment_plan, trader_investment_plan, final_trade_decision
        - Research team:bull_researcher, bear_researcher, research_team_decision
        - Risk Team:risky_analyst, safe_analyst, neutral_analyst, risk_management_decision
        """
        from app.utils.report_formatter import format_analysis_result

        # Extract model information and analyst information from parameters
        if parameters:
            analysts = parameters.selected_analysts or ["market", "fundamentals"]
            research_depth = parameters.research_depth or "标准"
            quick_model = getattr(parameters, 'quick_analysis_model', None) or getattr(parameters, 'quick_model', None) or "Unknown"
            deep_model = getattr(parameters, 'deep_analysis_model', None) or getattr(parameters, 'deep_model', None) or "Unknown"
        else:
            analysts = ["market", "fundamentals"]
            research_depth = "标准"
            quick_model = "Unknown"
            deep_model = "Unknown"

        # Extract report_manifest from raw_result (dynamically generated by WorkflowEngine)
        report_manifest = raw_result.get("report_manifest")

        result = format_analysis_result(
            raw_result=raw_result,
            stock_code=stock_code,
            stock_name=self._resolve_stock_name(stock_code),
            analysis_date=analysis_date,
            task_id=task_id,
            analysts=analysts,
            research_depth=research_depth,
            quick_model=quick_model,
            deep_model=deep_model,
            report_manifest=report_manifest,
        )

        logger.info(f"[统一引擎] 格式化结果完成: reports={len(result.get('reports', {}))}个")
        return result

    async def analyze_batch(
        self,
        stock_codes: List[str],
        analysis_date: Optional[str] = None,
        workflow_id: Optional[str] = None,
        parameters: Optional[AnalysisParameters] = None,
        progress_callback: Optional[Callable] = None,
        max_concurrent: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Analyze stocks in batches

        Args:
            stock_codes: Stock code list
            analysis_date: Analysis date
            workflow_id: Workflow ID
            parameters: Analysis parameters
            progress_callback: Progress callback
            max_concurrent: Maximum number of concurrencies

        Returns:
            Analysis result list
        """
        results = []
        total = len(stock_codes)
        completed = 0

        # 🔧 JD Cloud Mode: Reduce the number of concurrencies and avoid LLM speed limit (429)
        if is_jdyun_mode():
            jdyun_max = get_jdyun_batch_max_concurrent()
            if max_concurrent > jdyun_max:
                logger.info(f"🔧 [京东云模式] 批量分析并发数 {max_concurrent} → {jdyun_max}（避免 LLM 限速）")
                max_concurrent = jdyun_max

        # Using semaphores to control concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_one(code: str, index: int) -> Dict[str, Any]:
            nonlocal completed
            async with semaphore:
                task_id = f"batch_{uuid.uuid4().hex[:8]}_{index}"

                # Single stock progress callback
                def single_progress(progress, message, **kwargs):
                    if progress_callback:
                        # Calculate overall progress
                        overall = (completed * 100 + progress) / total
                        progress_callback(
                            overall,
                            f"[{index+1}/{total}] {code}: {message}",
                            stock_code=code,
                            **kwargs
                        )

                result = await self.analyze(
                    stock_code=code,
                    analysis_date=analysis_date,
                    workflow_id=workflow_id,
                    parameters=parameters,
                    progress_callback=single_progress,
                    task_id=task_id,
                )

                completed += 1
                return result

        # Concurrent execution
        tasks = [
            analyze_one(code, i)
            for i, code in enumerate(stock_codes)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append({
                    "success": False,
                    "stock_code": stock_codes[i],
                    "error": str(result),
                })
            else:
                final_results.append(result)

        return final_results


    async def execute_analysis_for_ab_test(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest,
        progress_tracker=None,
    ) -> Dict[str, Any]:
        """
        Analysis execution portal provided for AB testing

        with SimpleAnalysisService.execute_analysis_background() Interface compatible
        Use WorkflowEngine instead TradingAgentsGraph

        Args:
            task_id: Task ID
            user_id: User ID
            request: Analysis request
            progress_tracker: RedisProgressTracker Instance (optional, will be created automatically if not provided)

        Returns:
            Analyze results
        """
        import asyncio
        from app.services.progress.tracker import RedisProgressTracker

        stock_code = request.get_symbol()
        parameters = request.parameters
        memory_manager = get_memory_state_manager()

        try:
            logger.info(f"🔄 [AB Test-Unified Engine] Start analysis: {stock_code}, task_id={task_id}")

            # 🔥 Update memory manager status to RUNNING
            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=5,
                message="🚀 [unified engine] Starting analysis...",
                current_step="启动"
            )

            # If progress_tracker is not passed in, create it yourself
            if progress_tracker is None:
                def create_progress_tracker():
                    return RedisProgressTracker(
                        task_id=task_id,
                        analysts=parameters.selected_analysts if parameters else ["market", "fundamentals"],
                        research_depth=parameters.research_depth if parameters else "标准",
                        llm_provider="dashscope"
                    )
                progress_tracker = await asyncio.to_thread(create_progress_tracker)

            # Create a progress callback adapter
            def progress_callback(progress: float, message: str, **kwargs):
                """Convert the progress callback of the unified engine to RedisProgressTracker format"""
                if progress_tracker:
                    try:
                        # 🔑 Key: extract step_name (short name) from kwargs
                        step_name = kwargs.get("step_name", "")

                        progress_tracker.update_progress({
                            "progress_percentage": progress,
                            "last_message": message,
                            "current_step_name": step_name,  # ✅ short step name
                            "current_step_description": message,  # ✅ detailed description
                            **kwargs
                        })
                        # 🔥 Also update the memory manager (use asyncio.create_task to avoid event loop conflicts)
                        import asyncio
                        try:
                            # Get the currently running event loop
                            loop = asyncio.get_running_loop()
                            # Create background tasks without waiting for completion
                            loop.create_task(
                                memory_manager.update_task_status(
                                    task_id=task_id,
                                    status=TaskStatus.RUNNING,
                                    progress=int(progress),
                                    message=message,
                                    current_step=step_name or message  # ✅ Use step_name instead message
                                )
                            )
                        except RuntimeError:
                            # Skip memory manager updates if no event loop is running
                            logger.debug("No event loop running, memory manager updates skipped")
                    except Exception as e:
                        logger.warning(f"进度更新失败: {e}")

            # Get analysis date
            analysis_date = None
            if parameters and parameters.analysis_date:
                if isinstance(parameters.analysis_date, datetime):
                    analysis_date = parameters.analysis_date.strftime("%Y-%m-%d")
                else:
                    analysis_date = str(parameters.analysis_date)[:10]

            # Get workflow ID
            workflow_id = None
            if parameters and hasattr(parameters, "workflow_id"):
                workflow_id = parameters.workflow_id

            # Initialization progress
            await asyncio.to_thread(
                progress_tracker.update_progress,
                {"progress_percentage": 10, "last_message": "🚀 [unified engine] Start stock analysis"}
            )

            # 🔥 Update memory manager status
            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=10,
                message="🚀 [unified engine] Start stock analysis",
                current_step="开始分析"
            )

            # Call the Unified Analysis Service (all fields in _format_result are populated)
            result = await self.analyze(
                stock_code=stock_code,
                analysis_date=analysis_date,
                workflow_id=workflow_id,
                parameters=parameters,
                progress_callback=progress_callback,
                task_id=task_id,
                user_id=user_id,  # ✅ Pass user_id to create AgentContext
            )

            # Analysis completed, mark progress
            # Note:mark_completed() does not accept parameters
            await asyncio.to_thread(progress_tracker.mark_completed)

            # Save analysis results to database
            await self._save_analysis_result(task_id, user_id, stock_code, result, parameters)

            # mem0: Asynchronous storage analysis insights
            asyncio.create_task(
                _store_analysis_insight(
                    self._get_db(), user_id, stock_code,
                    analysis_date,
                    result.get("summary", ""),
                    result.get("recommendation", ""),
                    task_id,
                )
            )

            # 🔥 Update memory manager status to COMPLETED
            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="✅ 分析完成",
                current_step="完成",
                result_data=result
            )

            logger.info(f"✅ [AB Test-Unified Engine] Analysis completed: {stock_code}")
            return result

        except Exception as e:
            logger.error(f"❌ [AB Test-Unified Engine] Analysis failed: {stock_code}, error={e}")

            # Marking progress tracker failed
            if progress_tracker:
                try:
                    await asyncio.to_thread(progress_tracker.mark_failed, str(e))
                except Exception:
                    pass

            # 🔥 Update memory manager status to FAILED
            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.FAILED,
                message=f"❌ 分析失败: {str(e)}",
                error_message=str(e)
            )

            # Update database status failed
            await self._update_task_failed(task_id, str(e))
            raise

    async def execute_analysis_for_v2_engine(
        self,
        task_id: str,
        user_id: str,
        request: SingleAnalysisRequest,
        progress_tracker=None,
    ) -> Dict[str, Any]:
        import asyncio
        from app.services.progress.tracker import RedisProgressTracker

        stock_code = request.get_symbol()
        parameters = request.parameters
        memory_manager = get_memory_state_manager()

        try:
            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=5,
                message="🚀 [v2.0 engine] Starting analysis...",
                current_step="启动"
            )

            if progress_tracker is None:
                def create_progress_tracker():
                    return RedisProgressTracker(
                        task_id=task_id,
                        analysts=parameters.selected_analysts if parameters else ["market", "fundamentals"],
                        research_depth=parameters.research_depth if parameters else "标准",
                        llm_provider="dashscope"
                    )
                progress_tracker = await asyncio.to_thread(create_progress_tracker)

            def progress_callback(progress: float, message: str, **kwargs):
                if progress_tracker:
                    try:
                        progress_tracker.update_progress({
                            "progress_percentage": progress,
                            "last_message": message,
                            **kwargs
                        })
                        import asyncio
                        try:
                            # Get the currently running event loop
                            loop = asyncio.get_running_loop()
                            # Create background tasks without waiting for completion
                            loop.create_task(
                                memory_manager.update_task_status(
                                    task_id=task_id,
                                    status=TaskStatus.RUNNING,
                                    progress=int(progress),
                                    message=message,
                                    current_step=kwargs.get("step", "分析中")
                                )
                            )
                        except RuntimeError:
                            # Skip memory manager updates if no event loop is running
                            logger.debug("No event loop running, memory manager updates skipped")
                    except Exception as e:
                        logger.warning(f"进度更新失败: {e}")

            analysis_date = None
            if parameters and parameters.analysis_date:
                if isinstance(parameters.analysis_date, datetime):
                    analysis_date = parameters.analysis_date.strftime("%Y-%m-%d")
                else:
                    analysis_date = str(parameters.analysis_date)[:10]

            workflow_id = None
            if parameters and hasattr(parameters, "workflow_id"):
                workflow_id = parameters.workflow_id
            if not workflow_id:
                workflow_id = self._workflow_provider.get_active_workflow_id("stock_analysis")

            try:
                wf = self._workflow_provider.load_workflow(workflow_id)
                tags = getattr(wf, "tags", []) or []
                wf_id = str(getattr(wf, "id", "") or "")
                wf_name = str(getattr(wf, "name", "") or "")
                wf_version = str(getattr(wf, "version", "") or "")
                is_v2 = (
                    "v2.0" in tags
                    or wf_id.endswith("_v2")
                    or "v2.0" in wf_name
                    or wf_version.startswith("2.")
                )
                if not is_v2:
                    workflow_id = "v2_stock_analysis"
            except Exception:
                workflow_id = "v2_stock_analysis"

            await asyncio.to_thread(
                progress_tracker.update_progress,
                {"progress_percentage": 10, "last_message": "🚀 [v2.0 engine] Start stock analysis"}
            )

            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress=10,
                message="🚀 [v2.0 engine] Start stock analysis",
                current_step="开始分析"
            )


            result = await self.analyze(
                stock_code=stock_code,
                analysis_date=analysis_date,
                workflow_id=workflow_id,
                parameters=parameters,
                progress_callback=progress_callback,
                task_id=task_id,
            )

            await asyncio.to_thread(progress_tracker.mark_completed)
            await self._save_analysis_result(task_id, user_id, stock_code, result, parameters)

            # mem0: Asynchronous storage analysis insights
            asyncio.create_task(
                _store_analysis_insight(
                    self._get_db(), user_id, stock_code,
                    analysis_date,
                    result.get("summary", ""),
                    result.get("recommendation", ""),
                    task_id,
                )
            )

            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="✅ 分析完成",
                current_step="完成",
                result_data=result
            )

            return result
        except Exception as e:
            logger.error(f"❌ [v2.0 engine] Analysis failed: {stock_code}, error={e}")
            if progress_tracker:
                try:
                    await asyncio.to_thread(progress_tracker.mark_failed, str(e))
                except Exception:
                    pass
            await memory_manager.update_task_status(
                task_id=task_id,
                status=TaskStatus.FAILED,
                message=f"❌ 分析失败: {str(e)}",
                error_message=str(e)
            )
            await self._update_task_failed(task_id, str(e))
            raise

    async def _save_analysis_result(
        self,
        task_id: str,
        user_id: str,
        stock_code: str,
        result: Dict[str, Any],
        parameters=None
    ):
        """
        Save analysis results to MongoDB - consistent format with SimpleAnalysisService
        """
        db = self._get_db()
        if db is None:
            logger.warning("Unable to save analysis results: Database not connected")
            return

        try:
            timestamp = now_tz()  # ✅ Use now_tz() Make sure to include time zone information
            analysis_id = result.get("analysis_id", str(uuid.uuid4()))

            # Get stock name
            stock_name = self._resolve_stock_name(stock_code)
            market_type = "A股" if stock_code.isdigit() and len(stock_code) == 6 else "美股"

            # 🔥 Clean duplicate data in reports (if present)
            reports_raw = result.get("reports", {})
            cleaned_reports = {}
            if isinstance(reports_raw, dict):
                for key, value in reports_raw.items():
                    # Skip structured_reports (if present to avoid duplication)
                    if key != "structured_reports":
                        cleaned_reports[key] = value

            # Update analysis_tasks status
            db.analysis_tasks.update_one(
                {"task_id": task_id},
                {
                    "$set": {
                        "status": "completed",
                        "progress": 100,
                        "completed_at": timestamp,
                        "updated_at": timestamp,
                        # 🔥 Save complete result to analysis_tasks (consistent with SimpleAnalysisService)
                        "result": {
                            "analysis_id": analysis_id,
                            "stock_symbol": stock_code,
                            "stock_code": stock_code,
                            "analysis_date": result.get("analysis_date"),
                            "summary": result.get("summary", ""),
                            "recommendation": result.get("recommendation", ""),
                            "confidence_score": result.get("confidence_score", 0.0),
                            "risk_level": result.get("risk_level", "中等"),
                            "key_points": result.get("key_points", []),
                            # 🔥 Note: detailed_analysis and state saved to the database here are used for debugging/auditing
                            # However, when the API returns, it will be decided based on the query parameters whether to include
                            "detailed_analysis": result.get("detailed_analysis", {}),
                            "state": result.get("state", {}),
                            "execution_time": result.get("execution_time", 0),
                            "tokens_used": result.get("tokens_used", 0),
                            "reports": cleaned_reports,  # 🔥 Use the cleaned reports
                            "decision": result.get("decision", {}),
                        }
                    }
                }
            )

            # 🔥 Clean duplicate data in reports (if present)
            reports_raw = result.get("reports", {})
            cleaned_reports = {}
            if isinstance(reports_raw, dict):
                for key, value in reports_raw.items():
                    # Skip structured_reports (if present to avoid duplication)
                    if key != "structured_reports":
                        cleaned_reports[key] = value

            # 🔥 Save to analysis_reports (same format as SimpleAnalysisService)
            document = {
                "analysis_id": analysis_id,
                "stock_symbol": stock_code,
                "stock_name": result.get("stock_name", stock_name),  # Give priority to names in result
                "market_type": market_type,
                "model_info": result.get("model_info", "Unknown"),
                "quick_model": result.get("quick_model", "Unknown"),  # 🔥 Add quick model fields
                "deep_model": result.get("deep_model", "Unknown"),    # 🔥 Add depth model field
                "analysis_date": timestamp.strftime('%Y-%m-%d'),
                "timestamp": timestamp,
                "status": "completed",
                "source": "api",
                "engine": (getattr(parameters, "engine", None) or "unified"),

                # Summary of analysis results
                "summary": result.get("summary", ""),
                "analysts": result.get("analysts", []),
                "research_depth": result.get("research_depth", "标准"),

                # Report content (use cleaned reports to avoid duplicate data)
                "reports": cleaned_reports,

                # 🔥 Key: decision field
                "decision": result.get("decision", {}),

                # metadata
                "task_id": task_id,
                "user_id": user_id,
                "created_at": timestamp,
                "updated_at": timestamp,

                # Other fields
                "recommendation": result.get("recommendation", ""),
                "confidence_score": result.get("confidence_score", 0.0),
                "risk_level": result.get("risk_level", "中等"),
                "key_points": result.get("key_points", []),
                "execution_time": result.get("execution_time", 0),
                "tokens_used": result.get("tokens_used", 0),
            }

            db.analysis_reports.update_one(
                {"task_id": task_id},
                {"$set": document},
                upsert=True
            )
            logger.info(f"✅ Analysis results have been saved to the database: {task_id}")
            logger.debug(f"📊 saved decision: {result.get('decision', {})}")
        except Exception as e:
            logger.error(f"❌ 保存分析结果失败: {e}")

    def _resolve_stock_name(self, stock_code: str) -> str:
        """Parse stock names - logic consistent with SimpleAnalysisService"""
        if not stock_code:
            return ""

        try:
            db = self._get_db()
            code_str = str(stock_code).strip().zfill(6)

            if db is not None:
                if _is_cn_etf_symbol(code_str):
                    etf_doc = db.etf_basic_info.find_one(
                        {"code": code_str},
                        {"name": 1, "fund_name": 1, "etf_name": 1, "_id": 0}
                    )
                    if etf_doc:
                        etf_name = etf_doc.get("name") or etf_doc.get("fund_name") or etf_doc.get("etf_name")
                        if etf_name:
                            return etf_name

                stock_doc = db.stock_basic_info.find_one(
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

            # Alternative: Get string from interface and parse
            from tradingagents.dataflows.interface import get_china_stock_info_unified
            info_str = get_china_stock_info_unified(stock_code)

            if info_str and isinstance(info_str, str) and "股票名称:" in info_str:
                stock_name = info_str.split("股票名称:")[1].split("\n")[0].strip()
                if stock_name:
                    return stock_name
            elif info_str and isinstance(info_str, dict) and info_str.get("name"):
                return info_str["name"]

        except Exception as e:
            logger.warning(f"⚠️ 解析股票名称失败: {stock_code} - {e}")

        return f"{'ETF' if _is_cn_etf_symbol(stock_code) else 'stocks'}{stock_code}"

    # ==================== Position analysis related methods ====================

    async def create_position_analysis_task(
        self,
        user_id: str,
        code: str,
        market: str = "CN",
        task_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a position analysis task

        Args:
            user_id: User ID
            code: Stock code
            market: market type (CN/HK/US)
            task_params: Task parameters

        Returns:
            Task information dictionary
        """
        logger.info(f"🔧 [Position analysis service] create_position_analysis_task called: user_id={user_id}, code={code}, market={market}")
        from bson import ObjectId
        from app.core.database import get_mongo_db

        task_id = str(uuid.uuid4())
        logger.info(f"📝 [Position analysis service] Generate tasks ID: {task_id}")
        task_params = task_params or {}

        # 🔥 Read risk preference settings from user preferences
        from app.routers.analysis import get_user_risk_preference
        preference_type = await get_user_risk_preference(user_id)
        logger.info(f"📊 [Position analysis service] Use user risk preferences: {preference_type}")

        # Create unified analysis tasks
        logger.info(f"🔄 [Position analysis service] Create a UnifiedAnalysisTask object...")
        task = UnifiedAnalysisTask(
            task_id=task_id,
            user_id=ObjectId(user_id),
            task_type=AnalysisTaskType.POSITION_ANALYSIS,
            task_params={
                "code": code,
                "market": market,
                **task_params
            },
            engine_type="v2",  # Using v2.0 engine
            preference_type=preference_type,  # 🔥 Use user preferences
            status=AnalysisStatus.PENDING,
            created_at=now_tz(),  # ✅ Use now_tz() Make sure to include time zone information
        )

        # Save to database
        logger.info(f"💾 [Position analysis service] Prepare to save to database...")
        try:
            db = get_mongo_db()
            task_dict = task.model_dump(by_alias=True, exclude={"id"})

            # ✅ Make sure user_id is of type ObjectId, not a string
            if 'user_id' in task_dict and isinstance(task_dict['user_id'], str):
                task_dict['user_id'] = ObjectId(task_dict['user_id'])
                logger.info(f"🔄 [Position analysis service] Convert user_id from string to ObjectId: {task_dict['user_id']}")

            logger.info(f"💾 [持仓分析服务] 保存文档: user_id={task_dict.get('user_id')} (类型: {type(task_dict.get('user_id'))})")

            await db.unified_analysis_tasks.insert_one(task_dict)
            logger.info(f"✅ [Position analysis service] Saved to database, task ID: {task_id}")
            logger.info(f"✅ [Position analysis service] Task has been created: {task_id} - {code}")
        except Exception as e:
            logger.error(f"❌ [Position analysis] Failed to save task: {e}")
            raise

        # Save to memory state manager
        logger.info(f"💾 [Position analysis service] Prepare to save to memory state manager...")
        memory_manager = get_memory_state_manager()
        await memory_manager.create_task(
            task_id=task_id,
            user_id=user_id,
            stock_code=code,
            stock_name=f"{code} 持仓分析",
            parameters=task_params,
        )
        logger.info(f"✅ [Position analysis service] Saved to memory state manager")

        logger.info(f"🎉 [Position analysis service] The task is created and results are ready to be returned.")
        return {
            "task_id": task_id,
            "code": code,
            "market": market,
            "status": "pending",
            "message": "The position analysis task has been created and is expected to take 2-5 minutes.",
            "created_at": task.created_at.isoformat()
        }

    async def execute_position_analysis(
        self,
        task_id: str,
        user_id: str,
        code: str,
        market: str = "CN",
        task_params: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Perform position analysis

        Args:
            task_id: Task ID
            user_id: User ID
            code: Stock code
            market: market type
            task_params: Task parameters
            progress_callback: Progress callback function

        Returns:
            Analysis result dictionary
        """
        logger.info(f"🚀 [Position analysis service] execute_position_analysis called: task_id={task_id}, code={code}")
        logger.info(f"📋 [Position analysis service] Task parameters: {task_params}")

        try:
            # Update task status to Processing
            await self._update_position_task_status(
                task_id=task_id,
                status=AnalysisStatus.PROCESSING,
                message="正在分析持仓..."
            )

            # Call the position analysis service
            from app.services.portfolio_service import get_portfolio_service
            from app.models.portfolio import PositionAnalysisByCodeRequest

            portfolio_service = get_portfolio_service()

            # Build an analysis request
            task_params = task_params or {}
            analysis_request = PositionAnalysisByCodeRequest(
                code=code,
                market=market,
                research_depth=task_params.get("research_depth", "标准"),
                include_add_position=task_params.get("include_add_position", True),
                target_profit_pct=task_params.get("target_profit_pct", 20.0),
                total_capital=task_params.get("total_capital"),
                max_position_pct=task_params.get("max_position_pct", 30.0),
                max_loss_pct=task_params.get("max_loss_pct", 10.0),
                risk_tolerance=task_params.get("risk_tolerance", "medium"),
                investment_horizon=task_params.get("investment_horizon", "medium"),
                analysis_focus=task_params.get("analysis_focus", "comprehensive"),
                position_type=task_params.get("position_type", "real"),
            )

            # Perform analysis
            report = await portfolio_service.analyze_position_by_code(
                user_id=user_id,
                code=code,
                market=market,
                params=analysis_request
            )

            # Format results
            result = {
                "success": True,
                "task_id": task_id,
                "code": code,
                "market": market,
                "analysis_id": report.analysis_id,
                "position_snapshot": report.position_snapshot.model_dump() if report.position_snapshot else None,
                "ai_analysis": report.ai_analysis.model_dump() if report.ai_analysis else None,
                "status": report.status.value,
                "execution_time": report.execution_time,
                "error_message": report.error_message,
            }

            # Update task status to complete
            await self._update_position_task_status(
                task_id=task_id,
                status=AnalysisStatus.COMPLETED if report.status.value == "completed" else AnalysisStatus.FAILED,
                message="持仓分析完成" if report.status.value == "completed" else report.error_message,
                result=result
            )

            if report.status.value == "completed":
                try:
                    from app.services.intelligent_assistant_service import write_report_back_to_assistant_thread

                    preferred_thread_id = ((task_params or {}).get("_assistant_thread_id") or "").strip() or None
                    report_summary = ((report.ai_analysis.action_reason if report.ai_analysis else "") or "")[:400]
                    writeback_message = (
                        f"【持仓分析已归档】{code}({market})\n"
                        f"Task ID: {task_id}\n"
                        f"Summary: {(report_summary or 'The position analysis is completed and can be viewed in the associated report.')[:300]}"
                    )
                    await write_report_back_to_assistant_thread(
                        db=get_mongo_db(),
                        user_id=user_id,
                        preferred_thread_id=preferred_thread_id,
                        report_ref={
                            "ref_type": "position_report",
                            "report_key": str(report.analysis_id or task_id),
                            "source_collection": "position_analysis_reports",
                            "title": f"{code} 持仓分析报告",
                            "symbol": code,
                            "summary": report_summary,
                            "status": report.status.value,
                            "task_id": task_id,
                            "analysis_id": str(report.analysis_id),
                            "created_at": now_tz(),
                        },
                        summary_message=writeback_message,
                    )
                except Exception as writeback_err:
                    logger.warning(f"⚠️ [Position analysis] Failed to write back research topic (ignored): {writeback_err}")

            logger.info(f"✅ [Position analysis] Execution completed: {task_id} - {code}")
            return result

        except Exception as e:
            logger.error(f"❌ [Position analysis] Execution failed: {task_id} - {e}", exc_info=True)

            # Update task status is failed
            await self._update_position_task_status(
                task_id=task_id,
                status=AnalysisStatus.FAILED,
                message=f"持仓分析失败: {str(e)}"
            )

            return {
                "success": False,
                "task_id": task_id,
                "code": code,
                "error": str(e),
            }

    async def _update_position_task_status(
        self,
        task_id: str,
        status: AnalysisStatus,
        message: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
    ):
        """更新持仓分析任务状态"""
        from app.core.database import get_mongo_db

        try:
            db = get_mongo_db()

            update_data = {
                "status": status.value if hasattr(status, "value") else status,  # Make sure to store as string value
                "message": message,
                "updated_at": now_tz(),  # ✅ Use now_tz() Make sure to include time zone information
            }

            if status == AnalysisStatus.PROCESSING:
                update_data["started_at"] = now_tz()  # ✅ Use now_tz() Make sure to include time zone information
            elif status in [AnalysisStatus.COMPLETED, AnalysisStatus.FAILED]:
                update_data["completed_at"] = now_tz()  # ✅ Use now_tz() Make sure to include time zone information

            if result is not None:
                update_data["result"] = result

            await db.unified_analysis_tasks.update_one(
                {"task_id": task_id},
                {"$set": update_data}
            )

            # Update memory status
            memory_manager = get_memory_state_manager()
            memory_status = TaskStatus.RUNNING if status == AnalysisStatus.PROCESSING else (
                TaskStatus.COMPLETED if status == AnalysisStatus.COMPLETED else TaskStatus.FAILED
            )
            await memory_manager.update_task_status(
                task_id=task_id,
                status=memory_status,
                message=message or "",
            )

        except Exception as e:
            logger.error(f"❌ [Position analysis] Failed to update task status: {e}")

    # ==================== Methods related to transaction review ====================

    async def create_trade_review_task(
        self,
        user_id: str,
        request: "CreateTradeReviewRequest",
    ) -> Dict[str, Any]:
        """Create a transaction review task

        Reference:create_position_analysis_task() realization

        Args:
            user_id: User ID
            request: Review request

        Returns:
            Task information dictionary {"task_id": "...", "status": "pending"}
        """
        logger.info(f"🔧 [Transaction review service] create_trade_review_task called")
        logger.info(f"   📋 user_id: {user_id}")
        logger.info(f"   📋 code: {request.code}")
        logger.info(f"   📋 trade_ids: {request.trade_ids}")
        logger.info(f"   📋 review_type: {request.review_type}")
        logger.info(f"   📋 source: {request.source}")
        logger.info(f"   📋 use_workflow: {request.use_workflow}")

        from bson import ObjectId
        from app.core.database import get_mongo_db

        task_id = str(uuid.uuid4())
        logger.info(f"📝 [Transaction review service] Generate tasks ID: {task_id}")

        # Get stock name
        stock_code = request.code or "未知"
        stock_name = self._resolve_stock_name(stock_code) if stock_code != "未知" else "未知股票"
        logger.info(f"📊 [Transaction review service] stock information: code={stock_code}, name={stock_name}")

        # 🔑 Extract market field from transaction information (quick inference, no waiting for database query)
        market = None
        # Prioritize inference from code (Chinese stock codes are usually 6 digits) to avoid database query delays
        if stock_code:
            if len(stock_code) == 6 and stock_code.isdigit():
                # China's stock code: starting with 6 is the Science and Technology Innovation Board, starting with 0/3 is the GEM/Shenzhen Stock Exchange, and starting with 6 is the Shanghai Stock Exchange
                market = "CN"
                logger.info(f"📊 [Transaction review service] Inferred from stock ticker market: {market}")
            elif stock_code.startswith("HK"):
                market = "HK"
            elif stock_code.startswith("US") or "." in stock_code:
                market = "US"
        
        # If no market is inferred, use the default value (CN)
        if not market:
            market = "CN"
            logger.info(f"📊 [Transaction review service] Use default market: {market}")
        
        # Note: The precise extraction of market information will be completed in the background task. Only quick inference is done here to ensure immediate return.
        
        # Prepare task parameters
        task_params = {
            "trade_ids": request.trade_ids,
            "stock_code": stock_code,  # Use stock_code instead code
            "code": request.code,  # Keep original fields for compatibility
            "stock_name": stock_name,  # Add stock name
            "market": market,  # 🔑 Add market field
            "market_type": market,  # 🔑 Compatible fields
            "review_type": request.review_type,
            "source": request.source or "paper",
            "trading_system_id": request.trading_system_id,
            "use_workflow": request.use_workflow
        }
        logger.info(f"📦 [Transaction review service] Task parameters: {task_params}")

        # Create unified analysis tasks
        logger.info(f"🔄 [Transaction review service] Create a UnifiedAnalysisTask object...")
        task = UnifiedAnalysisTask(
            task_id=task_id,
            user_id=ObjectId(user_id),
            task_type=AnalysisTaskType.TRADE_REVIEW,
            task_params=task_params,
            engine_type="workflow" if request.use_workflow else "auto",
            status=AnalysisStatus.PENDING,
            created_at=now_tz(),
        )
        logger.info(f"✅ [Transaction review service] UnifiedAnalysisTask Object created successfully")
        logger.info(f"   📋 task_type: {task.task_type}")
        logger.info(f"   📋 engine_type: {task.engine_type}")
        logger.info(f"   📋 status: {task.status}")

        # Save to database
        logger.info(f"💾 [Transaction review service] Prepare to save to database...")
        try:
            db = get_mongo_db()
            logger.info(f"✅ [Transaction review service] Obtain database connection successfully")

            task_dict = task.model_dump(by_alias=True, exclude={"id"})
            logger.info(f"📦 [Transaction review service] task dictionary: {list(task_dict.keys())}")

            # Make sure user_id is of type ObjectId
            if 'user_id' in task_dict and isinstance(task_dict['user_id'], str):
                logger.info(f"🔄 [Transaction review service] Convert user_id to ObjectId")
                task_dict['user_id'] = ObjectId(task_dict['user_id'])

            await db.unified_analysis_tasks.insert_one(task_dict)
            logger.info(f"✅ [Transaction review service] Task saved to database: {task_id}")
        except Exception as e:
            logger.error(f"❌ [Transaction review service] Failed to save task to database: {e}", exc_info=True)
            raise

        # Save to memory state manager
        logger.info(f"💾 [Transaction review service] Prepare to save to memory state manager...")
        try:
            memory_manager = get_memory_state_manager()
            logger.info(f"✅ [Transaction review service] Obtain memory status manager successfully")

            await memory_manager.create_task(
                task_id=task_id,
                user_id=user_id,
                stock_code=stock_code,  # Use what you have obtained previously stock_code
                stock_name=stock_name,  # Use what you have obtained previously stock_name
                parameters=task_params
            )
            logger.info(f"✅ [Transaction review service] Task saved to memory: {task_id}")
        except Exception as e:
            logger.error(f"❌ [Transaction review service] Failed to save task to memory: {e}", exc_info=True)
            # Memory status failure does not affect the main process and continues execution.

        result = {
            "task_id": task_id,
            "status": AnalysisStatus.PENDING.value,
            "message": "The transaction review task has been created and is expected to take 1-3 minutes.",
            "created_at": task.created_at.isoformat()
        }
        logger.info(f"🎉 [Transaction review service] create_trade_review_task Complete")
        logger.info(f"   📋 返回结果: {result}")

        return result

    async def execute_trade_review(
        self,
        task_id: str,
        user_id: str,
        request: "CreateTradeReviewRequest",
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Perform transaction review tasks

        Reference:execute_position_analysis() realization

        Args:
            task_id: Task ID
            user_id: User ID
            request: Review request
            progress_callback: Progress callback function

        Returns:
            Analysis result dictionary
        """
        logger.info(f"🚀 [Transaction review service] execute_trade_review called")
        logger.info(f"   📋 task_id: {task_id}")
        logger.info(f"   📋 user_id: {user_id}")
        logger.info(f"   📋 trade_ids: {request.trade_ids}")
        logger.info(f"   📋 code: {request.code}")
        logger.info(f"   📋 review_type: {request.review_type}")
        logger.info(f"   📋 source: {request.source}")
        logger.info(f"   📋 use_workflow: {request.use_workflow}")

        try:
            # Update task status to Processing
            logger.info(f"🔄 [Transaction review service] Update task status to PROCESSING...")
            await self._update_trade_review_task_status(
                task_id=task_id,
                status=AnalysisStatus.PROCESSING,
                message="正在进行交易复盘..."
            )
            logger.info(f"✅ [Transaction review service] The task status has been updated to PROCESSING")

            # 🔥 Create a wrapped progress callback: save progress to database and memory
            from app.services.memory_state_manager import get_memory_state_manager, TaskStatus
            memory_manager = get_memory_state_manager()

            async def wrapped_progress_callback(progress: int, message: str, **kwargs):
                """Wrapped progress callback: update task progress and save to database and memory"""
                step_name = kwargs.get("step_name", "")

                # Update memory state manager
                await memory_manager.update_task_status(
                    task_id=task_id,
                    status=TaskStatus.RUNNING,
                    progress=progress,
                    message=message,
                    current_step=step_name or message,
                    current_step_name=step_name,
                    current_step_description=message
                )

                # Update task progress in database
                from app.core.database import get_mongo_db
                db = get_mongo_db()
                await db.unified_analysis_tasks.update_one(
                    {"task_id": task_id},
                    {"$set": {
                        "progress": progress,
                        "current_step": step_name or message,
                        "message": message
                    }}
                )

                logger.info(f"📊 [Transaction review] Progress saved: {progress}% - {step_name} - {message}")

                # Call the original callback (if any)
                if progress_callback:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback(progress, message, **kwargs)
                    else:
                        progress_callback(progress, message, **kwargs)

            # Call existing review service
            logger.info(f"🔄 [Transaction review service] Get TradeReviewService instance...")
            from app.services.trade_review_service import get_trade_review_service

            trade_review_service = get_trade_review_service()
            logger.info(f"✅ [Transaction review service] TradeReviewService Instance obtained successfully")

            # Perform review (using existing logic)
            logger.info(f"🔄 [Transaction review service] call TradeReviewService.create_trade_review()...")
            logger.info(f"   📋 This will use existing review logic (including the workflow engine)")

            report = await trade_review_service.create_trade_review(
                user_id=user_id,
                request=request,
                progress_callback=wrapped_progress_callback  # 🔥 Pass progress callback
            )
            logger.info(f"✅ [Transaction review service] TradeReviewService.create_trade_review() Executed successfully")
            logger.info(f"   📋 review_id: {report.review_id}")
            logger.info(f"   📋 status: {report.status}")
            logger.info(f"   📋 code: {report.trade_info.code}")
            logger.info(f"   📋 name: {report.trade_info.name}")
            logger.info(f"   📋 execution_time: {report.execution_time}s")

            # Format results
            logger.info(f"🔄 [Transaction review service] Format results...")
            result = {
                "success": True,
                "task_id": task_id,
                "review_id": report.review_id,
                "code": report.trade_info.code,
                "name": report.trade_info.name,
                "ai_review": report.ai_review.model_dump() if report.ai_review else None,
                "trade_info": report.trade_info.model_dump(),
                "market_snapshot": report.market_snapshot.model_dump() if report.market_snapshot else None,
                "status": report.status.value,
                "execution_time": report.execution_time
            }
            logger.info(f"✅ [Transaction review service] Result formatting completed")

            # Update task status to complete
            logger.info(f"🔄 [Transaction review service] Update task status to COMPLETED...")
            # 🔑 Pass execution_time to avoid recalculation
            await self._update_trade_review_task_status(
                task_id=task_id,
                status=AnalysisStatus.COMPLETED,
                result=result,
                message="复盘完成",
                execution_time=report.execution_time  # 🔑 Use report in execution_time
            )
            logger.info(f"✅ [Transaction review service] The task status has been updated to COMPLETED")

            logger.info(f"🎉 [Transaction review service] Task execution successful: {task_id}")
            logger.info(f"   📋 总耗时: {report.execution_time}s")

            return result

        except Exception as e:
            logger.error(f"❌ [Transaction review service] Task execution failed: {task_id}")
            logger.error(f"   📋 错误类型: {type(e).__name__}")
            logger.error(f"   📋 错误信息: {str(e)}")
            logger.error(f"   📋 详细堆栈:", exc_info=True)

            # Update task status is failed
            logger.info(f"🔄 [Transaction review service] Update task status to FAILED...")
            await self._update_trade_review_task_status(
                task_id=task_id,
                status=AnalysisStatus.FAILED,
                error_message=str(e),
                message=f"复盘失败: {str(e)}"
            )
            logger.info(f"✅ [Transaction review service] The task status has been updated to FAILED")

            # Return wrong result
            error_result = {
                "success": False,
                "task_id": task_id,
                "error": str(e),
            }
            logger.info(f"📋 [Transaction review service] Return wrong result: {error_result}")

            return error_result

    async def _update_trade_review_task_status(
        self,
        task_id: str,
        status: AnalysisStatus,
        message: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        execution_time: Optional[float] = None,  # 🔑 New parameter: execution time
    ):
        """Update transaction review task status

        Reference:_update_position_task_status() realization
        """
        logger.info(f"🔄 [Transaction review service] _update_trade_review_task_status called")
        logger.info(f"   📋 task_id: {task_id}")
        logger.info(f"   📋 status: {status}")
        logger.info(f"   📋 message: {message}")
        logger.info(f"   📋 has_result: {result is not None}")
        logger.info(f"   📋 error_message: {error_message}")

        from app.core.database import get_mongo_db

        try:
            # Update database
            logger.info(f"💾 [Transaction review service] Prepare to update the database...")
            db = get_mongo_db()
            logger.info(f"✅ [Transaction review service] Obtain database connection successfully")

            update_data = {
                "status": status.value if hasattr(status, "value") else status,
                "message": message,
                "updated_at": now_tz(),
            }

            if status == AnalysisStatus.PROCESSING:
                update_data["started_at"] = now_tz()
                logger.info(f"   📋 settings started_at: {update_data['started_at']}")
            elif status in [AnalysisStatus.COMPLETED, AnalysisStatus.FAILED]:
                completed_at = now_tz()
                update_data["completed_at"] = completed_at
                logger.info(f"   📋 settings completed_at: {completed_at}")
                
                # 🔑 settings execution_time
                if execution_time is not None:
                    # If execution_time is passed in, use it directly
                    update_data["execution_time"] = execution_time
                    logger.info(f"   📋 Use the incoming execution_time: {execution_time:.2f}s")
                else:
                    # Otherwise calculate execution_time
                    task_doc = await db.unified_analysis_tasks.find_one({"task_id": task_id})
                    if task_doc and task_doc.get("started_at"):
                        started_at = task_doc["started_at"]
                        if isinstance(started_at, str):
                            from datetime import datetime
                            started_at = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                        
                        # 🔥 Ensure consistent time zones: use ensure_timezone to unify time zones
                        # completed_at is offset-aware (from now_tz()) , started_at It also needs to be offset-aware
                        from app.utils.timezone import ensure_timezone
                        started_at = ensure_timezone(started_at)
                        completed_at = ensure_timezone(completed_at)
                        
                        calculated_time = (completed_at - started_at).total_seconds()
                        update_data["execution_time"] = calculated_time
                        logger.info(f"   📋 Calculate execution_time: {calculated_time:.2f}s (started_at: {started_at}, completed_at: {completed_at})")
                    else:
                        logger.warning(f"   ⚠️ Unable to calculate execution_time: started_at does not exist")
                
                # 🔑 Make sure progress is 100 (if completed)
                if status == AnalysisStatus.COMPLETED:
                    update_data["progress"] = 100
                    logger.info(f"   📋 settings progress: 100")

            if result is not None:
                update_data["result"] = result
                logger.info(f"   📋 设置 result (包含 {len(result)} 个字段)")

            if error_message is not None:
                update_data["error_message"] = error_message
                logger.info(f"   📋 settings error_message: {error_message}")

            logger.info(f"🔄 [Transaction review service] Perform database updates...")
            await db.unified_analysis_tasks.update_one(
                {"task_id": task_id},
                {"$set": update_data}
            )
            logger.info(f"✅ [Transaction review service] Database update successful")

            # Update memory status
            logger.info(f"💾 [Transaction review service] Prepare to update memory status...")
            memory_manager = get_memory_state_manager()
            logger.info(f"✅ [Transaction review service] Obtain memory status manager successfully")

            memory_status = TaskStatus.RUNNING if status == AnalysisStatus.PROCESSING else (
                TaskStatus.COMPLETED if status == AnalysisStatus.COMPLETED else TaskStatus.FAILED
            )
            logger.info(f"   📋 内存状态: {memory_status}")

            if status == AnalysisStatus.PROCESSING:
                logger.info(f"🔄 [Transaction review service] Update the memory status to RUNNING...")
                await memory_manager.update_task_status(
                    task_id=task_id,
                    status=memory_status,
                    message=message or "处理中...",
                )
                logger.info(f"✅ [Transaction review service] The memory status has been updated to RUNNING")
            elif status == AnalysisStatus.COMPLETED:
                logger.info(f"🔄 [Transaction review service] Complete the task...")
                await memory_manager.update_task_status(
                    task_id=task_id,
                    status=memory_status,
                    progress=100,
                    message=message or "分析完成",
                    result_data=result
                )
                logger.info(f"✅ [Transaction review service] Task marked as complete")
            elif status == AnalysisStatus.FAILED:
                logger.info(f"🔄 [Transaction review service] Mark task failed...")
                await memory_manager.update_task_status(
                    task_id=task_id,
                    status=memory_status,
                    progress=0,
                    message=message or "分析失败",
                    error_message=error_message or "未知错误"
                )
                logger.info(f"✅ [Transaction review service] Task marked as failed")

            logger.info(f"🎉 [Transaction review service] _update_trade_review_task_status Complete")

        except Exception as e:
            logger.error(f"❌ [Transaction review service] Failed to update task status")
            logger.error(f"   📋 task_id: {task_id}")
            logger.error(f"   📋 错误类型: {type(e).__name__}")
            logger.error(f"   📋 错误信息: {str(e)}")
            logger.error(f"   📋 详细堆栈:", exc_info=True)

    async def _update_task_failed(self, task_id: str, error_message: str):
        """更新任务状态为失败"""
        db = self._get_db()
        if db is None:
            return

        try:
            db.analysis_tasks.update_one(
                {"task_id": task_id},
                {
                    "$set": {
                        "status": "failed",
                        "error_message": error_message,
                        "completed_at": now_tz(),  # ✅ Use now_tz() Make sure to include time zone information
                        "updated_at": now_tz(),  # ✅ Use now_tz() Make sure to include time zone information
                    }
                }
            )
        except Exception as e:
            logger.error(f"❌ 更新任务状态失败: {e}")


# Singleton instance
_unified_service: Optional[UnifiedAnalysisService] = None


def get_unified_analysis_service() -> UnifiedAnalysisService:
    """获取统一分析服务单例"""
    global _unified_service
    if _unified_service is None:
        _unified_service = UnifiedAnalysisService()
    return _unified_service


# ------------------------------------------------------------------
#  mem0 unified memory layer — Workflow analytics integration
# ------------------------------------------------------------------

def _get_memory_market_type(stock_code: str) -> str:
    try:
        from tradingagents.utils.stock_utils import StockMarket, StockUtils

        market = StockUtils.identify_stock_market(stock_code)
        mapping = {
            StockMarket.CHINA_A: "cn",
            StockMarket.HONG_KONG: "hk",
            StockMarket.US: "us",
            StockMarket.UNKNOWN: "cn",
        }
        return mapping.get(market, "cn")
    except Exception:
        return "cn"

async def _recall_analysis_memory(db, user_id: str, stock_code: str) -> str:
    """Recall the user s historical analysis memory of this stock from mem0"""
    try:
        from core.memory.service import get_memory_service
        svc = get_memory_service(db)
        normalized_symbol = str(stock_code or "").strip().upper()
        market_type = _get_memory_market_type(normalized_symbol)

        analysis_memory = await svc.recall_formatted(
            query=f"{normalized_symbol} 历史分析结论",
            user_id=user_id,
            scopes=["analysis_insight"],
            metadata_filters={
                "object_type": "stock",
                "memory_kind": "stock_analysis",
                "symbol": normalized_symbol,
                "market": market_type,
            },
            limit=3,
            max_chars=1200,
        )
        preference_memory = await svc.recall_formatted(
            query=f"{normalized_symbol} 分析偏好",
            user_id=user_id,
            scopes=["user_preference"],
            limit=2,
            max_chars=300,
        )
        return f"{analysis_memory}{preference_memory}"
    except Exception as e:
        logger.debug("[mem0] Analyze memory recall failure: %s", e)
        return ""


async def _store_analysis_insight(
    db, user_id: str, stock_code: str,
    analysis_date: str, summary: str, recommendation: str, task_id: str,
) -> None:
    """Write the analysis conclusion into the objectized stock long-term memory (asynchronously, without blocking the main process)"""
    if not summary and not recommendation:
        return
    try:
        from core.memory.service import get_memory_service
        svc = get_memory_service(db)
        normalized_symbol = str(stock_code or "").strip().upper()
        structured_summary = str(summary or recommendation or "").strip()
        structured_recommendation = str(recommendation or "").strip()
        result = await svc.store_stock_analysis(
            user_id=user_id,
            symbol=normalized_symbol,
            market=_get_memory_market_type(normalized_symbol),
            summary=structured_summary,
            recommendation=structured_recommendation,
            analysis_date=analysis_date,
            task_id=task_id,
            agent_id="workflow_analyst",
            session_id=task_id,
            next_checks=[structured_recommendation] if structured_recommendation else None,
        )
        logger.info(
            "[mem0] Objectized stock memory writing results — user=%s symbol=%s task=%s facts=%d success=%s error=%s",
            user_id,
            normalized_symbol,
            task_id,
            result.facts_extracted,
            result.success,
            result.error or "",
        )
    except Exception as e:
        logger.debug("[mem0] Analytics insights storage failed (ignored): %s", e)
