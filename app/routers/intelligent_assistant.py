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
from motor.motor_asyncio import AsyncIOMotorDatabase

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
