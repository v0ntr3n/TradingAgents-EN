"""
Database management API routing
"""

import logging
import json
import os
from datetime import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.routers.auth_db import get_current_user
from app.core.database import get_mongo_db, get_redis_client
from app.services.database_service import DatabaseService

router = APIRouter(prefix="/database", tags=["Database management"])
logger = logging.getLogger("webapi")

# request model
class BackupRequest(BaseModel):
    """Backup request"""
    name: str
    collections: List[str] = []  # An empty list means backing up all collections

class ImportRequest(BaseModel):
    """import request"""
    collection: str
    format: str = "json"  # json, csv
    overwrite: bool = False

class ExportRequest(BaseModel):
    """Export request"""
    collections: List[str] = []  # An empty list means exporting all collections
    format: str = "json"  # json, csv
    sanitize: bool = False  # Whether to desensitize (clear sensitive fields, used for demonstration system)

# response model
class DatabaseStatusResponse(BaseModel):
    """Database status response"""
    mongodb: Dict[str, Any]
    redis: Dict[str, Any]

class DatabaseStatsResponse(BaseModel):
    """Database statistics response"""
    total_collections: int
    total_documents: int
    total_size: int
    collections: List[Dict[str, Any]]

class BackupResponse(BaseModel):
    """Backup response"""
    id: str
    name: str
    size: int
    created_at: str
    collections: List[str]

# Database service instance
database_service = DatabaseService()

@router.get("/status")
async def get_database_status(
    current_user: dict = Depends(get_current_user)
):
    """Get database connection status"""
    try:
        logger.info(f"🔍 User {current_user['username']} Request database status")
        status_info = await database_service.get_database_status()
        return {
            "success": True,
            "message": "Obtaining database status successfully",
            "data": status_info
        }
    except Exception as e:
        logger.error(f"Failed to get database status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get database status: {str(e)}"
        )

@router.get("/stats")
async def get_database_stats(
    current_user: dict = Depends(get_current_user)
):
    """Get database statistics"""
    try:
        logger.info(f"📊 User {current_user['username']} Request database statistics")
        stats = await database_service.get_database_stats()
        return {
            "success": True,
            "message": "Obtaining database statistics successfully",
            "data": stats
        }
    except Exception as e:
        logger.error(f"Failed to obtain database statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain database statistics: {str(e)}"
        )

@router.get("/connection-info")
async def get_connection_info(
    current_user: dict = Depends(get_current_user)
):
    """Get MongoDB connection information (used to generate backup/restore commands)"""
    try:
        from app.core.config import settings
        from pathlib import Path
        import os
        
        logger.info(f"🔗 User {current_user['username']} Request MongoDB connection information")
        
        # Get MongoDB URI and database name
        mongo_uri = settings.MONGO_URI
        database_name = settings.MONGODB_DATABASE
        
        # For security, return a URI for display (hidden password)
        display_uri = mongo_uri
        if settings.MONGODB_USERNAME and settings.MONGODB_PASSWORD:
            # Hide password and only show username
            display_uri = mongo_uri.replace(
                f":{settings.MONGODB_PASSWORD}@",
                ":****@"
            )
        
        # Get the application installation directory (project root directory)
        # Method 1: Search upward from the current file to find the directory containing .env or pyproject.toml
        current_file = Path(__file__).resolve()
        # app/routers/database.py -> app/routers -> app -> project_root
        project_root = current_file.parent.parent.parent
        
        # Verify it is the project root directory (check if there is .env or pyproject.toml)
        if not (project_root / ".env").exists() and not (project_root / "pyproject.toml").exists():
            # Method 2: Try to get from the current working directory
            project_root = Path.cwd()
            if not (project_root / ".env").exists() and not (project_root / "pyproject.toml").exists():
                # Method 3: Infer from data directory
                if settings.TRADINGAGENTS_DATA_DIR:
                    data_dir = Path(settings.TRADINGAGENTS_DATA_DIR).resolve()
                    if data_dir.exists():
                        # data The directory is usually the data subdirectory under the project root directory
                        project_root = data_dir.parent
                        # Verify inferred directories
                        if not (project_root / ".env").exists() and not (project_root / "pyproject.toml").exists():
                            # If still not found, use the parent directory of the directory where the current file is located.
                            project_root = current_file.parent.parent.parent
        
        # Convert to absolute path string
        install_dir = str(project_root.resolve())
        
        logger.debug(f"📁 Application installation directory: {install_dir}")
        
        return {
            "success": True,
            "message": "Obtained connection information successfully",
            "data": {
                "mongo_uri": mongo_uri,  # Full URI (for command execution)
                "display_uri": display_uri,  # Display URI (hide password)
                "database_name": database_name,
                "host": settings.MONGODB_HOST,
                "port": settings.MONGODB_PORT,
                "has_auth": bool(settings.MONGODB_USERNAME and settings.MONGODB_PASSWORD),
                "install_dir": install_dir  # Application installation directory (project root directory)
            }
        }
    except Exception as e:
        logger.error(f"Failed to obtain connection information: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain connection information: {str(e)}"
        )

@router.post("/test")
async def test_database_connections(
    current_user: dict = Depends(get_current_user)
):
    """Test database connection"""
    try:
        logger.info(f"🧪 User {current_user['username']} Test database connection")
        results = await database_service.test_connections()
        return {
            "success": True,
            "message": "Database connection test completed",
            "data": results
        }
    except Exception as e:
        logger.error(f"Test database connection failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test database connection failed: {str(e)}"
        )

@router.post("/backup")
async def create_backup(
    request: BackupRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a database backup"""
    try:
        logger.info(f"💾 User {current_user['username']} Create backup: {request.name}")
        backup_info = await database_service.create_backup(
            name=request.name,
            collections=request.collections,
            user_id=current_user['id']
        )
        return {
            "success": True,
            "message": "Backup created successfully",
            "data": backup_info
        }
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create backup: {str(e)}"
        )

@router.get("/backups")
async def list_backups(
    current_user: dict = Depends(get_current_user)
):
    """Get backup list"""
    try:
        logger.info(f"📋 User {current_user['username']} Get backup list")
        backups = await database_service.list_backups()
        return {
            "success": True,
            "data": backups
        }
    except Exception as e:
        logger.error(f"Failed to get backup list: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get backup list: {str(e)}"
        )

@router.post("/import")
async def import_data(
    file: UploadFile = File(...),
    collection: str = "imported_data",
    format: str = "json",
    overwrite: bool = False,
    current_user: dict = Depends(get_current_user)
):
    """Import data"""
    try:
        logger.info(f"📥 User {current_user['username']} Import data into a collection: {collection}")
        logger.info(f"   file name: {file.filename}")
        
        # Read file contents
        content = await file.read()
        logger.info(f"   file size: {len(content)} Bytes")
        
        # Automatically detect file types (prefer filename extension, otherwise check file content)
        detected_format = format
        if file.filename:
            file_ext = os.path.splitext(file.filename)[1].lower()
            if file_ext == '.zip':
                detected_format = 'json'  # ZIP Inside the file is JSON
                logger.info(f"   ZIP file detected, will be automatically decompressed")
            elif file_ext == '.json':
                detected_format = 'json'
        
        logger.info(f"   Format: {detected_format}")
        logger.info(f"   overlay mode: {overwrite}")

        result = await database_service.import_data(
            content=content,
            collection=collection,
            format=detected_format,
            overwrite=overwrite,
            filename=file.filename
        )

        logger.info(f"✅ Import successful: {result}")

        return {
            "success": True,
            "message": "Data import successful",
            "data": result
        }
    except Exception as e:
        logger.error(f"❌ Import data failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import data failed: {str(e)}"
        )

@router.post("/export")
async def export_data(
    request: ExportRequest,
    current_user: dict = Depends(get_current_user)
):
    """Export data"""
    try:
        sanitize_info = " (desensitization mode)" if request.sanitize else ""
        logger.info(f"📤 User {current_user['username']} Export data{sanitize_info}")

        file_path = await database_service.export_data(
            collections=request.collections,
            format=request.format,
            sanitize=request.sanitize
        )

        # Check the file extension and set the correct one media_type
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext == '.zip':
            media_type = 'application/zip'
        elif file_ext == '.json':
            media_type = 'application/json'
        elif file_ext == '.csv':
            media_type = 'text/csv'
        elif file_ext in ['.xlsx', '.xls']:
            media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            media_type = 'application/octet-stream'
        
        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type=media_type
        )
    except Exception as e:
        logger.error(f"Failed to export data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export data: {str(e)}"
        )

@router.delete("/backups/{backup_id}")
async def delete_backup(
    backup_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete backup"""
    try:
        logger.info(f"🗑️ User {current_user['username']} Delete backup: {backup_id}")
        await database_service.delete_backup(backup_id)
        return {
            "success": True,
            "message": "Backup deleted successfully"
        }
    except Exception as e:
        logger.error(f"Failed to delete backup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete backup: {str(e)}"
        )

@router.post("/cleanup")
async def cleanup_old_data(
    days: int = 30,
    current_user: dict = Depends(get_current_user)
):
    """Clean old data"""
    try:
        logger.info(f"🧹 User {current_user['username']} clean up {days} Data from days ago")
        result = await database_service.cleanup_old_data(days)
        return {
            "success": True,
            "message": f"Cleanup completed, deleted {result['deleted_count']} records",
            "data": result
        }
    except Exception as e:
        logger.error(f"Cleaning data failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cleaning data failed: {str(e)}"
        )

@router.post("/cleanup/analysis")
async def cleanup_analysis_results(
    days: int = 30,
    current_user: dict = Depends(get_current_user)
):
    """Clean up expired analysis results"""
    try:
        logger.info(f"🧹 User {current_user['username']} clean up {days} Analysis results from days ago")
        result = await database_service.cleanup_analysis_results(days)
        return {
            "success": True,
            "message": f"The analysis results have been cleaned and deleted. {result['deleted_count']} records",
            "data": result
        }
    except Exception as e:
        logger.error(f"Failed to clean up analysis results: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clean up analysis results: {str(e)}"
        )

@router.post("/cleanup/logs")
async def cleanup_operation_logs(
    days: int = 90,
    current_user: dict = Depends(get_current_user)
):
    """Clean operation log"""
    try:
        logger.info(f"🧹 User {current_user['username']} clean up {days} Operation log from days ago")
        result = await database_service.cleanup_operation_logs(days)
        return {
            "success": True,
            "message": f"The operation log has been cleaned and deleted. {result['deleted_count']} records",
            "data": result
        }
    except Exception as e:
        logger.error(f"Failed to clear operation log: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear operation log: {str(e)}"
        )
