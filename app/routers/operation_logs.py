"""
Operation log API routing
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import StreamingResponse

from app.routers.auth_db import get_current_user
from app.services.operation_log_service import get_operation_log_service
from app.models.operation_log import (
    OperationLogQuery,
    OperationLogListResponse,
    OperationLogStatsResponse,
    ClearLogsRequest,
    ClearLogsResponse,
    OperationLogCreate
)

router = APIRouter(prefix="/logs", tags=["Operation log"])
logger = logging.getLogger("webapi")


@router.get("/list", response_model=OperationLogListResponse)
async def get_operation_logs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Quantity per page"),
    start_date: str = Query(None, description="start date"),
    end_date: str = Query(None, description="end date"),
    action_type: str = Query(None, description="Operation type"),
    success: bool = Query(None, description="Is it successful?"),
    keyword: str = Query(None, description="keyword search"),
    current_user: dict = Depends(get_current_user)
):
    """Get operation log list"""
    try:
        logger.info(f"🔍 User {current_user['username']} Get operation log list")
        
        service = get_operation_log_service()
        query = OperationLogQuery(
            page=page,
            page_size=page_size,
            start_date=start_date,
            end_date=end_date,
            action_type=action_type,
            success=success,
            keyword=keyword
        )
        
        logs, total = await service.get_logs(query)
        
        return OperationLogListResponse(
            success=True,
            data={
                "logs": [log.dict() for log in logs],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            },
            message="Obtaining operation log list successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to obtain operation log list: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain operation log list: {str(e)}"
        )


@router.get("/stats", response_model=OperationLogStatsResponse)
async def get_operation_log_stats(
    days: int = Query(30, ge=1, le=365, description="Statistical days"),
    current_user: dict = Depends(get_current_user)
):
    """Get operation log statistics"""
    try:
        logger.info(f"📊 User {current_user['username']} Get operation log statistics")
        
        service = get_operation_log_service()
        stats = await service.get_stats(days)
        
        return OperationLogStatsResponse(
            success=True,
            data=stats,
            message="Obtain operation log statistics successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to obtain operation log statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain operation log statistics: {str(e)}"
        )


@router.get("/{log_id}")
async def get_operation_log_detail(
    log_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get operation log details"""
    try:
        logger.info(f"🔍 User {current_user['username']} Get operation log details: {log_id}")
        
        service = get_operation_log_service()
        log = await service.get_log_by_id(log_id)
        
        if not log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Operation log does not exist"
            )
        
        return {
            "success": True,
            "data": log.dict(),
            "message": "Obtaining operation log details successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to obtain operation log details: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain operation log details: {str(e)}"
        )


@router.post("/clear", response_model=ClearLogsResponse)
async def clear_operation_logs(
    request: ClearLogsRequest,
    current_user: dict = Depends(get_current_user)
):
    """Clear operation log"""
    try:
        logger.info(f"🗑️ User {current_user['username']} Clear operation log")
        
        service = get_operation_log_service()
        result = await service.clear_logs(
            days=request.days,
            action_type=request.action_type
        )
        
        message = f"The operation log was cleared successfully and deleted. {result['deleted_count']} records"
        if request.days:
            message += f" ({request.days}Days ago s log)"
        if request.action_type:
            message += f" (Type: {request.action_type}) "
        
        return ClearLogsResponse(
            success=True,
            data=result,
            message=message
        )
        
    except Exception as e:
        logger.error(f"Failed to clear operation log: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear operation log: {str(e)}"
        )


@router.post("/create")
async def create_operation_log(
    log_data: OperationLogCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Manually create operation logs"""
    try:
        logger.info(f"📝 User {current_user['username']} Manually create operation logs")
        
        service = get_operation_log_service()
        
        # Get client information
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        
        log_id = await service.create_log(
            user_id=current_user["id"],
            username=current_user["username"],
            log_data=log_data,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        return {
            "success": True,
            "data": {"log_id": log_id},
            "message": "Operation log created successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to create operation log: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create operation log: {str(e)}"
        )


@router.get("/export/csv")
async def export_logs_csv(
    start_date: str = Query(None, description="start date"),
    end_date: str = Query(None, description="end date"),
    action_type: str = Query(None, description="Operation type"),
    current_user: dict = Depends(get_current_user)
):
    """The export operation log is CSV"""
    try:
        logger.info(f"📤 User {current_user['username']} Export operation log CSV")
        
        service = get_operation_log_service()
        query = OperationLogQuery(
            page=1,
            page_size=10000,  # Get more data when exporting
            start_date=start_date,
            end_date=end_date,
            action_type=action_type
        )
        
        logs, _ = await service.get_logs(query)
        
        # Generate CSV content
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "time", "User", "Operation type", "Operation content", "Status", "Time consuming(ms)", "IP address", "error message"
        ])
        
        # Write data
        for log in logs:
            writer.writerow([
                log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                log.username,
                log.action_type,
                log.action,
                "success" if log.success else "failed",
                log.duration_ms or "",
                log.ip_address or "",
                log.error_message or ""
            ])
        
        output.seek(0)
        
        # Return CSV file
        from datetime import datetime
        filename = f"operation_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Failed to export operation log CSV: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export operation log CSV: {str(e)}"
        )
