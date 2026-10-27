"""Nanobot Friendly agent design and resource reconnaissance tool."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Annotated, Any

from langchain_core.tools import tool

from app.core.database import get_mongo_db
from app.core.database import get_mongo_db_sync
from app.models.capability_index import CapabilitySearchHit
try:
    from app.pro.models.agent_workshop import AgentSpec, AgentSpecIOField, AgentSpecStatus
    from app.pro.models.prompt_template import TemplateContent
    from app.pro.services.agent_workshop_service import AgentWorkshopService
except ImportError:  # The community version does not have the Agent Workshop module (manifest removed), and this tool chain is disabled in the community version.
    AgentSpec = AgentSpecIOField = AgentSpecStatus = None  # type: ignore[assignment,misc]
    TemplateContent = None  # type: ignore[assignment,misc]
    AgentWorkshopService = None  # type: ignore[assignment,misc]
from core.agents.factory import AgentFactory
from core.config.binding_manager import BindingManager
from app.services.capability_index_service import CapabilityIndexService
from core.agents.registry import get_registry
from core.tools import get_tool_registry
from core.tools.base import register_tool
from core.tools.context import get_current_assistant_thread_context, get_current_assistant_thread_id, require_current_user_id

logger = logging.getLogger(__name__)

_DEFAULT_CALLABLE_SURFACES = ["assistant", "workflow", "agent"]
_GLOBAL_NO_TRADING_ADVICE_POLICY = (
    "Global iron law: All Agents are prohibited from outputting any trading recommendations, buying and selling/holding judgments, position recommendations,"
    "Target price, stop-loss and take-profit, position range, timing conclusion and other operational instructions; only research conclusions,"
    "Key rationales, risk factors and scenario analysis."
)
_GLOBAL_NUMERICAL_TOOL_POLICY = (
    "Global iron law: All key numerical calculations must be completed through the tools or skills provided by the project."
    "LLM is prohibited from calculating itself. Including but not limited to DCF valuations, relative valuation metrics, financial ratios,"
    "Rating, ranking, weight, fair price, target price range, any precise value."
    "If the corresponding tool or skill is missing, it must be marked as a blocking gap and filled in."
    "Do not use LLM can do it yourself as a downgrade plan."
)
_GLOBAL_DATA_SOURCE_POLICY = (
    "Global iron law: Prioritize the use of data sources provided by this system (tushare, akshare, QMT, etc.)."
    "Skill If non-system data sources are used (such as directly crawling web pages, third-party APIs, own data interfaces, etc.),"
    "The source must be clearly marked in the data_source field and Skill description,"
    "It is convenient for users to judge the reliability and traceability of data."
    "Concealing or obscuring the source of data when using external data sources is prohibited."
)
_OUTPUT_PREVIEW_KEYWORDS = (
    "样式",
    "模板",
    "骨架",
    "预览",
    "输出结构",
    "字段结构",
    "章节",
    "preview",
    "style",
    "format",
    "section",
    "outline",
)
_REPORT_KEYWORDS = (
    "报告",
    "report",
    "输出",
    "result",
)


def _auto_update_intent(
    *,
    action: str = "",
    stage: str = "",
    spec_id: str = "",
    spec_name: str = "",
    intent_summary: str = "",
    active_subtask: str = "",
    next_action: str = "",
    evaluation_decision: str = "",
    evaluation_blockers: list[str] | None = None,
    evaluation_categories: list[str] | None = None,
    pending_options: list[dict[str, Any]] | None = None,
    pending_question: str = "",
    proposed_items: list[dict[str, Any]] | None = None,
    clear_pending_options: bool = False,
    task: dict[str, str] | None = None,
    linked_skill: dict[str, str] | None = None,
    conversation_summary: str = "",
) -> None:
    """Automatically updates the current thread s intent context (contextvar)."""
    try:
        from core.embedded_nanobot.intent_context import (
            update_intent_context_in_thread,
            update_evaluation_evidence_in_thread,
        )
        update_intent_context_in_thread(
            action=action,
            stage=stage,
            spec_id=spec_id,
            spec_name=spec_name,
            intent_summary=intent_summary,
            active_subtask=active_subtask,
            next_action=next_action,
            pending_options=pending_options,
            pending_question=pending_question,
            proposed_items=proposed_items,
            clear_pending_options=clear_pending_options,
            task=task,
            linked_skill=linked_skill,
            conversation_summary=conversation_summary,
        )
        if evaluation_decision or evaluation_blockers or evaluation_categories:
            update_evaluation_evidence_in_thread(
                decision=evaluation_decision,
                blockers=evaluation_blockers,
                categories=evaluation_categories,
            )
    except Exception as exc:
        logger.debug("[IntentContext][AutoUpdate] skipped: %s", exc)


def _get_collection(db: Any, name: str) -> Any:
    if db is None:
        return None
    collection = getattr(db, name, None)
    if collection is not None:
        return collection
    try:
        return db[name]
    except Exception:
        return None


def _json_response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _parse_source_types(raw: str) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_string_list(raw: str) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _dedupe_string_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _truncate_text(value: Any, max_chars: int = 1200) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def _collect_gap_job_known_context(
    gaps: list[dict[str, Any]],
    *,
    exclude_gap_id: str = "",
    max_failures: int = 5,
    max_facts: int = 12,
) -> dict[str, list[str]]:
    """Aggregate known failure summaries and verified facts within the same GapJob to avoid pitfalls in subsequent gaps."""
    failures: list[str] = []
    facts: list[str] = []
    for gap in gaps or []:
        if not isinstance(gap, dict):
            continue
        gap_id = str(gap.get("gap_id") or "").strip()
        if exclude_gap_id and gap_id == exclude_gap_id:
            continue
        summary = str(gap.get("agentic_failure_summary") or gap.get("error") or "").strip()
        if summary:
            prefix = str(gap.get("description") or gap_id or "未知缺口").strip()
            failures.append(_truncate_text(f"{prefix}: {summary}", 1000))
        for item in list(gap.get("agentic_verified_facts") or []):
            if str(item or "").strip():
                facts.append(_truncate_text(item, 800))
    return {
        "known_failure_summaries": _dedupe_string_list(failures)[:max_failures],
        "known_verified_facts": _dedupe_string_list(facts)[:max_facts],
    }


def _extract_agentic_context_from_session_doc(session_doc: dict[str, Any]) -> dict[str, Any]:
    """Extract Agentic failed experience from skill_creation_sessions."""
    result = session_doc.get("pipeline_result") or {}
    metadata = result.get("final_metadata") if isinstance(result, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    facts = metadata.get("verified_facts") if isinstance(metadata.get("verified_facts"), list) else []
    trace = metadata.get("agentic_trace") if isinstance(metadata.get("agentic_trace"), list) else []
    failure_summary = ""
    if isinstance(result, dict):
        failure_summary = str(result.get("error") or "").strip()
    if not failure_summary:
        for item in reversed(trace):
            if isinstance(item, dict) and str(item.get("failure_summary") or "").strip():
                failure_summary = str(item.get("failure_summary") or "").strip()
                break
    if not failure_summary:
        failure_summary = str(session_doc.get("pipeline_message") or "").strip()
    return {
        "failure_summary": _truncate_text(failure_summary, 2000),
        "verified_facts": _dedupe_string_list([_truncate_text(item, 800) for item in facts])[:20],
        "agentic_trace": trace[-20:] if isinstance(trace, list) else [],
        "generation_engine": str(metadata.get("generation_engine") or ""),
    }


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


def _parse_json_tool_result(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"status": "error", "message": "Tool returns not a JSON object"}
    except Exception as exc:
        return {"status": "error", "message": f"The tool return cannot be parsed as JSON: {exc}", "raw": raw}


async def _create_skill_generation_service_with_system_llm(db: Any) -> Any:
    """Create SkillGenerationService and read inference model and programming model configuration according to system settings."""
    from app.services.skill_generation_service import SkillGenerationService
    from app.services.intelligent_assistant_service import get_coding_llm_config, get_reasoning_llm_config
    from core.llm import UnifiedLLMClient

    reasoning_config = None
    coding_config = None
    try:
        reasoning_config = await get_reasoning_llm_config(db)
    except Exception as exc:
        logger.debug("[SkillGeneration][LLMConfig] Failed to read inference model configuration, use default configuration: %s", exc)
    try:
        coding_config = await get_coding_llm_config(db)
    except Exception as exc:
        logger.debug("[SkillGeneration][LLMConfig] Failed to read programming model configuration, using default configuration: %s", exc)
    reasoning_client = UnifiedLLMClient.from_config(reasoning_config) if reasoning_config else None
    coding_client = UnifiedLLMClient.from_config(coding_config) if coding_config else None
    if coding_config:
        logger.info(
            "[SkillGeneration][LLMConfig] coding provider=%s model=%s base_url=%s",
            getattr(coding_config, "provider", ""),
            getattr(coding_config, "model", ""),
            getattr(coding_config, "base_url", ""),
        )
    try:
        return SkillGenerationService(
            db=db,
            reasoning_llm_client=reasoning_client,
            coding_llm_client=coding_client,
        )
    except TypeError:
        return SkillGenerationService(db=db)


def _parse_optional_json_object(raw: str, field_name: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except Exception as exc:
        raise ValueError(f"{field_name} Not a valid JSON object: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{field_name} 必须是 JSON 对象")
    return data


def _json_compact_dump(obj: Any) -> str:
    """Compact JSON serialization, only for logging debugging."""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))
    except Exception:
        return str(obj)[:500]


_EXTERNAL_DATA_RISK_KEYWORDS = (
    "akshare",
    "tushare",
    "yfinance",
    "wind",
    "同花顺",
    "网络",
    "联网",
    "实时",
    "api",
    "http",
    "third-party",
    "第三方",
    "外部数据",
    "爬取",
    "抓取",
)


def _contains_external_data_risk(text: str) -> bool:
    lower_text = str(text or "").strip().lower()
    if not lower_text:
        return False
    return any(keyword in lower_text for keyword in _EXTERNAL_DATA_RISK_KEYWORDS)


def _is_skill_source_type(source_type: str) -> bool:
    source = str(source_type or "").strip().lower()
    return source in {"skill", "external_skill"}


_GAP_RESOLUTION_JOB_COLLECTION = "agent_workshop_gap_resolution_jobs"
_GAP_JOB_ACTIVE_STATUSES = {"pending", "running", "partial_completed"}
_GAP_JOB_TERMINAL_STATUSES = {"completed", "failed", "timeout", "cancelled"}
_GAP_ITEM_TIMEOUT_SECONDS = 1800
_GAP_JOB_CLAIM_LEASE_SECONDS = 30
_GAP_AUTO_RETRY_MAX_ATTEMPTS = 3
_GAP_AUTO_RETRY_BASE_DELAY_SECONDS = 30
_GAP_AUTO_RETRY_MAX_DELAY_SECONDS = 600


def _build_gap_resolution_job_id(seed: str) -> str:
    now_token = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    return f"gap_job_{now_token}_{digest}"


def _build_gap_resolution_idempotency_key(session_id: str, gaps: list[str]) -> str:
    normalized = "|".join(_dedupe_string_list(gaps))
    payload = f"{session_id}::{normalized}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _normalize_gap_capability_key(text: str) -> str:
    return "".join(ch for ch in str(text or "").strip().lower() if ch.isalnum())


async def _find_active_gap_skill_session(
    db: Any,
    *,
    agent_spec_id: str = "",
    workshop_session_id: str = "",
    gap_id: str = "",
    gap_description: str = "",
) -> dict[str, Any] | None:
    """Find existing active Skill generation sessions for the same Agent/same capability gap to avoid repeated generation."""
    try:
        from app.services.skill_generation_service import SESSION_COLLECTION

        collection = _get_collection(db, SESSION_COLLECTION)
        if collection is None:
            return None

        active_statuses = ["gathering", "confirmed", "generating"]
        cursor = collection.find({
            "status": {"$in": active_statuses},
            "handoff_context.source": "agent_studio_gap",
        })
        docs = await cursor.to_list(length=200)

        clean_spec_id = str(agent_spec_id or "").strip()
        clean_session_id = str(workshop_session_id or "").strip()
        clean_gap_id = str(gap_id or "").strip()
        capability_key = _normalize_gap_capability_key(gap_description)

        for doc in docs:
            ctx = dict((doc or {}).get("handoff_context") or {})
            ctx_spec_id = str(ctx.get("source_spec_id") or ctx.get("spec_id") or "").strip()
            if clean_spec_id and ctx_spec_id and ctx_spec_id != clean_spec_id:
                continue
            ctx_workshop_session_id = str(ctx.get("workshop_session_id") or "").strip()
            if clean_session_id and ctx_workshop_session_id and ctx_workshop_session_id != clean_session_id:
                continue
            ctx_gap_id = str(ctx.get("gap_id") or "").strip()
            if clean_gap_id and ctx_gap_id and ctx_gap_id == clean_gap_id:
                return dict(doc or {})
            target_key = _normalize_gap_capability_key(str(ctx.get("target_capability") or ""))
            if capability_key and target_key and capability_key == target_key:
                return dict(doc or {})
        return None
    except Exception as exc:
        logger.debug("Finding active gap skill sessions failed, ignored: %s", exc)
        return None


async def _resolve_single_gap_capability(
    *,
    db: Any,
    ws_service: Any,
    gap_description: str,
    gap_id: str,
    gap_index: int = 0,
    workshop_session_id: str = "",
    agent_spec_id: str = "",
    agent_name: str = "",
    agent_goal: str = "",
    user_id: str = "nanobot",
    allow_medium_similarity_autocreate: bool = False,
    related_gaps: list[str] | None = None,
    known_context: dict[str, list[str]] | None = None,
    handoff_intent: str = "auto_resolve_blocking_gap",
) -> dict[str, Any]:
    """Unified processing of builtin evidence, deduplication and skill generation session startup for a single gap."""
    clean_gap = str(gap_description or "").strip()
    result: dict[str, Any] = {
        "gap_index": gap_index,
        "gap_id": str(gap_id or f"gap_{gap_index + 1}").strip(),
        "gap_description": clean_gap,
        "status": "pending",
        "pipeline_stage": "",
        "pipeline_message": "",
        "dedup": {},
        "dedup_candidate": {},
        "skill_tool_id": None,
        "skill_display_name": None,
        "session_id": None,
        "error": None,
        "elapsed_seconds": 0,
    }

    if not clean_gap:
        result.update({"status": "failed", "error": "gap_description cannot be empty"})
        return result

    try:
        builtin_evidence_fn = getattr(ws_service, "_builtin_tool_evidence_for_gap", None)
        builtin_evidence = builtin_evidence_fn(clean_gap) if callable(builtin_evidence_fn) else None
        if builtin_evidence is not None:
            result.update({
                "status": "reused_existing",
                "skill_tool_id": str(builtin_evidence.get("skill_tool_id") or ""),
                "skill_display_name": str(builtin_evidence.get("skill_display_name") or builtin_evidence.get("skill_tool_id") or ""),
                "pipeline_stage": "builtin_evidence",
                "pipeline_message": str(builtin_evidence.get("reason") or "Hit the registered built-in capability and reuse it directly"),
                "dedup": {
                    "source": "builtin_evidence",
                    "reason": builtin_evidence.get("reason"),
                    "additional_tool_ids": list(builtin_evidence.get("additional_tool_ids") or []),
                },
            })
            logger.info(
                "[GapResolver][builtin_evidence] reused_existing tool_id=%s gap=%s",
                result["skill_tool_id"],
                clean_gap,
            )
            return result

        dedup_hits = await CapabilityIndexService(db).search_capabilities(
            query=clean_gap,
            top_k=8,
            bindable_only=True,
            source_types=["builtin_tool", "skill", "external_skill"],
        )
        dedup_candidates: list[dict[str, Any]] = []
        for hit in dedup_hits:
            capability = hit.capability
            dedup_candidates.append({
                "capability_id": str(getattr(capability, "capability_id", "") or ""),
                "source_type": str(getattr(capability, "source_type", "") or ""),
                "registry_tool_id": str(getattr(capability, "registry_tool_id", "") or ""),
                "name": str(getattr(capability, "name", "") or ""),
                "display_name": str(getattr(capability, "display_name", "") or str(getattr(capability, "name", "") or "")),
                "description": str(getattr(capability, "description", "") or ""),
                "score": float(getattr(hit, "score", 0.0) or 0.0),
            })
        result["dedup"] = {
            "candidate_count": len(dedup_candidates),
            "top_candidates": dedup_candidates[:3],
        }

        high_match = next(
            (
                item for item in dedup_candidates
                if str(item.get("registry_tool_id") or "").strip()
                and (_is_skill_source_type(item.get("source_type")) or str(item.get("source_type") or "") == "builtin_tool")
                and float(item.get("score") or 0.0) >= 0.85
            ),
            None,
        )
        if high_match is not None:
            result.update({
                "status": "reused_existing",
                "pipeline_stage": "dedup_reuse",
                "pipeline_message": "Hits with high similarity already have binding capabilities and can be reused directly.",
                "skill_tool_id": str(high_match.get("registry_tool_id") or ""),
                "skill_display_name": str(high_match.get("name") or high_match.get("display_name") or ""),
            })
            logger.info(
                "[GapResolver][dedup] reused_existing source_type=%s tool_id=%s score=%s gap=%s",
                high_match.get("source_type"),
                high_match.get("registry_tool_id"),
                high_match.get("score"),
                clean_gap,
            )
            return result

        medium_match = next(
            (
                item for item in dedup_candidates
                if str(item.get("registry_tool_id") or "").strip()
                and (_is_skill_source_type(item.get("source_type")) or str(item.get("source_type") or "") == "builtin_tool")
                and 0.6 <= float(item.get("score") or 0.0) < 0.85
            ),
            None,
        )
        if medium_match is not None and not allow_medium_similarity_autocreate:
            result.update({
                "status": "needs_dedup_confirmation",
                "pipeline_stage": "dedup_confirmation",
                "pipeline_message": "Hits the candidate Skill with medium similarity and requires the user to confirm whether to reuse or create a new one",
                "error": "needs_dedup_confirmation",
                "dedup_candidate": {
                    "name": str(medium_match.get("name") or medium_match.get("display_name") or ""),
                    "registry_tool_id": str(medium_match.get("registry_tool_id") or ""),
                    "score": round(float(medium_match.get("score") or 0.0), 2),
                    "description": str(medium_match.get("description") or ""),
                    "source_type": str(medium_match.get("source_type") or ""),
                },
            })
            return result

        existing_skill_session = await _find_active_gap_skill_session(
            db,
            agent_spec_id=agent_spec_id,
            workshop_session_id=workshop_session_id,
            gap_id=gap_id,
            gap_description=clean_gap,
        )
        if existing_skill_session is not None:
            skill_session_id = str(existing_skill_session.get("session_id") or "")
            result.update({
                "status": "generating",
                "pipeline_stage": str(existing_skill_session.get("pipeline_stage") or "generating"),
                "pipeline_message": "Reuse existing Skill generation sessions for the same Agent/same capability gap to avoid repeated generation",
                "session_id": skill_session_id,
                "skill_session_id": skill_session_id,
            })
            logger.info(
                "[GapResolver][ReuseSkillSession] gap_id=%s skill_session_id=%s skill_status=%s",
                gap_id,
                skill_session_id,
                existing_skill_session.get("status"),
            )
            return result

        context = dict(known_context or {})
        candidates_for_context = [str(item.get("name") or item.get("registry_tool_id") or "") for item in dedup_candidates[:5]]
        skill_service = await _create_skill_generation_service_with_system_llm(db=db)
        start_result = await skill_service.start_session(
            description=clean_gap,
            user_id=str(user_id or "nanobot").strip() or "nanobot",
            handoff_context={
                "source": "agent_studio_gap",
                "source_spec_id": agent_spec_id,
                "source_name": agent_name,
                "target_capability": clean_gap,
                "handoff_intent": handoff_intent,
                "user_id": str(user_id or "nanobot").strip() or "nanobot",
                "workshop_session_id": workshop_session_id,
                "spec_id": agent_spec_id,
                "gap_id": gap_id,
                "agent_name": agent_name,
                "agent_goal": agent_goal,
                "gap_context": f"{agent_name or 'Agent'} 为达成目标“{agent_goal or '未提供'}”缺少能力：{clean_gap}",
                "related_gaps": [str(item or "") for item in (related_gaps or []) if str(item or "").strip() and str(item or "").strip() != clean_gap][:8],
                "searched_capabilities": [f"CapabilityIndex Searched for:{clean_gap}", *candidates_for_context],
                "confirmed_data_sources": [],
                "user_clarifications": [],
                "known_failure_summaries": context.get("known_failure_summaries") or [],
                "known_verified_facts": context.get("known_verified_facts") or [],
            },
        )
        skill_session_id = str((start_result or {}).get("session_id") or "").strip()
        if not skill_session_id:
            result.update({"status": "failed", "error": "Failed to start Skill generation session"})
            return result

        await skill_service.respond_to_session(skill_session_id, "Confirm that it is designed for reusability. This is a tool that can be parameterized and bound to an Agent.")
        preview = await skill_service.preview_spec(skill_session_id, "确认")
        if not preview:
            result.update({"status": "failed", "session_id": skill_session_id, "error": "Failed to preview Skill specifications"})
            return result
        await skill_service.confirm_spec(skill_session_id, "确认生成")
        result.update({
            "status": "generating",
            "pipeline_stage": "generating",
            "pipeline_message": "Skill Build submitted, waiting to be completed",
            "session_id": skill_session_id,
            "skill_session_id": skill_session_id,
        })
        return result
    except Exception as exc:
        logger.error("[GapResolver] Handle gap exception: %s", exc, exc_info=True)
        result.update({"status": "failed", "error": str(exc)})
        return result


def _summarize_gap_job_gaps(gaps: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {
        "total": 0,
        "pending": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "timeout": 0,
        "cancelled": 0,
    }
    for item in gaps:
        summary["total"] += 1
        status = str((item or {}).get("status") or "").strip().lower()
        if status in summary:
            summary[status] += 1
    return summary


def _derive_gap_job_status(gaps: list[dict[str, Any]]) -> str:
    summary = _summarize_gap_job_gaps(gaps)
    total = int(summary.get("total") or 0)
    if total <= 0:
        return "completed"

    pending_or_running = int(summary.get("pending") or 0) + int(summary.get("running") or 0)
    if pending_or_running > 0:
        return "running"

    completed = int(summary.get("completed") or 0)
    failed = int(summary.get("failed") or 0) + int(summary.get("timeout") or 0)
    cancelled = int(summary.get("cancelled") or 0)

    if completed == total:
        return "completed"
    if cancelled == total:
        return "cancelled"
    if completed > 0 and (failed > 0 or cancelled > 0):
        return "partial_completed"
    if failed > 0 and completed <= 0:
        return "failed"
    return "failed"


def _derive_gap_execution_state(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"pending", "running", "partial_completed"}:
        return "running"
    if normalized in {"completed", "failed", "timeout", "cancelled"}:
        return normalized
    return "queued"


def _iso_elapsed_seconds(started_at: str, now_utc: datetime | None = None) -> int:
    text = str(started_at or "").strip()
    if not text:
        return 0
    try:
        start = datetime.fromisoformat(text)
    except Exception:
        return 0
    now = now_utc or datetime.utcnow()
    return max(int((now - start).total_seconds()), 0)


def _is_claim_expired(expires_at: str, now_utc: datetime | None = None) -> bool:
    text = str(expires_at or "").strip()
    if not text:
        return True
    try:
        expires = datetime.fromisoformat(text)
    except Exception:
        return True
    now = now_utc or datetime.utcnow()
    return expires <= now


def _is_retry_due(next_retry_at: str, now_utc: datetime | None = None) -> bool:
    text = str(next_retry_at or "").strip()
    if not text:
        return True
    try:
        next_at = datetime.fromisoformat(text)
    except Exception:
        return True
    now = now_utc or datetime.utcnow()
    return next_at <= now


def _read_gap_retry_policy(job_doc: dict[str, Any]) -> dict[str, int]:
    execution = dict((job_doc or {}).get("execution") or {})
    policy = dict(execution.get("retry_policy") or {})

    max_attempts = int(policy.get("max_attempts") or _GAP_AUTO_RETRY_MAX_ATTEMPTS)
    base_delay_seconds = int(policy.get("base_delay_seconds") or _GAP_AUTO_RETRY_BASE_DELAY_SECONDS)
    max_delay_seconds = int(policy.get("max_delay_seconds") or _GAP_AUTO_RETRY_MAX_DELAY_SECONDS)

    return {
        "max_attempts": max(0, min(max_attempts, 10)),
        "base_delay_seconds": max(1, min(base_delay_seconds, 3600)),
        "max_delay_seconds": max(1, min(max_delay_seconds, 3600)),
    }


def _compute_retry_backoff_seconds(attempt: int, retry_policy: dict[str, int]) -> int:
    base = int(retry_policy.get("base_delay_seconds") or _GAP_AUTO_RETRY_BASE_DELAY_SECONDS)
    cap = int(retry_policy.get("max_delay_seconds") or _GAP_AUTO_RETRY_MAX_DELAY_SECONDS)
    step = max(0, int(attempt) - 1)
    delay = base * (2 ** step)
    return max(1, min(delay, cap))


def _apply_gap_retry_or_dead_letter(
    target_gap: dict[str, Any],
    *,
    reason_code: str,
    reason_message: str,
    terminal_status: str,
    now_utc: datetime,
    now_iso: str,
    retry_policy: dict[str, int],
) -> dict[str, Any]:
    max_attempts = int(retry_policy.get("max_attempts") or 0)
    current_retry = int(target_gap.get("auto_retry_count") or 0)

    if max_attempts > 0 and current_retry < max_attempts:
        next_retry = current_retry + 1
        delay_seconds = _compute_retry_backoff_seconds(next_retry, retry_policy)
        next_retry_at = (now_utc + timedelta(seconds=delay_seconds)).isoformat()

        target_gap["status"] = "pending"
        target_gap["pipeline_stage"] = "retry_backoff"
        target_gap["pipeline_message"] = (
            f"{reason_message}；将在 {delay_seconds}s 后自动重试（{next_retry}/{max_attempts}）"
        )
        target_gap["error"] = str(reason_code or "retryable_failure").strip() or "retryable_failure"
        target_gap["last_error"] = target_gap["error"]
        target_gap["last_error_message"] = str(reason_message or "").strip()
        target_gap["last_failure_at"] = now_iso
        target_gap["next_retry_at"] = next_retry_at
        target_gap["auto_retry_count"] = next_retry
        target_gap["dead_letter"] = {}
        return target_gap

    terminal = str(terminal_status or "failed").strip().lower() or "failed"
    if terminal not in {"failed", "timeout", "cancelled", "completed"}:
        terminal = "failed"
    target_gap["status"] = terminal
    target_gap["pipeline_stage"] = "dead_letter"
    target_gap["pipeline_message"] = (
        f"{reason_message}; The automatic retry limit has been reached ({max_attempts}) , transfer in dead-letter"
    )
    target_gap["error"] = str(reason_code or "dead_lettered").strip() or "dead_lettered"
    target_gap["last_error"] = target_gap["error"]
    target_gap["last_error_message"] = str(reason_message or "").strip()
    target_gap["last_failure_at"] = now_iso
    target_gap["next_retry_at"] = ""
    target_gap["dead_letter"] = {
        "reason_code": target_gap["error"],
        "reason_message": str(reason_message or "").strip(),
        "failed_at": now_iso,
        "auto_retry_count": int(target_gap.get("auto_retry_count") or 0),
        "max_attempts": max_attempts,
    }
    return target_gap


def _build_gap_job_claim_token(job_id: str, worker_id: str, now_iso: str) -> str:
    seed = f"{job_id}:{worker_id}:{now_iso}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


async def _try_claim_gap_resolution_job(
    collection: Any,
    job_doc: dict[str, Any],
    worker_id: str,
    lease_seconds: int,
) -> dict[str, Any]:
    clean_job_id = str((job_doc or {}).get("job_id") or "").strip()
    if not clean_job_id:
        return {"claimed": False, "reason": "job_id_missing"}

    current_status = str((job_doc or {}).get("status") or "").strip().lower()
    if current_status not in _GAP_JOB_ACTIVE_STATUSES:
        return {"claimed": False, "reason": "job_not_active"}

    now_utc = datetime.utcnow()
    now_iso = now_utc.isoformat()
    lease = max(5, min(int(lease_seconds), 300))
    expires_iso = (now_utc + timedelta(seconds=lease)).isoformat()

    execution = dict((job_doc or {}).get("execution") or {})
    claim = dict(execution.get("claim") or {})
    owner = str(claim.get("owner") or "").strip()
    expires_at = str(claim.get("expires_at") or "").strip()
    if owner and owner != worker_id and not _is_claim_expired(expires_at, now_utc):
        return {"claimed": False, "reason": "already_claimed", "owner": owner}

    token = _build_gap_job_claim_token(clean_job_id, worker_id, now_iso)
    update_result = await collection.update_one(
        {
            "job_id": clean_job_id,
            "status": current_status,
            "updated_at": (job_doc or {}).get("updated_at"),
        },
        {
            "$set": {
                "execution.claim.owner": worker_id,
                "execution.claim.token": token,
                "execution.claim.claimed_at": now_iso,
                "execution.claim.heartbeat_at": now_iso,
                "execution.claim.expires_at": expires_iso,
                "execution.claim.lease_seconds": lease,
                "execution.last_worker_id": worker_id,
                "updated_at": now_iso,
            }
        },
    )

    modified_count = getattr(update_result, "modified_count", None)
    if modified_count is not None and int(modified_count) <= 0:
        return {"claimed": False, "reason": "claim_conflict"}

    return {
        "claimed": True,
        "owner": worker_id,
        "token": token,
        "claimed_at": now_iso,
        "expires_at": expires_iso,
    }


async def _release_gap_resolution_job_claim(
    collection: Any,
    job_id: str,
    worker_id: str,
    token: str,
) -> None:
    now_iso = _utc_now_iso()
    await collection.update_one(
        {
            "job_id": str(job_id or "").strip(),
            "execution.claim.owner": str(worker_id or "").strip(),
            "execution.claim.token": str(token or "").strip(),
        },
        {
            "$set": {
                "execution.claim.released_at": now_iso,
                "execution.claim.owner": "",
                "execution.claim.token": "",
                "execution.claim.expires_at": now_iso,
                "execution.claim.heartbeat_at": now_iso,
                "updated_at": now_iso,
            }
        },
    )


async def _process_single_gap_resolution_job(db: Any, job_doc: dict[str, Any]) -> dict[str, Any]:
    from app.services.skill_generation_service import SESSION_COLLECTION

    collection = _get_collection(db, _GAP_RESOLUTION_JOB_COLLECTION)
    if collection is None:
        return {"status": "error", "message": f"数据库中不可用集合: {_GAP_RESOLUTION_JOB_COLLECTION}"}

    clean_job_id = str((job_doc or {}).get("job_id") or "").strip()
    if not clean_job_id:
        return {"status": "error", "message": "job_id 为空"}

    now_iso = _utc_now_iso()
    now_utc = datetime.utcnow()
    job_status = str((job_doc or {}).get("status") or "").strip().lower()
    if job_status in _GAP_JOB_TERMINAL_STATUSES:
        return {"status": "ok", "job_id": clean_job_id, "processed": False, "message": "job 已在终态"}

    workshop_session_id = str((job_doc or {}).get("workshop_session_id") or "").strip()
    retry_policy = _read_gap_retry_policy(job_doc)
    mode = str((job_doc or {}).get("mode") or "manual_confirmed").strip().lower() or "manual_confirmed"
    allow_medium_similarity_autocreate = mode == "auto"

    logger.info(
        "[GapJob][ProcessJob] start job_id=%s session_id=%s mode=%s status=%s",
        clean_job_id,
        workshop_session_id or "-",
        mode,
        job_status,
    )

    ws_service = AgentWorkshopService(db=db)
    workshop_session = None
    if workshop_session_id:
        try:
            workshop_session = await ws_service._load_session(workshop_session_id)
        except Exception as exc:
            logger.debug("worker Failed to read workshop session, downgrade continues: session_id=%s err=%s", workshop_session_id, exc)
    agent_spec_id = str((job_doc or {}).get("spec_id") or "").strip()
    if not agent_spec_id and workshop_session is not None:
        agent_spec_id = str(getattr(workshop_session, "spec_id", "") or "").strip()

    agent_name = ""
    agent_goal = ""
    session_owner = str((job_doc or {}).get("user_id") or "").strip()
    if workshop_session is not None:
        snapshot = getattr(workshop_session, "current_spec_snapshot", None)
        if snapshot is not None:
            agent_name = str(getattr(snapshot, "name", "") or "").strip()
            agent_goal = str(getattr(snapshot, "primary_goal", "") or "").strip()
        if not session_owner:
            session_owner = str(getattr(workshop_session, "user_id", "") or "").strip()
    effective_user_id = session_owner or "nanobot"

    gaps: list[dict[str, Any]] = [dict(item or {}) for item in list((job_doc or {}).get("gaps") or [])]
    if not gaps:
        derived_status = "completed"
        await collection.update_one(
            {"job_id": clean_job_id},
            {
                "$set": {
                    "status": derived_status,
                    "execution.state": _derive_gap_execution_state(derived_status),
                    "updated_at": now_iso,
                }
            },
        )
        return {"status": "ok", "job_id": clean_job_id, "processed": False, "message": "job 无 gaps"}

    target_index = -1
    for idx, gap in enumerate(gaps):
        if str(gap.get("status") or "").strip().lower() == "pending":
            if not _is_retry_due(str(gap.get("next_retry_at") or ""), now_utc):
                continue
            target_index = idx
            break
    if target_index < 0:
        for idx, gap in enumerate(gaps):
            if str(gap.get("status") or "").strip().lower() == "running":
                target_index = idx
                break

    if target_index < 0:
        derived_status = _derive_gap_job_status(gaps)
        await collection.update_one(
            {"job_id": clean_job_id},
            {
                "$set": {
                    "status": derived_status,
                    "execution.state": _derive_gap_execution_state(derived_status),
                    "updated_at": now_iso,
                }
            },
        )
        return {"status": "ok", "job_id": clean_job_id, "processed": False, "message": "job 无可执行 gap"}

    target_gap = dict(gaps[target_index] or {})
    gap_id = str(target_gap.get("gap_id") or f"gap_{target_index + 1}").strip() or f"gap_{target_index + 1}"
    gap_desc = str(target_gap.get("description") or "").strip()
    gap_status = str(target_gap.get("status") or "").strip().lower()

    async def _persist_gap(target: dict[str, Any]) -> dict[str, Any]:
        target["gap_id"] = gap_id
        target["updated_at"] = now_iso
        gaps[target_index] = target
        derived = _derive_gap_job_status(gaps)
        logger.info(
            "[GapJob][PersistGap] job_id=%s gap_id=%s gap_status=%s stage=%s derived_job_status=%s skill_tool_id=%s",
            clean_job_id,
            gap_id,
            target.get("status"),
            target.get("pipeline_stage"),
            derived,
            target.get("skill_tool_id") or "-",
        )
        await collection.update_one(
            {"job_id": clean_job_id},
            {
                "$set": {
                    "gaps": gaps,
                    "status": derived,
                    "updated_at": now_iso,
                    "execution.state": _derive_gap_execution_state(derived),
                    "execution.last_gap_id": gap_id,
                    "execution.last_gap_status": str(target.get("status") or "").strip().lower(),
                    "execution.last_gap_message": str(target.get("pipeline_message") or "").strip(),
                }
            },
        )
        return {
            "status": "ok",
            "job_id": clean_job_id,
            "processed": True,
            "job_status": derived,
            "gap": target,
            "summary": _summarize_gap_job_gaps(gaps),
        }

    if gap_status == "pending":
        # Switch to running first to avoid repeated preemption by concurrent workers
        target_gap["status"] = "running"
        target_gap["pipeline_stage"] = "planning"
        target_gap["pipeline_message"] = "worker Order received and processing started"
        target_gap.setdefault("retry_count", 0)
        target_gap.setdefault("auto_retry_count", 0)
        target_gap["next_retry_at"] = ""
        target_gap.setdefault("created_at", now_iso)
        target_gap.setdefault("started_at", now_iso)

        known_context = _collect_gap_job_known_context(gaps, exclude_gap_id=gap_id)
        logger.info(
            "[GapJob][KnownContext] job_id=%s gap_id=%s known_failures=%s known_facts=%s",
            clean_job_id,
            gap_id,
            len(known_context.get("known_failure_summaries") or []),
            len(known_context.get("known_verified_facts") or []),
        )
        resolution = await _resolve_single_gap_capability(
            db=db,
            ws_service=ws_service,
            gap_description=gap_desc,
            gap_id=gap_id,
            gap_index=0,
            workshop_session_id=workshop_session_id,
            agent_spec_id=agent_spec_id,
            agent_name=agent_name,
            agent_goal=agent_goal,
            user_id=effective_user_id,
            allow_medium_similarity_autocreate=allow_medium_similarity_autocreate,
            related_gaps=[str(item.get("description") or "") for item in gaps if isinstance(item, dict)],
            known_context=known_context,
            handoff_intent="async_gap_resolution_worker",
        )

        resolution_status = str(resolution.get("status") or "").strip().lower()
        target_gap["pipeline_stage"] = str(resolution.get("pipeline_stage") or target_gap.get("pipeline_stage") or "")
        target_gap["pipeline_message"] = str(resolution.get("pipeline_message") or target_gap.get("pipeline_message") or "")
        target_gap["skill_tool_id"] = str(resolution.get("skill_tool_id") or target_gap.get("skill_tool_id") or "")
        target_gap["skill_display_name"] = str(resolution.get("skill_display_name") or target_gap.get("skill_display_name") or "")
        target_gap["skill_session_id"] = str(resolution.get("skill_session_id") or resolution.get("session_id") or target_gap.get("skill_session_id") or "")
        target_gap["dedup"] = resolution.get("dedup") or target_gap.get("dedup") or {}
        if resolution.get("dedup_candidate"):
            target_gap["dedup_candidate"] = resolution.get("dedup_candidate")
        target_gap["elapsed_seconds"] = _iso_elapsed_seconds(str(target_gap.get("started_at") or now_iso), now_utc)

        if resolution_status == "reused_existing":
            target_gap["status"] = "completed"
            target_gap["error"] = None
            target_gap["next_retry_at"] = ""
            logger.info(
                "[GapJob][ResolvedExisting] job_id=%s gap_id=%s stage=%s tool_id=%s",
                clean_job_id,
                gap_id,
                target_gap.get("pipeline_stage"),
                target_gap.get("skill_tool_id") or "-",
            )
            return await _persist_gap(target_gap)

        if resolution_status == "needs_dedup_confirmation":
            target_gap["status"] = "failed"
            target_gap["error"] = "needs_dedup_confirmation"
            target_gap["next_retry_at"] = ""
            return await _persist_gap(target_gap)

        if resolution_status == "generating":
            target_gap["status"] = "running"
            target_gap["error"] = None
            target_gap["next_retry_at"] = ""
            return await _persist_gap(target_gap)

        target_gap = _apply_gap_retry_or_dead_letter(
            target_gap,
            reason_code=str(resolution.get("error") or "skill_resolution_failed"),
            reason_message=str(resolution.get("error") or "Failed to start Skill generation session"),
            terminal_status="failed",
            now_utc=now_utc,
            now_iso=now_iso,
            retry_policy=retry_policy,
        )
        target_gap["elapsed_seconds"] = _iso_elapsed_seconds(str(target_gap.get("started_at") or now_iso), now_utc)
        return await _persist_gap(target_gap)


    # running Status: Polling Skill to generate session
    skill_session_id = str(target_gap.get("skill_session_id") or "").strip()
    if not skill_session_id:
        target_gap = _apply_gap_retry_or_dead_letter(
            target_gap,
            reason_code="missing_skill_session_id",
            reason_message="running gap missing skill_session_id",
            terminal_status="failed",
            now_utc=now_utc,
            now_iso=now_iso,
            retry_policy=retry_policy,
        )
        target_gap["elapsed_seconds"] = _iso_elapsed_seconds(str(target_gap.get("started_at") or now_iso), now_utc)
        return await _persist_gap(target_gap)

    session_doc = await db[SESSION_COLLECTION].find_one({"session_id": skill_session_id})
    if not session_doc:
        target_gap = _apply_gap_retry_or_dead_letter(
            target_gap,
            reason_code="skill_session_not_found",
            reason_message="Skill Generate session does not exist",
            terminal_status="failed",
            now_utc=now_utc,
            now_iso=now_iso,
            retry_policy=retry_policy,
        )
        target_gap["elapsed_seconds"] = _iso_elapsed_seconds(str(target_gap.get("started_at") or now_iso), now_utc)
        return await _persist_gap(target_gap)

    skill_status = str(session_doc.get("status") or "").strip().lower()
    target_gap["pipeline_stage"] = str(session_doc.get("pipeline_stage") or target_gap.get("pipeline_stage") or "")
    target_gap["pipeline_message"] = str(session_doc.get("pipeline_message") or target_gap.get("pipeline_message") or "")
    target_gap["elapsed_seconds"] = _iso_elapsed_seconds(str(target_gap.get("started_at") or now_iso), now_utc)

    if skill_status == "completed":
        agentic_context = _extract_agentic_context_from_session_doc(session_doc)
        spec = session_doc.get("spec") or {}
        target_gap["status"] = "completed"
        target_gap["skill_tool_id"] = str(spec.get("tool_id") or "")
        target_gap["skill_display_name"] = str(spec.get("display_name") or "")
        target_gap["error"] = None
        target_gap["next_retry_at"] = ""
        target_gap["dead_letter"] = {}
        if agentic_context.get("verified_facts"):
            target_gap["agentic_verified_facts"] = agentic_context.get("verified_facts") or []
        if agentic_context.get("agentic_trace"):
            target_gap["agentic_trace"] = agentic_context.get("agentic_trace") or []
        if agentic_context.get("generation_engine"):
            target_gap["generation_engine"] = agentic_context.get("generation_engine")
        logger.info(
            "[GapJob][AgenticContext] job_id=%s gap_id=%s skill_status=completed engine=%s facts=%s trace_events=%s",
            clean_job_id,
            gap_id,
            agentic_context.get("generation_engine") or "-",
            len(agentic_context.get("verified_facts") or []),
            len(agentic_context.get("agentic_trace") or []),
        )
        return await _persist_gap(target_gap)

    if skill_status == "failed":
        agentic_context = _extract_agentic_context_from_session_doc(session_doc)
        if agentic_context.get("failure_summary"):
            target_gap["agentic_failure_summary"] = agentic_context.get("failure_summary")
        if agentic_context.get("verified_facts"):
            target_gap["agentic_verified_facts"] = agentic_context.get("verified_facts") or []
        if agentic_context.get("agentic_trace"):
            target_gap["agentic_trace"] = agentic_context.get("agentic_trace") or []
        if agentic_context.get("generation_engine"):
            target_gap["generation_engine"] = agentic_context.get("generation_engine")
        logger.info(
            "[GapJob][AgenticContext] job_id=%s gap_id=%s skill_status=failed engine=%s facts=%s trace_events=%s failure_summary=%s",
            clean_job_id,
            gap_id,
            agentic_context.get("generation_engine") or "-",
            len(agentic_context.get("verified_facts") or []),
            len(agentic_context.get("agentic_trace") or []),
            (agentic_context.get("failure_summary") or "")[:300],
        )
        target_gap = _apply_gap_retry_or_dead_letter(
            target_gap,
            reason_code="skill_generation_failed",
            reason_message=str(session_doc.get("pipeline_message") or "Skill 生成失败").strip() or "Skill 生成失败",
            terminal_status="failed",
            now_utc=now_utc,
            now_iso=now_iso,
            retry_policy=retry_policy,
        )
        return await _persist_gap(target_gap)

    if target_gap["elapsed_seconds"] >= _GAP_ITEM_TIMEOUT_SECONDS:
        target_gap = _apply_gap_retry_or_dead_letter(
            target_gap,
            reason_code="skill_generation_timeout",
            reason_message=f"Skill 生成超时（>{_GAP_ITEM_TIMEOUT_SECONDS}s）",
            terminal_status="timeout",
            now_utc=now_utc,
            now_iso=now_iso,
            retry_policy=retry_policy,
        )
        return await _persist_gap(target_gap)

    # not finished yet, keep running
    return await _persist_gap(target_gap)


async def process_agent_workshop_gap_resolution_jobs_once(
    limit: int = 1,
    worker_id: str = "",
    claim_lease_seconds: int = _GAP_JOB_CLAIM_LEASE_SECONDS,
) -> dict[str, Any]:
    """Called by a background worker: a single consumption and advancement of the gap resolution jobs state machine."""
    try:
        db = get_mongo_db()
        collection = _get_collection(db, _GAP_RESOLUTION_JOB_COLLECTION)
        if collection is None:
            return {
                "status": "error",
                "message": f"数据库中不可用集合: {_GAP_RESOLUTION_JOB_COLLECTION}",
                "processed": 0,
            }

        cap = max(1, min(int(limit), 20))
        effective_worker_id = str(worker_id or "").strip() or "gap-worker"
        lease_seconds = max(5, min(int(claim_lease_seconds), 300))
        docs = await collection.find({}).to_list(length=200)
        if len(docs) == 0:
            logger.debug(
                "[GapJob][Worker] worker_id=%s total_jobs=0 cap=%s (idle, skip)",
                effective_worker_id,
                cap,
            )
            return {
                "status": "ok",
                "active_jobs": 0,
                "processed": 0,
                "attempted": 0,
                "claim_skipped": 0,
            }

        active_docs = [
            doc
            for doc in docs
            if str((doc or {}).get("status") or "").strip().lower() in _GAP_JOB_ACTIVE_STATUSES
        ]
        active_docs.sort(key=lambda item: str((item or {}).get("updated_at") or ""))

        if len(active_docs) == 0:
            logger.debug(
                "[GapJob][Worker] worker_id=%s total_jobs=%s active_jobs=0 cap=%s (all terminal, skip)",
                effective_worker_id,
                len(docs),
                cap,
            )
            return {
                "status": "ok",
                "active_jobs": 0,
                "processed": 0,
                "attempted": 0,
                "claim_skipped": 0,
            }

        logger.info(
            "[GapJob][Worker] worker_id=%s total_jobs=%s active_jobs=%s cap=%s",
            effective_worker_id,
            len(docs),
            len(active_docs),
            cap,
        )

        handled: list[dict[str, Any]] = []
        claim_skipped = 0
        for doc in active_docs[:cap]:
            claim = await _try_claim_gap_resolution_job(
                collection=collection,
                job_doc=doc,
                worker_id=effective_worker_id,
                lease_seconds=lease_seconds,
            )
            if not bool(claim.get("claimed")):
                claim_skipped += 1
                continue

            try:
                handled.append(await _process_single_gap_resolution_job(db, doc))
            finally:
                try:
                    await _release_gap_resolution_job_claim(
                        collection=collection,
                        job_id=str((doc or {}).get("job_id") or ""),
                        worker_id=effective_worker_id,
                        token=str(claim.get("token") or ""),
                    )
                except Exception as release_exc:
                    logger.debug("[GapJob][Worker] release_claim_fail job_id=%s err=%s", (doc or {}).get("job_id"), release_exc)

        processed_count = sum(1 for item in handled if bool((item or {}).get("processed")))

        if processed_count > 0 or len(handled) > 0:
            logger.info(
                "[GapJob][Worker] done worker_id=%s handled=%s processed=%s claim_skipped=%s",
                effective_worker_id,
                len(handled),
                processed_count,
                claim_skipped,
            )
        else:
            logger.debug(
                "[GapJob][Worker] done worker_id=%s handled=%s processed=%s claim_skipped=%s (idle)",
                effective_worker_id,
                len(handled),
                processed_count,
                claim_skipped,
            )

        return {
            "status": "ok",
            "active_jobs": len(active_docs),
            "processed": processed_count,
            "attempted": len(handled),
            "claim_skipped": claim_skipped,
            "results": handled,
        }
    except Exception as exc:
        logger.error("worker Consuming gap resolution jobs failed: %s", exc, exc_info=True)
        return {"status": "error", "message": f"worker Failed to consume gap jobs: {exc}", "processed": 0}


def _extract_blocking_gaps_from_report(gap_report: Any) -> list[str]:
    blocking_gaps = _read_mapping_or_attr(gap_report, "blocking_gaps", []) or []
    if not isinstance(blocking_gaps, list):
        return []
    return [str(item).strip() for item in blocking_gaps if str(item).strip()]


def _parse_optional_json_list(raw: str, field_name: str) -> list[Any]:
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except Exception as exc:
        raise ValueError(f"{field_name} Not a valid JSON array: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError(f"{field_name} 必须是 JSON 数组")
    return data


def _with_nanobot_review_worker_flags(runtime_result: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if runtime_result is None:
        return None
    payload = dict(runtime_result)
    payload.setdefault("review_worker_mode", "nanobot-assisted")
    payload.setdefault("nanobot_evidence_workers", True)
    return payload


def _has_workshop_runtime_evidence(runtime_result: dict[str, Any] | None) -> bool:
    if not isinstance(runtime_result, dict) or not runtime_result:
        return False
    if str(runtime_result.get("output_text") or "").strip():
        return True
    if str(runtime_result.get("report") or "").strip():
        return True
    if runtime_result.get("output_payload"):
        return True
    if runtime_result.get("raw_result"):
        return True
    if runtime_result.get("tool_trace"):
        return True

    debug_prompt = runtime_result.get("debug_prompt")
    if isinstance(debug_prompt, dict):
        if debug_prompt.get("tool_trace"):
            return True
        if str(debug_prompt.get("system_prompt") or "").strip():
            return True
        if str(debug_prompt.get("user_prompt") or "").strip():
            return True
        if str(debug_prompt.get("output_text") or "").strip():
            return True

    raw_result = runtime_result.get("raw_result")
    if isinstance(raw_result, dict):
        if raw_result.get("tool_trace"):
            return True
        nested_debug_prompt = raw_result.get("__debug_prompt__")
        if isinstance(nested_debug_prompt, dict):
            if nested_debug_prompt.get("tool_trace"):
                return True
            if str(nested_debug_prompt.get("system_prompt") or "").strip():
                return True
            if str(nested_debug_prompt.get("user_prompt") or "").strip():
                return True
            if str(nested_debug_prompt.get("output_text") or "").strip():
                return True
    return False


def _build_tool_stage_event(name: str, status: str, detail: str) -> dict[str, str]:
    return {
        "name": name,
        "status": status,
        "detail": str(detail or "").strip(),
    }


_WORKSHOP_SPEC_COLLECTION = "agent_specs"
_WORKSHOP_SESSION_COLLECTION = "agent_workshop_sessions"
_WORKSHOP_VERSION_COLLECTION = "agent_versions"
_WORKSHOP_EVALUATION_COLLECTION = "agent_evaluations"


def _compute_workshop_phase(
    *,
    feasibility_status: str,
    completeness_score: float,
    version_status: str,
    latest_evaluation_decision: str,
    has_version: bool,
) -> str:
    if feasibility_status == "not-feasible":
        return "blocked"
    if version_status == "active":
        return "published"
    if version_status == "testing" and latest_evaluation_decision == "pass":
        return "publish-ready"
    if latest_evaluation_decision:
        return "evaluation"
    if version_status == "testing":
        return "testing"
    if has_version or (feasibility_status == "feasible" and completeness_score >= 0.75):
        return "generation"
    if feasibility_status == "need-clarification":
        return "confirmation"
    return "requirement-intake"


def _humanize_workshop_phase(phase: str) -> str:
    mapping = {
        "requirement-intake": "需求收集中",
        "confirmation": "待确认",
        "generation": "生成阶段",
        "testing": "真数据测试中",
        "evaluation": "待修正",
        "publish-ready": "待确认发布",
        "published": "已发布",
        "blocked": "不可继续",
    }
    return mapping.get(str(phase or "").strip(), str(phase or "未定义阶段").strip() or "未定义阶段")


async def _resolve_workshop_session_phase_context(db: Any, session_id: str) -> dict[str, Any]:
    sessions = _get_collection(db, _WORKSHOP_SESSION_COLLECTION)
    specs = _get_collection(db, _WORKSHOP_SPEC_COLLECTION)
    versions = _get_collection(db, _WORKSHOP_VERSION_COLLECTION)
    evaluations = _get_collection(db, _WORKSHOP_EVALUATION_COLLECTION)

    clean_session_id = str(session_id or "").strip()
    if not clean_session_id:
        return {"exists": False, "session_id": clean_session_id, "guard_available": False}
    if sessions is None or specs is None or versions is None or evaluations is None:
        return {"exists": False, "session_id": clean_session_id, "guard_available": False}

    session_doc = await sessions.find_one({"session_id": clean_session_id})
    if not session_doc:
        return {"exists": False, "session_id": clean_session_id, "guard_available": True}

    spec_snapshot = _read_mapping_or_attr(session_doc, "current_spec_snapshot", {}) or {}
    spec_id = str(
        session_doc.get("spec_id")
        or _read_mapping_or_attr(spec_snapshot, "spec_id", "")
        or ""
    ).strip()
    spec_doc = await specs.find_one({"spec_id": spec_id}) if spec_id and specs is not None else None

    current_version_id = str(
        (spec_doc or {}).get("current_version_id")
        or _read_mapping_or_attr(spec_snapshot, "current_version_id", "")
        or ""
    ).strip()
    version_doc = await versions.find_one({"version_id": current_version_id}) if current_version_id and versions is not None else None
    latest_evaluation_doc = (
        await evaluations.find_one({"version_id": current_version_id}, sort=[("created_at", -1)])
        if current_version_id and evaluations is not None
        else None
    )

    feasibility_status = str(session_doc.get("feasibility_status") or "").strip().lower()
    try:
        completeness_score = float(session_doc.get("completeness_score") or 0)
    except Exception:
        completeness_score = 0.0
    version_status = str((version_doc or {}).get("status") or "").strip().lower()
    latest_evaluation_decision = str((latest_evaluation_doc or {}).get("decision") or "").strip().lower()
    phase = _compute_workshop_phase(
        feasibility_status=feasibility_status,
        completeness_score=completeness_score,
        version_status=version_status,
        latest_evaluation_decision=latest_evaluation_decision,
        has_version=bool(version_doc),
    )

    return {
        "exists": True,
        "guard_available": True,
        "session_id": clean_session_id,
        "spec_id": spec_id,
        "current_version_id": current_version_id,
        "feasibility_status": feasibility_status,
        "completeness_score": completeness_score,
        "version_status": version_status,
        "latest_evaluation_decision": latest_evaluation_decision,
        "phase": phase,
        "phase_label": _humanize_workshop_phase(phase),
    }


async def _get_existing_version_summary(db: Any, version_id: str) -> dict[str, Any]:
    """Get summary information of existing versions for"overwrite or continue"Decision display."""
    if not version_id:
        return {"version_id": "", "found": False}
    versions = _get_collection(db, _WORKSHOP_VERSION_COLLECTION)
    if versions is None:
        return {"version_id": version_id, "found": False}
    version_doc = await versions.find_one({"version_id": version_id})
    if not version_doc:
        return {"version_id": version_id, "found": False}

    required_tools = version_doc.get("required_tools") or []
    required_capabilities = version_doc.get("required_capabilities") or []
    # required_tools may be ["tool_id|tool_name", ...] format, extract tool_id
    tool_ids = []
    for item in required_tools[:20]:
        if isinstance(item, str):
            tool_ids.append(item.split("|")[0].strip())
        elif isinstance(item, dict):
            tool_ids.append(str(item.get("tool_id") or item.get("id") or "").strip())

    return {
        "version_id": version_id,
        "found": True,
        "status": version_doc.get("status") or "",
        "created_at": str(version_doc.get("created_at") or "")[:19],
        "required_tools": tool_ids,
        "required_tools_count": len(tool_ids),
        "required_capabilities_count": len(required_capabilities),
        "agent_metadata": {
            "name": (version_doc.get("agent_metadata") or {}).get("name") or "",
            "type": (version_doc.get("agent_metadata") or {}).get("type") or "",
        },
    }


def _get_current_thread_context_spec_id() -> str:
    """Read the current thread s spec_id from contextvar."""
    try:
        from core.tools.context import get_current_assistant_thread_context
        ctx = get_current_assistant_thread_context() or {}
        return str(ctx.get("spec_id") or "").strip()
    except Exception:
        return ""


def _agent_id_equivalent(left: str, right: str) -> bool:
    """Determine whether the candidate Agent ID is just a historical prefix difference."""
    clean_left = str(left or "").strip()
    clean_right = str(right or "").strip()
    if not clean_left or not clean_right:
        return False
    if clean_left == clean_right:
        return True

    def _canonical(value: str) -> str:
        for prefix in ("agent_candidate_", "candidate_"):
            if value.startswith(prefix):
                return value[len(prefix):]
        return value

    return _canonical(clean_left) == _canonical(clean_right)


async def _resolve_spec_name(db: Any, spec_id: str) -> str:
    """Parse the name corresponding to spec_id from the database."""
    try:
        specs = _get_collection(db, _WORKSHOP_SPEC_COLLECTION)
        if specs is None:
            return ""
        doc = await specs.find_one({"spec_id": spec_id})
        if doc:
            return str(doc.get("name") or "").strip()
    except Exception:
        pass
    return ""


async def _resolve_workshop_version_phase_context(db: Any, version_id: str) -> dict[str, Any]:
    versions = _get_collection(db, _WORKSHOP_VERSION_COLLECTION)
    evaluations = _get_collection(db, _WORKSHOP_EVALUATION_COLLECTION)

    clean_version_id = str(version_id or "").strip()
    if not clean_version_id:
        return {"exists": False, "version_id": clean_version_id, "guard_available": False}
    if versions is None or evaluations is None:
        return {"exists": False, "version_id": clean_version_id, "guard_available": False}

    version_doc = await versions.find_one({"version_id": clean_version_id})
    if not version_doc:
        return {"exists": False, "version_id": clean_version_id, "guard_available": True}

    latest_evaluation_doc = (
        await evaluations.find_one({"version_id": clean_version_id}, sort=[("created_at", -1)])
        if evaluations is not None
        else None
    )
    version_status = str(version_doc.get("status") or "").strip().lower()
    latest_evaluation_decision = str((latest_evaluation_doc or {}).get("decision") or "").strip().lower()
    phase = _compute_workshop_phase(
        feasibility_status="feasible",
        completeness_score=1.0,
        version_status=version_status,
        latest_evaluation_decision=latest_evaluation_decision,
        has_version=True,
    )

    return {
        "exists": True,
        "guard_available": True,
        "version_id": clean_version_id,
        "spec_id": str(version_doc.get("spec_id") or "").strip(),
        "version_status": version_status,
        "latest_evaluation_decision": latest_evaluation_decision,
        "phase": phase,
        "phase_label": _humanize_workshop_phase(phase),
    }


async def _auto_sync_gap_tools_to_workshop_version(db: Any, version_id: str) -> dict[str, Any]:
    """Synchronize the completed/reusable gap tools to the current testing version to avoid deadlock in the rebuild/iterate phase."""
    clean_version_id = str(version_id or "").strip()
    versions = _get_collection(db, _WORKSHOP_VERSION_COLLECTION)
    if not clean_version_id or versions is None:
        return {"status": "skipped", "reason": "missing_version_or_collection", "version_id": clean_version_id}

    version_doc = await versions.find_one({"version_id": clean_version_id})
    if not version_doc:
        return {"status": "skipped", "reason": "version_not_found", "version_id": clean_version_id}
    version_status = str(version_doc.get("status") or "").strip().lower()
    if version_status not in {"testing", "draft", "evaluation"}:
        return {"status": "skipped", "reason": f"version_status_{version_status or 'unknown'}", "version_id": clean_version_id}

    service = AgentWorkshopService(db=db)
    workshop_session_id = str(version_doc.get("published_from_session_id") or "").strip()
    if not workshop_session_id:
        return {"status": "skipped", "reason": "missing_workshop_session_id", "version_id": clean_version_id}
    session = await service._load_session(workshop_session_id)
    if session is None:
        return {"status": "skipped", "reason": "workshop_session_not_found", "version_id": clean_version_id}

    existing_tools = _parse_string_list(",".join(list(version_doc.get("required_tools") or [])))
    auto_resolved = await service._collect_auto_resolved_gaps_for_session(workshop_session_id)
    auto_resolved_tools = [
        str(item.get("skill_tool_id") or "").strip()
        for item in auto_resolved
        if str(item.get("skill_tool_id") or "").strip()
    ]
    builtin_tools: list[str] = []
    gap_report = getattr(session, "gap_report", None)
    for gap_text in list(_read_mapping_or_attr(gap_report, "blocking_gaps", []) or []):
        evidence = service._builtin_tool_evidence_for_gap(str(gap_text or ""))
        if evidence:
            for tool_id in [str(evidence.get("skill_tool_id") or "").strip(), *[str(item or "").strip() for item in list(evidence.get("additional_tool_ids") or [])]]:
                if tool_id:
                    builtin_tools.append(tool_id)

    merged_tools = _dedupe_string_list([*existing_tools, *auto_resolved_tools, *builtin_tools])
    if merged_tools == existing_tools:
        return {
            "status": "unchanged",
            "version_id": clean_version_id,
            "workshop_session_id": workshop_session_id,
            "required_tools": merged_tools,
            "auto_resolved_tools": auto_resolved_tools,
            "builtin_tools": builtin_tools,
        }

    sync_result = await service.sync_version_required_tools(
        version_id=clean_version_id,
        required_tools=merged_tools,
        default_tools=merged_tools[:4],
        max_tool_calls=max(6, len(merged_tools)),
    )
    logger.info(
        "[AgentWorkshop][AutoSyncGapTools] version_id=%s session_id=%s added_tools=%s total_tools=%s",
        clean_version_id,
        workshop_session_id,
        [tool_id for tool_id in merged_tools if tool_id not in existing_tools],
        len(merged_tools),
    )
    return {
        "status": "synced",
        "version_id": clean_version_id,
        "workshop_session_id": workshop_session_id,
        "required_tools": merged_tools,
        "auto_resolved_tools": auto_resolved_tools,
        "builtin_tools": builtin_tools,
        "sync_result": sync_result,
    }


async def _resolve_workshop_draft_target_context(db: Any, agent_id: str, thread_id: str = "") -> dict[str, Any]:
    specs = _get_collection(db, _WORKSHOP_SPEC_COLLECTION)
    versions = _get_collection(db, _WORKSHOP_VERSION_COLLECTION)
    threads = _get_collection(db, "embedded_nanobot_threads")

    clean_agent_id = str(agent_id or "").strip()
    clean_thread_id = str(thread_id or "").strip()
    default_context = {
        "exists": False,
        "guard_available": bool(specs is not None and versions is not None),
        "matched_existing_asset": False,
        "target_kind": "",
        "agent_id": clean_agent_id,
        "thread_id": clean_thread_id,
    }
    if not clean_agent_id:
        return default_context
    if specs is None or versions is None:
        return default_context

    version_doc = await versions.find_one({"version_id": clean_agent_id})
    if version_doc:
        phase_context = await _resolve_workshop_version_phase_context(db, clean_agent_id)
        return {
            **phase_context,
            "matched_existing_asset": True,
            "target_kind": "version_id",
            "agent_id": clean_agent_id,
            "thread_id": clean_thread_id,
        }

    spec_doc = await specs.find_one({"spec_id": clean_agent_id})
    if spec_doc:
        current_version_id = str(spec_doc.get("current_version_id") or "").strip()
        phase_context = {
            "exists": True,
            "guard_available": True,
            "spec_id": clean_agent_id,
            "version_id": current_version_id,
            "version_status": "",
            "latest_evaluation_decision": "",
            "phase": "generation",
            "phase_label": _humanize_workshop_phase("generation"),
        }
        if current_version_id:
            phase_context = await _resolve_workshop_version_phase_context(db, current_version_id)
        return {
            **phase_context,
            "matched_existing_asset": True,
            "target_kind": "spec_id",
            "agent_id": clean_agent_id,
            "thread_id": clean_thread_id,
        }

    if not clean_thread_id or threads is None:
        return default_context

    thread_doc = await threads.find_one({"thread_id": clean_thread_id})
    if thread_doc is None:
        thread_doc = await threads.find_one({"session_key": clean_thread_id})
    thread_context = dict((thread_doc or {}).get("thread_context") or {})
    resolved_spec_id = str(thread_context.get("spec_id") or "").strip()
    resolved_version_id = str(thread_context.get("version_id") or "").strip()
    resolved_version_status = str(thread_context.get("version_status") or "").strip().lower()
    if clean_agent_id not in {resolved_spec_id, resolved_version_id}:
        return default_context

    if resolved_version_id:
        phase_context = await _resolve_workshop_version_phase_context(db, resolved_version_id)
        if phase_context.get("exists"):
            return {
                **phase_context,
                "matched_existing_asset": True,
                "target_kind": "thread_context",
                "agent_id": clean_agent_id,
                "thread_id": clean_thread_id,
                "spec_id": resolved_spec_id or phase_context.get("spec_id"),
            }

    phase = "published" if resolved_version_status == "active" else "generation"
    return {
        "exists": True,
        "guard_available": True,
        "matched_existing_asset": True,
        "target_kind": "thread_context",
        "agent_id": clean_agent_id,
        "thread_id": clean_thread_id,
        "spec_id": resolved_spec_id,
        "version_id": resolved_version_id,
        "version_status": resolved_version_status,
        "latest_evaluation_decision": "",
        "phase": phase,
        "phase_label": _humanize_workshop_phase(phase),
    }


def _build_phase_guard_blocked_response(
    *,
    tool_name: str,
    blocked_code: str,
    message: str,
    next_action: str,
    phase_context: dict[str, Any],
    target_fields: dict[str, Any],
) -> str:
    return _json_response({
        "status": "blocked",
        "blocked_by": "phase_guard",
        "blocked_code": str(blocked_code or "phase_not_ready").strip() or "phase_not_ready",
        "message": message,
        "next_action": next_action,
        "current_phase": phase_context.get("phase"),
        "current_phase_label": phase_context.get("phase_label"),
        "summary": {
            "blocked_code": str(blocked_code or "phase_not_ready").strip() or "phase_not_ready",
            "current_phase": phase_context.get("phase"),
            "current_phase_label": phase_context.get("phase_label"),
            "version_status": phase_context.get("version_status"),
            "latest_evaluation_decision": phase_context.get("latest_evaluation_decision"),
            "feasibility_status": phase_context.get("feasibility_status"),
            "completeness_score": phase_context.get("completeness_score"),
        },
        "_tool_events": [
            _build_tool_stage_event(
                f"{tool_name}.phase_guard",
                "blocked",
                message,
            ),
        ],
        **target_fields,
    })


async def _resolve_workshop_test_llm_payload(
    db: Any,
    temperature: float = 0.2,
    max_tokens: int = 4000,
) -> dict[str, Any]:
    from app.services.intelligent_assistant_service import get_reasoning_llm_config

    config = await get_reasoning_llm_config(db)
    if not config:
        raise ValueError("No available default inference model configuration was found in the system. Please configure the large model in the system settings first.")

    clean_provider = str(getattr(config, "provider", "") or "").strip()
    clean_model = str(
        getattr(config, "model", "")
        or getattr(config, "model_name", "")
        or ""
    ).strip()
    clean_backend_url = str(
        getattr(config, "base_url", "")
        or getattr(config, "api_base", "")
        or ""
    ).strip()
    clean_api_key = str(getattr(config, "api_key", "") or "").strip()

    try:
        temperature = float(getattr(config, "temperature", temperature) or temperature)
    except Exception:
        pass
    try:
        max_tokens = int(getattr(config, "max_tokens", max_tokens) or max_tokens)
    except Exception:
        pass

    if not clean_provider:
        raise ValueError("The system default inference model lacks provider configuration")
    if not clean_model:
        raise ValueError("The system default inference model lacks model configuration")

    return {
        "provider": clean_provider,
        "model": clean_model,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "backend_url": clean_backend_url or None,
        "api_key": clean_api_key or None,
    }


def _read_mapping_or_attr(value: Any, field: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(field, default)
    return getattr(value, field, default)


async def _sync_linked_workshop_versions(
    db: Any,
    agent_id: str,
    candidate_config: dict[str, Any],
    resolved_tools: list[str],
    resolved_default_tools: list[str],
    max_tool_calls: int,
) -> dict[str, Any]:
    versions = _get_collection(db, "agent_versions")
    if versions is None:
        return {
            "status": "skipped",
            "reason": "agent_versions_unavailable",
            "attempted_version_ids": [],
            "synced_version_ids": [],
            "skipped": [],
        }

    metadata = dict(candidate_config.get("metadata") or {})
    version_candidates = [
        metadata.get("version_id"),
        metadata.get("latest_workshop_version_id"),
        metadata.get("current_version_id"),
    ]
    spec_id = str(metadata.get("spec_id") or "").strip()
    if spec_id:
        specs = _get_collection(db, "agent_specs")
        if specs is not None:
            spec_doc = await specs.find_one({"spec_id": spec_id}, {"current_version_id": 1}) or {}
            version_candidates.append(spec_doc.get("current_version_id"))

    target_version_ids = _dedupe_string_list([str(item or "").strip() for item in version_candidates])
    if not target_version_ids:
        return {
            "status": "not_linked",
            "reason": "no_linked_version",
            "attempted_version_ids": [],
            "synced_version_ids": [],
            "skipped": [],
        }

    synced_version_ids: list[str] = []
    skipped: list[dict[str, str]] = []
    workshop_service = AgentWorkshopService(db=db)

    for version_id in target_version_ids:
        version_doc = await versions.find_one({"version_id": version_id})
        if not version_doc:
            skipped.append({"version_id": version_id, "reason": "version_not_found"})
            continue

        version_status = str(version_doc.get("status") or "").strip().lower()
        if version_status == "active":
            skipped.append({"version_id": version_id, "reason": "version_active"})
            continue

        await workshop_service.sync_version_required_tools(
            version_id=version_id,
            required_tools=list(resolved_tools),
            default_tools=list(resolved_default_tools),
            max_tool_calls=int(max_tool_calls),
        )
        synced_version_ids.append(version_id)

    if synced_version_ids:
        logger.info(
            "Synchronized tool candidate Agent %s is bound to the Agent Workshop version: %s",
            agent_id,
            ", ".join(synced_version_ids),
        )

    return {
        "status": "ok" if synced_version_ids else "skipped",
        "reason": None if synced_version_ids else "no_sync_target",
        "attempted_version_ids": target_version_ids,
        "synced_version_ids": synced_version_ids,
        "skipped": skipped,
    }


async def _auto_build_workshop_version_result(session_id: str) -> dict[str, Any]:
    return _parse_json_tool_result(await build_agent_workshop_version.ainvoke({
        "session_id": session_id,
    }))


def _extract_governance_version_id(version_result: dict[str, Any] | None) -> str | None:
    """Safely extract version_id from build_workshop_version results, compatible with version field being dict or str."""
    if not isinstance(version_result, dict):
        return None
    version = version_result.get("version")
    if isinstance(version, dict):
        return str(version.get("version_id") or "").strip() or None
    if isinstance(version, str):
        return version.strip() or None
    return None


def _looks_unspecified(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    vague_markers = {
        "不知道",
        "未定",
        "待定",
        "随便",
        "你决定",
        "都可以",
        "暂时没有",
        "none",
        "unknown",
        "tbd",
        "na",
        "n/a",
    }
    return text in vague_markers


def _generate_short_agent_name_llm(user_request: str, target_responsibility: str = "") -> dict:
    """Use LLM to synchronously generate a short Agent Chinese name and English slug (called in the synchronization tool function).

    LLM When failed, use simple pinyin/hash to find out (no longer use keyword mapping table).
    Return {"name": "Chinese name", "slug": "english_slug"}
    """
    text = f"{target_responsibility or ''} {user_request or ''}".strip()
    if not text:
        return {"name": "智能分析助手", "slug": "intelligent_analysis"}

    try:
        from app.core.database import get_mongo_db_sync
        from core.llm import UnifiedLLMClient
        from core.llm.models import Message

        # Read LLM configuration synchronously
        sync_db = get_mongo_db_sync()
        config_doc = sync_db.system_configs.find_one(
            {"is_active": True},
            sort=[("version", -1)],
        )
        if not config_doc or "llm_configs" not in config_doc:
            logger.warning("[AgentName][LLM] No active LLM configuration, use Pinyin to cover")
            return _generate_simple_slug_fallback(user_request, target_responsibility)

        # Reuse the model selection logic of intelligent_assistant_service (synchronization part)
        from app.services.intelligent_assistant_service import _resolve_models, _selection_model_name, _selection_config_id, resolve_llm_config_from_config_doc
        _, deep_selection, reasoning_selection, _ = _resolve_models(config_doc)
        target_selection = reasoning_selection or deep_selection
        target_model = _selection_model_name(target_selection)
        target_config_id = _selection_config_id(target_selection)
        if not target_model:
            logger.warning("[AgentName][LLM] Unable to parse the model name, use pinyin to find out. (reasoning=%s deep=%s)", reasoning_selection, deep_selection)
            return _generate_simple_slug_fallback(user_request, target_responsibility)

        config = resolve_llm_config_from_config_doc(
            config_doc,
            target_model=target_model,
            target_config_id=target_config_id,
            purpose="agent_naming",
        )
        if not config:
            logger.warning("[AgentName][LLM] Unable to build LLM configuration (model=%s config_id=%s), Use pinyin to tell the truth", target_model, target_config_id)
            return _generate_simple_slug_fallback(user_request, target_responsibility)

        client = UnifiedLLMClient.from_config(config)

        system_prompt = """You are an expert in agent naming. Based on user needs and responsibility descriptions, generate a short, professional, and easy-to-remember Agent Chinese name and corresponding English logo (slug).

Naming rules:
 [Chinese name]
1. The name must be short: no more than 12 Chinese characters (can include English abbreviation such as DCF/PE/PB)
2. The name must reflect the Agent s core business capabilities and should not contain"For A shares""listed company""execute""output"redundant words
3. Name starts with"Assistant"or"expert"end (default"Assistant") 
4. Do not use"Agent"this English word

 [English slug]
1. All lowercase, separated by underscores, can only contain letters, numbers, and underscores
2. Length is controlled between 3-40 characters
3. Accurately reflect the Agent s core business capabilities, giving priority to professional terminology
4. to "_analyst" or "_assistant" ending (more specific by default)
5. Do not use "agent", "nanobot", "candidate" meaningless words

Output format (strictly JSON, no explanation):
{"name": "Chinese name", "slug": "english_slug"}

Example:
- demand"Perform multi-dimensional valuation analysis on A-share listed companies" → {"name": "Multi-dimensional valuation analysis assistant", "slug": "multidimensional_valuation_analyst"}
- demand"Help me create a financial report demining assistant" → {"name": "Financial report demining assistant", "slug": "financial_risk_screener"}
- demand"Analyze dividend rates and dividends" → {"name": "Dividend Yield Analysis Assistant", "slug": "dividend_yield_analyst"}
- demand"Make a DCF valuation tool" → {"name": "DCF Valuation Assistant", "slug": "dcf_valuation_assistant"}
- demand"Create a technical analysis Agent" → {"name": "Technical analysis assistant", "slug": "technical_analysis_assistant"}
- demand"Conduct risk demining on listed companies" → {"name": "Risk demining assistant", "slug": "risk_screening_assistant"}
- demand"Generate research reports" → {"name": "Research report generation assistant", "slug": "research_report_generator"}"""

        user_prompt = f"User needs:{user_request or '(Not provided)'}\n Responsibilities Description:{target_responsibility or '(Not provided)'}\n\n Please generate the Chinese name and English slug of Agent (strictly output JSON):"

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ]
        # DeepSeek The inference model will output the thinking process first and then JSON, which requires sufficient token quota.
        response = client.chat(messages, temperature=0.3, max_tokens=1000)
        raw_content = str(response.content or "").strip()

        logger.info("[AgentName][LLM] original response: %s", raw_content[:400])

        # Try to parse JSON (support inference model output thinking text before and after JSON)
        import json as _json
        try:
            cleaned = raw_content.strip()
            # Remove markdown code block tags
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```$", "", cleaned)
            # First try to extract JSON objects from text
            json_match = re.search(r'\{[^{}]*"name"[^{}]*"slug"[^{}]*\}', cleaned, re.DOTALL)
            if not json_match:
                # Relaxed matching: find the last one { to the last one } content between
                last_brace = cleaned.rfind("{")
                last_close = cleaned.rfind("}")
                if last_brace >= 0 and last_close > last_brace:
                    json_match = re.search(
                        r'\{.*\}', cleaned[last_brace:last_close + 1], re.DOTALL
                    )
                    if json_match:
                        cleaned = json_match.group(0)
            if json_match and json_match is not cleaned:
                cleaned = json_match.group(0)
            result = _json.loads(cleaned)
            name = str(result.get("name", "")).strip()
            slug = str(result.get("slug", "")).strip().lower()
            logger.info("[AgentName][LLM] Parsed successfully: name=%s slug=%s", name, slug)
        except Exception as parse_exc:
            # JSON Parsing failed, trying to intelligently extract names from text
            logger.warning("[AgentName][LLM] JSON Parsing failed: %s, raw=%s", parse_exc, raw_content[:200])
            # Try to extract from think text "Chinese name:xxx" or "Name:xxx" mode
            name = ""
            slug = ""
            name_match = re.search(r'(?:Chinese name|name)[: :]\s*([^\n. ]{2,12})', raw_content)
            if name_match:
                name = name_match.group(1).strip()
            if not name:
                # Try to find slug pattern: "English slug:xxx"
                slug_match = re.search(r'(?:English\s*slug|slug)[: :]\s*([a-z][a-z0-9_]{2,39})', raw_content)
                if slug_match:
                    slug = slug_match.group(1).strip().lower()
                # The final tip: take the first line
                name = raw_content.strip().strip("\"'""''「」【】 ").split("\n")[0].strip()
                name = name.rstrip("。.；;")

        # Clean up Chinese names
        name = name.rstrip("。.；;")

        # Verify slug format
        import re as _re
        if not slug or not _re.match(r"^[a-z][a-z0-9_]{2,39}$", slug):
            # slug Non-compliance, use simple pinyin to explain
            logger.warning("[AgentName][LLM] slug Non-compliance: slug=%r, Use pinyin to tell the truth", slug)
            slug = _generate_simple_slug_fallback(name or user_request, target_responsibility)["slug"]

        if name and len(name) <= 20:
            logger.info("[AgentName][LLM] final result: request=%s -> name=%s slug=%s", user_request[:40], name, slug)
            return {"name": name, "slug": slug}

        logger.warning("[AgentName][LLM] The name is illegal: name=%r (len=%d), Use pinyin to tell the truth", name, len(name or ""))
        return _generate_simple_slug_fallback(user_request, target_responsibility)
    except Exception as exc:
        logger.error("[AgentName][LLM] LLM Naming anomaly: %s", exc, exc_info=True)
        return _generate_simple_slug_fallback(user_request, target_responsibility)


def _fallback_slug_from_name(name: str, user_request: str = "", target_responsibility: str = "") -> str:
    """Simple back-up: Generate hash slug from text (the naming is handled by LLM, this is just the final back-up)."""
    text = f"{name or ''} {target_responsibility or ''} {user_request or ''}".strip()
    if not text:
        return "analysis_assistant"
    import hashlib
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()[:6]
    # Try to extract prefix from English name (if English is available)
    import re as _re
    english_parts = _re.findall(r'[a-zA-Z]{2,}', text)
    if english_parts:
        prefix = english_parts[0].lower()[:15]
        return f"{prefix}_assistant_{digest}"
    return f"analysis_assistant_{digest}"


def _generate_simple_slug_fallback(user_request: str, target_responsibility: str = "") -> dict:
    """LLM Simple explanation when naming fails (no longer using keyword mapping).

    Return {"name": "Chinese name", "slug": "english_slug"}
    """
    text = f"{target_responsibility or ''} {user_request or ''}".strip()
    if not text:
        return {"name": "智能分析助手", "slug": "intelligent_analysis_assistant"}

    # Extract first 10 words from requirement as short name
    short_name = text[:10].rstrip(", . , Yes") + "助手"
    slug = _fallback_slug_from_name(short_name, user_request, target_responsibility)
    return {"name": short_name, "slug": slug}


# Keep the old name as an alias, compatible with references to agent_builder_nodes.py
_generate_short_agent_name_fallback = _generate_simple_slug_fallback


def _contains_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return any(keyword in lowered for keyword in keywords)


def _is_stock_analysis_request(*values: str) -> bool:
    keywords = (
        "估值",
        "valuation",
        "股票",
        "a股",
        "stock",
        "pe",
        "pb",
        "peg",
        "ticker",
    )
    return any(_contains_any_keyword(value, keywords) for value in values)


def _is_output_preview_request(*values: str) -> bool:
    text = " ".join(str(value or "").strip().lower() for value in values if str(value or "").strip())
    if not text:
        return False

    if not any(keyword in text for keyword in _REPORT_KEYWORDS):
        return False

    preview_cues = any(keyword in text for keyword in _OUTPUT_PREVIEW_KEYWORDS)
    question_cues = any(
        cue in text
        for cue in (
            "什么样",
            "长什么样",
            "示例",
            "例子",
            "长这样",
            "looks like",
            "example",
        )
    )
    return preview_cues or question_cues


def _is_report_like_request(*values: str) -> bool:
    return any(_contains_any_keyword(value, _REPORT_KEYWORDS) for value in values)


def _build_temp_agent_spec_for_confirmation(
    *,
    agent_id: str,
    agent_name: str,
    responsibility: str,
    output_field: str,
    desired_output_shape: str,
    non_goals: list[str],
    constraints: list[str],
    valuation_method_scope: str,
    tool_ids: list[str],
) -> AgentSpec:
    capability_requirements = []
    for idx, text in enumerate([responsibility, desired_output_shape, valuation_method_scope], start=1):
        clean_text = str(text or "").strip()
        if not clean_text:
            continue
        capability_requirements.append({
            "capability_key": f"requirement_{idx}",
            "capability_name": clean_text[:40],
            "capability_type": "orchestration" if idx == 1 else "output",
            "description": clean_text,
            "delivery_requirement": "tool-or-prompt",
            "acceptance_criteria": ["Deliver within the boundaries of the confirmed draft and do not exceed a single responsibility"],
        })
    preferred_methods = [item for item in [valuation_method_scope] if str(item or "").strip()]
    if tool_ids:
        preferred_methods.append("Candidate tools:" + "、".join(tool_ids))
    return AgentSpec(
        spec_id=agent_id,
        name=agent_name,
        domain="stock_analysis" if _is_stock_analysis_request(agent_name, responsibility, desired_output_shape) else "general",
        primary_goal=responsibility,
        responsibilities=[responsibility],
        non_goals=non_goals,
        inputs=[AgentSpecIOField(name="symbol", type="string", required=False, description="股票代码或用户输入标的")],
        outputs=[AgentSpecIOField(name=str(output_field or "analysis_report").strip() or "analysis_report", type="string", description=desired_output_shape or "分析报告")],
        constraints=constraints,
        preferred_methods=preferred_methods,
        capability_requirements=capability_requirements,
        status=AgentSpecStatus.DRAFT,
        source="nanobot_prepare",
    )


def _build_capability_inventory_from_hits(hits: list[Any]) -> dict[str, Any]:
    formatted: list[dict[str, Any]] = []
    available_tools: list[str] = []
    available_skills: list[str] = []
    missing_capabilities: list[str] = []
    for hit in hits or []:
        try:
            item = _format_capability_hit(hit)
        except Exception:
            continue
        formatted.append(item)
        tool_id = str(item.get("registry_tool_id") or item.get("capability_id") or "").strip()
        source_type = str(item.get("source_type") or "").strip().lower()
        if tool_id and source_type in {"skill", "external_skill"}:
            available_skills.append(tool_id)
        elif tool_id:
            available_tools.append(tool_id)
    return {
        "available_tools": _dedupe_string_list(available_tools),
        "available_skills": _dedupe_string_list(available_skills),
        "missing_capabilities": missing_capabilities,
        "results": formatted,
        "count": len(formatted),
    }


def _gap_report_to_dict(gap_report: Any) -> dict[str, Any]:
    if hasattr(gap_report, "model_dump"):
        return gap_report.model_dump(mode="json")
    return dict(gap_report or {}) if isinstance(gap_report, dict) else {}


def _gap_item_to_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("description") or item.get("gap") or item.get("gap_id") or "").strip()
    return str(item or "").strip()


def _quick_plan_feasible(gap_report: dict[str, Any], resolved_tools: list[str]) -> bool:
    blocking = [_gap_item_to_text(item) for item in gap_report.get("blocking_gaps") or []]
    if not resolved_tools:
        return False
    hard_markers = ("外部数据", "新数据源", "实时", "爬取", "api", "接口", "必须补齐", "无法降级")
    return not any(any(marker in gap for marker in hard_markers) for gap in blocking)


def _build_candidate_plans(gap_report: dict[str, Any], resolved_tools: list[str]) -> tuple[list[dict[str, Any]], str]:
    blocking_gaps = [_gap_item_to_text(item) for item in gap_report.get("blocking_gaps") or [] if _gap_item_to_text(item)]
    blocking_count = len(blocking_gaps)
    plans: list[dict[str, Any]] = []
    label_ord = ord("A")

    def add_plan(plan_id: str, name: str, description: str, recommended: bool, risk: str, required_new_skills: list[str] | None = None) -> None:
        nonlocal label_ord
        display_label = chr(label_ord)
        label_ord += 1
        plans.append({
            "plan_id": plan_id,
            "display_label": display_label,
            "plan_name": name,
            "name": f"{display_label}. {name}",
            "description": description,
            "required_new_skills": required_new_skills or [],
            "acknowledged_gaps": blocking_gaps if plan_id in {"complete", "quick"} else [],
            "estimated_effort": "低" if plan_id in {"direct", "quick"} else "中-高" if plan_id == "complete" else "待重新确认",
            "risk": risk,
            "recommended": recommended,
        })

    if blocking_count == 0:
        add_plan("direct", "推荐完整交付", "The existing capabilities have covered the requirements and can directly generate a complete version of Agent and enter real data testing according to the original core risk/analysis dimensions.", True, "Low: The main risk comes from real data quality and subsequent acceptance results.")
        add_plan("strict", "保守可追溯版", "Existing capabilities are still used, but output boundaries are tightened: only conclusions clearly supported by tools and data are output, and parts that are not covered or have insufficient data are marked as information gaps.", False, "Low: Coverage is more robust, but reporting expressions will be more conservative.")
        add_plan("enhanced", "扩展增强版", "On the basis that the core requirements have been met, non-blocking enhancements can be used as optional extensions, such as more detailed warning classification, more risk signals or richer scenario descriptions.", False, "Medium: Not required for current delivery, too much extension will increase testing and interpretation complexity.")
        return plans, "direct"

    suggested_skills = []
    for item in list(gap_report.get("suggested_tools") or []) + list(gap_report.get("suggested_capabilities") or []):
        if isinstance(item, dict):
            tool_id = str(item.get("tool_id") or item.get("capability_id") or "").strip()
            if tool_id:
                suggested_skills.append(tool_id)
    add_plan("complete", "完整方案", "First recognize and fill blocking gaps, and then generate a complete Agent, retaining the original demand target and output depth.", True, "It requires replenishing abilities or generating Skills, which is more time-consuming but has a complete goal.", _dedupe_string_list(suggested_skills))
    if _quick_plan_feasible(gap_report, resolved_tools):
        add_plan("quick", "快速方案", "Instead of adding new capabilities, use existing tools to generate a simplified version first; missing fields mark information gaps and do not output a comprehensive four-color rating.", False, "The coverage is limited and is suitable for trial run verification first.")
    if blocking_count >= 3:
        add_plan("narrow", "缩小需求范围", "First go back to requirements redefinition, narrow the target or output scope, and then re-inventory capabilities.", False, "The user is required to reconfirm the scope and is not generated directly.")
    return plans, "complete"


def _plan_options_for_intent(candidate_plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "index": idx + 1,
            "id": str(plan.get("plan_id") or ""),
            "name": str(plan.get("name") or plan.get("plan_name") or plan.get("plan_id") or ""),
            "description": str(plan.get("description") or ""),
            "display_label": str(plan.get("display_label") or ""),
            "selected_plan_id": str(plan.get("plan_id") or ""),
            "acknowledged_gaps": list(plan.get("acknowledged_gaps") or []),
        }
        for idx, plan in enumerate(candidate_plans)
    ]


def _quick_plan_constraint_text(acknowledged_gaps: list[str] | None = None) -> str:
    gap_text = "；".join([str(item).strip() for item in acknowledged_gaps or [] if str(item).strip()])
    suffix = f" Known gaps:{gap_text}" if gap_text else ""
    return (
        "quick Solution constraints: Only existing bound tools are allowed to be used to directly return traceable indicators; missing fields must be marked as information gaps;"
        "It is prohibited to require the LLM to calculate key audit/financial/valuation indicators by itself; it is prohibited to create a comprehensive four-color rating by itself or use missing data to piece together the rating."
        + suffix
    )


def _parse_acknowledged_gaps(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return _dedupe_string_list([str(item or "").strip() for item in raw if str(item or "").strip()])
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return _dedupe_string_list([str(item or "").strip() for item in parsed if str(item or "").strip()])
    except Exception:
        pass
    return _parse_string_list(text)

def _humanize_preview_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized in {"structure_skeleton", "skeleton", "outline", ""}:
        return "只看结构骨架"
    if normalized in {"placeholder_mock", "mock", "placeholder"}:
        return "允许占位符 mock"
    return str(mode or "未指定").strip() or "未指定"


def _join_display_items(values: list[str], default: str = "未指定") -> str:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return "、".join(cleaned) if cleaned else default


def _build_confirmation_template(
    *,
    agent_id: str,
    agent_name: str,
    responsibility: str,
    desired_output_shape: str,
    output_field: str,
    bound_tools: list[str],
    non_goals: list[str],
    valuation_method_scope: str,
    test_strategy: str,
    report_contract: dict[str, Any] | None,
    overwrite_risk: dict[str, Any],
) -> str:
    """Construct the user confirmation draft in the tone of a financial product expert to avoid technical list-style output.

    After the system receives this template, it should communicate with the user from the perspective of a financial product consultant——
    Talk about the analysis framework and business value, rather than reading tool IDs and technical parameters line by line.
    The technical binding information required by the backend is passed in other fields of the JSON.
    """
    # ── Business narrative version confirmation draft (not technical checklist) ──
    lines = [
        "【方案概览】",
        f"Name:{agent_name}",
        f"Positioning:{responsibility}",
        f"Output:{desired_output_shape}",
    ]

    scope_parts = []
    if valuation_method_scope:
        scope_parts.append(f"Valuation method:{valuation_method_scope}")
    if resolved_default_tools := bound_tools:
        # Do not list tool_id, just say which dimensions are covered
        pass  # Dimension coverage is provided by the business description of capability_inventory
    lines.append("")

    if non_goals:
        lines.append("【明确不做的】")
        for item in non_goals:
            lines.append(f"- {item}")
        lines.append("")

    if report_contract is not None:
        forbidden_items = report_contract.get("forbidden_expansions") or []
        lines.append("【报告内容边界】")
        lines.append(f"Chapter scope:{report_contract.get('content_scope') or 'Valuation analysis chapters that match the responsibilities'}")
        lines.append(f"Preview method:{_humanize_preview_mode(str(report_contract.get('style_preview_mode') or ''))}")
        if forbidden_items:
            lines.append(f"Explicitly excluded:{_join_display_items(forbidden_items, default='None')}")
        lines.append("")

    # Covering risks
    overwrite_text = "Existing configurations will be overwritten and explicit consent from the user is required." if overwrite_risk.get("requires_explicit_overwrite") else "不影响现有配置"
    lines.append(f"【覆盖影响】{overwrite_text}")
    lines.append("")

    # Confirm boot
    lines.append("If the above content is confirmed to be correct, please reply: Confirm")
    if overwrite_risk.get("requires_explicit_overwrite"):
        lines.append(" (Note: The existing configuration will be overwritten when the Agent is subsequently generated)")

    return "\n".join(lines)


def _normalize_recommendation_policy(_: str = "") -> str:
    return f"{_GLOBAL_NO_TRADING_ADVICE_POLICY}\n\n{_GLOBAL_NUMERICAL_TOOL_POLICY}"


def _append_trading_guard(text: str) -> str:
    clean_text = str(text or "").strip()
    if not clean_text:
        return f"{_GLOBAL_NO_TRADING_ADVICE_POLICY}\n\n{_GLOBAL_NUMERICAL_TOOL_POLICY}"
    if _GLOBAL_NO_TRADING_ADVICE_POLICY in clean_text and _GLOBAL_NUMERICAL_TOOL_POLICY in clean_text:
        return clean_text
    if _GLOBAL_NO_TRADING_ADVICE_POLICY in clean_text:
        return f"{clean_text}\n\n{_GLOBAL_NUMERICAL_TOOL_POLICY}"
    if _GLOBAL_NUMERICAL_TOOL_POLICY in clean_text:
        return f"{clean_text}\n\n{_GLOBAL_NO_TRADING_ADVICE_POLICY}"
    return f"{clean_text}\n\n{_GLOBAL_NO_TRADING_ADVICE_POLICY}\n\n{_GLOBAL_NUMERICAL_TOOL_POLICY}"


def _append_trading_guard_constraint(text: str) -> str:
    clean_text = str(text or "").strip()
    if _GLOBAL_NO_TRADING_ADVICE_POLICY in clean_text and _GLOBAL_NUMERICAL_TOOL_POLICY in clean_text:
        return clean_text
    if _GLOBAL_NO_TRADING_ADVICE_POLICY in clean_text:
        return f"{clean_text}\n{_GLOBAL_NUMERICAL_TOOL_POLICY}"
    if _GLOBAL_NUMERICAL_TOOL_POLICY in clean_text:
        return f"{clean_text}\n{_GLOBAL_NO_TRADING_ADVICE_POLICY}"
    if not clean_text:
        return f"{_GLOBAL_NO_TRADING_ADVICE_POLICY}\n{_GLOBAL_NUMERICAL_TOOL_POLICY}"
    return f"{clean_text}\n{_GLOBAL_NO_TRADING_ADVICE_POLICY}\n{_GLOBAL_NUMERICAL_TOOL_POLICY}"


def _match_keyword(keyword: str, *values: Any) -> bool:
    keyword_text = str(keyword or "").strip().lower()
    if not keyword_text:
        return True
    haystack = " ".join(str(value or "") for value in values).lower()
    return keyword_text in haystack


def _format_capability_hit(hit: CapabilitySearchHit) -> dict[str, Any]:
    capability = hit.capability
    return {
        "capability_id": capability.capability_id,
        "registry_tool_id": capability.registry_tool_id,
        "source_type": capability.source_type,
        "category": capability.category,
        "name": capability.name,
        "description": capability.description,
        "when_to_use": capability.when_to_use,
        "when_not_to_use": capability.when_not_to_use,
        "returns": capability.returns,
        "related_tools": capability.related_tools,
        "coverage_terms": capability.coverage_terms,
        "data_source": capability.data_source,
        "bindable": capability.bindable,
        "fc_enabled": capability.fc_enabled,
        "status": capability.status,
        "metadata": capability.metadata,
        "score": round(hit.score, 4),
    }


def _format_agent_metadata(metadata) -> dict[str, Any]:
    return {
        "id": metadata.id,
        "name": metadata.name,
        "description": metadata.description,
        "category": metadata.category,
        "version": metadata.version,
        "maintenance_status": metadata.maintenance_status,
        "callable_surfaces": metadata.callable_surfaces,
        "input_mode": metadata.input_mode,
        "tools": metadata.tools,
        "default_tools": metadata.default_tools,
        "max_tool_calls": metadata.max_tool_calls,
        "depends_on": metadata.depends_on,
        "tags": metadata.tags,
        "inputs": [item.model_dump(mode="json") for item in metadata.inputs],
        "outputs": [item.model_dump(mode="json") for item in metadata.outputs],
        "requires_tools": metadata.requires_tools,
        "output_field": metadata.output_field,
        "report_label": metadata.report_label,
        "node_name": metadata.node_name,
        "execution_order": metadata.execution_order,
    }


def _format_runtime_agent_config(doc: dict[str, Any], bound_tools: list[str], registry_metadata: Any | None) -> dict[str, Any]:
    agent_id = str(doc.get("agent_id") or "").strip()
    config_tools = doc.get("tools") or []
    default_tools = doc.get("default_tools") or []
    runtime_tools = bound_tools or config_tools or default_tools
    runtime_mode = "builtin_override" if registry_metadata is not None else "universal_agent"
    return {
        "agent_id": agent_id,
        "name": doc.get("name") or doc.get("agent_name") or agent_id,
        "description": doc.get("description") or "",
        "output_field": doc.get("output_field") or "analysis_report",
        "runtime_mode": runtime_mode,
        "has_builtin_blueprint": registry_metadata is not None,
        "bound_tools": bound_tools,
        "config_tools": config_tools,
        "default_tools": default_tools,
        "effective_tools": runtime_tools,
        "max_tool_calls": doc.get("max_tool_calls"),
        "status": doc.get("status") or doc.get("metadata", {}).get("status") or "unknown",
        "metadata": doc.get("metadata") or {},
        "updated_at": doc.get("updated_at"),
    }


async def _is_orphaned_workshop_runtime_agent(doc: dict[str, Any], db: Any) -> bool:
    metadata = doc.get("metadata") or {}
    source = str(metadata.get("source") or "").strip().lower()
    if source not in {"agent_workshop", "nanobot_generated"}:
        return False

    version_id = str(metadata.get("version_id") or "").strip()
    spec_id = str(metadata.get("spec_id") or "").strip()
    if not version_id and not spec_id:
        return False

    try:
        if version_id:
            version_doc = await _get_collection(db, "agent_versions").find_one({"version_id": version_id}, {"_id": 1})
            if version_doc:
                return False
        if spec_id:
            spec_doc = await _get_collection(db, "agent_specs").find_one({"spec_id": spec_id}, {"_id": 1})
            if spec_doc:
                return False
    except Exception as exc:
        logger.warning("Failed to check whether the Agent lost contact when the workshop was running: %s", exc)
        return False

    return True


def _format_agent_spec(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "spec_id": doc.get("spec_id"),
        "name": doc.get("name"),
        "domain": doc.get("domain"),
        "primary_goal": doc.get("primary_goal"),
        "responsibilities": doc.get("responsibilities") or [],
        "status": doc.get("status"),
        "current_version_id": doc.get("current_version_id"),
        "version_count": doc.get("version_count") or 0,
        "owner_user_id": doc.get("owner_user_id") or "",
        "updated_at": doc.get("updated_at"),
    }


def _format_agent_version(doc: dict[str, Any]) -> dict[str, Any]:
    metadata = doc.get("agent_metadata") or {}
    return {
        "version_id": doc.get("version_id"),
        "spec_id": doc.get("spec_id"),
        "version": doc.get("version"),
        "status": doc.get("status"),
        "agent_id": metadata.get("id") or metadata.get("agent_id") or "",
        "agent_name": metadata.get("name") or metadata.get("agent_name") or "",
        "required_tools": doc.get("required_tools") or [],
        "required_capabilities": doc.get("required_capabilities") or doc.get("required_skills") or [],
        "prompt_template_ref": doc.get("prompt_template_ref") or {},
        "updated_at": doc.get("updated_at"),
    }


async def _merge_latest_evaluations_into_versions(
    version_results: list[dict[str, Any]],
    db,
) -> None:
    """Query the latest evaluation records in batches and merge scores/conclusions into version_results."""
    if not version_results:
        return
    version_ids = [str(v.get("version_id") or "").strip() for v in version_results if v.get("version_id")]
    if not version_ids:
        return

    try:
        evaluations_collection = _get_collection(db, _WORKSHOP_EVALUATION_COLLECTION)
        if evaluations_collection is None:
            return

        # Batch query for all related evaluations, in descending order by created_at
        eval_cursor = evaluations_collection.find(
            {"version_id": {"$in": version_ids}},
            {"_id": 0, "evaluation_id": 1, "version_id": 1, "decision": 1, "scores": 1, "issues": 1, "created_at": 1},
        )
        if hasattr(eval_cursor, "sort"):
            eval_cursor = eval_cursor.sort("created_at", -1)

        eval_docs = await eval_cursor.to_list(length=len(version_ids) * 3)

        # Group by version_id and get the latest evaluation of each version
        latest_eval_by_version: dict[str, dict[str, Any]] = {}
        for doc in eval_docs:
            vid = str(doc.get("version_id") or "").strip()
            if vid and vid not in latest_eval_by_version:
                latest_eval_by_version[vid] = doc

        for version in version_results:
            vid = str(version.get("version_id") or "").strip()
            if not vid:
                continue
            eval_doc = latest_eval_by_version.get(vid)
            if not eval_doc:
                continue
            scores = eval_doc.get("scores") or {}
            version["latest_evaluation"] = {
                "decision": str(eval_doc.get("decision") or ""),
                "overall_score": scores.get("overall") if isinstance(scores, dict) else None,
                "issues_count": len(eval_doc.get("issues") or []),
                "evaluation_id": str(eval_doc.get("evaluation_id") or ""),
            }
    except Exception:
        pass


def _format_prompt_template_record(doc: dict[str, Any]) -> dict[str, Any]:
    content = doc.get("content") or {}
    return {
        "template_id": str(doc.get("_id") or doc.get("id") or ""),
        "agent_type": doc.get("agent_type"),
        "agent_name": doc.get("agent_name"),
        "template_name": doc.get("template_name"),
        "workflow_id": doc.get("workflow_id"),
        "node_id": doc.get("node_id"),
        "status": doc.get("status"),
        "version": doc.get("version"),
        "content_fields": sorted(content.keys()) if isinstance(content, dict) else [],
        "updated_at": doc.get("updated_at"),
    }


def _format_prompt_template_detail(doc: dict[str, Any]) -> dict[str, Any]:
    formatted = _format_prompt_template_record(doc)
    content = doc.get("content") or {}
    formatted["content"] = {
        "system_prompt": str(content.get("system_prompt") or "").strip(),
        "user_prompt": str(content.get("user_prompt") or "").strip(),
        "tool_guidance": str(content.get("tool_guidance") or "").strip(),
        "analysis_requirements": str(content.get("analysis_requirements") or "").strip(),
        "output_format": str(content.get("output_format") or "").strip(),
        "constraints": str(content.get("constraints") or "").strip(),
    }
    formatted["remark"] = str(doc.get("remark") or "").strip()
    formatted["is_system"] = bool(doc.get("is_system", False))
    formatted["created_at"] = doc.get("created_at")
    formatted["preference_type"] = doc.get("preference_type")
    return formatted


def _parse_auto_bool(raw: str, default: bool | None = None) -> bool | None:
    text = str(raw or "").strip().lower()
    if not text or text == "auto":
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


async def _resolve_effective_prompt_template_payload(
    *,
    agent_type: str,
    agent_name: str,
    preference_id: str = "neutral",
    workflow_id: str = "",
    node_id: str = "",
    is_debug_mode: bool = False,
    debug_template_id: str = "",
    user_id: str = "",
) -> dict[str, Any]:
    clean_agent_type = str(agent_type or "").strip()
    clean_agent_name = str(agent_name or "").strip()
    if not clean_agent_type or not clean_agent_name:
        return {"status": "error", "message": "agent_type and agent_name cannot be empty"}

    resolved_user_id = str(user_id or "").strip()
    if not resolved_user_id:
        try:
            resolved_user_id = str(require_current_user_id() or "").strip()
        except Exception:
            resolved_user_id = ""

    context = {
        "user_id": resolved_user_id or None,
        "preference_id": str(preference_id or "neutral").strip() or "neutral",
        "workflow_id": str(workflow_id or "").strip() or None,
        "node_id": str(node_id or "").strip() or None,
        "is_debug_mode": bool(is_debug_mode),
        "debug_template_id": str(debug_template_id or "").strip() or None,
    }

    from tradingagents.utils.template_client import get_template_client

    template_client = get_template_client()
    effective = template_client.get_effective_template(
        clean_agent_type,
        clean_agent_name,
        user_id=resolved_user_id or None,
        preference_id=context["preference_id"],
        context=context,
        workflow_id=context["workflow_id"],
        node_id=context["node_id"],
    )
    if not effective:
        return {
            "status": "error",
            "message": "未找到当前生效模板",
            "resolution_input": {
                "agent_type": clean_agent_type,
                "agent_name": clean_agent_name,
                "user_id": resolved_user_id,
                "preference_id": context["preference_id"],
                "workflow_id": context["workflow_id"],
                "node_id": context["node_id"],
                "is_debug_mode": context["is_debug_mode"],
                "debug_template_id": context["debug_template_id"],
            },
        }

    return {
        "status": "ok",
        "resolution_input": {
            "agent_type": clean_agent_type,
            "agent_name": clean_agent_name,
            "user_id": resolved_user_id,
            "preference_id": context["preference_id"],
            "workflow_id": context["workflow_id"],
            "node_id": context["node_id"],
            "is_debug_mode": context["is_debug_mode"],
            "debug_template_id": context["debug_template_id"],
        },
        "template": effective,
    }


async def _resolve_current_thread_effective_template_input(
    *,
    db: Any,
    user_id: str,
    thread_id: str,
    preference_id: str = "neutral",
    workflow_id: str = "",
    node_id: str = "",
    debug_template_id: str = "",
    debug_mode: str = "auto",
    agent_type: str = "",
    agent_name: str = "",
) -> dict[str, Any]:
    clean_user_id = str(user_id or "").strip()
    clean_thread_id = str(thread_id or "").strip()
    if not clean_user_id or not clean_thread_id:
        return {"status": "error", "message": "user_id and thread_id cannot be empty"}

    threads = _get_collection(db, "embedded_nanobot_threads")
    if threads is None:
        return {"status": "error", "message": "The embedded_nanobot_threads collection is not available in the current database"}

    thread_doc = await threads.find_one({"user_id": clean_user_id, "thread_id": clean_thread_id})
    if thread_doc is None:
        thread_doc = await threads.find_one({"user_id": clean_user_id, "session_key": clean_thread_id})
    if thread_doc is None:
        return {"status": "error", "message": f"未找到 thread_id={clean_thread_id} 对应的会话"}

    thread_context = dict(thread_doc.get("thread_context") or {})
    channel = str(thread_doc.get("channel") or "embedded").strip() or "embedded"
    resolved_version_id = str(thread_context.get("version_id") or "").strip()
    resolved_spec_id = str(thread_context.get("spec_id") or "").strip()
    resolved_version_status = str(thread_context.get("version_status") or "").strip()
    explicit_workflow_id = str(thread_context.get("workflow_id") or "").strip()
    explicit_node_id = str(thread_context.get("node_id") or "").strip()
    explicit_preference_id = str(thread_context.get("preference_id") or "").strip()
    explicit_debug_template_id = str(thread_context.get("debug_template_id") or "").strip()

    specs = _get_collection(db, "agent_specs")
    versions = _get_collection(db, "agent_versions")
    if not resolved_version_id and resolved_spec_id and specs is not None:
        spec_doc = await specs.find_one({"spec_id": resolved_spec_id}, {"current_version_id": 1}) or {}
        resolved_version_id = str(spec_doc.get("current_version_id") or "").strip()

    version_doc = None
    if resolved_version_id and versions is not None:
        version_doc = await versions.find_one({"version_id": resolved_version_id})

    resolved_agent_type = str(agent_type or "").strip()
    resolved_agent_name = str(agent_name or "").strip()
    if version_doc is not None:
        if not resolved_agent_type:
            resolved_agent_type = "universal"
        if not resolved_agent_name:
            resolved_agent_name = str(version_doc.get("version_id") or resolved_version_id).strip()

    if not resolved_agent_type or not resolved_agent_name:
        return {
            "status": "error",
            "message": "The current thread lacks enough context to automatically infer agent_type/agent_name; please first let the thread enter a state with version context, or explicitly pass in agent_type and agent_name",
            "thread_context": thread_context,
        }

    template_ref = dict((version_doc or {}).get("prompt_template_ref") or {})
    resolved_debug_template_id = str(debug_template_id or explicit_debug_template_id or template_ref.get("template_id") or "").strip()
    resolved_workflow_id = str(workflow_id or explicit_workflow_id or "").strip()
    if not resolved_workflow_id and resolved_version_id and channel == "agent_workshop":
        resolved_workflow_id = f"agent_workshop_debug_{resolved_version_id}"

    resolved_node_id = str(node_id or explicit_node_id or "").strip()
    requested_preference_id = str(preference_id or "").strip()
    if explicit_preference_id and requested_preference_id in {"", "neutral"}:
        resolved_preference_id = explicit_preference_id
    else:
        resolved_preference_id = requested_preference_id or "neutral"
    explicit_debug_mode = _parse_auto_bool(debug_mode, default=None)
    if explicit_debug_mode is None:
        resolved_is_debug_mode = bool(
            resolved_debug_template_id and (
                channel == "agent_workshop"
                or resolved_version_status.lower() in {"testing", "draft"}
            )
        )
    else:
        resolved_is_debug_mode = explicit_debug_mode

    return {
        "status": "ok",
        "thread_id": str(thread_doc.get("thread_id") or clean_thread_id),
        "session_key": str(thread_doc.get("session_key") or "").strip(),
        "channel": channel,
        "thread_context": thread_context,
        "resolution_input": {
            "agent_type": resolved_agent_type,
            "agent_name": resolved_agent_name,
            "user_id": clean_user_id,
            "preference_id": resolved_preference_id,
            "workflow_id": resolved_workflow_id or None,
            "node_id": resolved_node_id or None,
            "is_debug_mode": resolved_is_debug_mode,
            "debug_template_id": resolved_debug_template_id or None,
        },
        "resolution_source": {
            "resolved_spec_id": resolved_spec_id or None,
            "resolved_version_id": resolved_version_id or None,
            "resolved_version_status": resolved_version_status or None,
            "used_version_doc": bool(version_doc is not None),
            "used_thread_channel": channel,
            "used_explicit_workflow_id": bool(explicit_workflow_id),
            "used_explicit_node_id": bool(explicit_node_id),
            "used_explicit_preference_id": bool(explicit_preference_id),
            "used_explicit_debug_template_id": bool(explicit_debug_template_id),
        },
    }


async def _inspect_agent_overwrite_risk(db: Any, agent_id: str, status: str = "active") -> dict[str, Any]:
    agent_configs = _get_collection(db, "agent_configs")
    prompt_templates = _get_collection(db, "prompt_templates")
    bindings = _get_collection(db, "tool_agent_bindings")

    existing_config = await agent_configs.find_one({"agent_id": agent_id}) if agent_configs is not None else None
    existing_prompt = await prompt_templates.find_one(
        {"agent_type": "universal", "agent_name": agent_id, "workflow_id": None, "node_id": None, "status": status}
    ) if prompt_templates is not None else None
    existing_binding_count = 0
    if bindings is not None:
        binding_cursor = bindings.find({"agent_id": agent_id, "is_active": {"$ne": False}}, {"_id": 0, "tool_id": 1})
        existing_binding_count = len(await binding_cursor.to_list(length=None))

    return {
        "agent_config_exists": existing_config is not None,
        "prompt_template_exists": existing_prompt is not None,
        "existing_binding_count": existing_binding_count,
        "requires_explicit_overwrite": bool(existing_config or existing_prompt or existing_binding_count),
    }


@tool
@register_tool(
    tool_id="prepare_agent_requirement_intake",
    name="Generate Agent requirements collection outline",
    description="Based on the user s initial creation request, generate a requirement collection outline that should be followed up in the next round to avoid directly generating Agents when the requirements are still vague.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use when the user has just come up with the idea of creating an Agent, but the boundaries of responsibilities, output shape, non-goals, or tool dependencies are not yet clear.",
    when_not_to_use="When the requirements are clear and can go directly to the confirmation draft or generation stage, there is no need to call it again.",
    returns="Returns a JSON string containing known information, missing decisions, recommended follow-up questions, and whether it is possible to proceed directly to the confirmation phase.",
    example="prepare_agent_requirement_intake(user_request='Help me do a valuation analysis agent')",
    related_tools=["prepare_agent_generation_confirmation", "generate_confirmed_candidate_agent"],
    data_source_handling="local_only",
)
def prepare_agent_requirement_intake(
    user_request: Annotated[str, "User original request, for example, help me do a valuation analysis agent"],
    target_responsibility: Annotated[str, "Currently known single responsibility, can be left blank"] = "",
    desired_output_shape: Annotated[str, "The currently known output shape, which can be left blank, such as Structured Valuation Report"] = "",
    non_goals: Annotated[str, "Specify what not to do. You can leave it blank and separate it with commas."] = "",
    preferred_tools: Annotated[str, "User s specified or currently known preference tools, comma separated"] = "",
    existing_agent_id: Annotated[str, "If the user mentions that they want to overwrite or continue an existing agent, fill in the existing agent_id"] = "",
    recommendation_policy: Annotated[str, "Whether to allow the output of trading suggestions/positions/price ranges; for example, only do research but not give suggestions"] = "",
    valuation_method_scope: Annotated[str, "Valuation method boundaries, such as PE/PB/PEG only, excluding DCF or comprehensive valuation"] = "",
    test_strategy: Annotated[str, "Whether to allow automatic testing after generation; for example, only configuration verification is performed, and real stock samples are not run."] = "",
    preview_mode: Annotated[str, "If the user is asking about the report style, should we only see the structural skeleton, or should we allow placeholder examples?"] = "",
    report_section_scope: Annotated[str, "Report chapter boundaries, such as only valuation-related chapters, excluding technical aspects/transaction execution plans/multi-scenario research"] = "",
) -> str:
    """Generate requirements gathering outline before Agent creation —— Automatically complete smart default values to promote only the most critical decisions to users."""
    try:
        clean_request = str(user_request or "").strip()
        if not clean_request:
            return _json_response({"status": "error", "message": "user_request cannot be empty"})

        resolved_non_goals = _parse_string_list(non_goals)
        resolved_tools = _parse_string_list(preferred_tools)
        stock_analysis_request = _is_stock_analysis_request(clean_request, target_responsibility, desired_output_shape)
        output_preview_request = _is_output_preview_request(clean_request, desired_output_shape)

        # ── 🔍 Entrance log: demand collection ──
        logger.info(
            "[Intake][Entry] request_len=%d responsibility_len=%d output_shape_len=%d "
            "non_goals_len=%d preferred_tools=%s stock=%s output_preview=%s existing=%s",
            len(clean_request),
            len(str(target_responsibility or "")),
            len(str(desired_output_shape or "")),
            len(str(non_goals or "")),
            str(preferred_tools or "")[:80],
            "yes" if stock_analysis_request else "no",
            "yes" if output_preview_request else "no",
            str(existing_agent_id or ""),
        )
        effective_recommendation_policy = _normalize_recommendation_policy(recommendation_policy)

        # === Intelligent default value: automatic completion when the user does not say anything ===
        smart_defaults = {
            "output_shape": "Structured natural language reporting with ratings/ratings and key data support",
            "non_goals": "No trading advice/position advice/target price range/stop loss and take profit/technical timing",
            "preferred_tools": resolved_tools,  # If empty, let the gap analysis stage automatically recommend
            "creation_mode": "new",  # New by default
            "recommendation_policy": "It only conducts research and analysis, and does not output any buying and selling recommendations, position recommendations, target prices, stop-loss, take-profit and other operational instructions.",
            "valuation_method_scope": "Comprehensive valuation (industry comparison PE/PB + historical valuation quantiles + DCF) , If specified by the user, the user will be given priority.",
            "test_strategy": "auto_test",  # By default, automatic sample verification is allowed.
            "preview_mode": "structure_only",  # Report style preview only looks at the structural skeleton
            "report_section_scope": "Only chapters related to valuation/analysis are retained, and do not extend to technical aspects, transaction execution plans, and multi-scenario research.",
        }

        # Determine the actual value (user provided > smart default)
        effective_output_shape = desired_output_shape if not _looks_unspecified(desired_output_shape) else smart_defaults["output_shape"]
        effective_non_goals = resolved_non_goals if resolved_non_goals else _parse_string_list(smart_defaults["non_goals"])
        effective_tools = resolved_tools if resolved_tools else []
        effective_creation_mode = "new" if not existing_agent_id.strip() else "overwrite"
        effective_valuation_scope = valuation_method_scope if not _looks_unspecified(valuation_method_scope) else smart_defaults["valuation_method_scope"]
        effective_test_strategy = test_strategy if not _looks_unspecified(test_strategy) else smart_defaults["test_strategy"]
        effective_preview_mode = preview_mode if not _looks_unspecified(preview_mode) else smart_defaults["preview_mode"]
        effective_report_scope = report_section_scope if not _looks_unspecified(report_section_scope) else smart_defaults["report_section_scope"]

        # === Elevate only truly critical decisions to users (max 2) ===
        critical_questions: list[dict] = []
        has_critical_single_responsibility_gap = _looks_unspecified(target_responsibility)

        if has_critical_single_responsibility_gap:
            critical_questions.append({
                "id": "single_responsibility",
                "question": "What is this Agent going to do? Please describe its core mission in one sentence.",
                "why_critical": "Without clear boundaries of responsibilities, subsequent tool selection and output structure cannot be accurately matched.",
            })

        if not effective_tools and not has_critical_single_responsibility_gap:
            # Tool preferences are missing but can be automatically recommended when responsibilities are clear
            critical_questions.append({
                "id": "tool_preferences",
                "question": "Do you already know what tools or data sources it must rely on? If there is no preference, I will automatically recommend the most suitable tool during the gap analysis phase.",
                "why_critical": "The scope of tools affects the boundaries of capabilities, but you can also leave it entirely to my recommendation.",
            })

        # === Generate a short Agent name (Chinese name + English slug)===
        naming_result = _generate_short_agent_name_llm(clean_request, target_responsibility)
        proposed_agent_name = naming_result.get("name", "智能分析助手")
        proposed_agent_slug = naming_result.get("slug", "analysis_assistant")

        # === Build proposal ===
        proposed_plan = {
            "single_responsibility": target_responsibility if not has_critical_single_responsibility_gap else "（待确认）",
            "proposed_agent_name": proposed_agent_name,
            "proposed_agent_slug": proposed_agent_slug,
            "output_shape": effective_output_shape,
            "non_goals": effective_non_goals,
            "preferred_tools": effective_tools if effective_tools else "（缺口分析阶段自动推荐）",
            "creation_mode": effective_creation_mode,
            "recommendation_policy": effective_recommendation_policy,
        }
        if stock_analysis_request:
            proposed_plan["valuation_method_scope"] = effective_valuation_scope
            proposed_plan["test_strategy"] = effective_test_strategy
            proposed_plan["preview_mode"] = effective_preview_mode
            proposed_plan["report_section_scope"] = effective_report_scope

        can_proceed_to_confirmation = len(critical_questions) == 0

        # ── 🔍 Export log: demand collection results ──
        logger.info(
            "[Intake][Exit] responsibility=%s output=%s can_proceed=%s critical_q=%d next=%s",
            str(target_responsibility or "")[:80],
            str(desired_output_shape or "")[:80],
            "yes" if can_proceed_to_confirmation else "no",
            len(critical_questions),
            "prepare_agent_generation_confirmation" if can_proceed_to_confirmation else "present_proposed_plan_and_ask_critical_questions",
        )

        # ── Update thread_context: Let FlowController track progress ──
        try:
            from core.embedded_nanobot.intent_context import update_intent_context_in_thread
            stage = "exploring" if not can_proceed_to_confirmation else "draft_preparing"
            pending_q = ""
            pending_opts = []
            if not can_proceed_to_confirmation and critical_questions:
                # Write key questions into the pending state to ensure that cross-turn conversations do not lose context
                pending_q = critical_questions[0]["question"]
                pending_opts = [
                    {"index": i + 1, "id": q["id"], "name": q["question"][:60], "description": q.get("why_critical", "")}
                    for i, q in enumerate(critical_questions[:3])
                ]
            update_intent_context_in_thread(
                action="requirement_intake",
                stage=stage,
                pending_question=pending_q,
                pending_options=pending_opts,
            )
        except Exception:
            pass

        return _json_response({
            "status": "ok",
            "user_request": clean_request,
            "request_profile": {
                "stock_analysis_request": stock_analysis_request,
                "output_preview_request": output_preview_request,
            },
            "proposed_plan": proposed_plan,
            "critical_questions": critical_questions,
            "can_proceed_to_confirmation": can_proceed_to_confirmation,
            "recommended_next_step": (
                "prepare_agent_generation_confirmation" if can_proceed_to_confirmation
                else "present_proposed_plan_and_ask_critical_questions"
            ),
            "nanobot_guidance": (
                "✅ The solution has been automatically completed. You are now a financial product expert, not a questionnaire surveyor.\n\n"
                "Core Principle: Initiate new ideas —— Give your professional draft first and users will naturally correct it.\n\n"
                "Communication rules:\n"
                "1. Present the proposed_plan first, using business language to explain the reasons for each choice.\n"
                "2. If critical_questions is non-empty, at most 1 most critical question will be asked, and the rest will use default values.\n"
                "3. Each question must give context, the differences between the options, your recommendations and your rationale.\n"
                "   For example, instead of saying Which valuation methods do you want to use? , say There are two major categories of valuation: relative valuation (PE/PB/PEG, etc., look at comparison with the same industry) and absolute valuation (DCF, etc., look at intrinsic value). The two are complementary, and I recommend including them both. What do you think? \n"
                "4. Don t list a long list of questions for users to answer one by one. This is the most efficient way to communicate.\n"
                "5. It is forbidden to ask users What data source/data terminal do you use? ——The platform has built-in data sources such as Tushare/AKShare/BaoStock, and the Agent automatically obtains data through tools without user selection.\n"
                "6. If the user says yes , ok and no objection , it will be deemed as approval and will be directly advanced to the confirmation stage.\n"
                "7. For dimensions not mentioned by the user, simply use professional default values to complete them without asking.\n"
                "   For example, if the user does not say whether he wants a risk warning, it will be added by default; if the user does not say whether it is A shares or Hong Kong stocks, it will be added by default.\n"
                "   Users will naturally tell you if they disagree with the default value after seeing it in the draft.\n"
                "8.  [Important] It is prohibited to mention any tool names (such as get_dcf_valuation, get_comparable_company_valuation, etc.) in the reply.\n"
                "   Users don t care which tool is used at the bottom layer, they only care about what business problems the Agent can solve.\n"
                "   Tool binding is an internal matter of the platform and will be automatically processed in the subsequent capability inventory stage. It does not need to and should not be exposed to users.\n"
                "   Correct statement: We will automatically obtain the valuation data of the same industry for horizontal comparison The system will pull the historical valuation range to calculate the quantile \n"
                "   Error: The platform has the get_comparable_company_valuation tool You need to confirm whether the get_historical_valuation_percentile_tool is ready "
            ) if can_proceed_to_confirmation else (
                "✅ The scheme has automatically completed most dimensions. You are now a financial product expert, not a questionnaire surveyor.\n\n"
                "Core Principle: Initiate new ideas —— Give your professional draft first and users will naturally correct it.\n\n"
                "Communication rules:\n"
                "1. The proposed_plan is briefly presented first, explaining the rationale for each default choice.\n"
                "2. For critical_questions, expand up to 1 most critical question, and use default values for the rest.\n"
                "3. Each question must give context, options, your recommendations and reasons. Don t just throw questions.\n"
                "4. Don t list a long list of questions for users to answer one by one.\n"
                "5. For dimensions not mentioned by the user, simply use professional default values to complete them without asking.\n"
                "6. It is forbidden to ask users What data source/data terminal do you use? ——The platform has built-in data sources such as Tushare/AKShare/BaoStock, and the Agent automatically obtains data through tools without user selection.\n"
                "7. If the user says yes , ok and no objection , it will be deemed as approval and will be promoted directly.\n"
                "8.  [Important] It is prohibited to mention any tool names (such as get_dcf_valuation, get_comparable_company_valuation, etc.) in the reply.\n"
                "   Users don t care which tool is used at the bottom layer, they only care about what business problems the Agent can solve.\n"
                "   Tool binding is an internal matter of the platform and will be automatically processed in the subsequent capability inventory stage. It does not need to and should not be exposed to users.\n"
                "   Correct statement: We will automatically obtain the valuation data of the same industry for horizontal comparison The system will pull the historical valuation range to calculate the quantile \n"
                "   Error: The platform has the get_comparable_company_valuation tool You need to confirm whether the get_historical_valuation_percentile_tool is ready "
            ),
        })
    except Exception as exc:
        logger.error("Failed to generate Agent requirements collection outline: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to generate Agent requirements collection outline: {exc}"})


@tool
@register_tool(
    tool_id="prepare_agent_generation_confirmation",
    name="Generate Agent creation confirmation draft",
    description="Before actually writing to the database, a streamlined confirmation draft is generated to clarify the boundaries of responsibilities, output shapes, tool bindings and coverage risks for user confirmation.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when a candidate Agent solution has been formed but has not yet received clear confirmation from the user on the responsibility boundaries, output shape, and coverage risks.",
    when_not_to_use="It is not suitable to directly drop the library to create Agent. It is only responsible for generating confirmation drafts.",
    returns="Returns a JSON string containing the confirmation, coverage risk, and recommended user confirmation.",
    example="prepare_agent_generation_confirmation(agent_id='valuation_candidate_v1', agent_name='Valuation candidates Agent', target_responsibility='Output A-share valuation conclusion', tool_ids='get_value_factor_bundle_tool')",
    related_tools=["generate_confirmed_candidate_agent", "create_or_update_runtime_agent_config"],
    data_source_handling="local_only",
)
async def prepare_agent_generation_confirmation(
    agent_id: Annotated[str, "候选 Agent ID"],
    agent_name: Annotated[str, "Candidate Agent display name"],
    target_responsibility: Annotated[str, "单一职责的一句话描述"],
    tool_ids: Annotated[str, "Tool IDs to be bound, separated by commas"],
    output_field: Annotated[str, "Output field name, default analysis_report"] = "analysis_report",
    default_tools: Annotated[str, "Default tool ID, separated by commas; if empty, the first two items of tool_ids will be taken by default."] = "",
    desired_output_shape: Annotated[str, "Expected output shape description, such as structured valuation report"] = "结构化估值报告",
    non_goals: Annotated[str, "Specify what not to do, separated by commas"] = "",
    recommendation_policy: Annotated[str, "Whether to allow the output of trading suggestions/positions/price ranges; for example, only do research but not give suggestions"] = "",
    valuation_method_scope: Annotated[str, "Valuation method boundaries, such as PE/PB/PEG only, excluding DCF or comprehensive valuation"] = "",
    test_strategy: Annotated[str, "Whether to allow automatic testing after generation; for example, only configuration verification is performed, and real stock samples are not run."] = "",
    preview_mode: Annotated[str, "If the user is asking about the report style, should we only see the structural skeleton, or should we allow placeholder examples?"] = "",
    report_section_scope: Annotated[str, "Report chapter boundaries, such as only valuation-related chapters, excluding technical aspects/transaction execution plans/multi-scenario research"] = "",
    status: Annotated[str, "Target template status, default active"] = "active",
) -> str:
    """Generate Agent creation confirmation draft."""
    try:
        clean_agent_id = str(agent_id or "").strip()
        clean_agent_name = str(agent_name or "").strip()
        clean_responsibility = str(target_responsibility or "").strip()
        if not clean_agent_id or not clean_agent_name or not clean_responsibility:
            return _json_response({"status": "error", "message": "agent_id, agent_name, target_responsibility cannot be empty"})

        # ── 🔍 Entrance log: Generate confirmation draft ──
        logger.info(
            "[Prepare][Entry] agent_id=%s name=%s responsibility_len=%d tool_count=%d",
            clean_agent_id,
            str(clean_agent_name)[:60],
            len(clean_responsibility),
            len(_parse_string_list(tool_ids)),
        )

        resolved_tools = _parse_string_list(tool_ids)
        resolved_default_tools = _parse_string_list(default_tools) or resolved_tools[:2] or list(resolved_tools)
        resolved_non_goals = _parse_string_list(non_goals)
        effective_recommendation_policy = _normalize_recommendation_policy(recommendation_policy)
        output_preview_request = _is_output_preview_request(clean_responsibility, desired_output_shape)
        report_like_request = _is_report_like_request(output_field, desired_output_shape, clean_responsibility)
        # The requirement confirmation phase allows tool_ids to be empty: at this time the confirmation draft only contains responsibilities/outputs/non-goals,
        # Tool candidates are left to be completed during the capability inventory (CAPABILITY_CHECK) stage.
        # Consistent with _build_confirmation_template's handling of empty bound_tools.

        stock_analysis_request = _is_stock_analysis_request(clean_agent_name, clean_responsibility, desired_output_shape)
        # Auto-complete default value, consistent with prepare_agent_requirement_intake
        if stock_analysis_request and not resolved_non_goals:
            resolved_non_goals = _parse_string_list("No trading advice/position advice/target price range/stop loss and take profit/technical timing")
        if stock_analysis_request and _looks_unspecified(valuation_method_scope):
            valuation_method_scope = "Comprehensive valuation (industry comparison PE/PB + historical valuation quantiles + DCF) "
        if stock_analysis_request and _looks_unspecified(test_strategy):
            test_strategy = "auto_test"
        if output_preview_request and _looks_unspecified(preview_mode):
            preview_mode = "structure_only"
        if stock_analysis_request and output_preview_request and _looks_unspecified(report_section_scope):
            report_section_scope = "Only chapters related to valuation/analysis are retained, and do not extend to technical aspects, transaction execution plans, and multi-scenario research."

        registry = get_tool_registry()
        missing_tools = [tool_id for tool_id in resolved_tools if registry.get(tool_id) is None]
        if missing_tools:
            return _json_response({"status": "error", "message": f"以下工具未注册: {', '.join(missing_tools)}", "missing_tools": missing_tools})

        db = get_mongo_db()

        # ── Idempotence protection: overwriting is prohibited when the same agent_id already has an active confirmation draft ──
        try:
            existing_doc = await db["agent_workshop_sessions"].find_one(
                {"agent_id": clean_agent_id, "builder_contracts.stage": "confirmation_pending"},
                {"session_id": 1, "builder_contracts": 1},
            )
        except Exception:
            existing_doc = None
        if existing_doc:
            logger.warning(
                "[Prepare][Idempotent] ⚠️ agent_id=%s There is already an active confirmation draft and overwriting is refused. session_id=%s",
                clean_agent_id,
                existing_doc.get("session_id", ""),
            )
            return _json_response({
                "status": "already_pending",
                "message": (
                    f"Agent `{clean_agent_id}` There is a build plan to be confirmed."
                    f"Please directly guide users to choose plans or respond to questions, and do not repeatedly generate confirmation drafts."
                    f"If the user has explicitly selected an option, call generate_confirmed_candidate_agent."
                ),
            })

        # ── V2 Process: The requirements confirmation phase only confirms responsibilities/outputs/boundaries, does not display tool candidates, and does not perform gap analysis. ──
        # Gap analysis is performed uniformly in the CAPABILITY_CHECK stage after the user confirms their requirements.
        # Capability_inventory / gap_report is not exposed to users at this stage.
        logger.info(
            "[Prepare][RequirementOnly] agent_id=%s name=%s (no capability inventory, no gap analysis)",
            clean_agent_id,
            clean_agent_name,
        )
        overwrite_risk = await _inspect_agent_overwrite_risk(db, clean_agent_id, status=status)
        report_contract = None
        if report_like_request:
            report_contract = {
                "style_preview_mode": preview_mode or "structure_skeleton",
                "content_scope": report_section_scope or "Only chapters related to currently confirmed responsibilities and shall not be automatically extended to unconfirmed modules",
                "preview_instruction": "In the confirmation phase, only the chapter skeleton/field template is displayed by default without filling in the real content; placeholder mocks are only allowed when explicitly requested by the user.",
                "forbidden_expansions": [
                    "技术分析",
                    "交易执行方案",
                    "多情景研究",
                    "目标价或区间",
                    "仓位建议",
                    "其他操作性指令",
                ],
            }
        user_confirmation_template = _build_confirmation_template(
            agent_id=clean_agent_id,
            agent_name=clean_agent_name,
            responsibility=clean_responsibility,
            desired_output_shape=desired_output_shape,
            output_field=output_field,
            bound_tools=resolved_tools,
            non_goals=resolved_non_goals,
            valuation_method_scope=valuation_method_scope,
            test_strategy=test_strategy,
            report_contract=report_contract,
            overwrite_risk=overwrite_risk,
        )

        pending_question = (
            "The above is my understanding of the requirements of this Agent. Please confirm whether the responsibility boundaries and output shape meet your expectations."
            "If it is correct, please reply Confirm ; if you need to make adjustments, please tell me the modification points directly."
        )

        # Update intent context: wait for user confirmation of requirement
        _auto_update_intent(
            action="create_agent",
            stage="requirement_confirmation_pending",
            spec_id=clean_agent_id,
            spec_name=clean_agent_name,
            intent_summary=f"Create Agent:{clean_responsibility}",
            pending_options=[],
            proposed_items=[],
            pending_question=pending_question,
            active_subtask="等待用户确认需求",
            next_action="After the user confirms the requirement, enter CAPABILITY_CHECK and call search_project_capabilities + analyze_agent_workshop_gaps",
        )

        # ── 🔍 Trace log: Confirm prepare phase output ──
        logger.info(
            "[Prepare][Output] agent_id=%s confirmation_type=requirement_confirmation "
            "responsibility_len=%d output_shape_len=%d pending_question_len=%d",
            clean_agent_id,
            len(clean_responsibility),
            len(desired_output_shape or ""),
            len(pending_question),
        )

        return _json_response({
            "status": "ok",
            "confirmation_required": True,
            "ready_to_execute": False,
            "confirmation_type": "requirement_confirmation",
            "nanobot_guidance": (
                "You are now communicating with users as a financial product expert, not a technical architect.\n\n"
                "Core Principle: Initiate new ideas —— Give your professional confirmation draft first, and users will naturally correct it.\n\n"
                "Communication rules:\n"
                "1. Only talk about business value: what this Agent does, what it outputs, and what it doesn t do."
                "Don t say several tools are bound or list tool_id.\n"
                "2. Don t show a capability inventory: users don t need to know what tools the system has;"
                "Just need to know what problem the Agent can solve.\n"
                "3. Do not give plans in advance: only the needs are confirmed at this stage, and the plans will be released after the needs are confirmed."
                "Give it after completing the ability inventory.\n"
                "4. Don t ask a series of questions: the requirements are automatically completed with default values via proposed_plan,"
                "Present the confirmation draft directly, allowing users to make corrections naturally after seeing the draft.\n"
                "5. It is forbidden to ask users What data source/data terminal do you use? ——The platform has built-in data sources such as Tushare/AKShare/BaoStock, and the Agent automatically obtains data through tools without user selection.\n"
                "6. The user replies with any approval expression such as confirm , ok , ok , etc."
                "It is considered that the demand has been confirmed and the next stage is to do a capability inventory."
            ),
            "pending_question": pending_question,
            "confirmation_brief": {
                "target_responsibility": clean_responsibility,
                "proposed_agent_id": clean_agent_id,
                "proposed_agent_name": clean_agent_name,
                "desired_output_shape": desired_output_shape,
                "output_field": output_field,
                "chosen_build_path": "create_universal_agent",
                "confirmation_type": "requirement_confirmation",
                "agent_id": clean_agent_id,
                "agent_name": clean_agent_name,
                "target_responsibility": clean_responsibility,
                "desired_output_shape": desired_output_shape,
                "output_field": output_field,
                "bound_tools": resolved_tools,
                "default_tools": resolved_default_tools,
                "non_goals": resolved_non_goals,
                "recommendation_policy": effective_recommendation_policy,
                "valuation_method_scope": valuation_method_scope,
                "test_strategy": test_strategy,
                "report_contract": report_contract,
                "report_contract_display": {
                    "content_scope": report_contract["content_scope"] if report_contract else "不适用",
                    "style_preview_mode": _humanize_preview_mode(str(report_contract["style_preview_mode"])) if report_contract else "不适用",
                    "preview_instruction": report_contract["preview_instruction"] if report_contract else "不适用",
                    "forbidden_expansions": report_contract["forbidden_expansions"] if report_contract else [],
                },
                "preview_mode": preview_mode,
                "report_section_scope": report_section_scope,
                "overwrite_risk": overwrite_risk,
                "user_confirmation_template": user_confirmation_template,
                "required_user_confirmations": [
                    "Boundary of responsibilities: Does this Agent meet your expectations about what it should do and what it should not do?",
                    "Output content: Does the structure of the report/analysis cover the dimensions you care about?",
                    "Analysis approach: Are the valuation logic and coverage accurate?",
                ],
                "suggested_user_reply": f"Confirm;allow_overwrite={'yes' if overwrite_risk['requires_explicit_overwrite'] else 'no'}",
            },
        })
    except Exception as exc:
        logger.error("Failed to generate Agent creation confirmation draft: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to generate Agent creation confirmation draft: {exc}"})


@tool
@register_tool(
    tool_id="propose_agent_build_plans",
    name="基于缺口分析生成候选方案",
    description="After the requirements are confirmed, 2-4 Agent construction plans (recommended full version/strict delivery version/extended enhanced version/downgraded version) are generated based on gap_report for users to choose from.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use=(
        "After user needs have been confirmed and capability inventory and gap analysis have been completed,"
        "Use it when you need to translate technical gaps into multiple feasible solutions that users can understand."
    ),
    when_not_to_use=(
        "Don t call it before the requirement is confirmed; don t call it when there is no gap_report."
        "This tool is only responsible for generating solutions and does not perform Agent creation."
    ),
    returns=(
        "Returns a JSON string containing candidate_plans (fixed fields), recommended_plan_id, pending_question."
    ),
    example="propose_agent_build_plans(gap_report_json='{\"blocking_gaps\":[],\"non_blocking_gaps\":[]}')",
    related_tools=["search_project_capabilities", "analyze_agent_workshop_gaps", "generate_confirmed_candidate_agent"],
    data_source_handling="local_only",
)
async def propose_agent_build_plans(
    gap_report_json: Annotated[str, "JSON String, including blocking_gaps, non_blocking_gaps, suggested_tools, etc."],
    agent_responsibility: Annotated[str, "Agent Responsibility descriptions to generate more relevant solutions"] = "",
    agent_output_shape: Annotated[str, "Agent 输出形状描述"] = "",
) -> str:
    """Generate candidate build solutions based on gap analysis reports."""
    try:
        gap_report = _parse_optional_json_object(gap_report_json, "gap_report_json")
        blocking_gaps = gap_report.get("blocking_gaps") or []
        non_blocking_gaps = gap_report.get("non_blocking_gaps") or []
        inferable_gaps = gap_report.get("inferable_gaps") or []
        if not isinstance(blocking_gaps, list):
            blocking_gaps = []
        if not isinstance(non_blocking_gaps, list):
            non_blocking_gaps = []
        if not isinstance(inferable_gaps, list):
            inferable_gaps = []

        # Construct LLM prompt words
        system_prompt = (
            "You are a senior financial product expert. Your task is to analyze the results based on the system s capability gaps,"
            "Generate 2-4 clear, executable, and comparable Agent construction plans for users. Even if there is no blocking gap, candidates for different delivery orientations must be given, not just one set.\n\n"
            "Rules:\n"
            "1. The output must be valid JSON and do not contain markdown code block tags.\n"
            "2. Describe the solution in business language and do not expose internal tool IDs or technical details.\n"
            "3. Number of plans:\n"
            "   - 0 A blocking gap: at least three sets of direct (recommended for complete delivery), strict (conservative traceable version) and enhanced (enhanced version) are provided; enhanced can only be used as an optional extension, and required gaps cannot be forged.\n"
            "   - 1-2 A blocking gap: provide complete (complete), quick (downgrade first) and strict (narrow to traceable range).\n"
            "   - 3 and above blocking gaps: three sets of complete, quick, and narrow are provided.\n"
            "4. complete The scheme must list required_new_skills (skills that need to be generated/reused).\n"
            "5. quick/strict The plan must describe which outputs will be downgraded, narrowed or require a more stringent data basis.\n"
            "6. narrow The plan must propose a narrowed scope of responsibilities.\n"
            "7. Recommended_plan_id must be set: direct is recommended when there are 0 blocking gaps; complete is recommended by default when there are blocking gaps.\n"
            "8. Each solution must contain a gap_summary field that describes the data coverage under the solution: which data are supported by direct tools, which are obtained through inference, and which are missing.\n"
            "9. Each solution must include a feasibility field that describes the feasibility of implementation: whether it can be implemented, what difficulties there are, and what additional development or data access is required.\n"
            "10. For solutions with blocking_gaps, it must be clearly stated in the feasibility whether these gaps can be filled, the method of filling (new Skill/access to external data/downgrade processing) and the impact of failure to fill.\n"
        )

        user_prompt = (
            f"Agent Responsibilities:{agent_responsibility or ' (not provided)'}\n"
            f"Agent Output:{agent_output_shape or ' (not provided)'}\n\n"
            "Capability gap analysis results:\n"
            f"blocking_gaps (Blocking gaps, unachievable dimensions of analysis) Number:{len(blocking_gaps)}\n"
            f"blocking_gaps Details:{_json_compact_dump(blocking_gaps)}\n"
            f"inferable_gaps (The gap can be inferred, and there is relevant data that can be qualitatively inferred but not blocked) Quantity:{len(inferable_gaps)}\n"
            f"inferable_gaps Details:{_json_compact_dump(inferable_gaps)}\n"
            f"non_blocking_gaps (Other non-blocking gaps) quantity:{len(non_blocking_gaps)}\n"
            f"non_blocking_gaps Details:{_json_compact_dump(non_blocking_gaps)}\n\n"
            "Please output in the following fixed JSON format:\n"
            "{\n"
            '  "candidate_plans": [\n'
            '    {"plan_id": "direct|strict|enhanced|complete|quick|narrow", "plan_name": "...", "description": "...", "required_new_skills": [...], "estimated_effort": "high|in|low", "risk": "...", "gap_summary": "Description of the data coverage of this plan", "feasibility": "Implementation feasibility description, including whether it can be achieved, difficulties and supplementary methods", "recommended": true|false}\n'
            '  ],\n'
            '  "recommended_plan_id": "...",\n'
            '  "pending_question": "..."\n'
            "}"
        )

        plan_data = None
        try:
            db = get_mongo_db()
            from app.services.intelligent_assistant_service import get_reasoning_llm_config
            from core.llm import UnifiedLLMClient
            from core.llm.models import Message

            config = await get_reasoning_llm_config(db)
            if not config:
                raise ValueError("No available default inference model configuration was found in the system")
            client = UnifiedLLMClient.from_config(config)

            messages = [
                Message(role="system", content=system_prompt),
                Message(role="user", content=user_prompt),
            ]
            response = await client.achat(messages, temperature=0.3, max_tokens=4000)
            raw_content = str(response.content or "").strip()

            # Try to extract from markdown code block JSON
            plan_payload = _extract_json_from_markdown(raw_content) or raw_content
            try:
                plan_data = json.loads(plan_payload)
            except Exception as exc:
                logger.warning("[ProposePlans][ParseFailed] raw=%s exc=%s", raw_content[:500], exc)
        except Exception as exc:
            logger.warning("[ProposePlans][LLMFallback] using rule-based plans because llm failed: %s", exc, exc_info=True)

        if not isinstance(plan_data, dict):
            plan_data = _fallback_build_plans(blocking_gaps, non_blocking_gaps)

        candidate_plans = plan_data.get("candidate_plans") or []
        recommended_plan_id = str(plan_data.get("recommended_plan_id") or "").strip()
        if not candidate_plans:
            candidate_plans = _fallback_build_plans(blocking_gaps, non_blocking_gaps).get("candidate_plans", [])
        if not recommended_plan_id:
            recommended_plan_id = candidate_plans[0].get("plan_id") if candidate_plans else "direct"

        # Standardize the fields of each plan
        normalized_plans = []
        for p in candidate_plans:
            plan_id = str(p.get("plan_id") or "").strip()
            if not plan_id:
                continue
            normalized_plans.append({
                "plan_id": plan_id,
                "plan_name": str(p.get("plan_name") or _humanize_plan_id(plan_id)),
                "description": str(p.get("description") or ""),
                "required_new_skills": _to_str_list(p.get("required_new_skills")),
                "estimated_effort": str(p.get("estimated_effort") or "中"),
                "risk": str(p.get("risk") or ""),
                "gap_summary": str(p.get("gap_summary") or ""),
                "feasibility": str(p.get("feasibility") or ""),
                "recommended": bool(p.get("recommended", False)),
            })

        # Safety net: When LLM still only returns one set, it will be supplemented to comparable solutions according to the rules to avoid the solution selection stage from degenerating into a single choice.
        min_expected = 3 if len(blocking_gaps) == 0 else 2
        if len(normalized_plans) < min_expected:
            fallback_plans = _fallback_build_plans(blocking_gaps, non_blocking_gaps).get("candidate_plans", [])
            seen_plan_ids = {str(p.get("plan_id") or "").strip() for p in normalized_plans}
            for fallback_plan in fallback_plans:
                fallback_plan_id = str(fallback_plan.get("plan_id") or "").strip()
                if not fallback_plan_id or fallback_plan_id in seen_plan_ids:
                    continue
                normalized_plans.append({
                    "plan_id": fallback_plan_id,
                    "plan_name": str(fallback_plan.get("plan_name") or _humanize_plan_id(fallback_plan_id)),
                    "description": str(fallback_plan.get("description") or ""),
                    "required_new_skills": _to_str_list(fallback_plan.get("required_new_skills")),
                    "estimated_effort": str(fallback_plan.get("estimated_effort") or "中"),
                    "risk": str(fallback_plan.get("risk") or ""),
                    "gap_summary": str(fallback_plan.get("gap_summary") or ""),
                    "feasibility": str(fallback_plan.get("feasibility") or ""),
                    "recommended": bool(fallback_plan.get("recommended", False)),
                })
                seen_plan_ids.add(fallback_plan_id)
                if len(normalized_plans) >= min_expected:
                    break

        if recommended_plan_id not in {p.get("plan_id") for p in normalized_plans}:
            fallback_recommended = str(_fallback_build_plans(blocking_gaps, non_blocking_gaps).get("recommended_plan_id") or "").strip()
            recommended_plan_id = fallback_recommended or (normalized_plans[0].get("plan_id") if normalized_plans else "direct")

        # Make sure the recommended flag matches recommended_plan_id
        for p in normalized_plans:
            p["recommended"] = (p["plan_id"] == recommended_plan_id)

        pending_question = str(plan_data.get("pending_question") or "Which option do you want to adopt?").strip()

        # Update intent context: wait for user to select plan
        pending_options = [
            {
                "index": i + 1,
                "id": p["plan_id"],
                "name": p["plan_name"],
                "description": p["description"],
                "recommended": bool(p.get("recommended")),
                "acknowledged_gaps": blocking_gaps if p["plan_id"] in {"complete", "quick"} else [],
                "gap_summary": p.get("gap_summary", ""),
                "feasibility": p.get("feasibility", ""),
            }
            for i, p in enumerate(normalized_plans)
        ]
        _auto_update_intent(
            action="create_agent",
            stage="plan_selection_pending",
            intent_summary="Wait for the user to select the Agent build plan",
            pending_options=pending_options,
            proposed_items=[{"index": i + 1, "id": p["plan_id"], "name": p["plan_name"]} for i, p in enumerate(normalized_plans)],
            pending_question=pending_question,
            active_subtask="等待用户选择方案",
            next_action="After the user selects the plan, call generate_confirmed_candidate_agent and pass in selected_plan_id and acknowledged_gaps",
        )

        logger.info(
            "[ProposePlans][Output] plan_count=%d recommended=%s blocking_gaps=%d pending_options=%d option_ids=%s",
            len(normalized_plans),
            recommended_plan_id,
            len(blocking_gaps),
            len(pending_options),
            [opt.get("id") for opt in pending_options],
        )

        return _json_response({
            "status": "ok",
            "candidate_plans": normalized_plans,
            "recommended_plan_id": recommended_plan_id,
            "pending_question": pending_question,
            "pending_options": pending_options,
            "nanobot_guidance": (
                "You are now a financial product expert. When presenting solutions to users:\n"
                "1. Explain the differences between each option in business terms.\n"
                "2. Do not expose internal codenames such as direct/strict/enhanced/complete/quick/narrow.\n"
                "3. Clearly explain the differences between each plan in terms of delivery scope, degree of conservatism, whether to supplement capabilities, and whether to expand and enhance.\n"
                "4. The user replies with any approval expressions such as Choose A , Follow the recommendations , Confirm , etc."
                "It is considered that recommended_plan_id has been selected and generate_confirmed_candidate_agent is called directly."
            ),
        })
    except Exception as exc:
        logger.error("生成候选方案失败: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"生成候选方案失败: {exc}"})


@tool
@register_tool(
    tool_id="search_project_capabilities",
    name="搜索项目能力",
    description="Lightly search for reusable tools, skills, external skills and MCP capabilities in the current project for resource reconnaissance before Agent design.", 
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use=(
        "Use it when you need to confirm what types of capabilities are already in the warehouse before deciding how to design or create a new Agent."
        "It is suitable to search based on required keywords instead of directly guessing the tool name."
    ),
    when_not_to_use=(
        "It is not suitable for directly performing stock analysis, nor is it suitable for directly generating the final Agent implementation."
        "It is only responsible for resource reconnaissance and capability confirmation."
    ),
    returns=(
        "Returns a JSON string, including capability_id, source_type, category, description, when_to_use,"
        "related_tools, bindable, metadata.parameters Summary of other abilities."
    ),
    example="search_project_capabilities(query='A Stock Valuation Industry Comparison Factors', top_k=8)",
    related_tools=["inspect_agent_blueprints", "get_agent_blueprint_details"],
    data_source_handling="local_only",
)
async def search_project_capabilities(
    query: Annotated[str, "Capability retrieval requirements, such as A-share valuation, industry comparison, portfolio review, and report generation"],
    top_k: Annotated[int, "Number of results returned, default 8, maximum 20"] = 8,
    bindable_only: Annotated[bool, "Whether to only return capabilities that can be directly bound to the Agent, default true"] = True,
    source_types: Annotated[str, "Filter by capability source, separated by commas, such as builtin_tool,skill,mcp_tool"] = "builtin_tool,skill,external_skill,mcp_tool",
) -> str:
    """Search items now have the ability for Nanobot to do resource reconnaissance before creating an Agent."""
    try:
        db = get_mongo_db()
        service = CapabilityIndexService(db)
        hits = await service.search_capabilities(
            query=query,
            top_k=max(1, min(int(top_k), 20)),
            bindable_only=bindable_only,
            source_types=_parse_source_types(source_types),
        )
        return _json_response({
            "query": query,
            "bindable_only": bindable_only,
            "source_types": _parse_source_types(source_types),
            "count": len(hits),
            "results": [_format_capability_hit(hit) for hit in hits],
        })
    except Exception as exc:
        logger.error("搜索项目能力失败: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"搜索项目能力失败: {exc}"})


@tool
@register_tool(
    tool_id="inspect_runtime_agent_configs",
    name="View runtime Agent configuration",
    description="Check the configured Agent runtime definitions in the database, including agent_configs and tool_agent_bindings, to determine whether the UniversalAgent base can be directly reused.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use=(
        "When you need to confirm whether a database-driven dedicated Agent already exists in the project,"
        "Or determine whether a certain ability can be passed UniversalAgent + agent_configs Used for direct loading."
    ),
    when_not_to_use="Not suitable for executing Agents, nor for searching for common tool capabilities; it only looks at runtime Agent definitions in the database.",
    returns=(
        "Returns a JSON string, including runtime_mode, effective_tools, output_field, metadata,"
        "And whether the configuration overrides the built-in blueprint."
    ),
    example="inspect_runtime_agent_configs(keyword='Valuation', limit=5)",
    related_tools=["inspect_agent_workshop_assets", "inspect_agent_blueprints", "search_project_capabilities"],
    data_source_handling="local_only",
)
async def inspect_runtime_agent_configs(
    keyword: Annotated[str, "Fuzzy filter by agent_id, name, description, metadata, can be left blank"] = "",
    limit: Annotated[int, "Number of items returned, default 10, maximum 20"] = 10,
    include_builtin_overrides: Annotated[bool, "Whether to include the database override configuration of the built-in Agent, default true"] = True,
) -> str:
    """View the runtime Agent configuration in the database."""
    try:
        db = get_mongo_db()
        agent_configs = _get_collection(db, "agent_configs")
        if agent_configs is None:
            return _json_response({"status": "error", "message": "The agent_configs collection is not available in the current database"})

        registry = get_registry()
        capped_limit = max(1, min(int(limit), 20))
        cursor = agent_configs.find({}, {"_id": 0})
        if hasattr(cursor, "sort"):
            cursor = cursor.sort("updated_at", -1)
        docs = await cursor.to_list(length=max(capped_limit * 5, 20))

        bindings_collection = _get_collection(db, "tool_agent_bindings")
        results: list[dict[str, Any]] = []
        for doc in docs:
            agent_id = str(doc.get("agent_id") or "").strip()
            if not agent_id:
                continue
            if await _is_orphaned_workshop_runtime_agent(doc, db):
                continue
            registry_metadata = registry.get_metadata(agent_id)
            if not include_builtin_overrides and registry_metadata is not None:
                continue

            bound_tools: list[str] = []
            if bindings_collection is not None:
                binding_cursor = bindings_collection.find(
                    {"agent_id": agent_id, "is_active": {"$ne": False}},
                    {"_id": 0, "tool_id": 1, "priority": 1},
                )
                if hasattr(binding_cursor, "sort"):
                    binding_cursor = binding_cursor.sort("priority", 1)
                binding_docs = await binding_cursor.to_list(length=None)
                bound_tools = [str(item.get("tool_id") or "").strip() for item in binding_docs if item.get("tool_id")]

            formatted = _format_runtime_agent_config(doc, bound_tools, registry_metadata)
            if not _match_keyword(
                keyword,
                formatted.get("agent_id"),
                formatted.get("name"),
                formatted.get("description"),
                formatted.get("runtime_mode"),
                formatted.get("effective_tools"),
                formatted.get("metadata"),
            ):
                continue
            results.append(formatted)
            if len(results) >= capped_limit:
                break

        return _json_response({
            "keyword": keyword,
            "include_builtin_overrides": include_builtin_overrides,
            "count": len(results),
            "results": results,
            "design_references": [
                "docs/05-design/v3.0/ai-workflow-generation.md",
                "docs/05-design/v3.0/agent-workshop-interface-sequence.md",
                "docs/05-design/v3.0/implementation-status-report.md",
            ],
        })
    except Exception as exc:
        logger.error("Failed to view runtime Agent configuration: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to view runtime Agent configuration: {exc}"})


@tool
@register_tool(
    tool_id="inspect_agent_blueprints",
    name="查看 Agent 蓝图",
    description="View the metadata blueprint of the registered Agent in the current warehouse, which is used to select the closest starting point for the new Agent.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use=(
        "Used when you need to determine which existing Agent mode should be reused."
        "It is suitable to filter by keywords, categories or maintenance status first, and then decide which implementation to read."
    ),
    when_not_to_use="It is not suitable to directly output the final implementation code. What it provides is a structured blueprint summary of existing Agents.",
    returns=(
        "Returns a JSON string, including agent_id, description, tools, default_tools, inputs, outputs,"
        "callable_surfaces, maintenance_status metadata."
    ),
    example="inspect_agent_blueprints(keyword='Valuation', category='analyst', limit=5)",
    related_tools=["get_agent_blueprint_details", "search_project_capabilities"],
    data_source_handling="local_only",
)
def inspect_agent_blueprints(
    keyword: Annotated[str, "Fuzzy filter by name, description, label, tool name, can be left blank"] = "",
    category: Annotated[str, "Filter by Agent category, such as analyst, can be left blank"] = "",
    limit: Annotated[int, "Number of items returned, default 10, maximum 20"] = 10,
    maintained_only: Annotated[bool, "Whether to exclude blueprints marked unmaintained by default"] = True,
) -> str:
    """View reusable Agent blueprints in the current project."""
    try:
        registry = get_registry()
        items = registry.list_all()
        keyword_text = str(keyword or "").strip().lower()
        category_text = str(category or "").strip().lower()
        results: list[dict[str, Any]] = []
        for metadata in items:
            maintenance_status = str(metadata.maintenance_status or "")
            if maintained_only and maintenance_status == "unmaintained":
                continue
            if category_text and str(metadata.category or "").lower() != category_text:
                continue
            if keyword_text:
                haystack = " ".join([
                    str(metadata.id or ""),
                    str(metadata.name or ""),
                    str(metadata.description or ""),
                    " ".join(metadata.tags or []),
                    " ".join(metadata.tools or []),
                ]).lower()
                if keyword_text not in haystack:
                    continue
            results.append(_format_agent_metadata(metadata))
            if len(results) >= max(1, min(int(limit), 20)):
                break
        return _json_response({
            "keyword": keyword,
            "category": category,
            "maintained_only": maintained_only,
            "count": len(results),
            "results": results,
        })
    except Exception as exc:
        logger.error("Failed to view Agent blueprint: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to view Agent blueprint: {exc}"})


@tool
@register_tool(
    tool_id="get_agent_blueprint_details",
    name="View Agent Blueprint Details",
    description="View the complete metadata blueprint of a single registered Agent to confirm its suitability as a template or reference object for a new Agent.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use=(
        "When the candidate Agent has been found through inspect_agent_blueprints,"
        "Use it when further confirmation of input and output, default tools, dependencies, and call surfaces is required."
    ),
    when_not_to_use="Not suitable for searching capability sets; filter candidates first and then look at details.",
    returns="Returns a JSON string containing complete metadata details for a single Agent.",
    example="get_agent_blueprint_details(agent_id='valuation_analyst_v2')",
    related_tools=["inspect_agent_blueprints", "search_project_capabilities"],
    data_source_handling="local_only",
)
def get_agent_blueprint_details(
    agent_id: Annotated[str, "Registered Agent ID, such as valuation_analyst_v2"]
) -> str:
    """View individual Agent blueprint details."""
    try:
        registry = get_registry()
        metadata = registry.get_metadata(agent_id)
        if metadata is None:
            return _json_response({"status": "not_found", "message": f"Agent blueprint not found: {agent_id}"})
        return _json_response({
            "status": "ok",
            "agent": _format_agent_metadata(metadata),
            "suggested_reference_files": [
                "core/agents/config.py",
                "core/agents/adapters/",
            ],
        })
    except Exception as exc:
        logger.error("Failed to view Agent blueprint details: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to view Agent blueprint details: {exc}"})


@tool
@register_tool(
    tool_id="inspect_agent_workshop_assets",
    name="View Agent Workshop Assets",
    description="View the summary of agent_specs and agent_versions in the database, and support precise verification by keyword, workshop_session_id or spec_id/version_id/agent_id, which is used to confirm whether there are reusable configured Agent specifications, versions or prompt word assets.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use=(
        "Use it when you need to confirm whether there are Agent specifications, built versions, or prompt words assets that are close to the requirements."
        "It is suitable to look at the existing configuration assets before deciding to create a new one, or to do precise verification when the current thread knows the workshop_session_id/spec_id/version_id."
        "**important**: Under the agent_workshop channel, if the current thread has a selected Agent (thread_context contains spec_id/version_id),"
        "If no filter parameters are specified when calling, this tool will automatically return only the assets of the currently selected Agent instead of searching in full."
        "If you really need to view all assets, please explicitly pass in keyword='' or other filter parameters."
    ),
    when_not_to_use="It is not suitable for general tool search, nor is it suitable for directly publishing Agents; it only summarizes workshop asset summaries.",
    returns=(
        "Returns a JSON string, including spec summary, version summary, required_tools, required_capabilities,"
        "prompt_template_ref and other information, as well as the precise filtering conditions after this use or analysis."
    ),
    example="inspect_agent_workshop_assets(workshop_session_id='session_001')",
    related_tools=["inspect_runtime_agent_configs", "inspect_agent_blueprints", "search_project_capabilities"],
    data_source_handling="local_only",
)
async def inspect_agent_workshop_assets(
    keyword: Annotated[str, "Fuzzy filter by spec name, target, version agent_metadata, can be left blank"] = "",
    workshop_session_id: Annotated[str, "Accurately locate the current spec/version according to the Agent workshop session_id, which can be left blank."] = "",
    spec_id: Annotated[str, "Filter precisely by spec_id, which can be left blank; suitable for scenarios where the spec_id is known to the current thread"] = "",
    version_id: Annotated[str, "Filter accurately by version_id, which can be left blank; suitable for scenarios where the version_id of the current thread is known"] = "",
    agent_id: Annotated[str, "Exact filter by runtime agent_id, can be left blank"] = "",
    limit: Annotated[int, "Number of results returned for each category, default 10, maximum 20"] = 10,
    include_archived: Annotated[bool, "Whether to include the spec/version of archived status, default false"] = False,
) -> str:
    """View the Agent Workshop Asset Summary."""
    try:
        db = get_mongo_db()
        sessions_collection = _get_collection(db, _WORKSHOP_SESSION_COLLECTION)
        specs_collection = _get_collection(db, "agent_specs")
        versions_collection = _get_collection(db, "agent_versions")
        if specs_collection is None or versions_collection is None:
            return _json_response({"status": "error", "message": "The agent_specs or agent_versions collections are not available in the current database"})

        capped_limit = max(1, min(int(limit), 20))
        clean_keyword = str(keyword or "").strip()
        clean_workshop_session_id = str(workshop_session_id or "").strip()
        clean_spec_id = str(spec_id or "").strip()
        clean_version_id = str(version_id or "").strip()
        clean_agent_id = str(agent_id or "").strip()

        # 🔥 Automatically use thread context: When there is no explicit filter parameter, use the current thread's spec_id/version_id
        has_explicit_filters = bool(
            clean_keyword
            or clean_workshop_session_id
            or clean_spec_id
            or clean_version_id
            or clean_agent_id
        )
        if not has_explicit_filters:
            # priority use EmbededNanobotService.chat() Passed in and written to contextvar thread_context
            thread_context = get_current_assistant_thread_context()
            context_spec_id = str(thread_context.get("spec_id") or "").strip()
            context_version_id = str(thread_context.get("version_id") or "").strip()
            if not context_spec_id and not context_version_id:
                # contextvar No → Return to DB to check embedded_nanobot_threads
                current_thread_id = get_current_assistant_thread_id()
                if current_thread_id:
                    try:
                        threads_collection = _get_collection(db, "embedded_nanobot_threads")
                        if threads_collection is not None:
                            thread_doc = await threads_collection.find_one(
                                {"$or": [{"thread_id": current_thread_id}, {"session_key": current_thread_id}]}
                            )
                            if thread_doc:
                                thread_context2 = dict(thread_doc.get("thread_context") or {})
                                context_spec_id = str(thread_context2.get("spec_id") or "").strip()
                                context_version_id = str(thread_context2.get("version_id") or "").strip()
                    except Exception as ctx_exc:
                        logger.debug("Automatic reading of thread context failed, continue to use unfiltered mode: %s", ctx_exc)
            if context_spec_id:
                clean_spec_id = context_spec_id
                logger.info(
                    "[AgentWorkshop][ThreadContextFilter] auto spec_id=%s (from thread_context contextvar or DB)",
                    context_spec_id,
                )
                # 🔥 Automatically set intent context
                _auto_update_intent(
                    action="check_status",
                    stage="",
                    spec_id=context_spec_id,
                    spec_name=str(thread_context.get("spec_name") or "").strip() or context_spec_id,
                    intent_summary="View the progress and status of the current Agent",
                )
            if context_version_id:
                clean_version_id = context_version_id
                logger.info(
                    "[AgentWorkshop][ThreadContextFilter] auto version_id=%s (from thread_context contextvar or DB)",
                    context_version_id,
                )
            if not clean_spec_id and not clean_version_id:
                logger.info(
                    "[AgentWorkshop][ThreadContextFilter] no spec_id/version_id in thread_context, returning unfiltered results"
                )

        resolved_spec_id = clean_spec_id
        resolved_version_id = clean_version_id
        if clean_workshop_session_id:
            if sessions_collection is None:
                return _json_response({
                    "status": "error",
                    "message": "The agent_workshop_sessions collection is not available in the current database and cannot be verified by workshop_session_id",
                })
            session_doc = await sessions_collection.find_one({"session_id": clean_workshop_session_id})
            if session_doc is None:
                return _json_response({
                    "status": "ok",
                    "keyword": clean_keyword,
                    "workshop_session_id": clean_workshop_session_id,
                    "spec_id": clean_spec_id,
                    "version_id": clean_version_id,
                    "agent_id": clean_agent_id,
                    "include_archived": include_archived,
                    "spec_count": 0,
                    "version_count": 0,
                    "specs": [],
                    "versions": [],
                    "message": f"not found session_id={clean_workshop_session_id} Corresponding Agent Workshop session",
                    "design_references": [
                        "docs/05-design/v3.0/agent-workshop-interface-sequence.md",
                        "docs/05-design/v3.0/implementation-status-report.md",
                    ],
                })
            spec_snapshot = _read_mapping_or_attr(session_doc, "current_spec_snapshot", {}) or {}
            if not resolved_spec_id:
                resolved_spec_id = str(
                    session_doc.get("spec_id")
                    or _read_mapping_or_attr(spec_snapshot, "spec_id", "")
                    or ""
                ).strip()
            if not resolved_version_id:
                resolved_version_id = str(
                    _read_mapping_or_attr(spec_snapshot, "current_version_id", "")
                    or session_doc.get("current_version_id")
                    or ""
                ).strip()

        resolved_spec_doc = None
        if resolved_spec_id:
            resolved_spec_doc = await specs_collection.find_one({"spec_id": resolved_spec_id})
            if resolved_spec_doc is not None and not resolved_version_id:
                resolved_version_id = str(resolved_spec_doc.get("current_version_id") or "").strip()

        specs_cursor = specs_collection.find({}, {"_id": 0})
        versions_cursor = versions_collection.find({}, {"_id": 0})
        if hasattr(specs_cursor, "sort"):
            specs_cursor = specs_cursor.sort("updated_at", -1)
        if hasattr(versions_cursor, "sort"):
            versions_cursor = versions_cursor.sort("updated_at", -1)

        spec_docs = await specs_cursor.to_list(length=max(capped_limit * 5, 20))
        version_docs = await versions_cursor.to_list(length=max(capped_limit * 5, 20))

        matched_spec_ids_from_versions: set[str] = set()

        spec_results: list[dict[str, Any]] = []
        for doc in spec_docs:
            if not include_archived and str(doc.get("status") or "") == "archived":
                continue
            formatted = _format_agent_spec(doc)
            if resolved_spec_id and str(formatted.get("spec_id") or "").strip() != resolved_spec_id:
                continue
            if not resolved_spec_id and not resolved_version_id and not clean_agent_id and not clean_workshop_session_id and not _match_keyword(
                clean_keyword,
                formatted.get("spec_id"),
                formatted.get("name"),
                formatted.get("domain"),
                formatted.get("primary_goal"),
                formatted.get("responsibilities"),
            ):
                continue
            spec_results.append(formatted)
            if len(spec_results) >= capped_limit:
                break

        version_results: list[dict[str, Any]] = []
        for doc in version_docs:
            if not include_archived and str(doc.get("status") or "") == "archived":
                continue
            formatted = _format_agent_version(doc)
            if resolved_spec_id and str(formatted.get("spec_id") or "").strip() != resolved_spec_id:
                continue
            if resolved_version_id and str(formatted.get("version_id") or "").strip() != resolved_version_id:
                continue
            if clean_agent_id and str(formatted.get("agent_id") or "").strip() != clean_agent_id:
                continue
            if not resolved_spec_id and not resolved_version_id and not clean_agent_id and not clean_workshop_session_id and not _match_keyword(
                clean_keyword,
                formatted.get("version_id"),
                formatted.get("spec_id"),
                formatted.get("agent_id"),
                formatted.get("agent_name"),
                formatted.get("required_tools"),
                formatted.get("required_capabilities"),
            ):
                continue
            version_results.append(formatted)
            if formatted.get("spec_id"):
                matched_spec_ids_from_versions.add(str(formatted.get("spec_id")))
            if len(version_results) >= capped_limit:
                break

        if matched_spec_ids_from_versions and not clean_spec_id:
            existing_spec_ids = {str(item.get("spec_id") or "") for item in spec_results}
            for doc in spec_docs:
                if not include_archived and str(doc.get("status") or "") == "archived":
                    continue
                formatted = _format_agent_spec(doc)
                formatted_spec_id = str(formatted.get("spec_id") or "")
                if formatted_spec_id not in matched_spec_ids_from_versions or formatted_spec_id in existing_spec_ids:
                    continue
                spec_results.append(formatted)
                existing_spec_ids.add(formatted_spec_id)
                if len(spec_results) >= capped_limit:
                    break

        # 🔥 Get the latest evaluation data of each version in batches to avoid Nanobot relying on stale dialogue memory
        await _merge_latest_evaluations_into_versions(version_results, db)

        return _json_response({
            "keyword": clean_keyword,
            "workshop_session_id": clean_workshop_session_id,
            "spec_id": resolved_spec_id,
            "version_id": resolved_version_id,
            "agent_id": clean_agent_id,
            "include_archived": include_archived,
            "spec_count": len(spec_results),
            "version_count": len(version_results),
            "specs": spec_results,
            "versions": version_results,
            "design_references": [
                "docs/05-design/v3.0/agent-workshop-interface-sequence.md",
                "docs/05-design/v3.0/implementation-status-report.md",
            ],
        })
    except Exception as exc:
        logger.error("Failed to view Agent workshop assets: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to view Agent workshop assets: {exc}"})


@tool
@register_tool(
    tool_id="inspect_prompt_templates",
    name="查看提示词模板库",
    description="Query the template summary of the prompt_templates collection in the database, supporting filtering by agent_type, agent_name, status and keywords.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when you need to confirm which prompt word templates are in the database, which templates are currently bound to an Agent, or when you want to check template assets.",
    when_not_to_use="It is not suitable to directly modify the template text; only reading and filtering are done.",
    returns="Returns a JSON string containing a list of template summaries.",
    example="inspect_prompt_templates(agent_type='universal', keyword='Valuation', status='active', limit=10)",
    related_tools=["get_prompt_template_detail", "inspect_agent_workshop_assets", "create_or_update_universal_agent_prompt_template"],
    data_source_handling="local_only",
)
async def inspect_prompt_templates(
    agent_type: Annotated[str, "Filter accurately by agent_type, can be left blank"] = "",
    agent_name: Annotated[str, "Filter accurately by agent_name, can be left blank"] = "",
    status: Annotated[str, "Filter by status, such as active/draft, which can be left blank"] = "",
    keyword: Annotated[str, "Fuzzy filter by template_name, agent_name, remark, can be left blank"] = "",
    is_system_only: Annotated[bool, "Whether to view only system templates, default false"] = False,
    limit: Annotated[int, "Number of items returned, default 10, maximum 50"] = 10,
) -> str:
    """View a summary of prompt word templates in the database."""
    try:
        db = get_mongo_db()
        templates = _get_collection(db, "prompt_templates")
        if templates is None:
            return _json_response({"status": "error", "message": "The prompt_templates collection is not available in the current database"})

        capped_limit = max(1, min(int(limit), 50))
        cursor = templates.find({}, {"_id": 1, "agent_type": 1, "agent_name": 1, "template_name": 1, "workflow_id": 1, "node_id": 1, "status": 1, "is_system": 1, "remark": 1, "updated_at": 1, "version": 1})
        if hasattr(cursor, "sort"):
            cursor = cursor.sort("updated_at", -1)
        docs = await cursor.to_list(length=max(capped_limit * 5, 50))

        clean_agent_type = str(agent_type or "").strip()
        clean_agent_name = str(agent_name or "").strip()
        clean_status = str(status or "").strip()

        results: list[dict[str, Any]] = []
        for doc in docs:
            if clean_agent_type and str(doc.get("agent_type") or "").strip() != clean_agent_type:
                continue
            if clean_agent_name and str(doc.get("agent_name") or "").strip() != clean_agent_name:
                continue
            if clean_status and str(doc.get("status") or "").strip() != clean_status:
                continue
            if is_system_only and not bool(doc.get("is_system", False)):
                continue
            if not _match_keyword(keyword, doc.get("template_name"), doc.get("agent_name"), doc.get("remark"), doc.get("agent_type")):
                continue
            results.append(_format_prompt_template_record(doc))
            if len(results) >= capped_limit:
                break

        return _json_response({
            "status": "ok",
            "count": len(results),
            "filters": {
                "agent_type": clean_agent_type,
                "agent_name": clean_agent_name,
                "status": clean_status,
                "keyword": keyword,
                "is_system_only": is_system_only,
            },
            "templates": results,
        })
    except Exception as exc:
        logger.error("Failed to view prompt word template library: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"查看提示词模板库失败: {exc}"})


@tool
@register_tool(
    tool_id="get_prompt_template_detail",
    name="查看提示词模板详情",
    description="Read the complete template content of prompt_templates in the database by template_id.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when you already know the template_id and need to view the complete text of system_prompt, tool_guidance, output_format, etc.",
    when_not_to_use="Not suitable for fuzzy searching of template lists; inspect_prompt_templates should be used first in that scenario.",
    returns="Returns a JSON string containing template details and full content field.",
    example="get_prompt_template_detail(template_id='69cfdf8db1828a17f6b00cfb')",
    related_tools=["inspect_prompt_templates", "create_or_update_universal_agent_prompt_template"],
    data_source_handling="local_only",
)
async def get_prompt_template_detail(
    template_id: Annotated[str, "prompt_templates _id string in collection"],
) -> str:
    """View the complete contents of a single prompt word template in the database."""
    try:
        clean_template_id = str(template_id or "").strip()
        if not clean_template_id:
            return _json_response({"status": "error", "message": "template_id cannot be empty"})

        db = get_mongo_db()
        templates = _get_collection(db, "prompt_templates")
        if templates is None:
            return _json_response({"status": "error", "message": "The prompt_templates collection is not available in the current database"})

        cursor = templates.find({})
        docs = await cursor.to_list(length=500)
        matched = next((doc for doc in docs if str(doc.get("_id") or doc.get("id") or "").strip() == clean_template_id), None)
        if matched is None:
            return _json_response({"status": "error", "message": f"未找到 template_id={clean_template_id} 对应的模板"})

        return _json_response({
            "status": "ok",
            "template": _format_prompt_template_detail(matched),
        })
    except Exception as exc:
        logger.error("Failed to view prompt word template details: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"查看提示词模板详情失败: {exc}"})


@tool
@register_tool(
    tool_id="get_effective_prompt_template",
    name="获取当前生效提示词模板",
    description="The current effective template is parsed according to the system s real priority, and supports debugging templates, node-specific templates, process-specific templates, user activation templates and system default templates.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when you need to know which template the current Agent will actually use when debugging or running officially, instead of just looking at the template library list.",
    when_not_to_use="It is not suitable for fuzzy search of template libraries; in that scenario, inspect_prompt_templates should be used first.",
    returns="Returns a JSON string, including the currently effective template content, source, template_id, version and parsing parameters.",
    example="get_effective_prompt_template(agent_type='universal', agent_name='valuation_candidate_v1', workflow_id='wf_001', node_id='node_002', is_debug_mode=true, debug_template_id='69cfdf8db1828a17f6b00cfb')",
    related_tools=["inspect_prompt_templates", "get_prompt_template_detail", "create_or_update_universal_agent_prompt_template"],
    data_source_handling="local_only",
)
async def get_effective_prompt_template(
    agent_type: Annotated[str, "Agent Types such as universal, analysts,researchers"],
    agent_name: Annotated[str, "Agent name or runtime agent_id"],
    preference_id: Annotated[str, "Preference ID, default neutral"] = "neutral",
    workflow_id: Annotated[str, "Workflow ID, can be left blank"] = "",
    node_id: Annotated[str, "Node ID, can be left blank"] = "",
    is_debug_mode: Annotated[bool, "Whether to parse in debug mode, default false"] = False,
    debug_template_id: Annotated[str, "Debug template ID; can be left blank or specified explicitly when debugging"] = "",
    user_id: Annotated[str, "User ID; if not passed, the current conversation context user will be used by default."] = "",
) -> str:
    """Get the effective prompt word template that will currently be hit."""
    try:
        return _json_response(await _resolve_effective_prompt_template_payload(
            agent_type=agent_type,
            agent_name=agent_name,
            preference_id=preference_id,
            workflow_id=workflow_id,
            node_id=node_id,
            is_debug_mode=is_debug_mode,
            debug_template_id=debug_template_id,
            user_id=user_id,
        ))
    except Exception as exc:
        logger.error("Failed to obtain the current effective prompt word template: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to obtain the current effective prompt word template: {exc}"})


@tool
@register_tool(
    tool_id="get_current_thread_effective_prompt_template",
    name="Get the effective prompt word template of the current thread",
    description="Automatically infer the Agent version currently being debugged or discussed based on the current thread context, and then parse the prompt word template that is actually effective in this context.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="When the user asks which template is actually hit in the current thread, and the context is already in the current session, it will be used first.",
    when_not_to_use="Not suitable for template library browsing; inspect_prompt_templates should be used first in that scenario.",
    returns="Returns a JSON string, including the thread context, the automatically inferred resolution_input and the actual effective template content.",
    example="get_current_thread_effective_prompt_template()",
    related_tools=["get_effective_prompt_template", "inspect_prompt_templates", "get_prompt_template_detail"],
    data_source_handling="local_only",
)
async def get_current_thread_effective_prompt_template(
    preference_id: Annotated[str, "Preference ID, default neutral"] = "neutral",
    workflow_id: Annotated[str, "Automatically inferred workflow ID can be overridden explicitly and can be left blank"] = "",
    node_id: Annotated[str, "Automatically inferred node IDs can be overridden explicitly and can be left blank"] = "",
    debug_template_id: Annotated[str, "Automatically inferred debug template ID can be overridden explicitly and can be left blank"] = "",
    debug_mode: Annotated[str, "Debug mode, supports auto/true/false, default auto"] = "auto",
    user_id: Annotated[str, "User ID; if not passed, the current conversation context user will be used by default."] = "",
    thread_id: Annotated[str, "Thread ID; if not passed, the current conversation context thread will be used by default."] = "",
    agent_type: Annotated[str, "If automatic inference fails, you can explicitly specify agent_type"] = "",
    agent_name: Annotated[str, "If automatic inference fails, you can explicitly specify agent_name"] = "",
) -> str:
    """Automatically parse the current effective template based on the current Nanobot thread."""
    try:
        resolved_user_id = str(user_id or "").strip()
        if not resolved_user_id:
            try:
                resolved_user_id = str(require_current_user_id() or "").strip()
            except Exception:
                resolved_user_id = ""

        resolved_thread_id = str(thread_id or "").strip()
        if not resolved_thread_id:
            resolved_thread_id = str(get_current_assistant_thread_id() or "").strip()

        if not resolved_user_id or not resolved_thread_id:
            return _json_response({
                "status": "error",
                "message": "The current context lacks user_id or thread_id, and the current thread effective template cannot be automatically parsed; please explicitly pass in thread_id/user_id or return to use get_effective_prompt_template",
            })

        db = get_mongo_db()
        inferred = await _resolve_current_thread_effective_template_input(
            db=db,
            user_id=resolved_user_id,
            thread_id=resolved_thread_id,
            preference_id=preference_id,
            workflow_id=workflow_id,
            node_id=node_id,
            debug_template_id=debug_template_id,
            debug_mode=debug_mode,
            agent_type=agent_type,
            agent_name=agent_name,
        )
        if inferred.get("status") != "ok":
            return _json_response(inferred)

        resolution_input = dict(inferred.get("resolution_input") or {})
        payload = await _resolve_effective_prompt_template_payload(
            agent_type=str(resolution_input.get("agent_type") or ""),
            agent_name=str(resolution_input.get("agent_name") or ""),
            preference_id=str(resolution_input.get("preference_id") or "neutral"),
            workflow_id=str(resolution_input.get("workflow_id") or ""),
            node_id=str(resolution_input.get("node_id") or ""),
            is_debug_mode=bool(resolution_input.get("is_debug_mode")),
            debug_template_id=str(resolution_input.get("debug_template_id") or ""),
            user_id=str(resolution_input.get("user_id") or resolved_user_id),
        )
        return _json_response({
            **payload,
            "thread_id": inferred.get("thread_id"),
            "session_key": inferred.get("session_key"),
            "channel": inferred.get("channel"),
            "thread_context": inferred.get("thread_context") or {},
            "resolution_source": inferred.get("resolution_source") or {},
        })
    except Exception as exc:
        logger.error("Failed to obtain current thread effective prompt word template: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to obtain current thread effective prompt word template: {exc}"})


@tool
@register_tool(
    tool_id="create_or_update_runtime_agent_config",
    name="Create or update runtime Agent configuration",
    description="Create a runnable UniversalAgent candidate configuration, written in agent_configs, as the first step in the minimal build chain.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Used when you have confirmed that you want to generate a new profiled Agent candidate and are ready to write the minimum runtime definition to the database.",
    when_not_to_use="It is not suitable for resource reconnaissance, nor is it suitable for directly binding tools or writing prompt word templates.",
    returns="Returns a JSON string containing a summary of agent_configs as written.",
    example="create_or_update_runtime_agent_config(agent_id='valuation_candidate_v1', agent_name='Valuation candidates Agent', description='Output valuation conclusion')",
    related_tools=["create_or_update_universal_agent_prompt_template", "bind_agent_tools_and_validate_candidate"],
    data_source_handling="local_only",
)
async def create_or_update_runtime_agent_config(
    agent_id: Annotated[str, "Runtime Agent ID, e.g. valuation_candidate_v1"],
    agent_name: Annotated[str, "Agent 显示名称"],
    description: Annotated[str, "Agent single responsibility description"],
    output_field: Annotated[str, "Output field name, default analysis_report"] = "analysis_report",
    workflow_stage: Annotated[str, "Workflow stage, default analyst"] = "analyst",
    report_label: Annotated[str, "Report display label, can be empty"] = "",
    show_in_reports: Annotated[bool, "Whether to enter the workflow report list, default true"] = True,
    execution_order: Annotated[int, "Workflow display/execution order, default 50"] = 50,
    category: Annotated[str, "Agent Category, default analyst"] = "analyst",
    callable_surfaces: Annotated[str, "Allow call entries, comma separated, default assistant,workflow,agent"] = "assistant,workflow,agent",
    input_mode: Annotated[str, "Input mode, default standalone"] = "standalone",
    enabled: Annotated[bool, "Whether to enable, default true"] = True,
) -> str:
    """Create or update a profiled runtime Agent candidate."""
    try:
        clean_agent_id = str(agent_id or "").strip()
        clean_name = str(agent_name or "").strip()
        clean_description = str(description or "").strip()
        if not clean_agent_id or not clean_name or not clean_description:
            return _json_response({"status": "error", "message": "agent_id, agent_name, description cannot be empty"})

        db = get_mongo_db()
        collection = _get_collection(db, "agent_configs")
        if collection is None:
            return _json_response({"status": "error", "message": "The agent_configs collection is not available in the current database"})

        surfaces = _parse_string_list(callable_surfaces) or list(_DEFAULT_CALLABLE_SURFACES)
        existing = await collection.find_one({"agent_id": clean_agent_id}) or {}
        metadata = dict(existing.get("metadata") or {})
        metadata.update({
            "source": metadata.get("source") or "nanobot_generated",
            "callable_surfaces": surfaces,
            "input_mode": input_mode,
            "workflow_stage": workflow_stage,
            "output_field": output_field,
            "report_label": report_label or f"【{clean_name}】",
            "show_in_reports": show_in_reports,
            "execution_order": int(execution_order),
            "generation_status": "candidate",
        })

        update_doc = {
            "agent_id": clean_agent_id,
            "name": clean_name,
            "agent_name": clean_name,
            "description": clean_description,
            "output_field": output_field,
            "workflow_stage": workflow_stage,
            "report_label": report_label or f"【{clean_name}】",
            "node_name": clean_name,
            "execution_order": int(execution_order),
            "show_in_reports": show_in_reports,
            "callable_surfaces": surfaces,
            "category": category,
            "enabled": enabled,
            "metadata": metadata,
            "updated_at": _utc_now_iso(),
        }
        if not existing:
            update_doc["created_at"] = _utc_now_iso()

        await collection.update_one({"agent_id": clean_agent_id}, {"$set": update_doc}, upsert=True)
        persisted = await collection.find_one({"agent_id": clean_agent_id}, {"_id": 0}) or update_doc
        runtime_contract = {
            "agent_id": clean_agent_id,
            "agent_name": clean_name,
            "description": clean_description,
            "output_field": output_field,
            "workflow_stage": workflow_stage,
            "report_label": report_label or f"【{clean_name}】",
            "node_name": clean_name,
            "execution_order": int(execution_order),
            "show_in_reports": show_in_reports,
            "category": category,
            "callable_surfaces": surfaces,
        }
        return _json_response({
            "status": "ok",
            "action": "updated" if existing else "created",
            "agent": _format_runtime_agent_config(persisted, [], None),
            "runtime_contract": runtime_contract,
        })
    except Exception as exc:
        logger.error("Creating or updating runtime Agent configuration failed: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Creating or updating runtime Agent configuration failed: {exc}"})


@tool
@register_tool(
    tool_id="create_or_update_agent_workshop_draft",
    name="Create or update an Agent Workshop Draft",
    description="Synchronize the confirmed candidate Agent to the Agent Workshop Draft asset layer so that it is visible in the workshop list and can continue version management.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="When the candidate Agent s responsibilities, output, and tool scope have been confirmed, we hope to precipitate it into an Agent Workshop Draft instead of just using it at runtime.",
    when_not_to_use="It is not suitable for direct version release, nor is it suitable for calling when the requirements have not been confirmed.",
    returns="Returns a JSON string containing the written spec_id, session_id, and overview information.",
    example="create_or_update_agent_workshop_draft(agent_id='valuation_candidate_v1', agent_name='Valuation candidates Agent', target_responsibility='Output A-share valuation conclusion')",
    related_tools=["generate_confirmed_candidate_agent", "inspect_agent_workshop_assets", "create_or_update_runtime_agent_config"],
    data_source_handling="local_only",
)
async def create_or_update_agent_workshop_draft(
    agent_id: Annotated[str, "Candidate Agent ID, e.g. valuation_candidate_v1"],
    agent_name: Annotated[str, "Agent 显示名称"],
    target_responsibility: Annotated[str, "单一职责描述"],
    output_field: Annotated[str, "Output field name; if left blank or given a common name, the system will automatically generate an exclusive field name with agent semantics"] = "analysis_report",
    workflow_stage: Annotated[str, "Workflow stage, default analyst"] = "analyst",
    report_label: Annotated[str, "Report display label, can be empty"] = "",
    show_in_reports: Annotated[bool, "Whether to enter the workflow report list, default true"] = True,
    execution_order: Annotated[int, "Workflow display/execution order, default 50"] = 50,
    tool_ids: Annotated[str, "Candidate tool IDs, comma separated"] = "",
    non_goals: Annotated[str, "List of non-targets, comma separated"] = "",
    preferred_methods: Annotated[str, "Method scopes or preferences, comma separated"] = "",
    constraints: Annotated[str, "Additional constraints, comma separated"] = "",
) -> str:
    """Synchronize Nanobot candidate to Agent workshop Draft."""
    try:
        clean_agent_id = str(agent_id or "").strip()
        clean_agent_name = str(agent_name or "").strip()
        clean_responsibility = str(target_responsibility or "").strip()
        if not clean_agent_id or not clean_agent_name or not clean_responsibility:
            return _json_response({"status": "error", "message": "agent_id, agent_name, target_responsibility cannot be empty"})

        try:
            user_id = require_current_user_id()
        except RuntimeError:
            user_id = ""
        current_thread_id = (get_current_assistant_thread_id() or "").strip()
        db = get_mongo_db()

        # 🔥 Prevent LLM intent drift: compare agent_id with the current thread context spec_id
        thread_context_spec_id = _get_current_thread_context_spec_id()
        # 🔑 Key Trace Log: IntentGuard Check
        logger.info(
            "[WorkshopDraft][IntentGuard] thread_context.spec_id=%r tool_arg.agent_id=%r equivalent=%s",
            thread_context_spec_id, clean_agent_id,
            _agent_id_equivalent(thread_context_spec_id, clean_agent_id) if thread_context_spec_id else "N/A(empty_ctx)",
        )
        if thread_context_spec_id and thread_context_spec_id != clean_agent_id:
            if _agent_id_equivalent(thread_context_spec_id, clean_agent_id):
                logger.info(
                    "[AgentWorkshop][IntentGuard] Allow historical candidate ID prefix differences: thread_context.spec_id='%s' tool_arg.agent_id='%s'",
                    thread_context_spec_id, clean_agent_id,
                )
                clean_agent_id = thread_context_spec_id
            else:
                existing_name = await _resolve_spec_name(db, thread_context_spec_id) or thread_context_spec_id
                logger.warning(
                    "[AgentWorkshop][IntentGuard] ⚠️ LLM Intentions drift!"
                    " thread_context.spec_id='%s' name='%s' ≠ tool_arg.agent_id='%s' agent_name='%s'",
                    thread_context_spec_id, existing_name, clean_agent_id, clean_agent_name,
                )
                return _json_response({
                    "status": "error",
                    "code": "intent_drift_detected",
                    "message": (
                        f"Intent drift detection: The currently operating Agent is "
                        f"「{existing_name}」（{thread_context_spec_id}），"
                        f"But the agent_id you passed in is {clean_agent_id}]  ({clean_agent_name}) . "
                        f"Please use the correct agent_id={thread_context_spec_id} agent_name={existing_name} Try again."
                    ),
                })

        draft_target_context = await _resolve_workshop_draft_target_context(
            db,
            clean_agent_id,
            thread_id=current_thread_id,
        )
        if draft_target_context.get("guard_available") and draft_target_context.get("matched_existing_asset"):
            version_status = str(draft_target_context.get("version_status") or "").strip().lower()
            current_phase = str(draft_target_context.get("phase") or "").strip().lower()
            if version_status == "active" or current_phase == "published":
                resolved_version_id = str(draft_target_context.get("version_id") or clean_agent_id).strip()
                resolved_spec_id = str(draft_target_context.get("spec_id") or "").strip()
                return _build_phase_guard_blocked_response(
                    tool_name="create_or_update_agent_workshop_draft",
                    blocked_code="active_version_requires_iteration",
                    message=(
                        "The current target points to the published version; create_or_update_agent_workshop_draft only works for new candidate Drafts,"
                        "You cannot directly overwrite published assets with existing spec_id or version_id."
                    ),
                    next_action=(
                        f"Please call first iterate_agent_workshop_version(version_id='{resolved_version_id}') Create the next round,"
                        "Continue making changes in a new session."
                        if resolved_version_id
                        else "Please inspect the current version first and initiate iterate before continuing to modify it in the next session."
                    ),
                    phase_context=draft_target_context,
                    target_fields={
                        "agent_id": clean_agent_id,
                        "spec_id": resolved_spec_id or None,
                        "version_id": resolved_version_id or None,
                    },
                )
        # 🔑 Key tracking log: create_nanobot_draft before writing the library
        logger.info(
            "[WorkshopDraft][WriteDB] About to be called create_nanobot_draft agent_id=%r agent_name=%r",
            clean_agent_id, clean_agent_name,
        )
        result = await AgentWorkshopService(db=db).create_nanobot_draft(
            agent_id=clean_agent_id,
            agent_name=clean_agent_name,
            target_responsibility=clean_responsibility,
            output_field=output_field,
            tool_ids=_parse_string_list(tool_ids),
            non_goals=_parse_string_list(non_goals),
            preferred_methods=_parse_string_list(preferred_methods),
            constraints=_parse_string_list(constraints),
            runtime_contract={
                "output_field": output_field,
                "workflow_stage": workflow_stage,
                "report_label": report_label,
                "show_in_reports": show_in_reports,
                "execution_order": int(execution_order),
                "category": "analyst" if str(workflow_stage or "").strip().lower() == "analyst" else "researcher",
            },
            prompt_contract={
                "agent_type": "universal",
                "agent_name": clean_agent_id,
                "must_match_universal_agent": True,
            },
            tooling_contract={
                "required_tools": _parse_string_list(tool_ids),
            },
            owner_user_id=user_id,
            source_thread_id=current_thread_id,
        )
        # 🔑 Key tracking log: create_nanobot_draft after writing the library
        result_status = result.get("status", "") if isinstance(result, dict) else "non_dict"
        result_spec_id = result.get("spec_id", "") if isinstance(result, dict) else ""
        result_session_id = result.get("session_id", "") if isinstance(result, dict) else ""
        logger.info(
            "[WorkshopDraft][WriteDB] create_nanobot_draft result status=%s spec_id=%r session_id=%r",
            result_status, result_spec_id, result_session_id,
        )
        if result_status != "ok":
            logger.warning(
                "[WorkshopDraft][WriteDB] ❌ create_nanobot_draft Failure!full_result=%s",
                json.dumps(result, ensure_ascii=False, default=str)[:500] if isinstance(result, dict) else str(result)[:500],
            )
        # 🔥 Automatically update intent context
        # V2 Process: The session is created after the requirements are confirmed. It may be in the capability_check stage at this time.
        # The stage should not be changed back to draft_preparing.
        current_stage = _get_current_intent_stage()
        if current_stage in {"capability_check", "plan_selection_pending", "requirement_confirmation_pending"}:
            next_stage = "capability_check"
            next_action = "Continue to perform a capability inventory:search_project_capabilities + analyze_agent_workshop_gaps"
            task_status = "capability_check"
        else:
            next_stage = "draft_preparing"
            next_action = "Continue to perform gap analysis. If there is a blocking gap, create/bind Skill for the current Agent, and then return to version building and real data testing."
            task_status = "draft_preparing"
        _auto_update_intent(
            action="create_agent",
            stage=next_stage,
            spec_id=clean_agent_id,
            spec_name=clean_agent_name,
            intent_summary=f"创建 Agent「{clean_agent_name}」，准备工坊草稿",
            next_action=next_action,
            task={
                "type": "agent",
                "id": clean_agent_id,
                "name": clean_agent_name,
                "status": task_status,
            },
        )
        return _json_response({**result, "status": "ok"})
    except Exception as exc:
        logger.error("Failed to create or update Agent Workshop Draft: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to create or update Agent Workshop Draft: {exc}"})


@tool
@register_tool(
    tool_id="analyze_agent_workshop_gaps",
    name="Perform Agent Workshop Gap Analysis",
    description="Directly triggers the gap analysis phase of the Agent Workshop session and returns a structured gap summary. If there is no existing session_id, basic information such as agent_id can be passed in to automatically create a temporary session.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Used when user requirements have been confirmed and real gap analysis needs to be run. If there is already a session_id, analyze it directly; if not, you can pass in agent_id/agent_name/target_responsibility/tool_ids to automatically create a session and then analyze it.",
    when_not_to_use="Not suitable for calling when the requirements have not been confirmed. It is also not suitable to be called after the version has been automatically built by auto-build (such as generate_confirmed_candidate_agent), because auto-build already performs gap analysis internally. If you are currently in the BUILDING phase, you should skip this tool and go directly to testing.",
    returns="Returns a JSON string containing session_id, spec_id and gap_report summary.",
    example="analyze_agent_workshop_gaps(session_id='session_123') or analyze_agent_workshop_gaps(agent_id='risk_signal_agent', agent_name='Financial Report Risk Signal Assistant', target_responsibility='Identify financial reporting risk signals', tool_ids='tool_a,tool_b')",
    related_tools=["create_or_update_agent_workshop_draft", "search_project_capabilities", "generate_agent_workshop_tooling_plan", "build_agent_workshop_version"],
    data_source_handling="local_only",
)
async def analyze_agent_workshop_gaps(
    session_id: Annotated[str, "Agent Workshop session ID; if it is empty, you need to provide parameters such as agent_id to automatically create"] = "",
    agent_id: Annotated[str, "Candidate Agent ID, required when session_id is empty"] = "",
    agent_name: Annotated[str, "Agent Display name, required when session_id is empty"] = "",
    target_responsibility: Annotated[str, "Single responsibility description, required when session_id is empty"] = "",
    tool_ids: Annotated[str, "Candidate tool IDs, separated by commas, used when session_id is empty"] = "",
) -> str:
    """Performs Agent Workshop gap analysis and returns structured results."""
    try:
        clean_session_id = str(session_id or "").strip()
        clean_agent_id = str(agent_id or "").strip()
        clean_agent_name = str(agent_name or "").strip()
        clean_responsibility = str(target_responsibility or "").strip()

        db = get_mongo_db()

        # If there is no session_id, try to find or create based on agent_id session
        if not clean_session_id:
            if not clean_agent_id or not clean_agent_name or not clean_responsibility:
                return _json_response({
                    "status": "error",
                    "message": "session_id When empty, agent_id, agent_name, and target_responsibility cannot be empty.",
                })

            # Prioritize the search for existing threads with the same agent_id session
            current_thread_id = (get_current_assistant_thread_id() or "").strip()
            existing_session = None
            try:
                sessions = _get_collection(db, "agent_workshop_sessions")
                if sessions is not None:
                    existing_session = await sessions.find_one(
                        {"agent_id": clean_agent_id, "source_thread_id": current_thread_id},
                        {"session_id": 1},
                        sort=[("created_at", -1)],
                    )
            except Exception:
                existing_session = None

            if existing_session and existing_session.get("session_id"):
                clean_session_id = str(existing_session["session_id"]).strip()
                logger.info("[AnalyzeGaps] Reuse existing session_id=%s agent_id=%s", clean_session_id, clean_agent_id)
            else:
                # automatically created draft session
                draft_result = await AgentWorkshopService(db=db).create_nanobot_draft(
                    agent_id=clean_agent_id,
                    agent_name=clean_agent_name,
                    target_responsibility=clean_responsibility,
                    output_field="analysis_report",
                    tool_ids=_parse_string_list(tool_ids),
                    runtime_contract={"required_tools": _parse_string_list(tool_ids)},
                    tooling_contract={"required_tools": _parse_string_list(tool_ids)},
                    owner_user_id="",
                    source_thread_id=current_thread_id,
                )
                clean_session_id = str(draft_result.get("session_id") or "").strip()
                if not clean_session_id:
                    return _json_response({
                        "status": "error",
                        "message": "Automatic creation of Agent Workshop session failed and gap analysis could not be performed.",
                    })
                logger.info("[AnalyzeGaps] automatically created session_id=%s agent_id=%s", clean_session_id, clean_agent_id)

        result = await AgentWorkshopService(db=db).analyze_gaps(clean_session_id)
        gap_report = result.get("gap_report") if isinstance(result, dict) else None
        # AgentWorkshopService.analyze_gaps The gap_report returned is AgentWorkshopGapAnalysis
        # Pydantic model object. If passed directly to _json_response, json.dumps default=str Will
        # Convert it into a string, causing the downstream node_gap_analysis to not be able to extract fields such as blocking_gaps
        #  (state["gap_report"] always empty {}, further acknowledged_gaps=0, build failed).
        # This is uniformly converted into dict to ensure that JSON is still a structured object after serialization.
        if gap_report is not None and not isinstance(gap_report, dict):
            if hasattr(gap_report, "model_dump"):
                gap_report = gap_report.model_dump(by_alias=True, exclude_none=False)
            elif hasattr(gap_report, "dict"):
                gap_report = gap_report.dict(by_alias=True)
            else:
                # Get the scoop: use __dict__ or str
                gap_report = (
                    dict(getattr(gap_report, "__dict__", {}))
                    if getattr(gap_report, "__dict__", None)
                    else None
                )

        # Update intent context: After gap analysis is completed, enter the solution selection phase
        _auto_update_intent(
            action="create_agent",
            stage="plan_selection_pending",
            spec_id=clean_agent_id,
            spec_name=clean_agent_name,
            intent_summary=f"为 Agent「{clean_agent_name}」完成能力缺口分析，等待生成候选方案",
            next_action="Call propose_agent_build_plans to generate candidate plans",
        )

        return _json_response({
            "status": "ok",
            "session_id": clean_session_id,
            "spec_id": result.get("spec_id") if isinstance(result, dict) else "",
            "gap_report": gap_report,
            "summary": {
                "existing_tools": len(_read_mapping_or_attr(gap_report, "existing_tools", []) or []),
                "suggested_tools": len(_read_mapping_or_attr(gap_report, "suggested_tools", []) or []),
                "blocking_gaps": len(_read_mapping_or_attr(gap_report, "blocking_gaps", []) or []),
            },
        })
    except Exception as exc:
        logger.error("Failed to perform Agent Workshop gap analysis: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to perform Agent Workshop gap analysis: {exc}"})


@tool
@register_tool(
    tool_id="generate_agent_workshop_tooling_plan",
    name="Generate draft requirements for Agent workshop tools",
    description="Directly trigger the generation of the Agent workshop tool requirements draft and return the structured tool plan.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use only when manual diagnosis is required or to review draft tool requirements in isolation. Ordinary Agent generation main process does not need to be called directly, because build_agent_workshop_version and resolve_agent_workshop_blocking_gaps will automatically generate/use tooling_plan internally.",
    when_not_to_use="It is not suitable to be called when session_id is invalid; it is not suitable to be called as a necessary step in the ordinary automatic build process; it is not suitable to be called repeatedly in the BUILDING/TESTING/PUBLISHING stage.",
    returns="Returns a JSON string containing session_id, spec_id and tooling_plan.",
    example="generate_agent_workshop_tooling_plan(session_id='session_123')",
    related_tools=["analyze_agent_workshop_gaps", "build_agent_workshop_version"],
    data_source_handling="local_only",
)
async def generate_agent_workshop_tooling_plan(
    session_id: Annotated[str, "Agent workshop session ID"],
) -> str:
    """Generate draft requirements for Agent workshop tools and return structured results."""
    try:
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            return _json_response({"status": "error", "message": "session_id cannot be empty"})

        db = get_mongo_db()
        result = await AgentWorkshopService(db=db).generate_tooling_plan(clean_session_id)
        tooling_plan = result.get("tooling_plan") if isinstance(result, dict) else None
        missing_capabilities = []
        if isinstance(tooling_plan, dict):
            missing_capabilities = tooling_plan.get("missing_capabilities") or []
        else:
            missing_capabilities = getattr(tooling_plan, "missing_capabilities", []) or []

        return _json_response({
            "status": "ok",
            "session_id": clean_session_id,
            "spec_id": result.get("spec_id") if isinstance(result, dict) else "",
            "tooling_plan": tooling_plan,
            "summary": {
                "missing_capabilities": len(missing_capabilities),
            },
        })
    except Exception as exc:
        logger.error("Failed to generate draft requirements for Agent workshop tools: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to generate draft requirements for Agent workshop tools: {exc}"})


@tool
@register_tool(
    tool_id="build_agent_workshop_version",
    name="Generate Agent Workshop version draft",
    description="Directly trigger the generation of the Agent workshop version draft and return the generated version information. If an existing version is in testing, the needs_user_decision status will be returned to allow the user to choose whether to overwrite or continue to advance.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Used when Agent Draft has been generated but a test version has not yet been generated (READY_TO_BUILD stage). The tool does real gap analysis, tool planning and version draft generation in-house. if return status=needs_user_decision, The user must be shown the old version information (the tool list in existing_version) and ask the user to choose: overwrite the old version (use the overwrite_existing=True call it again) or continue pushing the old version (direct users to iterate_agent_workshop_version or continue testing).",
    when_not_to_use="Not suitable for calling when session_id is missing or the specification is not yet ready. If the user does not explicitly confirm that they want to overwrite, do not send overwrite_existing=True. ",
    returns="Returns a JSON string. Contains session_id, spec_id and version when normal; returns when there is a version status=needs_user_decision and older version information and options.",
    example="build_agent_workshop_version(session_id='session_123')",
    related_tools=["analyze_agent_workshop_gaps", "generate_agent_workshop_tooling_plan", "iterate_agent_workshop_version"],
    data_source_handling="local_only",
)
async def build_agent_workshop_version(
    session_id: Annotated[str, "Agent workshop session ID"],
    overwrite_existing: Annotated[bool, "Whether to overwrite the existing version (delete the old version and then rebuild). Only pass True if the user explicitly confirms the override."] = False,
) -> str:
    """Generate a draft Agent Workshop version and return structured results."""
    try:
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            return _json_response({"status": "error", "message": "session_id cannot be empty"})

        db = get_mongo_db()
        phase_context = await _resolve_workshop_session_phase_context(db, clean_session_id)
        if phase_context.get("guard_available") and not phase_context.get("exists"):
            return _json_response({"status": "error", "message": f"会话 {clean_session_id} 不存在"})

        version_status = str(phase_context.get("version_status") or "").strip().lower()
        feasibility_status = str(phase_context.get("feasibility_status") or "").strip().lower()
        completeness_score = float(phase_context.get("completeness_score") or 0)
        if phase_context.get("guard_available") and (feasibility_status != "feasible" or completeness_score < 0.75):
            return _build_phase_guard_blocked_response(
                tool_name="build_agent_workshop_version",
                blocked_code="phase_not_ready",
                message=(
                    f"当前阶段为{phase_context.get('phase_label')}，不能直接补建测试版本；"
                    "Please complete the requirements clarification first and put the session into executable state."
                ),
                next_action="First complete the points to be confirmed, target boundaries, output format and acceptance method.",
                phase_context=phase_context,
                target_fields={
                    "session_id": clean_session_id,
                    "spec_id": phase_context.get("spec_id"),
                },
            )
        if phase_context.get("guard_available") and version_status and version_status != "draft":
            current_version_id = str(phase_context.get("current_version_id") or "").strip()

            # User confirms that they want to overwrite the old version: delete the old version before continuing the build
            if overwrite_existing and current_version_id:
                svc = AgentWorkshopService(db=db)
                delete_result = await svc.delete_version(current_version_id, force=True)
                if not delete_result.get("deleted"):
                    return _json_response({
                        "status": "error",
                        "message": f"删除旧版本 {current_version_id} 失败：{delete_result.get('message', '未知原因')}",
                        "current_version_id": current_version_id,
                    })
                # Continue execution after successful deletion build_version
            else:
                # Return"Requires user decision-making"response, letting LLM ask the user whether to overwrite or move forward
                existing_version_summary = await _get_existing_version_summary(db, current_version_id)
                phase_label = phase_context.get("phase_label") or version_status
                response_payload = {
                    "status": "needs_user_decision",
                    "decision_type": "overwrite_or_continue",
                    "message": (
                        f"当前会话已有一个处于「{phase_label}」阶段的版本 {current_version_id}。"
                        f"Please show the old version information to the user and ask the user whether they want to overwrite the old version (delete and rebuild) or continue to push the old version."
                    ),
                    "existing_version": existing_version_summary,
                    "options": [
                        {
                            "label": "覆盖旧版本",
                            "description": "Delete the current version and rebuild based on the latest requirements (applicable to situations where tool selection or gap analysis is wrong and requires rebuilding)",
                            "action": "call build_agent_workshop_version(session_id, overwrite_existing=True)",
                        },
                        {
                            "label": "继续推进旧版本",
                            "description": "Keep the current version and continue to advance according to the process: first run the real data test, and after passing the evaluation, you can publish or iteratively create v2",
                            "action": "First call run_agent_workshop_real_data_test to perform real data testing; after passing the evaluation, you can call publish_agent_workshop_version to publish, or call iterate_agent_workshop_version to create a v2 version (note: iterate requires that the version has entered the evaluation/publish-ready/published stage, and the testing stage cannot iterate directly)",
                        },
                    ],
                    "current_phase": phase_context.get("phase"),
                    "current_phase_label": phase_label,
                    "session_id": clean_session_id,
                    "spec_id": phase_context.get("spec_id"),
                    "current_version_id": current_version_id,
                    "_tool_events": [
                        _build_tool_stage_event(
                            "build_agent_workshop_version.needs_user_decision",
                            "needs_user_decision",
                            f"已有版本 {current_version_id} 处于 {phase_label} 阶段，需要用户决策是否覆盖",
                        ),
                    ],
                }
                logger.info(
                    "[BuildAgent] needs_user_decision | current_version_id=%s | phase=%s | existing_version_keys=%s | options_count=%d",
                    current_version_id,
                    phase_label,
                    list(existing_version_summary.keys()) if existing_version_summary else [],
                    len(response_payload.get("options", [])),
                )
                return _json_response(response_payload)

        result = await AgentWorkshopService(db=db).build_version(clean_session_id)
        version = result.get("version") if isinstance(result, dict) else None
        # AgentWorkshopService.build_version The version returned is the AgentVersion Pydantic model object.
        # If passed directly to _json_response, json.dumps default=str will convert it to str repr
        #  (shaped like "id=ObjectId('...') version_id='...' spec_id='...' ...") , 
        # Causes the downstream node_generate_candidate_agent / node_build_or_ready to extract
        # version_id is the entire object repr rather than the version_id string, and thus real_data_test /
        # publish All failed. This is uniformly converted into dict to ensure that JSON is still a structured object after serialization.
        if version is not None and not isinstance(version, dict):
            if hasattr(version, "model_dump"):
                version = version.model_dump(by_alias=True, exclude_none=False)
            elif hasattr(version, "dict"):
                version = version.dict(by_alias=True)
            elif hasattr(version, "__dict__") and getattr(version, "__dict__", None):
                version = dict(getattr(version, "__dict__"))
            else:
                version = {"_repr": str(version)}
        # Top-level version_id: convenient for downstream direct access to avoid repeated nested parsing
        top_version_id = ""
        if isinstance(version, dict):
            top_version_id = str(version.get("version_id") or "").strip()
        return _json_response({
            "status": "ok",
            "session_id": clean_session_id,
            "spec_id": result.get("spec_id") if isinstance(result, dict) else "",
            "version_id": top_version_id,
            "version": version,
            "summary": {
                "version_id": top_version_id or None,
                "required_tools": len(_read_mapping_or_attr(version, "required_tools", []) or []) if version is not None else 0,
                "required_capabilities": len(_read_mapping_or_attr(version, "required_capabilities", []) or []) if version is not None else 0,
            },
        })
    except Exception as exc:
        logger.error("Failed to generate Agent Workshop version draft: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to generate Agent Workshop version draft: {exc}"})


@tool
@register_tool(
    tool_id="debug_agent_workshop_version",
    name="Debugging the Agent Workshop version",
    description="Execute a real stock sample run on the specified Agent Workshop version and return the debugging results; the tool will not automatically write formal evaluation records.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when the user clearly wants to debug troubleshooting, view the latest sample output, or diagnose prompt or runtime problems.",
    when_not_to_use="Not suitable as a substitute for formal real-data testing, acceptance, evaluation and rollout, pre-release validation, or answering why a version is still in testing.",
    returns="Returns a JSON string containing version_id, spec_id, report, raw_result, and run metadata, but does not automatically generate evaluation records.",
    example="debug_agent_workshop_version(version_id='spec_x_v1', stock_symbol='600519')",
    related_tools=["run_agent_workshop_real_data_test", "publish_agent_workshop_version"],
    data_source_handling="local_only",
)
async def debug_agent_workshop_version(
    version_id: Annotated[str, "Agent Workshop version ID"],
    stock_symbol: Annotated[str, "Real stock code, such as 600519"],
    market_type: Annotated[str, "Market type, default A shares"] = "A股",
    analysis_date: Annotated[str, "Analysis date, format YYYY-MM-DD, can be empty"] = "",
    user_goal: Annotated[str, "The target of this test can be empty"] = "",
    prompt_overrides_json: Annotated[str, "Prompt Override JSON object, can be null"] = "",
) -> str:
    """Run a single real-stock debug execution for one workshop version."""
    stage_events: list[dict[str, str]] = []
    try:
        clean_version_id = str(version_id or "").strip()
        clean_symbol = str(stock_symbol or "").strip()
        if not clean_version_id:
            return _json_response({"status": "error", "message": "version_id cannot be empty"})
        if not clean_symbol:
            return _json_response({"status": "error", "message": "stock_symbol cannot be empty"})

        prompt_overrides = _parse_optional_json_object(prompt_overrides_json, "prompt_overrides_json")

        db = get_mongo_db()
        phase_context = await _resolve_workshop_version_phase_context(db, clean_version_id)
        if phase_context.get("guard_available") and not phase_context.get("exists"):
            return _json_response({"status": "error", "message": f"版本 {clean_version_id} 不存在"})
        if phase_context.get("guard_available"):
            version_status = str(phase_context.get("version_status") or "").strip().lower()
            current_phase = str(phase_context.get("phase") or "").strip().lower()
            allowed_phases = {"testing", "evaluation", "publish-ready"}
            if current_phase not in allowed_phases:
                next_action = "Please let the version enter testing first, and then perform debugging."
                blocked_code = "version_not_testing"
                if version_status == "active":
                    blocked_code = "active_version_requires_iteration"
                    next_action = "The current version has been released; if you need to continue optimizing, please start the next round."
                elif version_status == "archived":
                    blocked_code = "archived_version_blocked"
                    next_action = "The archived version cannot be debugged anymore, please switch to the current testing version."
                return _build_phase_guard_blocked_response(
                    tool_name="debug_agent_workshop_version",
                    blocked_code=blocked_code,
                    message=(
                        f"当前阶段为{phase_context.get('phase_label')}，不能直接执行调试；"
                        "Only versions in the testing / evaluation / publish-ready stage are allowed to enter the debug link."
                    ),
                    next_action=next_action,
                    phase_context=phase_context,
                    target_fields={
                        "version_id": clean_version_id,
                        "spec_id": phase_context.get("spec_id"),
                    },
                )

        llm_payload = await _resolve_workshop_test_llm_payload(
            db=db,
        )
        stage_events.append(_build_tool_stage_event(
            "debug_agent_workshop_version.resolve_default_llm",
            "ok",
            f"已解析系统默认推理模型: {llm_payload.get('provider')}/{llm_payload.get('model')}",
        ))
        result = await AgentWorkshopService(db=db).debug_version(
            version_id=clean_version_id,
            llm=llm_payload,
            stock={
                "symbol": clean_symbol,
                "market_type": str(market_type or "A股").strip() or "A股",
                "analysis_date": str(analysis_date or "").strip() or None,
            },
            user_goal=str(user_goal or "").strip(),
            prompt_overrides=prompt_overrides,
        )
        return _json_response({
            "status": "ok",
            **result,
            "summary": {
            "_tool_events": [
                *stage_events,
                _build_tool_stage_event(
                    "debug_agent_workshop_version.debug_version",
                    "ok",
                    f"Debugging completed: symbol={result.get('symbol') or clean_symbol}, report_length={result.get('report_length')}",
                ),
                _build_tool_stage_event(
                    "debug_agent_workshop_version",
                    "ok",
                    "样例调试已完成",
                ),
            ],
                "version_id": result.get("version_id"),
                "spec_id": result.get("spec_id"),
                "symbol": result.get("symbol"),
                "analysis_date": result.get("analysis_date"),
                "report_length": result.get("report_length"),
            },
        })
    except Exception as exc:
        logger.error("Debugging Agent Workshop version failed: %s", exc, exc_info=True)
        return _json_response({
            "status": "error",
            "message": f"Debugging Agent Workshop version failed: {exc}",
            "failed_stage": "debug_agent_workshop_version",
            "_tool_events": [
                *stage_events,
                _build_tool_stage_event(
                    "debug_agent_workshop_version",
                    "error",
                    f"调试失败: {exc}",
                ),
            ],
        })


@tool
@register_tool(
    tool_id="run_agent_workshop_real_data_test",
    name="Execute Agent Workshop real data test",
    description="Execute a real stock sample test on the specified Agent Workshop version and automatically record the evaluation results to Agent Workshop.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when users want to perform real data testing, formal acceptance, verify whether it passes, view evaluation results, confirm readiness before release, or troubleshoot why the version is still stuck in testing.",
    when_not_to_use="It is not suitable for only style preview, discussion of solutions, single-step debugging Prompt, or when there is no version_id.",
    returns="Returns a JSON string, including debug_result, evaluation, latest_decision and whether formal deployment has been completed.",
    example="run_agent_workshop_real_data_test(version_id='spec_x_v1', stock_symbol='600519')",
    related_tools=["debug_agent_workshop_version", "publish_agent_workshop_version"],
    data_source_handling="local_only",
)
async def run_agent_workshop_real_data_test(
    version_id: Annotated[str, "Agent Workshop version ID"],
    stock_symbol: Annotated[str, "Real stock code, such as 600519"],
    market_type: Annotated[str, "Market type, default A shares"] = "A股",
    analysis_date: Annotated[str, "Analysis date, format YYYY-MM-DD, can be empty"] = "",
    user_goal: Annotated[str, "The target of this test can be empty"] = "",
    user_feedback: Annotated[str, "Supplementary feedback for this test, can be empty"] = "",
    prompt_overrides_json: Annotated[str, "Prompt Override JSON object, can be null"] = "",
    skip_evaluation: Annotated[bool, "Only runs the test without evaluation, the evaluation is performed separately by subsequent"] = False,
) -> str:
    """Execute the official real-data test loop and persist its evaluation."""
    stage_events: list[dict[str, str]] = []
    try:
        clean_version_id = str(version_id or "").strip()
        clean_symbol = str(stock_symbol or "").strip()
        if not clean_version_id:
            return _json_response({"status": "error", "message": "version_id cannot be empty"})
        if not clean_symbol:
            return _json_response({"status": "error", "message": "stock_symbol cannot be empty"})

        prompt_overrides = _parse_optional_json_object(prompt_overrides_json, "prompt_overrides_json")
        db = get_mongo_db()
        phase_context = await _resolve_workshop_version_phase_context(db, clean_version_id)
        if phase_context.get("guard_available") and not phase_context.get("exists"):
            return _json_response({"status": "error", "message": f"版本 {clean_version_id} 不存在"})
        if phase_context.get("guard_available") and str(phase_context.get("version_status") or "").strip().lower() != "testing":
            next_action = "Please build the test version first."
            if phase_context.get("version_status") == "active":
                next_action = "The current version has been released; if you need to continue optimizing, please start the next round first."
            elif phase_context.get("version_status") == "archived":
                next_action = "Please switch to the current testing version, or start a new build."
            return _build_phase_guard_blocked_response(
                tool_name="run_agent_workshop_real_data_test",
                blocked_code=(
                    "active_version_requires_iteration"
                    if phase_context.get("version_status") == "active"
                    else "archived_version_blocked"
                    if phase_context.get("version_status") == "archived"
                    else "version_not_testing"
                ),
                message=(
                    f"当前阶段为{phase_context.get('phase_label')}，不能直接执行真数据测试；"
                    "Only the testing version can enter the official test link."
                ),
                next_action=next_action,
                phase_context=phase_context,
                target_fields={
                    "version_id": clean_version_id,
                    "spec_id": phase_context.get("spec_id"),
                },
            )

        service = AgentWorkshopService(db=db)
        gap_tool_sync = await _auto_sync_gap_tools_to_workshop_version(db, clean_version_id)
        if gap_tool_sync.get("status") in {"synced", "unchanged"}:
            stage_events.append(_build_tool_stage_event(
                "run_agent_workshop_real_data_test.auto_sync_gap_tools",
                "ok",
                f"The gap tool has been synchronized to the current version: {gap_tool_sync.get('status')}; tools={len(gap_tool_sync.get('required_tools') or [])}",
            ))
        llm_payload = await _resolve_workshop_test_llm_payload(
            db=db,
        )
        stage_events.append(_build_tool_stage_event(
            "run_agent_workshop_real_data_test.resolve_default_llm",
            "ok",
            f"已解析系统默认推理模型: {llm_payload.get('provider')}/{llm_payload.get('model')}",
        ))
        debug_result = await service.debug_version(
            version_id=clean_version_id,
            llm=llm_payload,
            stock={
                "symbol": clean_symbol,
                "market_type": str(market_type or "A股").strip() or "A股",
                "analysis_date": str(analysis_date or "").strip() or None,
            },
            user_goal=str(user_goal or "").strip(),
            prompt_overrides=prompt_overrides,
        )
        stage_events.append(_build_tool_stage_event(
            "run_agent_workshop_real_data_test.debug_version",
            "ok",
            f"Sample run completed: symbol={debug_result.get('symbol') or clean_symbol}, report_length={debug_result.get('report_length')}",
        ))

        debug_prompt = debug_result.get("debug_prompt") if isinstance(debug_result.get("debug_prompt"), dict) else {}
        raw_result = debug_result.get("raw_result") if isinstance(debug_result.get("raw_result"), dict) else {}
        runtime_result_payload = _with_nanobot_review_worker_flags({
            "user_goal": str(user_goal or "").strip(),
            "report": debug_result.get("report") or "",
            "raw_result": raw_result,
            "debug_prompt": debug_prompt,
            "template": debug_result.get("template") or {},
            "metadata": debug_result.get("metadata") or {},
            "symbol": debug_result.get("symbol") or clean_symbol,
            "analysis_date": debug_result.get("analysis_date") or str(analysis_date or "").strip(),
            "output_text": debug_prompt.get("llm_final_response") or debug_result.get("report") or "",
            "output_payload": raw_result,
            "tool_trace": debug_prompt.get("tool_trace") or raw_result.get("tool_trace") or [],
        })

        # 🔑 skip_evaluation=True: Only tests are run, no evaluation is performed, and evaluation is performed separately by node_real_data_test subsequently.
        if skip_evaluation:
            stage_events.append(_build_tool_stage_event(
                "run_agent_workshop_real_data_test.skip_evaluation",
                "ok",
                "The test is completed and the evaluation phase is skipped (executed separately later)",
            ))
            return _json_response({
                "status": "ok",
                "test_chain_status": "test_only",
                "version_id": clean_version_id,
                "spec_id": debug_result.get("spec_id"),
                "debug_result": debug_result,
                "runtime_result": runtime_result_payload,
                "user_feedback": str(user_feedback or "").strip(),
                "_tool_events": [
                    *stage_events,
                    _build_tool_stage_event(
                        "run_agent_workshop_real_data_test",
                        "ok",
                        "Real data testing completed (evaluation skipped)",
                    ),
                ],
                "summary": {
                    "symbol": debug_result.get("symbol"),
                    "analysis_date": debug_result.get("analysis_date"),
                    "report_length": debug_result.get("report_length"),
                },
                "message": "The real data test has been completed and the test report has been generated. The evaluation will be performed separately in the next step.",
            })

        evaluation_result = await service.evaluate_version(
            clean_version_id,
            evaluation_type="production-review",
            user_feedback=str(user_feedback or "").strip(),
            runtime_result=runtime_result_payload,
        )
        evaluation = evaluation_result.get("evaluation") if isinstance(evaluation_result, dict) else None
        evaluation_decision = _read_mapping_or_attr(evaluation, "decision", None)
        acceptance_passed = evaluation_decision == "pass"

        # 🔥 Write the evaluation evidence back to the intent context for fine-grained routing in the ITERATING phase
        publish_readiness = (_read_mapping_or_attr(evaluation, "publish_readiness", {}) or {}) if isinstance(evaluation, dict) else {}
        if isinstance(publish_readiness, dict):
            eval_blockers = [str(b).strip() for b in (publish_readiness.get("blockers") or []) if str(b).strip()]
            eval_categories = []
            details = _read_mapping_or_attr(evaluation, "details", {}) or {}
            evidence_bundle = details.get("evidence_bundle") if isinstance(details, dict) else None
            if isinstance(evidence_bundle, dict):
                for finding in (evidence_bundle.get("findings") or []):
                    if isinstance(finding, dict):
                        cat = str(finding.get("category") or "").strip()
                        if cat:
                            eval_categories.append(cat)
            if not eval_categories:
                # fallback: Inferred from blockers text category
                blocker_text = " ".join(eval_blockers).lower()
                if "工具" in blocker_text or "tool" in blocker_text:
                    eval_categories.append("tool_usage")
                if "输出字段" in blocker_text or "output" in blocker_text:
                    eval_categories.append("output_coverage")
                if "执行计划" in blocker_text or "execution_plan" in blocker_text:
                    eval_categories.append("execution_plan")
            _auto_update_intent(
                evaluation_decision=str(evaluation_decision or "").strip().lower(),
                evaluation_blockers=eval_blockers,
                evaluation_categories=_dedupe_string_list(eval_categories),
            )

        stage_events.append(_build_tool_stage_event(
            "run_agent_workshop_real_data_test.evaluate_version",
            "ok",
            f"Assessment recorded: decision={evaluation_decision or 'unknown'}, overall={_read_mapping_or_attr(_read_mapping_or_attr(evaluation, 'scores', {}), 'overall', None)}",
        ))
        return _json_response({
            "status": "ok",
            "test_chain_status": "ok",
            "official_acceptance_decision": evaluation_decision,
            "official_acceptance_passed": acceptance_passed,
            "version_id": clean_version_id,
            "spec_id": debug_result.get("spec_id"),
            "debug_result": debug_result,
            "evaluation": evaluation,
            "_tool_events": [
                *stage_events,
                _build_tool_stage_event(
                    "run_agent_workshop_real_data_test",
                    "ok",
                    "Real data testing and evaluation have been completed",
                ),
            ],
            "summary": {
                "symbol": debug_result.get("symbol"),
                "analysis_date": debug_result.get("analysis_date"),
                "report_length": debug_result.get("report_length"),
                "decision": evaluation_decision,
                "overall_score": _read_mapping_or_attr(_read_mapping_or_attr(evaluation, "scores", {}), "overall", None),
                "recorded_in_workshop": bool(_read_mapping_or_attr(evaluation, "evaluation_id", None)),
                "official_acceptance_passed": acceptance_passed,
            },
            "message": (
                "The real data test link has been executed and completed the evaluation and storage; the latest official acceptance conclusion is pass, and the version has now entered the pending release status and must be manually confirmed by the user before it can be officially released."
                if acceptance_passed
                else f"The real data test link has been executed and evaluated and dropped into the library; however, the latest official acceptance conclusion is {evaluation_decision or 'unknown'}, Currently cannot be considered passed."
            ),
        })
    except Exception as exc:
        logger.error("Failed to execute Agent Workshop real data test: %s", exc, exc_info=True)
        failed_stage = "run_agent_workshop_real_data_test.evaluate_version" if any(event.get("name") == "run_agent_workshop_real_data_test.debug_version" for event in stage_events) else "run_agent_workshop_real_data_test.debug_version"
        return _json_response({
            "status": "error",
            "message": f"Failed to execute Agent Workshop real data test: {exc}",
            "failed_stage": failed_stage,
            "_tool_events": [
                *stage_events,
                _build_tool_stage_event(
                    failed_stage,
                    "error",
                    str(exc),
                ),
                _build_tool_stage_event(
                    "run_agent_workshop_real_data_test",
                    "error",
                    f"Real data test failed, failure stage={failed_stage}",
                ),
            ],
        })


@tool
@register_tool(
    tool_id="publish_agent_workshop_version",
    name="Release Agent Workshop version",
    description="After the user has manually confirmed the release, the Agent Workshop version that has passed the latest real data test evaluation will be released as active.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Only used when the version is already in testing and the latest evaluation conclusion is pass, and the user explicitly confirms the release in the current round.",
    when_not_to_use="Not suitable for calling when the real data test evaluation has not been completed, the evaluation has failed, or the test has just passed but the user has not explicitly confirmed the release.",
    returns="Returns a JSON string containing the version status and spec_id after release.",
    example="publish_agent_workshop_version(version_id='spec_x_v1')",
    related_tools=["run_agent_workshop_real_data_test", "debug_agent_workshop_version"],
    data_source_handling="local_only",
)
async def publish_agent_workshop_version(
    version_id: Annotated[str, "Agent Workshop version ID"],
) -> str:
    """Publish a workshop version after its latest evaluation has passed."""
    try:
        clean_version_id = str(version_id or "").strip()
        if not clean_version_id:
            return _json_response({"status": "error", "message": "version_id cannot be empty"})

        db = get_mongo_db()
        phase_context = await _resolve_workshop_version_phase_context(db, clean_version_id)
        if phase_context.get("guard_available") and not phase_context.get("exists"):
            return _json_response({"status": "error", "message": f"版本 {clean_version_id} 不存在"})
        if phase_context.get("guard_available") and str(phase_context.get("version_status") or "").strip().lower() != "testing":
            next_action = "Please let the version enter testing first, and then perform real data testing."
            if phase_context.get("version_status") == "active":
                next_action = "The current version has been released; if you need to continue optimizing, please start the next round."
            elif phase_context.get("version_status") == "archived":
                next_action = "The archived version cannot be published directly, please switch to the current testing version."
            return _build_phase_guard_blocked_response(
                tool_name="publish_agent_workshop_version",
                blocked_code=(
                    "active_version_requires_iteration"
                    if phase_context.get("version_status") == "active"
                    else "archived_version_blocked"
                    if phase_context.get("version_status") == "archived"
                    else "version_not_testing"
                ),
                message=(
                    f"当前阶段为{phase_context.get('phase_label')}，不能直接发布正式版本；"
                    "Only testing versions are allowed to be released."
                ),
                next_action=next_action,
                phase_context=phase_context,
                target_fields={
                    "version_id": clean_version_id,
                    "spec_id": phase_context.get("spec_id"),
                },
            )
        if phase_context.get("guard_available") and str(phase_context.get("latest_evaluation_decision") or "").strip().lower() != "pass":
            return _build_phase_guard_blocked_response(
                tool_name="publish_agent_workshop_version",
                blocked_code="latest_evaluation_not_pass",
                message=(
                    f"当前阶段为{phase_context.get('phase_label')}，不能直接发布正式版本；"
                    "Only the testing version whose latest real data test evaluation is pass can be released."
                ),
                next_action="First complete the latest real data test and confirm that the official acceptance conclusion is pass.",
                phase_context=phase_context,
                target_fields={
                    "version_id": clean_version_id,
                    "spec_id": phase_context.get("spec_id"),
                },
            )

        result = await AgentWorkshopService(db=db).publish_version(clean_version_id)
        payload = dict(result or {})
        version_status = payload.pop("status", None)
        return _json_response({
            "status": "ok",
            **payload,
            "version_status": version_status,
        })
    except Exception as exc:
        logger.error("Failed to publish Agent workshop version: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to publish Agent workshop version: {exc}"})


@tool
@register_tool(
    tool_id="evaluate_agent_workshop_version",
    name="Evaluate the Agent Workshop version",
    description="Perform an explicit evaluation and drop-in for the specified Agent workshop version, and return the latest evaluation results.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when the version is already in the testing/evaluation stage and needs to re-record the formal evaluation conclusion.",
    when_not_to_use="Not suitable for calling when version_id does not exist, has not yet entered testing, or just wants to see the latest evaluation results.",
    returns="Returns a JSON string containing version_id, evaluation, and summary of the latest decision.",
    example="evaluate_agent_workshop_version(version_id='spec_x_v1', evaluation_type='production-review', runtime_result_json='{\"output_text\":\"...\"}')",
    related_tools=["debug_agent_workshop_version", "run_agent_workshop_real_data_test", "iterate_agent_workshop_version"],
    data_source_handling="local_only",
)
async def evaluate_agent_workshop_version(
    version_id: Annotated[str, "Agent Workshop version ID"],
    evaluation_type: Annotated[str, "Evaluation type, default production-review"] = "production-review",
    sample_set_id: Annotated[str, "Sample set ID, can be empty"] = "",
    user_feedback: Annotated[str, "Evaluation supplementary feedback, can be empty"] = "",
    benchmark_outputs_json: Annotated[str, "benchmark Output array JSON, can be empty"] = "",
    runtime_result_json: Annotated[str, "Actual running result JSON object, can be empty"] = "",
) -> str:
    """Persist one explicit evaluation result for a workshop version."""
    try:
        clean_version_id = str(version_id or "").strip()
        if not clean_version_id:
            return _json_response({"status": "error", "message": "version_id cannot be empty"})

        benchmark_outputs = _parse_optional_json_list(benchmark_outputs_json, "benchmark_outputs_json")
        runtime_result = _parse_optional_json_object(runtime_result_json, "runtime_result_json")

        db = get_mongo_db()
        phase_context = await _resolve_workshop_version_phase_context(db, clean_version_id)
        if phase_context.get("guard_available") and not phase_context.get("exists"):
            return _json_response({"status": "error", "message": f"版本 {clean_version_id} 不存在"})
        if phase_context.get("guard_available"):
            version_status = str(phase_context.get("version_status") or "").strip().lower()
            current_phase = str(phase_context.get("phase") or "").strip().lower()
            allowed_phases = {"testing", "evaluation", "publish-ready"}
            if current_phase not in allowed_phases:
                next_action = "Please put the release into testing before performing formal evaluation."
                blocked_code = "version_not_testing"
                if version_status == "active":
                    blocked_code = "active_version_requires_iteration"
                    next_action = "The current version has been released; if you need to continue optimizing, please start the next round."
                elif version_status == "archived":
                    blocked_code = "archived_version_blocked"
                    next_action = "Archived versions cannot be evaluated further, please switch to the current testing version."
                return _build_phase_guard_blocked_response(
                    tool_name="evaluate_agent_workshop_version",
                    blocked_code=blocked_code,
                    message=(
                        f"当前阶段为{phase_context.get('phase_label')}，不能直接执行正式评估；"
                        "Only versions in the testing / evaluation / publish-ready stage are allowed to enter the evaluation link."
                    ),
                    next_action=next_action,
                    phase_context=phase_context,
                    target_fields={
                        "version_id": clean_version_id,
                        "spec_id": phase_context.get("spec_id"),
                    },
                )

        normalized_evaluation_type = str(evaluation_type or "production-review").strip() or "production-review"
        gap_tool_sync = await _auto_sync_gap_tools_to_workshop_version(db, clean_version_id)
        normalized_runtime_result = runtime_result or None
        if normalized_evaluation_type == "production-review" and normalized_runtime_result is not None:
            if not _has_workshop_runtime_evidence(normalized_runtime_result):
                return _json_response({
                    "status": "error",
                    "message": (
                        "production-review runtime_result_json is provided but lacks available evidence;"
                        "Requires at least one of output_text, report, output_payload, raw_result, debug_prompt or tool_trace"
                    ),
                })
            normalized_runtime_result = _with_nanobot_review_worker_flags(normalized_runtime_result)

        result = await AgentWorkshopService(db=db).evaluate_version(
            clean_version_id,
            evaluation_type=normalized_evaluation_type,
            sample_set_id=str(sample_set_id or "").strip() or None,
            user_feedback=str(user_feedback or "").strip(),
            benchmark_outputs=benchmark_outputs,
            runtime_result=normalized_runtime_result,
        )
        evaluation = result.get("evaluation") if isinstance(result, dict) else None
        decision = _read_mapping_or_attr(evaluation, "decision", None)
        # Convert Pydantic model to dict to avoid _json_response default=str Serialize it into a string
        # As a result, evaluation is not dict during front-end parsing, and decisions/scores cannot obtain values.
        if result and "evaluation" in result:
            eval_obj = result["evaluation"]
            if hasattr(eval_obj, "model_dump"):
                result["evaluation"] = eval_obj.model_dump(mode="json")
            elif hasattr(eval_obj, "dict"):
                result["evaluation"] = eval_obj.dict()
        return _json_response({
            "status": "ok",
            **(result or {}),
            "_tool_events": [
                *([
                    _build_tool_stage_event(
                        "evaluate_agent_workshop_version.auto_sync_gap_tools",
                        "ok",
                        f"The gap tool has been synchronized to the current version: {gap_tool_sync.get('status')}; tools={len(gap_tool_sync.get('required_tools') or [])}",
                    )
                ] if gap_tool_sync.get("status") in {"synced", "unchanged"} else []),
                _build_tool_stage_event(
                    "evaluate_agent_workshop_version.evaluate_version",
                    "ok",
                    f"The assessment has been dropped: decision={decision or 'unknown'}",
                ),
                _build_tool_stage_event(
                    "evaluate_agent_workshop_version",
                    "ok",
                    "版本评估已完成",
                ),
            ],
            "summary": {
                "version_id": clean_version_id,
                "spec_id": _read_mapping_or_attr(evaluation, "spec_id", None) or phase_context.get("spec_id"),
                "evaluation_id": _read_mapping_or_attr(evaluation, "evaluation_id", None),
                "evaluation_type": _read_mapping_or_attr(evaluation, "evaluation_type", None),
                "decision": decision,
                "overall_score": _read_mapping_or_attr(_read_mapping_or_attr(evaluation, "scores", {}), "overall", None),
                "recorded_in_workshop": bool(_read_mapping_or_attr(evaluation, "evaluation_id", None)),
            },
            "message": f"The version evaluation has been completed and the latest conclusion is {decision or 'unknown'}. ",
        })
    except Exception as exc:
        logger.error("Failed to evaluate Agent Workshop version: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to evaluate Agent Workshop version: {exc}"})


@tool
@register_tool(
    tool_id="iterate_agent_workshop_version",
    name="Launch the next iteration of Agent Workshop",
    description="Initiate the next iteration based on the specified Agent workshop version and create a new Session.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when the version has entered evaluation/publish-ready/published and needs to start the next round based on the existing conclusions.",
    when_not_to_use="Not suitable for calling when test evaluation has not been completed or is still in the early stages of generation/testing.",
    returns="Returns a JSON string containing source_version_id, session_id, spec_id, and ai_message.",
    example="iterate_agent_workshop_version(version_id='spec_x_v1', feedback='Supplementary explanation of sources of score fluctuations')",
    related_tools=["evaluate_agent_workshop_version", "build_agent_workshop_version", "publish_agent_workshop_version"],
    data_source_handling="local_only",
)
async def iterate_agent_workshop_version(
    version_id: Annotated[str, "Agent Workshop version ID"],
    feedback: Annotated[str, "Iteration feedback, can be empty"] = "",
) -> str:
    """Start the next workshop iteration from an evaluated or published version."""
    try:
        clean_version_id = str(version_id or "").strip()
        if not clean_version_id:
            return _json_response({"status": "error", "message": "version_id cannot be empty"})

        db = get_mongo_db()
        phase_context = await _resolve_workshop_version_phase_context(db, clean_version_id)
        if phase_context.get("guard_available") and not phase_context.get("exists"):
            return _json_response({"status": "error", "message": f"版本 {clean_version_id} 不存在"})
        if phase_context.get("guard_available"):
            version_status = str(phase_context.get("version_status") or "").strip().lower()
            current_phase = str(phase_context.get("phase") or "").strip().lower()
            allowed_phases = {"evaluation", "publish-ready", "published"}
            if current_phase not in allowed_phases:
                blocked_code = "phase_not_ready"
                next_action = "Please complete at least one formal assessment round before deciding whether to start another round."
                if version_status == "archived":
                    blocked_code = "archived_version_blocked"
                    next_action = "The archived version cannot be used as the starting point for the current iteration. Please switch to the latest version."
                return _build_phase_guard_blocked_response(
                    tool_name="iterate_agent_workshop_version",
                    blocked_code=blocked_code,
                    message=(
                        f"当前阶段为{phase_context.get('phase_label')}，不能直接开始下一轮；"
                        "Only versions in the evaluation / publish-ready / published stages are allowed to initiate iterate."
                    ),
                    next_action=next_action,
                    phase_context=phase_context,
                    target_fields={
                        "version_id": clean_version_id,
                        "spec_id": phase_context.get("spec_id"),
                    },
                )

        result = await AgentWorkshopService(db=db).iterate_version(
            clean_version_id,
            feedback=str(feedback or "").strip(),
        )
        return _json_response({
            "status": "ok",
            **(result or {}),
            "_tool_events": [
                _build_tool_stage_event(
                    "iterate_agent_workshop_version.iterate_version",
                    "ok",
                    f"Next round created Session: {result.get('session_id') or ''}; Draft version: {result.get('version_id') or ''}",
                ),
                _build_tool_stage_event(
                    "iterate_agent_workshop_version",
                    "ok",
                    "下一轮迭代已创建",
                ),
            ],
            "summary": {
                "source_version_id": result.get("source_version_id") or clean_version_id,
                "session_id": result.get("session_id"),
                "spec_id": result.get("spec_id") or phase_context.get("spec_id"),
                "version_id": result.get("version_id"),
                "version_status": result.get("version_status"),
                "feedback": str(feedback or "").strip(),
            },
        })
    except Exception as exc:
        logger.error("Failed to initiate the next iteration of Agent Workshop: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to initiate the next iteration of Agent Workshop: {exc}"})


@tool
@register_tool(
    tool_id="create_or_update_universal_agent_prompt_template",
    name="Create or update a UniversalAgent prompt word template",
    description="Create or update the default prompt word template for configured UniversalAgent candidates so that the runtime can read the template directly by agent_id.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Used when you have decided to create a profiled Agent candidate and need the Agent to read available prompt words at runtime.",
    when_not_to_use="Not suitable for tool binding or ability scouting.",
    returns="Returns a JSON string containing a summary of prompt_templates as written.",
    example="create_or_update_universal_agent_prompt_template(agent_id='valuation_candidate_v1', template_name='Valuation candidate template', system_prompt='You are a valuation analyst')",
    related_tools=["create_or_update_runtime_agent_config", "bind_agent_tools_and_validate_candidate"],
    data_source_handling="local_only",
)
async def create_or_update_universal_agent_prompt_template(
    agent_id: Annotated[str, "Corresponding to UniversalAgent agent_id"],
    template_name: Annotated[str, "模板名称"],
    system_prompt: Annotated[str, "系统提示词"],
    user_prompt: Annotated[str, "User prompt word, can be empty"] = "",
    tool_guidance: Annotated[str, "工具使用指导"] = "Prioritize using bound tools to obtain real data, do not make it up, and do not skip key verifications.",
    analysis_requirements: Annotated[str, "分析要求"] = "Complete tasks around a single responsibility, with clear conclusions and explanation of key basis and applicable boundaries.",
    output_format: Annotated[str, "输出格式"] = "Please output a structured conclusion and clarify core judgments, key basis, and risk warnings.",
    constraints: Annotated[str, "约束条件"] = "Do not exceed the Agent s single scope of responsibility.",
    status: Annotated[str, "Template status, default active"] = "active",
) -> str:
    """Create or update the UniversalAgent default prompt word template."""
    try:
        clean_agent_id = str(agent_id or "").strip()
        clean_template_name = str(template_name or "").strip()
        clean_system_prompt = _append_trading_guard(system_prompt)
        if not clean_agent_id or not clean_template_name or not clean_system_prompt:
            return _json_response({"status": "error", "message": "agent_id, template_name, system_prompt cannot be empty"})

        db = get_mongo_db()
        templates = _get_collection(db, "prompt_templates")
        if templates is None:
            return _json_response({"status": "error", "message": "The prompt_templates collection is not available in the current database"})

        query = {
            "agent_type": "universal",
            "agent_name": clean_agent_id,
            "workflow_id": None,
            "node_id": None,
            "status": status,
        }
        existing = await templates.find_one(query)
        content_model = TemplateContent(
            system_prompt=clean_system_prompt,
            user_prompt=user_prompt,
            tool_guidance=tool_guidance,
            analysis_requirements=analysis_requirements,
            output_format=output_format,
            constraints=_append_trading_guard_constraint(constraints),
        )
        if existing:
            await templates.update_one(
                {"_id": existing.get("_id")},
                {
                    "$set": {
                        "template_name": clean_template_name,
                        "content": content_model.model_dump(),
                        "remark": "nanobot generated candidate template",
                        "status": status,
                        "updated_at": datetime.utcnow(),
                    },
                    "$inc": {"version": 1},
                },
            )
            persisted = await templates.find_one({"_id": existing.get("_id")})
            action = "updated"
        else:
            await templates.insert_one(
                {
                    "agent_type": "universal",
                    "agent_name": clean_agent_id,
                    "template_name": clean_template_name,
                    "workflow_id": None,
                    "node_id": None,
                    "preference_type": None,
                    "content": content_model.model_dump(),
                    "remark": "nanobot generated candidate template",
                    "is_system": True,
                    "created_by": None,
                    "base_template_id": None,
                    "base_version": None,
                    "status": status,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "version": 1,
                }
            )
            persisted = await templates.find_one({"agent_type": "universal", "agent_name": clean_agent_id, "status": status}, sort=[("updated_at", -1)])
            action = "created"

        if persisted is None:
            return _json_response({"status": "error", "message": "The prompt word template failed to be read again after being written."})

        agent_configs = _get_collection(db, "agent_configs")
        if agent_configs is not None:
            await agent_configs.update_one(
                {"agent_id": clean_agent_id},
                {
                    "$set": {
                        "updated_at": _utc_now_iso(),
                        "metadata.default_prompt_template_id": str(persisted.get("_id") or ""),
                    }
                },
                upsert=True,
            )

        return _json_response({
            "status": "ok",
            "action": action,
            "template": _format_prompt_template_record(persisted),
            "prompt_contract": {
                "agent_type": "universal",
                "agent_name": clean_agent_id,
                "template_name": clean_template_name,
                "status": status,
                "workflow_id": None,
                "node_id": None,
                "must_match_universal_agent": True,
            },
        })
    except Exception as exc:
        logger.error("Failed to create or update UniversalAgent prompt word template: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to create or update UniversalAgent prompt word template: {exc}"})


@tool
@register_tool(
    tool_id="bind_agent_tools_and_validate_candidate",
    name="Bind Agent tools and verify candidates",
    description="Write tool_agent_bindings for the candidate Agent, and do a dry run verification based on the real runtime logic to confirm that the configured Agent has the minimum operable conditions; this verification is not equal to the official test acceptance of the Agent Workshop.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Used when agent_configs and prompt word templates have been written, ready to bind tools and confirm whether candidate Agents can be created normally by the runtime.",
    when_not_to_use="Not suitable for searching resources or generating prompt words.",
    returns="Returns a JSON string, including the bound tool list, prompt word template existence, and dry run verification results; the results only represent the options for instantiation at runtime, and do not represent that the Workshop version has been generated or has passed formal acceptance.",
    example="bind_agent_tools_and_validate_candidate(agent_id='valuation_candidate_v1', tool_ids='get_value_factor_bundle_tool,get_peer_comparison')",
    related_tools=["create_or_update_runtime_agent_config", "create_or_update_universal_agent_prompt_template"],
    data_source_handling="local_only",
)
async def bind_agent_tools_and_validate_candidate(
    agent_id: Annotated[str, "候选 Agent ID"],
    tool_ids: Annotated[str, "Tool IDs to bind, comma separated"],
    default_tools: Annotated[str, "Default tool IDs, comma separated; empty to reuse tool_ids"] = "",
    max_tool_calls: Annotated[int, "Maximum number of tool calls, default 5"] = 5,
    validate_runtime: Annotated[bool, "Whether to do dry run verification, default true"] = True,
) -> str:
    """Bind candidate agent tools and perform minimal runtime verification."""
    try:
        clean_agent_id = str(agent_id or "").strip()
        if not clean_agent_id:
            return _json_response({"status": "error", "message": "agent_id cannot be empty"})

        resolved_tools = _parse_string_list(tool_ids)
        resolved_default_tools = _parse_string_list(default_tools) or list(resolved_tools)
        if not resolved_tools:
            return _json_response({"status": "error", "message": "至少需要一个工具 ID"})

        registry = get_tool_registry()
        missing_tools = [tool_id for tool_id in resolved_tools if registry.get(tool_id) is None]
        if missing_tools:
            return _json_response({"status": "error", "message": f"以下工具未注册: {', '.join(missing_tools)}", "missing_tools": missing_tools})

        db = get_mongo_db()
        bindings = _get_collection(db, "tool_agent_bindings")
        agent_configs = _get_collection(db, "agent_configs")
        prompt_templates = _get_collection(db, "prompt_templates")
        if bindings is None or agent_configs is None:
            return _json_response({"status": "error", "message": "The tool_agent_bindings or agent_configs collections are not available in the current database"})

        await bindings.delete_many({"agent_id": clean_agent_id})
        await bindings.insert_many([
            {
                "agent_id": clean_agent_id,
                "tool_id": tool_id,
                "priority": index + 1,
                "is_active": True,
                "created_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
            }
            for index, tool_id in enumerate(resolved_tools)
        ])
        existing_config = await agent_configs.find_one({"agent_id": clean_agent_id}) or {}
        await agent_configs.update_one(
            {"agent_id": clean_agent_id},
            {
                "$set": {
                    "tools": resolved_tools,
                    "default_tools": resolved_default_tools,
                    "max_tool_calls": int(max_tool_calls),
                    "enabled": True,
                    "updated_at": _utc_now_iso(),
                }
            },
            upsert=True,
        )
        persisted_config = await agent_configs.find_one({"agent_id": clean_agent_id}) or {
            **existing_config,
            "agent_id": clean_agent_id,
            "tools": resolved_tools,
            "default_tools": resolved_default_tools,
            "max_tool_calls": int(max_tool_calls),
        }
        workshop_sync = await _sync_linked_workshop_versions(
            db=db,
            agent_id=clean_agent_id,
            candidate_config=persisted_config,
            resolved_tools=resolved_tools,
            resolved_default_tools=resolved_default_tools,
            max_tool_calls=int(max_tool_calls),
        )

        prompt_doc = None
        if prompt_templates is not None:
            prompt_doc = await prompt_templates.find_one(
                {"agent_type": "universal", "agent_name": clean_agent_id, "workflow_id": None, "node_id": None, "status": "active"},
                sort=[("updated_at", -1)],
            )

        validation: dict[str, Any] = {
            "prompt_template_found": prompt_doc is not None,
            "prompt_template": _format_prompt_template_record(prompt_doc) if prompt_doc else None,
            "dry_run": None,
        }

        if validate_runtime:
            sync_db = get_mongo_db_sync()
            BindingManager().set_database(sync_db)
            factory = AgentFactory()
            agent = factory.create_with_dynamic_tools(clean_agent_id, llm=None)
            validation["dry_run"] = {
                "instantiated": agent is not None,
                "agent_class": type(agent).__name__,
                "agent_id": getattr(agent, "agent_id", clean_agent_id),
                "loaded_tools": [getattr(tool, "name", str(tool)) for tool in getattr(agent, "_langchain_tools", [])],
                "output_field": getattr(agent, "_output_field", None),
            }

        return _json_response({
            "status": "ok",
            "agent_id": clean_agent_id,
            "bound_tools": resolved_tools,
            "default_tools": resolved_default_tools,
            "workshop_sync": workshop_sync,
            "validation": validation,
        })
    except Exception as exc:
        logger.error("Bind Agent tool and verify candidate failure: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Bind Agent tool and verify candidate failure: {exc}"})


@tool
@register_tool(
    tool_id="generate_confirmed_candidate_agent",
    name="Generate candidates after confirming the plan Agent",
    description="After the user clearly selects a plan, the configuration writing, prompt word template writing, tool binding and dry run verification are completed in one go; if it has been synchronized to Agent Workshop Draft, a test version will be automatically generated by default. Selected_plan_id, acknowledged_gaps and gap_report_json must be passed in the V2 process to avoid repeated gap analysis during the execution phase.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="After the requirements confirmation, capability inventory, and solution selection have been completed, and the user s clear solution selection is obtained, candidate Agents are generated with one call.",
    when_not_to_use="Do not call it before selecting a plan; it is not suitable for resource reconnaissance or gap analysis.",
    returns="Returns a JSON string containing the results of the three steps of writing, the final dry run verification results, optional automatic version generation results, and governance prompts related to Agent Workshop s formal acceptance boundaries.",
    example="generate_confirmed_candidate_agent(agent_id='valuation_candidate_v1', agent_name='Valuation candidates Agent', target_responsibility='Output A-share valuation conclusion', tool_ids='get_value_factor_bundle_tool', system_prompt='You are a valuation analyst', selected_plan_id='complete', acknowledged_gaps='[\"financial_ratio_calculator\"]', gap_report_json='{...}')",
    related_tools=["propose_agent_build_plans", "bind_agent_tools_and_validate_candidate", "resolve_agent_workshop_blocking_gaps"],
    data_source_handling="local_only",
)
async def generate_confirmed_candidate_agent(
    agent_id: Annotated[str, "候选 Agent ID"],
    agent_name: Annotated[str, "Candidate Agent display name"],
    target_responsibility: Annotated[str, "单一职责的一句话描述"],
    tool_ids: Annotated[str, "Tool IDs to be bound, separated by commas"],
    system_prompt: Annotated[str, "系统提示词"],
    user_prompt: Annotated[str, "User prompt word, can be empty"] = "",
    tool_guidance: Annotated[str, "工具使用指导"] = "Prioritize using bound tools to obtain real data, do not make it up, and do not skip key verifications.",
    analysis_requirements: Annotated[str, "分析要求"] = "Complete tasks around a single responsibility, with clear conclusions and explanation of key basis and applicable boundaries.",
    output_format: Annotated[str, "输出格式"] = "Please output a structured conclusion and clarify core judgments, key basis, and risk warnings.",
    constraints: Annotated[str, "约束条件"] = "Do not exceed the Agent s single scope of responsibility.",
    output_field: Annotated[str, "Output field name, default analysis_report"] = "analysis_report",
    workflow_stage: Annotated[str, "Workflow stage, default analyst"] = "analyst",
    report_label: Annotated[str, "Report display label, can be empty"] = "",
    show_in_reports: Annotated[bool, "Whether to enter the workflow report list, default true"] = True,
    execution_order: Annotated[int, "Workflow display/execution order, default 50"] = 50,
    template_name: Annotated[str, "Template name; automatically generated when empty"] = "",
    default_tools: Annotated[str, "Default tool ID, separated by commas; if empty, the first two items of tool_ids will be taken by default."] = "",
    max_tool_calls: Annotated[int, "Maximum number of tool calls, default 5"] = 5,
    category: Annotated[str, "Agent Category, default analyst"] = "analyst",
    callable_surfaces: Annotated[str, "Allow call entries, comma separated, default assistant,workflow,agent"] = "assistant,workflow,agent",
    input_mode: Annotated[str, "Input mode, default standalone"] = "standalone",
    enabled: Annotated[bool, "Whether to enable, default true"] = True,
    status: Annotated[str, "Template status, default active"] = "active",
    sync_to_workshop_draft: Annotated[bool, "Whether to create Agent Workshop Draft simultaneously, default true"] = True,
    auto_build_workshop_version: Annotated[bool, "If it has been synchronized to Agent Workshop Draft, whether to automatically generate a testable version, default true"] = True,
    confirmed: Annotated[bool, "是否已拿到用户明确确认"] = False,
    allow_overwrite: Annotated[bool, "If there is a risk of overwriting, is it allowed to overwrite existing configurations?"] = False,
    selected_plan_id: Annotated[str, "User-selected plan ID: direct/strict/enhanced/complete/quick/narrow; when empty, it is compatible with the old confirmation process"] = "",
    acknowledged_gaps: Annotated[str, "blocking gaps known and accepted by the user, JSON array or comma separated; old process can be empty"] = "",
    capability_inventory_json: Annotated[str, "prepare Stage capability inventory JSON, can be empty"] = "",
    gap_report_json: Annotated[str, "prepare gap_report JSON returned by stage analyze_spec_gaps. Complete/quick scheme must be passed; direct scheme can be empty"] = "",
) -> str:
    """After confirmation, candidate Agents are generated once."""
    try:
        if not confirmed:
            return _json_response({
                "status": "error",
                "message": "Without explicit confirmation from the user, writing is refused. Please generate a confirmation draft first and wait for user confirmation.",
            })

        clean_agent_id = str(agent_id or "").strip()
        clean_agent_name = str(agent_name or "").strip()
        clean_responsibility = str(target_responsibility or "").strip()
        clean_system_prompt = str(system_prompt or "").strip()
        clean_selected_plan_id = str(selected_plan_id or "").strip().lower()
        parsed_acknowledged_gaps = _parse_acknowledged_gaps(acknowledged_gaps)
        capability_inventory = _parse_optional_json_object(capability_inventory_json, "capability_inventory_json")
        gap_report = _parse_optional_json_object(gap_report_json, "gap_report_json")
        # ── 🔍 Key tracking log: records all parameters passed in by LLM ──
        logger.info(
            "[GenAgent][Params] agent_id=%s plan=%s acknowledged_gaps=%d gap_report_keys=%s gap_report_json_size=%d "
            "capability_inventory_size=%d selected_plan_id_raw=%r",
            clean_agent_id,
            clean_selected_plan_id,
            len(parsed_acknowledged_gaps),
            sorted(gap_report.keys()) if gap_report else [],
            len(str(gap_report_json or "")),
            len(str(capability_inventory_json or "")),
            str(selected_plan_id or "")[:120],
        )
        for i, item in list(enumerate(parsed_acknowledged_gaps))[:10]:
            logger.info("[GenAgent][Params]   acknowledged_gaps[%d] = %s", i, item[:200])
        for i, item in list(enumerate(gap_report.get("blocking_gaps") or []))[:10]:
            _desc = _gap_item_to_text(item)
            logger.info("[GenAgent][Params]   gap_report.blocking_gaps[%d] = %s", i, _desc[:200])
        if clean_selected_plan_id in {"complete", "quick"} and not gap_report:
            logger.warning(
                "[GenAgent][Params] ⚠️ %s Scheme but gap_report_json is empty! build_version will try to restore from builder_contracts",
                clean_selected_plan_id,
            )
        if clean_selected_plan_id == "narrow":
            _auto_update_intent(
                action="create_agent",
                stage="exploring",
                spec_id=clean_agent_id,
                spec_name=clean_agent_name,
                intent_summary=f"Agent「{clean_agent_name}」选择缩小需求范围",
                next_action="Back to demand redefinition, first narrow down the target/output scope and then redo capability inventory and plan confirmation.",
                task={"type": "agent", "id": clean_agent_id, "name": clean_agent_name, "status": "exploring"},
                clear_pending_options=True,
            )
            return _json_response({
                "status": "ok",
                "agent_id": clean_agent_id,
                "selected_plan_id": "narrow",
                "next_stage": "exploring",
                "message": "Returned to requirements redefinition in narrow scheme. This solution will not directly generate Agents. Please narrow down the scope first and then take inventory of capabilities again.",
            })
        if clean_selected_plan_id not in {"", "direct", "strict", "enhanced", "complete", "quick"}:
            return _json_response({"status": "error", "message": "selected_plan_id Only supports direct/strict/enhanced/complete/quick/narrow"})
        if clean_selected_plan_id == "quick":
            quick_constraint = _quick_plan_constraint_text(parsed_acknowledged_gaps)
            constraints = _append_trading_guard_constraint(f"{constraints}\n{quick_constraint}")
            tool_guidance = f"{tool_guidance}\n{quick_constraint}"
            analysis_requirements = f"{analysis_requirements}\n{quick_constraint}"
            output_format = f"{output_format}\n Information gaps must be marked for missing fields, and a comprehensive four-color rating will not be output."
        if not clean_agent_id or not clean_agent_name or not clean_responsibility or not clean_system_prompt:
            return _json_response({"status": "error", "message": "agent_id, agent_name, target_responsibility, system_prompt cannot be empty"})

        db = get_mongo_db()
        overwrite_risk = await _inspect_agent_overwrite_risk(db, clean_agent_id, status=status)
        if overwrite_risk["requires_explicit_overwrite"] and not allow_overwrite:
            return _json_response({
                "status": "error",
                "message": "The target Agent already has configuration, template or tool binding, but is not provided. allow_overwrite=True. ",
                "overwrite_risk": overwrite_risk,
            })

        resolved_default_tools = _parse_string_list(default_tools) or _parse_string_list(tool_ids)[:2]
        workshop_result = None
        if sync_to_workshop_draft:
            workshop_constraints = constraints
            if clean_selected_plan_id == "quick" and _quick_plan_constraint_text(parsed_acknowledged_gaps) not in workshop_constraints:
                workshop_constraints = f"{workshop_constraints}\n{_quick_plan_constraint_text(parsed_acknowledged_gaps)}"
            # 🔑 Key tracking log: print agent_id and agent_name
            logger.info(
                "[GenAgent][WriteDraft] About to be called create_or_update_agent_workshop_draft "
                "agent_id=%r agent_name=%r responsibility=%r",
                clean_agent_id, clean_agent_name, clean_responsibility[:80],
            )
            workshop_result = _parse_json_tool_result(await create_or_update_agent_workshop_draft.ainvoke({
                "agent_id": clean_agent_id,
                "agent_name": clean_agent_name,
                "target_responsibility": clean_responsibility,
                "output_field": output_field,
                "workflow_stage": workflow_stage,
                "report_label": report_label,
                "show_in_reports": show_in_reports,
                "execution_order": execution_order,
                "tool_ids": tool_ids,
                "preferred_methods": "quick_plan" if clean_selected_plan_id == "quick" else "",
                "constraints": workshop_constraints,
            }))
            # 🔑 Key tracking log: writing library results
            logger.info(
                "[GenAgent][WriteDraft] result status=%s spec_id=%r session_id=%r message=%s",
                workshop_result.get("status", ""),
                workshop_result.get("spec_id", ""),
                workshop_result.get("session_id", ""),
                str(workshop_result.get("message", ""))[:200],
            )
            if workshop_result.get("status") != "ok":
                logger.warning(
                    "[GenAgent][WriteDraft] ❌ workshop_draft Failure! The agent will not write to the database.full_result=%s",
                    json.dumps(workshop_result, ensure_ascii=False)[:500],
                )
                return _json_response({"status": "error", "stage": "workshop_draft", "result": workshop_result})

        config_result = _parse_json_tool_result(await create_or_update_runtime_agent_config.ainvoke({
            "agent_id": clean_agent_id,
            "agent_name": clean_agent_name,
            "description": clean_responsibility,
            "output_field": output_field,
            "workflow_stage": workflow_stage,
            "report_label": report_label,
            "show_in_reports": show_in_reports,
            "execution_order": int(execution_order),
            "category": category,
            "callable_surfaces": callable_surfaces,
            "input_mode": input_mode,
            "enabled": enabled,
        }))
        if config_result.get("status") != "ok":
            return _json_response({"status": "error", "stage": "agent_config", "result": config_result})

        # 🔑 Generic templates are only created separately when not synchronized to Workshop
        # When synchronizing to Workshop, Workshop will create the version template when building the version and synchronize the template binding of the short name configuration
        # Avoid generating two sets of duplicate templates
        prompt_result = {"status": "ok", "message": "skipped (workshop manages templates)"}
        if not sync_to_workshop_draft:
            prompt_result = _parse_json_tool_result(await create_or_update_universal_agent_prompt_template.ainvoke({
                "agent_id": clean_agent_id,
                "template_name": template_name or f"{clean_agent_name}模板",
                "system_prompt": clean_system_prompt,
                "user_prompt": user_prompt,
                "tool_guidance": tool_guidance,
                "analysis_requirements": analysis_requirements,
                "output_format": output_format,
                "constraints": constraints,
                "status": status,
            }))
            if prompt_result.get("status") != "ok":
                return _json_response({"status": "error", "stage": "prompt_template", "result": prompt_result})

        binding_result = _parse_json_tool_result(await bind_agent_tools_and_validate_candidate.ainvoke({
            "agent_id": clean_agent_id,
            "tool_ids": tool_ids,
            "default_tools": ",".join(resolved_default_tools),
            "max_tool_calls": max_tool_calls,
            "validate_runtime": True,
        }))
        if binding_result.get("status") != "ok":
            return _json_response({"status": "error", "stage": "bindings", "result": binding_result})

        dry_run_validation = binding_result.get("validation") or {}
        if sync_to_workshop_draft and isinstance(workshop_result, dict) and workshop_result.get("spec_id"):
            agent_configs = _get_collection(db, "agent_configs")
            workshop_session_id = str(workshop_result.get("session_id") or "").strip()
            builder_contracts_patch = {
                "selected_plan_id": clean_selected_plan_id or "legacy_confirmed",
                "acknowledged_gaps": parsed_acknowledged_gaps,
            }
            if capability_inventory:
                builder_contracts_patch["capability_inventory"] = capability_inventory
            if gap_report:
                builder_contracts_patch["gap_report"] = gap_report
            if clean_selected_plan_id == "quick":
                builder_contracts_patch["quick_plan_constraints"] = _quick_plan_constraint_text(parsed_acknowledged_gaps)
            sessions = _get_collection(db, "agent_workshop_sessions")
            if sessions is not None and workshop_session_id:
                await sessions.update_one(
                    {"session_id": workshop_session_id},
                    {"$set": {
                        "builder_contracts.selected_plan_id": builder_contracts_patch["selected_plan_id"],
                        "builder_contracts.acknowledged_gaps": parsed_acknowledged_gaps,
                        "builder_contracts.capability_inventory": capability_inventory,
                        "builder_contracts.gap_report": gap_report,
                        "builder_contracts.quick_plan_constraints": builder_contracts_patch.get("quick_plan_constraints", ""),
                        "gap_report": gap_report if gap_report else None,
                        "updated_at": _utc_now_iso(),
                    }},
                    upsert=False,
                )
            if agent_configs is not None:
                await agent_configs.update_one(
                    {"agent_id": clean_agent_id},
                    {
                        "$set": {
                            "metadata.source": "nanobot_generated",
                            "metadata.spec_id": workshop_result.get("spec_id"),
                            "metadata.session_id": workshop_result.get("session_id"),
                            "metadata.linked_agent_workshop": True,
                            "updated_at": _utc_now_iso(),
                        }
                    },
                    upsert=False,
                )

        workshop_version_result = None
        should_auto_build_workshop_version = (
            auto_build_workshop_version
            and not (clean_selected_plan_id == "complete" and bool(parsed_acknowledged_gaps))
            and clean_selected_plan_id != "quick"  # quick Scheme accepted gap, skipped auto-build
        )
        # ── 🔍 Trace log: auto-build decisions ──
        logger.info(
            "[GenAgent][AutoBuild] should_auto=%s plan=%s has_gaps=%s gap_report_keys=%s session_id=%s",
            should_auto_build_workshop_version,
            clean_selected_plan_id,
            bool(parsed_acknowledged_gaps),
            sorted(gap_report.keys()) if gap_report else [],
            str(workshop_result.get("session_id") or "") if isinstance(workshop_result, dict) else "N/A",
        )
        # Safety net: In the complete/quick scheme, if gap_report is not passed in, it is prohibited. auto-build
        # Otherwise build_version will rerun analyze_spec_gaps, resulting in inconsistent blocking_gap text,
        # As a result, acknowledged_gaps cannot be matched and the error is blocked.
        if clean_selected_plan_id in {"complete", "quick"} and not gap_report:
            logger.warning(
                "[GenAgent] gap_report_json Not passed in but is %s scheme, skip auto-build session_id=%s",
                clean_selected_plan_id,
                str(workshop_result.get("session_id") or "").strip(),
            )
            should_auto_build_workshop_version = False
        if should_auto_build_workshop_version and sync_to_workshop_draft and isinstance(workshop_result, dict):
            workshop_session_id = str(workshop_result.get("session_id") or "").strip()
            if workshop_session_id:
                workshop_version_result = await _auto_build_workshop_version_result(workshop_session_id)
                if workshop_version_result.get("status") != "ok":
                    error_message = str(workshop_version_result.get("message") or workshop_version_result.get("error") or "")
                    likely_gap_blocked = any(
                        marker in error_message.lower()
                        for marker in ("blocking", "gap", "缺口", "阻断")
                    )
                    _auto_update_intent(
                        action="create_agent",
                        stage="gap_resolving" if likely_gap_blocked else "ready_to_build",
                        spec_id=clean_agent_id,
                        spec_name=clean_agent_name,
                        intent_summary=f"Agent [{clean_agent_name}] Generated, but automatic build failed",
                        next_action=(
                            "Interpret the blocking gap found by the automatic build and call it after user confirmation resolve_agent_workshop_blocking_gaps"
                            if likely_gap_blocked
                            else "Check the cause of the build failure and call it again after repairing it. build_agent_workshop_version"
                        ),
                        task={
                            "type": "agent",
                            "id": clean_agent_id,
                            "name": clean_agent_name,
                            "status": "gap_resolving" if likely_gap_blocked else "ready_to_build",
                        },
                    )
                    return _json_response({"status": "error", "stage": "workshop_version", "result": workshop_version_result})
                built_version = workshop_version_result.get("version")
                if isinstance(built_version, dict):
                    built_version_id = str(built_version.get("version_id") or "").strip()
                else:
                    built_version_id = str(built_version or "").strip()
                if built_version_id and agent_configs is not None:
                    await agent_configs.update_one(
                        {"agent_id": clean_agent_id},
                        {
                            "$set": {
                                "metadata.latest_workshop_version_id": built_version_id,
                                "updated_at": _utc_now_iso(),
                            }
                        },
                        upsert=False,
                    )

        workshop_governance = {
            "asset_layer": "agent_workshop" if sync_to_workshop_draft else "runtime_only",
            "spec_id": workshop_result.get("spec_id") if isinstance(workshop_result, dict) else None,
            "session_id": workshop_result.get("session_id") if isinstance(workshop_result, dict) else None,
            "spec_status": "draft" if sync_to_workshop_draft else "not_synced",
            "version_generated": bool((workshop_version_result or {}).get("version")),
            "version_id": _extract_governance_version_id(workshop_version_result),
            "selected_plan_id": clean_selected_plan_id or "legacy_confirmed",
            "acknowledged_gaps": parsed_acknowledged_gaps,
            "official_acceptance_status": "not_started",
            "acceptance_ready": False,
            "release_ready": False,
            "next_required_action": (
                "At present, the Agent Workshop test version has been automatically generated; the next step is to conduct real data testing directly, and decide whether it can be released based on the latest evaluation conclusion."
                if (workshop_version_result or {}).get("version")
                else "The next step should be to generate a test version of Agent Workshop before testing on real data; the current dry-run only proves that the candidate runtime configuration can be instantiated."
                if sync_to_workshop_draft
                else "Currently, only runtime selection and generation have been completed; if you need formal test acceptance of Agent Workshop, please synchronize to Draft first and generate version."
            ),
        }

        # 🔥 Automatically update the intent context as"Generation completed"
        #    auto-build success: building = Version is built and ready for testing
        #    Not yet auto-build: ready_to_build = Draft Generated, version to be built
        #    quick Plan: building = Gap accepted, ready for testing (skipping auto-build)
        built_workshop_version = bool((workshop_version_result or {}).get("version"))
        if clean_selected_plan_id == "complete" and parsed_acknowledged_gaps and not built_workshop_version:
            next_stage = "gap_resolving"
            next_action_text = "Fill in the blocking gaps according to the confirmed complete plan, and then build the test version after completion"
            task_status = "gap_resolving"
        elif clean_selected_plan_id == "quick":
            next_stage = "building"
            next_action_text = "The simplified version of Agent has been generated, and the gap has been confirmed and accepted; the next step is to directly run the real data test (run_agent_workshop_real_data_test)"
            task_status = "building"
        elif built_workshop_version:
            next_stage = "building"
            next_action_text = "The test version has been generated according to the confirmed plan; the next step is to run the real data test (run_agent_workshop_real_data_test)"
            task_status = "building"
        else:
            next_stage = "ready_to_build"
            next_action_text = "Draft has been generated according to the confirmed plan; the next step is to call build_agent_workshop_version to generate a test version"
            task_status = "ready_to_build"
        _auto_update_intent(
            action="create_agent",
            stage=next_stage,
            spec_id=clean_agent_id,
            spec_name=clean_agent_name,
            intent_summary=f"Agent「{clean_agent_name}」已按 {clean_selected_plan_id or 'legacy'} 方案生成",
            next_action=next_action_text,
            clear_pending_options=True,
            task={
                "type": "agent",
                "id": clean_agent_id,
                "name": clean_agent_name,
                "status": task_status,
            },
        )

        return _json_response({
            "status": "ok",
            "agent_id": clean_agent_id,
            "nanobot_guidance": (
                "Candidate Agent has been generated successfully. Please briefly report the generated results to users, focusing on business value.\n\n"
                "Reply rules:\n"
                "1. Just describe the Agent name, core responsibilities, and what reports to output.\n"
                "2. You can briefly introduce the report structure (what each chapter covers) to help users establish expectations.\n"
                "3.  [Prohibited] Listing available paths/call portals/Assistant/Workflow/Agent Workshop and other technical access methods——Users don t care where they are called from, this is an internal matter of the platform.\n"
                "4.  [Prohibited] Display of technical metadata such as Agent ID, execution sequence, running mode, output field name, etc.\n"
                "5. The tool name can be briefly described in business language (such as peer valuation comparison, historical quantile, DCF valuation ) in Bound Capabilities , but do not write function names like get_xxx.\n"
                "6. The end naturally guides the user to the next step: you can run it with a real stock code to test and verify the effect (such as Do you want to run it with 600519? )."
            ),
            "confirmation": {
                "confirmed": confirmed,
                "allow_overwrite": allow_overwrite,
                "selected_plan_id": clean_selected_plan_id or "legacy_confirmed",
                "acknowledged_gaps": parsed_acknowledged_gaps,
                "execution_message": "The plan confirmed by the user in the prepare stage has been executed, and the gap analysis will not be reconfirmed this time.",
            },
            "steps": {
                "workshop_draft": workshop_result,
                "agent_config": config_result,
                "prompt_template": prompt_result,
                "bindings_and_validation": binding_result,
                "workshop_version": workshop_version_result,
            },
            "final_validation": dry_run_validation,
            "governance_boundary": {
                "selected_plan_id": clean_selected_plan_id or "legacy_confirmed",
                "acknowledged_gaps": parsed_acknowledged_gaps,
                "next_stage": next_stage,
                "runtime_candidate_validation": {
                    "agent_config_written": config_result.get("status") == "ok",
                    "prompt_template_written": prompt_result.get("status") == "ok",
                    "tool_bindings_written": binding_result.get("status") == "ok",
                    "dry_run_instantiated": bool(((dry_run_validation.get("dry_run") or {}).get("instantiated"))),
                },
                "workshop_governance": workshop_governance,
                "warnings": [
                    (
                        "Dry-run It only means that the candidate Agent can be instantiated according to the runtime configuration; the test version has been automatically generated, but this still does not mean that the real data test has passed."
                        if workshop_governance["version_generated"]
                        else "Dry-run It only means that the candidate Agent can be instantiated according to the runtime configuration, but it does not mean that the Agent Workshop has generated a version."
                        if clean_selected_plan_id != "quick"
                        else "Lite Agent has skipped the Workshop version build (Gap confirmed acceptance). You can run real data tests directly, or manually call build_agent_workshop_version to generate a version."
                    ),
                    "Even if the test version has been automatically generated, the sample real data test evaluation recorded in the Agent Workshop must first be completed, and the latest evaluation conclusion should be used as the basis for release."
                    if workshop_governance["version_generated"]
                    else "The simplified version of Agent can directly use run_agent_workshop_real_data_test to conduct real data testing; after passing the test, it will be evaluated whether to release it."
                    if clean_selected_plan_id == "quick"
                    else "Even if the test version has been automatically generated, the sample real data test evaluation recorded in the Agent Workshop must first be completed, and the latest evaluation conclusion should be used as the basis for release.",
                ],
            },
        })
    except Exception as exc:
        logger.error("Failed to generate candidate Agent after confirmation: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"Failed to generate candidate Agent after confirmation: {exc}"})


@tool
@register_tool(
    tool_id="resolve_agent_workshop_blocking_gaps",
    name="Completing the gaps in Agent s workshop capabilities",
    description="When gap analysis finds blocking_gaps, Skill generation sessions are automatically created for each gap and wait for completion, returning new capabilities that can be bound.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="heavy",
    when_to_use=(
        "When blocking_gaps are found (from any source: auto-build s gap_report, analyze_agent_workshop_gaps return value, or evaluation feedback),"
        "And these gaps are used when they are indeed reusable capabilities."
        "Instead of manually calling the Skill creation tool one by one, gap completion can be completed in one call."
    ),
    when_not_to_use=(
        "Not suitable for calling when the gap is not yet clear (confirm blocking_gaps exists first);"
        "Not suitable for completing too many items at once (>3 ) gaps, in that case it is recommended to process them in batches;"
        "Not suitable for calling in TESTING or PUBLISHING phases without gaps."
    ),
    returns="Returns a JSON string containing the processing results for each gap, the resulting Skill information, and subsequent recommendations.",
    example="resolve_agent_workshop_blocking_gaps(session_id='ws_abc123')",
    related_tools=[
        "analyze_agent_workshop_gaps",
        "build_agent_workshop_version",
        "search_project_capabilities",
    ],
    data_source_handling="local_only",
)
async def resolve_agent_workshop_blocking_gaps(
    session_id: Annotated[str, "Agent workshop session ID"],
    blocking_gaps_json: Annotated[str, "Optional JSON array, directly specifying the gap description to be completed; if it is empty, it will be read from the session s gap_report"] = "",
    max_wait_seconds: Annotated[int, "The maximum waiting time (seconds) for each Skill to be generated, default 300"] = 300,
    auto_continue_build: Annotated[bool, "Whether to automatically perform capability recheck after completion and continue building the version, default true"] = True,
    confirm_external_data_risk: Annotated[bool, "If the gap involves external data sources/third-party interfaces, have the risks been clearly disclosed to users and confirmed?"] = False,
    allow_medium_similarity_autocreate: Annotated[bool, "When hitting a candidate Skill with medium similarity (0.6-0.85), whether to allow the new creation to continue directly"] = False,
    mode: Annotated[str, "Task mode: auto or manual_confirmed, consistent with start_agent_workshop_gap_resolution; overridden if specified allow_medium_similarity_autocreate"] = "",
) -> str:
    """Automatically complete the ability gaps in Agent s workshop.

    Process:
    1. Read from workshop session gap_report.blocking_gaps
    2. Start skill generation sessions in parallel for each gap
    3. Wait for all Skill generation to complete (with timeout)
    4. Return results for subsequent build_version use
    """
    try:
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            return _json_response({"status": "error", "message": "session_id cannot be empty"})

        # Unify the mode parameter: override if mode is specified allow_medium_similarity_autocreate
        clean_mode = str(mode or "").strip().lower()
        if clean_mode in ("auto", "manual_confirmed"):
            allow_medium_similarity_autocreate = clean_mode == "auto"
        elif clean_mode:
            return _json_response({"status": "error", "message": f"mode Only supports auto or manual_confirmed, actually passed in: {clean_mode}"})

        db = get_mongo_db()
        from app.services.skill_generation_service import SESSION_COLLECTION

        # Parse the real initiating user (for Skill ownership and permissions), and fall back to nanobot
        resolved_user_id = ""
        try:
            resolved_user_id = str(require_current_user_id() or "").strip()
        except Exception:
            resolved_user_id = ""
        effective_user_id = resolved_user_id or "nanobot"

        # Always load the workshop session and extract the Agent source context (spec_id/name/target) for reverse tracing
        ws_service = AgentWorkshopService(db=db)
        workshop_session = await ws_service._load_session(clean_session_id)
        agent_spec_id = ""
        agent_name = ""
        agent_goal = ""
        if workshop_session is not None:
            agent_spec_id = str(getattr(workshop_session, "spec_id", "") or "")
            spec_snapshot = getattr(workshop_session, "current_spec_snapshot", None)
            if spec_snapshot is not None:
                agent_name = str(getattr(spec_snapshot, "name", "") or "")
                agent_goal = str(getattr(spec_snapshot, "primary_goal", "") or "")
            # When the caller has no user context, it will fall back to the workshop session and belong to the user to avoid falling into anonymity. nanobot
            if not resolved_user_id:
                session_user = str(getattr(workshop_session, "user_id", "") or "").strip()
                if session_user:
                    effective_user_id = session_user

        # 1. get blocking_gaps
        gaps: list[str] = []
        if blocking_gaps_json.strip():
            try:
                parsed = json.loads(blocking_gaps_json)
                if isinstance(parsed, list):
                    gaps = [str(g).strip() for g in parsed if str(g).strip()]
            except (json.JSONDecodeError, TypeError):
                return _json_response({"status": "error", "message": "blocking_gaps_json Not a valid JSON array"})

        if not gaps:
            # Reading from a loaded workshop session
            if workshop_session is None:
                return _json_response({"status": "error", "message": f"Agent 工坊会话 {clean_session_id} 不存在"})

            gap_report = workshop_session.gap_report
            if not gap_report:
                # Try performing a gap analysis first
                gap_analysis = await ws_service.analyze_gaps(clean_session_id)
                gap_report = gap_analysis.get("gap_report") if isinstance(gap_analysis, dict) else None

            if not gap_report:
                return _json_response({"status": "error", "message": "Unable to obtain gap analysis report, please execute first analyze_agent_workshop_gaps"})

            blocking_gaps = getattr(gap_report, "blocking_gaps", None) or []
            if isinstance(blocking_gaps, list):
                gaps = [str(g).strip() for g in blocking_gaps if str(g).strip()]

        if not gaps:
            return _json_response({
                "status": "ok",
                "message": "没有需要补全的阻塞缺口",
                "gaps_found": 0,
                "skills_generated": [],
            })

        capped_gaps = gaps[:3]
        if len(gaps) > 3:
            logger.warning(
                "[resolve_gaps] The number of gaps %d exceeds the default upper limit. Only the first 3 will be processed. The rest are recommended to be batched.: %s",
                len(gaps), capped_gaps,
            )

        risky_gaps = [gap for gap in capped_gaps if _contains_external_data_risk(gap)]
        if risky_gaps and not confirm_external_data_risk:
            return _json_response({
                "status": "blocked",
                "blocked_by": "external_data_risk_confirmation",
                "message": "Detected gaps may rely on external data sources or third-party interfaces, and the sources and risks must be disclosed to the user and confirmed before being generated.",
                "workshop_session_id": clean_session_id,
                "risky_gaps": risky_gaps,
                "next_action": "After confirming with the user, call resolve_agent_workshop_blocking_gaps again and pass confirm_external_data_risk=true",
            })

        wait_seconds = max(60, min(int(max_wait_seconds), 600))

        logger.info(
            "[resolve_gaps] Start filling %d capability gaps (workshop_session=%s, timeout=%ds): %s",
            len(capped_gaps), clean_session_id, wait_seconds, capped_gaps,
        )

        # 2. Start skill generation for each gap
        results: list[dict[str, Any]] = []

        async def _process_single_gap(gap_index: int, gap_description: str) -> dict[str, Any]:
            gap_id = f"gap_{gap_index + 1}"
            gap_result = await _resolve_single_gap_capability(
                db=db,
                ws_service=ws_service,
                gap_description=gap_description,
                gap_id=gap_id,
                gap_index=gap_index,
                workshop_session_id=clean_session_id,
                agent_spec_id=agent_spec_id,
                agent_name=agent_name,
                agent_goal=agent_goal,
                user_id=effective_user_id,
                allow_medium_similarity_autocreate=allow_medium_similarity_autocreate,
                related_gaps=capped_gaps,
                handoff_intent="auto_resolve_blocking_gap",
            )
            if str(gap_result.get("status") or "") != "generating":
                return gap_result

            skill_session_id = str(gap_result.get("session_id") or gap_result.get("skill_session_id") or "").strip()
            if not skill_session_id:
                gap_result["status"] = "failed"
                gap_result["error"] = "Skill 生成会话丢失"
                return gap_result

            poll_interval = 5
            elapsed = 0
            while elapsed < wait_seconds:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                gap_result["elapsed_seconds"] = elapsed

                session_doc = await db[SESSION_COLLECTION].find_one({"session_id": skill_session_id})
                if not session_doc:
                    gap_result["status"] = "failed"
                    gap_result["error"] = "Skill 生成会话丢失"
                    return gap_result

                status = session_doc.get("status", "")
                pipeline_stage = session_doc.get("pipeline_stage", "")
                pipeline_message = session_doc.get("pipeline_message", "")
                gap_result["pipeline_stage"] = pipeline_stage
                gap_result["pipeline_message"] = pipeline_message

                if status == "completed":
                    spec = session_doc.get("spec") or {}
                    gap_result["status"] = "completed"
                    gap_result["skill_tool_id"] = spec.get("tool_id", "")
                    gap_result["skill_display_name"] = spec.get("display_name", "")
                    logger.info(
                        "[resolve_gaps] Skill #%d Generation completed: tool_id=%s display_name=%s elapsed=%ds",
                        gap_index,
                        gap_result["skill_tool_id"],
                        gap_result["skill_display_name"],
                        elapsed,
                    )
                    return gap_result

                if status == "failed":
                    gap_result["status"] = "failed"
                    gap_result["error"] = f"Skill 生成失败: {pipeline_message}"
                    return gap_result

                logger.debug(
                    "[resolve_gaps] Skill #%d still being generated: status=%s stage=%s elapsed=%ds",
                    gap_index, status, pipeline_stage, elapsed,
                )

            gap_result["status"] = "timeout"
            gap_result["error"] = f"Skill 生成超时（{wait_seconds}s）"
            return gap_result

        # Process all gaps in parallel
        tasks = [
            _process_single_gap(i, gap_desc)
            for i, gap_desc in enumerate(capped_gaps)
        ]
        results = await asyncio.gather(*tasks)

        successful = [r for r in results if r["status"] in ("completed", "reused_existing")]
        completed = [r for r in results if r["status"] == "completed"]
        reused = [r for r in results if r["status"] == "reused_existing"]
        pending_confirmation = [r for r in results if r["status"] == "needs_dedup_confirmation"]
        failed = [r for r in results if r["status"] in ("failed", "timeout")]

        auto_continue = {
            "enabled": bool(auto_continue_build),
            "status": "skipped",
            "capability_search": None,
            "gap_analysis": None,
            "tooling_plan": None,
            "build_version": None,
            "error": None,
        }

        if auto_continue_build and successful:
            try:
                # Step A: Re-retrieval capabilities to help subsequent gap/tool planning and consumption new generation Skill
                capability_query = " ".join(_dedupe_string_list([
                    *capped_gaps,
                    agent_name,
                    agent_goal,
                    *[str(item.get("skill_display_name") or "") for item in successful],
                    *[str(item.get("skill_tool_id") or "") for item in successful],
                ])).strip()
                capability_hits = await CapabilityIndexService(db).search_capabilities(
                    query=capability_query or "agent capability",
                    top_k=12,
                    bindable_only=True,
                    source_types=["builtin_tool", "skill", "external_skill", "mcp_tool"],
                )
                auto_continue["capability_search"] = {
                    "query": capability_query or "agent capability",
                    "count": len(capability_hits),
                    "top_results": [_format_capability_hit(hit) for hit in capability_hits[:5]],
                }

                # Step B/C: Reanalyze the gap -> Generate tool plan
                # v3.6.0 Item 6 Path B: No longer automatically called after the generation is completed build_version / sync_version_required_tools
                # Instead, write skill_review_queue and wait for user review. The binding will be triggered only after user confirmation.
                gap_analysis_result = await ws_service.analyze_gaps(clean_session_id)
                tooling_plan_result = await ws_service.generate_tooling_plan(clean_session_id)
                phase_context = await _resolve_workshop_session_phase_context(db, clean_session_id)
                current_version_id = str(phase_context.get("current_version_id") or "").strip()
                current_version_status = str(phase_context.get("version_status") or "").strip().lower()

                # Write records to be audited (path B HITL)
                pending_reviews: list[dict[str, Any]] = []
                try:
                    from app.pro.services.skill_review_service import SkillReviewService
                    review_service = SkillReviewService(db=db)
                    pending_reviews = await review_service.create_pending_reviews_for_workshop(
                        workshop_session_id=clean_session_id,
                        agent_spec_id=agent_spec_id,
                        agent_name=agent_name,
                        user_id=effective_user_id,
                        successful_items=successful,
                    )
                except Exception as review_exc:
                    logger.warning(
                        "[resolve_gaps] Writing to skill_review_queue failed (not blocking): %s",
                        review_exc, exc_info=True,
                    )

                auto_continue["gap_analysis"] = {
                    "spec_id": gap_analysis_result.get("spec_id") if isinstance(gap_analysis_result, dict) else "",
                    "blocking_gaps": len(_read_mapping_or_attr(gap_analysis_result.get("gap_report") if isinstance(gap_analysis_result, dict) else None, "blocking_gaps", []) or []),
                }
                auto_continue["tooling_plan"] = {
                    "spec_id": tooling_plan_result.get("spec_id") if isinstance(tooling_plan_result, dict) else "",
                    "missing_capabilities": len(_read_mapping_or_attr(tooling_plan_result.get("tooling_plan") if isinstance(tooling_plan_result, dict) else None, "missing_capabilities", []) or []),
                }
                # build_version Fields remain backwards compatible, but versions are no longer automatically built
                auto_continue["build_version"] = {
                    "spec_id": agent_spec_id,
                    "version_id": current_version_id,
                    "existing_version_status": current_version_status,
                    "skipped": True,
                    "reason": "pending_user_review",
                    "pending_review_count": len(pending_reviews),
                }
                auto_continue["pending_user_review"] = {
                    "count": len(pending_reviews),
                    "tool_ids": [r.get("tool_id") for r in pending_reviews if r.get("tool_id")],
                    "review_ids": [r.get("review_id") for r in pending_reviews if r.get("review_id")],
                    "next_action": (
                        "Called after user review "
                        "/api/agent-workshop/skill-review/{session_id}/{tool_id}/confirm or /reject"
                    ),
                }
                auto_continue["status"] = "pending_user_review"
            except Exception as auto_exc:
                logger.warning("[resolve_gaps] Automatic renewal failed: %s", auto_exc, exc_info=True)
                auto_continue["status"] = "failed"
                auto_continue["error"] = str(auto_exc)

        summary = {
            "total_gaps": len(capped_gaps),
            "generated": len(completed),
            "reused": len(reused),
            "completed": len(completed),
            "successful": len(successful),
            "needs_confirmation": len(pending_confirmation),
            "failed": len(failed),
            "generated_tool_ids": [r["skill_tool_id"] for r in completed if r["skill_tool_id"]],
            "reused_tool_ids": [r["skill_tool_id"] for r in reused if r["skill_tool_id"]],
            "failed_gaps": [
                {
                    "gap_id": r.get("gap_id"),
                    "gap_description": r.get("gap_description"),
                    "error": r.get("error") or r.get("pipeline_message") or "补齐失败",
                    "skill_session_id": r.get("session_id"),
                }
                for r in failed
            ],
            "pending_confirmation_details": [
                {
                    "gap_id": r.get("gap_id"),
                    "gap_description": r.get("gap_description"),
                    "dedup_candidate": r.get("dedup_candidate") or {},
                    "pipeline_message": r.get("pipeline_message"),
                }
                for r in pending_confirmation
            ],
            "next_action": (
                (
                    "There is a medium similarity candidate Skill waiting for confirmation:"
                    + "；".join([
                        f"缺口「{r.get('gap_description') or r.get('gap_id') or '?'}」"
                        + "命中候选 Skill「"
                        + str((r.get('dedup_candidate') or {}).get('name') or '?') + '」'
                        + f"（相似度 {(r.get('dedup_candidate') or {}).get('score') or 0:.0%}）"
                        for r in pending_confirmation
                    ])
                    + ". Please show the user the name, functional description and similarity of the candidate Skill."
                    "Ask the user to confirm whether to reuse an existing skill or create a new one."
                )
                if pending_confirmation
                else (
                    # v3.6.0 Item 6 Path B: All Skills require user review after generation and will no longer be automatically bound.
                    "All gaps have been filled, and the generated Skill is waiting for user review. Please show users the code and test results for each Skill,"
                    "Called after user confirmation /api/agent-workshop/skill-review/{session_id}/{tool_id}/confirm binding,"
                    "or /reject to reject (the skill remains in the workshop). After all Skills are approved, the build_agent_workshop_version build version will be called."
                    if len(successful) == len(capped_gaps)
                    else (
                        f"已补全 {len(completed)}/{len(capped_gaps)} 个缺口，"
                        "Remaining gaps may require manual processing. The generated Skill is waiting for user review (bind after confirmation)."
                        "After the review is completed, it is recommended to call build_agent_workshop_version to build the version."
                    )
                )
            ),
            "user_facing_message": (
                (
                    f"Agent「{agent_name}」有 {len(failed)} 个能力缺口自动补齐失败，Agent 版本不能视为完整通过："
                    + "、".join([
                        f" [{r.get('gap_description') or r.get('gap_id') or '?'}] Reason for failure:{r.get('error') or r.get('pipeline_message') or 'unknown'}"
                        for r in failed
                    ])
                    + ". Please fix or retry these skills before continuing to build, review, or publish the Agent."
                )
                if failed
                else (
                    (
                        "There is a medium similarity candidate Skill waiting for confirmation:\n"
                        + "\n".join([
                            f"• 缺口「{r.get('gap_description') or r.get('gap_id') or '?'}」"
                            + f" → Candidate Skill: {str((r.get('dedup_candidate') or {}).get('name') or '?')}] "
                            + f"（相似度 {round(float((r.get('dedup_candidate') or {}).get('score') or 0) * 100)}%）"
                            + (
                                f"\n  Function description:{str((r.get('dedup_candidate') or {}).get('description') or '')[:200]}"
                                if str((r.get('dedup_candidate') or {}).get('description') or '').strip()
                                else ""
                            )
                            for r in pending_confirmation
                        ])
                        + "\n\n Please show the name and function description of the candidate Skill to the user, explain the pros and cons of reusing vs. creating a new one, and let the user make a choice."
                    )
                    if pending_confirmation
                    else (
                        # v3.6.0 Item 6 Path B: After successful generation, it will no longer be automatically bound and the user will be prompted for review.
                        f"已为 Agent「{agent_name}」自动补齐 {len(successful)} 个能力缺口：\n"
                        + "\n".join([
                            f"• 「{r.get('skill_display_name') or r.get('skill_tool_id') or '?'}」"
                            + f" (Gap:{r.get('gap_description', '')}) "
                            for r in successful
                        ])
                        + "\n\n These skills pass quality gates (grammar/sandbox/evaluation) but are not automatically bound to the Agent."
                        "Please show the code and test results of each Skill to users and let them decide whether to bind:\n"
                        "  - Confirm binding: call /api/agent-workshop/skill-review/{session_id}/{tool_id}/confirm\n"
                        "  - Refuse to bind: call /api/agent-workshop/skill-review/{session_id}/{tool_id}/reject (Skill Leave it in the workshop and can be reused later)\n"
                        "After all Skill reviews are completed, continue the Agent version building process."
                        if successful
                        else "If any gaps were not successfully filled, please check the reason for the failure and try again."
                    )
                )
            ),
        }

        logger.info(
            "[resolve_gaps] Completed: completed=%d failed=%d tool_ids=%s",
            len(completed), len(failed), summary["generated_tool_ids"],
        )

        # 🔥 record Agent → Gap → Skill The parent-child task chain ensures that Nanobot returns to the parent after completing the Skill. Agent
        # At the same time, write the dedup candidates that require user confirmation into last_proposed_items to support subsequent reference resolution.
        dedup_items = [
            {
                "index": idx + 1,
                "id": f"dedup_{r.get('gap_id') or idx}",
                "name": f"缺口「{r.get('gap_description') or r.get('gap_id') or '?'}」的候选 Skill「{str((r.get('dedup_candidate') or {}).get('name') or '?')}」",
                "description": (
                    f"相似度 {round(float((r.get('dedup_candidate') or {}).get('score') or 0) * 100)}%；"
                    + f"Candidate description:{str((r.get('dedup_candidate') or {}).get('description') or '')[:200]}"
                ),
                "gap_id": str(r.get("gap_id") or ""),
                "candidate_name": str((r.get("dedup_candidate") or {}).get("name") or ""),
                "candidate_score": float((r.get("dedup_candidate") or {}).get("score") or 0),
            }
            for idx, r in enumerate(pending_confirmation)
        ]
        if dedup_items:
            _auto_update_intent(
                action="resolve_gap",
                stage="gap_resolving",
                spec_id=agent_spec_id,
                spec_name=agent_name,
                pending_question=f"Agent「{agent_name}」有 {len(dedup_items)} 个缺口发现相似候选 Skill，请确认对每个缺口是复用候选还是新建 Skill？",
                proposed_items=dedup_items,
                active_subtask="Waiting for user confirmation of candidate Skill reuse/new creation",
                next_action="After the user confirms, call resolve_agent_workshop_blocking_gaps again and pass in clear parameters.",
            )

        for idx, gap_text in enumerate(capped_gaps):
            _auto_update_intent(
                action="resolve_gap",
                stage="gap_resolving",
                spec_id=agent_spec_id,
                spec_name=agent_name,
                active_subtask=f"为 Agent「{agent_name}」补齐缺口：{gap_text}",
                next_action=summary.get("next_action") or "Return to the parent Agent to continue building/testing",
                task={
                    "type": "gap",
                    "id": f"{clean_session_id}:gap_{idx + 1}",
                    "name": gap_text[:80],
                    "status": "completed" if idx < len(successful) else "failed_or_pending",
                    "parent_id": agent_spec_id,
                },
            )
        for item in successful:
            gaps_all_successful = len(successful) == len(capped_gaps)
            next_stage_after_skill = (
                "building"
                if auto_continue.get("status") == "completed"
                else "ready_to_build"
                if gaps_all_successful
                else "gap_resolving"
            )
            _auto_update_intent(
                action="resolve_gap",
                stage=next_stage_after_skill,
                spec_id=agent_spec_id,
                spec_name=agent_name,
                linked_skill={
                    "skill_id": str(item.get("skill_tool_id") or ""),
                    "skill_name": str(item.get("skill_display_name") or item.get("skill_tool_id") or ""),
                    "gap": str(item.get("gap_description") or ""),
                    "status": str(item.get("status") or ""),
                },
                task={
                    "type": "skill",
                    "id": str(item.get("skill_tool_id") or item.get("session_id") or ""),
                    "name": str(item.get("skill_display_name") or item.get("skill_tool_id") or ""),
                    "status": str(item.get("status") or ""),
                    "parent_id": agent_spec_id,
                },
            )

        return _json_response({
            "status": "error" if failed else "ok",
            "message": summary.get("user_facing_message", ""),
            "workshop_session_id": clean_session_id,
            "summary": summary,
            "results": results,
            "auto_continue": auto_continue,
        })

    except Exception as exc:
        logger.error("Failed to fill gaps in Agent s workshop capabilities: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"补全能力缺口失败: {exc}"})


@tool
@register_tool(
    tool_id="start_agent_workshop_gap_resolution",
    name="Start the asynchronous filling task of Agent capability gap",
    description="Create a gap resolution job and return job_id for subsequent polling progress and control.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="When gap filling may take a long time, create an asynchronous job first and then manage it through the inspect/cancel/retry tool.",
    when_not_to_use="Not suitable for calling when session_id is invalid.",
    returns="Returns a JSON string containing job_id, status, gaps and idempotency_key.",
    example="start_agent_workshop_gap_resolution(session_id='ws_123')",
    related_tools=[
        "inspect_agent_workshop_gap_resolution",
        "cancel_agent_workshop_gap_resolution",
        "retry_agent_workshop_gap_resolution_item",
    ],
    data_source_handling="local_only",
)
async def start_agent_workshop_gap_resolution(
    session_id: Annotated[str, "Agent workshop session ID"],
    blocking_gaps_json: Annotated[str, "Optional JSON array, directly specify the gap description; when empty, read from session gap_report"] = "",
    mode: Annotated[str, "Task mode: auto or manual_confirmed, default manual_confirmed"] = "manual_confirmed",
    idempotency_key: Annotated[str, "Idempotent key; press when empty session_id + gaps Automatically generated"] = "",
    max_items: Annotated[int, "The maximum number of gaps included in the job, default 3, maximum 10"] = 3,
) -> str:
    """Create a job to fill the Agent capability gap asynchronously, and return job_id and initial status."""
    try:
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            return _json_response({"status": "error", "message": "session_id cannot be empty"})

        db = get_mongo_db()
        ws_service = AgentWorkshopService(db=db)
        workshop_session = await ws_service._load_session(clean_session_id)
        if workshop_session is None:
            return _json_response({"status": "error", "message": f"Agent 工坊会话 {clean_session_id} 不存在"})

        gaps: list[str] = []
        if str(blocking_gaps_json or "").strip():
            try:
                parsed = json.loads(blocking_gaps_json)
                if isinstance(parsed, list):
                    gaps = [str(item).strip() for item in parsed if str(item).strip()]
            except Exception as exc:
                return _json_response({"status": "error", "message": f"blocking_gaps_json Parsing failed: {exc}"})
        if not gaps:
            gap_report = getattr(workshop_session, "gap_report", None)
            if gap_report is None:
                analysis = await ws_service.analyze_gaps(clean_session_id)
                gap_report = analysis.get("gap_report") if isinstance(analysis, dict) else None
            gaps = _extract_blocking_gaps_from_report(gap_report)

        capped_limit = max(1, min(int(max_items), 10))
        gaps = gaps[:capped_limit]
        if not gaps:
            return _json_response({
                "status": "ok",
                "message": "There are currently no blocking gaps, so there is no need to create an asynchronous completion task.",
                "workshop_session_id": clean_session_id,
                "created": False,
            })

        clean_mode = str(mode or "manual_confirmed").strip().lower() or "manual_confirmed"
        if clean_mode not in {"auto", "manual_confirmed"}:
            clean_mode = "manual_confirmed"

        effective_idempotency_key = str(idempotency_key or "").strip() or _build_gap_resolution_idempotency_key(clean_session_id, gaps)
        collection = _get_collection(db, _GAP_RESOLUTION_JOB_COLLECTION)
        if collection is None:
            return _json_response({"status": "error", "message": f"数据库中不可用集合: {_GAP_RESOLUTION_JOB_COLLECTION}"})

        existing_docs = await collection.find({
            "workshop_session_id": clean_session_id,
            "idempotency_key": effective_idempotency_key,
        }).to_list(length=5)
        for doc in existing_docs:
            if str((doc or {}).get("status") or "").strip().lower() in _GAP_JOB_ACTIVE_STATUSES:
                logger.info(
                    "[GapJob][Start] idempotent_hit session_id=%s key=%s existing_job_id=%s status=%s",
                    clean_session_id,
                    effective_idempotency_key,
                    doc.get("job_id"),
                    doc.get("status"),
                )
                return _json_response({
                    "status": "ok",
                    "created": False,
                    "message": "Hit an idempotent task and return to the existing one in progress job",
                    "job": {
                        "job_id": doc.get("job_id"),
                        "status": doc.get("status"),
                        "workshop_session_id": doc.get("workshop_session_id"),
                        "mode": doc.get("mode"),
                        "idempotency_key": doc.get("idempotency_key"),
                    },
                })

        now_iso = _utc_now_iso()
        seed = f"{clean_session_id}:{effective_idempotency_key}:{now_iso}"
        job_id = _build_gap_resolution_job_id(seed)
        job_gaps = [
            {
                "gap_id": f"gap_{index + 1}",
                "description": gap,
                "status": "pending",
                "pipeline_stage": "queued",
                "pipeline_message": "等待 worker 执行",
                "error": None,
                "skill_session_id": "",
                "skill_tool_id": "",
                "skill_display_name": "",
                "retry_count": 0,
                "auto_retry_count": 0,
                "next_retry_at": "",
                "dead_letter": {},
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            for index, gap in enumerate(gaps)
        ]

        job_doc = {
            "job_id": job_id,
            "workshop_session_id": clean_session_id,
            "spec_id": str(getattr(workshop_session, "spec_id", "") or ""),
            "version_id": "",
            "user_id": str(getattr(workshop_session, "user_id", "") or ""),
            "status": "pending",
            "mode": clean_mode,
            "idempotency_key": effective_idempotency_key,
            "execution": {
                "runner": "worker_required",
                "state": "queued",
                "note": "Phase 3 The job protocol is dropped first; execution is taken over by the background worker",
                "retry_policy": {
                    "max_attempts": _GAP_AUTO_RETRY_MAX_ATTEMPTS,
                    "base_delay_seconds": _GAP_AUTO_RETRY_BASE_DELAY_SECONDS,
                    "max_delay_seconds": _GAP_AUTO_RETRY_MAX_DELAY_SECONDS,
                },
            },
            "gaps": job_gaps,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        await collection.insert_one(job_doc)

        logger.info(
            "[GapJob][Start] created session_id=%s job_id=%s gaps=%d mode=%s key=%s",
            clean_session_id,
            job_id,
            len(job_gaps),
            clean_mode,
            effective_idempotency_key,
        )

        return _json_response({
            "status": "ok",
            "created": True,
            "message": "A gap resolution job has been created and is waiting for worker consumption",
            "job": {
                "job_id": job_id,
                "status": "pending",
                "workshop_session_id": clean_session_id,
                "spec_id": job_doc.get("spec_id"),
                "mode": clean_mode,
                "idempotency_key": effective_idempotency_key,
                "summary": _summarize_gap_job_gaps(job_gaps),
            },
        })
    except Exception as exc:
        logger.error("Failed to start Agent gap asynchronous filling task: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"启动异步补齐任务失败: {exc}"})


@tool
@register_tool(
    tool_id="inspect_agent_workshop_gap_resolution",
    name="View the asynchronous filling tasks for Agent capability gaps",
    description="Query the current status of the gap resolution job and the progress of each gap.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when you need to continuously check the progress of the completion task in Agent Studio.",
    when_not_to_use="Not suitable for calling when job_id does not exist.",
    returns="Returns a JSON string containing job status, gap list, and summary count.",
    example="inspect_agent_workshop_gap_resolution(job_id='gap_job_xxx')",
    related_tools=[
        "start_agent_workshop_gap_resolution",
        "cancel_agent_workshop_gap_resolution",
        "retry_agent_workshop_gap_resolution_item",
    ],
    data_source_handling="local_only",
)
async def inspect_agent_workshop_gap_resolution(
    job_id: Annotated[str, "gap resolution job_id"],
    include_gaps: Annotated[bool, "Whether to return each gap details, default true"] = True,
) -> str:
    """Query the status, summary and (optional) gap details of the gap resolution job."""
    try:
        clean_job_id = str(job_id or "").strip()
        if not clean_job_id:
            return _json_response({"status": "error", "message": "job_id 不能为空"})

        db = get_mongo_db()
        collection = _get_collection(db, _GAP_RESOLUTION_JOB_COLLECTION)
        if collection is None:
            return _json_response({"status": "error", "message": f"数据库中不可用集合: {_GAP_RESOLUTION_JOB_COLLECTION}"})

        doc = await collection.find_one({"job_id": clean_job_id})
        if not doc:
            return _json_response({"status": "error", "message": f"job {clean_job_id} 不存在"})

        gaps = list(doc.get("gaps") or [])
        summary = _summarize_gap_job_gaps(gaps)
        logger.info(
            "[GapJob][Inspect] job_id=%s status=%s summary=%s",
            clean_job_id,
            doc.get("status"),
            summary,
        )
        payload = {
            "status": "ok",
            "job": {
                "job_id": doc.get("job_id"),
                "workshop_session_id": doc.get("workshop_session_id"),
                "spec_id": doc.get("spec_id"),
                "version_id": doc.get("version_id"),
                "user_id": doc.get("user_id"),
                "status": doc.get("status"),
                "mode": doc.get("mode"),
                "idempotency_key": doc.get("idempotency_key"),
                "execution": doc.get("execution") or {},
                "summary": _summarize_gap_job_gaps(gaps),
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("updated_at"),
            },
        }
        if include_gaps:
            payload["job"]["gaps"] = gaps
        return _json_response(payload)
    except Exception as exc:
        logger.error("View Agent gap asynchronous filling task failed: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"查看异步补齐任务失败: {exc}"})


@tool
@register_tool(
    tool_id="cancel_agent_workshop_gap_resolution",
    name="Cancel Agent capability gap asynchronous filling task",
    description="Mark the pending/running gap resolution job as canceled.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Used when the user explicitly requests to stop the current completion task.",
    when_not_to_use="Not suitable for canceling completed tasks.",
    returns="Returns a JSON string containing the cancellation results and updated summary.",
    example="cancel_agent_workshop_gap_resolution(job_id='gap_job_xxx')",
    related_tools=[
        "inspect_agent_workshop_gap_resolution",
        "retry_agent_workshop_gap_resolution_item",
    ],
    data_source_handling="local_only",
)
async def cancel_agent_workshop_gap_resolution(
    job_id: Annotated[str, "gap resolution job_id"],
    reason: Annotated[str, "Reason for cancellation, optional"] = "",
) -> str:
    """Cancel pending/running gap resolution job."""
    try:
        clean_job_id = str(job_id or "").strip()
        if not clean_job_id:
            return _json_response({"status": "error", "message": "job_id 不能为空"})

        db = get_mongo_db()
        collection = _get_collection(db, _GAP_RESOLUTION_JOB_COLLECTION)
        if collection is None:
            return _json_response({"status": "error", "message": f"数据库中不可用集合: {_GAP_RESOLUTION_JOB_COLLECTION}"})

        doc = await collection.find_one({"job_id": clean_job_id})
        if not doc:
            return _json_response({"status": "error", "message": f"job {clean_job_id} 不存在"})

        current_status = str(doc.get("status") or "").strip().lower()
        if current_status in _GAP_JOB_TERMINAL_STATUSES:
            return _json_response({
                "status": "ok",
                "message": f"job 已处于终态: {current_status}，无需取消",
                "job": {
                    "job_id": clean_job_id,
                    "status": current_status,
                    "summary": _summarize_gap_job_gaps(list(doc.get("gaps") or [])),
                },
            })

        now_iso = _utc_now_iso()
        updated_gaps: list[dict[str, Any]] = []
        for gap in list(doc.get("gaps") or []):
            item = dict(gap or {})
            gap_status = str(item.get("status") or "").strip().lower()
            if gap_status not in {"completed", "failed", "timeout"}:
                item["status"] = "cancelled"
                item["pipeline_message"] = str(reason or "用户取消任务")
                item["updated_at"] = now_iso
            updated_gaps.append(item)

        await collection.update_one(
            {"job_id": clean_job_id},
            {
                "$set": {
                    "status": "cancelled",
                    "gaps": updated_gaps,
                    "updated_at": now_iso,
                    "execution.state": "cancelled",
                    "execution.cancel_reason": str(reason or "").strip(),
                }
            },
        )

        logger.info(
            "[GapJob][Cancel] done job_id=%s reason=%s summary=%s",
            clean_job_id,
            str(reason or "").strip() or "-",
            _summarize_gap_job_gaps(updated_gaps),
        )

        return _json_response({
            "status": "ok",
            "message": "Canceled gap resolution job",
            "job": {
                "job_id": clean_job_id,
                "status": "cancelled",
                "summary": _summarize_gap_job_gaps(updated_gaps),
                "updated_at": now_iso,
            },
        })
    except Exception as exc:
        logger.error("Failed to cancel Agent gap asynchronous filling task: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"取消异步补齐任务失败: {exc}"})


@tool
@register_tool(
    tool_id="retry_agent_workshop_gap_resolution_item",
    name="Retrying a single gap in an Agent gap filling task",
    description="Reset a gap to pending and wait for the worker to re-execute the item.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    when_to_use="Use it when you want to retry a single item after a gap fails/times out/cancels.",
    when_not_to_use="It is not appropriate to repeatedly retry a gap that is still running.",
    returns="Returns a JSON string containing the job summary and target gap status after retry.",
    example="retry_agent_workshop_gap_resolution_item(job_id='gap_job_xxx', gap_id='gap_1')",
    related_tools=[
        "inspect_agent_workshop_gap_resolution",
        "cancel_agent_workshop_gap_resolution",
    ],
    data_source_handling="local_only",
)
async def retry_agent_workshop_gap_resolution_item(
    job_id: Annotated[str, "gap resolution job_id"],
    gap_id: Annotated[str, "Target gap ID, e.g. gap_1"],
    reason: Annotated[str, "Retry reason, optional"] = "",
) -> str:
    """Retry a single failure/timeout/cancellation item in a gap resolution job."""
    try:
        clean_job_id = str(job_id or "").strip()
        clean_gap_id = str(gap_id or "").strip()
        if not clean_job_id:
            return _json_response({"status": "error", "message": "job_id 不能为空"})
        if not clean_gap_id:
            return _json_response({"status": "error", "message": "gap_id 不能为空"})

        db = get_mongo_db()
        collection = _get_collection(db, _GAP_RESOLUTION_JOB_COLLECTION)
        if collection is None:
            return _json_response({"status": "error", "message": f"数据库中不可用集合: {_GAP_RESOLUTION_JOB_COLLECTION}"})

        doc = await collection.find_one({"job_id": clean_job_id})
        if not doc:
            return _json_response({"status": "error", "message": f"job {clean_job_id} 不存在"})

        now_iso = _utc_now_iso()
        target_after: dict[str, Any] | None = None
        updated_gaps: list[dict[str, Any]] = []
        found = False
        for gap in list(doc.get("gaps") or []):
            item = dict(gap or {})
            if str(item.get("gap_id") or "").strip() != clean_gap_id:
                updated_gaps.append(item)
                continue

            found = True
            current_status = str(item.get("status") or "").strip().lower()
            if current_status in {"pending", "running"}:
                return _json_response({
                    "status": "error",
                    "message": f"gap {clean_gap_id} 当前状态为 {current_status}，无需重试",
                })

            item["status"] = "pending"
            item["pipeline_stage"] = "queued"
            item["pipeline_message"] = str(reason or "Submitted for retry, waiting for worker execution")
            item["error"] = None
            item["updated_at"] = now_iso
            item["retry_count"] = int(item.get("retry_count") or 0) + 1
            item["auto_retry_count"] = 0
            item["next_retry_at"] = ""
            item["dead_letter"] = {}
            target_after = item
            updated_gaps.append(item)

        if not found:
            return _json_response({"status": "error", "message": f"job {clean_job_id} 中不存在 gap_id={clean_gap_id}"})

        await collection.update_one(
            {"job_id": clean_job_id},
            {
                "$set": {
                    "status": "pending",
                    "gaps": updated_gaps,
                    "updated_at": now_iso,
                    "execution.state": "queued",
                }
            },
        )

        return _json_response({
            "status": "ok",
            "message": "Target gap has been reset to pending",
            "job": {
                "job_id": clean_job_id,
                "status": "pending",
                "summary": _summarize_gap_job_gaps(updated_gaps),
                "updated_at": now_iso,
            },
            "gap": target_after,
        })
    except Exception as exc:
        logger.error("Retry Agent gap asynchronous completion failed: %s", exc, exc_info=True)
        return _json_response({"status": "error", "message": f"重试异步补齐项失败: {exc}"})


__all__ = [
    "search_project_capabilities",
    "propose_agent_build_plans",
    "inspect_runtime_agent_configs",
    "inspect_agent_blueprints",
    "get_agent_blueprint_details",
    "inspect_agent_workshop_assets",
    "prepare_agent_requirement_intake",
    "prepare_agent_generation_confirmation",
    "create_or_update_agent_workshop_draft",
    "analyze_agent_workshop_gaps",
    "generate_agent_workshop_tooling_plan",
    "build_agent_workshop_version",
    "debug_agent_workshop_version",
    "run_agent_workshop_real_data_test",
    "publish_agent_workshop_version",
    "evaluate_agent_workshop_version",
    "iterate_agent_workshop_version",
    "create_or_update_runtime_agent_config",
    "create_or_update_universal_agent_prompt_template",
    "bind_agent_tools_and_validate_candidate",
    "generate_confirmed_candidate_agent",
    "resolve_agent_workshop_blocking_gaps",
    "start_agent_workshop_gap_resolution",
    "inspect_agent_workshop_gap_resolution",
    "cancel_agent_workshop_gap_resolution",
    "retry_agent_workshop_gap_resolution_item",
]


async def _get_progress_collection():
    """Get workshop_test_progress collection (lazy initialization)."""
    try:
        db = get_mongo_db()
        collection = db.get_collection("workshop_test_progress")
        await collection.create_index("version_id", unique=True)
        return collection
    except Exception:
        return None


def _get_current_intent_stage() -> str:
    """Read the intent stage of the current thread (module storage first, contextvar second)."""
    try:
        from core.tools.context import get_latest_nanobot_intent
        intent = get_latest_nanobot_intent()
        if isinstance(intent, dict):
            return str(intent.get("stage") or "").strip()
    except Exception:
        pass
    try:
        from core.tools.context import get_current_assistant_thread_context
        ctx = get_current_assistant_thread_context() or {}
        intent = ctx.get("intent") or {}
        if isinstance(intent, dict):
            return str(intent.get("stage") or "").strip()
    except Exception:
        pass
    return ""


def _extract_json_from_markdown(text: str) -> str:
    """Extract JSON string from markdown code block."""
    clean = str(text or "").strip()
    if clean.startswith("```"):
        # Remove the first line ```json / ```
        lines = clean.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return clean


def _humanize_plan_id(plan_id: str) -> str:
    """Translate the internal plan_id into a user-readable plan name."""
    mapping = {
        "direct": "推荐完整交付",
        "strict": "保守可追溯版",
        "enhanced": "扩展增强版",
        "complete": "完整方案",
        "quick": "快速方案",
        "narrow": "缩小范围",
    }
    return mapping.get(str(plan_id or "").strip().lower(), "方案")


def _to_str_list(value: Any) -> list[str]:
    """Convert any value to a list of strings.

    - None / null value → []
    - list / tuple → item by item str() and filter out null values
    - Others → [str(value)]  (filter null values)
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result
    text = str(value or "").strip()
    return [text] if text else []


def _fallback_build_plans(blocking_gaps: list[Any], non_blocking_gaps: list[Any]) -> dict[str, Any]:
    """Regularized plan generation when LLM parsing fails."""
    blocking_count = len(blocking_gaps)
    blocking_descriptions = []
    for g in blocking_gaps:
        if isinstance(g, dict):
            desc = str(g.get("description") or g.get("gap") or "")
        else:
            desc = str(g)
        if desc:
            blocking_descriptions.append(desc)

    if blocking_count == 0:
        candidate_plans = [
            {
                "plan_id": "direct",
                "plan_name": "推荐完整交付",
                "description": "The existing capabilities have covered the requirements and can directly generate a complete version of Agent and enter real data testing according to the original core risk/analysis dimensions.",
                "required_new_skills": [],
                "estimated_effort": "低",
                "risk": "Capabilities are covered and the main risks come from real data quality and subsequent acceptance results.",
                "gap_summary": "All analysis dimensions are supported by direct tools and there are no data gaps.",
                "feasibility": "Can be implemented directly without additional development.",
                "recommended": True,
            },
            {
                "plan_id": "strict",
                "plan_name": "保守可追溯版",
                "description": "Existing capabilities are still used, but output boundaries are tightened: only conclusions clearly supported by tools and data are output, and parts that are not covered or have insufficient data are marked as information gaps.",
                "required_new_skills": [],
                "estimated_effort": "低",
                "risk": "The coverage is more robust, but the report expression will be more conservative, and some extended interpretations will not be carried out.",
                "gap_summary": "All analysis dimensions are supported by direct tools, but inferential conclusions are strictly limited.",
                "feasibility": "Can be implemented directly without additional development.",
                "recommended": False,
            },
            {
                "plan_id": "enhanced",
                "plan_name": "扩展增强版",
                "description": "On the basis that the core requirements have been met, non-blocking enhancements can be used as optional extensions, such as more detailed warning classification, more risk signals or richer scenario descriptions.",
                "required_new_skills": [],
                "estimated_effort": "中",
                "risk": "Not required for current delivery; may increase testing and interpretation complexity if extended too much.",
                "gap_summary": "Core dimensions are supported by direct tools, while extended dimensions may require additional data access.",
                "feasibility": "Achievable, but extensions require additional development and data access.",
                "recommended": False,
            },
        ]
        recommended_plan_id = "direct"
    elif blocking_count <= 2:
        candidate_plans = [
            {
                "plan_id": "complete",
                "plan_name": "完整方案",
                "description": f"补齐 {blocking_count} 个阻塞性能力缺口，输出完整功能。",
                "required_new_skills": blocking_descriptions,
                "estimated_effort": "高",
                "risk": "New capabilities need to be generated, which may fail or be time consuming",
                "gap_summary": f"有 {blocking_count} 个阻塞性缺口需要补齐，补齐后所有维度均可覆盖。",
                "feasibility": f"Need to create new Skill to complete {blocking_count} gap, may fail or be time consuming. Completion method: Create a new Skill or access external data sources.",
                "recommended": True,
            },
            {
                "plan_id": "quick",
                "plan_name": "快速方案",
                "description": "Use existing capabilities to make simplified versions and skip missing capabilities.",
                "required_new_skills": [],
                "estimated_effort": "低",
                "risk": "Incomplete functionality, some output will be degraded or omitted",
                "gap_summary": f"有 {blocking_count} 个维度无法覆盖，将标注为'数据不足'或做降级处理。",
                "feasibility": "It can be implemented directly, but some analysis dimensions will be missing or degraded.",
                "recommended": False,
            },
        ]
        recommended_plan_id = "complete"
    else:
        candidate_plans = [
            {
                "plan_id": "complete",
                "plan_name": "完整方案",
                "description": f"补齐 {blocking_count} 个阻塞性能力缺口，输出完整功能。",
                "required_new_skills": blocking_descriptions,
                "estimated_effort": "高",
                "risk": "Multiple new capabilities need to be generated, which takes a long time",
                "gap_summary": f"有 {blocking_count} 个阻塞性缺口需要补齐，补齐后所有维度均可覆盖。",
                "feasibility": f"Need to create multiple skills to complete {blocking_count} A gap has a long cycle and may fail. Completion method: Create a new Skill or access external data sources.",
                "recommended": True,
            },
            {
                "plan_id": "quick",
                "plan_name": "快速方案",
                "description": "Use existing capabilities to make a simplified version, giving priority to covering core dimensions.",
                "required_new_skills": [],
                "estimated_effort": "低",
                "risk": "Incomplete functionality, some output will be degraded or omitted",
                "gap_summary": f"有 {blocking_count} 个维度无法覆盖，将标注为'数据不足'或做降级处理。",
                "feasibility": "It can be implemented directly, but many analysis dimensions will be missing or degraded.",
                "recommended": False,
            },
            {
                "plan_id": "narrow",
                "plan_name": "缩小范围",
                "description": "Narrow the scope of requirements to a subset that can be covered by existing capabilities.",
                "required_new_skills": [],
                "estimated_effort": "低",
                "risk": "只覆盖部分需求",
                "gap_summary": f"After narrowing the scope, only the dimensions that can be supported by existing capabilities are covered.{blocking_count} gap dimensions are not in range.",
                "feasibility": "Achievable, but requires narrowing the Agent s scope of responsibilities.",
                "recommended": False,
            },
        ]
        recommended_plan_id = "complete"

    return {
        "candidate_plans": candidate_plans,
        "recommended_plan_id": recommended_plan_id,
        "pending_question": "Which option do you want to adopt?",
    }
