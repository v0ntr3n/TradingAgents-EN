from __future__ import annotations
import sys as _sys
import types as _types
import app.routers as _routers_pkg
_self_mod = _sys.modules[__name__]
_snapshots = {}

# === intelligent_assistant.py ===
"""
Smart Assistant API Routing
"""

import asyncio
import contextlib
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.routers.auth_db import get_current_user
from app.core.database import get_mongo_db
from app.schemas.intelligent_assistant import (
    AssistantThreadAttachReportRequest,
    AssistantThreadAttachReportResponse,
    AssistantThreadItem,
    AssistantThreadListResponse,
    AssistantThreadMessagesResponse,
    AssistantThreadReportSearchResponse,
    ChatRequest,
    ChatResponse,
    ConversationResponse,
    CreateAssistantThreadRequest,
    PlannedAnalysisResponse,
    ThreadDeleteResponse,
    ThreadSummarizeResponse,
    AssistantThreadReportDetailResponse,
)
from app.services.intelligent_assistant_service import (
    chat_with_assistant,
    stream_chat_with_assistant,
    create_assistant_thread,
    delete_assistant_thread,
    get_assistant_conversation,
    get_assistant_thread_messages,
    get_or_create_assistant_thread,
    list_assistant_threads,
    clear_assistant_conversation,
    attach_existing_report_to_thread,
    save_assistant_message,
    search_assistant_attachable_reports,
    serialize_assistant_report_ref,
    summarize_assistant_thread,
    get_assistant_thread_report_detail,
)
from app.services.planned_analysis_service import PlannedAnalysisService
from app.services.planned_analysis_service import stream_planned_analysis_with_assistant
try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = AsyncIOMotorDatabase = AsyncIOMotorCollection = object

router = APIRouter(prefix="/api/assistant", tags=["assistant"])
logger = logging.getLogger(__name__)


# SSE Heartbeat interval: must be less than the 90s idle timeout of the front-end fetchSSE
_SSE_HEARTBEAT_INTERVAL = 15


async def sse_stream_with_heartbeat(agen, heartbeat_interval: int = _SSE_HEARTBEAT_INTERVAL):
    """Wrap asynchronous generators into SSE event streams with heartbeats.

    ⚠️ Key constraint: heartbeat timeout**The underlying generator must never be canceled**. 

    old implementation `await asyncio.wait_for(gen.__anext__(), timeout=15)` When canceling on timeout
    A CanceledError will be injected into the generator s suspension point, causing the first silence to exceed 15 seconds.
    Entire stream killed (minimum reproducible demonstration: second time after timeout ``__anext__()`` Throw directly
    StopAsyncIteration) . Long tool execution in the intelligent assistant (valuation Excel: data assembly +
    LLM specifications are generated up to 3 times, and the legal time is 30-180s). It hits exactly, and the flow is silently cut off.
    Or the front end waits for 90 seconds and then reports the idle timeout."The server did not respond for a long time". 

    Correct mode: independent pump task pushes the generator output into the queue,``wait_for`` Only works on
    ``queue.get()``——Only discard queue waiting once after timeout, pump task and underlying generator
    It is not affected at all and continues to produce normally.

    Exceptions thrown inside the generator are converted to error events here (consistent with the old implementation behavior).
    """
    import json as _json

    queue: "asyncio.Queue[object]" = asyncio.Queue()
    sentinel = object()

    async def _pump() -> None:
        try:
            async for chunk in agen:
                await queue.put(chunk)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - Convert error event to the front end
            logger.exception("[Smart Assistant API·streaming] Underlying generator exception")
            await queue.put(
                "event: error\n"
                f"data: {_json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"
            )
        finally:
            await queue.put(sentinel)

    pump_task = asyncio.create_task(_pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
            except asyncio.TimeoutError:
                # The queue is empty (long silent period for tool execution): only heartbeat is sent, and pump continues to run.
                yield ": keepalive\n\n"
                continue
            if item is sentinel:
                break
            yield item
    finally:
        # Client disconnects or terminates: stops the pump and closes the underlying generator (triggering its internal finally cleanup)
        pump_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump_task
        await agen.aclose()


@router.post("/user-manual-index/rebuild")
async def rebuild_user_manual_index(
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Reinitialize and rebuild the user manual vector index.

    Scenario: The Embedding API Key is not configured/error causes the user manual index building to fail when the system starts.
     (Semantic retrieval using the Q&A Assistant is not available), the user can call this interface manually after configuring the Key.
    Rebuild without restarting the backend.
    """
    from core.knowledge.user_manual_manager import UserManualManager

    manager = UserManualManager(db=db)

    # 1. If the vector backend is unavailable (initialization failed at startup), reinitialize it first
    if not manager.available:
        ok = manager.reinit()
        if not ok:
            raise HTTPException(
                status_code=400,
                detail="Vector retrieval backend failed to reinitialize, please check Embedding API Key configuration (system settings -> LLM/Embedding) , Try again after configuring",
            )

    # 2. Force index rebuild (ignore signature comparison, full rebuild)
    result = await asyncio.to_thread(manager.ensure_indexed, True)

    if result.get("error"):
        raise HTTPException(status_code=400, detail=f"User manual index rebuild failed: {result['error']}")

    return {
        "success": True,
        "rebuilt": result.get("rebuilt", False),
        "sections_count": result.get("sections_count", 0),
        "manuals_count": result.get("manuals_count", 0),
        "signature": result.get("signature", ""),
    }


def _resolve_requested_model(request: ChatRequest) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    unified_model = (request.model or "").strip() or None
    unified_model_config_id = (request.model_config_id or "").strip() or None
    if unified_model:
        return unified_model, unified_model, unified_model_config_id, unified_model_config_id
    if unified_model_config_id:
        return None, None, unified_model_config_id, unified_model_config_id

    quick_model = (request.quick_model or "").strip() or None
    deep_model = (request.deep_model or "").strip() or None
    quick_model_config_id = (request.quick_model_config_id or "").strip() or None
    deep_model_config_id = (request.deep_model_config_id or "").strip() or None
    fallback_model = deep_model or quick_model
    fallback_config_id = deep_model_config_id or quick_model_config_id
    return (
        quick_model or fallback_model,
        deep_model or fallback_model,
        quick_model_config_id or fallback_config_id,
        deep_model_config_id or fallback_config_id,
    )


@router.get("/conversation", response_model=ConversationResponse)
async def get_conversation(
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    conversation_id: Optional[str] = Query(None),
):
    """Get the current user s smart assistant session history"""
    user_id = str(current_user["id"])
    thread = await get_or_create_assistant_thread(db, user_id, conversation_id)
    messages = await get_assistant_conversation(db, user_id, thread["thread_id"])
    return ConversationResponse(messages=messages, conversation_id=thread["thread_id"])


@router.delete("/conversation")
async def clear_conversation(
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    conversation_id: Optional[str] = Query(None),
):
    """Clear the current user s smart assistant session"""
    user_id = str(current_user["id"])
    await clear_assistant_conversation(db, user_id, conversation_id)
    return {"success": True}


@router.get("/threads", response_model=AssistantThreadListResponse)
async def get_threads(
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get the current user s topic session list"""
    user_id = str(current_user["id"])
    items = await list_assistant_threads(db, user_id)
    return AssistantThreadListResponse(
        items=[AssistantThreadItem(**item) for item in items],
        total=len(items),
    )


@router.post("/threads", response_model=AssistantThreadItem)
async def create_thread(
    request: CreateAssistantThreadRequest,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Create topic session"""
    user_id = str(current_user["id"])
    try:
        item = await create_assistant_thread(db, user_id, request.title, request.parent_thread_id)
        return AssistantThreadItem(**item)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/threads/{thread_id}", response_model=ThreadDeleteResponse)
async def delete_thread(
    thread_id: str,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Delete the specified topic and its subtopics"""
    user_id = str(current_user["id"])
    try:
        deleted_ids = await delete_assistant_thread(db, user_id, thread_id)
        return ThreadDeleteResponse(success=True, deleted_thread_ids=deleted_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/threads/{thread_id}/messages", response_model=AssistantThreadMessagesResponse)
async def get_thread_messages(
    thread_id: str,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get the message list of the specified topic"""
    user_id = str(current_user["id"])
    thread, messages = await get_assistant_thread_messages(db, user_id, thread_id)
    return AssistantThreadMessagesResponse(
        messages=messages,
        conversation_id=thread_id,
        thread=AssistantThreadItem(**thread),
    )


@router.get(
    "/threads/{thread_id}/reports/{ref_type}/{report_key}",
    response_model=AssistantThreadReportDetailResponse,
)
async def get_thread_report_detail(
    thread_id: str,
    ref_type: str,
    report_key: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    try:
        detail = await get_assistant_thread_report_detail(
            db,
            str(current_user["id"]),
            thread_id,
            ref_type,
            report_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get associated report details: {exc}") from exc

    return AssistantThreadReportDetailResponse(detail=detail)


@router.get(
    "/threads/{thread_id}/report-candidates",
    response_model=AssistantThreadReportSearchResponse,
)
async def get_thread_report_candidates(
    thread_id: str,
    ref_type: str = Query("stock_report"),
    keyword: Optional[str] = Query(None),
    limit: int = Query(8, ge=1, le=20),
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    try:
        items = await search_assistant_attachable_reports(
            db,
            str(current_user["id"]),
            thread_id,
            ref_type=ref_type,
            keyword=keyword,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Search for relatable reports failed: {exc}") from exc

    return AssistantThreadReportSearchResponse(
        items=[serialize_assistant_report_ref(item) for item in items],
        total=len(items),
    )


@router.post(
    "/threads/{thread_id}/report-links",
    response_model=AssistantThreadAttachReportResponse,
)
async def attach_thread_report(
    thread_id: str,
    request: AssistantThreadAttachReportRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    try:
        attached_ref = await attach_existing_report_to_thread(
            db,
            str(current_user["id"]),
            thread_id,
            request.ref_type,
            request.report_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to associate old reports: {exc}") from exc

    return AssistantThreadAttachReportResponse(
        success=True,
        attached_ref=serialize_assistant_report_ref(attached_ref),
    )


@router.delete("/threads/{thread_id}/messages")
async def clear_thread_messages(
    thread_id: str,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Clear the message list of the specified topic"""
    user_id = str(current_user["id"])
    await clear_assistant_conversation(db, user_id, thread_id)
    return {"success": True}


@router.post("/threads/{thread_id}/summarize", response_model=ThreadSummarizeResponse)
async def summarize_thread(
    thread_id: str,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Manually trigger summary updates for a specified topic"""
    user_id = str(current_user["id"])
    summary = await summarize_assistant_thread(db, user_id, thread_id, summary_type="manual")
    return ThreadSummarizeResponse(conversation_id=thread_id, summary=summary)


@router.post("/chat", response_model=ChatResponse)
async def assistant_chat(
    request: ChatRequest,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """
    Intelligent assistant conversation interface

    Supports natural language questions, and the assistant will independently select tools to obtain data and generate answers.
    The conversation will be persistent and you can view the history next time you enter.
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user_id = str(current_user["id"])
    quick_model, deep_model, quick_model_config_id, deep_model_config_id = _resolve_requested_model(request)

    try:
        result = await chat_with_assistant(
            db=db,
            user_message=request.message.strip(),
            user_id=user_id,
            conversation_id=request.conversation_id,
            model=deep_model or quick_model,
            model_config_id=deep_model_config_id or quick_model_config_id,
            assistant_role=request.assistant_role,
            user_context=request.user_context,
        )
        return ChatResponse(**result)
    except Exception as e:
        logger.exception("[Smart Assistant API] Processing failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def assistant_chat_stream(
    request: ChatRequest,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """
    Intelligent Assistant Streaming Conversation Interface (SSE)

    Return to the Server-Sent Events stream to push tool call progress and reply content in real time.
    Event type:tool_started / tool_completed / token / done / error
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user_id = str(current_user["id"])
    quick_model, deep_model, quick_model_config_id, deep_model_config_id = _resolve_requested_model(request)

    async def event_generator():
        gen = stream_chat_with_assistant(
            db=db,
            user_message=request.message.strip(),
            user_id=user_id,
            conversation_id=request.conversation_id,
            model=deep_model or quick_model,
            model_config_id=deep_model_config_id or quick_model_config_id,
            assistant_role=request.assistant_role,
            user_context=request.user_context,
        )
        async for chunk in sse_stream_with_heartbeat(gen):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/planned-analysis", response_model=PlannedAnalysisResponse)
async def planned_analysis(
    request: ChatRequest,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """
    Planning analysis interface — Plan-then-Execute mode

    Supports three-level guarantee: seed process matching → LLM independent planning → ReAct Fallback.
    Return the complete analysis plan, execution results of each step and comprehensive answers.
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user_id = str(current_user["id"])
    quick_model, deep_model, quick_model_config_id, deep_model_config_id = _resolve_requested_model(request)

    try:
        service = PlannedAnalysisService(
            db,
            preferred_models={
                "model": deep_model or quick_model,
                "model_config_id": deep_model_config_id or quick_model_config_id,
            },
        )
        result = await service.analyze(
            question=request.message.strip(),
            user_id=user_id,
            conversation_id=request.conversation_id,
        )

        # Persistent sessions (share session history with ReAct mode)
        if result.reply:
            try:
                await save_assistant_message(
                    db,
                    user_id=user_id,
                    user_content=request.message.strip(),
                    assistant_content=result.reply,
                    tools_used=result.tools_used or [],
                    conversation_id=request.conversation_id,
                )
            except Exception as e:
                logger.warning("[planning analysis API] Failed to save session: %s", e)

        thread = await get_or_create_assistant_thread(db, user_id, request.conversation_id)

        return PlannedAnalysisResponse(
            reply=result.reply,
            tools_used=result.tools_used,
            data_refs=result.data_refs,
            conversation_id=thread["thread_id"],
            plan=result.plan.dict() if result.plan else None,
            step_results=[sr.dict() for sr in result.step_results] if result.step_results else None,
            source=result.source.value,
            supplemented=result.supplemented,
        )
    except Exception as e:
        logger.exception("[planning analysis API] Processing failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/planned-analysis/stream")
async def planned_analysis_stream(
    request: ChatRequest,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Planning and analysis streaming interface (SSE). """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user_id = str(current_user["id"])
    quick_model, deep_model, quick_model_config_id, deep_model_config_id = _resolve_requested_model(request)

    async def event_generator():
        gen = stream_planned_analysis_with_assistant(
            db=db,
            user_message=request.message.strip(),
            user_id=user_id,
            conversation_id=request.conversation_id,
            model=deep_model or quick_model,
            model_config_id=deep_model_config_id or quick_model_config_id,
        )
        async for chunk in sse_stream_with_heartbeat(gen):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/deliverables/{filename}")
async def download_assistant_deliverable(
    request: Request,
    filename: str,
    exp: Optional[int] = Query(None),
    sig: Optional[str] = Query(None),
    authorization: Optional[str] = Header(default=None),
):
    """Download the deliverable file generated by the intelligent assistant (valuation calculation/table export xlsx).

    Authentication uses dual channels:
    1. Signature link (attached when the tool generates the file ?exp=&sig=, HMAC-SHA256 + time limit)——
       The browser directly clicks the markdown download link (without JWT header);
    2. Fallback when signature is missing/invalid get_current_user(JWT header/Session Cookie),
       API Directly calling the scene behaves the same as before.

    Security constraints: File names only allow letters/digits/underscores/dots/hyphens/Chinese/brackets, and must be
    .xlsx, Limited to the data/deliverables directory to prevent path traversal.
    """
    import re
    from pathlib import Path

    from fastapi.responses import FileResponse

    from core.deliverables.download_links import verify_deliverable_signature

    if not verify_deliverable_signature(filename, exp, sig):
        # No valid signature → Must be logged in (get_current_user throws 401 on failure)
        await get_current_user(request, authorization)

    # Chinese characters and full-angle brackets are allowed (AI generated file names contain Chinese titles), and path separators are prohibited.
    if (
        not re.fullmatch(r"[A-Za-z0-9_.\-\u4e00-\u9fff（）()]+", filename)
        or ".." in filename
        or not filename.lower().endswith(".xlsx")
    ):
        raise HTTPException(status_code=400, detail="Illegal file name")

    base_dir = (Path.cwd() / "data" / "deliverables").resolve()
    file_path = (base_dir / filename).resolve()
    if base_dir not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File does not exist")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ============================================================
# v3.5.0 Item 4: Intelligent Assistant HITL (Key Operation Confirmation)API
# ============================================================


@router.get("/hitl/pending")
async def list_pending_hitl(
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
    conversation_id: Optional[str] = Query(None),
):
    """List the key operations to be confirmed by the current user (for front-end display)."""
    from core.hitl.assistant_hitl import list_pending_for_user

    user_id = str(current_user.id) if hasattr(current_user, "id") else str(current_user.get("_id", ""))
    items = await list_pending_for_user(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    return {"items": items, "count": len(items)}


@router.post("/hitl/{pending_id}/confirm")
async def confirm_hitl(
    pending_id: str,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Confirm execution of key operations to be confirmed."""
    from core.hitl.assistant_hitl import confirm_pending

    user_id = str(current_user.id) if hasattr(current_user, "id") else str(current_user.get("_id", ""))
    result = await confirm_pending(db, pending_id=pending_id, user_id=user_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Confirmation failed"))
    return result


@router.post("/hitl/{pending_id}/reject")
async def reject_hitl(
    pending_id: str,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Deny execution of critical operations pending confirmation."""
    from core.hitl.assistant_hitl import reject_pending

    user_id = str(current_user.id) if hasattr(current_user, "id") else str(current_user.get("_id", ""))
    result = await reject_pending(db, pending_id=pending_id, user_id=user_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "reject failure"))
    return result
_snapshots['intelligent_assistant'] = dict(globals())

# === embedded_nanobot.py ===

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = AsyncIOMotorDatabase = AsyncIOMotorCollection = object
from starlette.responses import StreamingResponse

from app.core.database import get_mongo_db
from app.routers.auth_db import get_current_user
from app.schemas.embedded_nanobot import EmbeddedNanobotChatRequest, EmbeddedNanobotChatResponse, EmbeddedNanobotThreadArchiveResponse, EmbeddedNanobotThreadContextUpdateRequest, EmbeddedNanobotThreadListResponse, EmbeddedNanobotThreadMessagesResponse, EmbeddedNanobotThreadRestoreResponse
from app.services.embedded_nanobot_service import EmbeddedNanobotService

router = APIRouter(prefix="/api/embedded-nanobot", tags=["embedded-nanobot"])
logger = logging.getLogger(__name__)
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
NANOBOT_EVENT_LOG_DIR = WORKSPACE_ROOT / "logs" / "embedded_nanobot_events"


def _append_nanobot_event_log(*, chat_id: str, session_key: str, event: str, payload: dict) -> None:
    """Append front-end streaming events to ndjson to facilitate troubleshooting after refreshing."""
    try:
        NANOBOT_EVENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        safe_chat_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(chat_id or session_key or "default"))[:120]
        log_path = NANOBOT_EVENT_LOG_DIR / f"{safe_chat_id}_{datetime.now().strftime('%Y%m%d')}.ndjson"
        record = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "event": event,
            "chat_id": chat_id,
            "session_key": session_key,
            "payload": payload,
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception as exc:
        logger.debug("[EmbeddedNanobotEventLog] write skipped: %s", exc)


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.get("/threads", response_model=EmbeddedNanobotThreadListResponse)
async def list_embedded_nanobot_threads(
    limit: int = 50,
    archived_only: bool = False,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    user_id = str(current_user["id"])
    service = EmbeddedNanobotService(db=db, workspace=WORKSPACE_ROOT)
    items = await service.list_threads(user_id=user_id, limit=max(1, min(limit, 200)), archived_only=archived_only)
    return EmbeddedNanobotThreadListResponse(items=items, total=len(items))


@router.get("/threads/{thread_id}/messages", response_model=EmbeddedNanobotThreadMessagesResponse)
async def get_embedded_nanobot_thread_messages(
    thread_id: str,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    user_id = str(current_user["id"])
    service = EmbeddedNanobotService(db=db, workspace=WORKSPACE_ROOT)
    thread, messages = await service.get_thread_messages(user_id=user_id, thread_id=thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Session does not exist")
    return EmbeddedNanobotThreadMessagesResponse(thread=thread, messages=messages)


@router.delete("/threads/{thread_id}", response_model=EmbeddedNanobotThreadArchiveResponse)
async def delete_embedded_nanobot_thread(
    thread_id: str,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    user_id = str(current_user["id"])
    service = EmbeddedNanobotService(db=db, workspace=WORKSPACE_ROOT)
    result = await service.delete_thread(user_id=user_id, thread_id=thread_id)
    if not result.get("archived"):
        raise HTTPException(status_code=404, detail="Session does not exist")
    return result


@router.post("/threads/{thread_id}/restore", response_model=EmbeddedNanobotThreadRestoreResponse)
async def restore_embedded_nanobot_thread(
    thread_id: str,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    user_id = str(current_user["id"])
    service = EmbeddedNanobotService(db=db, workspace=WORKSPACE_ROOT)
    result = await service.restore_thread(user_id=user_id, thread_id=thread_id)
    if not result.get("restored"):
        raise HTTPException(status_code=404, detail="Session does not exist")
    return result


@router.put("/threads/{thread_id}/context", response_model=EmbeddedNanobotThreadMessagesResponse)
async def update_embedded_nanobot_thread_context(
    thread_id: str,
    request: EmbeddedNanobotThreadContextUpdateRequest,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    user_id = str(current_user["id"])
    service = EmbeddedNanobotService(db=db, workspace=WORKSPACE_ROOT)
    thread = await service.update_thread_context(
        user_id=user_id,
        thread_id=thread_id,
        session_key=request.session_key or thread_id,
        channel=request.channel,
        thread_context=request.thread_context.model_dump(exclude_none=True),
    )
    if not thread:
        raise HTTPException(status_code=400, detail="Unable to update session context")
    _, messages = await service.get_thread_messages(user_id=user_id, thread_id=thread_id)
    return EmbeddedNanobotThreadMessagesResponse(thread=thread, messages=messages)


@router.get("/status")
async def embedded_nanobot_status(current_user=Depends(get_current_user)):
    return {
        "enabled": True,
        "user_id": str(current_user["id"]),
        "workspace": str(WORKSPACE_ROOT),
    }


@router.post("/chat", response_model=EmbeddedNanobotChatResponse)
async def embedded_nanobot_chat(
    request: EmbeddedNanobotChatRequest,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    message = request.message.strip()
    display_message = str(request.display_message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user_id = str(current_user["id"])
    session_key = request.session_key or f"embedded:user:{user_id}"
    chat_id = request.chat_id or session_key

    try:
        service = EmbeddedNanobotService(db=db, workspace=WORKSPACE_ROOT, preferred_model=request.model)
        result = await service.chat(
            user_message=message,
            display_message=display_message,
            session_key=session_key,
            user_id=user_id,
            current_thread_id=chat_id,
            channel=request.channel,
            chat_id=chat_id,
            media=request.media,
            skill_names=request.skill_names,
            thread_context=request.thread_context.model_dump(exclude_none=True) if request.thread_context else {},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[EmbeddedNanobot API] Conversation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return EmbeddedNanobotChatResponse(
        content=result.get("content", ""),
        session_key=session_key,
        thread_id=chat_id,
        stop_reason=result.get("stop_reason"),
        tools_used=result.get("tools_used", []),
        usage=result.get("usage", {}),
        tool_events=result.get("tool_events", []),
        thread_context=result.get("thread_context"),
    )


@router.post("/chat/stream")
async def embedded_nanobot_chat_stream(
    request: EmbeddedNanobotChatRequest,
    current_user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    message = request.message.strip()
    display_message = str(request.display_message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user_id = str(current_user["id"])
    session_key = request.session_key or f"embedded:user:{user_id}"
    chat_id = request.chat_id or session_key
    service = EmbeddedNanobotService(db=db, workspace=WORKSPACE_ROOT, preferred_model=request.model)

    async def event_stream():
        queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

        async def emit(event: str, payload: dict) -> None:
            payload_with_meta = {**payload, "chat_id": chat_id}
            _append_nanobot_event_log(
                chat_id=chat_id,
                session_key=session_key,
                event=event,
                payload=payload_with_meta,
            )
            await queue.put((event, payload_with_meta))

        await emit("started", {"message": "The assistant has started processing the request", "session_key": session_key})

        async def on_progress(progress_message: str) -> None:
            await emit("progress", {"message": progress_message, "session_key": session_key})

        async def on_stream(delta: str) -> None:
            if delta:
                await emit("token", {"content": delta, "session_key": session_key})

        async def on_tool_event(tool_event: dict) -> None:
            await emit("tool_event", {**tool_event, "session_key": session_key})

        async def on_step_event(step_event: dict) -> None:
            await emit("step_event", {**step_event, "session_key": session_key})

        async def run_chat() -> None:
            try:
                result = await service.chat(
                    user_message=message,
                    display_message=display_message,
                    session_key=session_key,
                    user_id=user_id,
                    current_thread_id=chat_id,
                    channel=request.channel,
                    chat_id=chat_id,
                    media=request.media,
                    skill_names=request.skill_names,
                    thread_context=request.thread_context.model_dump(exclude_none=True) if request.thread_context else {},
                    on_progress=on_progress,
                    on_stream=on_stream,
                    on_tool_event=on_tool_event,
                    on_step_event=on_step_event,
                )
                await emit("done", {
                    "content": result.get("content", ""),
                    "session_key": session_key,
                    "thread_id": chat_id,
                    "stop_reason": result.get("stop_reason"),
                    "tools_used": result.get("tools_used", []),
                    "usage": result.get("usage", {}),
                    "tool_events": result.get("tool_events", []),
                    "thread_context": result.get("thread_context"),
                })
            except Exception as exc:
                logger.exception("[EmbeddedNanobot API] Streaming conversation failed")
                await emit("error", {"message": str(exc), "session_key": session_key})
            finally:
                await queue.put(None)

        task = asyncio.create_task(run_chat())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event, payload = item
                yield _sse_event(event, payload)
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    import contextlib

    return StreamingResponse(event_stream(), media_type="text/event-stream")
_snapshots['embedded_nanobot'] = dict(globals())

# === memory.py ===
"""
mem0 unified memory layer API

Provides memory health check, status query, list browsing, semantic search and deletion management interfaces.
"""

import logging
import re
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from app.routers.auth_db import get_current_user
from app.core.database import get_mongo_db
try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = AsyncIOMotorDatabase = AsyncIOMotorCollection = object

router = APIRouter(prefix="/api/memory", tags=["memory"])
logger = logging.getLogger(__name__)

ALL_SCOPES = [
    "conversation", "user_preference", "analysis_insight",
    "skill_lesson", "agent_experience", "trade_pattern",
]


def _resolve_user_id(user: dict) -> str:
    return str(user.get("user_id") or user.get("id") or "")


def _build_metadata_filters(
    *,
    object_type: Optional[str] = None,
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    memory_kind: Optional[str] = None,
) -> Optional[dict[str, str]]:
    filters: dict[str, str] = {}
    if object_type:
        filters["object_type"] = object_type.strip().lower()
    if symbol:
        filters["symbol"] = symbol.strip().upper()
    if market:
        filters["market"] = market.strip().lower()
    if memory_kind:
        filters["memory_kind"] = memory_kind.strip().lower()
    return filters or None


@router.get("/health")
async def memory_health(db: AsyncIOMotorDatabase = Depends(get_mongo_db)):
    """mem0 Memory layer health check"""
    from core.memory.service import get_memory_service
    svc = get_memory_service(db)
    result = await svc.health_check()
    ok = bool(result.get("ok", False))
    return JSONResponse(
        status_code=200 if ok else 503,
        content={
            "success": ok,
            "data": result,
            "message": "" if ok else (result.get("error") or "Memory layer is not available"),
        },
    )


@router.get("/stats")
async def memory_stats(
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get the memory statistics of the current user (count by scope)"""
    from core.memory.service import get_memory_service, _is_mem0_enabled
    user_id = _resolve_user_id(user)
    logger.info("[memory-api] stats request — resolved_user_id=%s", user_id)

    if not _is_mem0_enabled():
        return {
            "success": True,
            "data": {"enabled": False, "message": "Memory function is not enabled"},
        }

    svc = get_memory_service(db)
    if not svc.available:
        await svc._ensure_init()

    if not svc.available:
        return {
            "success": True,
            "data": {"enabled": True, "available": False, "message": svc._init_error},
        }

    all_result = await svc.get_all(user_id=user_id, limit=200, page=1)
    total = all_result["total"]
    scope_counts: dict[str, int] = {}
    for item in all_result["items"]:
        s = item.scope or "unknown"
        scope_counts[s] = scope_counts.get(s, 0) + 1

    if total > len(all_result["items"]):
        remaining = await svc.get_all(user_id=user_id, limit=total, page=1)
        scope_counts = {}
        for item in remaining["items"]:
            s = item.scope or "unknown"
            scope_counts[s] = scope_counts.get(s, 0) + 1

    return {
        "success": True,
        "data": {
            "enabled": True,
            "available": True,
            "user_id": user_id,
            "total": total,
            "scopes": scope_counts,
        },
    }


@router.get("/list")
async def memory_list(
    scope: Optional[str] = Query(None, description="Filter by scope"),
    object_type: Optional[str] = Query(None, description="Filter by object type"),
    symbol: Optional[str] = Query(None, description="Filter by ticker"),
    market: Optional[str] = Query(None, description="Filter by market"),
    memory_kind: Optional[str] = Query(None, description="Filter by memory type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get the memory list of the current user by pagination"""
    from core.memory.service import get_memory_service
    user_id = _resolve_user_id(user)
    logger.info(
        "[memory-api] list request — resolved_user_id=%s scope=%s page=%d page_size=%d",
        user_id, scope, page, page_size,
    )
    svc = get_memory_service(db)

    scopes = [scope] if scope else None
    metadata_filters = _build_metadata_filters(
        object_type=object_type,
        symbol=symbol,
        market=market,
        memory_kind=memory_kind,
    )
    result = await svc.get_all(
        user_id=user_id,
        scopes=scopes,
        metadata_filters=metadata_filters,
        limit=page_size,
        page=page,
    )
    return {
        "success": True,
        "data": {
            "items": [item.model_dump() for item in result["items"]],
            "total": result["total"],
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/recall")
async def memory_recall(
    query: str = Query(..., min_length=1, description="Query text"),
    scope: Optional[str] = Query(None, description="limited scope"),
    object_type: Optional[str] = Query(None, description="Filter by object type"),
    symbol: Optional[str] = Query(None, description="Filter by ticker"),
    market: Optional[str] = Query(None, description="Filter by market"),
    memory_kind: Optional[str] = Query(None, description="Filter by memory type"),
    limit: int = Query(5, ge=1, le=20),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """semantic search memory"""
    from core.memory.service import get_memory_service
    user_id = _resolve_user_id(user)
    logger.info(
        "[memory-api] recall request — resolved_user_id=%s scope=%s limit=%d query=%s",
        user_id, scope, limit, query[:80],
    )
    svc = get_memory_service(db)

    scopes = [scope] if scope else None
    metadata_filters = _build_metadata_filters(
        object_type=object_type,
        symbol=symbol,
        market=market,
        memory_kind=memory_kind,
    )
    items = await svc.recall(
        query=query,
        user_id=user_id,
        scopes=scopes,
        metadata_filters=metadata_filters,
        limit=limit,
    )
    return {
        "success": True,
        "data": {
            "count": len(items),
            "items": [item.model_dump() for item in items],
        },
    }


@router.post("/batch-delete")
async def memory_batch_delete(
    memory_ids: List[str] = Body(..., embed=True),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Delete memories in batches"""
    from core.memory.service import get_memory_service
    svc = get_memory_service(db)
    deleted = 0
    for mid in memory_ids[:50]:
        if await svc.delete_memory(mid):
            deleted += 1
    return {"success": True, "data": {"deleted": deleted, "requested": len(memory_ids)}}


@router.delete("/clear-all")
async def memory_delete_all(
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Clear all memories of current user"""
    from core.memory.service import get_memory_service
    user_id = _resolve_user_id(user)
    svc = get_memory_service(db)
    count = await svc.delete_all_user_memories(user_id)
    return {"success": True, "data": {"deleted": count}}


@router.delete("/{memory_id}")
async def memory_delete(
    memory_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Delete a single memory"""
    from core.memory.service import get_memory_service
    svc = get_memory_service(db)
    ok = await svc.delete_memory(memory_id)
    if ok:
        return {"success": True, "message": "memory deleted"}
    return {"success": False, "message": "Deletion failed, please try again later"}


# =============================================================================
# Intelligent Assistant Fact Memory (assistant_memory_facts)
# Unlike mem0 object memory: fact memory is extracted by the intelligent assistant from the network tool results (including numeric
# short sentences,≤150 characters), stored in the assistant_memory_facts collection, recalled across sessions for reference by the assistant.
# Read-only browsing, search and delete capabilities are provided here.
# =============================================================================
_FACTS_COLLECTION = "assistant_memory_facts"


def _serialize_fact(doc: dict) -> dict:
    """Serialize the fact document into a front-end usable dict (_id -> id) . """
    out = {"id": str(doc["_id"])}
    out.update({k: v for k, v in doc.items() if k != "_id"})
    return out


@router.get("/assistant-facts")
async def assistant_facts_list(
    q: Optional[str] = Query(None, description="Search by topic/content keywords"),
    symbol: Optional[str] = Query(None, description="Filter by ticker"),
    category: Optional[str] = Query(None, description="Filter by data category"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Paging query of the fact memory extracted by the intelligent assistant (in reverse order of collection time)."""
    query: dict = {}
    if q:
        q = q.strip()
        if q:
            query["$or"] = [
                {"topic": {"$regex": re.escape(q), "$options": "i"}},
                {"content": {"$regex": re.escape(q), "$options": "i"}},
            ]
    if symbol:
        query["symbol"] = symbol.strip()
    if category:
        query["category"] = category.strip()
    total = await db[_FACTS_COLLECTION].count_documents(query)
    cursor = (
        db[_FACTS_COLLECTION]
        .find(query)
        .sort("fetched_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_serialize_fact(doc) async for doc in cursor]
    logger.info("[memory-api] assistant-facts list — page=%d page_size=%d total=%d", page, page_size, total)
    return {
        "success": True,
        "data": {"items": items, "total": total, "page": page, "page_size": page_size},
    }


@router.post("/assistant-facts/batch-delete")
async def assistant_facts_batch_delete(
    fact_ids: List[str] = Body(..., embed=True),
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Delete fact memories in batches."""
    from bson import ObjectId
    ids = [ObjectId(fid) for fid in fact_ids[:100] if ObjectId.is_valid(fid)]
    result = await db[_FACTS_COLLECTION].delete_many({"_id": {"$in": ids}})
    return {
        "success": True,
        "data": {"deleted": result.deleted_count, "requested": len(fact_ids)},
    }


@router.delete("/assistant-facts/{fact_id}")
async def assistant_facts_delete(
    fact_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Delete single fact memory."""
    from bson import ObjectId
    if not ObjectId.is_valid(fact_id):
        return {"success": False, "message": "invalid fact ID"}
    result = await db[_FACTS_COLLECTION].delete_one({"_id": ObjectId(fact_id)})
    if result.deleted_count:
        return {"success": True, "message": "Factual memory deleted"}
    return {"success": False, "message": "Deletion failed, please try again later"}
_snapshots['memory'] = dict(globals())

# === advanced_courses.py ===
"""Advanced course content authorized access routing"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.permissions import require_feature
from app.core.response import ok


router = APIRouter(
    prefix="/api/learning/advanced-courses",
    tags=["advanced-courses"],
    dependencies=[Depends(require_feature("advanced_courses"))]
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COURSE_ROOT = PROJECT_ROOT / "docs" / "courses" / "advanced" / "expanded"
IMAGE_ROOT = COURSE_ROOT / "images"

LESSON_FILE_PREFIX = "lesson-"
LESSON_FILE_SUFFIX = ".md"

SAMPLE_FILE_MAP = {
    "000001-research-report-2026-04-30": "000001_research report_2026-04-30.md",
}


def _resolve_within(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    resolved_root = root.resolve()

    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Resource does not exist") from exc

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Resource does not exist")

    return candidate


def _resolve_lesson_file(filename: str) -> Path:
    if not filename.startswith(LESSON_FILE_PREFIX) or not filename.endswith(LESSON_FILE_SUFFIX):
        raise HTTPException(status_code=404, detail="Course does not exist")

    return _resolve_within(COURSE_ROOT, filename)


def _resolve_sample_file(sample_id: str) -> Path:
    filename = SAMPLE_FILE_MAP.get(sample_id)
    if not filename:
        raise HTTPException(status_code=404, detail="Course example does not exist")

    return _resolve_within(COURSE_ROOT, filename)


@router.get("/lessons/content")
async def get_lesson_content(filename: str = Query(..., min_length=1)):
    lesson_path = _resolve_lesson_file(filename)
    return ok({
        "filename": lesson_path.name,
        "content": lesson_path.read_text(encoding="utf-8"),
    })


@router.get("/lessons/download")
async def download_lesson(filename: str = Query(..., min_length=1)):
    lesson_path = _resolve_lesson_file(filename)
    return FileResponse(
        lesson_path,
        media_type="text/markdown; charset=utf-8",
        filename=lesson_path.name,
    )


@router.get("/samples/{sample_id}")
async def get_sample_content(sample_id: str):
    sample_path = _resolve_sample_file(sample_id)
    return ok({
        "sample_id": sample_id,
        "filename": sample_path.name,
        "content": sample_path.read_text(encoding="utf-8"),
    })


@router.get("/samples/{sample_id}/download")
async def download_sample(sample_id: str):
    sample_path = _resolve_sample_file(sample_id)
    return FileResponse(
        sample_path,
        media_type="text/markdown; charset=utf-8",
        filename=sample_path.name,
    )


@router.get("/images/{image_path:path}")
async def get_course_image(image_path: str):
    image_file = _resolve_within(IMAGE_ROOT, image_path)
    return FileResponse(image_file)
_snapshots['advanced_courses'] = dict(globals())

for _stem, _snap in _snapshots.items():
    _vmod = _types.ModuleType(f"app.routers.{_stem}")
    _vmod.__dict__.update(_snap)
    _sys.modules[f"app.routers.{_stem}"] = _vmod
    setattr(_routers_pkg, _stem, _vmod)
    setattr(_self_mod, _stem, _vmod)