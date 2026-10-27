"""
Workflow API interface

Workflow execution interface provided for external service calls
Supports both synchronous and asynchronous execution modes
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field

from app.routers.auth_db import get_current_user
from app.core.response import ok, fail
from app.services.task_analysis_service import get_task_analysis_service
from app.models.analysis import AnalysisTaskType, PyObjectId
from bson import ObjectId

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflow", tags=["Workflow API"])


# ========== request model ==========

class WorkflowExecuteRequest(BaseModel):
    """Workflow execution request"""
    
    # Required parameters
    workflow_id: str = Field(..., description="Workflow ID (workflow ID in the database or system preset workflow ID)")
    
    # Stock analysis parameters
    ticker: Optional[str] = Field(None, description="Stock code (e.g.:000001, AAPL) ")
    stock_code: Optional[str] = Field(None, description="Stock code (alias, choose one from ticker)")
    analysis_date: Optional[str] = Field(None, description="Analysis date (format: YYYY-MM-DD, default is today)")
    market_type: Optional[str] = Field(None, description="Market type (cn/us/hk, automatically recognized by default)")
    
    # Analysis configuration
    research_depth: Optional[str] = Field("fast", description="Research Depth (Quick/Standard/Deep)")
    preference_type: Optional[str] = Field("neutral", description="Risk preference (aggressive/neutral/conservative)")
    
    # Model configuration
    quick_analysis_model: Optional[str] = Field(None, description="Quickly analyze models")
    deep_analysis_model: Optional[str] = Field(None, description="Deep analysis model")
    
    # Workflow parameters
    lookback_days: Optional[int] = Field(30, description="Lookback days")
    max_debate_rounds: Optional[int] = Field(2, description="Maximum number of debate rounds")
    
    # Custom parameters (additional parameters passed to the workflow)
    custom_params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom parameters")
    
    # execution mode
    async_mode: bool = Field(True, description="Whether to execute asynchronously (True=Return task_id,False=Waiting for results)")
    timeout: Optional[int] = Field(1800, description="Timeout in synchronous mode (seconds), default 30 minutes")
    
    # Callback configuration
    callback_url: Optional[str] = Field(None, description="Callback URL in asynchronous mode (POST result after task completion)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "workflow_id": "stock_analysis_workflow",
                "ticker": "000001",
                "analysis_date": "2026-02-19",
                "research_depth": "Standard",
                "preference_type": "neutral",
                "async_mode": True
            }
        }


class WorkflowExecuteResponse(BaseModel):
    """Workflow execution response"""
    
    # Asynchronous mode returns
    task_id: Optional[str] = Field(None, description="Task ID (asynchronous mode)")
    status: Optional[str] = Field(None, description="Task status")
    message: Optional[str] = Field(None, description="Prompt message")
    
    # Synchronous mode returns
    success: Optional[bool] = Field(None, description="Whether the execution is successful (synchronous mode)")
    result: Optional[Dict[str, Any]] = Field(None, description="Execution results (synchronous mode)")
    execution_time: Optional[float] = Field(None, description="Execution time (seconds)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "pending",
                "message": "The task has been submitted and is being executed in the background"
            }
        }


class TaskStatusResponse(BaseModel):
    """Task status response"""
    
    task_id: str = Field(..., description="Task ID")
    status: str = Field(..., description="Task status (pending/running/completed/failed)")
    progress: int = Field(0, description="Execution progress (0-100)")
    message: Optional[str] = Field(None, description="Current status description")
    
    # Mission information
    created_at: Optional[datetime] = Field(None, description="creation time")
    started_at: Optional[datetime] = Field(None, description="start time")
    completed_at: Optional[datetime] = Field(None, description="completion time")
    execution_time: Optional[float] = Field(None, description="Execution time (seconds)")
    
    # Result (only when completed)
    result: Optional[Dict[str, Any]] = Field(None, description="Execution result")
    error: Optional[str] = Field(None, description="Error message (on failure)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "completed",
                "progress": 100,
                "message": "Task execution completed",
                "execution_time": 125.5,
                "result": {
                    "summary": "Analysis completed",
                    "recommendation": "Recommended to pay attention to"
                }
            }
        }


# ========== API endpoint ==========

@router.post("/execute", response_model=WorkflowExecuteResponse)
async def execute_workflow(
    request: WorkflowExecuteRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)  # Support JWT Token and Session authentication
):
    """
    Execute workflow
    
    Two modes are supported:
    1. **asynchronous mode** (Default): immediately returns task_id, passed /task/{task_id}/status Query status
    2. **synchronous mode**: Wait for the execution to complete before returning the result (suitable for workflows with short timeouts)
    
    Authentication method:
    - Header: `Authorization: Bearer <token>`
    - Header: `X-API-Key: <api_key>`
    """
    try:
        user_id = user.get("user_id") or user.get("_id")
        logger.info(f"🎯 [Workflow API] Execution request received: workflow_id={request.workflow_id}, user={user_id}")

        # 🆕 Query the workflow type and determine whether ticker is required.
        from app.core.database import get_mongo_db
        from app.models.analysis import AnalysisTaskType
        db = get_mongo_db()
        wf_doc = await db.workflows.find_one(
            {"_id": request.workflow_id},
            {"workflow_type": 1, "input_config": 1}
        )
        workflow_type = wf_doc.get("workflow_type", "stock_analysis") if wf_doc else "stock_analysis"
        input_config = wf_doc.get("input_config") if wf_doc else None

        # Get stock code (required only for stock_analysis/etf_analysis)
        ticker = request.ticker or request.stock_code
        TICKER_REQUIRED_TYPES = {"stock_analysis", "etf_analysis"}
        if workflow_type in TICKER_REQUIRED_TYPES and not ticker:
            raise HTTPException(status_code=400, detail=f"Workflow type {workflow_type} The ticker or stock_code parameter must be provided")

        # 🆕 Mapping based on workflow_type task_type
        WORKFLOW_TYPE_TO_TASK_TYPE = {
            "stock_analysis": AnalysisTaskType.STOCK_ANALYSIS,
            "etf_analysis": AnalysisTaskType.ETF_ANALYSIS,
            "position_analysis": AnalysisTaskType.POSITION_ANALYSIS,
            "trade_review": AnalysisTaskType.TRADE_REVIEW,
            "general": AnalysisTaskType.STOCK_ANALYSIS,
        }
        task_type = WORKFLOW_TYPE_TO_TASK_TYPE.get(workflow_type, AnalysisTaskType.STOCK_ANALYSIS)

        # Build task parameters
        task_params = {}
        if ticker:
            task_params["symbol"] = ticker
            task_params["stock_code"] = ticker
        task_params["analysis_date"] = request.analysis_date or datetime.now().strftime("%Y-%m-%d")
        task_params["market_type"] = request.market_type
        task_params["research_depth"] = request.research_depth
        task_params["quick_analysis_model"] = request.quick_analysis_model
        task_params["deep_analysis_model"] = request.deep_analysis_model
        task_params["lookback_days"] = request.lookback_days
        task_params["max_debate_rounds"] = request.max_debate_rounds

        # 🆕 Supplement missing parameters based on the default value of input_config.fields
        if input_config and isinstance(input_config, dict):
            fields = input_config.get("fields", [])
            for field in fields:
                fname = field.get("name")
                if fname and fname not in task_params and fname not in ("ticker", "symbol", "stock_code"):
                    default_val = field.get("default")
                    if default_val is not None:
                        task_params[fname] = default_val

        # Merge custom parameters
        task_params.update(request.custom_params)

        # Mark the general type
        if workflow_type == "general":
            task_params["task_category"] = "general"

        # Get task service
        task_service = get_task_analysis_service()

        if request.async_mode:
            # Asynchronous mode: create task and return task_id
            task = await task_service.create_task(
                user_id=PyObjectId(user_id),
                task_type=task_type,
                task_params=task_params,
                engine_type="workflow",
                preference_type=request.preference_type,
                workflow_id=request.workflow_id
            )

            # Execute tasks asynchronously
            asyncio.create_task(task_service.execute_task(task))

            logger.info(f"✅ [Workflow API] Asynchronous task has been created: task_id={task.task_id}")

            return WorkflowExecuteResponse(
                task_id=task.task_id,
                status=task.status,
                message="The task has been submitted and is being executed in the background"
            )
        else:
            # Synchronous mode: wait for execution to complete
            task = await task_service.create_task(
                user_id=PyObjectId(user_id),
                task_type=task_type,
                task_params=task_params,
                engine_type="workflow",
                preference_type=request.preference_type,
                workflow_id=request.workflow_id
            )

            logger.info(f"🔄 [Workflow API] Execute tasks synchronously: task_id={task.task_id}")

            # Execute tasks synchronously (wait for completion)
            try:
                result = await asyncio.wait_for(
                    task_service.execute_task(task),
                    timeout=request.timeout
                )

                # Retrieve task status
                task = await task_service.get_task(task.task_id)

                logger.info(f"✅ [Workflow API] Synchronization task completed: task_id={task.task_id}")

                return WorkflowExecuteResponse(
                    success=True,
                    result=task.result,
                    execution_time=task.execution_time,
                    message="Task execution completed"
                )
            except asyncio.TimeoutError:
                logger.warning(f"⏰ [Workflow API] Synchronization task timeout: task_id={task.task_id}")
                return WorkflowExecuteResponse(
                    success=False,
                    task_id=task.task_id,
                    message=f"Task execution timeout (exceeds{request.timeout}seconds), please use asynchronous mode or query the results by task_id"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Workflow API] Execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/task/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Query task status

    Used to query task execution status and progress in asynchronous mode
    """
    try:
        user_id = user.get("user_id") or user.get("_id")
        logger.info(f"🔍 [Workflow API] Query task status: task_id={task_id}, user={user_id}")

        task_service = get_task_analysis_service()
        task = await task_service.get_task(task_id)

        if not task:
            raise HTTPException(status_code=404, detail="Task does not exist")

        # Verify task ownership
        if str(task.user_id) != str(user_id):
            raise HTTPException(status_code=403, detail="Don t have permission to access this task")

        return TaskStatusResponse(
            task_id=task.task_id,
            status=task.status,
            progress=task.progress,
            message=task.status_message,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            execution_time=task.execution_time,
            result=task.result if task.status == "completed" else None,
            error=task.error_message if task.status == "failed" else None
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Workflow API] Failed to query task status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/task/{task_id}/result")
async def get_task_result(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Get task results

    Return detailed results of completed tasks
    """
    try:
        user_id = user.get("user_id") or user.get("_id")
        logger.info(f"📊 [Workflow API] Get task results: task_id={task_id}, user={user_id}")

        task_service = get_task_analysis_service()
        task = await task_service.get_task(task_id)

        if not task:
            raise HTTPException(status_code=404, detail="Task does not exist")

        # Verify task ownership
        if str(task.user_id) != str(user_id):
            raise HTTPException(status_code=403, detail="Don t have permission to access this task")

        if task.status != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"The task has not been completed yet, current status: {task.status}"
            )

        return ok({
            "task_id": task.task_id,
            "status": task.status,
            "result": task.result,
            "execution_time": task.execution_time,
            "completed_at": task.completed_at
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Workflow API] Failed to obtain task results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/task/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Cancel task

    Cancel an executing or waiting task
    """
    try:
        user_id = user.get("user_id") or user.get("_id")
        logger.info(f"🛑 [Workflow API] Cancel task: task_id={task_id}, user={user_id}")

        task_service = get_task_analysis_service()
        task = await task_service.get_task(task_id)

        if not task:
            raise HTTPException(status_code=404, detail="Task does not exist")

        # Verify task ownership
        if str(task.user_id) != str(user_id):
            raise HTTPException(status_code=403, detail="Don t have permission to access this task")

        if task.status in ["completed", "failed", "cancelled"]:
            raise HTTPException(
                status_code=400,
                detail=f"The task has ended and cannot be canceled. Current status: {task.status}"
            )

        # Update task status to Canceled
        await task_service.cancel_task(task_id)

        return ok({
            "task_id": task_id,
            "status": "cancelled",
            "message": "Task canceled"
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Workflow API] Failed to cancel task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

