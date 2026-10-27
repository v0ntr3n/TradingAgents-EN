from datetime import datetime
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from bson import ObjectId
from core.tools.registry import get_tool_registry
from app.core.database import get_mongo_db
from app.routers.auth_db import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skill-center", tags=["skill-center"])

class SkillSummary(BaseModel):
    skill_id: str = Field(description="Skill ID")
    display_name: str = Field(description="display name")
    description: str = Field(description="Description")
    source: str = Field(description="Source: system/imported/ai_generated/gap_generated")
    type: str = Field(description="Type: knowledge/executable/api/mcp")
    status: str = Field(description="Status: draft/testing/active/disabled/archived/failed")
    bindable: bool = Field(description="Whether it can be bound")
    tool_id: Optional[str] = Field(description="Tools ID")
    test_status: Optional[str] = Field(description="test status: passed/failed/unknown")
    last_tested_at: Optional[str] = Field(description="Last test time")
    bindings: Dict[str, List[str]] = Field(description="Binding relationship")
    created_at: Optional[str] = Field(description="creation time")
    updated_at: Optional[str] = Field(description="Update time")

    model_config = {
        "from_attributes": True,
        "populate_by_name": True
    }

def _convert_standard_skill(doc: dict) -> SkillSummary:
    tool_id = doc.get("name", "").replace("-", "_")
    implementation = doc.get("implementation")
    source_type = doc.get("source_type")
    return SkillSummary(
        skill_id=doc.get("name", str(doc.get("_id"))),
        display_name=doc.get("name", ""),
        description=doc.get("description", ""),
        source="clawhub" if source_type == "clawhub" else "imported",
        type="executable" if implementation or doc.get("executable", False) else "knowledge",
        status="active" if doc.get("enabled", False) else "disabled",
        bindable=True,
        tool_id=tool_id,
        test_status="unknown",
        last_tested_at=None,
        bindings={"agents": [], "workflows": []},
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at")
    )

def _convert_external_skill(doc: dict) -> SkillSummary:
    return SkillSummary(
        skill_id=doc.get("tool_id", str(doc.get("_id"))),
        display_name=doc.get("name", doc.get("tool_id", "")),
        description=doc.get("description", ""),
        source="ai_generated",
        type="executable",
        status=doc.get("status", "draft"),
        bindable=True,
        tool_id=doc.get("tool_id"),
        test_status=doc.get("test_status", "unknown"),
        last_tested_at=doc.get("last_test_at"),
        bindings={"agents": [], "workflows": []},
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at")
    )

async def _get_bindings_for_tool(db, tool_id: str) -> Dict[str, List[str]]:
    bindings = {"agents": [], "workflows": []}
    async for binding in db.tool_agent_bindings.find({"tool_id": tool_id, "is_active": {"$ne": False}}):
        if "agent_id" in binding:
            bindings["agents"].append(binding["agent_id"])
    return bindings

async def _check_registry_status(tool_id: str) -> bool:
    try:
        registry = get_tool_registry()
        return registry.has_tool(tool_id)
    except:
        return False

@router.get("/skills", response_model=List[SkillSummary])
async def list_all_skills(
    db = Depends(get_mongo_db),
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    user = Depends(get_current_user)
):
    all_skills = []
    
    async for doc in db.skills.find():
        skill = _convert_standard_skill(doc)
        skill.bindings = await _get_bindings_for_tool(db, skill.tool_id)
        all_skills.append(skill)
    
    async for doc in db.external_skills.find():
        skill = _convert_external_skill(doc)
        skill.bindings = await _get_bindings_for_tool(db, skill.tool_id)
        all_skills.append(skill)
    
    if status:
        all_skills = [s for s in all_skills if s.status == status]
    
    if source:
        all_skills = [s for s in all_skills if s.source == source]
    
    all_skills.sort(key=lambda x: x.updated_at or x.created_at or "", reverse=True)
    return all_skills

@router.get("/skills/{skill_id}", response_model=SkillSummary)
async def get_skill_detail(
    skill_id: str,
    db = Depends(get_mongo_db),
    user = Depends(get_current_user)
):
    doc = await db.skills.find_one({"name": skill_id})
    if doc:
        skill = _convert_standard_skill(doc)
        skill.bindings = await _get_bindings_for_tool(db, skill.tool_id)
        return skill
    
    doc = await db.external_skills.find_one({"tool_id": skill_id})
    if doc:
        skill = _convert_external_skill(doc)
        skill.bindings = await _get_bindings_for_tool(db, skill.tool_id)
        return skill
    
    doc = await db.external_skills.find_one({"_id": ObjectId(skill_id)})
    if doc:
        skill = _convert_external_skill(doc)
        skill.bindings = await _get_bindings_for_tool(db, skill.tool_id)
        return skill
    
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Skill not found")

@router.get("/skills/{skill_id}/test")
async def test_skill(
    skill_id: str,
    db = Depends(get_mongo_db),
    user = Depends(get_current_user)
):
    from fastapi import HTTPException
    
    doc = await db.external_skills.find_one({"tool_id": skill_id})
    if doc:
        from core.tools.external_skill_loader import register_single_external_skill
        from core.tools.registry import get_tool_registry
        
        registry = get_tool_registry()
        try:
            register_single_external_skill(None, registry, doc)
            tool = registry.get_tool(skill_id)
            if tool:
                test_result = tool.test() if hasattr(tool, 'test') else {"status": "no_test_method"}
                return {"success": True, "result": test_result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    doc = await db.skills.find_one({"name": skill_id})
    if doc:
        tool_id = doc.get("name", "").replace("-", "_")
        registry = get_tool_registry()
        tool = registry.get_tool(tool_id)
        if tool:
            try:
                test_result = tool.test() if hasattr(tool, 'test') else {"status": "no_test_method"}
                return {"success": True, "result": test_result}
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    raise HTTPException(status_code=404, detail="Skill not found")

@router.post("/skills/{skill_id}/bind/{agent_id}")
async def bind_skill_to_agent(
    skill_id: str,
    agent_id: str,
    db = Depends(get_mongo_db),
    user = Depends(get_current_user)
):
    """Bind Skill to Agent"""
    from core.config.binding_manager import BindingManager

    binding_mgr = BindingManager()
    binding_mgr.set_database(db)

    success = binding_mgr.bind_tool(agent_id, skill_id, priority=0)
    if not success:
        raise HTTPException(status_code=500, detail="Binding failed")

    return {"success": True, "message": "Skill bound to agent"}

@router.delete("/skills/{skill_id}/bind/{agent_id}")
async def unbind_skill_from_agent(
    skill_id: str,
    agent_id: str,
    db = Depends(get_mongo_db),
    user = Depends(get_current_user)
):
    """Unbind Skill from Agent"""
    from core.config.binding_manager import BindingManager

    binding_mgr = BindingManager()
    binding_mgr.set_database(db)

    success = binding_mgr.unbind_tool(agent_id, skill_id)
    if not success:
        raise HTTPException(status_code=500, detail="Unbinding failed")

    return {"success": True, "message": "Skill unbound from agent"}


class BatchBindRequest(BaseModel):
    """Bulk bind requests"""
    agent_ids: List[str] = Field(..., description="Agent ID list")
    priority: int = Field(0, description="Priority (the bigger the priority)")


@router.post("/skills/{skill_id}/bind-batch")
async def batch_bind_skill_to_agents(
    skill_id: str,
    req: BatchBindRequest,
    db = Depends(get_mongo_db),
    user = Depends(get_current_user)
):
    """Batch bind skills to multiple Agent"""
    from core.config.binding_manager import BindingManager

    binding_mgr = BindingManager()
    binding_mgr.set_database(db)

    bound = []
    failed = []
    for agent_id in req.agent_ids:
        try:
            success = binding_mgr.bind_tool(agent_id, skill_id, priority=req.priority)
            if success:
                bound.append(agent_id)
            else:
                failed.append(agent_id)
        except Exception as e:
            logger.error(f"binding {skill_id} -> {agent_id} failed: {e}")
            failed.append(agent_id)

    return {
        "success": len(failed) == 0,
        "bound": bound,
        "failed": failed,
        "message": f"is bound to {len(bound)} a Agent" + (f", {len(failed)} a failure" if failed else "")
    }


@router.get("/skills/{skill_id}/bindings")
async def get_skill_bindings(
    skill_id: str,
    db = Depends(get_mongo_db),
    user = Depends(get_current_user)
):
    """Get all binding relationships of Skill"""
    bindings = await db.tool_agent_bindings.find(
        {"tool_id": skill_id, "is_active": {"$ne": False}}
    ).to_list(100)

    # Get Agent details
    agent_ids = [b["agent_id"] for b in bindings]
    agents = []
    for aid in agent_ids:
        # Find from BUILTIN_AGENTS
        from core.agents.config import BUILTIN_AGENTS
        agent_meta = BUILTIN_AGENTS.get(aid)
        if agent_meta:
            agents.append({
                "agent_id": aid,
                "name": agent_meta.name,
                "category": agent_meta.category,
                "priority": next((b.get("priority", 0) for b in bindings if b["agent_id"] == aid), 0)
            })
        else:
            agents.append({
                "agent_id": aid,
                "name": aid,
                "category": "custom",
                "priority": next((b.get("priority", 0) for b in bindings if b["agent_id"] == aid), 0)
            })

    return {"agents": agents}


@router.get("/tool-logs")
async def get_tool_execution_logs(
    tool_id: Optional[str] = Query(None, description="Filter by tool ID"),
    agent_id: Optional[str] = Query(None, description="Filter by Agent ID"),
    analysis_id: Optional[str] = Query(None, description="Filter by analysis task ID"),
    success: Optional[bool] = Query(None, description="Filter by success/failure"),
    limit: int = Query(50, ge=1, le=200, description="Return quantity"),
    db = Depends(get_mongo_db),
    user = Depends(get_current_user)
):
    """Query tool execution log"""
    query = {}
    if tool_id:
        query["tool_id"] = tool_id
    if agent_id:
        query["agent_id"] = agent_id
    if analysis_id:
        query["analysis_id"] = analysis_id
    if success is not None:
        query["success"] = success

    logs = await db["tool_execution_logs"].find(query).sort("created_at", -1).limit(limit).to_list(limit)

    # serialization
    for log in logs:
        log["_id"] = str(log["_id"])

    return {"logs": logs, "count": len(logs)}


@router.get("/tool-logs/stats")
async def get_tool_log_stats(
    db = Depends(get_mongo_db),
    user = Depends(get_current_user)
):
    """Tool execution log statistics"""
    total = await db["tool_execution_logs"].count_documents({})
    success_count = await db["tool_execution_logs"].count_documents({"success": True})
    fail_count = await db["tool_execution_logs"].count_documents({"success": False})

    # Statistics by tool
    tool_pipeline = [
        {"$group": {"_id": "$tool_id", "count": {"$sum": 1}, "avg_ms": {"$avg": "$execution_time_ms"}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    tool_stats = await db["tool_execution_logs"].aggregate(tool_pipeline).to_list(10)

    # Statistics by Agent
    agent_pipeline = [
        {"$group": {"_id": "$agent_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    agent_stats = await db["tool_execution_logs"].aggregate(agent_pipeline).to_list(10)

    return {
        "total": total,
        "success": success_count,
        "failed": fail_count,
        "by_tool": [{"tool_id": s["_id"], "count": s["count"], "avg_ms": int(s.get("avg_ms", 0))} for s in tool_stats],
        "by_agent": [{"agent_id": s["_id"], "count": s["count"]} for s in agent_stats],
    }


@router.get("/stats")
async def get_skill_stats(
    db = Depends(get_mongo_db),
    user = Depends(get_current_user)
):
    standard_count = await db.skills.count_documents({})
    external_count = await db.external_skills.count_documents({})
    active_count = await db.skills.count_documents({"enabled": True}) + await db.external_skills.count_documents({"status": "active"})
    binding_count = await db.tool_agent_bindings.count_documents({"is_active": {"$ne": False}})
    
    return {
        "total": standard_count + external_count,
        "standard": standard_count,
        "external": external_count,
        "active": active_count,
        "bindings": binding_count
    }