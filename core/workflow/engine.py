"""
Workflow execution engine

Responsible for the loading, verification and execution of workflows
"""

import logging
import uuid
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Protocol

from .models import (
    NodeType,
    OutputStrategy,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowExecutionState,
)
from core.state.models import FieldType
from .builder import WorkflowBuilder, ANALYST_TOOL_MAPPING
from .validator import WorkflowValidator, ValidationResult

logger = logging.getLogger(__name__)

_BUILTIN_REPORT_FIELDS = [
    # analyst stage
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "index_report",
    "sector_report",
    "social_report",
    "chip_report",
    # research stage
    "bull_report",
    "bear_report",
    "investment_plan",
    # risk stage
    "risky_opinion",
    "safe_opinion",
    "neutral_opinion",
    "risk_assessment",
    # manager stage
    "trader_investment_plan",
    "risk_conclusion",
    # trader stage
    "final_trade_decision",
    # Position analysis stage
    "technical_analysis",
    "fundamental_analysis",
    "risk_analysis",
    "action_advice",
    # Review stage
    "timing_analysis",
    "position_analysis",
    "emotion_analysis",
    "attribution_analysis",
    "review_summary",
]


def _get_dynamic_report_fields(agent_ids: List[str]) -> List[str]:
    """Dynamically derive report field list from agent metadata and agent_configs (replaces hard coding)

    Return only show_in_reports=True The agent s output_field.
    """
    fields = []

    try:
        from core.agents.registry import get_registry
        registry = get_registry()
        for meta in registry.list_all():
            if meta.id in agent_ids and meta.output_field and meta.output_field not in fields:
                # Check show_in_reports flag, default True
                if getattr(meta, 'show_in_reports', True):
                    fields.append(meta.output_field)
    except Exception as e:
        logger.warning(f"[Dynamic reporting fields] Failed to get from AgentRegistry: {e}")

    try:
        from pymongo import MongoClient
        from tradingagents.config.mongodb_utils import build_mongodb_connection_string, get_mongodb_database_name

        client = MongoClient(build_mongodb_connection_string(), serverSelectionTimeoutMS=2000)
        db = client[get_mongodb_database_name()]
        docs = list(db.agent_configs.find({
            "agent_id": {"$in": agent_ids},
            "enabled": True,
            "version_status": "active",
            "runtime_status": "active",
        }))
        client.close()
        for doc in docs:
            output_field = doc.get("output_field") or (doc.get("metadata") or {}).get("output_field")
            if output_field and output_field not in fields:
                # Check show_in_reports flag, default True
                show = doc.get("show_in_reports")
                if show is None:
                    show = (doc.get("metadata") or {}).get("show_in_reports", True)
                if show:
                    fields.append(output_field)
    except Exception as e:
        logger.warning(f"[Dynamic reporting fields] Failed to get from agent_configs: {e}")

    if "final_trade_decision" not in fields:
        fields.append("final_trade_decision")
    return fields if fields else _BUILTIN_REPORT_FIELDS

_AGENT_CATEGORY_DISPLAY = {
    "analyst": "Analyst Team",
    "researcher": "research team",
    "trader": "trading team",
    "risk": "risk management team",
    "manager": "decision-making level",
    "post_processor": "Post-processing",
}


def _prepare_workflow_runtime_inputs(
    inputs: Dict[str, Any],
    workflow_id: Optional[str],
    execution_id: str,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Inject lightweight runtime context into the initial state of the workflow without polluting the returned results."""
    prepared_inputs = inputs.copy() if inputs else {}
    runtime_context = dict(prepared_inputs.get("_workflow_runtime") or {})
    context = prepared_inputs.get("context")

    context_user_id = None
    context_thread_id = None
    if isinstance(context, dict):
        context_user_id = context.get("user_id")
        context_thread_id = context.get("thread_id") or context.get("session_id")
    elif context is not None:
        context_user_id = getattr(context, "user_id", None)
        context_thread_id = getattr(context, "thread_id", None) or getattr(context, "session_id", None)

    if workflow_id and not runtime_context.get("workflow_id"):
        runtime_context["workflow_id"] = workflow_id
    if execution_id and not runtime_context.get("execution_id"):
        runtime_context["execution_id"] = execution_id
    # 🔑 Inject task_id (task_id in the task center, the execution track is associated according to this, the front end checks the track according to task_id)
    if task_id and not runtime_context.get("task_id"):
        runtime_context["task_id"] = task_id
    if prepared_inputs.get("user_id") and not runtime_context.get("user_id"):
        runtime_context["user_id"] = prepared_inputs.get("user_id")
    if context_user_id and not runtime_context.get("user_id"):
        runtime_context["user_id"] = context_user_id
    if prepared_inputs.get("thread_id") and not runtime_context.get("thread_id"):
        runtime_context["thread_id"] = prepared_inputs.get("thread_id")
    if context_thread_id and not runtime_context.get("thread_id"):
        runtime_context["thread_id"] = context_thread_id

    if prepared_inputs.get("growth_memory_recall"):
        runtime_context["growth_memory_recall"] = prepared_inputs["growth_memory_recall"]

    ticker = prepared_inputs.get("ticker") or prepared_inputs.get("symbol") or prepared_inputs.get("stock_symbol") or prepared_inputs.get("company_of_interest")
    # 🔍 Debug log: troubleshooting ticker loss problem
    import logging as _logging
    _logger = _logging.getLogger("core.workflow.engine")
    _logger.info(f"🔍 [_prepare_workflow_runtime_inputs] ticker mapping: ticker={prepared_inputs.get('ticker')}, symbol={prepared_inputs.get('symbol')}, stock_symbol={prepared_inputs.get('stock_symbol')}, company_of_interest={prepared_inputs.get('company_of_interest')}, eventually ticker={ticker}")
    if ticker:
        prepared_inputs.setdefault("ticker", ticker)
        prepared_inputs.setdefault("stock_symbol", ticker)
        prepared_inputs.setdefault("symbol", ticker)
        prepared_inputs.setdefault("company_of_interest", ticker)

    analysis_date = prepared_inputs.get("analysis_date") or prepared_inputs.get("trade_date")
    if analysis_date:
        prepared_inputs.setdefault("analysis_date", analysis_date)
        prepared_inputs.setdefault("trade_date", analysis_date)

    prepared_inputs["_workflow_runtime"] = runtime_context
    return prepared_inputs


class ProgressCallback(Protocol):
    """Progress callback protocol"""
    def __call__(
        self,
        progress: float,
        message: str,
        step_name: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Progress callback

        Args:
            progress: progress percentage (0-100)
            message: progress message
            step_name: Current step name
            **kwargs: extra parameters
        """
        ...


class WorkflowEngine:
    """
    Workflow execution engine

    Usage:
        engine = WorkflowEngine()

        # Load workflow
        engine.load(workflow_definition)

        # Verify
        result = engine.validate()

        # execute
        output = engine.execute({"ticker": "AAPL", "trade_date": "2024-01-15"})

        # or streaming execution
        async for event in engine.execute_stream(inputs):
            print(event)

        # Execution with progress callback
        def on_progress(progress, message, **kwargs):
            print(f"{progress}% - {message}")
        output = engine.execute(inputs, progress_callback=on_progress)
    """

    def __init__(
        self,
        legacy_config: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        use_dynamic_state: bool = True,  # 🔥 Changed to enabled by default, required for dynamic Agent workflows
        llm: Optional[Any] = None
    ):
        """
        Initialize the workflow engine

        Args:
            legacy_config: Legacy agent configuration (used to create LLM and Toolkit)
            task_id: Task ID (for progress tracking)
            use_dynamic_state: Whether to use dynamic state generation (default True, supports dynamic Agent field)
            llm: Optional LLM instance (takes precedence over legacy_config)
        """
        self._definition: Optional[WorkflowDefinition] = None
        self._compiled_graph = None
        self._legacy_config = legacy_config
        self._task_id = task_id or str(uuid.uuid4())
        self._builder = WorkflowBuilder(legacy_config=legacy_config, llm_override=llm)
        self._validator = WorkflowValidator()
        self._current_execution: Optional[WorkflowExecution] = None
        self._progress_callback: Optional[Callable] = None

        # 🆕 Progress tracking status (progress is calculated based on the number of completed agents / total number, only increases but not decreases)
        self._progress_agent_nodes = []      # List of agent nodes with agent_id
        self._progress_node_keys = {}        # {key: node} Mapping, matching what stream returns node_name
        self._progress_completed = set()     # The key collection of agent has been completed
        self._progress_total = 0             # agent Total number of nodes N
        self._progress_max = 10              # The maximum reported progress value (guaranteed to only increase but not decrease)

        # 🆕 Dynamic state generation
        self._use_dynamic_state = use_dynamic_state
        self._state_schema = None
        if use_dynamic_state:
            from ..state.builder import StateSchemaBuilder
            from ..state.registry import StateRegistry
            self._state_builder = StateSchemaBuilder()
            self._state_registry = StateRegistry()
            logger.info("[WorkflowEngine] Enable dynamic state generation")
    
    def load(self, definition: WorkflowDefinition) -> "WorkflowEngine":
        """Load workflow definition"""
        self._definition = definition
        self._compiled_graph = None  # Clear compiled graph
        return self
    
    def load_from_dict(self, data: Dict[str, Any]) -> "WorkflowEngine":
        """Load workflow from dictionary"""
        definition = WorkflowDefinition.from_dict(data)
        return self.load(definition)
    
    def load_from_json(self, json_str: str) -> "WorkflowEngine":
        """Load workflow from JSON string"""
        definition = WorkflowDefinition.from_json(json_str)
        return self.load(definition)
    
    def validate(self) -> ValidationResult:
        """Validation workflow"""
        if self._definition is None:
            result = ValidationResult()
            result.add_error("NO_DEFINITION", "Workflow definition not loaded")
            return result
        
        return self._validator.validate(self._definition)
    
    def compile(self) -> "WorkflowEngine":
        """Compilation workflow"""
        if self._definition is None:
            raise ValueError("Workflow definition not loaded")

        # Verify first
        result = self.validate()
        if not result.is_valid:
            errors = "\n".join(str(e) for e in result.errors)
            raise ValueError(f"Workflow validation failed:\n{errors}")

        # 🆕 If dynamic status is enabled, generate status Schema
        state_schema = None
        if self._use_dynamic_state:
            agent_ids = self._extract_agent_ids(self._definition)
            if agent_ids:
                logger.info(f"[WorkflowEngine] for workflow {self._definition.id} Generate dynamic status, Agent list: {agent_ids}")

                internal_state_fields = self._build_internal_state_fields(self._definition)

                # Use StateRegistry to get or build a state class
                schema = self._state_registry.get_or_build(
                    workflow_id=self._definition.id,
                    agent_ids=agent_ids,
                    internal_state_fields=internal_state_fields,
                )
                state_schema = self._state_registry.get_state_class(self._definition.id)

                logger.info(f"[WorkflowEngine] Status class generated successfully: {state_schema.__name__ if state_schema else 'None'}")
                logger.info(f"[WorkflowEngine] status field: {list(schema.fields.keys())}")

        # Build diagram
        self._compiled_graph = self._builder.build(self._definition, state_schema=state_schema)
        return self

    def _extract_agent_ids(self, definition: WorkflowDefinition) -> list:
        """Extract the list of Agent IDs (containing debate participants and delegation agents) from the workflow definition"""
        agent_ids = []
        for node in definition.nodes:
            candidates = []
            if node.agent_id:
                candidates.append(node.agent_id)

            node_config = getattr(node, "config", None) or {}
            candidates.extend(node_config.get("participants") or [])
            candidates.extend(node_config.get("delegated_agent_ids") or [])

            for agent_id in candidates:
                if agent_id and agent_id not in agent_ids:
                    agent_ids.append(agent_id)
        return agent_ids
    
    def _build_internal_state_fields(self, definition: WorkflowDefinition) -> Dict[str, FieldType]:
        """Complete the internal control fields required by the dynamic State according to the workflow definition."""
        fields: Dict[str, FieldType] = {
            "investment_debate_state": FieldType.OBJECT,
            "risk_debate_state": FieldType.OBJECT,
            "_max_debate_rounds": FieldType.NUMBER,
            "_max_risk_rounds": FieldType.NUMBER,
            # A9-P1: Risk Self Debate Switch (True=The depth/comprehensive file takes the single-node self-debate path)
            "_risk_self_debate": FieldType.BOOLEAN,
            # A3: Investment debate parallel opening switch (True=First round of optimistic/cautious researchers concurrent briefing)
            "_parallel_opening": FieldType.BOOLEAN,
            "context": FieldType.OBJECT,
            "skip_cache": FieldType.BOOLEAN,
            "prompt_overrides": FieldType.OBJECT,
            "_workflow_runtime": FieldType.OBJECT,
            "_node_errors": FieldType.OBJECT,
            "tool_call_summaries": FieldType.OBJECT,
            "_condition_result": FieldType.BOOLEAN,
            "_condition_error": FieldType.STRING,
            "_analysis_data_source": FieldType.STRING,
            # External fact memory injection (facts extracted by the intelligent assistant online for reference in debate/risk assessment sessions)
            "memory_facts_summary": FieldType.STRING,
            # Position analysis workflow input: position_info/portfolio_data If not declared, LangGraph will dynamically
            # State Undeclared keys will be discarded, causing agents to be unable to obtain position data and report "Missing required parameters: ticker"
            "position_info": FieldType.OBJECT,
            "portfolio_data": FieldType.OBJECT,
            "position_type": FieldType.STRING,
            "analysis_params": FieldType.OBJECT,
            "stock_analysis_report": FieldType.OBJECT,
            "user_preference": FieldType.STRING,
            "trade_info": FieldType.OBJECT,
            "ticker": FieldType.STRING,
            "symbol": FieldType.STRING,
            "company_of_interest": FieldType.STRING,
        }

        for node in definition.nodes:
            node_type = node.type.value if hasattr(node.type, "value") else str(node.type)
            if node_type == "debate":
                fields[f"_debate_{node.id}_count"] = FieldType.NUMBER

            if node.agent_id:
                normalized = node.agent_id.replace("_analyst_v2", "").replace("_analyst", "")
                if normalized:
                    fields[f"_{normalized}_messages"] = FieldType.ARRAY
                    fields[f"{normalized}_tool_call_count"] = FieldType.NUMBER

                analyst_type = ANALYST_TOOL_MAPPING.get(node.agent_id)
                if analyst_type:
                    fields[f"_{analyst_type}_messages"] = FieldType.ARRAY
                    fields[f"{analyst_type}_tool_call_count"] = FieldType.NUMBER

            node_config = getattr(node, "config", None) or {}
            output_field = node_config.get("output_field")
            if output_field:
                fields[output_field] = FieldType.STRING

        return fields
    
    def set_progress_callback(self, callback: Optional[Callable]) -> "WorkflowEngine":
        """Set progress callback"""
        self._progress_callback = callback
        return self

    def _report_progress(
        self,
        progress: float,
        message: str,
        step_name: Optional[str] = None,
        **kwargs
    ) -> None:
        """Report progress"""
        if self._progress_callback:
            try:
                self._progress_callback(
                    progress=progress,
                    message=message,
                    step_name=step_name,
                    task_id=self._task_id,
                    **kwargs
                )
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    def _build_execution_config(
        self,
        config: Optional[Dict[str, Any]],
        inputs: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        execution_config = dict(config or {})
        if "recursion_limit" not in execution_config:
            recursion_limit = None
            if inputs:
                recursion_limit = inputs.get("recursion_limit") or inputs.get("workflow_recursion_limit")
            if recursion_limit is None and self._legacy_config:
                recursion_limit = self._legacy_config.get("recursion_limit")
            execution_config["recursion_limit"] = int(recursion_limit or 100)
        return execution_config

    def execute(
        self,
        inputs: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Execute workflows synchronously (use stream mode to get node-level progress updates)

        Args:
            inputs: input parameters
            config: Execute configuration
            progress_callback: Progress callback function

        Returns:
            Execution result
        """
        if progress_callback:
            self.set_progress_callback(progress_callback)

        if self._compiled_graph is None:
            self._report_progress(5, "Compilation workflow...", "compile")
            self.compile()

        runtime_inputs = _prepare_workflow_runtime_inputs(
            inputs,
            self._definition.id if self._definition else None,
            self._task_id,
            task_id=self._task_id,
        )
        execution_config = self._build_execution_config(config, runtime_inputs)

        # Create execution record
        execution = self._create_execution(inputs)
        self._init_progress_tracking()
        self._report_progress(10, "Start executing workflow", "start")

        try:
            execution.state = WorkflowExecutionState.RUNNING
            execution.started_at = datetime.now().isoformat()

            logger.info(f"Start executing workflow: {self._definition.id if self._definition else 'unknown'}")

            # Use stream mode to get node-level progress updates
            # stream_mode should be passed as keyword arguments rather than placed in the config dictionary
            final_state = inputs.copy() if inputs else {}

            for chunk in self._compiled_graph.stream(runtime_inputs, config=execution_config, stream_mode="updates"):
                # chunk Format: {node_name: state_update}
                if isinstance(chunk, dict):
                    for node_name, node_update in chunk.items():
                        if node_name.startswith('__'):
                            continue  # Skip special nodes

                        # Get progress information
                        progress_info = self._get_node_progress_info(node_name)
                        progress, message, step_name = progress_info

                        if progress is not None:
                            self._report_progress(progress, message, step_name)

                        # Cumulative status updates
                        if isinstance(node_update, dict):
                            try:
                                # 🔍 Debugging: Print fields updated by nodes
                                update_keys = list(node_update.keys())
                                logger.debug(f"[execution engine] 📝 node {node_name} Return field: {update_keys}")
                                # Check if there is index_report or sector_report
                                if "index_report" in node_update:
                                    logger.debug(f"[execution engine] ✅ detected index_report ({len(str(node_update['index_report']))} character)")
                                if "sector_report" in node_update:
                                    logger.debug(f"[execution engine] ✅ detected sector_report ({len(str(node_update['sector_report']))} character)")
                                final_state.update(node_update)
                            except Exception:
                                final_state[node_name] = node_update
                        else:
                            final_state[node_name] = node_update

            # Use accumulated final state
            result = final_state
            result = self._build_output_results(result)

            execution.state = WorkflowExecutionState.COMPLETED
            execution.outputs = result
            execution.completed_at = datetime.now().isoformat()

            self._report_progress(100, "Workflow execution completed", "completed")
            return result

        except Exception as e:
            execution.state = WorkflowExecutionState.FAILED
            execution.error = str(e)
            execution.completed_at = datetime.now().isoformat()
            self._report_progress(
                progress=self._progress_max,
                message=f"Execution failed: {str(e)}",
                step_name="error",
                error=str(e)
            )
            raise

        finally:
            self._current_execution = execution
    
    def _init_progress_tracking(self) -> None:
        """Initialization progress tracking: counting the total number of agent nodes and establishing matching mappings

        Use the node with agent_id as the agent node (control node
        PARALLEL/MERGE/DEBATE/START/END No agent_id, automatically excluded).
        The progress is calculated according to the number of completed agents/total number. It only increases but does not decrease, and automatically adapts to the increase or decrease of agents.
        """
        self._progress_completed = set()
        self._progress_max = 10
        self._progress_agent_nodes = []
        self._progress_node_keys = {}

        if not self._definition or not self._definition.nodes:
            self._progress_total = 0
            return

        for node in self._definition.nodes:
            agent_id = getattr(node, "agent_id", None)
            if not agent_id:
                continue  # Control node (start/end/parallel/merge/debate) skip
            self._progress_agent_nodes.append(node)
            # Establish mapping of multiple keys to match those returned by stream node_name
            for key in (agent_id, node.label, node.id):
                if key:
                    self._progress_node_keys[key] = node

        self._progress_total = len(self._progress_agent_nodes)

    def _get_node_progress_info(self, node_name: str) -> tuple:
        """Get node s progress information (percentage and friendly messages)

        🔥 Calculate the progress according to number of completed agents / total number , only increase but not decrease:
        - 10% Starting (compile/start), the 10%-90% range is evenly divided according to completed/N, and 100% is reported when the workflow is completed.
        - The control node does not increase completed, but reports the current progress. + friendly news
        - no definition(N==0) Fall back to node_mapping fixed percentage, compatible with single agent debugging

        Args:
            node_name: Node name (returned from LangGraph stream)

        Returns:
            (progress_percentage, friendly_message, step_name)
        """
        # Mapping of node names to friendly messages (for display only, progress values are no longer taken from this mapping)
        # Three formats are supported: old format ("Market Analyst") , v1 format("market_analyst") , v2 format("market_analyst_v2") 
        # Format:(progress_percentage, friendly_message, step_name)
        # - progress_percentage: progress percentage
        # - friendly_message: Detailed description (displayed in the message field)
        # - step_name: Short name (shown in the current_step_name field)
        node_mapping = {
            # === v2.0 Analyst Node ===
            "market_analyst_v2": (15, "📈 Market analysts are analyzing technical indicators and market trends...", "market analyst"),
            "fundamentals_analyst_v2": (25, "💰 Fundamental analyst is analyzing financial data...", "fundamental analyst"),
            "news_analyst_v2": (35, "📰 News analysts are analyzing relevant news and events...", "news analyst"),
            "social_analyst_v2": (40, "💬 Social media analysts are analyzing social media sentiment...", "social media analyst"),
            "sector_analyst_v2": (20, "📊 Sector analysts are analyzing industry trends...", "Sector Analyst"),
            "index_analyst_v2": (10, "📈 Market analysts are analyzing the market environment...", "Market Analyst"),

            # === v2.0 research team ===
            "bull_researcher_v2": (50, "🐂 Optimistic scenario researchers are constructing optimistic arguments...", "Optimistic Scenario Researcher"),
            "bear_researcher_v2": (55, "🐻 Prudential Scenario Researchers are Constructing Precautionary Arguments...", "Prudential Scenario Researcher"),
            "research_manager_v2": (60, "🔬 Research managers are synthesizing research ideas...", "research manager"),

            # === v2.0 Research integration stage ===
            "trader_v2": (92, "🧩 Research integrator is generating a user version of the research brief...", "research integrator"),

            # === v2.0 risk management team ===
            "risky_analyst_v2": (72, "⚡ High-resilience scenario analysts are reviewing conditions for upward revisions to conclusions...", "Highly Resilient Scenario Analyst"),
            "safe_analyst_v2": (78, "🛡️ Defense scenario analysts reviewing vulnerabilities and critical risks...", "Defense Scenario Analyst"),
            "neutral_analyst_v2": (84, "⚖️ Baseline scenario analysts are reviewing the baseline scenario and evidence completeness...", "Baseline Scenario Analyst"),
            "risk_manager_v2": (90, "👔 Risk assessors are reviewing the robustness of research conclusions...", "risk assessor"),

            # === v1.0 Analyst node (backwards compatible)===
            "market_analyst": (15, "📈 Market analysts are analyzing technical indicators and market trends...", "market analyst"),
            "fundamentals_analyst": (25, "💰 Fundamental analyst is analyzing financial data...", "fundamental analyst"),
            "news_analyst": (35, "📰 News analysts are analyzing relevant news and events...", "news analyst"),
            "social_analyst": (40, "💬 Social media analysts are analyzing social media sentiment...", "social media analyst"),
            "sentiment_analyst": (40, "💭 Sentiment analysts are analyzing market sentiment...", "sentiment analyst"),

            # === v1.0 research team ===
            "bull_researcher": (50, "🐂 Optimistic scenario researchers are constructing optimistic arguments...", "Optimistic Scenario Researcher"),
            "bear_researcher": (55, "🐻 Prudential Scenario Researchers are Constructing Precautionary Arguments...", "Prudential Scenario Researcher"),
            "research_manager": (60, "🔬 Research managers are synthesizing research ideas...", "research manager"),

            # === v1.0 Research integration stage ===
            "trader": (70, "🧩 A research integrator is summarizing research conclusions...", "research integrator"),

            # === v1.0 risk management team ===
            "risky_analyst": (75, "⚡ High-resilience scenario researchers are assessing the upside...", "Highly Resilient Scenario Researcher"),
            "safe_analyst": (80, "🛡️ Defense scenario researchers are assessing downside risks...", "Defense scenario researcher"),
            "neutral_analyst": (82, "⚖️ Neutral analysts are balancing risk-return...", "neutral analyst"),
            "risk_manager": (90, "👔 Risk assessors are forming final conclusions...", "risk assessor"),
            "risk_judge": (90, "👔 Risk assessors are forming final conclusions...", "risk assessor"),
            "portfolio_manager": (90, "👔 Risk assessor doing final study review...", "risk assessor"),

            # === Workflow control node ===
            "start": (5, "🚀 Start analysis...", "start"),
            "parallel_analysts": (10, "📊 Start an analyst team...", "Launch Analyst"),
            "merge_analysts": (42, "📋 Aggregate analyst reports...", "summary report"),
            "debate": (45, "💬 The research team started discussing...", "research discussion"),
            "risk_debate": (72, "⚖️ The risk assessment team begins discussions...", "risk discussion"),
            "end": (95, "✅ Analysis is almost complete...", "Complete"),

            # === Old format (backwards compatible)===
            "Market Analyst": (15, "📈 Market analysts are analyzing technical indicators and market trends...", "market analyst"),
            "Fundamentals Analyst": (25, "💰 Fundamental analyst is analyzing financial data...", "fundamental analyst"),
            "News Analyst": (35, "📰 News analysts are analyzing relevant news and events...", "news analyst"),
            "Social Analyst": (40, "💬 Social media analysts are analyzing social media sentiment...", "social media analyst"),
            "Bull Researcher": (50, "🐂 Optimistic scenario researchers are constructing optimistic arguments...", "Optimistic Scenario Researcher"),
            "Bear Researcher": (55, "🐻 Prudential Scenario Researchers are Constructing Precautionary Arguments...", "Prudential Scenario Researcher"),
            "Research Manager": (60, "🔬 Research managers are synthesizing research ideas...", "research manager"),
            "Trader": (70, "🧩 A research integrator is summarizing research conclusions...", "research integrator"),
            "Risky Analyst": (75, "⚡ High-resilience scenario researchers are assessing the upside...", "Highly Resilient Scenario Researcher"),
            "Safe Analyst": (80, "🛡️ Defense scenario researchers are assessing downside risks...", "Defense scenario researcher"),
            "Neutral Analyst": (82, "⚖️ Neutral analysts are balancing risk-return...", "neutral analyst"),
            "Risk Judge": (90, "👔 Risk assessors are forming final conclusions...", "risk assessor"),
            "Portfolio Manager": (90, "👔 Risk assessor doing final study review...", "risk assessor"),
        }

        # Ignored nodes (tool nodes, message cleaning nodes, etc.)
        ignored_patterns = ["tools_", "Msg Clear", "msg_clear_", "__start__", "__end__"]

        for pattern in ignored_patterns:
            if pattern in node_name:
                return (None, None, None)  # skip these nodes

        # Get friendly message from map (on hit; progress value is no longer taken from map)
        mapped = node_mapping.get(node_name)

        # Match the agent node and accumulate the number of completions (the control node has no agent_id and will not be hit)
        agent_node = self._progress_node_keys.get(node_name)
        if agent_node is not None and node_name not in self._progress_completed:
            self._progress_completed.add(node_name)

        # Calculate progress
        if self._progress_total > 0:
            # Divide the 10%-90% interval equally according to the number of completed agents
            progress = 10 + int(round(80 * len(self._progress_completed) / self._progress_total))
        elif mapped is not None:
            # No definition fallback: use a fixed percentage (compatible with scenarios such as single-agent debugging)
            progress = mapped[0]
        else:
            progress = self._progress_max  # Unknown node, keep current

        # only increase but not decrease
        if progress < self._progress_max:
            progress = self._progress_max
        else:
            self._progress_max = progress

        # Friendly news and step_name
        if mapped is not None:
            return (progress, mapped[1], mapped[2])

        # Dynamic derivation: finding nodes from workflow definition label
        for node in self._progress_agent_nodes:
            agent_id = node.agent_id or ""
            if agent_id == node_name or node.label == node_name or node.id == node_name:
                meta = self._lookup_agent_metadata(agent_id) if agent_id else None
                label = (meta.node_name if meta and meta.node_name
                         else node.label or agent_id.replace("_", " ").title())
                return (progress, f"Executing: {label}", label)

        friendly_name = node_name.replace("_v2", "").replace("_", " ").title()
        return (progress, f"Executing: {friendly_name}", friendly_name)

    async def execute_async(
        self,
        inputs: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Execute workflows asynchronously (use stream mode to get node-level progress updates)

        Args:
            inputs: input parameters
            config: Execute configuration
            progress_callback: Progress callback function

        Returns:
            Execution result
        """
        if progress_callback:
            self.set_progress_callback(progress_callback)

        if self._compiled_graph is None:
            self._report_progress(5, "Compilation workflow...", "compile")
            self.compile()

        runtime_inputs = _prepare_workflow_runtime_inputs(
            inputs,
            self._definition.id if self._definition else None,
            self._task_id,
            task_id=self._task_id,
        )
        execution_config = self._build_execution_config(config, runtime_inputs)

        execution = self._create_execution(inputs)
        self._init_progress_tracking()
        self._report_progress(10, "Start executing workflow", "start")

        try:
            execution.state = WorkflowExecutionState.RUNNING
            execution.started_at = datetime.now().isoformat()

            logger.info(f"Start asynchronous execution workflow: {self._definition.id if self._definition else 'unknown'}")

            # Using astream mode to get node-level progress updates
            # stream_mode should be passed as keyword arguments rather than placed in the config dictionary
            final_state = inputs.copy() if inputs else {}

            async for chunk in self._compiled_graph.astream(runtime_inputs, config=execution_config, stream_mode="updates"):
                # chunk Format: {node_name: state_update}
                if isinstance(chunk, dict):
                    for node_name, node_update in chunk.items():
                        if node_name.startswith('__'):
                            continue  # Skip special nodes

                        # 🔥 Key: check for cancellation flag after each node execution
                        # Trigger the cancellation check by calling progress_callback
                        # Get progress information
                        progress_info = self._get_node_progress_info(node_name)
                        progress, message, step_name = progress_info

                        if progress is not None:
                            # 🔥 Key: calling progress_callback triggers a cancellation check
                            # If the task is canceled, wrapped_progress_callback will throw TaskCancelledException
                            self._report_progress(progress, message, step_name)

                        # Cumulative status updates
                        if isinstance(node_update, dict):
                            try:
                                final_state.update(node_update)
                            except Exception:
                                final_state[node_name] = node_update
                        else:
                            final_state[node_name] = node_update

            # Use accumulated final state
            result = final_state
            result = self._build_output_results(result)

            execution.state = WorkflowExecutionState.COMPLETED
            execution.outputs = result
            execution.completed_at = datetime.now().isoformat()

            self._report_progress(100, "Workflow execution completed", "completed")
            return result

        except Exception as e:
            execution.state = WorkflowExecutionState.FAILED
            execution.error = str(e)
            execution.completed_at = datetime.now().isoformat()
            self._report_progress(
                progress=self._progress_max,
                message=f"Execution failed: {str(e)}",
                step_name="error",
                error=str(e)
            )
            raise

        finally:
            self._current_execution = execution
    
    async def execute_stream(
        self,
        inputs: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Streaming execution workflow
        
        Yields:
            execution event {"type": "node_start|node_end|output", ...}
        """
        if self._compiled_graph is None:
            self.compile()

        runtime_inputs = _prepare_workflow_runtime_inputs(
            inputs,
            self._definition.id if self._definition else None,
            self._task_id,
            task_id=self._task_id,
        )
        
        execution = self._create_execution(inputs)
        execution.state = WorkflowExecutionState.RUNNING
        execution.started_at = datetime.now().isoformat()
        
        try:
            async for event in self._compiled_graph.astream(runtime_inputs, config):
                # wrapper event
                yield {
                    "type": "node_output",
                    "execution_id": execution.id,
                    "data": event,
                    "timestamp": datetime.now().isoformat(),
                }
            
            execution.state = WorkflowExecutionState.COMPLETED
            execution.completed_at = datetime.now().isoformat()
            
            yield {
                "type": "completed",
                "execution_id": execution.id,
                "timestamp": datetime.now().isoformat(),
            }
            
        except Exception as e:
            execution.state = WorkflowExecutionState.FAILED
            execution.error = str(e)
            
            yield {
                "type": "error",
                "execution_id": execution.id,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
        
        finally:
            self._current_execution = execution
    
    def _create_execution(self, inputs: Dict[str, Any]) -> WorkflowExecution:
        """Create execution record"""
        return WorkflowExecution(
            id=self._task_id,
            workflow_id=self._definition.id if self._definition else "",
            inputs=inputs,
        )

    @property
    def task_id(self) -> str:
        """Task ID"""
        return self._task_id

    @task_id.setter
    def task_id(self, value: str) -> None:
        """Set tasks ID"""
        self._task_id = value

    @property
    def definition(self) -> Optional[WorkflowDefinition]:
        """Currently loaded workflow definition"""
        return self._definition

    # ------------------------------------------------------------------
    # Dynamic output collection
    # ------------------------------------------------------------------

    def _is_builtin_workflow(self, definition: WorkflowDefinition) -> bool:
        """Determine whether it is a built-in workflow (old workflow using standard report fields)"""
        if not definition:
            return True
        agent_ids = self._extract_agent_ids(definition)
        if not agent_ids:
            return True
        has_builtin_agents = any(
            aid.endswith("_v2") or aid in (
                "market_analyst", "fundamentals_analyst", "news_analyst",
                "social_analyst", "bull_researcher", "bear_researcher",
                "research_manager", "trader", "risk_manager",
                "risky_analyst", "safe_analyst", "neutral_analyst",
            )
            for aid in agent_ids
        )
        strategy = getattr(definition.output_config, "strategy", "auto")
        if strategy != "auto":
            return False
        return has_builtin_agents

    def _lookup_agent_metadata(self, agent_id: str):
        """Query Agent metadata: first DB dynamic Agent, then registry, and finally code constants"""
        # 1. First search for dynamic Agent (custom Agent created by Agent Workshop) from MongoDB agent_configs
        try:
            from app.core.database import get_mongo_db
            db = get_mongo_db()
            doc = db.agent_configs.find_one({"agent_id": agent_id, "enabled": True})
            if doc:
                from core.agents.config import AgentMetadata, AgentCategory
                metadata_fields = doc.get("metadata", {})
                return AgentMetadata(
                    id=agent_id,
                    name=doc.get("name", agent_id),
                    description=doc.get("description", ""),
                    category=AgentCategory(metadata_fields.get("workflow_stage", "analyst")),
                    tools=doc.get("default_tools", []),
                    default_tools=doc.get("default_tools", []),
                    license_tier=metadata_fields.get("license_tier", "pro"),
                    tags=metadata_fields.get("tags", []),
                    icon=metadata_fields.get("icon", "📄"),
                    color=metadata_fields.get("color", "#3498db"),
                    output_field=doc.get("output_field", f"{agent_id}_report"),
                    report_label=doc.get("name", agent_id),
                    show_in_reports=True,
                    node_name=doc.get("name", agent_id),
                )
        except Exception:
            pass

        # 2. Find from AgentRegistry
        try:
            from core.agents.registry import get_registry
            metadata = get_registry().get_metadata(agent_id)
            if metadata:
                return metadata
        except Exception:
            pass

        # 3. Fallback from code constants
        try:
            from core.agents.config import AGENT_METADATA_REGISTRY
            return AGENT_METADATA_REGISTRY.get(agent_id)
        except Exception:
            pass
        return None

    def _collect_output_manifest(
        self,
        state: Dict[str, Any],
        definition: WorkflowDefinition,
    ):
        """
        Collect outputs from state based on output_config.

        Returns:
            (structured_reports, report_manifest)
        """
        output_config = definition.output_config
        strategy = output_config.strategy

        if strategy == OutputStrategy.SPECIFIED and output_config.fields:
            return self._collect_specified(state, output_config)
        elif strategy == OutputStrategy.LAST_NODE:
            return self._collect_last_node(state, definition)
        elif strategy == OutputStrategy.COLLECT_ALL:
            return self._collect_all_agents(state, definition)
        else:
            return self._collect_auto(state, definition)

    def _collect_auto(self, state, definition):
        """AUTO Strategy: Automatically derive outputs from workflow topology and Agent declarations"""
        agent_nodes = [n for n in definition.nodes if n.agent_id]
        if not agent_nodes:
            return {}, []

        field_infos = []
        for node in agent_nodes:
            meta = self._lookup_agent_metadata(node.agent_id)
            # Check show_in_reports flag, default True
            if meta and not getattr(meta, 'show_in_reports', True):
                continue
            field_name = (meta.output_field if meta and meta.output_field
                          else f"{node.agent_id}_report")
            display_name = ""
            if meta:
                display_name = meta.report_label or meta.node_name
            display_name = display_name or node.label or node.agent_id.replace("_", " ").title()

            cat = ""
            if meta:
                cat_val = meta.category.value if hasattr(meta.category, "value") else str(meta.category)
                cat = _AGENT_CATEGORY_DISPLAY.get(cat_val, cat_val)
            cat = cat or "Others"

            order = meta.execution_order if meta else 100
            field_infos.append({
                "field": field_name,
                "display_name": display_name.strip("【】"),
                "category": cat,
                "order": order,
                "is_primary": False,
                "format_hint": "markdown",
                "agent_id": node.agent_id,
                "icon": meta.icon if meta else "📄",
                "description": meta.description if meta else "",
            })

        if field_infos:
            primary = max(field_infos, key=lambda f: f["order"])
            primary["is_primary"] = True

        return self._extract_from_state(state, field_infos)

    def _collect_all_agents(self, state, definition):
        """COLLECT_ALL Strategy: Collect the information of all Agent nodes output_field"""
        return self._collect_auto(state, definition)

    def _collect_last_node(self, state, definition):
        """LAST_NODE Strategy: Only collect the Agent output of the immediate predecessor of the END node"""
        end_nodes = definition.get_end_nodes()
        predecessor_agent_ids = set()
        for end_node in end_nodes:
            incoming = definition.get_edges_to(end_node.id)
            for edge in incoming:
                src_node = definition.get_node(edge.source)
                if src_node and src_node.agent_id:
                    predecessor_agent_ids.add(src_node.agent_id)

        if not predecessor_agent_ids:
            return self._collect_auto(state, definition)

        agent_nodes = [
            n for n in definition.nodes
            if n.agent_id and n.agent_id in predecessor_agent_ids
        ]
        field_infos = []
        for node in agent_nodes:
            meta = self._lookup_agent_metadata(node.agent_id)
            # Check show_in_reports flag, default True
            if meta and not getattr(meta, 'show_in_reports', True):
                continue
            field_name = (meta.output_field if meta and meta.output_field
                          else f"{node.agent_id}_report")
            display_name = ""
            if meta:
                display_name = meta.report_label or meta.node_name
            display_name = display_name or node.label or node.agent_id.replace("_", " ").title()
            cat_val = (meta.category.value if meta and hasattr(meta.category, "value")
                       else str(meta.category) if meta else "")
            field_infos.append({
                "field": field_name,
                "display_name": display_name.strip("【】"),
                "category": _AGENT_CATEGORY_DISPLAY.get(cat_val, cat_val) or "Others",
                "order": meta.execution_order if meta else 100,
                "is_primary": True,
                "format_hint": "markdown",
                "agent_id": node.agent_id,
                "icon": meta.icon if meta else "📄",
                "description": meta.description if meta else "",
            })

        return self._extract_from_state(state, field_infos)

    def _collect_specified(self, state, output_config):
        """SPECIFIED Strategy: Use a manually specified field list by the user"""
        field_infos = []
        for fc in output_config.fields:
            field_infos.append({
                "field": fc.field_name,
                "display_name": fc.display_name or fc.field_name.replace("_", " ").title(),
                "category": fc.category or "Others",
                "order": fc.order,
                "is_primary": fc.is_primary,
                "format_hint": fc.format_hint or "markdown",
                "agent_id": "",
                "icon": getattr(fc, "icon", "") or "📄",
                "description": getattr(fc, "description", "") or "",
            })
        if field_infos and not any(f["is_primary"] for f in field_infos):
            max_order = max(field_infos, key=lambda f: f["order"])
            max_order["is_primary"] = True
        return self._extract_from_state(state, field_infos)

    @staticmethod
    def _extract_text_value(v) -> str:
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            for k in ("content", "markdown", "text", "message", "report"):
                x = v.get(k)
                if isinstance(x, str) and x.strip():
                    return x
        return "" if v is None else str(v)

    def _extract_from_state(self, state, field_infos):
        """Extract field content from state, build structured_reports and report_manifest"""
        structured = {}
        manifest = []

        for info in sorted(field_infos, key=lambda f: f["order"]):
            field = info["field"]
            raw = state.get(field)
            text = self._extract_text_value(raw)
            has_content = bool(isinstance(text, str) and text.strip())

            structured[field] = {"content": text, "success": has_content}
            manifest.append({
                "field": field,
                "display_name": info["display_name"],
                "category": info["category"],
                "order": info["order"],
                "is_primary": info["is_primary"],
                "format_hint": info["format_hint"],
                "agent_id": info.get("agent_id", ""),
                "icon": info.get("icon", "📄"),
                "description": info.get("description", ""),
                "has_content": has_content,
            })

        return structured, manifest

    def _build_output_results(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build the output after execute completes.
        The built-in workflow uses old logic, and the customized workflow uses dynamic collection.
        """
        definition = self._definition
        if not definition:
            return result

        if self._is_builtin_workflow(definition):
            return self._build_builtin_output(result)

        structured, manifest = self._collect_output_manifest(result, definition)
        result["structured_reports"] = structured
        result["report_manifest"] = manifest

        if not result.get("final_trade_decision"):
            primary_items = [m for m in manifest if m.get("is_primary") and m.get("has_content")]
            if primary_items:
                pf = primary_items[0]["field"]
                result["final_trade_decision"] = self._extract_text_value(result.get(pf))
            elif manifest:
                sections = []
                for m in manifest:
                    if m.get("has_content"):
                        text = self._extract_text_value(result.get(m["field"]))
                        sections.append(f"## {m['display_name']}\n\n{text}")
                if sections:
                    result["final_trade_decision"] = "\n\n".join(sections)

        node_errors = result.get("_node_errors")
        if node_errors:
            result["degraded_nodes"] = node_errors
            logger.warning(
                f"[WorkflowEngine] There is a downgrade node in the workflow: "
                f"{list(node_errors.keys())}"
            )

        logger.info(
            f"[WorkflowEngine] Dynamic output collection completed: "
            f"{len(structured)} reports, {len(manifest)} Article manifest"
        )
        return result

    def _build_builtin_output(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Built-in workflow output logic (dynamic fields + backward compatible)"""
        # Dynamically derive report field list (new Agent's output_field is automatically included)
        agent_ids = self._extract_agent_ids(self._definition) if self._definition else []
        report_fields = _get_dynamic_report_fields(agent_ids) if agent_ids else _BUILTIN_REPORT_FIELDS
        
        # Display name mapping for built-in fields
        builtin_display_names = {
            "market_report": "📈 Market Technology Research",
            "sentiment_report": "💭 emotion research",
            "news_report": "📰 Journalism Research",
            "fundamentals_report": "💰 fundamental research",
            "index_report": "📊 market environment research",
            "sector_report": "🏭 Industry sector research",
            "social_report": "💭 social media research",
            "chip_report": "🧮 Chip distribution research",
            "bull_report": "🐂 Optimistic Scenario Researcher",
            "bear_report": "🐻 Prudential Scenario Researcher",
            "investment_plan": "📋 Research Manager Briefing",
            "trader_investment_plan": "🧩 research brief",
            "risky_opinion": "🔥 Highly resilient scenario perspective",
            "safe_opinion": "🛡️ defensive situational view",
            "neutral_opinion": "⚖️ base case view",
            "risk_assessment": "⚠️ Risk review conclusion",
            "risk_management_decision": "⚠️ Risk review conclusion",
            "final_trade_decision": "📝 Comprehensive research conclusion",
        }
        
        # Display name cache of workshop Agent (read from agent_configs)
        workshop_display_names = {}
        try:
            from tradingagents.config.mongodb_utils import build_mongodb_connection_string, get_mongodb_database_name
            from pymongo import MongoClient as _MC
            _client = _MC(build_mongodb_connection_string(), serverSelectionTimeoutMS=2000)
            _db = _client[get_mongodb_database_name()]
            _docs = list(_db.agent_configs.find(
                {"enabled": True, "version_status": "active", "runtime_status": "active"},
                {"agent_id": 1, "display_name": 1, "name": 1, "output_field": 1}
            ))
            _client.close()
            for _doc in _docs:
                _output_field = _doc.get("output_field")
                if _output_field:
                    _display_name = _doc.get("display_name") or _doc.get("name")
                    if _display_name:
                        workshop_display_names[_output_field] = f"📊 {_display_name}"
        except Exception as _e:
            logger.warning(f"⚠️ [WorkflowEngine] Failed to read workshop Agent display name: {_e}")
        
        structured = {}
        manifest = []
        
        for idx, f in enumerate(report_fields):
            if f not in result:
                continue
                
            text = self._extract_text_value(result.get(f))
            success = bool(isinstance(text, str) and text.strip())
            
            d = {"content": text, "success": success}
            if f == "bull_report":
                d["stance"] = "bull"
            if f == "bear_report":
                d["stance"] = "bear"
            structured[f] = d
            
            # Get display name
            display_name = workshop_display_names.get(f) or builtin_display_names.get(f) or f.replace("_", " ").title()
            
            # allocate category
            category = "analyst"
            if f in ["bull_report", "bear_report", "investment_plan", "trader_investment_plan", "research_team_decision"]:
                category = "research"
            elif f in ["risky_opinion", "safe_opinion", "neutral_opinion", "risk_assessment", "risk_management_decision"]:
                category = "risk"
            elif f == "final_trade_decision":
                category = "manager"
            
            manifest.append({
                "field": f,
                "display_name": display_name,
                "category": category,
                "order": idx,
                "is_primary": f == "final_trade_decision",
                "format_hint": "markdown",
                "icon": "📊",
                "description": "",
                "has_content": success,
            })
        
        result["structured_reports"] = structured
        result["report_manifest"] = manifest

        existing_ftd = result.get("final_trade_decision")
        has_action = existing_ftd and isinstance(existing_ftd, dict) and (
            existing_ftd.get("action") or existing_ftd.get("analysis_view")
        )
        if has_action:
            action = existing_ftd.get("action") or existing_ftd.get("analysis_view")
            logger.info(
                f"[WorkflowEngine] Using RiskManagerV2 final_trade_decision: "
                f"action={action}, confidence={existing_ftd.get('confidence')}"
            )
        else:
            final_trade_decision = self._generate_final_trade_decision(result)
            if final_trade_decision:
                result["final_trade_decision"] = final_trade_decision

        node_errors = result.get("_node_errors")
        if node_errors:
            result["degraded_nodes"] = node_errors
            logger.warning(
                f"[WorkflowEngine] There is a downgrade node in the built-in workflow: "
                f"{list(node_errors.keys())}"
            )
        return result

    def _generate_final_trade_decision(self, state: Dict[str, Any]) -> str:
        """
        Generate final research conclusions

        Taking into account the following:
        1. investment_plan (Summary of research observations from a research integrator)
        2. trader_investment_plan (Integration opinions from research integrators)
        3. risk_assessment (Risk Assessor s Risk Review Conclusions)

        Args:
            state: Workflow execution status

        Returns:
            Final research conclusion text (Markdown format)
        """
        # 🔍 Debugging: Print key fields in state
        logger.debug(f"🔍 [WorkflowEngine] state fields in: {list(state.keys())}")
        logger.debug(f"🔍 [WorkflowEngine] investment_plan exist: {'investment_plan' in state}")
        logger.debug(f"🔍 [WorkflowEngine] trader_investment_plan exist: {'trader_investment_plan' in state}")
        logger.debug(f"🔍 [WorkflowEngine] risk_assessment exist: {'risk_assessment' in state}")

        # Extract individual reports
        investment_plan = self._extract_text_from_state(state, "investment_plan")
        trader_plan = self._extract_text_from_state(state, "trader_investment_plan")
        risk_assessment = self._extract_text_from_state(state, "risk_assessment")

        # 🔍 Debugging: Print extraction results
        logger.debug(f"🔍 [WorkflowEngine] investment_plan length: {len(investment_plan)}")
        logger.debug(f"🔍 [WorkflowEngine] trader_plan length: {len(trader_plan)}")
        logger.debug(f"🔍 [WorkflowEngine] risk_assessment length: {len(risk_assessment)}")

        # If all three are empty, return an empty string
        if not any([investment_plan, trader_plan, risk_assessment]):
            logger.warning("⚠️ [WorkflowEngine] Unable to generate final_trade_decision: all input reports are empty")
            return ""

        # 🔥 New solution: simply splice three reports (maintain original behavior)
        # Note: This is just splicing, not comprehensive analysis.
        # The real comprehensive decision is extracted from investment_plan by TaskAnalysisService
        sections = []

        if investment_plan:
            sections.append(f"## 📋 Research conclusion\n\n{investment_plan}")

        if trader_plan:
            sections.append(f"## 🧩 Research and integrate opinions\n\n{trader_plan}")

        if risk_assessment:
            sections.append(f"## 🛡️ Risk review conclusion\n\n{risk_assessment}")

        final_decision = "\n\n".join(sections)
        logger.info(f"✅ [WorkflowEngine] Generate final_trade_decision, containing {len(sections)} parts")
        logger.info(f"✅ [WorkflowEngine] Generate final_trade_decision, length: {len(final_decision)}")
        logger.debug(f"🔍 [WorkflowEngine] final_trade_decision The first 500 characters of the content:\n{final_decision[:500]}")

        return final_decision

    def _extract_text_from_state(self, state: Dict[str, Any], field: str) -> str:
        """
        Extract text content from state

        Args:
            state: Workflow execution status
            field: Field name

        Returns:
            Extracted text content
        """
        value = state.get(field)

        # 🔍 debug log
        logger.debug(f"🔍 [_extract_text_from_state] Extract fields: {field}")
        logger.debug(f"🔍 [_extract_text_from_state] value type: {type(value)}")

        if value is None:
            logger.debug(f"🔍 [_extract_text_from_state] {field} is None, returns an empty string")
            return ""

        if isinstance(value, str):
            logger.debug(f"🔍 [_extract_text_from_state] {field} is a string, length: {len(value)}")
            logger.debug(f"🔍 [_extract_text_from_state] {field} The first 200 characters of the content: {value[:200]}")
            return value.strip()

        if isinstance(value, dict):
            logger.debug(f"🔍 [_extract_text_from_state] {field} is a dictionary, field: {list(value.keys())}")
            # 🛡️ Q1: Failure/empty response status is not reported——identify {'success': False, 'error': ...} (Node abnormality)
            # with {'content': '', 'success': True} (Empty response is packaged as success) Two types of exception packaging,
            # Render friendly hints instead of bare dict strings
            _content_val = value.get("content")
            if value.get("success") is False or (
                value.get("success") is True
                and not (isinstance(_content_val, str) and _content_val.strip())
            ):
                _err = value.get("error") or "Model response exception (empty content)"
                logger.warning(
                    f"⚠️ [_extract_text_from_state] {field} It is a failure/empty response form,"
                    f"Report content will be replaced with prompts: success={value.get('success')}, error={_err}"
                )
                return f"> ⚠️ **Generation of this section failed**: {_err}. It is recommended to reanalyze to get the full report."
            # Try to extract text from dictionary
            for key in ("content", "markdown", "text", "message", "report"):
                text = value.get(key)
                if isinstance(text, str) and text.strip():
                    logger.debug(f"🔍 [_extract_text_from_state] from {field}.{key} Extract to text, length: {len(text)}")
                    logger.debug(f"🔍 [_extract_text_from_state] The first 200 characters of the content: {text[:200]}")
                    return text.strip()

            logger.debug(f"🔍 [_extract_text_from_state] {field} Text field not found in dictionary")

        # Convert other types to string
        result = str(value).strip()
        logger.debug(f"🔍 [_extract_text_from_state] {field} Convert to string, length: {len(result)}")
        return result

    @property
    def last_execution(self) -> Optional[WorkflowExecution]:
        """Last execution record"""
        return self._current_execution
