from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['agent_executor', 'analysis_trigger', 'data_sync_status', 'export_table_excel_tool', 'favorite_manager', 'fetch_url', 'gain_alerts', 'manual_reader', 'paper_trading_status', 'position_analysis', 'recent_search', 'report_query', 'risk_alerts', 'running_tasks', 'schedule_manager', 'stock_sync_ops', 'system_status', 'token_usage', 'topic_manager', 'trade_review_ops', 'user_activity', 'user_state', 'watchlist_manager', 'web_search']:
    _sys.modules[f"{__name__}.{_sub}"] = _self_mod
    _top = _sub.split(".")[0]
    setattr(_self_mod, _top, _self_mod)

# === agent_executor ===
"""
Agent Call tool

Allow the smart assistant to directly call the encapsulated Agent as a complete capability unit.
Instead of always breaking it into multiple underlying tools and rearranging it.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.tools import tool

from core.collaboration_runtime import (
    InvocationArtifactRef,
    InvocationPolicy,
    InvocationProvenance,
    InvocationRequest,
    InvocationResult,
    InvocationSourceType,
    InvocationStatus,
    InvocationTargetType,
)
from core.tools.base import register_tool
from core.tools.context import get_current_assistant_thread_id, require_current_user_id

logger = logging.getLogger(__name__)

_ALLOWED_AGENT_CATEGORIES = {"analyst", "researcher", "manager", "risk", "trader"}
_DEFAULT_CALLABLE_SURFACES = {"assistant", "workflow"}


def _latest_trade_date() -> str:
    now = datetime.now()
    if now.weekday() == 5:
        now = now - timedelta(days=1)
    elif now.weekday() == 6:
        now = now - timedelta(days=2)
    return now.strftime("%Y-%m-%d")


def _normalize_text(value: Optional[str]) -> str:
    text = (value or "").strip().lower()
    for token in [" ", "_", "-", "（", "）", "(", ")", "/", "\\"]:
        text = text.replace(token, "")
    return text


def _get_sync_db():
    from app.core.database import get_mongo_db_sync

    return get_mongo_db_sync()


def _is_orphaned_workshop_agent_config(doc: Dict[str, Any], db: Any) -> bool:
    metadata = doc.get("metadata") or {}
    source = str(metadata.get("source") or "").strip().lower()
    if source != "agent_workshop":
        return False

    version_id = str(metadata.get("version_id") or "").strip()
    spec_id = str(metadata.get("spec_id") or "").strip()

    try:
        if version_id and db.agent_versions.find_one({"version_id": version_id}, {"_id": 1}):
            return False
        if spec_id and db.agent_specs.find_one({"spec_id": spec_id}, {"_id": 1}):
            return False
    except Exception as exc:
        logger.warning("[assistant agent executor] Failed to check workshop Agent associated assets: %s", exc)
        return False

    return bool(version_id or spec_id)


def _collect_callable_agents() -> List[Dict[str, Any]]:
    from core.agents import get_registry

    entries: Dict[str, Dict[str, Any]] = {}
    registry = get_registry()

    for metadata in registry.list_all():
        category = getattr(metadata.category, "value", str(metadata.category or ""))
        if category not in _ALLOWED_AGENT_CATEGORIES:
            continue
        entries[metadata.id] = {
            "agent_id": metadata.id,
            "name": getattr(metadata, "name", metadata.id),
            "description": getattr(metadata, "description", "") or "",
            "category": category,
            "source": "builtin",
            "output_field": getattr(metadata, "output_field", None),
            "callable_surfaces": list(_DEFAULT_CALLABLE_SURFACES),
        }

    try:
        db = _get_sync_db()
        docs = db.agent_configs.find({"enabled": True}, {"_id": 0})
        for doc in docs:
            agent_id = (doc.get("agent_id") or "").strip()
            if not agent_id:
                continue
            if _is_orphaned_workshop_agent_config(doc, db):
                continue
            category = str(doc.get("category") or "analyst")
            if category not in _ALLOWED_AGENT_CATEGORIES:
                continue
            entries[agent_id] = {
                "agent_id": agent_id,
                "name": doc.get("name") or agent_id,
                "description": doc.get("description") or "",
                "category": category,
                "source": (doc.get("metadata") or {}).get("source") or "agent_config",
                "output_field": doc.get("output_field") or (doc.get("metadata") or {}).get("output_field"),
                "callable_surfaces": list(
                    (doc.get("metadata") or {}).get("callable_surfaces") or _DEFAULT_CALLABLE_SURFACES
                ),
            }
    except Exception as exc:
        logger.warning("[assistant agent executor] Loading agent_configs failed: %s", exc)

    return list(entries.values())


def _search_callable_agents(keyword: Optional[str]) -> List[Dict[str, Any]]:
    entries = _collect_callable_agents()
    normalized_keyword = _normalize_text(keyword)
    if not normalized_keyword:
        return sorted(entries, key=lambda item: item["agent_id"])

    matches: List[Dict[str, Any]] = []
    for item in entries:
        haystack = "|".join([
            _normalize_text(item.get("agent_id")),
            _normalize_text(item.get("name")),
            _normalize_text(item.get("description")),
            _normalize_text(item.get("category")),
        ])
        if normalized_keyword in haystack:
            matches.append(item)
    return sorted(matches, key=lambda item: item["agent_id"])


def _resolve_callable_agent(agent_identifier: str) -> Dict[str, Any]:
    entries = _collect_callable_agents()
    normalized_identifier = _normalize_text(agent_identifier)
    if not normalized_identifier:
        raise ValueError("agent_identifier cannot be empty")

    exact_matches = [
        item for item in entries
        if normalized_identifier in {
            _normalize_text(item.get("agent_id")),
            _normalize_text(item.get("name")),
        }
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        names = "、".join(f"{item['name']}({item['agent_id']})" for item in exact_matches[:5])
        raise ValueError(f"Matched multiple Agents:{names}. Please use a more precise agent_id instead.")

    fuzzy_matches = _search_callable_agents(agent_identifier)
    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0]
    if len(fuzzy_matches) > 1:
        names = "、".join(f"{item['name']}({item['agent_id']})" for item in fuzzy_matches[:5])
        raise ValueError(f"Find multiple possible Agents:{names}. Please specify agent_id explicitly.")

    raise ValueError(f"Callable Agent not found:{agent_identifier}")


def _ensure_surface_access(agent_entry: Dict[str, Any], surface: str) -> None:
    allowed_surfaces = {
        str(item).strip().lower()
        for item in (agent_entry.get("callable_surfaces") or _DEFAULT_CALLABLE_SURFACES)
        if str(item).strip()
    }
    if surface.strip().lower() not in allowed_surfaces:
        raise ValueError(
            f"Agent {agent_entry.get('agent_id')} 当前不允许从 {surface} 入口直接调用"
        )


def _resolve_assistant_agent_llm(agent_id: str):
    from app.services.simple_analysis_service import get_provider_and_url_by_model_sync
    from core.config.agent_config_manager import AgentConfigManager
    from tradingagents.graph.trading_graph import create_llm_by_provider

    db = _get_sync_db()
    config_doc = db.system_configs.find_one({"is_active": True}, sort=[("version", -1)]) or {}
    default_models = config_doc.get("default_models") or {}
    system_settings = config_doc.get("system_settings") or {}

    target_model = (
        default_models.get("deep_reasoning_model")
        or system_settings.get("deep_reasoning_model")
        or default_models.get("deep_analysis_model")
        or system_settings.get("deep_analysis_model")
        or default_models.get("quick_analysis_model")
        or system_settings.get("quick_analysis_model")
        or config_doc.get("default_llm")
    )
    if not target_model:
        raise RuntimeError("The system is not configured with a model available for Agent invocation")

    provider_info = get_provider_and_url_by_model_sync(target_model)
    if not provider_info:
        raise RuntimeError(f"无法获取模型 {target_model} 的供应商配置")

    agent_config_manager = AgentConfigManager()
    agent_config_manager.set_database(db)
    agent_config = agent_config_manager.get_agent_config(agent_id) or {}
    execution_config = agent_config.get("config") or {}

    provider = provider_info.get("provider") or "deepseek"
    backend_url = provider_info.get("backend_url")
    api_key = provider_info.get("api_key")
    temperature = float(execution_config.get("temperature", 0.2))
    max_tokens = int(execution_config.get("max_tokens", 4000))
    timeout = int(execution_config.get("timeout", 180))

    llm = create_llm_by_provider(
        provider=provider,
        model=target_model,
        backend_url=backend_url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
        api_key=api_key,
    )
    return llm, agent_config


def _extract_agent_report(result: Dict[str, Any], preferred_output_field: Optional[str]) -> str:
    candidate_fields = [
        preferred_output_field,
        "final_report",
        "analysis_report",
        "summary",
        "analysis_result",
    ]
    for field_name in candidate_fields:
        if not field_name:
            continue
        value = result.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for value in result.values():
        if isinstance(value, str) and value.strip() and len(value.strip()) > 20:
            return value.strip()
    return "No valid analysis results were generated."


def _sanitize_structured_output(value: Any, max_text_length: int = 4000) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {"raw_result": str(value)[:max_text_length]}

    sanitized: Dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, str):
            sanitized[key] = item[:max_text_length]
            continue
        if isinstance(item, (int, float, bool)) or item is None:
            sanitized[key] = item
            continue
        if isinstance(item, list):
            sanitized[key] = item[:20]
            continue
        if isinstance(item, dict):
            sanitized[key] = item
            continue
        sanitized[key] = str(item)[:max_text_length]
    return sanitized


def _build_invocation_request(
    *,
    agent_id: str,
    user_id: str,
    thread_id: Optional[str],
    symbol: Optional[str],
    task_description: Optional[str],
    analysis_date: str,
    market_type: str,
) -> InvocationRequest:
    invocation_id = f"ainv_{uuid.uuid4().hex}"
    return InvocationRequest(
        invocation_id=invocation_id,
        target_type=InvocationTargetType.AGENT,
        target_id=agent_id,
        action="execute",
        payload={
            "symbol": (symbol or "").strip() or None,
            "task_description": (task_description or "").strip() or None,
            "analysis_date": analysis_date,
            "market_type": market_type,
        },
        provenance=InvocationProvenance(
            source_type=InvocationSourceType.ASSISTANT,
            source_id="assistant_ops.execute_callable_agent",
            user_id=user_id,
            session_id=thread_id,
            thread_id=thread_id,
            trigger="assistant_tool",
            metadata={"tool_name": "execute_callable_agent"},
        ),
        policy=InvocationPolicy(
            idempotency_key=invocation_id,
            timeout_seconds=180,
            lane="assistant.agent",
        ),
        metadata={
            "invocation_source": "assistant_ops",
            "root_invocation_id": invocation_id,
            "parent_invocation_id": None,
        },
    )


async def _persist_invocation_record(
    request: InvocationRequest,
    result: InvocationResult,
) -> None:
    from app.core.database import get_mongo_db

    db = get_mongo_db()
    await db.assistant_agent_invocations.update_one(
        {"invocation_id": request.invocation_id},
        {
            "$set": {
                "invocation_id": request.invocation_id,
                "root_invocation_id": request.metadata.get("root_invocation_id") or request.invocation_id,
                "parent_invocation_id": request.metadata.get("parent_invocation_id"),
                "user_id": request.provenance.user_id,
                "thread_id": request.provenance.thread_id,
                "target_type": request.target_type.value,
                "target_id": request.target_id,
                "status": result.status.value,
                "request": request.to_python_dict(),
                "result": result.to_python_dict(),
                "updated_at": datetime.utcnow(),
            },
            "$setOnInsert": {"created_at": datetime.utcnow()},
        },
        upsert=True,
    )


async def _write_invocation_ref_to_thread(
    *,
    request: InvocationRequest,
    result: InvocationResult,
    agent_name: str,
    symbol: Optional[str],
) -> None:
    if not request.policy.visible_to_caller:
        return
    if not request.provenance.thread_id or not request.provenance.user_id:
        return

    from app.core.database import get_mongo_db
    from app.services.intelligent_assistant_service import write_report_back_to_assistant_thread

    artifact = InvocationArtifactRef(
        ref_type="agent_invocation",
        artifact_key=request.invocation_id,
        source_collection="assistant_agent_invocations",
        title=f"Agent Call:{agent_name}",
        symbol=(symbol or "").strip() or None,
        summary=(result.output_text or result.error_message or "")[:300],
        output_field=result.output_field,
        metadata={
            "agent_id": request.target_id,
            "status": result.status.value,
        },
    )

    await write_report_back_to_assistant_thread(
        get_mongo_db(),
        user_id=request.provenance.user_id,
        report_ref=artifact.to_report_ref(status=result.status.value),
        preferred_thread_id=request.provenance.thread_id,
        summary_message=None,
    )


@tool
@register_tool(
    tool_id="list_callable_agents",
    name="列出可调用 Agent",
    description="Lists the complete capabilities of Agents that can be directly called by the current smart assistant. It is suitable to first check the valuation, research, risk control, and review Agents in the system that can be directly called.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["agent", "callable", "list", "query", "assistant_ops", "agent_registry", "agent_capability", "agent_search", "ai_agent", "agent_inventory", "agent_lookup"],
    tool_role_hint="supporting",
    output_shape="text",
    preferred_for=["查看可调用Agent", "Agent能力列表", "Agent搜索", "可用Agent查询"],
    when_to_use="It is used when the user wants to see which agents in the system can be directly called and search for available Agent capabilities by keywords. It is usually used as a prequery for execute_callable_agent.",
    returns="Returns a text list containing the name, ID, category, source, and description of the callable Agent.",
)
async def list_callable_agents(
    keyword: Annotated[Optional[str], "Filter Agents by keywords and can pass valuation, review, risk, ETF, sentiment, etc.; if empty, all commonly used ones will be listed. Agent"] = None,
    max_results: Annotated[int, "The maximum number of Agents returned, default 12"] = 12,
) -> str:
    """Lists the complete Agent capabilities that the current intelligent assistant can directly call."""
    matches = _search_callable_agents(keyword)
    limit = max(1, min(int(max_results or 12), 30))
    if not matches:
        return "No matching callable Agent found."

    lines = [f"Agents that can be called directly {len(matches)} , before the following display {min(limit, len(matches))} of:"]
    for item in matches[:limit]:
        lines.append(
            f"- {item['name']} ({item['agent_id']}) | 类别: {item['category']} | 来源: {item['source']}"
        )
        if item.get("description"):
            lines.append(f"  说明: {item['description'][:120]}")
    return "\n".join(lines)


@tool
@register_tool(
    tool_id="execute_callable_agent",
    name="Call Agent s complete capabilities",
    description="Directly call a registered or configured Agent to complete a complete task, which is suitable for valuation, research, review, risk control and other capabilities that have been encapsulated as Agents, rather than being re-decomposed into multiple underlying tools.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="heavy",
    data_source_handling="local_only",
    capability_tags=["agent", "callable", "execute", "invoke", "assistant_ops", "agent_invocation", "agent_execution", "ai_agent", "workflow", "capability_invocation", "agent_call"],
    tool_role_hint="primary",
    output_shape="report",
    preferred_for=["调用Agent能力", "执行完整Agent", "估值分析Agent", "研究Agent调用", "风控Agent调用"],
    when_to_use="It is used when the user wants to directly call an encapsulated Agent to complete complete tasks such as valuation, research, review, and risk control, rather than splitting it into multiple underlying tools.",
    returns="Returns a text report containing the called Agent name, call ID, analysis object, analysis date, task goal and complete analysis results generated by the Agent.",
)
async def execute_callable_agent(
    agent_identifier: Annotated[str, "Agent ID or name, such as valuation_analyst_v1, stock valuation analyst"],
    symbol: Annotated[Optional[str], "Stock code, such as 600519, 000001; some Agents can be empty, but individual stock Agent recommendations must be passed"] = None,
    task_description: Annotated[Optional[str], "The specific task objectives of this call, for example, please provide the comprehensive valuation conclusion of Moutai s PB/PE/DCF"] = None,
    analysis_date: Annotated[Optional[str], "Analysis date, format YYYY-MM-DD; if empty, the latest trading day will be automatically used"] = None,
    market_type: Annotated[Optional[str], "Market type, such as A-shares, Hong Kong stocks, and US stocks; if empty, the default is A-shares"] = None,
) -> str:
    """Directly execute an encapsulated Agent and let the assistant call it as a complete capability."""
    from core.api.workflow_api import WorkflowAPI
    from core.config.agent_config_manager import AgentConfigManager
    from core.workflow.engine import WorkflowEngine
    from core.workflow.templates.single_agent_workflow import SingleAgentWorkflow
    from tradingagents.agents.utils.agent_context import AgentContext

    user_id = require_current_user_id()
    resolved = _resolve_callable_agent(agent_identifier)
    _ensure_surface_access(resolved, "assistant")
    effective_date = (analysis_date or "").strip() or _latest_trade_date()
    effective_market_type = (market_type or "").strip() or "A股"
    current_thread_id = (get_current_assistant_thread_id() or "").strip() or None
    invocation_request = _build_invocation_request(
        agent_id=resolved["agent_id"],
        user_id=user_id,
        thread_id=current_thread_id,
        symbol=symbol,
        task_description=task_description,
        analysis_date=effective_date,
        market_type=effective_market_type,
    )
    started_at = datetime.utcnow()

    logger.info(
        "[execute_callable_agent] Start calling Agent: agent=%s symbol=%s user_id=%s invocation_id=%s",
        resolved["agent_id"],
        symbol,
        user_id,
        invocation_request.invocation_id,
    )

    llm, agent_config = _resolve_assistant_agent_llm(resolved["agent_id"])

    workflow_def = SingleAgentWorkflow(
        agent_id=resolved["agent_id"],
        config={
            "stock_symbol": symbol or "",
            "analysis_date": effective_date,
            "market_type": effective_market_type,
            "agent_config": agent_config,
        },
    )

    engine = WorkflowEngine(
        legacy_config={},
        task_id=invocation_request.invocation_id,
        llm=llm,
    )
    engine.load(workflow_def)

    ctx = AgentContext(
        user_id=user_id,
        session_id=current_thread_id,
        request_id=invocation_request.invocation_id,
        workflow_id=f"assistant_agent_{resolved['agent_id']}",
        node_id=resolved["agent_id"],
        extra={
            "invocation_source": "assistant_ops",
            "invocation_id": invocation_request.invocation_id,
            "root_invocation_id": invocation_request.metadata.get("root_invocation_id") or invocation_request.invocation_id,
            "parent_invocation_id": invocation_request.metadata.get("parent_invocation_id"),
            "invocation_provenance": invocation_request.provenance.to_python_dict(),
            "invocation_lane": invocation_request.policy.lane,
        },
    )

    inputs: Dict[str, Any] = {
        "stock_symbol": symbol or "",
        "ticker": symbol or "",
        "analysis_date": effective_date,
        "trade_date": effective_date,
        "company_of_interest": symbol or "",
        "market_type": effective_market_type,
        "thread_id": current_thread_id,
        "context": ctx,
        "task_description": (task_description or "").strip(),
        "skip_cache": True,
        "prompt_overrides": {},
    }

    if symbol:
        try:
            workflow_api = WorkflowAPI()
            system_vars = workflow_api._prepare_system_variables(stock_code=symbol, analysis_date=effective_date)
            inputs.update(system_vars)
        except Exception as exc:
            logger.warning("[execute_callable_agent] Failed to prepare system variables: %s", exc)

    try:
        result = await engine.execute_async(inputs)

        agent_config_manager = AgentConfigManager()
        agent_config_manager.set_database(_get_sync_db())
        effective_config = agent_config_manager.get_agent_config(resolved["agent_id"]) or agent_config or {}
        preferred_output_field = effective_config.get("output_field") or resolved.get("output_field")
        report = _extract_agent_report(result, preferred_output_field)

        invocation_result = InvocationResult(
            invocation_id=invocation_request.invocation_id,
            target_type=InvocationTargetType.AGENT,
            target_id=resolved["agent_id"],
            status=InvocationStatus.SUCCEEDED,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            output_text=report,
            structured_output=_sanitize_structured_output(result),
            output_field=preferred_output_field,
            artifacts=[
                InvocationArtifactRef(
                    ref_type="agent_invocation",
                    artifact_key=invocation_request.invocation_id,
                    source_collection="assistant_agent_invocations",
                    title=f"Agent Call:{resolved['name']}",
                    symbol=(symbol or "").strip() or None,
                    summary=report[:300],
                    output_field=preferred_output_field,
                )
            ],
            metadata={
                "agent_name": resolved["name"],
                "category": resolved.get("category"),
            },
        )
        await _persist_invocation_record(invocation_request, invocation_result)
        await _write_invocation_ref_to_thread(
            request=invocation_request,
            result=invocation_result,
            agent_name=resolved["name"],
            symbol=symbol,
        )

        return (
            f"已调用 Agent: {resolved['name']} ({resolved['agent_id']})\n"
            f"call ID: {invocation_request.invocation_id}\n"
            f"Analysis object: {symbol or 'unspecified'}\n"
            f"Analysis date: {effective_date}\n"
            f"mission objectives: {(task_description or 'Execution using Agent default responsibilities').strip()}\n\n"
            f"{report}"
        )
    except Exception as exc:
        invocation_result = InvocationResult(
            invocation_id=invocation_request.invocation_id,
            target_type=InvocationTargetType.AGENT,
            target_id=resolved["agent_id"],
            status=InvocationStatus.FAILED,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            error_message=str(exc),
            metadata={
                "agent_name": resolved["name"],
                "category": resolved.get("category"),
            },
        )
        await _persist_invocation_record(invocation_request, invocation_result)
        logger.exception(
            "[execute_callable_agent] Agent call failed: agent=%s invocation_id=%s",
            resolved["agent_id"],
            invocation_request.invocation_id,
        )
        raise

# === analysis_trigger ===
"""
Analysis trigger tools

Provides stock analysis task creation and status query functions.
The analysis task is executed asynchronously, and the tool returns task_id immediately without blocking waiting for results.
"""

import asyncio
import logging
import uuid
from typing import Annotated, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import get_current_assistant_thread_id, get_current_im_channel, require_current_user_id

logger = logging.getLogger(__name__)

# ── Depth mapping ──
_DEPTH_MAP = {1: "快速", 2: "基础", 3: "标准", 4: "深度", 5: "全面"}


def _depth_label(depth: int) -> str:
    return _DEPTH_MAP.get(depth, "标准")


def _analysis_models() -> tuple[str, str]:
    """Get the currently configured fast/deep analysis model and write task_params for the report page to display the model name.

    Consistent with the front-end/normal analysis entry (analysis_service also reads from unified_config),
    Prevent analysis reports initiated by smart assistants from displaying Unknown/Unknown.
    """
    try:
        from app.core.unified_config import unified_config
        return (
            unified_config.get_quick_analysis_model(),
            unified_config.get_deep_analysis_model(),
        )
    except Exception as e:
        logger.warning(f"[analysis_trigger] Failed to read analysis model configuration: {e}")
        return "qwen-turbo", "qwen-max"


@tool
@register_tool(
    tool_id="trigger_stock_analysis",
    name="触发股票分析",
    description="Create a new multi-agent in-depth analysis task, with multiple AI agents collaborating in the background to generate a new analysis report (taking 2-5 minutes).",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["analysis_trigger", "stock_analysis", "trigger", "create", "assistant_ops", "multi_agent_analysis", "async_task", "analysis_task", "deep_analysis"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["stock_analysis_trigger", "deep_analysis_initiation", "multi_agent_analysis", "async_analysis_task_creation"],
    returns="Returns a text message containing the task ID, ticker, depth of analysis, and estimated completion time.",
    when_to_use="It is used when the user requests to initiate in-depth analysis of a certain stock and generate an analysis report. The task is executed asynchronously in the background.",
)
async def trigger_stock_analysis(
    symbol: Annotated[str, "Stock code, 6 digits, such as 000001,600519"],
    depth: Annotated[int, "Analysis Depth 1-5 (1=fast 2=Basics 3=Standard 4=Depth 5=Comprehensive), default 3"] = 3,
    workflow_id: Annotated[Optional[str], "Specify workflow ID, leave blank to automatically select"] = None,
) -> str:
    """Launch a new stock analysis task. The task is executed asynchronously in the background (usually takes 2-5 minutes), and the task ID is returned for subsequent status query or reporting."""
    try:
        from bson import ObjectId
        from app.services.task_analysis_service import get_task_analysis_service
        from app.models.analysis import AnalysisTaskType

        user_id = require_current_user_id()
        logger.info("[trigger_stock_analysis] Start creating tasks: symbol=%s, depth=%s, user_id=%s", symbol, depth, user_id)

        service = get_task_analysis_service()

        # Construct task parameters, and append callback channel information if triggered on the IM channel (used for push notifications after task completion)
        quick_model, deep_model = _analysis_models()
        task_params: dict = {
            "symbol": symbol,
            "market_type": "cn",
            "research_depth": _depth_label(depth),
            "quick_analysis_model": quick_model,
            "deep_analysis_model": deep_model,
        }
        im_channel = get_current_im_channel()
        if im_channel:
            task_params["_im_channel"] = im_channel
            logger.info("[trigger_stock_analysis] IM Channel callback: %s", im_channel)
        current_thread_id = (get_current_assistant_thread_id() or "").strip()
        if current_thread_id:
            task_params["_assistant_thread_id"] = current_thread_id

        task = await service.create_task(
            user_id=ObjectId(user_id),
            task_type=AnalysisTaskType.STOCK_ANALYSIS,
            task_params=task_params,
            engine_type="auto",
            workflow_id=workflow_id,
        )
        logger.info("[trigger_stock_analysis] ✅ Task has been created: task_id=%s", task.task_id)

        # Background execution, no blocking
        bg_task = asyncio.create_task(service.execute_task(task.task_id))
        bg_task.add_done_callback(
            lambda t: logger.error("[trigger_stock_analysis] ❌ Background execution exception: %s", t.exception())
            if not t.cancelled() and t.exception() else None
        )
        logger.info("[trigger_stock_analysis] The background execution task has been submitted")

        return (
            f"✅ 分析任务已创建\n"
            f"- Task ID: {task.task_id}\n"
            f"- stocks: {symbol}\n"
            f"- Depth: {_depth_label(depth)}\n"
            f"- It is expected to take 2-5 minutes to complete. At that time, you can use the View Report function to view the results."
        )
    except Exception as e:
        logger.exception("[trigger_stock_analysis] ❌ Failed to create task: %s", e)
        return f"❌ 创建分析任务失败: {e}"


@tool
@register_tool(
    tool_id="trigger_batch_analysis",
    name="触发批量分析",
    description="Create analysis tasks (batch version of trigger_stock_analysis) for multiple stocks at the same time, returning the batch ID and each task ID. It is suitable for scenarios where users require to analyze multiple stocks at one time.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["analysis_trigger", "batch_analysis", "trigger", "create", "assistant_ops", "multi_stock_analysis", "async_task", "batch_task", "multi_agent_analysis", "batch_create"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["批量股票分析触发", "多只股票同时分析", "批量分析任务创建", "组合分析快速发起"],
    when_to_use="It is used when the user requires to analyze multiple stocks at one time and initiate analysis tasks in batches. Each stock will create a separate background asynchronous task.",
    returns="Returns a text message containing the batch ID, each stock task ID, analysis depth and estimated completion time.",
)
async def trigger_batch_analysis(
    symbols: Annotated[str, "List of stock symbols, separated by commas, such as 000001,600519,000858"],
    depth: Annotated[int, "Analysis depth 1-5, default 3"] = 3,
) -> str:
    """Trigger analysis tasks for multiple stocks in batches. Each stock creates a separate task, and all tasks are executed asynchronously in the background."""
    from bson import ObjectId
    from app.services.task_analysis_service import get_task_analysis_service
    from app.models.analysis import AnalysisTaskType

    user_id = require_current_user_id()
    service = get_task_analysis_service()
    batch_id = str(uuid.uuid4())

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return "❌ Please provide at least one ticker symbol"
    if len(symbol_list) > 10:
        return "❌ A single batch analysis supports up to 10 stocks"

    task_ids = []
    for sym in symbol_list:
        quick_model, deep_model = _analysis_models()
        task_params = {
            "symbol": sym,
            "market_type": "cn",
            "research_depth": _depth_label(depth),
            "quick_analysis_model": quick_model,
            "deep_analysis_model": deep_model,
        }
        current_thread_id = (get_current_assistant_thread_id() or "").strip()
        if current_thread_id:
            task_params["_assistant_thread_id"] = current_thread_id
        task = await service.create_task(
            user_id=ObjectId(user_id),
            task_type=AnalysisTaskType.STOCK_ANALYSIS,
            task_params=task_params,
            engine_type="auto",
            batch_id=batch_id,
        )
        asyncio.create_task(service.execute_task(task.task_id))
        task_ids.append(f"  - {sym}: {task.task_id}")

    return (
        f"✅ 批量分析已创建（{len(symbol_list)} 只股票）\n"
        f"- batch ID: {batch_id}\n"
        f"- Depth: {_depth_label(depth)}\n"
        + "\n".join(task_ids)
        + "\n- Expect 2-5 minutes per stock to complete."
    )


@tool
@register_tool(
    tool_id="get_analysis_status",
    name="查询分析状态",
    description="Query and analyze the execution status and progress of the task (queuing/running/completed/failed) based on the task ID. Used to know whether a previously initiated analysis is complete.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["analysis_trigger", "status_query", "query", "assistant_ops", "task_status", "analysis_progress", "task_tracking", "async_task", "monitor", "progress_check"],
    tool_role_hint="supporting",
    output_shape="text",
    preferred_for=["分析任务状态查询", "分析进度跟踪", "任务完成确认", "异步分析结果检查"],
    when_to_use="Used when the user wants to know whether a previously initiated analysis task has been completed, the current progress, or the cause of failure.",
    returns="Returns a text message containing task status, progress percentage, current step, and (if completed) a summary of the research conclusion tendencies.",
)
async def get_analysis_status(
    task_id: Annotated[str, "分析任务ID"],
) -> str:
    """Query the status, progress, and result summary of a specified analysis task."""
    from app.services.task_analysis_service import get_task_analysis_service

    service = get_task_analysis_service()
    task = await service.get_task(task_id)

    if not task:
        return f"❌ 未找到任务: {task_id}"

    status_emoji = {"pending": "⏳", "processing": "🔄", "completed": "✅", "failed": "❌", "cancelled": "🚫"}
    emoji = status_emoji.get(task.status, "❓")
    lines = [
        f"{emoji} 任务状态: {task.status}",
        f"- 任务ID: {task.task_id}",
        f"- 类型: {task.task_type}",
        f"- 进度: {task.progress}%",
    ]
    if task.current_step:
        lines.append(f"- 当前步骤: {task.current_step}")
    if task.status == "completed" and task.result:
        recommendation = task.result.get("recommendation", "")
        if recommendation:
            lines.append(f"- 研究结论倾向: {recommendation[:200]}")
    if task.status == "failed" and task.error_message:
        lines.append(f"- 错误: {task.error_message[:200]}")
    if task.execution_time > 0:
        lines.append(f"- 耗时: {task.execution_time:.1f}s")

    return "\n".join(lines)


# === data_sync_status ===
"""Use the Q&A bot tool: Query the data synchronization status.

Provides the ability to query the synchronization status of tushare/akshare s historical market prices, financial data, and basic stock data.
Allows using Q&A Assistant to"see"Whether data source synchronization is normal and whether new synchronization needs to be triggered?
Instead of guessing the answer based on the FAQ.

Covered query dimensions:
1. Stock basic data (stock_basic_info / sync_status collection)——Overall status of multi-source synchronization tasks
2. Historical market data (historical_data collection)——Number of stocks covered, date of latest data, number of records
3. Financial data (stock_financial_data collection)——Number of stocks covered, latest update time, number of records
4. Single stock synchronization status (when passing symbol)——The stock s historical/financial/basic data synchronization
5. Running synchronization tasks (stock_sync_tasks collection)——Are there any tasks running?
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


# Synchronization status collection and task identification (consistent with app/services/multi_source_basics_sync_service.py)
_SYNC_STATUS_COLLECTION = "sync_status"
_STOCK_BASICS_JOB_KEY = "stock_basics_multi_source"
_STOCK_SYNC_TASKS_COLLECTION = "stock_sync_tasks"

# data collection
_HISTORICAL_DATA_COLLECTION = "historical_data"
_FINANCIAL_DATA_COLLECTION = "stock_financial_data"
_STOCK_BASIC_INFO_COLLECTION = "stock_basic_info"


def _data_sync_status_format_time_ago(iso_str: Optional[str]) -> str:
    """Format ISO time string to human readable'X hours ago'format."""
    if not iso_str:
        return "从未"
    try:
        # Compatible with time strings with Z and time zone
        normalized = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        now = datetime.now()
        diff = now - dt
        if diff.total_seconds() < 0:
            return dt.strftime("%Y-%m-%d %H:%M")
        if diff.total_seconds() < 60:
            return "刚刚"
        if diff.total_seconds() < 3600:
            return f"{int(diff.total_seconds() / 60)} 分钟前"
        if diff.total_seconds() < 86400:
            return f"{int(diff.total_seconds() / 3600)} 小时前"
        days = int(diff.total_seconds() / 86400)
        if days < 30:
            return f"{days} 天前"
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(iso_str)[:19]


def _summarize_status(status: str) -> tuple[str, str]:
    """Map the internal status field to (emoji, Chinese description). """
    mapping = {
        "success": ("✅", "成功"),
        "success_with_errors": ("⚠️", "成功（含部分错误）"),
        "running": ("🔄", "运行中"),
        "queued": ("⏳", "排队中"),
        "failed": ("❌", "失败"),
        "idle": ("💤", "空闲"),
        "never_run": ("⚪", "从未运行"),
    }
    return mapping.get(status, ("❓", status or "未知"))


async def _query_stock_basics_sync(db) -> Dict[str, Any]:
    """Query the synchronization status of basic stock data (multi-source synchronization task)."""
    try:
        doc = await db[_SYNC_STATUS_COLLECTION].find_one({"job": _STOCK_BASICS_JOB_KEY})
        if not doc:
            return {"available": False}
        doc.pop("_id", None)
        return {"available": True, "doc": doc}
    except Exception as exc:
        logger.warning("[get_data_sync_status] Failed to query basic stock data synchronization status: %s", exc)
        return {"available": False, "error": str(exc)}


async def _query_historical_overview(db) -> Dict[str, Any]:
    """Query the overall situation of historical market data: number of stocks covered, latest data date, and total number of records."""
    try:
        total_records = await db[_HISTORICAL_DATA_COLLECTION].count_documents({})
        distinct_symbols = await db[_HISTORICAL_DATA_COLLECTION].distinct("symbol")
        # Latest data date (descending order by date field)
        latest_doc = await db[_HISTORICAL_DATA_COLLECTION].find_one(
            {}, sort=[("date", -1)]
        )
        latest_date = None
        if latest_doc:
            d = latest_doc.get("date")
            if isinstance(d, datetime):
                latest_date = d.strftime("%Y-%m-%d")
            elif d:
                latest_date = str(d)[:10]
        return {
            "total_records": total_records,
            "symbol_count": len(distinct_symbols) if distinct_symbols else 0,
            "latest_date": latest_date,
        }
    except Exception as exc:
        logger.warning("[get_data_sync_status] Querying the overall situation of historical data failed: %s", exc)
        return {"error": str(exc)}


async def _query_financial_overview(db) -> Dict[str, Any]:
    """Query the overall situation of financial data: number of stocks covered, latest update time, and total number of records."""
    try:
        total_records = await db[_FINANCIAL_DATA_COLLECTION].count_documents({})
        distinct_symbols = await db[_FINANCIAL_DATA_COLLECTION].distinct("symbol")
        latest_doc = await db[_FINANCIAL_DATA_COLLECTION].find_one(
            {}, sort=[("updated_at", -1)]
        )
        latest_updated = None
        if latest_doc:
            u = latest_doc.get("updated_at")
            if isinstance(u, datetime):
                latest_updated = u.isoformat()
            elif u:
                latest_updated = str(u)
        return {
            "total_records": total_records,
            "symbol_count": len(distinct_symbols) if distinct_symbols else 0,
            "latest_updated": latest_updated,
        }
    except Exception as exc:
        logger.warning("[get_data_sync_status] Failed to query the overall financial data: %s", exc)
        return {"error": str(exc)}


async def _query_running_sync_tasks(db) -> List[Dict[str, Any]]:
    """Query the running synchronization tasks."""
    try:
        cursor = db[_STOCK_SYNC_TASKS_COLLECTION].find(
            {"status": {"$in": ["running", "pending", "queued"]}},
            {"task_id": 1, "task_type": 1, "symbol": 1, "status": 1, "started_at": 1, "progress": 1}
        ).limit(10)
        docs = await cursor.to_list(length=10)
        for d in docs:
            d.pop("_id", None)
        return docs
    except Exception as exc:
        logger.warning("[get_data_sync_status] Synchronization task failed during query running: %s", exc)
        return []


async def _query_single_stock_status(db, symbol: str) -> Dict[str, Any]:
    """Query the synchronization status of a single stock. Reuse the logic of stock_sync routing."""
    try:
        normalized = str(symbol).strip().upper()
        if "." in normalized:
            normalized = normalized.split(".", 1)[0]

        # historical data
        hist_doc = await db[_HISTORICAL_DATA_COLLECTION].find_one(
            {"symbol": normalized}, sort=[("date", -1)]
        )
        hist_count = await db[_HISTORICAL_DATA_COLLECTION].count_documents({"symbol": normalized})

        # financial data
        fin_doc = await db[_FINANCIAL_DATA_COLLECTION].find_one(
            {"symbol": normalized}, sort=[("updated_at", -1)]
        )
        fin_count = await db[_FINANCIAL_DATA_COLLECTION].count_documents({"symbol": normalized})

        # Basic data
        basic_doc = await db[_STOCK_BASIC_INFO_COLLECTION].find_one({"symbol": normalized})

        return {
            "symbol": normalized,
            "historical": {
                "last_sync": hist_doc.get("updated_at") if hist_doc else None,
                "last_date": (
                    hist_doc.get("date").strftime("%Y-%m-%d")
                    if hist_doc and isinstance(hist_doc.get("date"), datetime)
                    else (str(hist_doc.get("date"))[:10] if hist_doc and hist_doc.get("date") else None)
                ),
                "total_records": hist_count,
            },
            "financial": {
                "last_sync": fin_doc.get("updated_at") if fin_doc else None,
                "total_records": fin_count,
            },
            "basic": {"available": basic_doc is not None},
        }
    except Exception as exc:
        logger.warning("[get_data_sync_status] Failed to query single stock synchronization status(%s): %s", symbol, exc)
        return {"symbol": symbol, "error": str(exc)}


def _format_single_stock_status(result: Dict[str, Any]) -> List[str]:
    """Format single sync status as a text line."""
    if result.get("error"):
        return [f"❌ 查询失败: {result['error']}"]

    lines = [f"📊 股票 {result.get('symbol', '?')} 的数据同步状态"]

    hist = result.get("historical", {})
    hist_records = hist.get("total_records", 0)
    if hist_records > 0:
        lines.append(
            f"- 历史行情: ✅ 已同步 {hist_records} 条，"
            f"latest date {hist.get('last_date', '?')} (Update time: {_data_sync_status_format_time_ago(hist.get('last_sync'))}) "
        )
    else:
        lines.append("- Historical Quotes: ❌ Not synchronized (the stock has no record in the historical_data collection)")

    fin = result.get("financial", {})
    fin_records = fin.get("total_records", 0)
    if fin_records > 0:
        lines.append(
            f"- 财务数据: ✅ 已同步 {fin_records} 条（更新时间: {_data_sync_status_format_time_ago(fin.get('last_sync'))}）"
        )
    else:
        lines.append("- financial data: ❌ Not synchronized (the stock has no record in the stock_financial_data collection)")

    basic = result.get("basic", {})
    if basic.get("available"):
        lines.append("- Basic data: ✅ Synced")
    else:
        lines.append("- Basic data: ❌ Not synced")

    # Comprehensive judgment
    has_data = hist_records > 0 or fin_records > 0
    if not has_data:
        lines.append("")
        lines.append("💡 This stock has not yet synchronized data. It is recommended to trigger synchronization before analysis.")
        lines.append("   It can be said: Synchronize the data of stock 600519 ")
    elif hist_records == 0:
        lines.append("")
        lines.append("💡 There is a lack of historical market data. If analysis is required, please synchronize historical data first.")
    elif fin_records == 0:
        lines.append("")
        lines.append("💡 Financial data is missing. If you need to do financial analysis, please synchronize the financial data first.")

    return lines


@tool
@register_tool(
    tool_id="get_data_sync_status",
    name="查询数据同步状态",
    description="Query the data synchronization status of tushare/akshare: basic stock data, historical quotes, the latest synchronization time of financial data, the number of records, and whether the synchronization task is running. Supports passing symbol to search single stocks, but not passing it to search the whole stock. When the user asks'Is the data synchronized?''Is the data up to date?''Do you want to resynchronize?'when used.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "data_sync_status", "tushare", "akshare", "historical_data", "financial_data", "sync_status", "data_freshness"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=[
        "数据同步好了吗",
        "数据是否最新",
        "tushare 同步状态",
        "历史数据同步到什么时候",
        "财务数据是否需要更新",
        "中国银行数据同步了吗",
        "是否需要重新同步",
        "有同步任务在跑吗",
    ],
    when_to_use="Used when users ask about data synchronization status, data freshness, whether resynchronization is needed, and whether there are synchronization tasks running. Supports passing symbol parameter to check single stock data synchronization status.",
    returns="Returns a data synchronization status summary in text format, including the latest synchronization time and record number of basic data/historical market data/financial data, running synchronization tasks, and judgment on whether new synchronization needs to be triggered.",
)
async def get_data_sync_status(
    symbol: Annotated[
        Optional[str],
        "Stock code (optional, 6 digits such as 600519). If it is passed in, the synchronization status of the stock will be checked; if it is not passed, the overall data synchronization status will be checked."
    ] = None,
) -> str:
    """Query the data synchronization status."""
    from app.core.database import get_mongo_db

    db = get_mongo_db()

    # ---- Single stock query branch ----
    if symbol and str(symbol).strip():
        result = await _query_single_stock_status(db, str(symbol).strip())
        return "\n".join(_format_single_stock_status(result))

    # ---- Overall query branch ----
    basics_sync = await _query_stock_basics_sync(db)
    hist_overview = await _query_historical_overview(db)
    fin_overview = await _query_financial_overview(db)
    running_tasks = await _query_running_sync_tasks(db)

    lines = ["📊 数据同步状态总览"]

    # 1) Stock basic data synchronization task
    if basics_sync.get("available"):
        doc = basics_sync["doc"]
        status = doc.get("status", "未知")
        emoji, status_cn = _summarize_status(status)
        lines.append("")
        lines.append(" [1] Basic stock data (A-share list+Industry+financial indicators)")
        lines.append(f"- 状态: {emoji} {status_cn}")
        if doc.get("started_at"):
            lines.append(f"- 最近开始时间: {_data_sync_status_format_time_ago(doc.get('started_at'))}")
        if doc.get("finished_at"):
            lines.append(f"- 最近完成时间: {_data_sync_status_format_time_ago(doc.get('finished_at'))}")
        total = doc.get("total", 0) or 0
        inserted = doc.get("inserted", 0) or 0
        updated = doc.get("updated", 0) or 0
        errors = doc.get("errors", 0) or 0
        if total > 0 or inserted > 0 or updated > 0:
            lines.append(f"- 总数 {total}：新增 {inserted}，更新 {updated}，错误 {errors}")
        if doc.get("last_trade_date"):
            lines.append(f"- 最近交易日: {doc.get('last_trade_date')}")
        sources_used = doc.get("data_sources_used") or []
        if sources_used:
            lines.append(f"- 使用的数据源: {', '.join(sources_used)}")
        if doc.get("message") and status in {"failed", "success_with_errors"}:
            lines.append(f"- 备注: {doc.get('message')}")
    else:
        lines.append("")
        lines.append(" [1] Basic stock data: ⚪ No synchronization task has ever been run")

    # 2) The overall situation of historical market data
    lines.append("")
    lines.append(" [2] Historical market data (historical_data)")
    if hist_overview.get("error"):
        lines.append(f"- ❌ 查询失败: {hist_overview['error']}")
    else:
        symbol_count = hist_overview.get("symbol_count", 0)
        total_records = hist_overview.get("total_records", 0)
        latest_date = hist_overview.get("latest_date")
        lines.append(f"- 已覆盖股票数: {symbol_count}")
        lines.append(f"- 总记录数: {total_records}")
        lines.append(f"- 最新数据日期: {latest_date or '无'}")
        if symbol_count == 0:
            lines.append("- ⚠️ The data is empty. It is recommended to trigger the synchronization of basic stock data before synchronizing single stocks.")

    # 3) Overall financial data
    lines.append("")
    lines.append(" [3] Financial data (stock_financial_data)")
    if fin_overview.get("error"):
        lines.append(f"- ❌ 查询失败: {fin_overview['error']}")
    else:
        symbol_count = fin_overview.get("symbol_count", 0)
        total_records = fin_overview.get("total_records", 0)
        latest_updated = fin_overview.get("latest_updated")
        lines.append(f"- 已覆盖股票数: {symbol_count}")
        lines.append(f"- 总记录数: {total_records}")
        lines.append(f"- 最近更新时间: {_data_sync_status_format_time_ago(latest_updated)}")

    # 4) Running sync tasks
    lines.append("")
    lines.append("【4】运行中的同步任务")
    if not running_tasks:
        lines.append("- 💤 There are currently no sync tasks running")
    else:
        lines.append(f"- 🔄 共 {len(running_tasks)} 个任务在运行:")
        for t in running_tasks[:5]:
            task_type = t.get("task_type", "?")
            sym = t.get("symbol", "?")
            st = t.get("status", "?")
            started = _data_sync_status_format_time_ago(t.get("started_at")) if t.get("started_at") else "?"
            progress = t.get("progress")
            progress_str = f", Progress {progress}" if progress is not None else ""
            lines.append(f"  • [{task_type}] {sym} | {st} | 开始于 {started}{progress_str}")

    # 5) Comprehensive suggestions
    lines.append("")
    lines.append("💡 综合判断")
    suggestions = []

    basics_status = basics_sync.get("doc", {}).get("status") if basics_sync.get("available") else "never_run"
    if basics_status == "running":
        suggestions.append("Basic stock data synchronization is running, please wait for completion before viewing details.")
    elif basics_status == "failed":
        suggestions.append("⚠️ The basic stock data synchronization failed last time. It is recommended to check the cause of the error on the Data Synchronization page or trigger it again.")
    elif basics_status in ("never_run", "idle") or not basics_sync.get("available"):
        suggestions.append("The basic stock data has not been synchronized yet. It is recommended to trigger the synchronization of the basic stock data first.")

    hist_symbol_count = hist_overview.get("symbol_count", 0) if not hist_overview.get("error") else 0
    if hist_symbol_count == 0:
        suggestions.append("The historical market data is empty. Stock data needs to be synchronized before analysis.")
    elif hist_symbol_count < 100:
        suggestions.append(f"历史行情仅覆盖 {hist_symbol_count} 只股票，建议补充同步")

    fin_symbol_count = fin_overview.get("symbol_count", 0) if not fin_overview.get("error") else 0
    if fin_symbol_count == 0:
        suggestions.append("The financial data is empty and needs to be synchronized before doing financial analysis.")

    if not suggestions:
        lines.append("- ✅ Data synchronization is normal and analysis tasks can be performed normally.")
    else:
        for s in suggestions:
            lines.append(f"- {s}")

    lines.append("")
    lines.append("📌 Note: JD Cloud version only supports Tushare + AKShare Two data sources, forcing single concurrency, synchronization will be slower")

    return "\n".join(lines)

# === export_table_excel_tool ===
# -*- coding: utf-8 -*-
"""Universal table Excel export tool.

Background: Excel generation capabilities were once tied to the valuation tool (generate_valuation_excel_tool).
That is a data assembly  → LLM Generate specs (max 3 attempts)→ Rendering s heavy-duty pipeline
 (heavy Level 180 seconds, actual measurement 2-6 minutes). The user puts the model that has been calculated in the conversation
 (Sales/revenue forecast, etc.) was incorrectly routed to the valuation tool when exporting to Excel and the model was regenerated.
Resulting in a 420 second timeout.

The division of labor between this tool and valuation tools:
- This tool:**Deterministic export**——LLM Transmit the Markdown table generated in the conversation as it is.
  Pure openpyxl rendering, zero LLM calls, completed in seconds. Any put the data/table just now
  All your needs for making it into Excel should go here.
- Valuation tool: data from local annual reports**Self-built**Valuation model (profit deduction formula + PE scenario),
  Only if explicitly requested by the user"Valuation Calculation Sheet/Valuation Model"when used.

Parameter design (Markdown transparent transmission instead of structured JSON):
LLM There is already a ready-made Markdown table in the context (shown in the reply), you can just paste the original text.
Structured JSON parameters (nested sheets/columns/rows) instead provide LLM with contrivance/rewriting
digital opportunities——Transparent transmission of the original text is correct"Data cannot be tampered with"The observance of ironclad rules.
"""

import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, List, Optional, Tuple

from langchain_core.tools import tool
try:
    from openpyxl import Workbook
except ImportError:
    from unittest.mock import MagicMock as _MM
    Workbook = _MM()
try:
    from openpyxl.styles import Alignment, Font, PatternFill
except ImportError:
    from unittest.mock import MagicMock as _MM
    Alignment = _MM(); Font = _MM(); PatternFill = _MM()
try:
    from openpyxl.utils import get_column_letter
except ImportError:
    from unittest.mock import MagicMock as _MM
    get_column_letter = _MM()

from core.tools.base import register_tool

logger = logging.getLogger(__name__)

_OUTPUT_DIR = "data/deliverables"

# Markdown Table separated rows (|---|---:| etc.)
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
# cell text → numerical value
_INT_RE = re.compile(r"^[+-]?\d+$")
_THOUSANDS_RE = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")
_NUMBER_RE = re.compile(r"^[+-]?\d+(\.\d+)?$")
_PERCENT_RE = re.compile(r"^([+-]?\d+(?:\.\d+)?)\s*%$")


def _parse_cell(text: str) -> Tuple[object, Optional[str]]:
    """cell text → (value, Number format). Returned when it cannot be parsed as a numeric value (original text, None). """
    s = (text or "").strip()
    if not s:
        return "", None
    # Thousandths:1,234 / 12,345.67
    if _THOUSANDS_RE.match(s):
        return float(s.replace(",", "")), "#,##0.##"
    if _INT_RE.match(s):
        return int(s), "#,##0"
    m = _PERCENT_RE.match(s)
    if m:
        return float(m.group(1)) / 100.0, "0.00%"
    if _NUMBER_RE.match(s):
        return float(s), "0.##"
    return s, None


def _split_row(line: str) -> List[str]:
    """Markdown table row → List of cells (tolerating any variation of leading and trailing vertical bars)."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_table_row(line: str) -> bool:
    return "|" in line and not _TABLE_SEP_RE.match(line)


def _parse_markdown_tables(
    markdown: str,
) -> List[Tuple[str, List[List[str]]]]:
    """Parse Markdown text → [(sheet name, Table row list), ...]. 

    For multiple sheets `## Title` Separate; if there is no title, all go into a single sheet.
    Each paragraph allows multiple consecutive tables (the beginning and the end are automatically spliced into one, and the number of columns is based on the table header).
    """
    # press ## title section
    segments: List[Tuple[str, List[str]]] = []
    current_title = ""
    current_lines: List[str] = []
    for line in (markdown or "").splitlines():
        m = re.match(r"^#{1,3}\s+(.+)$", line.strip())
        if m:
            if any(_is_table_row(l) for l in current_lines):
                segments.append((current_title, list(current_lines)))
            current_title = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if any(_is_table_row(l) for l in current_lines):
        segments.append((current_title, list(current_lines)))

    if not segments:
        return []

    result: List[Tuple[str, List[List[str]]]] = []
    for title, lines in segments:
        rows: List[List[str]] = []
        for line in lines:
            if _is_table_row(line):
                rows.append(_split_row(line))
        if rows:
            result.append((title or f"表格{len(result) + 1}", rows))
    return result


def _display_width(text: str) -> float:
    """Estimated display width: 2 for Chinese/full-width characters."""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(text))


def _sanitize_sheet_name(name: str, used: set) -> str:
    """Clean sheet names (Excel limitations:≤31 characters, disabled :\\/?*[]) . """
    clean = re.sub(r"[:\\/?*\[\]]", "_", (name or "").strip())[:31] or "Sheet"
    base, i = clean, 2
    while clean in used:
        suffix = f"_{i}"
        clean = base[: 31 - len(suffix)] + suffix
        i += 1
    used.add(clean)
    return clean


def _sanitize_filename_part(title: str) -> str:
    """Title → File name security fragment (retain Chinese characters, remove illegal characters).

    half-angle brackets () Must be replaced with full-width: unescaped half-width brackets in markdown link target
    The URL will be truncated according to CommonMark rules, resulting in incomplete download links.
    """
    slug = re.sub(r"[\\/:*?\"<>|\s]+", "_", (title or "").strip())
    slug = slug.replace("(", "（").replace(")", "）")
    slug = re.sub(r"_{2,}", "_", slug).strip("_")
    return slug[:40] or "table"


@tool
@register_tool(
    tool_id="export_table_excel_tool",
    name="表格Excel导出",
    description=(
        "Export the data table (original Markdown table) generated in the conversation to an Excel file (xlsx),"
        "Supports multiple tables divided into Sheets. Pure deterministic rendering, no data is regenerated or modified, and it is completed in seconds."
        "All numbers to be exported have already appeared in the conversation (forecast results, calculation tables, comparison tables, etc.),"
        "No matter what the user says'made Excel''Generate data table''Make a model table'Still'Export', This tool should be called"
        "Remodeling or switching to other modeling tools for this purpose is strictly prohibited."
    ),
    category="utility",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    capability_tags=[
        "excel_export", "table_export", "deliverable_generation",
        "markdown_to_excel", "data_export",
    ],
    tool_role_hint="specialized",
    output_shape="structured_markdown",
    when_to_use=(
        "The data/table/prediction results to be exported have been generated in the current conversation (the Markdown table has appeared in the LLM reply),"
        "Called when the user now requires them to be made into Excel/datasheet files——Just transmit the original text of the form verbatim."
        "For multiple tables '## table name' Separate. The user s statement may be'Make a model''Generate data table''Export'Wait,"
        "Use this tool whenever the data comes from conversational context and does not require recalculation."
    ),
    when_not_to_use=(
        "User explicit request'Valuation calculation sheet/valuation model/profit deduction/PE scenario' (Requires formula linkage"
        "financial model), use generate_valuation_excel_tool."
    ),
    returns=(
        "Markdown Text: export results, summary of rows and columns of each Sheet, file download link;"
        "Return an explicit failure description when there is no parsable table."
    ),
    example=(
        "export_table_excel_tool(title='Cyrus revenue forecast', "
        "markdown_tables='## Monthly Sales Forecast\\n| month | M9 | M7 |\\n|---|---:|---:|\\n| 2026-09 | 10500 | 8000 |')"
    ),
    related_tools=["generate_valuation_excel_tool"],
)
def export_table_excel_tool(
    title: Annotated[str, "Table theme (for file names and document titles), such as'Cyrus revenue forecast'"],
    markdown_tables: Annotated[
        str,
        "Markdown The original text of the form (directly pass through the form generated in the conversation, copy it verbatim, and it is strictly prohibited to rewrite any numbers)."
        "For multiple forms '## table name' Header rows are separated, and each header becomes a Sheet in Excel.",
    ],
    notes: Annotated[str, "Optional: Additional explanation (data source, caliber, assumptions, etc.), written at the bottom of the table"] = "",
) -> str:
    """Export the Markdown table in the conversation to an Excel file.

    Args:
        title: Table theme (file name)
        markdown_tables: Markdown Original form text, used for multiple sheets ## title separator
        notes: Optional footnote

    Returns:
        Markdown text(result summary + Download link, or failure instructions)
    """
    t0 = time.time()
    try:
        parsed = _parse_markdown_tables(markdown_tables or "")
        if not parsed:
            return (
                "### Table export failed\n\n"
                "The Markdown table was not parsed in the incoming content (required `|` Separated header rows and data rows).\n\n"
                "*Please confirm the table contents to be exported and try again.*"
            )

        wb = Workbook()
        wb.remove(wb.active)

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="4472C4")
        header_align = Alignment(horizontal="center", vertical="center")
        used_names: set = set()
        sheet_summaries: List[str] = []

        for sheet_title, rows in parsed:
            ws = wb.create_sheet(title=_sanitize_sheet_name(sheet_title, used_names))
            # Header = First line (the following delimited lines have been skipped during parsing)
            header = rows[0]
            data_rows = rows[1:]
            # Filter empty lines
            data_rows = [r for r in data_rows if any(c for c in r)]

            for col_idx, cell_text in enumerate(header, start=1):
                cell = ws.cell(row=1, column=col_idx, value=cell_text)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_align

            col_widths = [_display_width(h) + 4 for h in header]

            for row_idx, row in enumerate(data_rows, start=2):
                for col_idx in range(len(header)):
                    text = row[col_idx] if col_idx < len(row) else ""
                    value, num_fmt = _parse_cell(text)
                    cell = ws.cell(row=row_idx, column=col_idx + 1, value=value)
                    if num_fmt:
                        cell.number_format = num_fmt
                        cell.alignment = Alignment(horizontal="right")
                    if col_idx < len(row):
                        w = _display_width(text) + 2
                        if w > col_widths[col_idx]:
                            col_widths[col_idx] = w

            for col_idx, width in enumerate(col_widths, start=1):
                ws.column_dimensions[get_column_letter(col_idx)].width = min(width, 50)

            # Footnotes:notes + AI Generate Statement (Compliance Requirements)
            foot_row = len(data_rows) + 3
            footnotes = []
            if notes:
                footnotes.append(f"Description:{notes}")
            footnotes.append("This table is generated by AI and is for research reference only and does not constitute investment advice.")
            for i, note in enumerate(footnotes):
                c = ws.cell(row=foot_row + i, column=1, value=note)
                c.font = Font(size=9, color="808080")

            ws.freeze_panes = "A2"
            sheet_summaries.append(f"- **{sheet_title}**：{len(header)} 列 × {len(data_rows)} 行")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"table_{_sanitize_filename_part(title)}_{stamp}.xlsx"
        output_dir = Path(_OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename
        wb.save(str(output_path))

        # Signed download link: The browser clicks directly without JWT header and must use presigned URL for authentication.
        from urllib.parse import quote

        from core.deliverables.download_links import sign_deliverable_query

        download_url = (
            f"/api/assistant/deliverables/{quote(filename)}"
            f"?{sign_deliverable_query(filename)}"
        )

        elapsed = time.time() - t0
        return (
            f"### Excel 表格已导出 ✅\n\n"
            f"**{title}** · {len(parsed)} a Sheet · Time consuming to generate {elapsed:.1f} seconds\n\n"
            + "\n".join(sheet_summaries)
            + f"\n\n"
            f"📎 [Download Excel sheet]({download_url})\n\n"
            f"The tabular data comes verbatim from the model results generated in the conversation without any modifications."
            f"{'Description:' + notes if notes else ''}\n\n"
            f"*This table is generated by AI and is for research reference only and does not constitute investment advice.*"
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[ExportTableExcelTool] Export failed: %s", exc, exc_info=True)
        return f"### Table export failed\n\n**Execution exception**: {exc}\n\n*Please try again or simplify the table content.*"

# === favorite_manager ===
"""
Stock watchlist list management tool

Provides the ability to add stocks to the stock watch list in batches, suitable for linking with intelligent stock selection results.
"""

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _favorite_manager_normalize_market(market: str) -> str:
    value = (market or "A股").strip().upper()
    if value in ("A股", "CN", "SH", "SZ", "SSE", "SZSE", "BJ", "BSE"):
        return "A股"
    if value in ("港股", "HK", "HKEX"):
        return "港股"
    if value in ("美股", "US", "NASDAQ", "NYSE", "AMEX"):
        return "美股"
    return "A股"


def _parse_tags(tags: str) -> list[str]:
    raw = (tags or "").replace("，", ",").replace("、", ",")
    parsed = []
    seen = set()
    for item in raw.split(","):
        tag = item.strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        parsed.append(tag)
    return parsed


@tool
@register_tool(
    tool_id="list_favorite_stocks",
    name="查看股票关注列表",
    description="View the user s stock watch list (that is, the stock watch list list), optionally filtering by tag. The ticker, name, market and existing tags are returned.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["favorite_management", "watchlist", "query", "list", "assistant_ops", "stock_favorites", "stock_watchlist", "tag_filter", "favorites_view", "self_selected_stocks"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["查看股票关注列表列表", "浏览关注的股票", "按标签筛选股票关注列表", "确认已关注的股票"],
    when_to_use="It is used when users want to view their own stock watch list, stock watch list, or filter the stocks they have followed by tags.",
    returns="Returns a list of stock watchlists in text format, containing stock name, symbol, market, and existing tags.",
)
async def list_favorite_stocks(
    tag: Annotated[str, "Optional, filter by tag, such as Buffett; leave blank to view all stocks of interest"] = "",
) -> str:
    """View the current user s stock watch list (i.e. stock watch list), and supports filtering by tags."""
    from app.services.favorites_service import favorites_service

    user_id = require_current_user_id()
    favorites = await favorites_service.get_user_favorites(user_id)

    normalized_tag = str(tag or "").strip()
    if normalized_tag:
        favorites = [
            item for item in favorites
            if normalized_tag in list(item.get("tags") or [])
        ]

    if not favorites:
        if normalized_tag:
            return f"📂 There are no stocks in your watchlist tagged {normalized_tag}] of stocks."
        return "📂 Your stock watchlist is currently empty, no stocks have been added to your watchlist yet."

    lines = []
    for item in favorites:
        code = item.get("stock_code") or "-"
        name = item.get("stock_name") or code
        market = item.get("market") or "A股"
        tags = list(item.get("tags") or [])
        tag_text = f" | 标签: {', '.join(tags)}" if tags else ""
        lines.append(f"- {name} ({code}) | {market}{tag_text}")

    header = (
        f"📂 你的股票关注列表（标签：{normalized_tag}，共 {len(favorites)} 只）"
        if normalized_tag else
        f"📂 你的股票关注列表（共 {len(favorites)} 只）"
    )
    return header + "\n" + "\n".join(lines)


@tool
@register_tool(
    tool_id="add_stocks_to_favorites",
    name="Add stocks to stock watchlist in batches",
    description="Add one or more stocks to the user s stock watch list in batches, which is suitable for saving the recommendation results once after the intelligent stock selection is completed; it supports tagging these stocks at the same time through the tags parameter, and adding tags to the stocks already in the stock watch list.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["favorite_management", "watchlist", "add", "batch_add", "assistant_ops", "stock_favorites", "tag_assignment", "bulk_add", "favorites_update", "self_selected_stocks"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["批量添加股票关注列表", "保存智能选股结果", "给关注股票打标签", "补充已有股票关注列表标签"],
    when_to_use="It is used when the user wants to add one or more stocks to the stock watch list, or save the recommendation results in batches after the intelligent stock selection is completed.",
    returns="Returns a text message with statistics for new, skipped, supplementary tags, and failed tickers.",
)
async def add_stocks_to_favorites(
    stocks_json: Annotated[
        str,
        "Stocks JSON array, e.g. [{\"code\":\"600519\",\"name\":\"Kweichow Moutai\",\"market\":\"A shares\"}]",
    ],
    tags: Annotated[
        str,
        "Optional, tags to be given to these stocks at the same time, separated by commas, for example, Buffett,High dividends",
    ] = "",
) -> str:
    """Add stocks in batches to the current user s stock watch list, and add tags at the same time."""
    from app.services.favorites_service import favorites_service
    from app.services.tags_service import tags_service

    user_id = require_current_user_id()
    parsed_tags = _parse_tags(tags)

    try:
        items = json.loads(stocks_json)
    except json.JSONDecodeError:
        return "❌ The parameter format is wrong, please pass in the stock JSON array."

    if not isinstance(items, list) or not items:
        return "❌ Please provide at least one stock to be added to the stock watchlist."

    normalized_items = []
    seen_codes = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or item.get("symbol") or item.get("stock_code") or "").strip()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        normalized_items.append({
            "code": code,
            "name": str(item.get("name") or item.get("stock_name") or code).strip() or code,
            "market": _favorite_manager_normalize_market(str(item.get("market") or "A股")),
        })

    if not normalized_items:
        return "❌ No valid stock symbol was parsed."

    existing_favorites = await favorites_service.get_user_favorites(user_id)
    existing_map = {
        str(item.get("stock_code") or item.get("symbol") or "").strip(): item
        for item in existing_favorites
        if str(item.get("stock_code") or item.get("symbol") or "").strip()
    }

    if parsed_tags:
        try:
            existing_tags = {
                tag.get("name")
                for tag in await tags_service.list_tags(user_id)
                if tag.get("name")
            }
            for tag_name in parsed_tags:
                if tag_name in existing_tags:
                    continue
                try:
                    await tags_service.create_tag(user_id=user_id, name=tag_name)
                    existing_tags.add(tag_name)
                except Exception:
                    logger.debug("[add_stocks_to_favorites] Failed to create tags, continue to use favorite tag aggregation: %s", tag_name, exc_info=True)
        except Exception:
            logger.debug("[add_stocks_to_favorites] Failed to read/create tags, continue to perform collection update", exc_info=True)

    added_codes = []
    skipped_codes = []
    tagged_codes = []
    failed_codes = []

    for item in normalized_items:
        code = item["code"]
        try:
            existing = existing_map.get(code)
            if existing:
                current_tags = list(existing.get("tags") or [])
                merged_tags = current_tags
                if parsed_tags:
                    merged_tags = list(dict.fromkeys([*current_tags, *parsed_tags]))

                if merged_tags != current_tags:
                    await favorites_service.update_favorite(
                        user_id=user_id,
                        stock_code=code,
                        tags=merged_tags,
                    )
                    tagged_codes.append(code)
                else:
                    skipped_codes.append(code)
                continue

            await favorites_service.add_favorite(
                user_id=user_id,
                stock_code=code,
                stock_name=item["name"],
                market=item["market"],
                tags=parsed_tags,
            )
            added_codes.append(code)
        except Exception as e:
            logger.warning("[add_stocks_to_favorites] Failed to add stock watchlist: %s %s", code, e)
            failed_codes.append(code)

    lines = [
        f"✅ 已添加 {len(added_codes)} 只股票到股票关注列表" if added_codes else "✅ There are no new stocks to watch this time",
    ]
    if added_codes:
        lines.append(f"- 新增: {', '.join(added_codes)}")
    if parsed_tags:
        lines.append(f"- 标签: {', '.join(parsed_tags)}")
    if tagged_codes:
        lines.append(f"- 已补充标签 {len(tagged_codes)} 只: {', '.join(tagged_codes)}")
    if skipped_codes:
        lines.append(f"- 已存在 {len(skipped_codes)} 只: {', '.join(skipped_codes)}")
    if failed_codes:
        lines.append(f"- 失败 {len(failed_codes)} 只: {', '.join(failed_codes)}")

    return "\n".join(lines)

# === fetch_url ===
"""Web Content Scraping Tool - Get the complete body content of a web page."""

import logging
import random
from typing import Annotated
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20
MAX_CONTENT_LENGTH = 8000

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# Tags that need to be removed (navigation, advertising, etc. noise)
REMOVE_TAGS = [
    "script", "style", "nav", "footer", "header", "aside",
    "iframe", "noscript", "form", "button", "input", "select",
    "svg", "img", "video", "audio",
]

# Noisy text features (navigation menus, copyright notices, etc.)
NOISE_PATTERNS = [
    "首页", "登录", "注册", "VIP邮箱", "免费下载", "客户端下载",
    "快速导航", "网易首页", "应用", "安全退出", "移动端",
    " COPYRIGHT ", "@版权", "举报", "分享至", "微信扫码",
    "申请入驻", "客户端", "关注我们", "返回首页", "网站地图",
]


def _resolve_baidu_link(url: str) -> str:
    """If it is a Baidu jump link, parse out the real URL."""
    if "baidu.com/link" not in url and "baidu.php" not in url:
        return url
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": random.choice(USER_AGENTS)},
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=True,
        )
        if resp.url and resp.url != url:
            return resp.url
        soup = BeautifulSoup(resp.text, "html.parser")
        meta = soup.find("meta", attrs={"http-equiv": "refresh"})
        if meta:
            content = meta.get("content", "")
            if "url=" in content.lower():
                real_url = content.split("url=", 1)[-1].strip()
                if real_url.startswith("http"):
                    return real_url
    except Exception as exc:
        logger.warning("Failed to parse Baidu jump link: %s", exc)
    return url


def _is_noise(text: str) -> bool:
    """Determine whether the text is noise such as navigation menu."""
    if not text or len(text) < 10:
        return True
    # If the text is too short, it is most likely a navigation link
    if len(text) < 15 and any(kw in text for kw in ["登录", "注册", "首页", "退出", "关注", "分享"]):
        return True
    # If it contains too many noisy keywords
    noise_count = sum(1 for pattern in NOISE_PATTERNS if pattern in text)
    if noise_count >= 3:
        return True
    return False


def _extract_main_content(soup: BeautifulSoup) -> str:
    """Extract body content from BeautifulSoup, giving priority to the body container."""
    # priority 1: explicit body container
    for selector in [
        ("article", None),
        ("div", "post_body"),  # Baidu Baijiahao
        ("div", "article-content"),  # General articles
        ("div", "post_content"),  # Blog category
        ("div", "main-content"),  # Universal
        ("div", "content"),  # Universal
        ("div", "article_content"),  # NetEase
        ("div", "text"),  # Universal
        ("div", "detail"),  # Details page
        ("div", "post_body"),
        ("div", "art_content"),
        ("div", "article-body"),
        ("div", "news_content"),
        ("div", "TRS_Editor"),
        ("main", None),
    ]:
        tag, cls = selector
        if cls:
            el = soup.find(tag, class_=cls)
        else:
            el = soup.find(tag)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 100:
                return text

    # priority 2: body the longest within div
    body = soup.find("body")
    if not body:
        return ""

    best_text = ""
    best_len = 0
    for div in body.find_all("div"):
        text = div.get_text(separator="\n", strip=True)
        # filter noise
        if _is_noise(text):
            continue
        if len(text) > best_len:
            best_text = text
            best_len = len(text)

    return best_text


def _clean_content(text: str) -> str:
    """Clean up body text, removing redundant blank lines and noise."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if _is_noise(line):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _fetch_page(url: str) -> str:
    """Crawl web content and extract body text."""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    resp = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove unnecessary tags
    for tag in soup(REMOVE_TAGS):
        tag.decompose()

    # Extract title
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)

    # Extract text
    content = _extract_main_content(soup)
    content = _clean_content(content)

    if not content or len(content) < 50:
        return f"Title:{title}\n Links:{url}\n\n Unable to extract body content (page may require JavaScript rendering)."

    # Limit return length
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH] + "\n\n[The content has been truncated, please visit the original webpage for the complete content]"

    return f"Title:{title}\n Links:{url}\n\n{content}"


def run_fetch_url(url: str) -> str:
    """Crawl web content."""
    if not url or not url.strip():
        return "Please provide a link to the web page you want to crawl."

    url = url.strip()

    # If it is a Baidu jump link, first parse the real URL
    if "baidu.com/link" in url or "baidu.php" in url:
        logger.info("解析百度跳转链接: %s", url[:80])
        real_url = _resolve_baidu_link(url)
        if real_url != url:
            logger.info("真实URL: %s", real_url[:80])
            url = real_url

    # Check if it is a Baidu verification page
    if "wappass.baidu.com" in url or "captcha" in url:
        return "The link jumps to the Baidu security verification page and the content cannot be crawled. Please try other search results."

    try:
        logger.info("抓取网页: %s", url[:80])
        return _fetch_page(url)
    except requests.exceptions.Timeout:
        return f"Fetch timeout:{url}"
    except requests.exceptions.ConnectionError as exc:
        return f"Connection failed:{url}\n Error:{exc}"
    except Exception as exc:
        return f"Fetch failed:{url}\n Error:{exc}"


@tool
@register_tool(
    tool_id="fetch_url",
    name="网页内容抓取",
    description="Fetch the complete text content of the specified web page. Use this tool to crawl the full page linked to the search results when the summary information returned by web_search is not detailed enough. Supports parsing Baidu jump links to obtain real URLs. Automatically extract text content and filter out noise such as navigation menus and advertisements.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    data_source_handling="local_only",
    capability_tags=[
        "web_fetch", "content_extraction", "url_read",
        "page_scrape", "information_retrieval", "real_time_info",
    ],
    tool_role_hint="specialized",
    output_shape="report",
    preferred_for=[
        "Get the complete web content of the search results",
        "读取新闻文章原文",
        "查看公告或报告的详细内容",
        "补充搜索摘要中缺失的细节",
    ],
    when_to_use="Used when the summary information of web_search search results is not enough and the complete web page content needs to be obtained.",
    returns="Return the webpage title and body text (up to 8000 characters), and automatically remove irrelevant content such as navigation and advertisements.",
)
def fetch_url(
    url: Annotated[str, "The web link to be crawled can be a direct URL or a jump link from Baidu search results."],
) -> str:
    """Crawl the complete text content of the web page."""
    return run_fetch_url(url)

# === gain_alerts ===
"""
Revenue attention reminder tools

Provides the ability to set, view, and clear revenue attention price (price upper limit) reminders to facilitate users to track, study, and observe prices by themselves.
"""

import logging
from typing import Annotated

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _gain_alerts_normalize_market(market: str) -> str:
    value = (market or "CN").upper()
    if value in ("CN", "A股", "SH", "SZ"):
        return "A股"
    if value in ("HK", "港股"):
        return "港股"
    if value in ("US", "美股"):
        return "美股"
    return "A股"


@tool
@register_tool(
    tool_id="set_stop_gain_alert",
    name="设置收益关注提醒",
    description="Set a price limit (price limit) for stocks to pay attention to, and push notifications through the system when the price is close, making it easier for users to track, research and observe the price. Returns the stock name, symbol, market, and set earnings focus price.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["gain_alerts", "stop_gain", "alert", "set", "assistant_ops", "price_alert", "profit_taking", "notification", "alert_setup", "price_threshold"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["收益关注提醒设置", "收益关注价格配置", "价格上限提醒设置", "价格上限提醒"],
    when_to_use="This is used when the user wants to set a profit follow-up price (price ceiling) for a certain stock, and wants to receive a notification when the price rises to that price, so that he can follow the research and observation price by himself.",
    returns="Returns a text message containing the stock name, symbol, market, and set earnings focus price (price cap).",
)
async def set_stop_gain_alert(
    symbol: Annotated[str, "Stock code, such as 300033, 00700,AAPL"],
    gain_price: Annotated[float, "Pay attention to the price limit (remind you when it reaches or approaches this price)"],
    market: Annotated[str, "Market: CN/HK/US, default CN"] = "CN",
) -> str:
    """Set stock earnings watch price (price cap) alerts."""
    try:
        from app.core.database import get_mongo_db
        from app.services.favorites_service import favorites_service

        user_id = require_current_user_id()
        market_label = _gain_alerts_normalize_market(market)
        db = get_mongo_db()

        name = symbol
        pos = await db.real_positions.find_one({"user_id": user_id, "code": symbol}, {"name": 1})
        if pos and pos.get("name"):
            name = pos["name"]

        exists = await favorites_service.is_favorite(user_id, symbol)
        if not exists:
            await favorites_service.add_favorite(
                user_id=user_id,
                stock_code=symbol,
                stock_name=name,
                market=market_label,
            )

        ok = await favorites_service.update_alert_gain_price(user_id, symbol, gain_price)
        if not ok:
            return f"未找到 {symbol} 的股票关注列表记录，设置收益关注提醒失败。"

        return (
            f"✅ 已设置收益关注提醒（价格上限）\n"
            f"- stocks: {name}({symbol})\n"
            f"- market: {market_label}\n"
            f"- Earnings focus on price: {gain_price:.2f}\n"
            f"When the price approaches or reaches the profit attention price, you will receive a system notification so that you can pay attention to, research and observe the price yourself."
        )
    except Exception as e:
        logger.exception("[set_stop_gain_alert] Failed to set revenue attention reminder: %s", e)
        return f"设置收益关注提醒失败: {e}"


@tool
@register_tool(
    tool_id="list_stop_gain_alerts",
    name="查看收益关注提醒",
    description="View all currently set revenue focus alerts (price caps). Returns the number of alerts and the stock name, symbol, market, and earnings focus price for each alert.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["gain_alerts", "stop_gain", "alert", "list", "query", "assistant_ops", "price_alert", "profit_taking", "alert_query", "notification_list"],
    tool_role_hint="supporting",
    output_shape="text",
    preferred_for=["收益关注提醒查看", "收益关注列表查询", "已配置提醒浏览", "价格上限确认"],
    when_to_use="This is used when the user wants to view all currently set earnings focus reminders (price caps) and confirm which stocks have configured earnings focus prices.",
    returns="Returns a text message, including the number of earnings attention reminders and the stock, market, and earnings attention price (price limit) of each reminder.",
)
async def list_stop_gain_alerts() -> str:
    """View a list of configured revenue focus alerts (price caps)."""
    try:
        from app.services.favorites_service import favorites_service

        user_id = require_current_user_id()
        items = await favorites_service.get_user_favorites(user_id)
        alerts = [item for item in items if item.get("alert_gain_price") is not None]

        if not alerts:
            return "There are currently no revenue focus alerts (price caps) set."

        lines = [f"共 {len(alerts)} 条收益关注提醒（价格上限）：\n"]
        for item in alerts:
            code = item.get("stock_code", "")
            name = item.get("stock_name", code)
            market = item.get("market", "A股")
            gain = item.get("alert_gain_price")
            lines.append(f"- {name}({code}) | {market} | 收益关注价格: {float(gain):.2f}")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("[list_stop_gain_alerts] Failed to view revenue attention reminder: %s", e)
        return f"查看收益关注提醒失败: {e}"


@tool
@register_tool(
    tool_id="clear_stop_gain_alert",
    name="清除收益关注提醒",
    description="Clear the earnings attention reminder price of the specified stock (price limit, only clear the reminder, do not remove the stock attention list). Returns the operation result or a prompt that the configuration is not found.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["gain_alerts", "stop_gain", "alert", "clear", "delete", "assistant_ops", "price_alert", "profit_taking", "alert_removal", "notification_cleanup"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["收益关注提醒清除", "收益关注价格移除", "提醒配置删除", "价格上限取消"],
    when_to_use="It is used when the user wants to clear the earnings attention reminder (price limit) of a certain stock and no longer receive earnings attention notifications for the stock (only clears the reminder, but does not remove the stock watch list).",
    returns="Return a text message to confirm that the revenue attention reminder has been cleared or that the relevant configuration is not found.",
)
async def clear_stop_gain_alert(
    symbol: Annotated[str, "Stock code, such as 300033, 00700,AAPL"],
) -> str:
    """Clear earnings attention alerts (price caps) for a stock."""
    try:
        from app.services.favorites_service import favorites_service

        user_id = require_current_user_id()
        ok = await favorites_service.update_alert_gain_price(user_id, symbol, None)
        if ok:
            return f"✅ 已清除 {symbol} 的收益关注提醒（价格上限）。"
        return f"未找到 {symbol} 的提醒配置，或该股票不在股票关注列表中。"
    except Exception as e:
        logger.exception("[clear_stop_gain_alert] Failed to clear earnings attention reminder: %s", e)
        return f"清除收益关注提醒失败: {e}"

# === manual_reader ===
"""Use the Q&A bot tool: Read the user manual by chapter name.

Allows using Q&A Assistant to"Check"Specific chapter content of the user manual to avoid cramming all 139KB into system prompt words.
Slice by secondary title and return by fuzzy matching of chapter name.

Jingdong cloud version (JDYUN_MODE=true) It will automatically switch to jdyun-user-manual-v3.0.md,
The content is specifically for JD Cloud Edition users (deployment, speed limit, volume name issues, etc.).
"""

import logging
import os
import re
from typing import Annotated, List, Tuple

from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _manual_reader_is_jdyun_mode() -> bool:
    """判断是否为京东云模式"""
    return os.environ.get("JDYUN_MODE", "false").lower() == "true"


def _resolve_manual_path() -> str:
    """Locate the current user manual that should be used.

    Jingdong cloud version (JDYUN_MODE=true) → priority use jdyun-user-manual-v3.0.md
    Standard Edition → priority use user-manual-v3.0.md
    When the corresponding version cannot be found, fall back to the standard version to avoid the manual becoming completely unusable.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # core/tools/implementations/assistant_ops/manual_reader.py -> Project root directory
    project_root = os.path.abspath(os.path.join(current_dir, "..", "..", "..", ".."))
    user_guide_dir = os.path.join(project_root, "docs", "02-user-guide")

    if _manual_reader_is_jdyun_mode():
        # JD Cloud version searches jdyun-user-manual-v3.0.md first and returns to the main manual.
        candidates = [
            os.path.join(user_guide_dir, "jdyun-user-manual-v3.0.md"),
            os.path.join(user_guide_dir, "user-manual-v3.0.md"),
            os.path.join(user_guide_dir, "user-manual.md"),
        ]
    else:
        candidates = [
            os.path.join(user_guide_dir, "user-manual-v3.0.md"),
            os.path.join(user_guide_dir, "user-manual.md"),
            os.path.join(user_guide_dir, "jdyun-user-manual-v3.0.md"),
        ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


def _resolve_all_manual_paths() -> List[Tuple[str, str]]:
    """Lists all available user manuals (in order of priority) for multi-manual searches.

    Return [(manual path, Manual type), ...]
    Manual type: "jdyun" | "standard"
    For the JD Cloud version, put the JD Cloud manual first, and for the standard version, put the main manual first.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", "..", "..", ".."))
    user_guide_dir = os.path.join(project_root, "docs", "02-user-guide")

    standard_path = os.path.join(user_guide_dir, "user-manual-v3.0.md")
    jdyun_path = os.path.join(user_guide_dir, "jdyun-user-manual-v3.0.md")

    manuals = []
    if _manual_reader_is_jdyun_mode():
        if os.path.exists(jdyun_path):
            manuals.append((jdyun_path, "jdyun"))
        if os.path.exists(standard_path):
            manuals.append((standard_path, "standard"))
    else:
        if os.path.exists(standard_path):
            manuals.append((standard_path, "standard"))
        if os.path.exists(jdyun_path):
            manuals.append((jdyun_path, "jdyun"))
    return manuals


def _split_sections(content: str) -> List[Tuple[str, str, int]]:
    """Slice by markdown header.

    Return [(title, body, level), ...]
    level Yes # quantity (1-4)
    """
    sections: List[Tuple[str, str, int]] = []
    # Matches 1-4 at the beginning of the line # followed by space and title
    parts = re.split(r'\n(?=#{1,4}\s+[^\n]+)', content)
    for part in parts:
        match = re.match(r'^(#{1,4})\s+([^\n]+)\n(.*)', part, re.DOTALL)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            body = match.group(3).strip()
            sections.append((title, body, level))
    return sections


def _truncate_to_next_level(body: str, current_level: int) -> str:
    """Cut to the next sibling or higher heading"""
    pattern = re.compile(rf'\n#{{1,{current_level}}}\s+')
    match = pattern.search(body)
    if match:
        return body[:match.start()].strip()
    return body.strip()


def _extract_keyword_fragments(keyword: str, min_len: int = 2) -> List[str]:
    """Extract all contiguous subsegments from the keyword that can be used for fuzzy matching.

    solve"Single container data loss"Unable to match"Q5: Data is lost after a single container is restarted"problem.
    Extract all lengths >= min_len Continuous substrings of , arranged in reverse order of length (long segments are matched first).

    Example:
        "Single container data loss" → ["single container", "data", "lost", "Container data", "data lost", ...]
        "data loss" → ["data", "lost", "data lost"]
    """
    if not keyword or len(keyword) < min_len:
        return []
    fragments = set()
    n = len(keyword)
    for length in range(min_len, n + 1):
        for i in range(n - length + 1):
            frag = keyword[i:i + length]
            if len(frag) >= min_len:
                fragments.add(frag)
    # Sort by length in descending order (longer fragments preferred, more accurate)
    return sorted(fragments, key=len, reverse=True)


def _extract_two_char_fragments(keyword: str) -> List[str]:
    """Extract all 2-word consecutive fragments in the keyword (duplication removed, in order of appearance).

    used for"Most hits"Fuzzy match: A match is considered as long as 60% of the fragments are included in the title.
    solve"Single container data loss" vs "Q5: Data is lost after a single container is restarted" This type of long sentence reorganization problem.

    Example:
        "Single container data loss" → ["single container", "Number of containers", "lost", "lost"]  (Actually"single container","container","According to","lost"Wait)
        Actually take a fixed 2-word window:"Single capacity","container","data","lost"
    """
    if not keyword or len(keyword) < 2:
        return []
    frags = []
    seen = set()
    for i in range(len(keyword) - 1):
        frag = keyword[i:i + 2]
        if frag not in seen:
            seen.add(frag)
            frags.append(frag)
    return frags


@tool
@register_tool(
    tool_id="read_user_manual_section",
    name="读取用户手册章节",
    description="Read the contents of the user manual by chapter name. Support fuzzy matching, such as input'Installation'Can match'Installation and deployment'chapter. When the user asks'How to configure Token''How to activate simulated trading''How to add discretionary stocks''429 What to do about speed limit''Single container data loss'Used when there are operational process issues. JD Cloud Edition users will automatically read the JD Cloud Edition special manual (including answers to JD Cloud-specific questions such as deployment, speed limits, data volumes, etc.).",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "manual", "documentation", "user_guide", "operation_flow", "jdyun_manual"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["怎么配置 Token", "模拟交易怎么开通", "怎么加自选股", "License 怎么激活", "429 限速", "单容器数据丢失", "操作流程", "京东云部署"],
    when_to_use="When users ask about specific operating procedures, function configuration steps, or how to use the system, they should give priority to calling this tool to check the documentation instead of answering from memory.",
    returns="Returns the user manual chapter content in text format. If there is no match, return the list of optional chapters.",
)
async def read_user_manual_section(
    section_name: Annotated[str, "Chapter name or keyword, such as'Installation and deployment', 'Data source configuration', 'simulated trading', 'License', 'timing analysis', 'Stock Watchlist', '429 speed limit', 'Single container data loss'"],
) -> str:
    """Read the contents of the user manual by chapter name."""
    manual_paths = _resolve_all_manual_paths()
    if not manual_paths:
        return "❌ User manual file does not exist. Please check if there is user-manual-v3.0.md file in the docs/02-user-guide/ directory."

    keyword = (section_name or "").strip().lower()
    is_jdyun = _manual_reader_is_jdyun_mode()
    current_manual_label = "京东云版专用手册" if is_jdyun else "标准版主手册"

    # 1) List of chapter overviews for all manuals
    if not keyword:
        # Collect all manual chapters
        overview_lines = [f"📖 当前模式: {current_manual_label}", ""]
        for path, manual_type in manual_paths:
            label = "京东云版专用手册" if manual_type == "jdyun" else "标准版主手册"
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                sections = _split_sections(content)
                if not sections:
                    continue
                overview_lines.append(f"━━━ {label} ({os.path.basename(path)}) ━━━")
                for title, body, level in sections:
                    if level <= 2:  # List only first- and second-level headings
                        prefix = "  " * (level - 1) + "-"
                        overview_lines.append(f"{prefix} {title}")
                overview_lines.append("")
            except Exception as exc:
                logger.warning("[read_user_manual_section] Overview read failed %s: %s", path, exc)
        overview_lines.append("💡 Please provide specific chapter names or keywords (such as 'Installation and deployment', '429 speed limit', 'Single container data loss') ")
        return "\n".join(overview_lines)

    # 2) Keyword search: Search JD Cloud version first(if exists), Search the standard version again, merge and remove duplicates
    all_matches = []  # [(Manual type, Manual name, title, body, level)]
    primary_label = manual_paths[0][1] if manual_paths else "standard"
    seen_titles = set()  # Used to remove duplicates

    for path, manual_type in manual_paths:
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            sections = _split_sections(content)
        except Exception as exc:
            logger.warning("[read_user_manual_section] Failed to read manual %s: %s", path, exc)
            continue

        # Primary match: The title contains exactly the keyword
        primary_hits = 0
        for title, body, level in sections:
            if keyword in title.lower():
                dedup_key = f"{manual_type}:{title}"
                if dedup_key not in seen_titles:
                    seen_titles.add(dedup_key)
                    all_matches.append((manual_type, path, title, body, level))
                    primary_hits += 1

        # Fuzzy matching: only tried if there is no main matching result in the current manual (to avoid polluting the main match)
        if primary_hits == 0:
            # Option 1: Use the longest 2-word fragment of the keyword(Take the first 2-3)do"Most hits"judge
            # solve"Single container data loss"No match found"Q5: Data is lost after a single container is restarted"question
            # Both share fragments: "single container" / "data" / "lost" - 3 2-word fragments
            two_char_frags = _extract_two_char_fragments(keyword)
            if two_char_frags:
                # A match must hit at least 60% of 2-word fragments
                threshold = max(1, int(len(two_char_frags) * 0.6))
                for title, body, level in sections:
                    title_lower = title.lower()
                    hit_count = sum(1 for f in two_char_frags if f in title_lower)
                    if hit_count >= threshold:
                        dedup_key = f"{manual_type}:{title}"
                        if dedup_key not in seen_titles:
                            seen_titles.add(dedup_key)
                            all_matches.append((manual_type, path, title, body, level))

    # If the main match has no results, try splitting the match by word
    if not all_matches:
        keywords = [k for k in keyword.split() if len(k) >= 2]
        if keywords:
            for path, manual_type in manual_paths:
                try:
                    with open(path, encoding="utf-8") as f:
                        content = f.read()
                    sections = _split_sections(content)
                except Exception:
                    continue
                for title, body, level in sections:
                    if any(k in title.lower() for k in keywords):
                        dedup_key = f"{manual_type}:{title}"
                        if dedup_key not in seen_titles:
                            seen_titles.add(dedup_key)
                            all_matches.append((manual_type, path, title, body, level))

    if not all_matches:
        # Collect the first and second level titles of all manuals as an optional list
        all_titles = []
        for path, manual_type in manual_paths:
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                sections = _split_sections(content)
                label = "京东云版" if manual_type == "jdyun" else "标准版"
                for title, _, level in sections:
                    if level <= 2 and (label, title) not in all_titles:
                        all_titles.append((label, title))
            except Exception:
                continue
        titles_text = "\n".join(f"  - [{label}] {t}" for label, t in all_titles[:40])
        return f"❌ 未找到章节 '{section_name}'。\n\n📖 可选章节:\n{titles_text}"

    # 3) Splice matching results and control the total length
    parts = []
    total_len = 0
    max_len = 6000  # Truncate to prevent overlength
    matches_to_show = all_matches[:3]  # Returns up to 3 matching chapters

    for manual_type, path, title, body, level in matches_to_show:
        truncated = _truncate_to_next_level(body, level)
        prefix = "#" * level
        manual_label = "📕 京东云版" if manual_type == "jdyun" else "📘 标准版"
        section_text = f"{manual_label} | {prefix} {title}\n\n{truncated}"
        if total_len + len(section_text) > max_len:
            remaining = max_len - total_len
            if remaining > 200:
                section_text = section_text[:remaining] + "\n\n...(The content has been truncated. If you need the complete content, please provide a more precise chapter name.)"
                parts.append(section_text)
                total_len = max_len
            break
        parts.append(section_text)
        total_len += len(section_text)

    header = f"📖 用户手册搜索结果（keyword='{section_name}', 当前模式: {current_manual_label}）:\n\n"
    return header + "\n\n---\n\n".join(parts)


# ============================================================
# Vector retrieval tool: Based on semantic matching, it solves the problem that natural language problems cannot match chapters.
# ============================================================


@tool
@register_tool(
    tool_id="search_user_manual",
    name="语义搜索用户手册",
    description=(
        "Retrieve user manuals based on vector semantics and find relevant chapters in natural language."
        "When a user asks a question in natural language (e.g.'How to do analysis''How to research a stock''How to use position analysis''How to configure Token') When using this tool,"
        "It returns the top-5 semantically most relevant chapters."
        "This tool is more suitable for handling users natural language questions than read_user_manual_section."
        "It is recommended to use this tool to search first, and then use read_user_manual_section to read the complete content according to the precise chapter name."
    ),
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "manual", "vector_search", "semantic_search", "user_guide"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=[
        "怎么做分析", "怎么研究股票", "如何分析一只股票", "单股分析怎么用",
        "分析在哪", "怎么发起分析", "研究流程", "怎么用平台做分析",
        "持仓分析", "选股助手怎么用", "怎么配置 Token", "怎么加自选",
    ],
    when_to_use=(
        "This tool is used first when users use natural language to ask about system usage, functional processes, and operating steps."
        "This tool is based on vector semantic matching and can understand'How to do analysis'Wait for natural language questions and recall relevant chapters."
    ),
    returns="Returns the titles and content fragments of the Top-5 relevant chapters, sorted in descending order of similarity.",
)
async def search_user_manual(
    query: Annotated[
        str,
        "User s natural language questions such as'How to do analysis''How to research a stock''How to use position analysis''How to configure Token''429 What to do about speed limit'",
    ],
) -> str:
    """Retrieve user manuals based on vector semantics and find relevant chapters in natural language."""
    try:
        from core.knowledge.user_manual_manager import UserManualManager

        manager = UserManualManager()

        # Check if the vector library is available; try to reinitialize if not
        #  (The user may have configured the Embedding Key, reinit will re-read the configuration without restarting the backend)
        if not manager.available:
            try:
                if manager.reinit() and manager.available:
                    logger.info("[search_user_manual] Vector retrieval is reinitialized successfully and semantic retrieval continues.")
                else:
                    raise RuntimeError("reinit 失败")
            except Exception as e:
                # Graceful degradation: fallback to read_user_manual_section keyword matching
                logger.warning(
                    "[search_user_manual] Vector search is not available (%s), fallback to keyword matching."
                    "It is recommended to check the Embedding configuration (system settings -> LLM/Embedding) Or restart the backend.",
                    e,
                )
                return (
                    "⚠️ Vector retrieval is currently unavailable (Embedding or vector database is not ready) and has fallen back to keyword matching mode.\n\n"
                    "Please try calling the read_user_manual_section tool with a more precise section name,"
                    "Such as 'single stock research', 'Data source configuration', 'simulated trading' wait."
                )

        # Check if the index has been built
        count = manager.get_count()
        if count == 0:
            logger.warning("[search_user_manual] Manual index is empty, try to trigger a rebuild")
            # Trigger a rebuild synchronously (do not block for too long, or downgrade if failed)
            try:
                manager.ensure_indexed(force=False)
            except Exception as e:
                logger.error(f"[search_user_manual] Trigger rebuild failed: {e}")

            count = manager.get_count()
            if count == 0:
                return (
                    "⚠️ The user manual index has not been built yet, and vector search is not available yet.\n"
                    "You can instead use the read_user_manual_section tool to read accurately by chapter name."
                )

        # Perform semantic searches
        results = manager.search(query, top_k=5)

        if not results:
            return (
                f"❌ 未找到与 '{query}' 语义相关的手册章节。\n"
                "Try calling the read_user_manual_section tool with more specific keywords."
            )

        # Formatted output
        import os
        is_jdyun = _manual_reader_is_jdyun_mode()
        current_label = "京东云版专用手册" if is_jdyun else "标准版主手册"

        lines = [
            f"📖 用户手册语义检索结果（query='{query}', 当前模式: {current_label}）",
            f"找到 {len(results)} 个相关章节（按相似度降序）：",
            "",
        ]

        for i, r in enumerate(results, 1):
            manual_label = "📕 京东云版" if r.manual_type == "jdyun" else "📘 标准版"
            sim_pct = f"{r.similarity * 100:.0f}%"
            parent_hint = f" (Belongs to:{r.parent_title}) " if r.parent_title else ""

            # Control the length of individual results to avoid the total output being too long
            content_display = r.content
            if len(content_display) > 800:
                content_display = content_display[:800] + "\n...(The content has been truncated. If you need the complete content, please use read_user_manual_section to read by title.)"

            lines.append(f"━━━ #{i} {manual_label} | 相似度 {sim_pct} ━━━")
            lines.append(f"📌 标题: {r.title}{parent_hint}")
            lines.append("📄 内容:")
            lines.append(content_display)
            lines.append("")

        lines.append(
            "💡 If you want to view the complete content of a section, you can use the read_user_manual_section tool to read it exactly by the above title."
        )

        return "\n".join(lines)

    except ImportError:
        logger.error("[search_user_manual] UserManualManager Module not found")
        return "❌ The vector retrieval module is not installed. Please use the read_user_manual_section tool instead."
    except Exception as e:
        logger.error(f"[search_user_manual] Retrieval exception: {e}", exc_info=True)
        return f"❌ 检索失败: {e}\n请改用 read_user_manual_section 工具按章节名精确读取。"


# === paper_trading_status ===
"""Use the Q&A robot tool: Check the status of your demo trading account.

Allows using Q&A Assistant to"see"The user s current simulated trading account status, including:
- Total assets, available funds, position market value
- Realized profit and loss, floating profit and loss
- Number of stocks held, number of profitable/losing stocks
- Position details (up to 10 stocks)

Avoid robots guessing answers based on FAQs, and when encountering problems related to simulated trading, directly adjust the tool to see the real status.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _format_money(value: Optional[float]) -> str:
    """Format the amount as a Chinese readable string."""
    if value is None:
        return "未知"
    try:
        v = float(value)
        if abs(v) >= 100_000_000:
            return f"{v / 100_000_000:.2f} 亿"
        if abs(v) >= 10_000:
            return f"{v / 10_000:.2f} 万"
        return f"{v:.2f} 元"
    except Exception:
        return str(value)


def _format_pnl(value: Optional[float]) -> str:
    """Format profit and loss amount (with sign)."""
    if value is None:
        return "未知"
    try:
        v = float(value)
        sign = "+" if v >= 0 else ""
        return f"{sign}{_format_money(v)}"
    except Exception:
        return str(value)


async def _get_paper_account(db, user_id: str) -> Optional[Dict[str, Any]]:
    """Get or create a paper trading account."""
    try:
        # Compatible user_id is ObjectId or string
        from bson import ObjectId
        uid = user_id
        try:
            uid = ObjectId(user_id)
        except Exception:
            pass

        acc = await db["paper_accounts"].find_one({"user_id": uid})
        if not acc:
            # Try the string form
            acc = await db["paper_accounts"].find_one({"user_id": user_id})
        if not acc:
            # Check whether there is an initialized account
            acc = await db["paper_accounts"].find_one({"user_id": uid, "status": "active"})
        return acc
    except Exception as exc:
        logger.warning("[get_paper_trading_status] Failed to query demo account: %s", exc)
        return None


async def _get_paper_positions(db, user_id: str) -> List[Dict[str, Any]]:
    """Get the list of positions."""
    try:
        from bson import ObjectId
        uid = user_id
        try:
            uid = ObjectId(user_id)
        except Exception:
            pass

        cursor = db["paper_positions"].find({"user_id": uid})
        docs = await cursor.to_list(length=50)
        if not docs:
            docs = await db["paper_positions"].find({"user_id": user_id}).to_list(length=50)
        return docs or []
    except Exception as exc:
        logger.warning("[get_paper_trading_status] Failed to query position: %s", exc)
        return []


async def _get_latest_prices(db, codes: List[str]) -> Dict[str, Optional[float]]:
    """Get the latest prices in batches (from the market_quotes or historical_data collection)."""
    prices: Dict[str, Optional[float]] = {}
    if not codes:
        return prices
    try:
        for code in codes:
            # Take priority from the market_quotes collection
            quote = await db["market_quotes"].find_one({"code": code}, sort=[("updated_at", -1)])
            if quote and quote.get("last_price"):
                prices[code] = float(quote["last_price"])
                continue
            # Go back to historical_data and get the latest one
            hist = await db["historical_data"].find_one({"symbol": code}, sort=[("date", -1)])
            if hist and hist.get("close"):
                prices[code] = float(hist["close"])
            else:
                prices[code] = None
    except Exception as exc:
        logger.warning("[get_paper_trading_status] Failed to get latest price: %s", exc)
    return prices


@tool
@register_tool(
    tool_id="get_paper_trading_status",
    name="查询模拟交易账户状态",
    description="Query the current user s simulated trading account status: total assets, available funds, market value of positions, realized profit and loss, floating profit and loss, number of stocks held, and number of stocks with profits and losses. When the user asks'How much does a demo account cost?''What s the profit and loss today?''How much money is left''How many stocks are held?''Which one loses the most?'when used.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "paper_trading", "portfolio", "account_balance", "pnl", "positions", "virtual_trading"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=[
        "模拟账户多少钱",
        "模拟交易总资产",
        "今天盈亏多少",
        "可用资金还有多少",
        "持仓几只股票",
        "哪只股票亏得最多",
        "持仓股票盈亏情况",
        "模拟交易账户状态",
    ],
    when_to_use="It is used when the user asks about the simulated trading account balance, available funds, number of positions, and profit and loss.",
    returns="Returns a simulated trading account summary in text format, including total assets, available funds, market value of positions, profit and loss, and list of stocks held.",
)
async def get_paper_trading_status() -> str:
    """Check the status of simulated trading account."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()

    acc = await _get_paper_account(db, user_id)
    if not acc:
        return (
            "📊 Demo trading account status\n"
            "\n"
            "❌ You have not opened a demo trading account yet\n"
            "\n"
            "💡 Tip: You can go to the dashboard and click the Simulated Trading Total Assets card, or select the Simulated Trading menu in the sidebar."
            "When you enter for the first time, a virtual account will be automatically opened for you (initial capital is 1 million)."
        )

    positions = await _get_paper_positions(db, user_id)

    # Parse funds information (multi-currency format)
    cash_dict = acc.get("cash", {})
    realized_pnl_dict = acc.get("realized_pnl", {})

    # Compatible with old formats (single cash)
    if not isinstance(cash_dict, dict):
        cash_dict = {"CNY": float(cash_dict or 0)}
    if not isinstance(realized_pnl_dict, dict):
        realized_pnl_dict = {"CNY": float(realized_pnl_dict or 0)}

    # Get the latest price of the held stock
    codes = [p.get("code") for p in positions if p.get("code")]
    prices = await _get_latest_prices(db, codes)

    # Calculate the market value of positions (simplified in CNY)
    positions_value_cny = 0.0
    floating_pnl_cny = 0.0
    enriched_positions: List[Dict[str, Any]] = []

    for p in positions:
        code = p.get("code", "?")
        name = p.get("name", "") or code
        qty = int(p.get("quantity", 0) or 0)
        avg_cost = float(p.get("avg_cost", 0) or 0.0)
        last_price = prices.get(code)
        mkt_value = (last_price or 0.0) * qty
        floating = (last_price - avg_cost) * qty if last_price is not None else None

        positions_value_cny += mkt_value
        if floating is not None:
            floating_pnl_cny += floating

        enriched_positions.append({
            "code": code,
            "name": name,
            "quantity": qty,
            "avg_cost": avg_cost,
            "last_price": last_price,
            "market_value": round(mkt_value, 2),
            "floating_pnl": round(floating, 2) if floating is not None else None,
            "floating_pnl_pct": (
                round(((last_price - avg_cost) / avg_cost) * 100, 2)
                if last_price is not None and avg_cost > 0 else None
            ),
        })

    cash_cny = float(cash_dict.get("CNY", 0) or 0)
    realized_pnl_cny = float(realized_pnl_dict.get("CNY", 0) or 0)
    total_assets = cash_cny + positions_value_cny
    total_pnl = realized_pnl_cny + floating_pnl_cny

    # Profit and loss statistics of held stocks
    profit_count = sum(1 for p in enriched_positions if (p.get("floating_pnl") or 0) > 0)
    loss_count = sum(1 for p in enriched_positions if (p.get("floating_pnl") or 0) < 0)
    flat_count = sum(1 for p in enriched_positions if (p.get("floating_pnl") or 0) == 0)

    # Find the stocks with the most losses and profits
    worst_position = None
    best_position = None
    if enriched_positions:
        with_pnl = [p for p in enriched_positions if p.get("floating_pnl") is not None]
        if with_pnl:
            worst_position = min(with_pnl, key=lambda x: x["floating_pnl"])
            best_position = max(with_pnl, key=lambda x: x["floating_pnl"])

    # Formatted output
    lines = ["📊 模拟交易账户状态"]
    lines.append("")
    lines.append("【1】资产概览")
    lines.append(f"- 总资产: {_format_money(total_assets)}")
    lines.append(f"- 可用资金: {_format_money(cash_cny)}")
    lines.append(f"- 持仓市值: {_format_money(positions_value_cny)}")
    lines.append("")
    lines.append("【2】盈亏情况")
    lines.append(f"- Total profit and loss(Realized+float): {_format_pnl(total_pnl)}")
    lines.append(f"- 已实现盈亏: {_format_pnl(realized_pnl_cny)}")
    lines.append(f"- 浮动盈亏: {_format_pnl(floating_pnl_cny)}")
    lines.append("")
    lines.append("【3】持仓统计")
    lines.append(f"- 持仓股票数: {len(enriched_positions)}")
    lines.append(f"- 盈利/亏损/持平: {profit_count}/{loss_count}/{flat_count}")

    if best_position and (best_position.get("floating_pnl") or 0) > 0:
        lines.append(
            f"- 盈利最多: {best_position['name']}({best_position['code']}) "
            f"{_format_pnl(best_position['floating_pnl'])} "
            f"({best_position.get('floating_pnl_pct', 0):+}%)"
        )
    if worst_position and (worst_position.get("floating_pnl") or 0) < 0:
        lines.append(
            f"- 亏损最多: {worst_position['name']}({worst_position['code']}) "
            f"{_format_pnl(worst_position['floating_pnl'])} "
            f"({worst_position.get('floating_pnl_pct', 0):+}%)"
        )

    # Position details (up to 10 stocks)
    if enriched_positions:
        lines.append("")
        lines.append(" [4] Position details (up to 10 stocks)")
        sorted_positions = sorted(
            enriched_positions,
            key=lambda x: abs(x.get("market_value") or 0),
            reverse=True,
        )
        for p in sorted_positions[:10]:
            pnl_str = (
                f"{_format_pnl(p['floating_pnl'])} ({p.get('floating_pnl_pct', 0):+}%)"
                if p.get("floating_pnl") is not None else "无最新价"
            )
            last_price_str = f"{p['last_price']:.2f}" if p.get("last_price") is not None else "无"
            lines.append(
                f"  • {p['name']}({p['code']}) 数量 {p['quantity']} | "
                f"cost {p['avg_cost']:.2f} | latest price {last_price_str} | "
                f"Market value {_format_money(p['market_value'])} | float {pnl_str}"
            )

    # Account update time
    updated_at = acc.get("updated_at") or acc.get("created_at")
    if updated_at:
        if isinstance(updated_at, datetime):
            updated_str = updated_at.strftime("%Y-%m-%d %H:%M")
        else:
            updated_str = str(updated_at)[:19]
        lines.append("")
        lines.append(f"📌 账户最近更新: {updated_str}")

    # Comprehensive suggestions
    lines.append("")
    lines.append("💡 综合判断")
    if not enriched_positions:
        lines.append("- Currently short position, sufficient funds available. You can go to the Simulated Trading page to practice virtual operations")
    else:
        if floating_pnl_cny > 0:
            lines.append(f"- 当前持仓整体浮盈 {_format_pnl(floating_pnl_cny)}，可关注收益关注价位")
        elif floating_pnl_cny < 0:
            lines.append(f"- 当前持仓整体浮亏 {_format_pnl(floating_pnl_cny)}，可关注风险关注价位")
        else:
            lines.append("- 当前持仓整体持平")

        if cash_cny / max(total_assets, 1) < 0.1:
            lines.append("- ⚠️ Percentage of available funds < 10%, High capital utilization rate, pay attention to risks")
        elif cash_cny / max(total_assets, 1) > 0.9 and positions_value_cny > 0:
            lines.append("- Percentage of available funds > 90%, Low capital utilization rate")

    return "\n".join(lines)

# === position_analysis ===
"""
Position analysis tools

Provides the functions of viewing the position list, querying the position analysis report, and initiating the position analysis.
"""

import asyncio
import logging
from typing import Annotated, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import get_current_assistant_thread_id, require_current_user_id

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="list_positions",
    name="查看持仓列表",
    description="Lists all stock positions currently held by the user, including cost price, current price, profit and loss and other information. Supports filtering by data source (real/simulated).",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["position_analysis", "position", "list", "query", "assistant_ops", "portfolio", "holdings", "position_query", "real_position", "paper_position", "portfolio_view"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["持仓列表查看", "持仓股票查询", "实盘持仓浏览", "模拟持仓查看", "持仓盈亏查询"],
    when_to_use="It is used when the user wants to view all the stocks currently held and understand the holding cost, current price and floating profit and loss. Filtering by real offer/simulation is supported.",
    returns="Returns a text message, including the position quantity and the code, name, quantity, cost price, current price, market value and floating profit and loss of each stock.",
)
async def list_positions(
    source: Annotated[str, "Data source:all=All, real=Firm position, paper=Simulated position"] = "all",
) -> str:
    """List all current positions of the user and return the code, name, quantity, cost price, current price, floating profit and loss, etc. of each stock."""
    try:
        from app.services.portfolio_service import get_portfolio_service

        user_id = require_current_user_id()
        service = get_portfolio_service()
        positions = await service.get_positions(user_id, source=source, include_market_data=True)

        if not positions:
            source_label = {"all": "", "real": "实盘", "paper": "模拟"}.get(source, "")
            return f"当前没有{source_label}持仓记录。"

        lines = [f"共 {len(positions)} 只持仓：\n"]
        for p in positions:
            pnl_str = ""
            if p.unrealized_pnl is not None:
                sign = "+" if p.unrealized_pnl >= 0 else ""
                pct = f"{p.unrealized_pnl_pct:+.2f}%" if p.unrealized_pnl_pct is not None else ""
                pnl_str = f"  浮动盈亏: {sign}{p.unrealized_pnl:.2f} ({pct})"

            src_label = "实盘" if p.source == "real" else "模拟"
            price_str = f"现价: {p.current_price:.2f}" if p.current_price else "现价: --"
            mv_str = f"{p.market_value:.2f}" if p.market_value is not None else "--"
            lines.append(
                f"[{src_label}] {p.code} {p.name or ''} | "
                f"Quantity: {p.quantity} | cost: {p.cost_price:.2f} | {price_str} | "
                f"Market value: {mv_str}{pnl_str}"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.exception("[list_positions] Failed to obtain position list: %s", e)
        return f"获取持仓列表时出错: {e}"


@tool
@register_tool(
    tool_id="get_position_analysis",
    name="获取持仓分析报告",
    description="Get the latest AI research analysis report on a certain stock, including research observation tendencies, key verification prices, risk review points, etc.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["position_analysis", "position", "query", "report", "assistant_ops", "ai_analysis", "position_report", "action_suggestion", "price_target", "risk_assessment", "holdings_analysis"],
    tool_role_hint="primary",
    output_shape="report",
    preferred_for=["持仓分析报告查看", "研究观察查询", "关键价位确认", "持仓风险审阅"],
    when_to_use="It is used when the user wants to view the latest AI research analysis report of a certain stock, obtain research observations and risk review references.",
    returns="Returns a text report, including research observation tendency, confidence level, position summary, key verification price, risk concern price and analysis details.",
)
async def get_position_analysis(
    code: Annotated[str, "Stock code, such as 600519,00700"],
    market: Annotated[str, "Market code:CN=A shares, HK=Hong Kong stocks, US=US stocks"] = "CN",
    position_type: Annotated[str, "Position type:real=firm offer, simulated=Simulation"] = "real",
) -> str:
    """Get the latest AI analysis report on specified stock positions."""
    try:
        from app.services.portfolio_service import get_portfolio_service
        from app.services.intelligent_assistant_service import attach_report_ref_to_thread
        from app.core.database import get_mongo_db

        user_id = require_current_user_id()
        service = get_portfolio_service()
        report = await service.get_latest_position_analysis(user_id, code, market, position_type)

        if not report:
            return f"未找到 {code} 的持仓分析报告。可以先发起一次持仓分析。"

        # Build summary
        lines = []
        name = report.get("name") or code
        action = report.get("action") or "未知"
        confidence = report.get("confidence")
        status = report.get("status", "")
        created = report.get("created_at", "")

        lines.append(f"{name}({code}) 持仓分析报告")
        lines.append(f"状态: {status} | 研究观察: {action}" + (f" | 置信度: {confidence}%" if confidence else ""))

        # Position summary
        summary = report.get("summary") or {}
        if summary.get("quantity"):
            cost = summary.get("cost_price", 0)
            cur = summary.get("current_price", 0)
            pnl = summary.get("unrealized_pnl")
            pnl_pct = summary.get("unrealized_pnl_pct")
            lines.append(f"持仓: {summary['quantity']}股 | 成本: {cost:.2f} | 现价: {cur:.2f}")
            if pnl is not None:
                lines.append(f"浮动盈亏: {pnl:+.2f}" + (f" ({pnl_pct:+.2f}%)" if pnl_pct is not None else ""))

        # Key verification price
        pt = report.get("price_targets") or {}
        if pt.get("target_price") or pt.get("stop_loss"):
            tp = pt.get("target_price")
            sl = pt.get("stop_loss")
            lines.append(f"关键验证价位: {tp}" + (f" | 风险关注价格: {sl}" if sl else ""))

        # Reason for operation
        reason = report.get("action_reason")
        if reason:
            lines.append(f"\n分析详情:\n{reason}")

        if created:
            lines.append(f"\n报告时间: {created[:16] if isinstance(created, str) else created}")

        await attach_report_ref_to_thread(
            get_mongo_db(),
            user_id,
            get_current_assistant_thread_id(),
            {
                "ref_type": "position_report",
                "report_key": (report.get("analysis_id") or report.get("task_id") or f"{code}_{market}_{position_type}"),
                "source_collection": "position_analysis_reports",
                "title": f"{name}({code}) 持仓分析报告",
                "symbol": code,
                "summary": (reason or report.get("summary") or "")[:400],
                "status": status or "completed",
                "task_id": report.get("task_id"),
                "analysis_id": report.get("analysis_id"),
                "created_at": report.get("created_at"),
            },
        )

        return "\n".join(lines)
    except Exception as e:
        logger.exception("[get_position_analysis] Failed to obtain position analysis report: %s", e)
        return f"获取持仓分析报告时出错: {e}"


@tool
@register_tool(
    tool_id="trigger_position_analysis",
    name="发起持仓分析",
    description="Initiate a new AI position research and analysis task for a certain stock position, and generate research observations, key verification prices and risk reviews based on information such as position costs, profits and losses, etc. The task is executed asynchronously in the background (about 2-5 minutes) and the task ID is returned.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["position_analysis", "position", "trigger", "create", "assistant_ops", "ai_analysis", "async_task", "position_analysis_task", "action_suggestion", "deep_analysis", "holdings_analysis"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["持仓分析触发", "持仓 AI 分析发起", "研究观察生成", "持仓深度分析"],
    when_to_use="It is used when the user requests to initiate AI research analysis on a certain stock position, generate research observations and key verification prices, and the task is executed asynchronously in the background (about 2-5 minutes).",
    returns="Returns a text message containing task ID, stock code, market, position type, analysis focus and estimated completion time.",
)
async def trigger_position_analysis(
    code: Annotated[str, "Stock code, such as 600519,00700"],
    market: Annotated[str, "Market code:CN=A shares, HK=Hong Kong stocks, US=US stocks"] = "CN",
    position_type: Annotated[str, "Position type:real=firm offer, simulated=Simulation"] = "real",
    analysis_focus: Annotated[str, "Analysis focus:technical=technical aspect, fundamental=Fundamentals, comprehensive=Comprehensive"] = "comprehensive",
) -> str:
    """Initiate a new AI analysis on a certain held stock, execute it asynchronously in the background, and return the task ID."""
    try:
        from app.core.database import get_mongo_db
        from app.services.intelligent_assistant_service import attach_report_ref_to_thread
        from app.services.unified_analysis_service import get_unified_analysis_service

        user_id = require_current_user_id()
        logger.info("[trigger_position_analysis] Start creating a position analysis task: code=%s, market=%s, user_id=%s", code, market, user_id)

        unified_service = get_unified_analysis_service()

        task_params = {
            "research_depth": "标准",
            "include_add_position": True,
            "target_profit_pct": 20.0,
            "max_position_pct": 30.0,
            "max_loss_pct": 10.0,
            "risk_tolerance": "medium",
            "investment_horizon": "medium",
            "analysis_focus": analysis_focus,
            "position_type": position_type,
        }
        current_thread_id = (get_current_assistant_thread_id() or "").strip()
        if current_thread_id:
            task_params["_assistant_thread_id"] = current_thread_id

        result = await unified_service.create_position_analysis_task(
            user_id=user_id,
            code=code,
            market=market,
            task_params=task_params,
        )
        task_id = result["task_id"]
        logger.info("[trigger_position_analysis] ✅ Task has been created: task_id=%s", task_id)

        # Background execution, no blocking
        bg_task = asyncio.create_task(
            unified_service.execute_position_analysis(
                task_id=task_id,
                user_id=user_id,
                code=code,
                market=market,
                task_params=task_params,
            )
        )
        bg_task.add_done_callback(
            lambda t: logger.error("[trigger_position_analysis] ❌ Background execution exception: %s", t.exception())
            if not t.cancelled() and t.exception() else None
        )

        await attach_report_ref_to_thread(
            get_mongo_db(),
            user_id,
            get_current_assistant_thread_id(),
            {
                "ref_type": "position_task",
                "report_key": task_id,
                "source_collection": "position_analysis_reports",
                "title": f"{code} 持仓分析任务",
                "symbol": code,
                "summary": f"已发起 {code} 的持仓分析任务，等待生成正式报告。",
                "status": "running",
                "task_id": task_id,
            },
        )

        return (
            f"✅ 持仓分析任务已创建\n"
            f"- Task ID: {task_id}\n"
            f"- stocks: {code} ({market}) \n"
            f"- Position type: {'firm offer' if position_type == 'real' else 'Simulation'}\n"
            f"- Analysis focus: {analysis_focus}\n"
            f"- It is expected to take 2-5 minutes to complete. At that time, you can use Get Position Analysis Report to view the results."
        )
    except Exception as e:
        logger.exception("[trigger_position_analysis] ❌ Failed to create task: %s", e)
        return f"❌ Failed to create position analysis task: {e}"


# === recent_search ===
"""Recent information search tool."""

import logging
import os
from datetime import datetime
from typing import Annotated, Any, Optional

from langchain_core.tools import tool
from openai import OpenAI

from core.tools.base import register_tool
from tradingagents.agents.utils.agent_utils import Toolkit

logger = logging.getLogger(__name__)

DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_SEARCH_MODEL = os.getenv("DASHSCOPE_SEARCH_MODEL", "qwen3.5-plus")


def _invoke_legacy_tool(tool_func, **kwargs):
    try:
        if hasattr(tool_func, "invoke"):
            return tool_func.invoke(kwargs)
        return tool_func(**kwargs)
    except Exception as exc:
        logger.error("Failed to call recent search underlying tool %s: %s", tool_func, exc)
        return f"近期信息搜索失败: {str(exc)}"


def _resolve_dashscope_runtime_config() -> tuple[Optional[str], str, str]:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL", DEFAULT_DASHSCOPE_BASE_URL)
    model = DEFAULT_SEARCH_MODEL

    if api_key:
        return api_key, base_url, model

    try:
        from pymongo import MongoClient
        from app.core.config import settings

        client = MongoClient(settings.MONGO_URI)
        db = client[settings.MONGO_DB]
        provider_doc = db.llm_providers.find_one({"name": "dashscope"}) or {}
        client.close()

        api_key = provider_doc.get("api_key") or api_key
        base_url = provider_doc.get("default_base_url") or base_url
    except Exception as exc:
        logger.warning("Failed to read DashScope configuration, fallback environment variables: %s", exc)

    return api_key, base_url, model


def _extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text).strip()

    pieces: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                pieces.append(str(text).strip())
    return "\n\n".join(piece for piece in pieces if piece).strip()


def _search_with_qwen(query: str, curr_date: str) -> str:
    api_key, base_url, model = _resolve_dashscope_runtime_config()
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not configured and not found in llm_providers DashScope API Key")

    client = OpenAI(api_key=api_key, base_url=base_url)
    prompt = (
        f"Please search online and confirm recent public information on the following issues:{query}. "
        f"The current date is {curr_date}. "
        "Priority will be given to using the information of the last 30 days; if not, it will fall back to the last 90 days."
        "Please give priority to citing exchange announcements, company announcements, and authoritative financial media."
        "Do not rely on common sense to add historical context and do not infer conclusions that are not directly supported by recent sources."
        "Don t use very likely  High probability This type of vague wording pretends to be a definite conclusion."
        "If the evidence is insufficient to fully confirm, don t just answer Unable to confirm It ends; you should continue to list recent media reports or market information that you can refer to, and indicate that they are not final confirmation."
        "Do not output a timeline table unless there is a recent, verifiable source for each time point."
        "Please output strictly in the following format:"
        " [The latest conclusion] First give the most reliable conclusion that can be confirmed at present. If you are not completely sure, please write clearly Unable to fully confirm at present , However, reference information still needs to be added."
        " [Corroborating basis] List 2-4 corroborating sources, each containing: Date | Source | Title | Information that can be directly confirmed. If not, just write No direct source of confirmation . "
        " [Reference reports] List 2-5 reference sources, such as Caixin, Securities Times, Reuters, Bloomberg, and mainstream financial media reports; each item includes: date | Source | Title | Reporting caliber. and clearly state at the beginning of this paragraph The following is a reference report and may not necessarily be equivalent to final official confirmation. . "
        " [Uncertain points] Clearly write down what evidence is missing, for example Lacking the latest equity disclosure from the Hong Kong Stock Exchange . If not, write None . "
        "If the media clearly reports Cleared  Has dropped below 5%  no longer disclosed , These contents should be entered into [Reference Reports] or [Latest Conclusions], but it must be distinguished whether they are media reports or official confirmations."
    )

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    }
                ],
            }
        ],
        text={"format": {"type": "text"}},
        reasoning={},
        tools=[
            {
                "type": "web_search_preview",
                "user_location": {"type": "approximate"},
                "search_context_size": "medium",
            }
        ],
        temperature=0.2,
        max_output_tokens=2048,
        top_p=0.9,
        store=False,
    )

    text = _extract_response_text(response)
    if not text:
        raise RuntimeError("百炼搜索返回为空")
    return text


def run_recent_information_search(query: str) -> str:
    """Search recent public information, giving priority to fact-confirmation questions.

    Search source priority:
    1. SearXNG Local instance (fast, about 1-2 seconds; enabled when SEARXNG_INSTANCES is configured)
    2. DashScope Internet search (qwen + web_search_preview, Slower, may timeout)
    3. Google News (full details)
    """
    query_clean = (query or "").strip()
    if not query_clean:
        return "Please provide the keywords to be searched, for example: BYD, Berkshire, shareholding reduction, shareholding ratio."

    curr_date = datetime.now().strftime("%Y-%m-%d")

    # 1) SearXNG Local search (priority, return within seconds)
    try:
        
        searx_result = run_web_search(query_clean, max_results=10)
        if searx_result and not searx_result.startswith("Web 搜索失败"):
            return (
                f"以下是“{query_clean}”的近期联网搜索结果（搜索引擎聚合，按相关性排序）。"
                "Please give priority to answers based on entries with the latest release date and more authoritative sources, and be sure to check the release date.\n\n"
                f"{searx_result}"
            )
        logger.warning("SearXNG No results found in search, return DashScope: %s", query_clean)
    except Exception as exc:
        logger.warning("SearXNG Search failed, fallback DashScope: %s", exc)

    # 2) DashScope Internet search (optional)
    try:
        result = _search_with_qwen(query_clean, curr_date)
        return (
            f"以下是“{query_clean}”的近期联网搜索结果。请优先依据发布时间最新、来源更权威的条目回答。\n\n"
            f"{result}"
        )
    except Exception as exc:
        logger.warning("Bailian s recent search failed and returned Google News: %s", exc)

    # 3) Google News (full details)
    result = _invoke_legacy_tool(Toolkit.get_google_news, query=query_clean, curr_date=curr_date)
    if not result or str(result).startswith("近期信息搜索失败"):
        return f"Recent information search failed:{result}"

    return (
        f"Bailian search is temporarily unavailable, and the following will fall back to recent Google News search results. Please give priority to answers based on items with the latest release date and more authoritative sources.\n\n"
        f"{result}"
    )


@tool
@register_tool(
    tool_id="search_recent_information",
    name="近期信息搜索",
    description="Search public news and recent information within the last 7 days. suitable answer Up to now  Latest  Are there any recent changes?  Need to confirm the latest shareholding ratio/announcement/news These kind of questions. The input should contain a company name, event keyword, or stock symbol.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    data_source_handling="local_only",
    capability_tags=["information_search", "recent_news", "web_search", "assistant_ops", "fact_check", "news_query", "current_events", "online_search", "market_information", "real_time_info"],
    tool_role_hint="specialized",
    output_shape="report",
    preferred_for=["搜索近期公开新闻", "确认最新事实信息", "查询近期公告或事件", "核实最新持股或市场动态"],
    when_to_use="When users ask Up to now  Latest  Are there any recent changes? Or use it when you need to confirm the latest shareholding ratio, announcements, market news, etc.",
    when_not_to_use="It is not suitable for checking the stock price trend of individual stocks, the rise and fall of the market, whether it rebounds/callbacks/breakthroughs and other price trend judgments.——For this type of problem, you must call market data tools (get_stock_market_data_unified / get_technical_indicators / real-time market conditions) to obtain real K-line data. Web search results cannot provide stock price trends; they are not suitable for querying historical price data.",
    returns="Returns search results in text format, including the latest conclusions, corroborating evidence, reference reports and uncertainties.",
)
def search_recent_information(
    query: Annotated[str, "Search keywords, for example: BYD, Berkshire, shareholding reduction, or CATL s latest announcement"],
) -> str:
    """Search recent public information for the latest fact-confirming questions."""
    return run_recent_information_search(query)

# === report_query ===
"""
Report query tools

Provides functions for searching analysis reports, viewing details, and obtaining the latest reports.
The query scope is limited to the current user s reports.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import get_current_assistant_thread_id, require_current_user_id

logger = logging.getLogger(__name__)

# ── Date range shortcut ──
_DATE_SHORTCUTS = {
    "today": 0,
    "yesterday": 1,
    "last_week": 7,
    "last_month": 30,
    "last_quarter": 90,
}


def _resolve_date_range(date_range: Optional[str]):
    """Convert natural language date range to (start, end) datetime. """
    if not date_range:
        return None, None
    key = date_range.strip().lower().replace(" ", "_")
    days = _DATE_SHORTCUTS.get(key)
    if days is not None:
        end = datetime.now()
        start = end - timedelta(days=days)
        return start, end
    # try to parse YYYY-MM-DD ~ YYYY-MM-DD
    if "~" in date_range:
        parts = date_range.split("~")
        try:
            return datetime.strptime(parts[0].strip(), "%Y-%m-%d"), datetime.strptime(parts[1].strip(), "%Y-%m-%d")
        except ValueError:
            pass
    return None, None


@tool
@register_tool(
    tool_id="search_reports",
    name="搜索分析报告",
    description="Search the user s existing historical analysis reports in the database, and support filtering by stock code, keywords, and date range. Returns a list of report summaries (title, stock, date, conclusion) without full text.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["report_query", "analysis_report", "search", "query", "assistant_ops", "report_search", "report_history", "report_filtering", "stock_report"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["report_search", "report_history_query", "analysis_report_filtering", "stock_report_lookup", "report_summary_viewing"],
    returns="Returns a list of report summaries in text format, containing task ID, ticker, date, and conclusion summary.",
    when_to_use="Used when users want to search, find or filter historical analysis reports, supporting filtering by stock code, keywords or date range.",
)
async def search_reports(
    symbol: Annotated[Optional[str], "Stock code screening, such as 600519"] = None,
    keyword: Annotated[Optional[str], "Search keywords to match report content"] = None,
    date_range: Annotated[Optional[str], "date range: today / last_week / last_month or YYYY-MM-DD~YYYY-MM-DD"] = None,
    limit: Annotated[int, "Returns the upper limit of quantity, default 5"] = 5,
) -> str:
    """Searching the list of analysis reports returns a condensed summary (title, stock, date, conclusion) without full content."""
    try:
        from bson import ObjectId
        from app.core.database import get_mongo_db

        user_id = require_current_user_id()
        db = get_mongo_db()

        query = {"user_id": ObjectId(user_id), "status": "completed"}

        if symbol:
            query["task_params.symbol"] = symbol
        if keyword:
            query["$or"] = [
                {"task_params.symbol": {"$regex": keyword, "$options": "i"}},
                {"result.recommendation": {"$regex": keyword, "$options": "i"}},
                {"result.summary": {"$regex": keyword, "$options": "i"}},
            ]
        start, end = _resolve_date_range(date_range)
        if start or end:
            date_q = {}
            if start:
                date_q["$gte"] = start
            if end:
                date_q["$lte"] = end
            query["created_at"] = date_q

        cursor = db.unified_analysis_tasks.find(
            query,
            {"task_id": 1, "task_type": 1, "task_params": 1, "created_at": 1, "result.recommendation": 1, "result.summary": 1, "execution_time": 1},
        ).sort("created_at", -1).limit(limit)

        results = []
        async for doc in cursor:
            sym = doc.get("task_params", {}).get("symbol", "N/A")
            created = doc.get("created_at")
            date_str = created.strftime("%Y-%m-%d %H:%M") if hasattr(created, "strftime") else (str(created)[:16] if created else "未知")
            rec = (doc.get("result") or {}).get("recommendation", "")
            summary = (doc.get("result") or {}).get("summary", "")
            brief = (rec or summary or "无摘要")[:120]
            results.append(f"  [{doc['task_id'][:8]}] {sym} | {date_str} | {brief}")

        if not results:
            return "No matching analysis reports were found."
        return f"📊 找到 {len(results)} 条报告：\n" + "\n".join(results) + "\n\n💡 Use View Report Details to get the complete content."
    except Exception as e:
        logger.exception("[search_reports] Query report failed: %s", e)
        return f"查询报告时出错: {str(e)}"


@tool
@register_tool(
    tool_id="get_report_detail",
    name="查看报告详情",
    description="Get the analysis report content based on the task ID. Two modes are supported:1) If module_key is not passed, the top-level summary (research conclusion tendency, key points, summary) will be returned;2) Passing module_key returns the complete text content of the specified submodule (such as market_report/fundamentals_report/news_report/sentiment_report/trader_investment_plan/research_team_decision/risk_management_decision/final_trade_decision, etc.). It is recommended to obtain specified modules on demand based on user issues to avoid pulling too much content at once.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["report_query", "analysis_report", "detail", "query", "assistant_ops", "report_detail", "report_content", "full_report", "markdown_report", "report_module"],
    tool_role_hint="primary",
    output_shape="report",
    preferred_for=["report_detail_viewing", "full_report_reading", "report_content_retrieval", "analysis_report_detail", "report_module_reading"],
    returns="Returns a formatted Markdown report. If module_key is not passed, the top-level summary is returned; if module_key is passed, the complete text of the specified module is returned.",
    when_to_use="Used when the user wants to view the content of the analysis report. Simple questions (such as overall conclusions) do not pass module_key; specific dimensional questions (such as technical aspects/fundamentals/news) pass the corresponding module_key to obtain the complete content.",
)
async def get_report_detail(
    task_id: Annotated[str, "分析任务ID"],
    module_key: Annotated[Optional[str], "Specify the submodule key to obtain the complete text. Optional values:market_report(Market technical analysis)/fundamentals_report(fundamental research)/news_report(Journalism Research)/sentiment_report(sentiment analysis)/trader_investment_plan(Research and integrate opinions)/research_team_decision(Research team conclusion)/risk_management_decision(Risk review conclusion)/final_trade_decision(Comprehensive research conclusion)/index_report(Market environment)/sector_report(Industry sector). If not passed, the top-level summary will be returned."] = None,
) -> str:
    """Get the report content of the specified analysis task. Passing module_key returns the complete text of the module, otherwise it returns the top-level summary."""
    try:
        from app.core.database import get_mongo_db
        from app.services.task_analysis_service import get_task_analysis_service
        from app.services.intelligent_assistant_service import attach_report_ref_to_thread

        user_id = require_current_user_id()
        service = get_task_analysis_service()
        task = await service.get_task(task_id)
        if not task:
            return f"❌ 未找到任务: {task_id}"
        if task.status != "completed":
            return f"⏳ The task has not yet been completed (current status: {task.status}, Progress: {task.progress}%) "
        if not task.result:
            return "⚠️ The task was completed but no report data was generated."

        r = task.result
        sym = task.task_params.get("symbol", "未知")

        # ── Module mode: Return the complete text of the specified submodule ──
        if module_key:
            module_key_clean = module_key.strip()
            reports_dict = r.get("reports") or {}
            if not isinstance(reports_dict, dict) or not reports_dict:
                return f"⚠️ 任务 {task_id} 的报告中未找到任何子模块数据。"
            content = reports_dict.get(module_key_clean)
            if not content or (isinstance(content, str) and not content.strip()):
                available = ", ".join(reports_dict.keys())
                return (
                    f"⚠️ 未找到模块 `{module_key_clean}`。\n"
                    f"The report contains the following modules available:{available}\n"
                    f"Please choose one of the above modules to call again."
                )
            label = _ANALYST_LABELS.get(module_key_clean, module_key_clean)
            # Compatible when content is a dictionary (for example, final_trade_decision may be structured data)
            if isinstance(content, dict):
                content_text = content.get("content") or content.get("report") or content.get("text") or content.get("markdown") or ""
                if not content_text:
                    content_text = json.dumps(content, ensure_ascii=False, indent=2)
            else:
                content_text = str(content)
            return f"# {label}\n\n{content_text}"

        # ── Top-level summary mode: Returns the overall summary of the report ──
        lines = [f"# 📈 {sym} 分析报告"]
        if r.get("recommendation"):
            lines.append(f"\n## 研究结论倾向\n{r['recommendation']}")
        if r.get("confidence_score"):
            lines.append(f"\n**置信度**: {r['confidence_score']}")
        if r.get("risk_level"):
            lines.append(f"**风险等级**: {r['risk_level']}")
        if r.get("key_points"):
            kps = r["key_points"] if isinstance(r["key_points"], list) else [r["key_points"]]
            lines.append("\n## 关键要点\n" + "\n".join(f"- {kp}" for kp in kps))
        if r.get("summary"):
            lines.append(f"\n## 摘要\n{r['summary']}")

        # Lists available submodules, directing LLM to get full content on demand
        reports_dict = r.get("reports") or {}
        if isinstance(reports_dict, dict) and reports_dict:
            available_lines = []
            for k in reports_dict.keys():
                label = _ANALYST_LABELS.get(k, k)
                available_lines.append(f"  • {k}（{label}）")
            lines.append("\n## 可用子模块")
            lines.append("To view the complete content of a module, call this tool again and pass in the module_key parameter:")
            lines.extend(available_lines)

        db = get_mongo_db()
        await attach_report_ref_to_thread(
            db,
            user_id,
            get_current_assistant_thread_id(),
            {
                "ref_type": "stock_report",
                "report_key": task.task_id,
                "source_collection": "unified_analysis_tasks",
                "title": f"{sym} 分析报告",
                "symbol": sym,
                "summary": (r.get("summary") or r.get("recommendation") or "")[:400],
                "status": task.status,
                "task_id": task.task_id,
                "created_at": getattr(task, "created_at", None),
            },
        )

        lines.append(f"\n---\n_任务ID: {task.task_id} | 耗时: {task.execution_time:.1f}s_")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("[get_report_detail] Failed to get report details: %s", e)
        return f"获取报告详情时出错: {str(e)}"



# ── Chinese labels for each analyst role ──
# Covers all submodules that may appear in the reports dictionary of single stock analysis reports
_ANALYST_LABELS = {
    # core decision-making
    "final_trade_decision":   "综合研究结论",
    "research_team_decision": "研究团队结论",
    "risk_management_decision": "风险审阅结论",
    "trader_investment_plan": "研究整合意见",
    "investment_plan":        "投资计划",
    # Researcher Debate Class
    "bull_researcher":        "乐观情景论证",
    "bear_researcher":        "审慎情景论证",
    "neutral_analyst":        "基准情景评估",
    "risky_analyst":          "高弹性情景评估",
    "safe_analyst":           "防御情景评估",
    # Individual stock analysis module
    "fundamentals_report":    "基本面研究",
    "market_report":          "市场技术分析",
    "news_report":            "新闻研究",
    "sentiment_report":       "情绪分析",
    "chip_report":            "筹码分布分析",
    # Macro analysis module
    "index_report":           "大盘环境研究",
    "sector_report":          "行业板块研究",
    # Position analysis module (some reports may be reused)
    "company_overview":       "公司概况",
    "financial_analysis":     "财务分析",
    "technical_analysis":     "技术分析",
    "market_analysis":        "市场分析",
    "risk_analysis":          "风险分析",
    "valuation_analysis":     "估值分析",
    "investment_recommendation": "研究结论摘要",
}
# Sort by importance and prioritize core decisions
_REPORT_PRIORITY = [
    "final_trade_decision",
    "research_team_decision",
    "risk_management_decision",
    "bull_researcher",
    "bear_researcher",
    "fundamentals_report",
    "market_report",
    "news_report",
    "sentiment_report",
    "investment_plan",
    "trader_investment_plan",
]
_MAX_TOTAL_CHARS = 6000   # Tool returns cap, controls LLM context
_EXCERPT_CHARS = 500      # Word count of excerpts per analyst report


@tool
@register_tool(
    tool_id="get_latest_report",
    name="获取最新报告",
    description="Read the summary of the latest completed analysis report for the specified stock (core conclusions of each analyst)+final research conclusion). No new tasks will be created. When symbol is empty, the user s most recent report is returned.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["report_query", "analysis_report", "latest", "query", "assistant_ops", "latest_report", "recent_report", "stock_report", "analyst_summary"],
    tool_role_hint="primary",
    output_shape="report",
    preferred_for=["latest_report_viewing", "recent_report_query", "stock_analysis_summary", "analyst_report_summary"],
    returns="Returns a formatted text report containing investment views, price range, decision rationale, key takeaways and individual analyst excerpts.",
    when_to_use="Used when the user wants to quickly view a summary of the latest completed analysis report for a certain stock. No new task will be created.",
)
async def get_latest_report(
    symbol: Annotated[str, "Stock code, such as 600519. If the user does not specify an empty string, the latest report for any stock will be returned."],
) -> str:
    """Read the summary of the latest completed analysis report for a certain stock without creating a new task. When symbol is empty, the user s latest report is returned."""
    try:
        from bson import ObjectId
        from app.core.database import get_mongo_db
        from app.services.intelligent_assistant_service import attach_report_ref_to_thread

        user_id = require_current_user_id()
        db = get_mongo_db()

        # ── Construct query: No limit on stock code when symbol is empty ──
        query: dict = {"user_id": ObjectId(user_id), "status": "completed"}
        sym_clean = (symbol or "").strip()
        if sym_clean:
            query["task_params.symbol"] = sym_clean

        doc = await db.unified_analysis_tasks.find_one(query, sort=[("created_at", -1)])
        if not doc:
            hint = f"{sym_clean} 的" if sym_clean else "任何"
            return (
                f"未找到{hint}分析报告。"
                f"{'You can use Trigger Stock Analysis to initiate analysis.' if sym_clean else 'Please trigger a stock analysis first.'}"
            )

        r = doc.get("result") or {}
        actual_symbol = doc.get("task_params", {}).get("symbol", sym_clean or "未知")
        created = doc.get("created_at")
        date_str = created.strftime("%Y-%m-%d %H:%M") if hasattr(created, "strftime") else (str(created)[:16] if created else "未知")
        task_id = doc.get("task_id", "")

        # ── Part One: Structured Summary (required) ──
        lines: list[str] = [f"📈 {actual_symbol} 分析报告（{date_str}）"]

        decision = r.get("decision") or {}
        action = decision.get("action") or decision.get("analysis_view", "")
        confidence = decision.get("confidence")
        risk_score = decision.get("risk_score")
        price_range = decision.get("price_analysis_range")
        reasoning = (decision.get("reasoning") or "")[:400]

        if action:
            conf_str = f"  置信度: {confidence:.0%}" if confidence is not None else ""
            risk_str = f"  风险分: {risk_score:.0%}" if risk_score is not None else ""
            lines.append(f"\n【投资观点】{action}{conf_str}{risk_str}")
        if price_range and isinstance(price_range, (list, tuple)) and len(price_range) == 2:
            lines.append(f"【价格区间参考】{price_range[0]} ~ {price_range[1]}")
        if reasoning:
            lines.append(f"【决策依据】\n{reasoning}")

        rec = (r.get("recommendation") or "")[:300]
        if rec and rec != action:
            lines.append(f"\n【建议摘要】\n{rec}")

        risk_level = r.get("risk_level", "")
        if risk_level:
            lines.append(f"【风险等级】{risk_level}")

        key_points = r.get("key_points") or []
        if key_points:
            kp_text = "\n".join(f"  • {kp}" for kp in key_points[:5])
            lines.append(f"\n【关键要点】\n{kp_text}")

        summary = (r.get("summary") or "")[:400]
        if summary:
            lines.append(f"\n【综合摘要】\n{summary}")

        await attach_report_ref_to_thread(
            db,
            user_id,
            get_current_assistant_thread_id(),
            {
                "ref_type": "stock_report",
                "report_key": task_id,
                "source_collection": "unified_analysis_tasks",
                "title": f"{actual_symbol} 分析报告",
                "symbol": actual_symbol,
                "summary": (summary or rec or reasoning or "")[:400],
                "status": doc.get("status") or "completed",
                "task_id": task_id,
                "created_at": created,
            },
        )

        # ── Part 2: Excerpts by analysts (by priority, subject to total word limit) ──
        reports: dict = r.get("reports") or {}
        if reports:
            lines.append("\n─── Excerpts from various analysts ───")
            current_len = sum(len(l) for l in lines)
            for key in _REPORT_PRIORITY:
                if current_len >= _MAX_TOTAL_CHARS:
                    lines.append(" (More content has been omitted, you can use View Report Details to get the full version)")
                    break
                text = reports.get(key)
                if not text or not isinstance(text, str) or len(text.strip()) < 20:
                    continue
                label = _ANALYST_LABELS.get(key, key)
                excerpt = text.strip()[:_EXCERPT_CHARS]
                if len(text.strip()) > _EXCERPT_CHARS:
                    excerpt += "…"
                snippet = f"\n[{label}]\n{excerpt}"
                lines.append(snippet)
                current_len += len(snippet)

        lines.append(f"\n─\n Task ID: {task_id[:12]}…")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("[get_latest_report] Failed to get latest report: %s", e)
        return f"获取最新报告时出错: {str(e)}"


@tool
@register_tool(
    tool_id="search_attachable_reports",
    name="搜索可关联旧报告",
    description="Search for old reports under the current topic that can be manually linked. Suitable for users to say Before linking old CATL reports to the current topic, first check what old reports are available. . ",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["report_query", "analysis_report", "search", "attachable", "assistant_ops", "report_attachment", "topic_report_linking", "report_search"],
    tool_role_hint="specialized",
    output_shape="text",
    preferred_for=["attachable_report_search", "report_attachment_query", "topic_report_linking_prep"],
    returns="Returns a text list containing the title, ticker, creation time, and report ID of the old report that can be associated.",
    when_to_use="This is used when the user wants to see what optional reports are available before linking an old report on a certain stock to the current topic.",
)
async def search_attachable_reports(
    keyword: Annotated[Optional[str], "Stock code, company name or report keywords, such as CATL/BYD / 300750"] = None,
    report_type: Annotated[str, "Report type: stock_report single stock report; position_report position report"] = "stock_report",
    limit: Annotated[int, "Returns the upper limit of quantity, default 5"] = 5,
) -> str:
    """Searches for old reports that can be associated with the current topic."""
    try:
        from app.core.database import get_mongo_db
        from app.services.intelligent_assistant_service import search_assistant_attachable_reports

        user_id = require_current_user_id()
        thread_id = get_current_assistant_thread_id()
        if not thread_id:
            return "There is currently no selected research topic to search for related reports."

        db = get_mongo_db()
        items = await search_assistant_attachable_reports(
            db,
            user_id,
            thread_id,
            ref_type=(report_type or "stock_report").strip() or "stock_report",
            keyword=(keyword or "").strip() or None,
            limit=max(1, min(limit, 10)),
        )
        if not items:
            target = (keyword or "历史报告").strip() or "历史报告"
            return f"未找到与“{target}”匹配的可关联旧报告。"

        lines = [f"找到 {len(items)} 条可关联旧报告："]
        for item in items:
            title = item.get("title") or "未命名报告"
            symbol = item.get("symbol") or ""
            created_at = item.get("created_at")
            if hasattr(created_at, "strftime"):
                created_text = created_at.strftime("%Y-%m-%d %H:%M")
            else:
                created_text = str(created_at)[:16] if created_at else "未知时间"
            report_key = item.get("report_key") or ""
            lines.append(f"- {title} | {symbol} | {created_text} | key={report_key}")
        lines.append("If you want to link directly to the current topic, you can continue to say: Link this old report to the current topic.")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("[search_attachable_reports] Search for relatable old reports failed: %s", e)
        return f"搜索可关联旧报告时出错: {str(e)}"


@tool
@register_tool(
    tool_id="attach_existing_report_to_current_topic",
    name="关联旧报告到当前主题",
    description="Directly link old reports that have been generated by the user to the current research topic. Suitable for users to say Relate old CATL reports to current topics . The latest matching copy is associated by default.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["report_query", "analysis_report", "attach", "link", "assistant_ops", "report_attachment", "topic_report_linking", "report_binding"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["report_attachment", "topic_report_linking", "historical_report_binding", "report_to_topic_association"],
    returns="Returns a text message containing correlation results and report identification.",
    when_to_use="It is used when the user requests to directly link the historical reports of a certain stock to the current research topic.",
)
async def attach_existing_report_to_current_topic(
    keyword: Annotated[str, "Stock code, company name or report keywords, such as CATL/BYD / 300750"],
    report_type: Annotated[str, "Report type: stock_report single stock report; position_report position report"] = "stock_report",
) -> str:
    """Hang the latest matching old reports to the current topic based on keywords."""
    try:
        from app.core.database import get_mongo_db
        from app.services.intelligent_assistant_service import (
            attach_existing_report_to_thread,
            search_assistant_attachable_reports,
        )

        user_id = require_current_user_id()
        thread_id = get_current_assistant_thread_id()
        if not thread_id:
            return "There is currently no research topic selected and old reports cannot be associated."

        keyword_clean = (keyword or "").strip()
        if not keyword_clean:
            return "Please provide stock code, company name or report keywords, for example: CATL, BYD, 300750."

        db = get_mongo_db()
        matches = await search_assistant_attachable_reports(
            db,
            user_id,
            thread_id,
            ref_type=(report_type or "stock_report").strip() or "stock_report",
            keyword=keyword_clean,
            limit=3,
        )
        if not matches:
            return f"未找到与“{keyword_clean}”匹配的旧报告，暂时无法关联。"

        target = matches[0]
        attached_ref = await attach_existing_report_to_thread(
            db,
            user_id,
            thread_id,
            target.get("ref_type") or report_type,
            target.get("report_key") or "",
        )
        if not attached_ref:
            return f"找到了“{keyword_clean}”的旧报告，但关联失败。"

        title = attached_ref.get("title") or keyword_clean
        report_key = attached_ref.get("report_key") or ""
        extra = ""
        if len(matches) > 1:
            extra = f"\n另外还找到 {len(matches) - 1} 条相近历史报告，如需可继续指定日期或让我继续关联。"
        return f"已将旧报告《{title}》关联到当前主题。\n报告标识: {report_key}{extra}"
    except Exception as e:
        logger.exception("[attach_existing_report_to_current_topic] Failed to associate old reports: %s", e)
        return f"关联旧报告时出错: {str(e)}"

# === risk_alerts ===
"""
Risk reminder tools

Provides the ability to set, view, and clear price lower limit reminders to facilitate users to track risks by themselves.
"""

import logging
from typing import Annotated, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _risk_alerts_normalize_market(market: str) -> str:
    m = (market or "CN").upper()
    if m in ("CN", "A股", "SH", "SZ"):
        return "A股"
    if m in ("HK", "港股"):
        return "港股"
    if m in ("US", "美股"):
        return "美股"
    return "A股"


@tool
@register_tool(
    tool_id="set_stop_loss_alert",
    name="设置价格下限提醒",
    description="Set a lower price limit reminder for a stock, and push notifications through the system when the price is close to or falls below, making it easier for users to track risks on their own. Returns the stock name, symbol, market and alert price.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["risk_alerts", "stop_loss", "alert", "set", "assistant_ops", "price_alert", "risk_management", "notification", "alert_setup", "price_threshold", "loss_prevention"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["价格下限提醒设置", "风险关注价格配置", "风险控制提醒", "价格下限提醒"],
    when_to_use="It is used when users want to set a lower price limit for a certain stock and want to be notified when the price falls below the threshold so that they can pay attention to the risk themselves.",
    returns="Returns a text message containing the stock name, symbol, market, and the price floor that has been set.",
)
async def set_stop_loss_alert(
    symbol: Annotated[str, "Stock code, such as 300033, 00700,AAPL"],
    stop_loss_price: Annotated[float, "Price lower limit (alert when it is below or close to this price)"],
    market: Annotated[str, "Market: CN/HK/US, default CN"] = "CN",
) -> str:
    """Set a stock price floor reminder."""
    try:
        from app.services.favorites_service import favorites_service
        from app.core.database import get_mongo_db

        user_id = require_current_user_id()
        market_label = _risk_alerts_normalize_market(market)
        db = get_mongo_db()

        # Try to complete the stock name from the position
        name = symbol
        pos = await db.real_positions.find_one({"user_id": user_id, "code": symbol}, {"name": 1})
        if pos and pos.get("name"):
            name = pos["name"]

        # If it does not exist, it will automatically be added to the stock watch list, and then the reminder threshold will be written.
        exists = await favorites_service.is_favorite(user_id, symbol)
        if not exists:
            await favorites_service.add_favorite(
                user_id=user_id,
                stock_code=symbol,
                stock_name=name,
                market=market_label,
                alert_price_low=stop_loss_price,
            )
        else:
            await favorites_service.update_favorite(
                user_id=user_id,
                stock_code=symbol,
                alert_price_low=stop_loss_price,
            )

        return (
            f"✅ 已设置价格下限提醒\n"
            f"- stocks: {name}({symbol})\n"
            f"- market: {market_label}\n"
            f"- price floor: {stop_loss_price:.2f}\n"
            f"When the price approaches or falls below the lower limit, you will receive a system notification so that you can pay attention to the risk yourself."
        )
    except Exception as e:
        logger.exception("[set_stop_loss_alert] Failed to set price minimum reminder: %s", e)
        return f"设置价格下限提醒失败: {e}"


@tool
@register_tool(
    tool_id="list_stop_loss_alerts",
    name="查看价格下限提醒",
    description="View all price floor alerts currently set. Returns the number of alerts and the stock name, symbol, market, and alert price for each alert.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["risk_alerts", "stop_loss", "alert", "list", "query", "assistant_ops", "price_alert", "risk_management", "alert_query", "notification_list"],
    tool_role_hint="supporting",
    output_shape="text",
    preferred_for=["价格下限提醒查看", "价格下限列表查询", "已配置提醒浏览", "风险控制确认"],
    when_to_use="This is used when the user wants to view all currently set price lower limit reminders and confirm which stocks have configured price lower limits.",
    returns="Returns a text message, including the number of price lower limit reminders and the stock, market, and reminder price of each reminder.",
)
async def list_stop_loss_alerts() -> str:
    """View a list of configured price floor alerts."""
    try:
        from app.services.favorites_service import favorites_service

        user_id = require_current_user_id()
        items = await favorites_service.get_user_favorites(user_id)
        alerts = [x for x in items if x.get("alert_price_low") is not None]

        if not alerts:
            return "There are currently no price floor alerts set."

        lines = [f"共 {len(alerts)} 条价格下限提醒：\n"]
        for it in alerts:
            code = it.get("stock_code", "")
            name = it.get("stock_name", code)
            market = it.get("market", "A股")
            low = it.get("alert_price_low")
            lines.append(f"- {name}({code}) | {market} | 价格下限: {float(low):.2f}")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("[list_stop_loss_alerts] Failed to check price lower limit reminder: %s", e)
        return f"查看价格下限提醒失败: {e}"


@tool
@register_tool(
    tool_id="clear_stop_loss_alert",
    name="清除价格下限提醒",
    description="Clear the lower price limit reminder for the specified stock (only clears the reminder, does not remove the stock watch list). Returns the operation result or a prompt that the configuration is not found.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["risk_alerts", "stop_loss", "alert", "clear", "delete", "assistant_ops", "price_alert", "risk_management", "alert_removal", "notification_cleanup"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["价格下限提醒清除", "风险关注价格移除", "提醒配置删除", "风险提醒取消"],
    when_to_use="It is used when the user wants to clear the price lower limit reminder of a certain stock and no longer receive the price lower limit notification of the stock (only clears the reminder and does not remove the stock watch list).",
    returns="Return a text message to confirm that the price lower limit reminder has been cleared or that the relevant configuration is not found.",
)
async def clear_stop_loss_alert(
    symbol: Annotated[str, "Stock code, such as 300033, 00700,AAPL"],
) -> str:
    """Clear the price floor alert for a stock."""
    try:
        from app.services.favorites_service import favorites_service

        user_id = require_current_user_id()
        ok = await favorites_service.update_favorite(
            user_id=user_id,
            stock_code=symbol,
            clear_alert_price_low=True,
        )
        if ok:
            return f"✅ 已清除 {symbol} 的价格下限提醒。"
        return f"未找到 {symbol} 的价格下限提醒配置，或该股票不在股票关注列表中。"
    except Exception as e:
        logger.exception("[clear_stop_loss_alert] Failed to clear price floor reminder: %s", e)
        return f"清除价格下限提醒失败: {e}"

# === running_tasks ===
"""Use the Q&A bot tool: Query running and queued tasks.

Allows using Q&A Assistant to"see"Tasks currently running and queued include:
- Running tasks, current steps, progress, elapsed time
- Queued tasks and estimated start times
- Recently completed tasks (used as contextual reference)

Avoid robot encounters"Where did the mission go?"You can only guess the answer based on the FAQ.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _format_duration(seconds: Optional[float]) -> str:
    """Format seconds into a human-readable duration."""
    if seconds is None or seconds < 0:
        return "未知"
    try:
        s = int(seconds)
        if s < 60:
            return f"{s} 秒"
        if s < 3600:
            return f"{s // 60} 分 {s % 60} 秒"
        h = s // 3600
        m = (s % 3600) // 60
        return f"{h} 时 {m} 分"
    except Exception:
        return str(seconds)


def _running_tasks_format_time_ago(dt_value: Any) -> str:
    """Format a datetime or ISO string as'X minutes ago'format."""
    if not dt_value:
        return "未知"
    try:
        if isinstance(dt_value, str):
            normalized = dt_value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
        elif isinstance(dt_value, datetime):
            dt = dt_value
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
        else:
            return str(dt_value)[:19]
        diff = (datetime.now() - dt).total_seconds()
        if diff < 0:
            return dt.strftime("%Y-%m-%d %H:%M")
        if diff < 60:
            return "刚刚"
        if diff < 3600:
            return f"{int(diff / 60)} 分钟前"
        if diff < 86400:
            return f"{int(diff / 3600)} 小时前"
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(dt_value)[:19]


def _calc_elapsed(started_at: Any) -> Optional[float]:
    """Calculates the number of seconds elapsed."""
    if not started_at:
        return None
    try:
        if isinstance(started_at, str):
            normalized = started_at.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
        elif isinstance(started_at, datetime):
            dt = started_at
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
        else:
            return None
        return (datetime.now() - dt).total_seconds()
    except Exception:
        return None


def _estimate_remaining(progress: int, elapsed_seconds: Optional[float]) -> Optional[float]:
    """Estimate remaining seconds based on progress and elapsed time."""
    if not elapsed_seconds or elapsed_seconds <= 0:
        return None
    if progress <= 0:
        return None
    if progress >= 100:
        return 0
    # Estimated total duration = Time spent / (Progress / 100)
    estimated_total = elapsed_seconds / (progress / 100)
    remaining = estimated_total - elapsed_seconds
    return max(0, remaining)


def _resolve_symbol(task_params: Dict[str, Any]) -> str:
    """Extract symbol/stock_code/analysis_target from task_params."""
    if not task_params:
        return "?"
    return (
        task_params.get("symbol")
        or task_params.get("stock_code")
        or task_params.get("code")
        or task_params.get("analysis_target")
        or "?"
    )


def _map_task_type_label(task_type: str) -> str:
    """Map task types to Chinese labels."""
    mapping = {
        "stock_analysis": "单股分析",
        "etf_analysis": "ETF 分析",
        "position_analysis": "持仓分析",
        "trade_review": "操作复盘",
        "portfolio_health": "组合健康度",
        "risk_assessment": "风险评估",
        "market_overview": "市场概览",
        "sector_analysis": "板块分析",
        "general": "通用研究",
    }
    return mapping.get(task_type, task_type or "未知")


def _map_status_label(status: str) -> tuple[str, str]:
    """Map the status to (emoji, Chinese description). """
    mapping = {
        "pending": ("⏳", "排队中"),
        "running": ("🔄", "运行中"),
        "processing": ("🔄", "运行中"),
        "completed": ("✅", "已完成"),
        "failed": ("❌", "失败"),
        "cancelled": ("⚪", "已取消"),
    }
    return mapping.get(status, ("❓", status or "未知"))


async def _query_active_tasks(db, user_id: str) -> List[Dict[str, Any]]:
    """Query running and queued tasks."""
    try:
        from bson import ObjectId
        # user_id May be ObjectId or string, for compatibility
        uid_variants = [user_id]
        try:
            uid_obj = ObjectId(user_id)
            uid_variants.append(uid_obj)
        except Exception:
            pass

        query = {
            "user_id": {"$in": uid_variants},
            "status": {"$in": ["pending", "running", "processing"]},
        }

        cursor = db["unified_analysis_tasks"].find(query).sort("created_at", -1).limit(20)
        docs = await cursor.to_list(length=20)
        for d in docs:
            d.pop("_id", None)
        return docs
    except Exception as exc:
        logger.warning("[get_running_tasks] Query running task failed: %s", exc)
        return []


async def _query_recent_completed(db, user_id: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Query recently completed tasks (used as a contextual reference)."""
    try:
        from bson import ObjectId
        uid_variants = [user_id]
        try:
            uid_obj = ObjectId(user_id)
            uid_variants.append(uid_obj)
        except Exception:
            pass

        query = {
            "user_id": {"$in": uid_variants},
            "status": {"$in": ["completed", "failed", "cancelled"]},
        }

        cursor = db["unified_analysis_tasks"].find(query).sort("completed_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        for d in docs:
            d.pop("_id", None)
        return docs
    except Exception as exc:
        logger.warning("[get_running_tasks] Failed to query recently completed tasks: %s", exc)
        return []


@tool
@register_tool(
    tool_id="get_running_tasks",
    name="查询运行中和排队的任务",
    description="Query the current user s running and queued analysis tasks: current step, progress percentage, elapsed time, estimated remaining time, and queue position. When the user asks'Where did the mission go?''How long will it take''There are several tasks queued''When will the analysis be completed?'when used.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "running_tasks", "task_progress", "pending_tasks", "task_status", "queue", "active_tasks"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=[
        "任务跑到哪一步了",
        "分析进度怎么样",
        "还要多久才能完成",
        "有几个任务在排队",
        "我的任务完成了吗",
        "任务什么时候结束",
        "正在运行的任务",
    ],
    when_to_use="Used when the user asks about the progress, remaining time, and queue status of running tasks. Returns a list of currently running, queued, and recently completed tasks.",
    returns="Returns a summary of the task running status in text format, including running tasks, queued tasks, recently completed tasks, and comprehensive judgments.",
)
async def get_running_tasks() -> str:
    """Query running and queued tasks."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()

    active_tasks = await _query_active_tasks(db, user_id)
    recent_completed = await _query_recent_completed(db, user_id, limit=3)

    lines = ["📊 任务运行状态"]

    if not active_tasks:
        lines.append("")
        lines.append("💤 There are currently no tasks running or queued")
    else:
        # Group by status: running first, pending next
        running = [t for t in active_tasks if t.get("status") in ("running", "processing")]
        pending = [t for t in active_tasks if t.get("status") == "pending"]

        # 1) Running tasks
        lines.append("")
        lines.append(f"【1】运行中任务（共 {len(running)} 个）")
        if not running:
            lines.append("- 无")
        else:
            for i, t in enumerate(running[:5], 1):
                task_type = t.get("task_type", "?")
                type_label = _map_task_type_label(task_type)
                symbol = _resolve_symbol(t.get("task_params") or {})
                progress = int(t.get("progress") or 0)
                current_step = t.get("current_step") or t.get("message") or "处理中"
                started_at = t.get("started_at") or t.get("created_at")
                elapsed = _calc_elapsed(started_at)
                remaining = _estimate_remaining(progress, elapsed)

                emoji, _ = _map_status_label(t.get("status", "running"))
                lines.append(
                    f"  {i}. {emoji} [{type_label}] {symbol}"
                )
                lines.append(f"      进度: {progress}%")
                lines.append(f"      当前步骤: {current_step}")
                lines.append(f"      已耗时: {_format_duration(elapsed)}")
                if remaining is not None:
                    lines.append(f"      预计剩余: {_format_duration(remaining)}")
                started_ago = _running_tasks_format_time_ago(started_at)
                lines.append(f"      开始时间: {started_ago}")

        # 2) Tasks in queue
        lines.append("")
        lines.append(f"【2】排队中任务（共 {len(pending)} 个）")
        if not pending:
            lines.append("- 无")
        else:
            for i, t in enumerate(pending[:5], 1):
                task_type = t.get("task_type", "?")
                type_label = _map_task_type_label(task_type)
                symbol = _resolve_symbol(t.get("task_params") or {})
                created_at = t.get("created_at")
                lines.append(
                    f"  {i}. ⏳ [{type_label}] {symbol} (排队位置: #{i})"
                )
                lines.append(f"      提交时间: {_running_tasks_format_time_ago(created_at)}")

    # 3) Recently completed tasks (contextual reference)
    lines.append("")
    lines.append(f"【3】最近完成的任务（{len(recent_completed)} 条，作上下文参考）")
    if not recent_completed:
        lines.append("- 暂无历史任务")
    else:
        for t in recent_completed[:3]:
            task_type = t.get("task_type", "?")
            type_label = _map_task_type_label(task_type)
            symbol = _resolve_symbol(t.get("task_params") or {})
            status = t.get("status", "?")
            emoji, status_cn = _map_status_label(status)
            completed_at = t.get("completed_at") or t.get("updated_at")
            execution_time = t.get("execution_time")

            # Analysis takes time
            if execution_time:
                duration_str = _format_duration(float(execution_time))
            else:
                # Calculated from started_at and completed_at
                started_at = t.get("started_at")
                if started_at and completed_at:
                    try:
                        if isinstance(started_at, str):
                            started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                            if started_at.tzinfo:
                                started_at = started_at.astimezone().replace(tzinfo=None)
                        if isinstance(completed_at, str):
                            completed_dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                            if completed_dt.tzinfo:
                                completed_dt = completed_dt.astimezone().replace(tzinfo=None)
                        else:
                            completed_dt = completed_at
                        duration_str = _format_duration((completed_dt - started_at).total_seconds())
                    except Exception:
                        duration_str = "未知"
                else:
                    duration_str = "未知"

            err_hint = ""
            if status == "failed" and t.get("error_message"):
                err_hint = f" | 错误: {str(t['error_message'])[:80]}"

            lines.append(
                f"  • {emoji} [{type_label}] {symbol} | {status_cn} | "
                f"Time consuming {duration_str} | Complete {_running_tasks_format_time_ago(completed_at)}{err_hint}"
            )

    # 4) Comprehensive judgment
    lines.append("")
    lines.append("💡 综合判断")
    running_count = sum(1 for t in active_tasks if t.get("status") in ("running", "processing"))
    pending_count = sum(1 for t in active_tasks if t.get("status") == "pending")

    if running_count == 0 and pending_count == 0:
        lines.append("- There are currently no running tasks, new analysis can be submitted")
        # Check if there are any recent failed tasks
        failed_recent = [t for t in recent_completed if t.get("status") == "failed"]
        if failed_recent:
            latest_failed = failed_recent[0]
            symbol = _resolve_symbol(latest_failed.get("task_params") or {})
            lines.append(f"- ⚠️ 最近一次 {symbol} 任务失败，建议查看错误原因后重试")
    else:
        if running_count > 0:
            # Get the first running task
            first_running = next((t for t in active_tasks if t.get("status") in ("running", "processing")), None)
            if first_running:
                symbol = _resolve_symbol(first_running.get("task_params") or {})
                progress = int(first_running.get("progress") or 0)
                started_at = first_running.get("started_at") or first_running.get("created_at")
                elapsed = _calc_elapsed(started_at)
                remaining = _estimate_remaining(progress, elapsed)
                lines.append(
                    f"- 正在分析 {symbol}，进度 {progress}%，已运行 {_format_duration(elapsed)}"
                )
                if remaining is not None and remaining > 0:
                    lines.append(f"- 预计还需 {_format_duration(remaining)} 完成")

        if pending_count > 0:
            lines.append(f"- 还有 {pending_count} 个任务在排队等待")

        # JD Cloud Edition: Force single concurrency, remind users
        import os
        is_jdyun = os.getenv("JDYUN_MODE", "").strip().lower() in ("true", "1", "yes")
        if is_jdyun and (running_count + pending_count) > 1:
            lines.append("- 📌 Jingdong Cloud version forces single concurrency, multiple tasks will be executed serially, and the waiting time will be long.")

    return "\n".join(lines)

# === schedule_manager ===
"""
Scheduled task management tools

Provides query, creation and enable/disable functions for scheduled analysis configuration.
User identity is obtained through core.tools.context.
"""

import logging
from typing import Annotated, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="list_scheduled_configs",
    name="查看定时分析配置",
    description="Lists all scheduled analysis configurations created by the user, displaying the name, CRON time period, and enabled/disabled status. Note: Scheduled analysis configuration is different from stock watch list (stock watch list) and stock watch list grouping; the former determines automatic analysis tasks, and the latter is just a stock pool or organization method.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["schedule", "scheduled_analysis", "config", "list", "query", "assistant_ops", "cron", "scheduled_task", "task_config", "automation_config", "schedule_query"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["查看定时配置", "定时任务列表", "计划任务查询", "自动分析配置查看"],
    when_to_use="This is used when the user wants to view the scheduled analysis configuration list that he has created and learn about the automatic analysis plans.",
    returns="Returns a scheduled analysis configuration list in text format, each containing configuration ID, name, enablement status, and CRON time period summary.",
)
async def list_scheduled_configs() -> str:
    """Lists a summary of all scheduled analysis configurations for the current user."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()

    cursor = db.scheduled_analysis_configs.find({"user_id": user_id}).sort("created_at", -1)

    configs = []
    async for doc in cursor:
        config_id = str(doc["_id"])
        name = doc.get("name", "未命名")
        enabled = "✅ 启用" if doc.get("enabled") else "⏸️ 禁用"
        slots = doc.get("time_slots", [])
        slot_summary = ", ".join(
            f"{s.get('name', '?')}({s.get('cron_expression', '?')})"
            for s in slots[:3]
        )
        if len(slots) > 3:
            slot_summary += f" +{len(slots) - 3}个"
        configs.append(f"  [{config_id[:8]}] {name} | {enabled} | {slot_summary}")

    if not configs:
        return "📋 There is currently no scheduled analysis configuration. You can ask me to create one for you."
    return f"📋 共 {len(configs)} 个定时分析配置：\n" + "\n".join(configs)


@tool
@register_tool(
    tool_id="create_scheduled_analysis",
    name="创建定时分析",
    description="Create a scheduled automatic analysis plan: specify the name, CRON time expression, and stock watch list grouping to be analyzed, and the system will automatically trigger the analysis according to the plan. Note: Only the groups configured here will enter timing analysis.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["schedule", "scheduled_analysis", "create", "config", "cron", "assistant_ops", "automation", "scheduled_task", "task_creation", "analysis_plan", "cron_expression"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["创建定时分析", "设置自动分析", "定时任务创建", "CRON计划配置"],
    when_to_use="Used when the user wants to create a new scheduled automatic analysis plan, specify CRON time and stock watch list grouping.",
    returns="Returns a text message containing the name of the new configuration, configuration ID, time period, analysis depth, and enabling status.",
)
async def create_scheduled_analysis(
    name: Annotated[str, "Configuration name, such as Daily Morning Analysis "],
    cron_expression: Annotated[str, "CRON Expressions such as 0 9 * * 1-5 Indicates 9 a.m. on weekdays"],
    group_ids: Annotated[str, "Stock watch list group ID list, comma separated"],
    slot_name: Annotated[str, "Time period name, such as Before the market opens "] = "默认时段",
    depth: Annotated[int, "Analysis depth 1-5, default 3"] = 3,
) -> str:
    """Create a new scheduled analysis configuration containing a time period."""
    from app.core.database import get_mongo_db
    from app.utils.timezone import now_tz

    user_id = require_current_user_id()
    db = get_mongo_db()

    # Check for name duplication
    existing = await db.scheduled_analysis_configs.find_one({"user_id": user_id, "name": name})
    if existing:
        return f"❌ 已存在同名配置「{name}」，请使用其他名称。"

    gid_list = [g.strip() for g in group_ids.split(",") if g.strip()]
    if not gid_list:
        return "❌ Please provide at least one stock watchlist group ID. You can first use View Stock Watch List Groups to obtain the group list."

    config_doc = {
        "user_id": user_id,
        "name": name,
        "description": "",
        "enabled": True,
        "time_slots": [{
            "name": slot_name,
            "cron_expression": cron_expression,
            "enabled": True,
            "group_ids": gid_list,
            "analysis_depth": depth,
        }],
        "default_group_ids": gid_list,
        "default_analysis_depth": depth,
        "default_quick_analysis_model": "",
        "default_deep_analysis_model": "",
        "default_prompt_template_id": None,
        "notify_on_complete": True,
        "notify_on_error": True,
        "send_email": False,
        "created_at": now_tz(),
        "updated_at": now_tz(),
    }

    result = await db.scheduled_analysis_configs.insert_one(config_doc)
    config_id = str(result.inserted_id)

    # Register to scheduler
    try:
        from app.pro.routers.scheduled_analysis import _register_scheduled_tasks
        config_doc["id"] = config_id
        await _register_scheduled_tasks(config_doc)
    except Exception as e:
        logger.warning(f"Failed to register scheduled tasks (configuration has been saved): {e}")

    return (
        f"✅ 定时分析配置已创建\n"
        f"- Name: {name}\n"
        f"- Configuration ID: {config_id}\n"
        f"- time period: {slot_name} ({cron_expression}) \n"
        f"- Analysis depth: {depth}\n"
        f"- Status: Enabled\n"
        f"The configuration will automatically perform analysis on a schedule."
    )


@tool
@register_tool(
    tool_id="toggle_scheduled_config",
    name="启用或禁用定时分析",
    description="Enable or disable existing scheduled analysis configurations (without deleting the configuration itself). Return the operation result and register or cancel the scheduler task synchronously.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["schedule", "scheduled_analysis", "toggle", "enable", "disable", "config", "assistant_ops", "scheduled_task", "automation_control", "task_status", "schedule_management"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["启用定时分析", "禁用定时分析", "切换任务状态", "暂停自动分析"],
    when_to_use="Used when the user wants to enable or disable an existing scheduled analysis configuration, pause or resume the automatic analysis plan.",
    returns="Returns a text message indicating the result of the configured enable/disable operation.",
)
async def toggle_scheduled_config(
    config_id: Annotated[str, "定时分析配置ID"],
    enabled: Annotated[bool, "True=enable, False=Disable"],
) -> str:
    """Enable or disable specified scheduled analysis configurations, and register or cancel scheduler tasks."""
    from bson import ObjectId
    from app.core.database import get_mongo_db
    from app.utils.timezone import now_tz

    user_id = require_current_user_id()
    db = get_mongo_db()

    try:
        oid = ObjectId(config_id)
    except Exception:
        return "❌ 无效的配置ID"

    config = await db.scheduled_analysis_configs.find_one({"_id": oid, "user_id": user_id})
    if not config:
        return f"❌ 未找到配置: {config_id}"

    if config.get("enabled") == enabled:
        status = "启用" if enabled else "禁用"
        return f"ℹ️ 配置「{config.get('name', '')}」已经是{status}状态。"

    await db.scheduled_analysis_configs.update_one(
        {"_id": oid},
        {"$set": {"enabled": enabled, "updated_at": now_tz()}},
    )

    # Update scheduler
    try:
        from app.pro.routers.scheduled_analysis import _register_scheduled_tasks, _unregister_scheduled_tasks
        if enabled:
            config["id"] = str(config.pop("_id"))
            config["enabled"] = True
            await _register_scheduled_tasks(config)
        else:
            await _unregister_scheduled_tasks(config_id)
    except Exception as e:
        logger.warning(f"Scheduler update failed (database updated): {e}")

    action = "启用" if enabled else "禁用"
    return f"✅ 已{action}定时分析配置「{config.get('name', '')}」"

# === stock_sync_ops ===
"""Single stock data synchronization tool."""

import logging
from typing import Annotated

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _normalize_cn_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text


def _format_sync_section(title: str, payload: dict | None) -> str:
    if payload is None:
        return f"- {title}: 未执行"

    if payload.get("success"):
        details = []
        if payload.get("records") is not None:
            details.append(f"记录数 {payload['records']}")
        if payload.get("data_source_used"):
            details.append(f"数据源 {payload['data_source_used']}")
        suffix = f"（{'，'.join(details)}）" if details else ""
        return f"- {title}: 成功{suffix}"

    error = payload.get("error") or payload.get("message") or "未知错误"
    return f"- {title}: 失败（{error}）"


@tool
@register_tool(
    tool_id="sync_single_stock_data",
    name="同步单股数据",
    description="Synchronize the data of a single stock to the local database, support historical market prices and financial data, and optionally supplement basic data. Suitable for users clear requirements Synchronize data of a certain stock  Update historical/financial data for a certain stock scene.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="heavy",
    data_source_handling="self_contained",
    capability_tags=["data_sync", "stock_data", "sync", "assistant_ops", "historical_data", "financial_data", "data_pipeline", "local_database", "stock_sync", "data_ingestion"],
    tool_role_hint="specialized",
    output_shape="text",
    preferred_for=["同步单只股票数据", "更新股票历史行情", "更新股票财务数据", "补充股票基础数据"],
    when_to_use="It is used when the user explicitly requests to synchronize the historical quotes and financial data of a certain stock, or update the local data of a certain stock.",
    returns="Returns the synchronization result in text format, including the synchronization status and record number of historical data, financial data, and basic data.",
)
async def sync_single_stock_data(
    symbol: Annotated[str, "Stock code, supports 6 digits or exchange suffix, such as 000001,600519.SH"],
    data_source: Annotated[str, "Data source, supports tushare or akshare, default tushare"] = "tushare",
    days: Annotated[int, "Number of days for historical data synchronization, default 365"] = 365,
    sync_historical: Annotated[bool, "Whether to synchronize historical quotes, default true"] = True,
    sync_financial: Annotated[bool, "Whether to synchronize financial data, default true"] = True,
    sync_basic: Annotated[bool, "Whether to supplement basic data, default false"] = False,
) -> str:
    """Synchronize historical and financial data for individual stocks."""
    from app.routers.stock_sync import SingleStockSyncRequest, run_single_stock_sync

    require_current_user_id()

    normalized_symbol = _normalize_cn_symbol(symbol)
    if not (len(normalized_symbol) == 6 and normalized_symbol.isdigit()):
        return f"❌ The stock symbol format is incorrect:{symbol}. Please enter a 6-digit code such as 000001 or 600519."

    if data_source not in {"tushare", "akshare"}:
        return f"❌ Currently only tushare or akshare data sources are supported, currently:{data_source}. "

    if not sync_historical and not sync_financial and not sync_basic:
        return "❌ Please select at least one type of synchronization: historical data, financial data, or basic data."

    try:
        result = await run_single_stock_sync(
            SingleStockSyncRequest(
                symbol=normalized_symbol,
                sync_realtime=False,
                sync_historical=sync_historical,
                sync_financial=sync_financial,
                sync_basic=sync_basic,
                data_source=data_source,
                days=days,
            )
        )
    except Exception as exc:
        logger.exception("[sync_single_stock_data] Single stock data synchronization failed: %s", exc)
        return f"❌ Single stock data synchronization failed:{exc}"

    lines = [
        f"{'✅' if result.get('overall_success') else '⚠️'} 单股数据同步完成",
        f"- 股票: {normalized_symbol}",
        f"- 数据源: {data_source}",
        _format_sync_section("历史数据", result.get("historical_sync")),
        _format_sync_section("财务数据", result.get("financial_sync")),
    ]

    if sync_basic:
        lines.append(_format_sync_section("基础数据", result.get("basic_sync")))

    if result.get("overall_success"):
        lines.append("- result: The synchronization item requested this time has been successfully completed. You can continue to query the latest data or initiate analysis.")
    else:
        lines.append("- result: There are failed items. Please decide whether to change the data source or try again later based on the above failure reasons.")

    return "\n".join(lines)

# === system_status ===
"""Use the Q&A bot tool: Query system status.

Provides the ability to query system mode (standard/JD Cloud), current default model, data source activation status, version number, etc.
Allows using Q&A Assistant to"see"The current real state of the system.
"""

import logging
import os
from typing import Annotated

from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _resolve_version() -> str:
    """Read VERSION file"""
    try:
        # Tool file path: core/tools/implementations/assistant_ops/system_status.py
        # Project root directory: Go to Level 4
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, "..", "..", "..", ".."))
        version_path = os.path.join(project_root, "VERSION")
        if os.path.exists(version_path):
            with open(version_path, encoding="utf-8") as f:
                return f.read().strip()
    except Exception as exc:
        logger.warning("[get_system_status] Failed to read VERSION file: %s", exc)
    return "未知"


def _system_status_is_jdyun_mode() -> bool:
    """判断是否为京东云模式"""
    return os.environ.get("JDYUN_MODE", "false").lower() == "true"


@tool
@register_tool(
    tool_id="get_system_status",
    name="获取系统状态",
    description="Query the current operating mode of the system (standard version/JD Cloud version), default large model, data source activation status and version number. When the user asks'what version is this''What model are you currently using?''What are the data sources?'Use it when you have questions.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "system_status", "jdyun_mode", "default_model", "data_sources", "version"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["当前是什么版本", "京东云版还是标准版", "当前用什么大模型", "数据源有哪些"],
    when_to_use="Used when the user asks about system configuration, schema, version, current model or data source status.",
    returns="Returns a system status summary in text format, including the operating mode, default model, data source list, and version number.",
)
async def get_system_status() -> str:
    """Get the current running status of the system."""
    from app.core.database import get_mongo_db

    db = get_mongo_db()
    jdyun = _system_status_is_jdyun_mode()
    version = _resolve_version()

    # Current default model
    default_model = "未配置"
    default_provider = "未配置"
    try:
        # Read enabled models from the llm_configs collection
        cursor = db.llm_configs.find({"enabled": True}, {"model_name": 1, "provider": 1, "is_default": 1}).limit(10)
        docs = await cursor.to_list(length=10)
        if docs:
            # Take priority is_default
            default_doc = next((d for d in docs if d.get("is_default")), docs[0])
            default_model = default_doc.get("model_name", "未知")
            default_provider = default_doc.get("provider", "未知")
    except Exception as exc:
        logger.warning("[get_system_status] Querying default model failed: %s", exc)

    # Data source enable status
    data_sources_lines = []
    try:
        cursor = db.data_sources.find({}, {"name": 1, "type": 1, "enabled": 1}).limit(20)
        docs = await cursor.to_list(length=20)
        if docs:
            for ds in docs:
                name = ds.get("name") or ds.get("type") or "?"
                ds_type = ds.get("type") or "?"
                enabled = "启用" if ds.get("enabled") else "禁用"
                # JD Cloud version hides unsupported data sources
                if jdyun and ds_type.lower() not in {"tushare", "akshare"}:
                    continue
                data_sources_lines.append(f"  - {name}({ds_type}): {enabled}")
        else:
            data_sources_lines.append("  - (The data source is not configured in the database)")
    except Exception as exc:
        logger.warning("[get_system_status] Querying data source failed: %s", exc)
        data_sources_lines.append(f"  - 查询失败: {exc}")

    lines = [
        "🖥️ 系统状态",
        f"- 运行模式: {'京东云版' if jdyun else '标准版'}",
        f"- 版本号: v{version}",
        f"- 默认大模型: {default_model} (厂家: {default_provider})",
        "- 数据源:",
    ]
    lines.extend(data_sources_lines or ["  - 无"])

    if jdyun:
        lines.append("- JD Cloud Version Instructions: Fully functional and open, no license required; large models and data sources are configured uniformly by the platform")

    return "\n".join(lines)

# === token_usage ===
"""Use the Q&A robot tool: Query Token usage statistics.

Allows using Q&A Assistant to"see"The user s current Token usage and quota usage,
This allows JD Cloud users to understand the rate of quota consumption in real time and avoid exceeding the quota.

Data source:
- Direct reuse UsageStatisticsService.get_usage_statistics() Get detailed statistics
- Read the quota upper limit from the environment variable JDYUN_TOKEN_QUOTA (valid only for JD Cloud version)
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Annotated, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _format_tokens(value: Optional[int]) -> str:
    """Format the token number as a human-readable string."""
    if value is None:
        return "未知"
    try:
        v = int(value)
        if v >= 1_000_000:
            return f"{v / 1_000_000:.2f} M"
        if v >= 1_000:
            return f"{v / 1_000:.2f} K"
        return f"{v}"
    except Exception:
        return str(value)


def _resolve_token_quota() -> int:
    """Read the Token quota limit (valid only for JD Cloud version)."""
    if os.getenv("JDYUN_MODE", "").strip().lower() in ("true", "1", "yes"):
        return int(os.getenv("JDYUN_TOKEN_QUOTA", "0") or "0")
    return 0


@tool
@register_tool(
    tool_id="get_token_usage",
    name="Query Token usage statistics",
    description="Query token usage statistics: number of used tokens today/this week/month, quota limit, remaining quota, consumption grouped by model, consumption grouped by task. When the user asks'How much did you use today? token''How much quota is left?''Which model consumes the most''Token Usage trends'when used.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "token_usage", "quota", "cost", "llm_usage", "api_usage"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=[
        "今天用了多少 token",
        "还剩多少配额",
        "Token 用量",
        "本周 Token 消耗",
        "哪个模型消耗最多",
        "Token 用量趋势",
        "配额什么时候重置",
        "还能用多少次分析",
    ],
    when_to_use="Used when users ask about token usage, quota usage, model consumption, and API call costs. Supports days parameter to specify statistical period (default 7 days).",
    returns="Returns a Token usage summary in text format, including used/quota/remaining/percentage/consumption grouped by model/trend by date.",
)
async def get_token_usage(
    days: Annotated[
        Optional[int],
        "Number of days in the statistical period (default 7 days, optional 1/7/30,1=Today,7=This week,30=this month). JD Cloud version recommends passing 1 or 7."
    ] = 7,
) -> str:
    """Query Token usage statistics."""
    from app.core.database import get_mongo_db
    from app.services.usage_statistics_service import usage_statistics_service

    # Trigger user context (although the service side presses global statistics, maintain consistency)
    require_current_user_id()

    # Standardize days
    try:
        days_int = int(days) if days else 7
    except (TypeError, ValueError):
        days_int = 7
    if days_int < 1:
        days_int = 1
    if days_int > 365:
        days_int = 365

    db = get_mongo_db()
    is_jdyun = os.getenv("JDYUN_MODE", "").strip().lower() in ("true", "1", "yes")

    # Reuse existing services to get detailed statistics
    try:
        stats = await usage_statistics_service.get_usage_statistics(days=days_int)
    except Exception as exc:
        logger.warning("[get_token_usage] Failed to query statistics: %s", exc)
        return (
            "📊 Token Usage statistics\n"
            "\n"
            f"❌ Query failed: {exc}\n"
            "\n"
            "Please try again later, or check the backend logs."
        )

    used_tokens = (stats.total_input_tokens or 0) + (stats.total_output_tokens or 0)
    input_tokens = stats.total_input_tokens or 0
    output_tokens = stats.total_output_tokens or 0
    total_requests = stats.total_requests or 0
    quota_tokens = _resolve_token_quota()
    percentage = round((used_tokens / quota_tokens) * 100, 2) if quota_tokens > 0 else 0.0
    remaining_tokens = max(0, quota_tokens - used_tokens) if quota_tokens > 0 else 0

    # Quota reset time
    reset_at = (datetime.utcnow() + timedelta(days=days_int)).strftime("%Y-%m-%d %H:%M UTC")

    # Group consumption by model (stats.by_model is dict: {model_name: {requests, input_tokens, output_tokens, cost, ...}}) 
    by_model_dict = getattr(stats, "by_model", None) or {}
    # Group consumption by provider (stats.by_provider is a dict)
    by_provider_dict = getattr(stats, "by_provider", None) or {}
    # Trend by date (stats.by_date is dict: {date_str: {...}}) 
    by_date_dict = getattr(stats, "by_date", None) or {}

    lines = ["📊 Token 用量统计"]
    period_label = {1: "今日", 7: "本周", 30: "本月"}.get(days_int, f"近 {days_int} 天")
    lines.append(f"- 统计周期: {period_label}（{days_int} 天）")
    lines.append("")

    # 1) Overview
    lines.append("【1】用量总览")
    lines.append(f"- 已用 Token: {_format_tokens(used_tokens)}（输入 {_format_tokens(input_tokens)} + 输出 {_format_tokens(output_tokens)}）")
    lines.append(f"- 总请求数: {total_requests}")

    if quota_tokens > 0:
        lines.append(f"- 配额上限: {_format_tokens(quota_tokens)}")
        lines.append(f"- 剩余配额: {_format_tokens(remaining_tokens)}")
        lines.append(f"- 使用率: {percentage}%")
        lines.append(f"- 配额重置时间: {reset_at}")

        # Quota warning
        if percentage >= 90:
            lines.append("- 🔴 The quota is about to be exhausted. It is recommended to reduce the analysis tasks or wait for reset.")
        elif percentage >= 70:
            lines.append("- 🟡 The quota is consumed quickly, so it is recommended to pay attention to the usage.")
        elif percentage >= 50:
            lines.append("- 🟢 More than half of the quota is used, which is normal.")
        else:
            lines.append("- 🟢 配额充足")
    else:
        lines.append("- Quota cap: Unlimited (standard version default)")

    # 2) Consumption grouped by model
    lines.append("")
    lines.append("【2】按模型分组消耗")
    if by_model_dict:
        # Sort by total_tokens in descending order, take TOP 5
        sorted_models = sorted(
            by_model_dict.items(),
            key=lambda kv: (kv[1].get("input_tokens", 0) + kv[1].get("output_tokens", 0)),
            reverse=True,
        )
        for model_name, m_data in sorted_models[:5]:
            m_input = m_data.get("input_tokens", 0)
            m_output = m_data.get("output_tokens", 0)
            m_tokens = m_input + m_output
            m_requests = m_data.get("requests", 0)
            lines.append(f"  • {model_name}: {_format_tokens(m_tokens)} ({m_requests} 次)")
    else:
        lines.append("  - 无数据")

    # 3) Consumption grouped by supplier
    lines.append("")
    lines.append("【3】按供应商分组消耗")
    if by_provider_dict:
        sorted_providers = sorted(
            by_provider_dict.items(),
            key=lambda kv: (kv[1].get("input_tokens", 0) + kv[1].get("output_tokens", 0)),
            reverse=True,
        )
        for provider_name, p_data in sorted_providers[:3]:
            p_tokens = p_data.get("input_tokens", 0) + p_data.get("output_tokens", 0)
            lines.append(f"  • {provider_name}: {_format_tokens(p_tokens)}")
    else:
        lines.append("  - 无数据")

    # 4) Trend by date
    lines.append("")
    lines.append("【4】每日用量趋势")
    if by_date_dict:
        # Sort by date in ascending order, take the last 7 days
        sorted_dates = sorted(by_date_dict.items(), key=lambda kv: kv[0], reverse=False)
        recent_dates = sorted_dates[-7:] if len(sorted_dates) > 7 else sorted_dates
        for date_str, d_data in recent_dates:
            d_tokens = d_data.get("input_tokens", 0) + d_data.get("output_tokens", 0)
            lines.append(f"  • {date_str}: {_format_tokens(d_tokens)}")
    else:
        lines.append("  - 无数据")

    # 5) Comprehensive judgment
    lines.append("")
    lines.append("💡 综合判断")
    if total_requests == 0:
        lines.append(f"- 近 {days_int} 天没有 LLM 调用记录，可能是分析任务未运行或统计未生效")
    else:
        avg_per_request = used_tokens // max(total_requests, 1)
        lines.append(f"- 平均每次请求消耗 {_format_tokens(avg_per_request)} Token")

        if is_jdyun:
            # JD Cloud Edition: Estimate how many more analyzes can be run
            avg_analysis_cost = 50_000  # A single single stock analysis is about 50,000 token
            if quota_tokens > 0:
                remaining_analyses = remaining_tokens // avg_analysis_cost
                lines.append(f"- 按单次分析约 5 万 Token 估算，剩余可执行约 {remaining_analyses} 次单股分析")
            else:
                lines.append("- JD Cloud version has no quota limit configured, please pay attention to the console usage alarm.")

        # Trend observation by date
        if by_date_dict:
            sorted_dates = sorted(by_date_dict.items(), key=lambda kv: kv[0], reverse=False)
            if len(sorted_dates) >= 2:
                last_date, last_data = sorted_dates[-1]
                prev_date, prev_data = sorted_dates[-2]
                last_tokens = last_data.get("input_tokens", 0) + last_data.get("output_tokens", 0)
                prev_tokens = prev_data.get("input_tokens", 0) + prev_data.get("output_tokens", 0)
                if prev_tokens > 0:
                    change_pct = ((last_tokens - prev_tokens) / prev_tokens) * 100
                    trend = "上升" if change_pct > 0 else "下降" if change_pct < 0 else "持平"
                    lines.append(f"- 最近一天用量 {_format_tokens(last_tokens)}，较前一日{trend} {abs(change_pct):.1f}%")

    if is_jdyun:
        lines.append("")
        lines.append("📌 Note: JD Cloud version only supports GLM series models, forcing single concurrency, and a single single stock analysis consumes about 50,000-100,000 Token")

    return "\n".join(lines)

# === topic_manager ===
"""
Smart assistant theme management tool

Allow AI to directly create research topics, create subtopics, view topic trees, and delete topic trees.
The user identity and current topic context are obtained through core.tools.context.
"""

import logging
from typing import Annotated, List, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import get_current_assistant_thread_id, get_current_im_channel, require_current_user_id, set_current_assistant_thread_id

logger = logging.getLogger(__name__)


async def _load_threads(db, user_id: str) -> List[dict]:
    cursor = db.assistant_threads.find({
        "user_id": user_id,
        "archived": {"$ne": True},
    }).sort([("pinned", -1), ("updated_at", -1)])
    docs = await cursor.to_list(length=None)
    return [
        doc for doc in docs
        if (doc.get("topic_type") or "") != "im_session" and not _is_gateway_session_thread_id(doc.get("thread_id"))
    ]


def _is_gateway_session_thread_id(thread_id: Optional[str]) -> bool:
    return bool(thread_id and ":" in thread_id)


async def _get_current_im_session(db, user_id: str) -> Optional[dict]:
    im_channel = get_current_im_channel()
    if not im_channel:
        return None

    from core.gateway.session import SessionManager

    session_manager = SessionManager(db)
    return await session_manager.get_or_create(
        user_id,
        im_channel.get("channel_type") or "",
        im_channel.get("channel_id") or "",
    )


async def _bind_current_topic(db, user_id: str, thread_id: Optional[str]) -> None:
    session = await _get_current_im_session(db, user_id)
    if session:
        from core.gateway.session import SessionManager

        session_manager = SessionManager(db)
        await session_manager.set_current_topic_id(session.get("session_key") or "", thread_id)

    set_current_assistant_thread_id(thread_id)


async def _get_bound_current_topic_id(db, user_id: str) -> Optional[str]:
    current_thread_id = (get_current_assistant_thread_id() or "").strip() or None
    if current_thread_id and not _is_gateway_session_thread_id(current_thread_id):
        return current_thread_id

    session = await _get_current_im_session(db, user_id)
    if not session:
        return None

    context = session.get("context") or {}
    return (context.get("current_topic_id") or "").strip() or None


async def _get_bound_current_topic_doc(db, user_id: str) -> Optional[dict]:
    current_topic_id = await _get_bound_current_topic_id(db, user_id)
    if not current_topic_id:
        return None
    return await db.assistant_threads.find_one({
        "user_id": user_id,
        "thread_id": current_topic_id,
        "archived": {"$ne": True},
    })


def _normalize_title(title: str) -> str:
    text = (title or "").strip().lower()
    if not text:
        return ""

    replacements = {
        "新能源汽车": "新能源车",
        "新能源汽車": "新能源车",
        "个股": "公司",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    for token in ["（", "）", "(", ")", "-", "_", " ", "　", "/", "\\", "·", "、"]:
        text = text.replace(token, "")

    removable_suffixes = [
        "研究主题",
        "产业链研究",
        "行业研究",
        "板块研究",
        "公司研究",
        "个股研究",
        "深度研究",
        "专题研究",
        "课题研究",
        "产业链",
        "行业",
        "板块",
        "研究",
        "分析",
        "跟踪",
        "专题",
        "主题",
    ]
    changed = True
    while changed and len(text) > 2:
        changed = False
        for suffix in removable_suffixes:
            if text.endswith(suffix) and len(text) > len(suffix) + 1:
                text = text[: -len(suffix)]
                changed = True
                break

    return text


def _titles_match(first: str, second: str) -> bool:
    normalized_first = _normalize_title(first)
    normalized_second = _normalize_title(second)
    if not normalized_first or not normalized_second:
        return False
    return normalized_first == normalized_second


def _find_matching_thread(docs: List[dict], title: str, parent_thread_id: Optional[str] = None) -> Optional[dict]:
    normalized_parent_id = (parent_thread_id or "").strip() or None
    candidates = [doc for doc in docs if (doc.get("parent_thread_id") or None) == normalized_parent_id]
    for doc in candidates:
        if _titles_match(doc.get("title") or "", title):
            return doc
    return None


def _format_thread_tree(docs: List[dict]) -> str:
    by_parent = {}
    by_id = {}
    for doc in docs:
        thread_id = doc.get("thread_id")
        by_id[thread_id] = doc
        by_parent.setdefault(doc.get("parent_thread_id"), []).append(doc)

    def _sort(items: List[dict]) -> List[dict]:
        return sorted(
            items,
            key=lambda item: (
                0 if item.get("pinned") else 1,
                -(item.get("updated_at").timestamp() if item.get("updated_at") else 0),
            ),
        )

    lines: List[str] = []

    def _walk(parent_id: Optional[str], depth: int = 0):
        for item in _sort(by_parent.get(parent_id, [])):
            prefix = "  " * depth + ("- " if depth else "• ")
            label = item.get("title") or "未命名主题"
            count = int(item.get("message_count") or 0)
            lines.append(f"{prefix}{label} [{item.get('thread_id')}]（{count} 条消息）")
            _walk(item.get("thread_id"), depth + 1)

    _walk(None)
    return "\n".join(lines)


async def _resolve_parent_thread_id(db, user_id: str, parent_title: Optional[str]) -> Optional[str]:
    title = (parent_title or "").strip()
    if not title:
        return await _get_bound_current_topic_id(db, user_id)

    all_docs = await _load_threads(db, user_id)
    matched = _find_matching_thread(all_docs, title, parent_thread_id=None)
    if matched:
        return matched.get("thread_id")

    docs = await db.assistant_threads.find({
        "user_id": user_id,
        "title": title,
        "archived": {"$ne": True},
    }).to_list(length=5)

    if not docs:
        raise ValueError(f"未找到标题为「{title}」的主题")
    if len(docs) > 1:
        raise ValueError(f"找到多个同名主题「{title}」，请先让我列出主题树后再指定更精确的父主题")
    return docs[0].get("thread_id")


async def _resolve_target_thread_id(db, user_id: str, title: Optional[str]) -> Optional[str]:
    normalized_title = (title or "").strip()
    if not normalized_title:
        return await _get_bound_current_topic_id(db, user_id)

    all_docs = await _load_threads(db, user_id)
    exact_or_semantic = [doc for doc in all_docs if _titles_match(doc.get("title") or "", normalized_title)]
    if len(exact_or_semantic) == 1:
        return exact_or_semantic[0].get("thread_id")
    if len(exact_or_semantic) > 1:
        raise ValueError(f"找到多个语义相近的主题「{normalized_title}」，请先让我列出主题树后再指定更精确的目标主题")

    docs = await db.assistant_threads.find({
        "user_id": user_id,
        "title": normalized_title,
        "archived": {"$ne": True},
    }).to_list(length=5)

    if not docs:
        raise ValueError(f"未找到标题为「{normalized_title}」的主题")
    if len(docs) > 1:
        raise ValueError(f"找到多个同名主题「{normalized_title}」，请先让我列出主题树后再指定更精确的目标主题")
    return docs[0].get("thread_id")


@tool
@register_tool(
    tool_id="list_assistant_topics",
    name="查看研究主题树",
    description="Lists the current user s research topic tree. Returns the topic level indentation, topic ID, and number of messages for each topic to facilitate viewing the research directory structure.",
    when_to_use="Used when the user wants to view the current research directory, topic structure, industry and company subtopic levels.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["topic_management", "research_topic", "topic_tree", "list", "query", "assistant_ops", "thread_management", "topic_hierarchy", "topic_structure", "research_directory"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["topic_tree_viewing", "research_structure_browsing", "topic_hierarchy_query", "thread_listing", "research_directory_viewing"],
    returns="Returns the topic tree in text format, including topic level indentation, topic ID, and number of messages in each topic.",
)
async def list_assistant_topics() -> str:
    """View the current user s research topic tree."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()
    docs = await _load_threads(db, user_id)
    if not docs:
        return "📁 There are currently no research topics. You can ask me to create an industry or company theme first."
    current_topic = await _get_bound_current_topic_doc(db, user_id)
    current_topic_line = ""
    if current_topic:
        current_topic_line = f"🎯 Current external conversation topic:{current_topic.get('title') or current_topic.get('thread_id')}\n"
    return current_topic_line + "📁 Current research topic tree:\n" + _format_thread_tree(docs)


@tool
@register_tool(
    tool_id="create_assistant_topic",
    name="创建研究主题",
    description="Create new top-level research topics for industry, strategy, or independent research lines. Returns the creation result (new/reused) and topic ID.",
    when_to_use="It is used when the user explicitly states that he wants to create a new research topic, industry directory, or research main line.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["topic_management", "research_topic", "create", "assistant_ops", "thread_management", "topic_creation", "research_mainline", "new_topic"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["topic_creation", "research_mainline_setup", "new_topic_initialization", "research_directory_creation"],
    returns="Returns a text message, including the creation result (new/reused) and topic ID.",
)
async def create_assistant_topic(
    title: Annotated[str, "Topic name to create, such as Battery Industry Tracking or Brokerage Sector Research"],
) -> str:
    """Create top-level research topics."""
    from app.core.database import get_mongo_db
    from app.services.intelligent_assistant_service import create_assistant_thread

    user_id = require_current_user_id()
    db = get_mongo_db()
    current_topic = await _get_bound_current_topic_doc(db, user_id)
    if current_topic and _titles_match(current_topic.get("title") or "", title):
        await _bind_current_topic(db, user_id, current_topic.get("thread_id"))
        return (
            f"ℹ️ Currently on the topic with the same semantics {current_topic.get('title') or title}] down,"
            f"No need to re-create.\n- Topic ID: {current_topic.get('thread_id')}"
        )

    item = await create_assistant_thread(db, user_id, title=title, parent_thread_id=None)
    await _bind_current_topic(db, user_id, item["thread_id"])
    if _titles_match(item.get("title") or "", title):
        return f"✅ Created and switched to research topic {item['title']}] \n- Topic ID: {item['thread_id']}"
    return f"ℹ️ Reused and switched to an existing theme with similar semantics {item['title']}] \n- Topic ID: {item['thread_id']}"


@tool
@register_tool(
    tool_id="create_assistant_subtopic",
    name="创建研究子主题",
    description="Create subtopics (industry company splits, company split valuations, etc.) under the current or specified parent topic. Returns the child theme creation result, parent theme and child theme ID.",
    when_to_use="When the user says Add a new subtopic under this topic ,  Add a company under an industry ,  Break out a sub-problem when used.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["topic_management", "research_topic", "create", "subtopic", "assistant_ops", "thread_management", "topic_hierarchy", "subtopic_creation", "child_topic"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["subtopic_creation", "topic_branching", "research_subdivision", "child_topic_setup"],
    returns="Returns a text message, including the child topic creation result, parent topic ID, and child topic ID.",
)
async def create_assistant_subtopic(
    title: Annotated[str, "Subtopic names, such as CATL, valuation breakdown, risk points"],
    parent_title: Annotated[Optional[str], "Optional, parent topic title; if left blank, it will default to the topic currently being discussed."] = None,
) -> str:
    """Create research subtopics."""
    from app.core.database import get_mongo_db
    from app.services.intelligent_assistant_service import create_assistant_thread

    user_id = require_current_user_id()
    db = get_mongo_db()
    try:
        parent_thread_id = await _resolve_parent_thread_id(db, user_id, parent_title)
    except ValueError as exc:
        return f"❌ {str(exc)}"

    if not parent_thread_id:
        return "❌ There is currently no available parent theme. Please create a research topic first, or tell me explicitly which topic you want to link to."

    all_docs = await _load_threads(db, user_id)
    similar_child = _find_matching_thread(all_docs, title, parent_thread_id=parent_thread_id)
    if similar_child:
        return (
            f"ℹ️ There are already sub-topics with similar semantics under the current topic {similar_child.get('title') or title}] , "
            f"No need to re-create.\n- subtopic ID: {similar_child.get('thread_id')}"
        )

    item = await create_assistant_thread(db, user_id, title=title, parent_thread_id=parent_thread_id)
    return (
        f"✅ 已创建子主题「{item['title']}」\n"
        f"- The current session is still bound to the parent topic: {parent_thread_id}\n"
        f"- Parent topic ID: {parent_thread_id}\n"
        f"- subtopic ID: {item['thread_id']}"
    )


@tool
@register_tool(
    tool_id="get_current_assistant_topic",
    name="查看当前研究主题",
    description="View current research topics on external session binding. Return the topic name and topic ID to facilitate confirmation of the main research line to which subsequent discussions belong.",
    when_to_use="It is used when the user asks which topic they are currently talking about, what this topic is, and which research directory it is currently hanging in.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["topic_management", "research_topic", "query", "current_topic", "assistant_ops", "thread_management", "context_query", "session_context"],
    tool_role_hint="supporting",
    output_shape="text",
    preferred_for=["current_topic_query", "session_context_check", "active_topic_verification"],
    returns="Returns a text message containing the current topic name and topic ID.",
)
async def get_current_assistant_topic() -> str:
    """View current research topics on external session binding."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()
    current_topic = await _get_bound_current_topic_doc(db, user_id)
    if not current_topic:
        return "ℹ️ The current external session does not have a research topic bound to it. You can ask me to create a topic first, or explicitly say Switch to a topic . "
    return (
        f"🎯 当前研究主题：{current_topic.get('title') or current_topic.get('thread_id')}\n"
        f"- Topic ID: {current_topic.get('thread_id')}"
    )


@tool
@register_tool(
    tool_id="switch_assistant_topic",
    name="切换当前研究主题",
    description="Bind the current session switch to an existing research topic, and subsequent discussions will be directed to this topic by default. Returns the switching result and target topic ID.",
    when_to_use="Use when the user explicitly requests to switch to a certain topic, continue with another industry or company topic, or specify that the current session should be bound to a certain line of research.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["topic_management", "research_topic", "switch", "assistant_ops", "thread_management", "topic_switching", "context_binding", "active_topic_change"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["topic_switching", "research_mainline_change", "session_binding_update", "active_topic_selection"],
    returns="Returns a text message containing the switch result and target topic ID.",
)
async def switch_assistant_topic(
    title: Annotated[str, "The topic title to be switched to, such as new energy vehicle research, CATL, securities sector research"],
) -> str:
    """Toggles the research topic bound to the current external session."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()
    try:
        thread_id = await _resolve_target_thread_id(db, user_id, title)
    except ValueError as exc:
        return f"❌ {str(exc)}"

    if not thread_id:
        return "❌ No switchable target theme found. Please create a topic first, or provide a more precise topic title."

    target = await db.assistant_threads.find_one({
        "user_id": user_id,
        "thread_id": thread_id,
        "archived": {"$ne": True},
    })
    if not target:
        return "❌ The target topic does not exist or has been deleted."

    await _bind_current_topic(db, user_id, thread_id)
    return (
        f"✅ The current research topic has been switched to {target.get('title') or thread_id}] \n"
        f"- Topic ID: {thread_id}"
    )


@tool
@register_tool(
    tool_id="delete_assistant_topic",
    name="删除研究主题树",
    description="Delete a research topic and all its subtopics, messages and abstracts (default current topic or by title). Returns the deleted topic number and topic ID list.",
    when_to_use="Only used when the user explicitly requests to delete a research topic, clean up a research main line, or delete the current topic and its subtopics. Involves destructive operations and must be called after the user clearly expresses the intention to delete.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["topic_management", "research_topic", "delete", "assistant_ops", "thread_management", "topic_deletion", "destructive_operation", "topic_tree_removal"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["topic_deletion", "research_cleanup", "topic_tree_removal", "theme_removal"],
    returns="Returns a text message containing the deletion result, the number of deleted topics, and the list of deleted topic IDs.",
)
async def delete_assistant_topic(
    title: Annotated[Optional[str], "Optional, topic title to be deleted; if left blank, the current topic will be deleted by default"] = None,
) -> str:
    """Delete the research topic tree."""
    from app.core.database import get_mongo_db
    from app.services.intelligent_assistant_service import ASSISTANT_DEFAULT_THREAD_ID, delete_assistant_thread

    user_id = require_current_user_id()
    db = get_mongo_db()

    try:
        thread_id = await _resolve_target_thread_id(db, user_id, title)
    except ValueError as exc:
        return f"❌ {str(exc)}"

    if not thread_id:
        return "❌ There are currently no target topics to delete. Please specify the topic title first, or perform deletion under a certain topic."
    if thread_id == ASSISTANT_DEFAULT_THREAD_ID:
        return "❌ The default theme cannot be deleted. Please switch to another theme or delete the child theme under the default theme."

    target = await db.assistant_threads.find_one({
        "user_id": user_id,
        "thread_id": thread_id,
        "archived": {"$ne": True},
    })
    if not target:
        return "❌ The target topic does not exist or has been deleted."

    try:
        deleted_ids = await delete_assistant_thread(db, user_id, thread_id)
    except ValueError as exc:
        return f"❌ {str(exc)}"

    current_topic_id = await _get_bound_current_topic_id(db, user_id)
    if current_topic_id and current_topic_id in deleted_ids:
        fallback_topic_id = (target.get("parent_thread_id") or "").strip() or None
        await _bind_current_topic(db, user_id, fallback_topic_id)

    deleted_count = len(deleted_ids)
    return (
        f"✅ 已删除主题树「{target.get('title') or thread_id}」\n"
        f"- Number of topics deleted: {deleted_count}\n"
        f"- Delete topic ID: {', '.join(deleted_ids)}"
    )

# === trade_review_ops ===
"""
Trading review tools

Provides the functions of querying review history, obtaining review report details, and initiating transaction review.
"""

import asyncio
import logging
from typing import Annotated, List, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="list_trade_reviews",
    name="查看复盘历史",
    description="Lists users transaction review records, and supports filtering by stock code, data source (simulated/real), and time range.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["trade_review", "review", "history", "list", "query", "assistant_ops", "trade_history", "review_records", "trade_analysis", "backtesting", "review_filtering"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["查看复盘历史", "复盘记录查询", "交易复盘列表", "按股票查复盘"],
    when_to_use="It is used when users want to view their own transaction review record list and filter review history by stock code or data source.",
    returns="Returns a list of review records in text format, each containing stock code, name, review type, profit and loss, score, status and review ID.",
)
async def list_trade_reviews(
    code: Annotated[Optional[str], "Stock code screening, such as 600519, leave blank for no limit"] = None,
    source: Annotated[Optional[str], "Data source filter:paper=simulated trading, position=Position operation, Leave blank for all"] = None,
    page: Annotated[int, "Page number, default 1"] = 1,
    page_size: Annotated[int, "Number per page, default 10"] = 10,
) -> str:
    """List the user s transaction review history."""
    try:
        from app.services.trade_review_service import get_trade_review_service

        user_id = require_current_user_id()
        service = get_trade_review_service()
        result = await service.get_review_history(
            user_id=user_id,
            page=page,
            page_size=page_size,
            code=code,
            source=source,
        )

        items = result.get("items", [])
        total = result.get("total", 0)

        if not items:
            filter_desc = ""
            if code:
                filter_desc += f" {code}"
            if source:
                filter_desc += f" ({source})"
            return f"没有找到{filter_desc}的复盘记录。"

        lines = [f"共 {total} 条复盘记录（第 {page} 页）：\n"]
        for item in items:
            code_str = item.get("code", "")
            name_str = item.get("name", "")
            review_type = item.get("review_type", "")
            status = item.get("status", "")
            score = item.get("overall_score", 0)
            pnl = item.get("realized_pnl", 0)
            created = item.get("created_at", "")
            review_id = item.get("review_id", "")

            # Format time
            if isinstance(created, str) and len(created) > 16:
                created = created[:16]

            pnl_str = f"{pnl:+.2f}" if pnl else "0"
            score_str = f"评分: {score}" if score else ""
            type_label = {"complete_trade": "完整交易", "holding_trade": "持仓中"}.get(review_type, review_type)

            lines.append(
                f"{code_str} {name_str} | {type_label} | 盈亏: {pnl_str} | {score_str} | {status} | {created}"
            )
            lines.append(f"  复盘ID: {review_id}")

        return "\n".join(lines)
    except Exception as e:
        logger.exception("[list_trade_reviews] Failed to obtain review history: %s", e)
        return f"获取复盘历史时出错: {e}"


@tool
@register_tool(
    tool_id="get_trade_review_detail",
    name="获取复盘报告详情",
    description="Get a complete report of a transaction review based on the review ID, including AI evaluation, ratings, improvement suggestions, etc.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["trade_review", "review", "detail", "report", "query", "assistant_ops", "review_detail", "ai_review", "review_report", "trade_analysis", "review_suggestions"],
    tool_role_hint="primary",
    output_shape="report",
    preferred_for=["复盘报告详情", "查看复盘结果", "AI评价查看", "复盘改进建议"],
    when_to_use="When the user wants to view the complete report details of a certain transaction review, obtain AI evaluation and improvement suggestions, the review ID needs to be provided.",
    returns="Returns the formatted review report text, including basic information, comprehensive score, summary, advantages, shortcomings and specific suggestions.",
)
async def get_trade_review_detail(
    review_id: Annotated[str, "Review ID, obtained from the review history list"],
) -> str:
    """Get the complete report details of the specified review ID."""
    try:
        from app.services.trade_review_service import get_trade_review_service

        user_id = require_current_user_id()
        service = get_trade_review_service()
        report = await service.get_review_detail(user_id, review_id)

        if not report:
            return f"未找到复盘报告（ID: {review_id}）。请检查 ID 是否正确。"

        lines = []
        trade_info = report.trade_info
        ai_review = report.ai_review

        # Basic information
        code = trade_info.code if trade_info else ""
        name = trade_info.name if trade_info and trade_info.name else ""
        lines.append(f"{name}({code}) 交易复盘报告")
        lines.append(f"复盘类型: {report.review_type} | 状态: {report.status}")

        if trade_info:
            pnl = trade_info.realized_pnl
            if pnl is not None:
                lines.append(f"已实现盈亏: {pnl:+.2f}")
            if trade_info.is_holding:
                lines.append("当前状态: 持仓中")

        # AI Evaluation
        if ai_review:
            if hasattr(ai_review, "overall_score") and ai_review.overall_score:
                lines.append(f"\n综合评分: {ai_review.overall_score}/100")
            if hasattr(ai_review, "summary") and ai_review.summary:
                lines.append(f"\n总结:\n{ai_review.summary}")
            if hasattr(ai_review, "strengths") and ai_review.strengths:
                lines.append("\n做得好的地方:")
                for s in ai_review.strengths:
                    lines.append(f"  ✅ {s}")
            if hasattr(ai_review, "weaknesses") and ai_review.weaknesses:
                lines.append("\n需要改进:")
                for w in ai_review.weaknesses:
                    lines.append(f"  ⚠️ {w}")
            if hasattr(ai_review, "suggestions") and ai_review.suggestions:
                lines.append("\n具体建议:")
                for sg in ai_review.suggestions:
                    lines.append(f"  💡 {sg}")

        created = report.created_at
        if created:
            ts = created.strftime("%Y-%m-%d %H:%M") if hasattr(created, "strftime") else str(created)[:16]
            lines.append(f"\n报告时间: {ts}")

        return "\n".join(lines)
    except Exception as e:
        logger.exception("[get_trade_review_detail] Failed to obtain review report: %s", e)
        return f"获取复盘报告时出错: {e}"


@tool
@register_tool(
    tool_id="trigger_trade_review",
    name="发起交易复盘",
    description="Initiate a new AI review analysis task for the specified transaction record. A list of transaction IDs is required (can be obtained from position change records or simulated transaction records). Asynchronous execution in the background (about 1-3 minutes), generating AI evaluations, ratings and improvement suggestions.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["trade_review", "review", "trigger", "create", "assistant_ops", "ai_review", "review_task", "trade_analysis", "backtesting", "async_task", "review_creation"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["发起交易复盘", "创建复盘任务", "AI交易分析", "交易记录复盘"],
    when_to_use="It is used when the user wants to initiate a new AI review analysis task for the specified transaction record, obtain transaction evaluation and improvement suggestions.",
    returns="Returns a text message, including task ID, number of transactions, data source and estimated completion time, and is executed asynchronously in the background.",
)
async def trigger_trade_review(
    trade_ids: Annotated[str, "Transaction ID to be reviewed, separate multiples with commas"],
    code: Annotated[Optional[str], "Stock code, such as 600519. Leave blank to automatically infer from transaction records"] = None,
    source: Annotated[str, "Data source:paper=simulated trading, position=Position operation"] = "paper",
) -> str:
    """Initiate a new AI review analysis on the specified transaction record, execute it asynchronously in the background, and return the task ID."""
    try:
        from app.services.unified_analysis_service import get_unified_analysis_service
        from app.models.review import CreateTradeReviewRequest

        user_id = require_current_user_id()
        id_list = [tid.strip() for tid in trade_ids.split(",") if tid.strip()]
        if not id_list:
            return "❌ Please provide at least one transaction ID."

        logger.info("[trigger_trade_review] Start creating a review task: trade_ids=%s, code=%s, user_id=%s", id_list, code, user_id)

        request = CreateTradeReviewRequest(
            trade_ids=id_list,
            code=code,
            source=source,
        )

        unified_service = get_unified_analysis_service()
        result = await unified_service.create_trade_review_task(
            user_id=user_id,
            request=request,
        )
        task_id = result["task_id"]
        logger.info("[trigger_trade_review] ✅ Task has been created: task_id=%s", task_id)

        # Background execution, no blocking
        bg_task = asyncio.create_task(
            unified_service.execute_trade_review(
                task_id=task_id,
                user_id=user_id,
                request=request,
            )
        )
        bg_task.add_done_callback(
            lambda t: logger.error("[trigger_trade_review] ❌ Background execution exception: %s", t.exception())
            if not t.cancelled() and t.exception() else None
        )

        code_str = f"（{code}）" if code else ""
        source_label = "模拟交易" if source == "paper" else "持仓操作"
        return (
            f"✅ 交易复盘任务已创建\n"
            f"- Task ID: {task_id}\n"
            f"- Number of transactions: {len(id_list)}{code_str}\n"
            f"- Data source: {source_label}\n"
            f"- It is expected to take 1-3 minutes to complete. At that time, you can use Get review report details to view the results."
        )
    except Exception as e:
        logger.exception("[trigger_trade_review] ❌ Failed to create task: %s", e)
        return f"❌ Failed to create transaction review task: {e}"


# === user_activity ===
"""Use the Q&A robot tool: query the user s recent tasks and error logs.

Provides the ability to query the user s recent N tasks, failed task error information, etc.
Allows using Q&A Assistant to"see"The true status of the user s recent operations for easy troubleshooting"Why is the error reported?""Where did the mission go?"etc. questions.
"""

import logging
from datetime import datetime
from typing import Annotated, Any, Dict, List

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _user_activity_is_valid_object_id(user_id: str) -> bool:
    if not user_id or not isinstance(user_id, str):
        return False
    try:
        from bson import ObjectId
        ObjectId(user_id)
        return len(user_id) == 24
    except Exception:
        return False


async def _query_recent_tasks(db, user_id: str, limit: int) -> List[Dict[str, Any]]:
    """Query the user s recent tasks (compatible with ObjectId and string user_id)"""
    queries = [{"user_id": user_id}]
    if _user_activity_is_valid_object_id(user_id):
        from bson import ObjectId
        queries.append({"user_id": ObjectId(user_id)})

    for query in queries:
        try:
            cursor = db.unified_analysis_tasks.find(
                query,
                {
                    "task_id": 1, "task_type": 1, "status": 1, "task_params": 1,
                    "created_at": 1, "started_at": 1, "completed_at": 1,
                    "execution_time": 1, "error_message": 1, "current_step": 1,
                }
            ).sort("created_at", -1).limit(limit)
            docs = await cursor.to_list(length=limit)
            if docs:
                return docs
        except Exception as exc:
            logger.warning("[get_user_recent_activity] Query failed query=%s: %s", query, exc)
    return []


def _format_task_line(t: Dict[str, Any]) -> str:
    """格式化单条任务"""
    params = t.get("task_params") or {}
    symbol = params.get("symbol") or params.get("stock_code") or params.get("analysis_target") or "?"
    status = t.get("status", "?")
    task_type = t.get("task_type", "?")
    task_id = t.get("task_id", "?")

    # time field
    created = t.get("created_at")
    started = t.get("started_at")
    completed = t.get("completed_at")
    created_str = created.isoformat()[:19] if isinstance(created, datetime) else (str(created)[:19] if created else "?")
    completed_str = completed.isoformat()[:19] if isinstance(completed, datetime) else (str(completed)[:19] if completed else "")

    # Execution time
    exec_time = t.get("execution_time") or 0
    exec_hint = f" | 耗时 {exec_time:.1f}s" if isinstance(exec_time, (int, float)) and exec_time > 0 else ""

    # error message
    error_hint = ""
    if status == "failed":
        err_msg = (t.get("error_message") or "无错误信息")[:200]
        error_hint = f"\n      ❌ 错误: {err_msg}"

    # Progress
    progress_hint = ""
    if status == "running" and t.get("current_step"):
        progress_hint = f" | 当前步骤: {t['current_step']}"

    completed_part = f" | 完成于 {completed_str}" if completed_str else ""
    return f"  • [{task_type}] {symbol} | {status}{progress_hint}{exec_hint}{completed_part} | 创建于 {created_str} | task_id={task_id}{error_hint}"


@tool
@register_tool(
    tool_id="get_user_recent_activity",
    name="获取用户最近活动",
    description="Query the execution status of the most recent N tasks (default 10) of the current user, including status, time consumption, and error information. When the user asks'Where did my mission go?''Why the task failed''What was executed recently'Use it when you have questions.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "user_activity", "recent_tasks", "error_log", "task_history"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["最近任务执行情况", "为什么任务失败", "任务去哪了", "排查报错"],
    when_to_use="Used when users ask about their recent task execution status, error reasons, or task history.",
    returns="Returns a list of recent tasks in text format, including task type, goal, status, time taken, and error information.",
)
async def get_user_recent_activity(
    limit: Annotated[int, "Return the most recent N tasks, default 10, maximum 30"] = 10,
) -> str:
    """Get the current user s recent task execution records."""
    from app.core.database import get_mongo_db

    if limit < 1:
        limit = 1
    if limit > 30:
        limit = 30

    user_id = require_current_user_id()
    db = get_mongo_db()

    tasks = await _query_recent_tasks(db, user_id, limit)

    if not tasks:
        return f"📭 There are no recent task records (queried {limit} Article upper limit,user_id={user_id}) . Possible reasons:\n  - You have not initiated any analysis tasks yet\n  - Database connection exception\n  - user_id Fields do not match (try Ctrl+F5 Refresh the page)"

    failed_count = sum(1 for t in tasks if t.get("status") == "failed")
    success_count = sum(1 for t in tasks if t.get("status") == "completed")
    running_count = sum(1 for t in tasks if t.get("status") == "running")
    pending_count = sum(1 for t in tasks if t.get("status") == "pending")

    lines = [
        f"📋 最近 {len(tasks)} 条任务（成功 {success_count} | 失败 {failed_count} | 运行中 {running_count} | 排队 {pending_count}）",
        "",
    ]
    for t in tasks:
        lines.append(_format_task_line(t))

    if failed_count > 0:
        lines.append("")
        lines.append(f"💡 失败任务 {failed_count} 条，请查看上方每条任务的错误信息。常见原因：")
        lines.append("  - Data source token is not configured or invalid")
        lines.append("  - LLM Call timeout or insufficient quota")
        lines.append("  - Stock code error or data does not exist")

    return "\n".join(lines)

# === user_state ===
"""Use the Q&A robot tool: query the user s current status.

Provides the ability to query the current user s watch list stocks, historical tasks, recent tasks, scheduled analysis configurations, etc.
Allows using Q&A Assistant to"see"The user s current status, rather than guessing the answer based on the FAQ.
"""

import logging
from datetime import datetime
from typing import Annotated, Any, Dict, List

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


def _user_state_is_valid_object_id(user_id: str) -> bool:
    if not user_id or not isinstance(user_id, str):
        return False
    try:
        from bson import ObjectId
        ObjectId(user_id)
        return len(user_id) == 24
    except Exception:
        return False


async def _count_user_favorites(db, user_id: str) -> tuple[int, List[Dict[str, Any]]]:
    """Return (Number of stocks on watch list, Top 5 stock names)"""
    try:
        if _user_state_is_valid_object_id(user_id):
            from bson import ObjectId
            user = await db.users.find_one({"_id": ObjectId(user_id)}, {"favorite_stocks": 1})
            if user is None:
                user = await db.users.find_one({"_id": user_id}, {"favorite_stocks": 1})
            favorites = (user or {}).get("favorite_stocks", []) or []
        else:
            doc = await db.user_favorites.find_one({"user_id": user_id}, {"favorites": 1})
            favorites = (doc or {}).get("favorites", []) or []

        count = len(favorites)
        preview = [
            f"{f.get('stock_name', '?')}({f.get('stock_code', '?')})"
            for f in favorites[:5]
        ]
        return count, preview
    except Exception as exc:
        logger.warning("[get_user_current_state] Failed to query watchlist: %s", exc)
        return -1, []


async def _count_user_tasks(db, user_id: str) -> tuple[int, int, List[Dict[str, Any]]]:
    """Return (total number of tasks, Number of failed tasks, Summary of the last 5 tasks)"""
    try:
        # unified_analysis_tasks The collection user_id may be a string or ObjectId
        query: Dict[str, Any] = {"user_id": user_id}
        total = await db.unified_analysis_tasks.count_documents(query)
        if total == 0 and _user_state_is_valid_object_id(user_id):
            from bson import ObjectId
            total = await db.unified_analysis_tasks.count_documents({"user_id": ObjectId(user_id)})

        recent_cursor = db.unified_analysis_tasks.find(
            query, {"status": 1, "task_params": 1, "created_at": 1, "task_type": 1, "error_message": 1}
        ).sort("created_at", -1).limit(5)
        recent = await recent_cursor.to_list(length=5)

        if not recent and _user_state_is_valid_object_id(user_id):
            from bson import ObjectId
            recent_cursor2 = db.unified_analysis_tasks.find(
                {"user_id": ObjectId(user_id)},
                {"status": 1, "task_params": 1, "created_at": 1, "task_type": 1, "error_message": 1}
            ).sort("created_at", -1).limit(5)
            recent = await recent_cursor2.to_list(length=5)
            if total == 0:
                total = await db.unified_analysis_tasks.count_documents({"user_id": ObjectId(user_id)})

        failed = sum(1 for t in recent if t.get("status") == "failed")
        preview = []
        for t in recent:
            params = t.get("task_params") or {}
            symbol = params.get("symbol") or params.get("stock_code") or "?"
            status = t.get("status", "?")
            created = t.get("created_at")
            created_str = created.isoformat()[:19] if isinstance(created, datetime) else (str(created)[:19] if created else "?")
            preview.append({
                "symbol": symbol,
                "status": status,
                "task_type": t.get("task_type", "?"),
                "created_at": created_str,
                "error": (t.get("error_message") or "")[:100] if status == "failed" else None,
            })
        return total, failed, preview
    except Exception as exc:
        logger.warning("[get_user_current_state] Query task failed: %s", exc)
        return -1, 0, []


async def _count_scheduled(db, user_id: str) -> int:
    """Returns the number of enabled scheduled analysis configurations"""
    try:
        count = await db.scheduled_analysis_configs.count_documents({"user_id": user_id, "enabled": True})
        return count
    except Exception as exc:
        logger.warning("[get_user_current_state] Query timing analysis configuration failed: %s", exc)
        return -1


@tool
@register_tool(
    tool_id="get_user_current_state",
    name="获取用户当前状态",
    description="Query the number of stocks in the current user s watch list, the total number of historical tasks, the execution status of recent tasks, and the number of scheduled analysis configurations. When the user asks'where is my mission''How many stocks are on the watch list?''Why is today s task 0'Use it when you have questions.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "user_state", "favorites_count", "task_count", "recent_tasks", "scheduled_analysis"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["查询关注列表数量", "查看任务总数", "今日任务为什么是0", "最近任务执行情况"],
    when_to_use="Used when the user asks about his current status (number of watch lists/number of tasks/scheduled analysis configuration).",
    returns="Returns a user status summary in text format, including the number of watch list stocks, total number of tasks, number of failed tasks, the last 5 tasks and the number of scheduled analysis configurations.",
)
async def get_user_current_state() -> str:
    """Get a summary of the current user s system status."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()

    fav_count, fav_preview = await _count_user_favorites(db, user_id)
    task_total, task_failed, task_recent = await _count_user_tasks(db, user_id)
    scheduled_count = await _count_scheduled(db, user_id)

    lines = ["📊 用户当前状态"]
    if fav_count >= 0:
        lines.append(f"- 关注列表股票数: {fav_count}")
        if fav_preview:
            lines.append(f"  前 5 只: {', '.join(fav_preview)}")
    else:
        lines.append("- Number of stocks on watch list: Query failed")

    if task_total >= 0:
        lines.append(f"- 历史任务总数: {task_total}")
        lines.append(f"- Number of failures in the last 5 tasks: {task_failed}")
        for t in task_recent:
            err_hint = f" ❌错误: {t['error']}" if t.get("error") else ""
            lines.append(f"  • {t['symbol']} | {t['task_type']} | {t['status']} | {t['created_at']}{err_hint}")
    else:
        lines.append("- 历史任务: 查询失败")

    if scheduled_count >= 0:
        lines.append(f"- Enabling scheduled analysis configuration: {scheduled_count}")
    else:
        lines.append("- Timing analysis configuration: Query failed")

    return "\n".join(lines)

# === watchlist_manager ===
"""
Stock watch list management tools

Provides functions for querying, adding stocks, and removing stocks grouped by stock watchlists.
User identity is obtained through core.tools.context.
"""

import logging
from typing import Annotated

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="list_watchlist_groups",
    name="查看股票关注列表分组",
    description="Lists the user s stock watchlist groups, showing the group name, stock number, and stock symbol preview. Note: This is a grouped view, which is not equal to the complete stock watch list itself, nor is it equal to the scheduled analysis configuration.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["watchlist", "group", "list", "query", "assistant_ops", "stock_group", "watchlist_group", "stock_watchlist", "portfolio_group", "self_selected", "watchlist_query"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["查看股票关注列表分组", "股票关注列表列表", "分组查询", "股票池查看"],
    when_to_use="Used when users want to view their own stock watch list group list and understand which stocks are included in each group.",
    returns="Returns a grouped list of stock watchlists in text format, each containing group ID, name, stock number and stock code preview.",
)
async def list_watchlist_groups() -> str:
    """Lists the current user s stock watch list groups and the number of stocks in each group."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()

    cursor = db.watchlist_groups.find({"user_id": user_id}).sort("sort_order", 1)

    groups = []
    async for doc in cursor:
        gid = str(doc["_id"])
        name = doc.get("name", "未命名")
        stocks = doc.get("stock_codes", [])
        active = "✅" if doc.get("is_active", True) else "⏸️"
        preview = ", ".join(stocks[:5])
        if len(stocks) > 5:
            preview += f" +{len(stocks) - 5}"
        groups.append(f"  {active} [{gid[:8]}] {name}（{len(stocks)}只）: {preview}")

    if not groups:
        return "📂 There is currently no stock watch list grouping. You can ask me to create one for you.\n\n Tip: Grouping is just a way of organizing; to see the full stock watchlist, use View stock watchlist . "
    return (
        f"📂 共 {len(groups)} 个股票关注列表分组：\n"
        + "\n".join(groups)
        + "\n\n Note: The above is the group view of your stock watch list, which is not equal to the complete stock watch list, nor is it equal to the scheduled analysis configuration."
        + "To see the full list of stocks to watch, call View stock watchlist ; To view the automated analysis schedule, call View scheduled analysis configuration . "
    )


@tool
@register_tool(
    tool_id="add_stock_to_watchlist",
    name="Add a stock to a stock watchlist group",
    description="Adds one or more stocks to the specified named Stock Watchlist group. Automatically create a new group if the group does not exist. Note: This is only group management and does not mean that it will automatically enter scheduled analysis.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["watchlist", "group", "add", "stock", "assistant_ops", "stock_add", "watchlist_add", "portfolio_management", "self_selected", "stock_code", "watchlist_management"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["添加股票关注列表", "加入股票分组", "股票关注列表管理", "新建股票分组"],
    when_to_use="This is used when the user wants to add one or more stocks to a stock watch list group, or needs to create a new group and add stocks.",
    returns="Returns a text message, prompting the number of new stocks and the total number of current stocks in the group; when creating a new group, returns the group creation result.",
)
async def add_stock_to_watchlist(
    group_name: Annotated[str, "Stock watch list group name, such as Technology stocks "],
    symbols: Annotated[str, "Stock codes to add, separated by commas, such as 000001,600519"],
) -> str:
    """Adds one or more stocks to the specified named Stock Watchlist group. The group is automatically created if it does not exist."""
    from app.core.database import get_mongo_db
    from app.utils.timezone import now_tz

    user_id = require_current_user_id()
    db = get_mongo_db()

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return "❌ Please provide at least one ticker symbol."

    # Find groups by name
    group = await db.watchlist_groups.find_one({"user_id": user_id, "name": group_name})

    if group:
        # Already grouped, add stocks (remove duplicates)
        current = set(group.get("stock_codes", []))
        new_codes = set(symbol_list) - current
        if not new_codes:
            return f"ℹ️ 这些股票已在分组「{group_name}」中，无需重复添加。"
        updated = list(current | set(symbol_list))
        await db.watchlist_groups.update_one(
            {"_id": group["_id"]},
            {"$set": {"stock_codes": updated, "updated_at": now_tz()}},
        )
        return (
            f"✅ 已添加 {len(new_codes)} 只股票到「{group_name}」\n"
            f"- New: {', '.join(sorted(new_codes))}\n"
            f"- The group currently has a total of {len(updated)} only stocks"
        )
    else:
        # Automatically create groups
        max_sort_doc = await db.watchlist_groups.find_one(
            {"user_id": user_id}, sort=[("sort_order", -1)]
        )
        next_sort = (max_sort_doc["sort_order"] + 1) if max_sort_doc else 0

        new_doc = {
            "user_id": user_id,
            "name": group_name,
            "description": "",
            "color": "#409EFF",
            "icon": "folder",
            "stock_codes": symbol_list,
            "analysis_depth": None,
            "quick_analysis_model": None,
            "deep_analysis_model": None,
            "prompt_template_id": None,
            "sort_order": next_sort,
            "is_active": True,
            "created_at": now_tz(),
            "updated_at": now_tz(),
        }
        await db.watchlist_groups.insert_one(new_doc)
        return (
            f"✅ 已自动创建分组「{group_name}」并添加 {len(symbol_list)} 只股票\n"
            f"- stocks: {', '.join(symbol_list)}"
        )


@tool
@register_tool(
    tool_id="remove_stock_from_watchlist",
    name="Remove a stock from a stock watchlist group",
    description="Removes one or more stocks from the specified stock watchlist grouping. The group itself will not be deleted, nor will existing scheduled analysis configurations be affected.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["watchlist", "group", "remove", "stock", "assistant_ops", "stock_remove", "watchlist_remove", "portfolio_management", "self_selected", "stock_delete", "watchlist_management"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["移除股票关注列表", "删除股票分组中的股票", "股票关注列表管理", "清理股票池"],
    when_to_use="Used when the user wants to remove one or more stocks from the stock watch list group and clear out stocks that are no longer followed.",
    returns="Returns a text message indicating the number of shares to remove and the number of shares remaining in the group.",
)
async def remove_stock_from_watchlist(
    group_name: Annotated[str, "股票关注列表分组名称"],
    symbols: Annotated[str, "Stock symbols to remove, comma separated"],
) -> str:
    """Removes one or more stocks from the specified stock watchlist grouping."""
    from app.core.database import get_mongo_db
    from app.utils.timezone import now_tz

    user_id = require_current_user_id()
    db = get_mongo_db()

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return "❌ Please provide at least one ticker symbol."

    group = await db.watchlist_groups.find_one({"user_id": user_id, "name": group_name})
    if not group:
        return f"❌ 未找到分组「{group_name}」。可以用「查看股票关注列表分组」查看现有分组。"

    current = set(group.get("stock_codes", []))
    to_remove = set(symbol_list) & current
    if not to_remove:
        return f"ℹ️ 这些股票不在分组「{group_name}」中。"

    remaining = list(current - to_remove)
    await db.watchlist_groups.update_one(
        {"_id": group["_id"]},
        {"$set": {"stock_codes": remaining, "updated_at": now_tz()}},
    )
    return (
        f"✅ 已从「{group_name}」移除 {len(to_remove)} 只股票\n"
        f"- Remove: {', '.join(sorted(to_remove))}\n"
        f"- Group remaining {len(remaining)} only stocks"
    )


# === web_search ===
"""Web Search Tool - Based on SearXNG meta-search engine, supporting Baidu/Bing crawler alternatives."""

import logging
import os
import random
import re
import time
from typing import Annotated, Optional
from urllib.parse import quote, unquote, urlencode, urlparse

import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30  # SearXNG takes longer

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

# SearXNG Engine rotation order (quality first).
# Note: don't let go bing——Bing The Chinese version will downgrade long Chinese queries to single-word matching.
# Return"race"Dictionary pages and other irrelevant results, filtering them will waste context tokens.
SEARXNG_ENGINE_ORDER = ["baidu", "sogou", "360so"]

# Engine fuse status: engine name -> Cooldown expiration timestamp.
# If the engine is continuously queried, it will trigger the anti-crawling CAPTCHA and be suspended by SearXNG (actual measurement of LLM round of dialogue)
# Triggered after 8 searches), the engine returns 0 results after suspending. Here is the circuit breaker on the client side:
# After an engine has no valid results, it will no longer be preferred within 5 minutes and will be automatically rotated to the next engine.
_engine_cooldown: dict = {}

# Minimum interval (seconds) between two SearXNG requests to reduce the probability of triggering anti-crawling
_SEARXNG_MIN_INTERVAL = 1.2
_last_searxng_ts = 0.0

# Financial website domain name priority (the higher the score, the priority)
FINANCE_DOMAINS = {
    # Official website (highest priority)
    "seres.cn": 100,
    "byd.com": 100,
    # Juchao Information (Official Announcement Platform)
    "cninfo.com.cn": 95,
    # Mainstream financial media
    "eastmoney.com": 90,
    "finance.sina.com.cn": 85,
    "10jqka.com.cn": 85,
    "stcn.com": 80,
    "cs.com.cn": 80,
    "cnstock.com": 80,
    "money.163.com": 75,
    "163.com": 70,
    "finance.qq.com": 75,
    "finance.ifeng.com": 75,
    "hexun.com": 70,
    "finance.people.com.cn": 70,
    # Passenger Car Association/Automobile Industry Association (authoritative source of sales data)
    "cpcaauto.com": 95,
    "caam.org.cn": 95,
}

# overall situation Session
_baidu_session: Optional[requests.Session] = None


def _get_domain_score(url: str) -> int:
    """Returns a financial priority score based on the URL domain."""
    try:
        domain = urlparse(url).netloc.lower()
        for fin_domain, score in FINANCE_DOMAINS.items():
            if fin_domain in domain:
                return score
    except Exception:
        pass
    return 0


def _sort_by_finance_priority(results: list[dict]) -> list[dict]:
    """Sort search results by financial website priority."""
    return sorted(results, key=lambda r: _get_domain_score(r.get("url", "")), reverse=True)


def _query_key_terms(query: str) -> list:
    """Extract the core words in the query (remove the year/number/quantifier/word for relevance filtering).

    Example:"Thalys June 2026 Production and Sales Report Sales Volume Units" -> ["Thalys", "Production and Sales Express", "Sales volume"]
    """
    tokens = re.split(r"[\s,，、/·\"']+", query.strip())
    terms = []
    for tok in tokens:
        # Remove pure numbers, year and month, percentages, and common quantifiers
        cleaned = re.sub(r"^\d{4}year?\d{0,2}month?\d{0,2}day?$|^\d+%?$|^\d+$", "", tok)
        if len(cleaned) >= 2:
            terms.append(cleaned)
    return terms


def _filter_irrelevant_results(query: str, results: list) -> list:
    """Filter junk results that have zero relevance to the query.

    Background: Bing China version will downgrade long Chinese queries to single word matching and return"race"word dictionary,
    Irrelevant pages such as Chinese dictionary pollute the LLM context. Filtering rules: Result title (including decoded URL)
    Contain at least one core word, otherwise discard.
    """
    terms = _query_key_terms(query)
    if not terms:
        return results  # Unable to extract core words (such as pure code query), no filtering

    kept = []
    for r in results:
        text = (r.get("title", "") or "") + " " + unquote(r.get("url", "") or "")
        if any(t in text for t in terms):
            kept.append(r)
    dropped = len(results) - len(kept)
    if dropped:
        logger.info("Spam result filtering: Discarding %d results with zero relevance to the query", dropped)
    return kept


def _search_searxng(
    instance_url: str, query: str, language: str, max_results: int
) -> list:
    """Search by SearXNG instance (engine rotation + fuse + relevance filtering).

    No longer run all engines concurrently (which will trigger the anti-crawling CAPTCHA of multiple engines at the same time),
    Instead, they are tried one by one in order of quality: an engine stops when it returns a valid result;
    Engines with no valid results will enter a 5-minute cooling period, and subsequent searches will be automatically rotated.
    """
    global _last_searxng_ts

    # Global throttling: two SearXNG requests are separated by at least _SEARXNG_MIN_INTERVAL seconds
    wait = _SEARXNG_MIN_INTERVAL - (time.time() - _last_searxng_ts)
    if wait > 0:
        time.sleep(wait)
    _last_searxng_ts = time.time()

    now = time.time()
    # Available engines are placed first (after cooling), maintaining quality order with the same priority.
    engines = sorted(
        SEARXNG_ENGINE_ORDER,
        key=lambda e: (_engine_cooldown.get(e, 0) > now, SEARXNG_ENGINE_ORDER.index(e)),
    )
    logger.info("SearXNG Engine order: %s (cooling: %s) ", engines, {
        e: f"{_engine_cooldown[e] - now:.0f}s" for e in _engine_cooldown if _engine_cooldown[e] > now
    } or "无")

    for engine in engines:
        params = {
            "q": query,
            "format": "json",
            "language": language,
            "safesearch": 0,
            "categories": "general",
            "engines": engine,
            "timeout": 6,
        }
        full_url = f"{instance_url.rstrip('/')}/search?{urlencode(params)}"
        try:
            resp = requests.get(
                full_url,
                headers={
                    "User-Agent": random.choice(USER_AGENTS),
                    "Accept": "application/json",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("SearXNG Engine %s query failed: %s", engine, exc)
            _engine_cooldown[engine] = time.time() + 300
            continue

        raw = data.get("results") or []
        unresponsive = [u[0] for u in (data.get("unresponsive_engines") or [])]
        if engine in unresponsive:
            logger.warning("SearXNG Engine %s has been suspended (anti-climb/timeout), cool down for 5 minutes", engine)
            _engine_cooldown[engine] = time.time() + 300
            continue

        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "engine": item.get("engine", engine),
                "published_date": item.get("publishedDate", ""),
            }
            for item in raw[: max_results * 2]
        ]
        results = _filter_irrelevant_results(query, results)
        if not results:
            logger.warning(
                "SearXNG Engine %s has no valid results (original %d bars), cool down for 5 minutes", engine, len(raw)
            )
            _engine_cooldown[engine] = time.time() + 300
            continue

        results = _sort_by_finance_priority(results)
        logger.info("SearXNG Hit engine %s: %d valid results", engine, len(results))
        return results[:max_results]

    return []


def _get_baidu_session() -> requests.Session:
    """Get Baidu Search Session."""
    global _baidu_session
    if _baidu_session is None or not _baidu_session.cookies:
        _baidu_session = requests.Session()
        _baidu_session.headers.update(
            {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://www.baidu.com/",
            }
        )
        try:
            _baidu_session.get("https://www.baidu.com/", timeout=DEFAULT_TIMEOUT)
        except Exception:
            pass
    return _baidu_session


def _search_baidu(query: str, max_results: int) -> list[dict]:
    """Crawling results through Baidu search."""
    session = _get_baidu_session()
    resp = session.get(
        "https://www.baidu.com/s",
        params={"wd": query, "rn": max_results, "ie": "utf-8"},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    results = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "baidu.com/link" not in href and "baidu.php" not in href:
            continue
        title = a.get_text(strip=True)
        if not title or len(title) < 5:
            continue
        snippet = ""
        h3 = a.find_parent("h3")
        container = h3.parent.parent if h3 and h3.parent else a.parent
        if container:
            for el in container.find_all(["span", "div", "p"]):
                text = el.get_text(strip=True)
                if len(text) > 30 and text != title and title not in text:
                    snippet = text[:300]
                    break
        results.append({"title": title, "url": href, "content": snippet, "engine": "baidu"})
        if len(results) >= max_results:
            break
    return results


def _format_results(query: str, results: list[dict], engine_used: str) -> str:
    """Format search results into LLM-friendly text."""
    if not results:
        return f"未找到与「{query}」相关的搜索结果。"

    lines = [
        f"Web Search results:{query}",
        f"Search engine:{engine_used}",
        f"共 {len(results)} 条结果\n",
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"--- 结果 {i} ---")
        lines.append(f"Title:{r['title']}")
        if r.get("published_date"):
            lines.append(f"Release date:{r['published_date']}")
        lines.append(f"Links:{r['url']}")
        if r["content"]:
            lines.append(f"Summary:{r['content'][:300]}")
        lines.append("")
    return "\n".join(lines)


def run_web_search(
    query: str,
    language: str = "zh",
    max_results: int = 10,
) -> str:
    """Perform a web search."""
    query_clean = (query or "").strip()
    if not query_clean:
        return "Please provide search keywords."

    errors = []

    # 1) SearXNG (Priority, only use domestic engines)
    searxng_instances = os.getenv("SEARXNG_INSTANCES", "").strip()
    if searxng_instances:
        for instance_url in searxng_instances.split(","):
            instance_url = instance_url.strip()
            if not instance_url:
                continue
            try:
                logger.info("SearXNG Search: %s | query=%s", instance_url, query_clean)
                results = _search_searxng(instance_url, query_clean, language, max_results)
                if results:
                    return _format_results(query_clean, results, f"SearXNG({instance_url})")
            except Exception as exc:
                logger.warning("SearXNG %s failed: %s", instance_url, exc)
                errors.append(f"searxng: {exc}")

    # 2) Baidu search (optional)
    try:
        logger.info("Baidu search: query=%s", query_clean)
        results = _search_baidu(query_clean, max_results)
        if results:
            return _format_results(query_clean, results, "百度")
    except Exception as exc:
        logger.warning("百度搜索失败: %s", exc)
        errors.append(f"baidu: {exc}")

    return f"Web Search failed, all search engines are unavailable. Error details:{'; '.join(errors)}"


@tool
@register_tool(
    tool_id="web_search",
    name="Web 搜索",
    description="Search Internet information through SearXNG meta-search engine (Baidu/360/Sogou/Bing China version engine aggregation). Automatically prioritize results from financial websites (Oriental Fortune, Sina Finance, Juchao Information, etc.). Suitable for obtaining real-time data that is not included in financial reports, such as monthly sales, latest announcements, industry news, etc.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    data_source_handling="local_only",
    capability_tags=[
        "web_search", "internet_search", "online_search", "information_search",
        "real_time_info", "current_events", "news_query", "fact_check",
        "market_information", "search_engine", "finance_data",
    ],
    tool_role_hint="specialized",
    output_shape="report",
    preferred_for=[
        "搜索互联网实时信息",
        "Obtain operating data outside of financial reports (such as monthly sales)",
        "查询最新新闻和公告",
        "事实核查和背景调研",
    ],
    when_to_use="Use it when you need to search the Internet to obtain the latest information, especially real-time data not covered in financial reports (monthly sales, industry trends, latest news, etc.).",
    returns="Return structured search results, including titles, links, and abstracts. Automatically prioritize financial websites and aggregate Baidu/360/Sogou/Bing China version engine results.",
)
def web_search(
    query: Annotated[str, "Search keywords, for example: Cyrus July 2025 sales, or BYD latest monthly sales"],
    max_results: Annotated[int, "Maximum number of results returned, default 10"] = 10,
) -> str:
    """Search Internet information and aggregate the results of multiple search engines, giving priority to financial websites."""
    return run_web_search(query=query, max_results=max_results)

