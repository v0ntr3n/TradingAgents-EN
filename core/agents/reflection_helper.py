"""
Reflection node unity helper.

All reflection nodes follow the same pattern:
1. Build reflection prompt
2. Adjust LLM to refine the structure JSON
3. write to mem0(infer=False, memory_kind=xxx_lesson) 
4. On failure, fallback to the original text (i.e. current behavior) without blocking the main process.

Three scenarios share this helper:
- Item 2: Review and Reflection (trade_lesson)
- Item 3: Researcher Report Reflection (analysis_lesson)
- Item 8: Debate reflection (debate_lesson)
"""

import asyncio
import json
import logging
import re
import threading
from typing import Any, Dict, Optional

from core.memory.models import MemoryScope
from core.memory.service import get_memory_service

logger = logging.getLogger(__name__)

# Reflect on the LLM call timeout (seconds), when the timeout expires, it will be downgraded to the original text writing
_REFLECTION_LLM_TIMEOUT = 30


def _resolve_reflection_llm_client(db) -> Optional[Any]:
    """Parse reflection from system configuration using LLM client.

    No more hard-coding providers, but in the order of model selection in system settings
     (quick_analysis_model → deep_analysis_model → first enabled configuration)
    Parse the complete LLMConfig and build the UnifiedLLMClient. Reflection is a lightweight refining task;
    Prefer using the quick_analysis model to control costs.

    db Type compatible:
    - sync PyMongo Database → direct inquiry
    - Motor AsyncIOMotorDatabase / proxy object → Automatically fallback to sync connection
       (Motor The find_one is an async method, the synchronous call only returns the coroutine and does not actually execute the query)

    If the database is unavailable or no configuration is available, None is returned; the caller should skip reflection refining accordingly.
    Downgrade to original writing (infer=False) , Instead of using a hard-coded provider to cover the whole story——
    If the system is not configured with this provider, the Doudi client will also not work.
    """
    try:
        from app.services.intelligent_assistant_service import (
            get_system_llm_config_from_config_doc,
        )
        # Reuse db type detection of mem0 configuration layer: Motor async client will automatically fall back to synchronous connection
        from core.memory.config import _read_active_system_config

        config_doc = _read_active_system_config(db)
        if not config_doc:
            logger.warning("[Reflection] The system configuration does not exist or fails to read, reflecting that LLM is unavailable.")
            return None

        llm_config = get_system_llm_config_from_config_doc(config_doc)
        if llm_config is None:
            logger.warning("[Reflection] No LLM configuration available in system configuration, reflection LLM is not available")
            return None

        from core.llm import UnifiedLLMClient

        logger.info(
            "[Reflection] Analysis and reflection from system configuration LLM: provider=%s model=%s",
            llm_config.provider,
            llm_config.model,
        )
        return UnifiedLLMClient.from_config(llm_config)
    except Exception as e:
        logger.warning("[Reflection] Parsing LLM from system configuration failed: %s", e)
        return None


def run_reflection_sync(**kwargs) -> bool:
    """run_reflection A synchronization wrapper for calls from sync contexts such as ResearcherAgent.execute.

    Automatically handles two scenarios:
    1. The current thread has no running event loop → direct asyncio.run()
    2. The current thread has a running event loop (such as a sync node called by LangGraph in an async context)
       → Create an independent event loop to run in a new thread

    All exceptions are caught and downgraded to False to ensure they do not block the main process.
    """
    try:
        try:
            asyncio.get_running_loop()
            running_loop = True
        except RuntimeError:
            running_loop = False

        if not running_loop:
            # There is no running event loop, just use asyncio.run
            return asyncio.run(run_reflection(**kwargs))

        # There is a running event loop, running in a new thread
        result: Dict[str, Any] = {"success": False, "error": None}

        def _run_in_thread():
            try:
                result["success"] = asyncio.run(run_reflection(**kwargs))
            except Exception as e:
                result["error"] = e

        t = threading.Thread(target=_run_in_thread, daemon=True)
        t.start()
        t.join(timeout=_REFLECTION_LLM_TIMEOUT + 10)
        if t.is_alive():
            logger.warning("[Reflection] sync Wrapper thread times out, downgrade returns False")
            return False
        if result["error"]:
            logger.warning("[Reflection] sync Wrapper thread exception: %s", result["error"])
            return False
        return result["success"]
    except Exception as e:
        logger.warning("[Reflection] run_reflection_sync Abnormal: %s", e)
        return False


async def run_reflection(
    *,
    db: Any,
    user_id: str,
    agent_id: str,
    scope: MemoryScope,
    memory_kind: str,
    system_prompt: str,
    user_prompt: str,
    fallback_content: str,
    fallback_metadata: Dict[str, Any],
    llm_client: Any = None,
) -> bool:
    """Execute reflection refinement nodes and downgrade them on failure.

    Process:
    1. Adjust LLM to extract structured JSON (timeout 30s)
    2. success → write to mem0(infer=False, memory_kind=xxx_lesson, reflection_success=True) 
    3. failed → Downgrade writes fallback_content original text (memory_kind=xxx_lesson, reflection_success=False) 
    4. mem0 Not available → Skip, return False

    Args:
        db: MongoDB Database handle (used to obtain MemoryService)
        user_id: User ID
        agent_id: Agent ID (for mem0 metadata)
        scope: MemoryScope enumeration value
        memory_kind: Lesson type (trade_lesson/analysis_lesson/debate_lesson)
        system_prompt: Reflection system prompt
        user_prompt: Reflection user prompt
        fallback_content: Original text written when downgrading
        fallback_metadata: Metadata when downgrading (this metadata will also be used as a basis when reflecting on success)
        llm_client: Optional UnifiedLLMClient instance, if not passed, it will be created with the default provider

    Returns:
        True Indicates that the reflection was successfully written into the structured lesson; False means that it was downgraded to the original text or failed completely.
    """
    svc = get_memory_service(db)
    if not svc.available:
        logger.info("[Reflection] mem0 Not available, skip reflection node (agent=%s scope=%s) ", agent_id, scope)
        return False

    # 1. Adjust LLM extraction
    lessons_json: Optional[str] = None
    try:
        if llm_client is None:
            # Parse LLM from system configuration, no longer hard-coded provider
            llm_client = _resolve_reflection_llm_client(db)

        if llm_client is None:
            # System configuration is not available → Directly write the downgraded original text (without adjusting LLM extraction)
            # No longer use hard-coded providers such as deepseek. If the provider is not configured in the system,
            # The cover-up client also fails to work and instead masks configuration issues.
            logger.warning(
                "[Reflection] The system configuration is not parsed into available LLM, reflection and refining are skipped, and the original text is downgraded (agent=%s scope=%s) ",
                agent_id, scope,
            )
        else:
            from core.llm.models import Message, MessageRole
            messages = [
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(role=MessageRole.USER, content=user_prompt),
            ]
            resp = await asyncio.wait_for(
                llm_client.achat(messages),
                timeout=_REFLECTION_LLM_TIMEOUT,
            )
            raw_content = resp.content or "" if hasattr(resp, "content") else str(resp)
            lessons_json = _extract_json(raw_content)
            if not lessons_json:
                logger.warning(
                    "[Reflection] LLM Valid JSON not returned (agent=%s) , Downgrade to original writing. First 200 words of raw output: %s",
                    agent_id,
                    raw_content[:200],
                )
    except asyncio.TimeoutError:
        logger.warning("[Reflection] LLM Call timeout (%ds,agent=%s) , Downgrade to original writing", _REFLECTION_LLM_TIMEOUT, agent_id)
    except Exception as e:
        logger.warning("[Reflection] LLM The call failed (agent=%s) : %s, Downgrade to original writing", agent_id, e)

    # 2. write mem0
    metadata = dict(fallback_metadata)
    metadata["memory_kind"] = memory_kind
    metadata["source"] = "reflection"

    try:
        if lessons_json:
            # Reflecting on Success: Writing Structured Lessons
            content = lessons_json
            metadata["reflection_success"] = True
        else:
            # Downgrade: write original text
            content = fallback_content
            metadata["reflection_success"] = False

        result = await svc.store(
            [{"role": "assistant", "content": content}],
            user_id=user_id,
            agent_id=agent_id,
            scope=scope,
            metadata=metadata,
            infer=False,  # It has been extracted with LLM and no longer triggers secondary extraction of mem0.
        )
        if result.success:
            if lessons_json:
                logger.info(
                    "[Reflection] Reflection successfully written (agent=%s scope=%s kind=%s) ",
                    agent_id, scope, memory_kind,
                )
            else:
                logger.info(
                    "[Reflection] Downgraded to write original text (agent=%s scope=%s kind=%s) ",
                    agent_id, scope, memory_kind,
                )
            return bool(lessons_json)
        else:
            logger.warning("[Reflection] mem0 Write failed: %s", result.error)
            return False
    except Exception as e:
        logger.warning("[Reflection] Exception writing to mem0 (agent=%s) : %s", agent_id, e)
        return False


def _extract_json(text: str) -> Optional[str]:
    """Extract JSON object strings from LLM output.

    Try both ways:
    1. Prioritize extraction ```json ... ``` code block
    2. Go back to the first one { ... } Yes

    Args:
        text: LLM Output text

    Returns:
        A valid JSON string, or None if it cannot be extracted
    """
    if not text or not text.strip():
        return None

    # Method 1: Extraction ```json ... ``` code block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    candidate = m.group(1).strip() if m else text.strip()

    # Method 2: Find the first one { ... } Yes
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    json_str = candidate[start:end + 1]

    # Verify it is legal JSON
    try:
        json.loads(json_str)
        return json_str
    except json.JSONDecodeError:
        return None


# ================================================================
#  Reflection and Lesson Recall (Closed Loop L2/L3)
#
# Writing to the loop is done in run_reflection (writing to mem0).
# The recall closed loop is implemented here: recall the structured lesson of memory_kind containing _lesson from mem0,
# Inject it into the prompt of the researcher/review/debate node, so that historical experience can truly affect the output.
# ================================================================


def recall_lessons_sync(
    *,
    db: Any,
    user_id: str,
    query: str,
    agent_id: str = "",
    limit: int = 3,
    max_chars: int = 1500,
) -> str:
    """Recall reflection lessons from mem0 (sync wrapper for LangGraph nodes to call).

    Priority is given to returning memory_kind structured lessons containing _lesson.
    Returns an empty string on failure and does not block the main process.

    Args:
        db: MongoDB Database handle
        user_id: User ID
        query: Query text (usually a stock symbol + key information)
        agent_id: limited Agent
        limit: Maximum number of items returned
        max_chars: Maximum number of characters returned

    Returns:
        Formatted lesson text, or empty string
    """
    try:
        try:
            asyncio.get_running_loop()
            running_loop = True
        except RuntimeError:
            running_loop = False

        if not running_loop:
            return asyncio.run(_recall_lessons_async(
                db=db, user_id=user_id, query=query,
                agent_id=agent_id, limit=limit, max_chars=max_chars,
            ))

        # There is a running event loop, running in a new thread
        result_holder: Dict[str, Any] = {"text": ""}

        def _run_in_thread() -> None:
            try:
                result_holder["text"] = asyncio.run(_recall_lessons_async(
                    db=db, user_id=user_id, query=query,
                    agent_id=agent_id, limit=limit, max_chars=max_chars,
                ))
            except Exception as exc:
                logger.warning("[Recall] sync Wrapper thread exception: %s", exc)

        t = threading.Thread(target=_run_in_thread, daemon=True)
        t.start()
        t.join(timeout=15)
        return result_holder.get("text", "")
    except Exception as exc:
        logger.warning("[Recall] recall_lessons_sync Abnormal: %s", exc)
        return ""


async def _recall_lessons_async(
    *,
    db: Any,
    user_id: str,
    query: str,
    agent_id: str = "",
    limit: int = 3,
    max_chars: int = 1500,
) -> str:
    """Recall reflection lessons from mem0 (async implementation)."""
    try:
        svc = get_memory_service(db)
        if not svc.available:
            return ""

        # Query all possible lessons scope
        items = await svc.recall(
            query=query,
            user_id=user_id,
            agent_id=agent_id,
            scopes=[
                MemoryScope.ANALYSIS_INSIGHT.value,
                MemoryScope.TRADE_PATTERN.value,
                MemoryScope.AGENT_EXPERIENCE.value,
            ],
            limit=max(limit * 3, 9),  # Expanding the candidate set, client filtering lessons
        )
        if not items:
            return ""

        # Client filtering: only keep memory_kind containing _lesson lessons
        lessons = []
        for item in items:
            meta = getattr(item, "metadata", None) or {}
            kind = meta.get("memory_kind", "")
            if "_lesson" in kind:
                lessons.append(item)

        if not lessons:
            return ""

        # Limit the number of entries and characters
        lines = []
        total = 0
        for item in lessons[:limit]:
            content = getattr(item, "content", "") or ""
            kind = (getattr(item, "metadata", None) or {}).get("memory_kind", "")
            scope = getattr(item, "scope", "") or ""
            # Mark lesson type
            kind_label = {
                "analysis_lesson": "Analyze lessons",
                "trade_lesson": "Trading Lessons",
                "debate_lesson": "Debate Lessons",
            }.get(kind, "Historical lessons")
            line = f"[{kind_label}] {content}"
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line)

        if not lines:
            return ""

        return " [Historical lessons] (from reflection nodes, priority reference)\n" + "\n".join(lines) + "\n"
    except Exception as exc:
        logger.warning("[Recall] _recall_lessons_async Abnormal: %s", exc)
        return ""

from tradingagents.graph.reflection import compute_counterfactual_attribution
