"""
Multi-source synchronization API routes
Provides endpoints for multi-source stock data synchronization
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.multi_source_basics_sync_service import get_multi_source_sync_service
from app.services.data_sources.manager import DataSourceManager

logger = logging.getLogger(__name__)

DATA_SOURCE_STATUS_TIMEOUT_SECONDS = 8

router = APIRouter(prefix="/api/sync/multi-source", tags=["Multi-Source Sync"])


async def _get_available_adapters_async(manager: DataSourceManager):
    return await asyncio.wait_for(
        asyncio.to_thread(manager.get_available_adapters),
        timeout=DATA_SOURCE_STATUS_TIMEOUT_SECONDS,
    )


class SyncRequest(BaseModel):
    """Synchronous request model"""
    force: bool = False
    preferred_sources: Optional[List[str]] = None


class SyncResponse(BaseModel):
    """Synchronous response model"""
    success: bool
    message: str
    data: Union[Dict[str, Any], List[Any], Any]


class DataSourceStatus(BaseModel):
    """Data source state model"""
    name: str
    priority: int
    available: bool
    description: str


@router.get("/sources/status")
async def get_data_sources_status():
    """Get the status of all data sources"""
    try:
        manager = DataSourceManager()
        available_adapters = await _get_available_adapters_async(manager)
        all_adapters = manager.adapters

        status_list = []
        for adapter in all_adapters:
            is_available = adapter in available_adapters

            # Provide description based on data source type
            descriptions = {
                "tushare": "Professional financial data API, providing high-quality A-share data and financial indicators",
                "akshare": "Open source financial database, providing basic stock information",
                "baostock": "Free and open source securities data platform, providing historical data"
            }

            status_item = {
                "name": adapter.name,
                "priority": adapter.priority,
                "available": is_available,
                "description": descriptions.get(adapter.name, f"{adapter.name}data source")
            }

            # Add Token source information (Tushare only)
            if adapter.name == "tushare" and is_available and hasattr(adapter, 'get_token_source'):
                token_source = adapter.get_token_source()
                if token_source:
                    status_item["token_source"] = token_source
                    if token_source == 'database':
                        status_item["description"] += " (Token Source: database)"
                    elif token_source == 'env':
                        status_item["description"] += " (Token Source: .env)"

            status_list.append(status_item)

        return SyncResponse(
            success=True,
            message="Data sources status retrieved successfully",
            data=status_list
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get data sources status: {str(e)}")


@router.get("/sources/current")
async def get_current_data_source():
    """Get the data source currently in use (the one with the highest priority and available)"""
    try:
        manager = DataSourceManager()
        available_adapters = await _get_available_adapters_async(manager)

        if not available_adapters:
            return SyncResponse(
                success=False,
                message="No available data sources",
                data={"name": None, "priority": None}
            )

        # Get the highest priority available data source (the higher the priority number, the higher)
        current_adapter = max(available_adapters, key=lambda x: x.priority)

        # Provide description based on data source type
        descriptions = {
            "tushare": "Professional financial data API",
            "akshare": "Open source financial database",
            "baostock": "Free securities data platform"
        }

        result = {
            "name": current_adapter.name,
            "priority": current_adapter.priority,
            "description": descriptions.get(current_adapter.name, current_adapter.name)
        }

        # Add Token source information (Tushare only)
        if current_adapter.name == "tushare" and hasattr(current_adapter, 'get_token_source'):
            token_source = current_adapter.get_token_source()
            if token_source:
                result["token_source"] = token_source
                if token_source == 'database':
                    result["token_source_display"] = "Database configuration"
                elif token_source == 'env':
                    result["token_source_display"] = ".env Configuration"

        return SyncResponse(
            success=True,
            message="Current data source retrieved successfully",
            data=result
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get current data source: {str(e)}")


@router.get("/status")
async def get_sync_status():
    """Get synchronization status of multiple data sources"""
    try:
        service = get_multi_source_sync_service()
        status = await service.get_status()
        
        return SyncResponse(
            success=True,
            message="Status retrieved successfully",
            data=status
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get sync status: {str(e)}")


@router.post("/stock_basics/run")
async def run_stock_basics_sync(
    force: bool = Query(False, description="Whether to force synchronization to run"),
    preferred_sources: Optional[str] = Query(None, description="Preferred data sources, separated by commas")
):
    """Run multi-data source stock basic information synchronization"""
    try:
        service = get_multi_source_sync_service()

        # Parse priority data sources
        sources_list = None
        if preferred_sources and isinstance(preferred_sources, str):
            sources_list = [s.strip() for s in preferred_sources.split(",") if s.strip()]

        # Change to background execution to avoid long-term blocking of front-end requests
        result = await service.start_background_sync(force=force, preferred_sources=sources_list)

        success = result.get("status") in ["queued", "running", "success", "success_with_errors"]
        message = "Synchronization task accepted"

        if result.get("launch_mode") == "already_running":
            message = result.get("message") or "Synchronization is already running"
        elif result.get("status") == "queued":
            message = result.get("message") or "Synchronization started in background"

        return SyncResponse(
            success=success,
            message=message,
            data=result
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run synchronization: {str(e)}")


async def _test_single_adapter(adapter) -> dict:
    """
    Test connectivity for a single data source adapter
    Only perform lightweight connectivity tests without obtaining complete data
    """
    result = {
        "name": adapter.name,
        "priority": adapter.priority,
        "available": False,
        "message": "Connection failed"
    }

    # Connectivity test timeout (seconds)
    test_timeout = 10

    try:
        # Test connectivity - force reconnect to use latest configuration
        logger.info(f"🧪 test {adapter.name} connectivity (timeout: {test_timeout}seconds)...")

        try:
            # For Tushare, force reconnect to use latest database configuration
            if adapter.name == "tushare" and hasattr(adapter, '_provider'):
                logger.info(f"🔄 force {adapter.name} Reconnect to use latest configuration...")
                provider = adapter._provider
                if provider:
                    # Reset connection status
                    provider.connected = False
                    provider.token_source = None
                    # Reconnect
                    await asyncio.wait_for(
                        asyncio.to_thread(provider.connect_sync),
                        timeout=test_timeout
                    )

            # Run in thread pool is_available() Check
            is_available = await asyncio.wait_for(
                asyncio.to_thread(adapter.is_available),
                timeout=test_timeout
            )

            if is_available:
                result["available"] = True

                # Get Token source (Tushare only)
                token_source = None
                if adapter.name == "tushare" and hasattr(adapter, 'get_token_source'):
                    token_source = adapter.get_token_source()

                if token_source == 'database':
                    result["message"] = "✅ Connection successful (Token Source: database)"
                    result["token_source"] = "database"
                elif token_source == 'env':
                    result["message"] = "✅ Connection successful (Token Source: .env)"
                    result["token_source"] = "env"
                else:
                    result["message"] = "✅ Connection successful"

                logger.info(f"✅ {adapter.name} Connectivity test successful, Token source: {token_source}")
            else:
                result["available"] = False
                result["message"] = "❌ Data source is not available"
                logger.warning(f"⚠️ {adapter.name} Not available")
        except asyncio.TimeoutError:
            result["available"] = False
            result["message"] = f"❌ Connection timeout ({test_timeout}seconds)"
            logger.warning(f"⚠️ {adapter.name} Connection timeout")
        except Exception as e:
            result["available"] = False
            result["message"] = f"❌ Connection failed: {str(e)}"
            logger.error(f"❌ {adapter.name} Connection failed: {e}")

    except Exception as e:
        result["available"] = False
        result["message"] = f"❌ Test exception: {str(e)}"
        logger.error(f"❌ test {adapter.name} error: {e}")

    return result


class TestSourceRequest(BaseModel):
    """Test data source request"""
    source_name: str | None = None


@router.post("/test-sources")
async def test_data_sources(request: TestSourceRequest = TestSourceRequest()):
    """
    Test connectivity to data sources

    parameters:
    - source_name: Optionally, specify the name of the data source to test. If not specified, all data sources are tested

    Only perform lightweight connectivity tests without obtaining complete data
    - test timeout: 10 seconds
    - Only obtain 1 data verification connection
    - Return results quickly
    """
    try:
        manager = DataSourceManager()
        all_adapters = manager.adapters

        # Get the data source name from the request body
        source_name = request.source_name
        logger.info(f"📥 Test request received,source_name={source_name}")

        # If a data source name is specified, only that data source is tested
        if source_name:
            adapters_to_test = [a for a in all_adapters if a.name.lower() == source_name.lower()]
            if not adapters_to_test:
                raise HTTPException(
                    status_code=400,
                    detail=f"Data source '{source_name}' not found"
                )
            logger.info(f"🧪 Start testing the data source: {source_name}")
        else:
            adapters_to_test = all_adapters
            logger.info(f"🧪 Start testing {len(all_adapters)} data source connectivity...")

        # Concurrent test adapter (executes in background thread)
        test_tasks = [_test_single_adapter(adapter) for adapter in adapters_to_test]
        test_results = await asyncio.gather(*test_tasks, return_exceptions=True)

        # Handle abnormal results
        final_results = []
        for i, result in enumerate(test_results):
            if isinstance(result, Exception):
                logger.error(f"❌ test adapter {adapters_to_test[i].name} error: {result}")
                final_results.append({
                    "name": adapters_to_test[i].name,
                    "priority": adapters_to_test[i].priority,
                    "available": False,
                    "message": f"❌ Test exception: {str(result)}"
                })
            else:
                final_results.append(result)

        # Statistical results
        available_count = sum(1 for r in final_results if r.get("available"))
        if source_name:
            logger.info(f"✅ data source {source_name} Test completed: {'Available' if available_count > 0 else 'Not available'}")
        else:
            logger.info(f"✅ Data source connectivity test completed: {available_count}/{len(final_results)} Available")

        return SyncResponse(
            success=True,
            message=f"Tested {len(final_results)} data sources, {available_count} available",
            data={"test_results": final_results}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error while testing data source: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to test data sources: {str(e)}")


@router.get("/recommendations")
async def get_sync_recommendations():
    """Get data source usage suggestions"""
    try:
        manager = DataSourceManager()
        available_adapters = await _get_available_adapters_async(manager)
        
        recommendations = {
            "primary_source": None,
            "fallback_sources": [],
            "suggestions": [],
            "warnings": []
        }
        
        if available_adapters:
            # Recommend the highest priority available data source as the primary data source
            primary = available_adapters[0]
            recommendations["primary_source"] = {
                "name": primary.name,
                "priority": primary.priority,
                "reason": "Highest priority available data source"
            }
            
            # Other available data sources as backup
            for adapter in available_adapters[1:]:
                recommendations["fallback_sources"].append({
                    "name": adapter.name,
                    "priority": adapter.priority
                })
        
        # Generate suggestions
        if not available_adapters:
            recommendations["warnings"].append("No data sources are available. Please check your configuration.")
        elif len(available_adapters) == 1:
            recommendations["suggestions"].append("Consider configuring additional data sources for redundancy.")
        else:
            recommendations["suggestions"].append(f"You have {len(available_adapters)} data sources available, which provides good redundancy.")
        
        # Recommendations for specific data sources
        tushare_available = any(a.name == "tushare" for a in available_adapters)
        if not tushare_available:
            recommendations["suggestions"].append("Consider configuring Tushare for the most comprehensive financial data.")
        
        return SyncResponse(
            success=True,
            message="Recommendations generated successfully",
            data=recommendations
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {str(e)}")


@router.get("/history")
async def get_sync_history(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="page size"),
    status: Optional[str] = Query(None, description="status filter")
):
    """Get sync history"""
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()

        # Build query conditions
        query = {"job": "stock_basics_multi_source"}
        if status:
            query["status"] = status

        # Count the number of skipped records
        skip = (page - 1) * page_size

        # Query history
        cursor = db.sync_status.find(query).sort("started_at", -1).skip(skip).limit(page_size)
        history_records = await cursor.to_list(length=page_size)

        # Get total
        total = await db.sync_status.count_documents(query)

        # Clean _id field in record
        for record in history_records:
            record.pop("_id", None)

        return SyncResponse(
            success=True,
            message="History retrieved successfully",
            data={
                "records": history_records,
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_more": skip + len(history_records) < total
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get sync history: {str(e)}")


@router.delete("/cache")
async def clear_sync_cache():
    """Clear synchronization related cache"""
    try:
        service = get_multi_source_sync_service()

        # Clear sync status cache
        cleared_items = 0

        # 1. Clear sync status
        try:
            from app.core.database import get_mongo_db
            db = get_mongo_db()

            # Delete sync status record
            result = await db.sync_status.delete_many({"job": "stock_basics_multi_source"})
            cleared_items += result.deleted_count

            # Reset service status
            service._running = False

        except Exception as e:
            logger.warning(f"Failed to clear sync status cache: {e}")

        # 2. Clear the data source cache (if any)
        try:
            manager = DataSourceManager()
            # Here you can add data source specific cache cleaning logic
            # Currently the data source adapter does not have a persistent cache, so skip
        except Exception as e:
            logger.warning(f"Failed to clear data source cache: {e}")

        return SyncResponse(
            success=True,
            message=f"Cache cleared successfully, {cleared_items} items removed",
            data={"cleared": True, "items_cleared": cleared_items}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")
