from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import ClassVar
from typing import Any

from core.tools.context import set_current_assistant_thread_context, set_current_assistant_thread_id, set_current_user_id


logger = logging.getLogger(__name__)

EMBEDDED_NANOBOT_THREAD_COLLECTION = "embedded_nanobot_threads"
EMBEDDED_NANOBOT_MESSAGE_COLLECTION = "embedded_nanobot_thread_messages"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _build_thread_title(value: str | None, limit: int = 28) -> str:
    text = _normalize_text(value)
    if not text:
        return "助手会话"
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _normalize_thread_context(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(value or {})
    normalized_symbol = str(raw.get("symbol") or raw.get("stock_symbol") or "").strip() or None
    normalized_object_type = str(raw.get("object_type") or "").strip() or None
    normalized_object_key = str(raw.get("object_key") or "").strip() or None
    if not normalized_object_key and normalized_symbol:
        normalized_object_key = normalized_symbol
    if not normalized_object_type and normalized_object_key == normalized_symbol and normalized_symbol:
        normalized_object_type = "stock"
    normalized = {
        "spec_id": str(raw.get("spec_id") or "").strip() or None,
        "spec_name": str(raw.get("spec_name") or "").strip() or None,
        "workshop_session_id": str(raw.get("workshop_session_id") or "").strip() or None,
        "version_id": str(raw.get("version_id") or "").strip() or None,
        "version_status": str(raw.get("version_status") or "").strip() or None,
        "workflow_id": str(raw.get("workflow_id") or "").strip() or None,
        "node_id": str(raw.get("node_id") or "").strip() or None,
        "preference_id": str(raw.get("preference_id") or "").strip() or None,
        "debug_template_id": str(raw.get("debug_template_id") or "").strip() or None,
        "has_blocking_gaps": bool(raw.get("has_blocking_gaps")) if "has_blocking_gaps" in raw else None,
        "evaluation_status": str(raw.get("evaluation_status") or raw.get("official_acceptance_decision") or "").strip() or None,
        "intent": raw.get("intent") if isinstance(raw.get("intent"), dict) else None,
        "symbol": normalized_symbol,
        "object_type": normalized_object_type,
        "object_key": normalized_object_key,
    }
    result = {key: item for key, item in normalized.items() if item is not None}
    return result


def _is_internal_worker_channel(channel: str | None) -> bool:
    clean = str(channel or "").strip().lower()
    return clean in {"agent_workshop_evaluation", "agent_workshop_worker"}


def _is_internal_worker_thread_id(thread_id: str | None) -> bool:
    clean = str(thread_id or "").strip()
    return (
        clean.startswith("agent-workshop-eval:")
        or clean.startswith("embedded:agent-workshop-eval:")
        or clean.startswith("agent-workshop-worker:")
        or clean.startswith("embedded:agent-workshop-worker:")
    )


def _is_internal_worker_thread(doc: dict[str, Any] | None) -> bool:
    if not doc:
        return False
    return _is_internal_worker_channel(doc.get("channel")) or _is_internal_worker_thread_id(doc.get("thread_id")) or _is_internal_worker_thread_id(doc.get("session_key"))


class EmbeddedNanobotService:
    _simple_chat_cache: ClassVar[dict[tuple[str, str | None], tuple[Any, list, dict]]] = {}

    def __init__(self, db, workspace: str | Path, preferred_model: str | None = None):
        self._db = db
        self._workspace = Path(workspace)
        self._preferred_model = preferred_model

    async def _get_or_create_thread(
        self,
        *,
        user_id: str,
        thread_id: str,
        session_key: str,
        channel: str,
        title_hint: str,
    ) -> dict[str, Any]:
        now = _now_utc()
        thread_doc = {
            "thread_id": thread_id,
            "user_id": user_id,
            "title": _build_thread_title(title_hint),
            "archived": False,
            "message_count": 0,
            "last_user_message": "",
            "current_summary": {
                "abstract": "",
            },
            "session_key": session_key,
            "channel": channel,
            "thread_context": {},
            "created_at": now,
            "updated_at": now,
        }
        await self._db[EMBEDDED_NANOBOT_THREAD_COLLECTION].update_one(
            {"user_id": user_id, "thread_id": thread_id},
            {"$setOnInsert": thread_doc},
            upsert=True,
        )
        return await self._db[EMBEDDED_NANOBOT_THREAD_COLLECTION].find_one({"user_id": user_id, "thread_id": thread_id}) or thread_doc

    async def _append_thread_message(
        self,
        *,
        user_id: str,
        thread_id: str,
        session_key: str,
        role: str,
        content: str,
        channel: str,
        raw_content: str | None = None,
        tools_used: list[str] | None = None,
        stop_reason: str | None = None,
        usage: dict[str, int] | None = None,
        tool_events: list[dict[str, Any]] | None = None,
    ) -> None:
        document = {
            "message_id": f"nanobot_msg_{uuid.uuid4().hex}",
            "thread_id": thread_id,
            "user_id": user_id,
            "session_key": session_key,
            "channel": channel,
            "role": role,
            "content": content,
            "tools_used": tools_used or [],
            "stop_reason": stop_reason,
            "usage": usage or {},
            "tool_events": tool_events or [],
            "created_at": _now_utc(),
        }
        clean_raw_content = str(raw_content or "").strip()
        if clean_raw_content:
            document["raw_content"] = clean_raw_content
        await self._db[EMBEDDED_NANOBOT_MESSAGE_COLLECTION].insert_one(document)

    async def persist_chat_turn(
        self,
        *,
        user_id: str,
        thread_id: str,
        session_key: str,
        channel: str,
        user_content: str,
        user_display_content: str | None = None,
        assistant_content: str,
        tools_used: list[str] | None = None,
        stop_reason: str | None = None,
        usage: dict[str, int] | None = None,
        tool_events: list[dict[str, Any]] | None = None,
        thread_context: dict[str, Any] | None = None,
    ) -> None:
        clean_user_raw_content = str(user_content or "").strip()
        clean_user_content = str(user_display_content or clean_user_raw_content or "").strip()
        clean_assistant_content = str(assistant_content or "").strip()
        clean_thread_id = str(thread_id or session_key or "").strip()
        clean_session_key = str(session_key or clean_thread_id or "").strip()
        clean_channel = str(channel or "embedded").strip() or "embedded"
        clean_thread_context = _normalize_thread_context(thread_context)
        if not user_id or not clean_thread_id:
            return

        inserted_count = 0
        await self._get_or_create_thread(
            user_id=user_id,
            thread_id=clean_thread_id,
            session_key=clean_session_key,
            channel=clean_channel,
            title_hint=clean_user_content,
        )

        if clean_user_content:
            await self._append_thread_message(
                user_id=user_id,
                thread_id=clean_thread_id,
                session_key=clean_session_key,
                role="user",
                content=clean_user_content,
                channel=clean_channel,
                raw_content=clean_user_raw_content if clean_user_raw_content != clean_user_content else None,
            )
            inserted_count += 1

        if clean_assistant_content or tools_used or tool_events or stop_reason:
            await self._append_thread_message(
                user_id=user_id,
                thread_id=clean_thread_id,
                session_key=clean_session_key,
                role="assistant",
                content=clean_assistant_content,
                channel=clean_channel,
                tools_used=tools_used,
                stop_reason=stop_reason,
                usage=usage,
                tool_events=tool_events,
            )
            inserted_count += 1

        updates: dict[str, Any] = {
            "updated_at": _now_utc(),
            "session_key": clean_session_key,
            "channel": clean_channel,
            "archived": False,
        }
        if clean_thread_context:
            updates["thread_context"] = clean_thread_context
            # 🔍 MongoDB Log before writing
            logger.info(
                "[EmbeddedNanobot][MongoWrite] thread_id=%s thread_context_keys=%s intent_stage=%s intent_action=%s",
                clean_thread_id,
                list(clean_thread_context.keys()),
                (clean_thread_context.get("intent") or {}).get("stage", ""),
                (clean_thread_context.get("intent") or {}).get("action", ""),
            )
        if clean_user_content:
            updates["last_user_message"] = clean_user_content[:200]
            updates["title"] = _build_thread_title(clean_user_content)
        if clean_assistant_content:
            updates["current_summary.abstract"] = clean_assistant_content[:120]

        write_result = await self._db[EMBEDDED_NANOBOT_THREAD_COLLECTION].update_one(
            {"user_id": user_id, "thread_id": clean_thread_id},
            {
                "$set": updates,
                "$inc": {"message_count": inserted_count},
            },
        )
        logger.info(
            "[EmbeddedNanobot][MongoResult] thread_id=%s matched=%d modified=%d upserted=%s intent_in_updates=%s",
            clean_thread_id,
            write_result.matched_count,
            write_result.modified_count,
            str(write_result.upserted_id) if write_result.upserted_id else "none",
            "yes" if "thread_context" in updates and (updates.get("thread_context") or {}).get("intent") else "no",
        )

    async def update_thread_context(
        self,
        *,
        user_id: str,
        thread_id: str,
        session_key: str,
        channel: str,
        thread_context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        clean_thread_id = str(thread_id or session_key or "").strip()
        clean_session_key = str(session_key or clean_thread_id or "").strip()
        clean_channel = str(channel or "embedded").strip() or "embedded"
        clean_thread_context = _normalize_thread_context(thread_context)
        if not user_id or not clean_thread_id:
            return None

        existing_thread = await self._get_or_create_thread(
            user_id=user_id,
            thread_id=clean_thread_id,
            session_key=clean_session_key,
            channel=clean_channel,
            title_hint=(clean_thread_context.get("spec_name") or "助手会话"),
        )
        updates: dict[str, Any] = {
            "updated_at": _now_utc(),
            "session_key": clean_session_key,
            "channel": clean_channel,
            "archived": False,
            "thread_context": clean_thread_context,
        }
        if clean_thread_context.get("spec_name") and not existing_thread.get("message_count"):
            updates["title"] = _build_thread_title(clean_thread_context.get("spec_name"))

        await self._db[EMBEDDED_NANOBOT_THREAD_COLLECTION].update_one(
            {"user_id": user_id, "thread_id": clean_thread_id},
            {"$set": updates},
        )
        return await self._db[EMBEDDED_NANOBOT_THREAD_COLLECTION].find_one({"user_id": user_id, "thread_id": clean_thread_id})

    async def list_threads(self, user_id: str, limit: int = 50, archived_only: bool = False) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        query: dict[str, Any] = {"user_id": user_id}
        if archived_only:
            query["archived"] = True
        else:
            query["archived"] = {"$ne": True}
        cursor = self._db[EMBEDDED_NANOBOT_THREAD_COLLECTION].find(query).sort("updated_at", -1).limit(limit * 3)
        async for doc in cursor:
            if _is_internal_worker_thread(doc):
                continue
            updated_at = doc.get("updated_at")
            created_at = doc.get("created_at")
            items.append({
                "thread_id": doc.get("thread_id", ""),
                "title": doc.get("title") or "助手会话",
                "session_key": doc.get("session_key") or doc.get("thread_id") or "",
                "channel": doc.get("channel") or "embedded",
                "archived": bool(doc.get("archived", False)),
                "message_count": int(doc.get("message_count", 0)),
                "last_user_message": doc.get("last_user_message", ""),
                "summary": (doc.get("current_summary") or {}).get("abstract", ""),
                "created_at": created_at.isoformat() if isinstance(created_at, datetime) else created_at,
                "updated_at": updated_at.isoformat() if isinstance(updated_at, datetime) else updated_at,
                "thread_context": _normalize_thread_context(doc.get("thread_context") or {}),
            })
            if len(items) >= limit:
                break
        return items

    async def restore_thread(self, user_id: str, thread_id: str) -> dict[str, Any]:
        clean_thread_id = str(thread_id or "").strip()
        if not clean_thread_id:
            return {"restored": False, "thread_id": clean_thread_id}

        thread = await self._db[EMBEDDED_NANOBOT_THREAD_COLLECTION].find_one({
            "user_id": user_id,
            "thread_id": clean_thread_id,
        })
        if not thread:
            return {"restored": False, "thread_id": clean_thread_id}

        if thread.get("archived") is not True:
            return {"restored": True, "thread_id": clean_thread_id, "archived": False}

        restored_thread = await self._db[EMBEDDED_NANOBOT_THREAD_COLLECTION].update_one({
            "user_id": user_id,
            "thread_id": clean_thread_id,
        }, {
            "$set": {
                "archived": False,
                "updated_at": _now_utc(),
            },
        })
        return {
            "restored": restored_thread.modified_count > 0,
            "thread_id": clean_thread_id,
            "archived": False,
        }

    async def get_thread_messages(self, user_id: str, thread_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        clean_thread_id = str(thread_id or "").strip()
        if not clean_thread_id:
            return None, []

        thread = await self._db[EMBEDDED_NANOBOT_THREAD_COLLECTION].find_one({
            "user_id": user_id,
            "thread_id": clean_thread_id,
        })
        if not thread:
            return None, []
        if _is_internal_worker_thread(thread):
            return None, []

        messages: list[dict[str, Any]] = []
        cursor = self._db[EMBEDDED_NANOBOT_MESSAGE_COLLECTION].find({
            "user_id": user_id,
            "thread_id": clean_thread_id,
        }).sort("created_at", 1)
        async for doc in cursor:
            created_at = doc.get("created_at")
            messages.append({
                "message_id": doc.get("message_id", ""),
                "role": doc.get("role", "assistant"),
                "content": doc.get("content", ""),
                "tools_used": doc.get("tools_used") or [],
                "stop_reason": doc.get("stop_reason"),
                "usage": doc.get("usage") or {},
                "tool_events": doc.get("tool_events") or [],
                "created_at": created_at.isoformat() if isinstance(created_at, datetime) else created_at,
            })

        updated_at = thread.get("updated_at")
        created_at = thread.get("created_at")
        thread_item = {
            "thread_id": thread.get("thread_id", ""),
            "title": thread.get("title") or "助手会话",
            "session_key": thread.get("session_key") or thread.get("thread_id") or "",
            "channel": thread.get("channel") or "embedded",
            "archived": bool(thread.get("archived", False)),
            "message_count": int(thread.get("message_count", 0)),
            "last_user_message": thread.get("last_user_message", ""),
            "summary": (thread.get("current_summary") or {}).get("abstract", ""),
            "created_at": created_at.isoformat() if isinstance(created_at, datetime) else created_at,
            "updated_at": updated_at.isoformat() if isinstance(updated_at, datetime) else updated_at,
            "thread_context": _normalize_thread_context(thread.get("thread_context") or {}),
        }
        return thread_item, messages

    async def delete_thread(self, user_id: str, thread_id: str) -> dict[str, Any]:
        clean_thread_id = str(thread_id or "").strip()
        if not clean_thread_id:
            return {"archived": False, "thread_id": clean_thread_id, "deleted_messages": 0}

        thread = await self._db[EMBEDDED_NANOBOT_THREAD_COLLECTION].find_one({
            "user_id": user_id,
            "thread_id": clean_thread_id,
        })
        if not thread:
            return {"archived": False, "thread_id": clean_thread_id, "deleted_messages": 0}

        if thread.get("archived") is True:
            return {
                "archived": True,
                "thread_id": clean_thread_id,
                "deleted_messages": 0,
            }

        archived_thread = await self._db[EMBEDDED_NANOBOT_THREAD_COLLECTION].update_one({
            "user_id": user_id,
            "thread_id": clean_thread_id,
        }, {
            "$set": {
                "archived": True,
                "updated_at": _now_utc(),
            },
        })
        return {
            "archived": archived_thread.modified_count > 0,
            "thread_id": clean_thread_id,
            "deleted_messages": 0,
        }

    def _cache_key(self) -> tuple[str, str | None]:
        return (str(self._workspace.resolve()), self._preferred_model)

    # ──────────────────────────────────────────────────────────────
    # Simple conversation mode (api channel): Use UnifiedLLMClient directly without leaving Nanobot Runtime
    # ──────────────────────────────────────────────────────────────

    async def _get_simple_chat_client(self) -> tuple[Any, list, dict]:
        """Get LLM clients and tools for simple conversations (with caching).

        Return (UnifiedLLMClient, openai_tool_schemas, tool_functions). 
        """
        cache_key = self._cache_key()
        cached = self._simple_chat_cache.get(cache_key)
        if cached is not None:
            return cached

        from app.services.intelligent_assistant_service import _get_assistant_llm_config
        from core.tools import get_tool_registry, tool_metadata_list_to_openai
        from core.llm import UnifiedLLMClient

        config = await _get_assistant_llm_config(
            self._db,
            use_reasoning_model=True,
            preferred_models={"model": self._preferred_model} if self._preferred_model else None,
        )
        if not config:
            raise ValueError("No LLM configuration available in database")

        client = UnifiedLLMClient.from_config(config)
        registry = get_tool_registry()
        all_metadata = registry.list_all()
        openai_tools = tool_metadata_list_to_openai(all_metadata)

        tool_functions: dict[str, Any] = {}
        for tool in all_metadata:
            if tool.fc_enabled:
                func = registry.get_function(tool.id)
                if func:
                    tool_functions[tool.id] = func

        client.inject_tools(tool_functions)
        logger.info(
            "[EmbeddedNanobot][SimpleChat] %d tools loaded (model=%s)",
            len(openai_tools), config.model,
        )

        cached = (client, openai_tools, tool_functions)
        self._simple_chat_cache[cache_key] = cached
        return cached

    async def _run_simple_chat(
        self,
        user_message: str,
        on_progress: Any = None,
        on_stream: Any = None,
        on_tool_event: Any = None,
        on_step_event: Any = None,
        session_key: str = "",
        chat_id: str = "",
        channel: str = "api",
    ) -> dict[str, Any]:
        """Simple conversation mode:UnifiedLLMClient.achat(auto_execute_tools=True). 

        Used for api channel (debug page), without going through Nanobot Runtime.
        """
        from core.llm.models import Message, MessageRole

        try:
            client, openai_tools, _ = await self._get_simple_chat_client()
        except Exception as e:
            logger.error("[EmbeddedNanobot][SimpleChat] Failed to get client: %s", e, exc_info=True)
            return {
                "content": f"Sorry, the assistant is temporarily unavailable:{e}",
                "tools_used": [],
                "messages": [],
                "stop_reason": "error",
            }

        messages = [
            Message(
                role=MessageRole.SYSTEM,
                content=(
                    "You are the intelligent assistant of the TradingAgentsCN platform. You can use tools to get real-time data."
                    "Please answer user questions based on real data returned by the tool and do not make up data."
                ),
            ),
            Message(role=MessageRole.USER, content=user_message),
        ]

        tools_used: list[str] = []

        async def _progress(payload: dict) -> None:
            event = payload.get("event", "")
            tool_name = payload.get("tool", "")
            if event == "tool_started" and tool_name:
                if on_tool_event:
                    await on_tool_event({
                        "name": tool_name,
                        "status": "running",
                        "label": f"Execution:{tool_name}",
                    })
                if on_step_event:
                    await on_step_event({
                        "step": f"tool_{tool_name}",
                        "status": "running",
                        "title": f"Execution tools:{tool_name}",
                        "session_key": session_key,
                        "chat_id": chat_id,
                        "channel": channel,
                    })
            elif event == "tool_completed" and tool_name:
                is_error = payload.get("is_error", False)
                if tool_name not in tools_used:
                    tools_used.append(tool_name)
                if on_tool_event:
                    await on_tool_event({
                        "name": tool_name,
                        "status": "error" if is_error else "completed",
                        "label": f"{'failed' if is_error else 'Complete'}: {tool_name}",
                    })
                if on_step_event:
                    await on_step_event({
                        "step": f"tool_{tool_name}",
                        "status": "completed",
                        "title": f"Tool completion:{tool_name}",
                        "session_key": session_key,
                        "chat_id": chat_id,
                        "channel": channel,
                    })

        if on_progress:
            await on_progress("正在分析需求...")

        try:
            response = await client.achat(
                messages,
                tools=openai_tools,
                auto_execute_tools=True,
                max_tool_rounds=8,
                tools_used=tools_used,
                dry_run=False,
                progress_callback=_progress,
            )
            content = getattr(response, "content", "") or ""
        except Exception as e:
            logger.error("[EmbeddedNanobot][SimpleChat] call failed: %s", e, exc_info=True)
            content = f"Sorry, there was a problem during processing:{e}"

        if on_stream and content:
            chunk_size = 40
            for i in range(0, len(content), chunk_size):
                await on_stream(content[i:i + chunk_size])
                await asyncio.sleep(0.012)

        return {
            "content": content,
            "tools_used": tools_used,
            "messages": [],
            "stop_reason": "completed",
            "tool_events": [
                {"name": name, "status": "ok"} for name in tools_used
            ],
        }

    async def _chat_via_simple_chat(
        self,
        *,
        user_message: str,
        display_message: str | None,
        session_key: str,
        user_id: str | None,
        current_thread_id: str | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """api channel Entrance: Take UnifiedLLMClient, do not go through Nanobot Runtime.

        Responsible for: Extracting SSE callbacks → settings contextvar → call _run_simple_chat → persistence → Return.
        """
        runtime_kwargs = dict(kwargs)
        thread_context = runtime_kwargs.pop("thread_context", None) or {}
        on_progress = runtime_kwargs.get("on_progress")
        on_stream = runtime_kwargs.get("on_stream")
        on_tool_event = runtime_kwargs.get("on_tool_event")
        on_step_event = runtime_kwargs.get("on_step_event")
        chat_id = runtime_kwargs.get("chat_id") or current_thread_id or session_key
        channel = "api"

        logger.info(
            "[EmbeddedNanobot][SimpleChat] enter thread_id=%s session_key=%s spec_id=%s",
            chat_id, session_key, thread_context.get("spec_id"),
        )

        user_token = set_current_user_id(user_id) if user_id else None
        thread_token = set_current_assistant_thread_id(current_thread_id) if current_thread_id else None
        thread_context_token = set_current_assistant_thread_context(thread_context)
        try:
            result = await self._run_simple_chat(
                user_message=user_message,
                on_progress=on_progress,
                on_stream=on_stream,
                on_tool_event=on_tool_event,
                on_step_event=on_step_event,
                session_key=session_key,
                chat_id=chat_id,
                channel=channel,
            )

            if user_id:
                try:
                    await self.persist_chat_turn(
                        user_id=user_id,
                        thread_id=chat_id,
                        session_key=session_key,
                        channel=channel,
                        user_content=user_message,
                        user_display_content=display_message,
                        assistant_content=str(result.get("content") or ""),
                        tools_used=result.get("tools_used") or [],
                        stop_reason=result.get("stop_reason"),
                        usage=result.get("usage") or {},
                        tool_events=result.get("tool_events") or [],
                        thread_context=thread_context,
                    )
                except Exception:
                    logger.exception("[EmbeddedNanobot][SimpleChat] Failed to write database session history")

            result["thread_context"] = thread_context
            logger.info(
                "[EmbeddedNanobot][SimpleChat] done thread_id=%s tools_used=%s stop_reason=%s",
                chat_id,
                result.get("tools_used") or [],
                result.get("stop_reason"),
            )
            return result
        finally:
            thread_context_token.var.reset(thread_context_token)
            if thread_token is not None:
                thread_token.var.reset(thread_token)
            if user_token is not None:
                user_token.var.reset(user_token)

    async def _chat_via_graph(
        self,
        *,
        user_message: str,
        display_message: str | None,
        session_key: str,
        user_id: str | None,
        current_thread_id: str | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """agent_workshop channel Entrance: Follow the LangGraph workflow + UnifiedLLMClient, Not going through Nanobot Runtime.

        Migrated from core.embedded_nanobot.runtime._run_agent_builder_graph.
        Responsible for: Extracting SSE callbacks → settings contextvar → execute Graph → persistence → Return.
        """
        from core.embedded_nanobot.workflows import (
            AgentBuilderGraphStore,
            new_agent_builder_state,
            build_agent_builder_graph,
            execute_graph,
        )
        from core.embedded_nanobot.workflows.tool_registry_adapter import StandardToolRegistryAdapter

        runtime_kwargs = dict(kwargs)
        thread_context = runtime_kwargs.pop("thread_context", None) or {}
        on_progress = runtime_kwargs.get("on_progress")
        on_stream = runtime_kwargs.get("on_stream")
        on_tool_event = runtime_kwargs.get("on_tool_event")
        on_step_event = runtime_kwargs.get("on_step_event")
        chat_id = runtime_kwargs.get("chat_id") or current_thread_id or session_key
        channel = "agent_workshop"

        # build thread_id
        effective_thread_id = current_thread_id or chat_id or f"agent-studio-{int(datetime.now().timestamp() * 1000)}"

        logger.info(
            "[AgentBuilderGraph][Entry] thread=%s user=%s msg_len=%d",
            effective_thread_id, user_id, len(user_message),
        )

        # ── SSE Event placement ──
        try:
            from app.routers.embedded_nanobot import _append_nanobot_event_log
        except ImportError:
            _append_nanobot_event_log = None

        def _log_event(event: str, payload: dict):
            if _append_nanobot_event_log:
                try:
                    _append_nanobot_event_log(
                        chat_id=chat_id or effective_thread_id,
                        session_key=session_key,
                        event=event,
                        payload=payload,
                    )
                except Exception:
                    pass

        _log_event("started", {"message": "助手已开始处理请求", "session_key": session_key})

        async def event_callback(event_type: str, label: str, payload: Any = None):
            """Events within a node → SSE flow + Place the plate."""
            if event_type == "step" and on_step_event:
                step_data = {
                    "step": label,
                    "status": "completed",
                    "title": label,
                    "detail": str(payload or ""),
                    "session_key": session_key,
                    "chat_id": chat_id or effective_thread_id,
                    "channel": channel,
                }
                _log_event("step_event", step_data)
                await on_step_event(step_data)
            elif event_type == "progress" and on_progress:
                _log_event("progress", {"label": label})
                await on_progress(label)
            elif event_type == "tool" and on_tool_event:
                tool_data = {
                    "name": payload if isinstance(payload, str) else label,
                    "status": "running",
                    "label": label,
                }
                _log_event("tool_event", tool_data)
                await on_tool_event(tool_data)
            elif event_type == "tool_done" and on_tool_event:
                tool_data = {
                    "name": payload if isinstance(payload, str) else label,
                    "status": "completed",
                    "label": label,
                }
                _log_event("tool_event", tool_data)
                await on_tool_event(tool_data)
            elif event_type == "tool_error" and on_tool_event:
                tool_data = {
                    "name": payload if isinstance(payload, str) else label,
                    "status": "error",
                    "label": label,
                }
                _log_event("tool_event", tool_data)
                await on_tool_event(tool_data)

        # Set contextvar (consistent with _chat_via_simple_chat)
        user_token = set_current_user_id(user_id) if user_id else None
        thread_token = set_current_assistant_thread_id(current_thread_id) if current_thread_id else None
        thread_context_token = set_current_assistant_thread_context(thread_context)
        try:
            store = AgentBuilderGraphStore(self._db)

            # Try to restore existing state
            state = await store.load_checkpoint(effective_thread_id)
            if state:
                state["user_message"] = user_message
                state["user_id"] = user_id or ""
                state["thread_id"] = effective_thread_id
                state["channel"] = channel
                state["chat_id"] = chat_id
                logger.info(
                    "[AgentBuilderGraph][Resume] node=%s stage=%s",
                    state.get("current_node", "?"),
                    state.get("stage", "?"),
                )
            else:
                # new session
                state = new_agent_builder_state(
                    thread_id=effective_thread_id,
                    user_id=user_id or "",
                    user_message=user_message,
                    channel=channel,
                    chat_id=chat_id,
                )

            # Build diagram
            graph = build_agent_builder_graph()

            # Create tool registry adapter (replaces Nanobot ToolRegistry)
            tool_registry = StandardToolRegistryAdapter()

            # Get UnifiedLLMClient (replaces self.provider.client)
            client, _, _ = await self._get_simple_chat_client()
            llm_client = client

            # Execution diagram
            try:
                result = await execute_graph(
                    graph=graph,
                    state=state,
                    tool_registry=tool_registry,
                    llm_client=llm_client,
                    event_callback=event_callback,
                    on_stream=on_stream,
                    max_steps=10,
                )
            except Exception as e:
                logger.error("[AgentBuilderGraph][Error] %s", e, exc_info=True)
                return {
                    "content": f"Sorry, there was a problem during processing:{e}",
                    "tools_used": [],
                    "messages": [],
                    "stop_reason": "error",
                }

            # Determine whether a pause is needed
            if result.get("awaiting_user"):
                await store.save_checkpoint(
                    effective_thread_id,
                    result,
                    result.get("current_node", "wait"),
                )
                logger.info(
                    "[AgentBuilderGraph][Checkpoint] saved node=%s stage=%s",
                    result.get("current_node"), result.get("stage"),
                )

            # Clean up runtime injected fields
            final_response = result.get("final_response", "")
            tool_events = result.get("tool_events", [])
            base_thread_context = dict(thread_context) if isinstance(thread_context, dict) else {}
            result_gap_report = result.get("gap_report") if isinstance(result.get("gap_report"), dict) else {}
            result_test_result = result.get("test_result") if isinstance(result.get("test_result"), dict) else {}
            result_thread_context = {
                **base_thread_context,
                "spec_id": str(result.get("spec_id") or base_thread_context.get("spec_id") or "").strip() or None,
                "spec_name": str(result.get("spec_name") or base_thread_context.get("spec_name") or "").strip() or None,
                "workshop_session_id": str(result.get("workshop_session_id") or base_thread_context.get("workshop_session_id") or "").strip() or None,
                "version_id": str(result.get("version_id") or base_thread_context.get("version_id") or "").strip() or None,
                "workflow_id": str(result.get("workflow_id") or base_thread_context.get("workflow_id") or "").strip() or None,
                "node_id": str(result.get("current_node") or base_thread_context.get("node_id") or "").strip() or None,
                "has_blocking_gaps": bool(result_gap_report.get("blocking_gaps")) if result_gap_report else base_thread_context.get("has_blocking_gaps"),
                "evaluation_status": str(result_test_result.get("status") or result.get("official_acceptance_decision") or base_thread_context.get("evaluation_status") or "").strip() or None,
                "intent": {
                    "action": str(result.get("user_intent") or "").strip(),
                    "confidence": result.get("intent_confidence"),
                    "stage": str(result.get("stage") or "").strip(),
                    "reason": str(result.get("intent_reason") or "").strip(),
                } if result.get("user_intent") else base_thread_context.get("intent"),
            }
            result_thread_context = _normalize_thread_context(result_thread_context)

            _log_event("done", {
                "content": final_response[:500],
                "tools_used": [e.get("name", "") for e in tool_events],
                "stop_reason": "completed",
            })

            result_dict = {
                "content": final_response or "处理完成",
                "tools_used": [e.get("name", "") for e in tool_events],
                "messages": [],
                "stop_reason": "completed",
                "tool_events": tool_events,
            }

            # Persistent session history
            if user_id:
                try:
                    await self.persist_chat_turn(
                        user_id=user_id,
                        thread_id=effective_thread_id,
                        session_key=session_key,
                        channel=channel,
                        user_content=user_message,
                        user_display_content=display_message,
                        assistant_content=str(result_dict.get("content") or ""),
                        tools_used=result_dict.get("tools_used") or [],
                        stop_reason=result_dict.get("stop_reason"),
                        usage=result_dict.get("usage") or {},
                        tool_events=result_dict.get("tool_events") or [],
                        thread_context=result_thread_context,
                    )
                except Exception:
                    logger.exception("[EmbeddedNanobot][Graph] Failed to write database session history")

            result_dict["thread_context"] = thread_context
            logger.info(
                "[EmbeddedNanobot][Graph] done thread_id=%s tools_used=%s stop_reason=%s",
                effective_thread_id,
                result_dict.get("tools_used") or [],
                result_dict.get("stop_reason"),
            )
            return result_dict
        finally:
            thread_context_token.var.reset(thread_context_token)
            if thread_token is not None:
                thread_token.var.reset(thread_token)
            if user_token is not None:
                user_token.var.reset(user_token)

    async def chat(
        self,
        user_message: str,
        display_message: str | None = None,
        session_key: str = "embedded:default",
        user_id: str | None = None,
        current_thread_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        channel = str(kwargs.get("channel") or "").strip()

        # ── api / agent_workshop_evaluation channel: Go directly to UnifiedLLMClient without passing Nanobot Runtime ──
        if channel in {"api", "agent_workshop_evaluation"}:
            return await self._chat_via_simple_chat(
                user_message=user_message,
                display_message=display_message,
                session_key=session_key,
                user_id=user_id,
                current_thread_id=current_thread_id,
                **kwargs,
            )

        # ── agent_workshop channel: Follow the LangGraph workflow + UnifiedLLMClient, not pass Nanobot Runtime ──
        if channel == "agent_workshop":
            return await self._chat_via_graph(
                user_message=user_message,
                display_message=display_message,
                session_key=session_key,
                user_id=user_id,
                current_thread_id=current_thread_id,
                **kwargs,
            )

        # ── Nanobot Runtime Removed: embedded channel (default, no frontend caller) is no longer supported ──
        logger.warning(
            "[EmbeddedNanobot][Deprecated] runtime The path is obsolete,channel=%s No longer supported."
            "Please use the agent_workshop/api/agent_workshop_evaluation channel.",
            channel or "embedded",
        )
        return {
            "content": "This channel is deprecated and the Agent Workshop Runtime has been removed. Please use the agent_workshop/api/agent_workshop_evaluation channel.",
            "tools_used": [],
            "messages": [],
            "stop_reason": "deprecated_channel",
        }


def _extract_pending_from_response(assistant_content: str, user_message: str) -> dict:
    """Extract the questions and options to be confirmed from the LLM response as the basis for intent.pending."""
    if not assistant_content:
        return {}

    result = {}
    # Find a question (starting with ? or ? The ending line may include "What do you think", "What do you think", etc.)
    lines = assistant_content.strip().split("\n")
    question_lines = []
    for line in lines[-10:]:  # Only look at the last 10 lines
        stripped = line.strip()
        if stripped.endswith("?") or stripped.endswith("？"):
            question_lines.append(stripped)
        elif any(kw in stripped for kw in ["你觉得呢", "你怎么看", "你更倾向", "你希望", "请确认", "请回复"]):
            question_lines.append(stripped)

    if question_lines:
        result["pending_question"] = question_lines[-1]  # Take the last question

    # Find options (A/B/C or option A/option B mode)
    option_lines = []
    for line in lines:
        stripped = line.strip()
        if re.match(r'^[（(]?[A-C][）)]?\s*[：:]', stripped) or re.match(r'^选项\s*[A-C]', stripped):
            option_lines.append(stripped)

    if option_lines and len(option_lines) >= 2:
        result["pending_options"] = [
            {"index": i + 1, "id": f"option_{chr(65 + i)}", "name": line[:80]}
            for i, line in enumerate(option_lines[:5])
        ]

    return result


    