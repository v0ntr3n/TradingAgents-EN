"""
Workflow growth API
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models.agent_growth import GrowthMemoryScope, GrowthMemoryStatus, GrowthSuggestionStatus
from app.routers.auth_db import get_current_user
from app.services.workflow_growth_service import get_workflow_growth_service

router = APIRouter(prefix="/api/workflow-growth", tags=["workflow-growth"])


@router.get("/memories", summary="Get a list of growing memories")
async def list_growth_memories(
    status: Optional[GrowthMemoryStatus] = Query(None, description="Status filtering"),
    scope: Optional[GrowthMemoryScope] = Query(None, description="Range filtering"),
    task_id: Optional[str] = Query(None, description="Filter by tasks"),
    limit: int = Query(50, ge=1, le=200, description="Return quantity"),
    user: dict = Depends(get_current_user),
):
    service = get_workflow_growth_service()
    items = await service.list_memory_items(
        user_id=str(user["id"]),
        status=status,
        scope=scope,
        task_id=task_id,
        limit=limit,
    )
    return {"success": True, "data": {"items": items, "total": len(items)}, "message": "ok"}


@router.get("/memories/pending", summary="Obtain growth memories to be reviewed")
async def list_pending_growth_memories(
    limit: int = Query(50, ge=1, le=200, description="Return quantity"),
    user: dict = Depends(get_current_user),
):
    service = get_workflow_growth_service()
    items = await service.list_memory_items(
        user_id=str(user["id"]),
        status=GrowthMemoryStatus.PENDING,
        limit=limit,
    )
    return {"success": True, "data": {"items": items, "total": len(items)}, "message": "ok"}


@router.post("/memories/{memory_id}/approve", summary="approved growing memory")
async def approve_growth_memory(memory_id: str, user: dict = Depends(get_current_user)):
    service = get_workflow_growth_service()
    success = await service.approve_memory_item(str(user["id"]), memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Growing up memory does not exist")
    return {"success": True, "message": "Approved for growing memory"}


@router.post("/memories/{memory_id}/reject", summary="Rejection of growing up memories")
async def reject_growth_memory(memory_id: str, user: dict = Depends(get_current_user)):
    service = get_workflow_growth_service()
    success = await service.reject_memory_item(str(user["id"]), memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Growing up memory does not exist")
    return {"success": True, "message": "Rejected growth memory"}


@router.get("/suggestions", summary="Get a list of growing tips")
async def list_growth_suggestions(
    status: Optional[GrowthSuggestionStatus] = Query(None, description="Status filtering"),
    task_id: Optional[str] = Query(None, description="Filter by tasks"),
    limit: int = Query(50, ge=1, le=200, description="Return quantity"),
    user: dict = Depends(get_current_user),
):
    service = get_workflow_growth_service()
    items = await service.list_suggestions(
        user_id=str(user["id"]),
        status=status,
        task_id=task_id,
        limit=limit,
    )
    return {"success": True, "data": {"items": items, "total": len(items)}, "message": "ok"}


@router.post("/suggestions/{suggestion_id}/accept", summary="Accept growth advice")
async def accept_growth_suggestion(suggestion_id: str, user: dict = Depends(get_current_user)):
    service = get_workflow_growth_service()
    result = await service.accept_suggestion(str(user["id"]), suggestion_id)
    if not result:
        raise HTTPException(status_code=404, detail="Growth advice does not exist")
    return {"success": True, "data": result, "message": "Growth suggestions accepted"}


@router.post("/suggestions/{suggestion_id}/dismiss", summary="Ignore growth advice")
async def dismiss_growth_suggestion(suggestion_id: str, user: dict = Depends(get_current_user)):
    service = get_workflow_growth_service()
    success = await service.dismiss_suggestion(str(user["id"]), suggestion_id)
    if not success:
        raise HTTPException(status_code=404, detail="Growth advice does not exist")
    return {"success": True, "message": "Growth suggestions ignored"}


@router.get("/tasks/{task_id}", summary="Get the growth extraction results of the task")
async def get_task_growth_context(task_id: str, user: dict = Depends(get_current_user)):
    service = get_workflow_growth_service()
    data = await service.get_task_context(str(user["id"]), task_id)
    return {"success": True, "data": data, "message": "ok"}