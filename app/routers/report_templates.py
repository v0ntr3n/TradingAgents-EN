"""
Report Template API Route

Provides CRUD interface for report templates and workflow report generation interface.
"""
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.database import get_mongo_db
from app.routers.auth_db import get_current_user
from app.models.report_template import (
    ReportTemplateCreate,
    ReportTemplateUpdate,
    ReportTemplateResponse
)
from app.services.report_template_service import ReportTemplateService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/report-templates", tags=["report template"])


def get_service():
    """Get report template service instance"""
    db = get_mongo_db()
    return ReportTemplateService(db)


@router.post("", response_model=ReportTemplateResponse)
async def create_template(
    data: ReportTemplateCreate,
    user: dict = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_service)
):
    """Create report template"""
    try:
        user_id = str(user.get("_id")) if user else None
        return await service.create_template(data, user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Failed to create report template: {e}")
        raise HTTPException(status_code=500, detail=f"Creation failed: {str(e)}")


@router.get("", response_model=List[ReportTemplateResponse])
async def list_templates(
    workflow_id: Optional[str] = Query(None, description="Workflow ID filtering"),
    status: Optional[str] = Query(None, description="status filter: active, inactive"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_service)
):
    """List report templates"""
    return await service.list_templates(
        workflow_id=workflow_id,
        status=status,
        skip=skip,
        limit=limit
    )


@router.get("/{template_id}", response_model=ReportTemplateResponse)
async def get_template(
    template_id: str,
    user: dict = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_service)
):
    """Get report template details"""
    template = await service.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template does not exist")
    return template


@router.get("/workflow/{workflow_id}", response_model=ReportTemplateResponse)
async def get_template_by_workflow(
    workflow_id: str,
    user: dict = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_service)
):
    """Get report template based on workflow ID"""
    template = await service.get_template_by_workflow(workflow_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} No associated report template")
    return template


@router.put("/{template_id}", response_model=ReportTemplateResponse)
async def update_template(
    template_id: str,
    data: ReportTemplateUpdate,
    user: dict = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_service)
):
    """Update report template"""
    result = await service.update_template(template_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Template does not exist")
    return result


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    user: dict = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_service)
):
    """Delete report template"""
    success = await service.delete_template(template_id)
    if not success:
        raise HTTPException(status_code=404, detail="Template does not exist")
    return {"message": "Delete successfully", "template_id": template_id}


@router.post("/generate")
async def generate_report(
    workflow_id: str = Query(..., description="Workflow ID"),
    agent_outputs: Dict[str, Any] = None,
    use_llm: bool = Query(True, description="Whether to use LLM to generate reports"),
    user: dict = Depends(get_current_user)
):
    """
    Generate reports based on workflow and Agent output
    
    It is usually called automatically after the workflow execution is completed, and the test can also be called manually.
    """
    from core.workflow.report_generator import ReportGenerator
    
    db = get_mongo_db()
    generator = ReportGenerator(db)
    
    try:
        report = await generator.generate_report(
            workflow_id=workflow_id,
            agent_outputs=agent_outputs or {},
            use_llm=use_llm
        )
        return {
            "success": True,
            "report": report
        }
    except Exception as e:
        logger.error(f"❌ Report generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")

