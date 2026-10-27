"""
Log management API routing
Provide log query, filtering and export functions
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.routers.auth_db import get_current_user
from app.services.log_export_service import get_log_export_service

router = APIRouter(prefix="/system-logs", tags=["System log"])
logger = logging.getLogger("webapi")


# request model
class LogReadRequest(BaseModel):
    """Log read request"""
    filename: str = Field(..., description="Log file name")
    lines: int = Field(default=1000, ge=1, le=10000, description="Number of lines read")
    level: Optional[str] = Field(default=None, description="Log level filtering")
    keyword: Optional[str] = Field(default=None, description="keyword filter")
    start_time: Optional[str] = Field(default=None, description="Start time (ISO format)")
    end_time: Optional[str] = Field(default=None, description="End time (ISO format)")


class LogExportRequest(BaseModel):
    """Log export request"""
    filenames: Optional[List[str]] = Field(default=None, description="List of file names to export (empty means all)")
    level: Optional[str] = Field(default=None, description="Log level filtering")
    start_time: Optional[str] = Field(default=None, description="Start time (ISO format)")
    end_time: Optional[str] = Field(default=None, description="End time (ISO format)")
    format: str = Field(default="zip", description="Export format:zip, txt")


# response model
class LogFileInfo(BaseModel):
    """Log file information"""
    name: str
    path: str
    size: int
    size_mb: float
    modified_at: str
    type: str


class LogContentResponse(BaseModel):
    """Log content response"""
    filename: str
    lines: List[str]
    stats: dict


class LogStatisticsResponse(BaseModel):
    """Log statistics response"""
    total_files: int
    total_size_mb: float
    error_files: int
    recent_errors: List[str]
    log_types: dict


@router.get("/files", response_model=List[LogFileInfo])
async def list_log_files(
    current_user: dict = Depends(get_current_user)
):
    """
    Get a list of all log files
    
    Returns the basic information of the log file, including file name, size, modification time, etc.
    """
    try:
        logger.info(f"📋 User {current_user['username']} Query log file list")
        
        service = get_log_export_service()
        files = service.list_log_files()
        
        return files
        
    except Exception as e:
        logger.error(f"❌ Failed to get log file list: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get log file list: {str(e)}")


@router.post("/read", response_model=LogContentResponse)
async def read_log_file(
    request: LogReadRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Read log file contents
    
    Support filter conditions:
    - lines: Number of lines read (starting from the end)
    - level: log level (ERROR, WARNING, INFO, DEBUG) 
    - keyword: keyword search
    - start_time/end_time: time range
    """
    try:
        logger.info(f"📖 User {current_user['username']} Read log file: {request.filename}")
        
        service = get_log_export_service()
        content = service.read_log_file(
            filename=request.filename,
            lines=request.lines,
            level=request.level,
            keyword=request.keyword,
            start_time=request.start_time,
            end_time=request.end_time
        )
        
        return content
        
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Failed to read log file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read log file: {str(e)}")


@router.post("/export")
async def export_logs(
    request: LogExportRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Export log file
    
    Supported export formats:
    - zip: Compressed package (recommended)
    - txt: merged text files
    
    Support filter conditions:
    - filenames: Specify the file to export
    - level: Log level filtering
    - start_time/end_time: time range filter
    """
    try:
        logger.info(f"📤 User {current_user['username']} Export log file")
        
        service = get_log_export_service()
        export_path = service.export_logs(
            filenames=request.filenames,
            level=request.level,
            start_time=request.start_time,
            end_time=request.end_time,
            format=request.format
        )
        
        # Return to file download
        import os
        filename = os.path.basename(export_path)
        media_type = "application/zip" if request.format == "zip" else "text/plain"
        
        return FileResponse(
            path=export_path,
            filename=filename,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Failed to export log file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export log file: {str(e)}")


@router.get("/statistics", response_model=LogStatisticsResponse)
async def get_log_statistics(
    days: int = Query(default=7, ge=1, le=30, description="Statistics of logs in recent days"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get log statistics
    
    Returns log statistics for the last N days, including:
    - Number of files and total size
    - Number of error logs
    - Recent error messages
    - Log type distribution
    """
    try:
        logger.info(f"📊 User {current_user['username']} Query log statistics")
        
        service = get_log_export_service()
        stats = service.get_log_statistics(days=days)
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ Failed to obtain log statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to obtain log statistics: {str(e)}")


@router.delete("/files/{filename}")
async def delete_log_file(
    filename: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete log files
    
    Note: This operation is not reversible, please use it with caution
    """
    try:
        logger.warning(f"🗑️ User {current_user['username']} Delete log files: {filename}")
        
        service = get_log_export_service()
        file_path = service.log_dir / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Log file does not exist")
        
        # Security check: only allow deletion of .log files
        if not filename.endswith('.log') and not '.log.' in filename:
            raise HTTPException(status_code=400, detail="Only log files can be deleted")
        
        file_path.unlink()
        
        return {
            "success": True,
            "message": f"Log file deleted: {filename}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete log file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete log file: {str(e)}")

