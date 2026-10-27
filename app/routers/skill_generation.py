"""
Skill generate API — v3.0 AI Driven Skill Creation

Provide endpoints such as demand communication (multiple rounds of dialogue), code generation pipeline, external Skill management, etc.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.core.database import get_mongo_db
from app.core.response import ok, fail
from app.services.capability_index_service import CapabilityIndexService
from app.services.skill_generation_service import SkillGenerationService
from core.tools.external.external_data_source_catalog import (
    EXTERNAL_DATA_SOURCE_CATALOG,
    EXTERNAL_DATA_SOURCE_DOC,
)
from core.tools.external.stock_data_catalog import (
    STOCK_DATA_COLLECTION_CATALOG,
    STOCK_DATA_COLLECTION_DOC,
)

logger = logging.getLogger("webapi")

router = APIRouter(prefix="/api/skill-generation", tags=["skill-generation"])


# =============================================================================
# request/response model
# =============================================================================

class StartSessionRequest(BaseModel):
    """Start creating a session"""
    description: str = Field(..., min_length=2, description="Requirement description")
    user_id: str = Field(default="", description="User ID")
    handoff_context: Optional[Dict[str, Any]] = Field(default=None, description="Handover context from upstream workshop")
    iterate_skill_id: Optional[str] = Field(default=None, description="Iterative mode: There are existing Skills to be optimized tool_id")
    provider: str = Field(default="deepseek", description="LLM Provider (for fallback)")
    model: Optional[str] = Field(default=None, description="Model name (for rollback)")
    reasoning_model: Optional[str] = Field(default=None, description="Requirements analysis model (overrides the system s default in-depth reasoning model)")
    coding_model: Optional[str] = Field(default=None, description="Code generation model (overrides the system s default programming model)")


class RespondRequest(BaseModel):
    """Reply to conversation"""
    message: str = Field(..., min_length=1, description="User reply")


class ConfirmSpecRequest(BaseModel):
    """Confirm specifications"""
    message: str = Field(default="Confirm", description="Confirmation message or additional explanation")
    codegen_timeout: Optional[int] = Field(default=None, ge=60, le=1800, description="Code generation single LLM call timeout (seconds), default value is used if not passed")


class UpdateStatusRequest(BaseModel):
    """Update skill status"""
    status: str = Field(..., description="new status: active / disabled / archived")


class UpdateSkillInfoRequest(BaseModel):
    """Update Skill display name and function description"""
    display_name: str = Field(..., min_length=1, max_length=100, description="display name")
    description: str = Field(default="", max_length=2000, description="Function description")


class TestSkillRequest(BaseModel):
    """test Skill"""
    args: Dict[str, Any] = Field(default_factory=dict, description="Test parameters")


class OptimizeSkillRequest(BaseModel):
    """Optimize Skill"""
    feedback: str = Field(..., min_length=2, description="Optimization requirement description")


class RepairSessionRequest(BaseModel):
    """Correct the current creation session based on failure results"""
    feedback: str = Field(..., min_length=2, description="Tell the AI what s wrong with this round of generation and how you want to change it")
    repair_plan: Optional[str] = Field(default="", description="The text of the correction plan confirmed by the user")
    codegen_timeout: Optional[int] = Field(default=None, ge=60, le=1800, description="Code generation single LLM call timeout (seconds), default value is used if not passed")


# =============================================================================
# Helper function
# =============================================================================

async def _get_service_with_llm(
    db: AsyncIOMotorDatabase,
    provider: str = "deepseek",
    model: Optional[str] = None,
    reasoning_model: Optional[str] = None,
    coding_model: Optional[str] = None,
) -> SkillGenerationService:
    """
    Create SkillGenerationService:
    - Requirements analysis: Specify reasoning_model first, otherwise use the system deep reasoning large model 
    - Code generation: coding_model is specified first, otherwise the system programming large model is used
    - Fall back to when neither is configured. provider/model
    """
    from app.services.intelligent_assistant_service import (
        get_coding_llm_config,
        get_quick_llm_config,
        get_reasoning_llm_config,
    )
    from core.llm import UnifiedLLMClient

    # Requirements Analysis: Deep Reasoning Large Model
    reasoning_config = None
    if reasoning_model:
        from app.services.intelligent_assistant_service import _get_llm_config_for_model
        reasoning_config = await _get_llm_config_for_model(db, reasoning_model)
    if not reasoning_config:
        reasoning_config = await get_reasoning_llm_config(db)
    reasoning_client = (
        UnifiedLLMClient.from_config(reasoning_config) if reasoning_config else None
    )
    if reasoning_client:
        logger.debug("Skill Requirements analysis uses deep reasoning large models")

    # Requirements dialogue: fast model (clarity assessment/boundary detection/multiple rounds of reply), significantly reducing round response delay
    quick_config = await get_quick_llm_config(db)
    quick_client = (
        UnifiedLLMClient.from_config(quick_config) if quick_config else None
    )
    if quick_client:
        logger.debug("Skill Requirements dialogue using quick models")

    # Code Generation: The Big Model of Programming
    coding_config = None
    if coding_model:
        from app.services.intelligent_assistant_service import _get_llm_config_for_model
        coding_config = await _get_llm_config_for_model(db, coding_model)
    if not coding_config:
        coding_config = await get_coding_llm_config(db)
    coding_client = (
        UnifiedLLMClient.from_config(coding_config) if coding_config else None
    )
    if coding_client:
        logger.debug("Skill Code generation using large programming models")

    return SkillGenerationService(
        db=db,
        reasoning_llm_client=reasoning_client,
        coding_llm_client=coding_client,
        quick_llm_client=quick_client,
        provider=provider,
        model=model,
    )


# =============================================================================
# Model Selection API (Open Large Model Search/Selection)
# =============================================================================

@router.get("/models")
async def list_available_models(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """
    Get Skill to generate a list of available models for front-end drop-down selection
    Return the model in the system configuration and mark the default requirements analysis model and code generation model
    """
    try:
        config_doc = await db.system_configs.find_one(
            {"is_active": True}, sort=[("version", -1)]
        )
        if not config_doc or "llm_configs" not in config_doc:
            return ok({
                "models": [],
                "default_reasoning_model": None,
                "default_coding_model": None,
            })

        default_models = config_doc.get("default_models") or {}
        system_settings = config_doc.get("system_settings") or {}
        reasoning = (
            default_models.get("deep_reasoning_model")
            or system_settings.get("deep_reasoning_model")
        )
        coding = (
            default_models.get("coding_model")
            or system_settings.get("coding_model")
        )

        llm_configs = config_doc.get("llm_configs", [])
        models = [
            {
                "model_name": c.get("model_name"),
                "display_name": c.get("model_display_name") or c.get("model_name"),
                "provider": c.get("provider"),
                "enabled": c.get("enabled", True),
            }
            for c in llm_configs
            if c.get("enabled", True)
        ]
        return ok({
            "models": models,
            "default_reasoning_model": reasoning,
            "default_coding_model": coding,
        })
    except Exception as e:
        logger.error(f"Failed to get model list: {e}", exc_info=True)
        return ok({"models": [], "default_reasoning_model": None, "default_coding_model": None})


@router.get("/catalog/stock-data")
async def get_stock_data_catalog():
    """Get the directory of stock data collections used by the Skill builder."""
    return ok({
        "collections": STOCK_DATA_COLLECTION_CATALOG,
        "doc": STOCK_DATA_COLLECTION_DOC,
    })


@router.get("/catalog/external-data-sources")
async def get_external_data_source_catalog():
    """Get the external interface and data source directory used by the Skill generator."""
    return ok({
        "sources": EXTERNAL_DATA_SOURCE_CATALOG,
        "doc": EXTERNAL_DATA_SOURCE_DOC,
    })


# =============================================================================
# Requirements communication API
# =============================================================================

@router.post("/sessions/start")
async def start_session(
    req: StartSessionRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Start a Skill creation session: Submit initial requirements, AI returns with clarification questions"""
    try:
        svc = await _get_service_with_llm(
            db,
            provider=req.provider,
            model=req.model,
            reasoning_model=req.reasoning_model,
            coding_model=req.coding_model,
        )
        result = await svc.start_session(
            description=req.description,
            user_id=req.user_id,
            handoff_context=req.handoff_context,
            iterate_skill_id=req.iterate_skill_id,
        )
        return ok(result)
    except Exception as e:
        logger.error(f"❌ Failed to create session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/respond")
async def respond_to_session(
    session_id: str,
    req: RespondRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Users reply to AI questions to advance the conversation"""
    try:
        svc = await _get_service_with_llm(db)
        result = await svc.respond_to_session(session_id, req.message)
        return ok(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Session reply failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/preview-spec")
async def preview_spec(
    session_id: str,
    req: ConfirmSpecRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Preview Skill specifications (without executing the pipeline) for display of specification confirmation steps"""
    try:
        svc = await _get_service_with_llm(db)
        result = await svc.preview_spec(session_id, req.message)
        if result is None:
            raise HTTPException(status_code=400, detail="Specification generation failed, please describe the requirements again")
        return ok(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Spec preview failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/confirm")
async def confirm_spec(
    session_id: str,
    req: ConfirmSpecRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Confirm Skill specifications and trigger the code generation pipeline"""
    try:
        svc = await _get_service_with_llm(db)
        result = await svc.confirm_spec(session_id, req.message, codegen_timeout=req.codegen_timeout)
        return ok(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Specification confirmation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/repair")
async def repair_session(
    session_id: str,
    req: RepairSessionRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """When the generation/verification fails, correct and generate again based on the failure reason and user feedback."""
    try:
        svc = await _get_service_with_llm(db)
        result = await svc.repair_session(
            session_id, req.feedback, req.repair_plan or "",
            codegen_timeout=req.codegen_timeout,
        )
        return ok(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Session remediation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/repair-plan")
async def preview_repair_session(
    session_id: str,
    req: RepairSessionRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """After failure, first generate an AI correction plan and wait for user confirmation before triggering a rerun."""
    try:
        svc = await _get_service_with_llm(db)
        result = await svc.preview_repair_session(session_id, req.feedback)
        return ok(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Failed to generate remediation plan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions(
    status: Optional[str] = Query(None, description="Filter by status, separate multiple with commas: gathering,confirmed,completed"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """List creation sessions (supports filtering by status, for viewing drafts/unfinished sessions)"""
    svc = await _get_service_with_llm(db)
    result = await svc.list_sessions(
        status=status, user_id=user_id, page=page, page_size=page_size
    )
    return ok(result)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get session details"""
    svc = await _get_service_with_llm(db)
    session = await svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"session {session_id} does not exist")
    return ok(session)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Delete draft conversation"""
    svc = await _get_service_with_llm(db)
    deleted = await svc.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"session {session_id} does not exist")
    return ok({"deleted": True})


# =============================================================================
# External Skill Management API
# =============================================================================

@router.get("/skills")
async def list_skills(
    category: Optional[str] = Query(None, description="Filter by category"),
    status: Optional[str] = Query(None, description="Filter by status: active/disabled/archived"),
    source: Optional[str] = Query(None, description="Filter by source: agent_studio_auto_gap_resolution/manual_or_other/generated"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get the AI-generated Skill list (paginated)"""
    svc = await _get_service_with_llm(db)
    result = await svc.list_skills(
        category=category, status=status, source=source, page=page, page_size=page_size
    )
    return ok(result)


@router.get("/skills/{skill_id}")
async def get_skill(
    skill_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get Skill details"""
    svc = await _get_service_with_llm(db)
    skill = await svc.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} does not exist")
    return ok(skill)


@router.get("/skills/{skill_id}/code")
async def get_skill_code(
    skill_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """View Skill source code"""
    svc = await _get_service_with_llm(db)
    code = await svc.get_skill_code(skill_id)
    if code is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} does not exist")
    return ok({"tool_id": skill_id, "code": code})


@router.get("/skills/{skill_id}/history")
async def get_skill_history(
    skill_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Get Skill s complete communication history (originally created + all optimization rounds)"""
    svc = await _get_service_with_llm(db)
    history = await svc.get_skill_history(skill_id)
    if not history:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} does not exist")
    return ok(history)


@router.get("/skills/{skill_id}/versions")
async def list_skill_versions(
    skill_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Query all versions of a Skill (all iterations of the same series)

    If skill_id is the root Skill, return parent_skill_id=skill_id All versions of + myself
    If skill_id is a subversion, first find the root, and then return to the entire version chain

    Returns are sorted in ascending order by version number, each version contains: tool_id, version, display_name, version_note, status, created_at
    """
    # First check the current skill and determine the root parent_skill_id
    current = await db["external_skills"].find_one({"tool_id": skill_id})
    if not current:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} does not exist")

    # Determine parent_skill_id (the parent_skill_id of the root Skill is empty, and you are the root)
    parent_skill_id = current.get("parent_skill_id") or skill_id

    # Query all versions of the same series: root Skill itself + All parent_skill_id point to the root version
    cursor = db["external_skills"].find({
        "$or": [
            {"tool_id": parent_skill_id},
            {"parent_skill_id": parent_skill_id},
        ]
    }).sort("version", 1)

    versions = []
    async for doc in cursor:
        doc.pop("_id", None)
        versions.append({
            "tool_id": doc.get("tool_id", ""),
            "version": doc.get("version", 1),
            "display_name": doc.get("display_name", ""),
            "version_note": doc.get("version_note", ""),
            "status": doc.get("status", ""),
            "created_at": doc.get("created_at", ""),
            "final_score": doc.get("final_score"),
            "is_current": doc.get("tool_id") == skill_id,
        })

    return ok({
        "parent_skill_id": parent_skill_id,
        "current_tool_id": skill_id,
        "versions": versions,
        "total": len(versions),
    })


@router.put("/skills/{skill_id}/status")
async def update_skill_status(
    skill_id: str,
    req: UpdateStatusRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Update skill status (enable/disable/archive)"""
    if req.status not in ("active", "disabled", "archived"):
        raise HTTPException(status_code=400, detail="The status must be active/disabled/archived")
    svc = await _get_service_with_llm(db)
    updated = await svc.update_skill_status(skill_id, req.status)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} does not exist")
    return ok({"tool_id": skill_id, "status": req.status})


@router.put("/skills/{skill_id}/info")
async def update_skill_info(
    skill_id: str,
    req: UpdateSkillInfoRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Update the display name and function description of the Skill (verified contracts such as parameters/code cannot be modified here)"""
    try:
        svc = await _get_service_with_llm(db)
        updated = await svc.update_skill_info(
            skill_id, req.display_name, req.description
        )
        if not updated:
            raise HTTPException(status_code=404, detail=f"Skill {skill_id} does not exist")
        return ok({
            "tool_id": skill_id,
            "display_name": req.display_name.strip(),
            "description": req.description.strip(),
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Skill Description update failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/skills/{skill_id}")
async def delete_skill(
    skill_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Delete Skill"""
    svc = await _get_service_with_llm(db)
    deleted = await svc.delete_skill(skill_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} does not exist")
    # Asynchronous trigger ability index synchronization, cleanup ghost tool
    asyncio.create_task(CapabilityIndexService.refresh_after_change(db))
    return ok({"tool_id": skill_id, "deleted": True})


@router.post("/skills/{skill_id}/test")
async def test_skill(
    skill_id: str,
    req: TestSkillRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Test the skill manually (execute in sandbox)"""
    try:
        svc = await _get_service_with_llm(db)
        result = await svc.test_skill(skill_id, test_args=req.args or None)
        return ok(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Skill test failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/skills/{skill_id}/optimize")
async def optimize_skill(
    skill_id: str,
    req: OptimizeSkillRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    """Optimize existing skills: regenerate code based on user feedback"""
    try:
        svc = await _get_service_with_llm(db)
        result = await svc.optimize_skill(skill_id, req.feedback)
        return ok(result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Skill Optimization failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
