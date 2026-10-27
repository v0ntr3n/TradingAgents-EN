"""
Cache management routing
Provides cache statistics, cleaning and other functions
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from datetime import datetime, timedelta

from app.routers.auth_db import get_current_user
from app.core.response import ok
from tradingagents.utils.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/cache", tags=["cache"])


@router.get("/stats")
async def get_cache_stats(current_user: dict = Depends(get_current_user)):
    """
    Get cache statistics
    
    Returns:
        dict: cache statistics
    """
    try:
        from tradingagents.dataflows.cache import get_cache
        
        cache = get_cache()
        
        # Get cache statistics
        stats = cache.get_cache_stats()
        
        logger.info(f"User {current_user['username']} Get cache statistics")
        
        return ok(
            data={
                "totalFiles": stats.get('total_files', 0),
                "totalSize": stats.get('total_size', 0),  # Bytes
                "maxSize": 1024 * 1024 * 1024,  # 1GB
                "stockDataCount": stats.get('stock_data_count', 0),
                "newsDataCount": stats.get('news_count', 0),
                "analysisDataCount": stats.get('fundamentals_count', 0)
            },
            message="Obtain cache statistics successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to obtain cache statistics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to obtain cache statistics: {str(e)}"
        )


@router.delete("/cleanup")
async def cleanup_old_cache(
    days: int = Query(7, ge=1, le=30, description="How many days old cache should be cleared?"),
    current_user: dict = Depends(get_current_user)
):
    """
    Clear expired cache
    
    Args:
        days: How many days old cache should be cleared?
        
    Returns:
        dict: Clean results
    """
    try:
        from tradingagents.dataflows.cache import get_cache
        
        cache = get_cache()
        
        # Clear expired cache
        cache.clear_old_cache(days)
        
        logger.info(f"User {current_user['username']} Cleaned up {days} Cache days ago")
        
        return ok(
            data={"days": days},
            message=f"Cleaned {days} Cache days ago"
        )
        
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear cache: {str(e)}"
        )


@router.delete("/clear")
async def clear_all_cache(current_user: dict = Depends(get_current_user)):
    """
    Clear all cache

    Returns:
        dict: Clean results
    """
    try:
        from tradingagents.dataflows.cache import get_cache

        cache = get_cache()

        # Clear all caches (clear all expired and unexpired caches)
        # Use clear_old_cache(0) to clear all caches
        cache.clear_old_cache(0)

        logger.warning(f"User {current_user['username']} Cleared all cache")

        return ok(
            data={},
            message="All caches have been cleared"
        )

    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear cache: {str(e)}"
        )


@router.get("/details")
async def get_cache_details(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Quantity per page"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get cache details list
    
    Args:
        page: Page number
        page_size: Quantity per page
        
    Returns:
        dict: Cache details list
    """
    try:
        from tradingagents.dataflows.cache import get_cache
        
        cache = get_cache()
        
        # Get cache details
        # Note: This method may need to be implemented in the cache class
        try:
            details = cache.get_cache_details(page=page, page_size=page_size)
        except AttributeError:
            # If the cache class does not implement this method, an empty list is returned.
            details = {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size
            }
        
        logger.info(f"User {current_user['username']} Get cache details (Page number: {page})")
        
        return ok(
            data=details,
            message="Obtain cache details successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to get cache details: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get cache details: {str(e)}"
        )


@router.get("/backend-info")
async def get_cache_backend_info(current_user: dict = Depends(get_current_user)):
    """
    Get cache backend information
    
    Returns:
        dict: Cache backend configuration information
    """
    try:
        from tradingagents.dataflows.cache import get_cache
        
        cache = get_cache()
        
        # Get backend information
        try:
            backend_info = cache.get_cache_backend_info()
        except AttributeError:
            # If the cache class does not implement this method, basic information is returned.
            backend_info = {
                "system": "file",
                "primary_backend": "file",
                "fallback_enabled": False
            }
        
        logger.info(f"User {current_user['username']} Get cache backend information")
        
        return ok(
            data=backend_info,
            message="Obtain cache backend information successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to obtain cache backend information: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to obtain cache backend information: {str(e)}"
        )

