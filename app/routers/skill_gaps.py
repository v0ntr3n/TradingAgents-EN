"""
Skill Gap-aware API routing

Provides operation interfaces such as list, details, ignore, and resolution of gap reports.
endpoint prefix: /api/skill-gaps
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.auth_db import get_current_user
from app.services.skill_gap_service import get_skill_gap_service

logger = logging.getLogger("webapi")

router = APIRouter(prefix="/api/skill-gaps", tags=["skill-gaps"])


# =============================================================================
# request model
# =============================================================================


class DismissRequest(BaseModel):
    """Ignore gap requests"""
    pass


class ResolveRequest(BaseModel):
    """Mark request resolved"""
    skill_id: str = ""


# =============================================================================
# endpoint
# =============================================================================


@router.get("", summary="Get a list of gap reports")
async def list_gaps(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    user: dict = Depends(get_current_user),
):
    """Get the tool gap report list of the current user in pagination"""
    svc = get_skill_gap_service()
    return await svc.list_gaps(user["id"], status, page, page_size)


@router.get("/stats", summary="gap statistics")
async def get_stats(user: dict = Depends(get_current_user)):
    """Get statistics for the current user gap report (grouped by status/type)"""
    svc = get_skill_gap_service()
    return await svc.get_stats(user["id"])


@router.get("/{report_id}", summary="Get a single gap report")
async def get_gap(report_id: str, user: dict = Depends(get_current_user)):
    """Get details of a specified gap report"""
    svc = get_skill_gap_service()
    doc = await svc.get_gap(report_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Gap report does not exist")
    if doc.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Don t have permission to access this report")
    return doc


@router.post("/{report_id}/dismiss", summary="ignore notch")
async def dismiss_gap(report_id: str, user: dict = Depends(get_current_user)):
    """Mark the gap report as ignored and will not report it to the tool with the same name again within 30 days"""
    svc = get_skill_gap_service()
    ok = await svc.dismiss_gap(report_id, user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="The gap report does not exist or does not have permission to operate")
    return {"success": True, "message": "Ignored"}


@router.post("/{report_id}/resolve", summary="Flag resolved")
async def resolve_gap(
    report_id: str,
    body: ResolveRequest,
    user: dict = Depends(get_current_user),
):
    """Mark the gap report as resolved to associate the created Skill ID"""
    svc = get_skill_gap_service()
    ok = await svc.resolve_gap(report_id, user["id"], body.skill_id)
    if not ok:
        raise HTTPException(status_code=404, detail="The gap report does not exist or does not have permission to operate")
    return {"success": True, "message": "Marked as resolved"}


@router.get("/{report_id}/create-skill-params", summary="Get the pre-filled parameters for creating Skill")
async def get_create_skill_params(
    report_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Generate pre-filled parameters for the Skill Workshop based on the gap report,
    The front end can jump directly to /workflow/skill-generation/create and pass in these parameters.
    """
    svc = get_skill_gap_service()
    doc = await svc.get_gap(report_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Gap report does not exist")
    if doc.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Don t have permission to access this report")

    gap = doc.get("gap", {})
    tool_name = gap.get("tool_name", "")
    gap_type = gap.get("type", "")
    error_msg = gap.get("error_message", "")
    source = doc.get("source", {})

    # Construct prefilled parameters
    description = f"for Agent [{source.get('agent_id', '')}] Provide tools `{tool_name}` function."
    if gap_type == "tool_execution_error" and error_msg:
        description += f"\n\n original error: {error_msg}"

    return {
        "prefill": {
            "name": tool_name,
            "description": description,
            "tags": ["auto-suggested", gap_type],
        },
        "report_id": report_id,
    }

