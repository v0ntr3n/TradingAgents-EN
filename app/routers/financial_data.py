#!/usr/bin/env python3
"""
Financial Data API Routing
Provide financial data query and synchronization management interface
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from app.routers.auth_db import get_current_user
from app.core.permissions import require_pro
from app.worker.financial_data_sync_service import get_financial_sync_service
from app.services.financial_data_service import get_financial_data_service
from app.core.response import ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/financial-data", tags=["financial data"])


# ==================== request model ====================

class FinancialSyncRequest(BaseModel):
    """Financial data synchronization request"""
    symbols: Optional[List[str]] = Field(None, description="Stock code list, if empty, all stocks will be synchronized.")
    data_sources: Optional[List[str]] = Field(
        ["tushare", "akshare", "baostock"], 
        description="Data source list"
    )
    report_types: Optional[List[str]] = Field(
        ["quarterly"], 
        description="List of report types (quarterly/annual)"
    )
    batch_size: int = Field(50, description="batch size", ge=1, le=200)
    delay_seconds: float = Field(1.0, description="API Call delay seconds", ge=0.1, le=10.0)


class SingleStockSyncRequest(BaseModel):
    """Single stock financial data synchronization request"""
    symbol: str = Field(..., description="Stock code")
    data_sources: Optional[List[str]] = Field(
        ["tushare", "akshare", "baostock"],
        description="Data source list"
    )


class FinancialDataBatchRequest(BaseModel):
    """Batch save financial data requests"""
    symbol: str = Field(..., description="Stock code")
    financial_data: List[Dict[str, Any]] = Field(..., description="Financial data list")
    overwrite: bool = Field(False, description="Whether to overwrite existing data")


# ==================== API endpoint ====================

@router.get("/query/{symbol}", summary="Query stock financial data")
async def query_financial_data(
    symbol: str,
    report_period: Optional[str] = Query(None, description="Reporting period screening (YYYYMMDD)"),
    data_source: Optional[str] = Query(None, description="Data source filtering"),
    report_type: Optional[str] = Query(None, description="Report type filter"),
    limit: Optional[int] = Query(10, description="Limit the number of returns", ge=1, le=100)
) -> dict:
    """
    Query stock financial data
    
    - **symbol**: Stock code (Required)
    - **report_period**: Report period screening, format YYYYMMDD
    - **data_source**: Data source filtering (tushare/akshare/baostock)
    - **report_type**: Report type filter (quarterly/annual)
    - **limit**: Limit the number of returns, default is 10
    """
    try:
        service = await get_financial_data_service()
        
        results = await service.get_financial_data(
            symbol=symbol,
            report_period=report_period,
            data_source=data_source,
            report_type=report_type,
            limit=limit
        )
        
        return ok(data={
                "symbol": symbol,
                "count": len(results),
                "financial_data": results
            },
            message=f"Found {len(results)} financial data"
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to query financial data {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to query financial data: {str(e)}")


@router.get("/latest/{symbol}", summary="Get the latest financial data")
async def get_latest_financial_data(
    symbol: str,
    data_source: Optional[str] = Query(None, description="Data source filtering")
) -> dict:
    """
    Get the latest financial data for a stock
    
    - **symbol**: Stock code (Required)
    - **data_source**: Data source filtering (tushare/akshare/baostock)
    """
    try:
        service = await get_financial_data_service()
        
        result = await service.get_latest_financial_data(
            symbol=symbol,
            data_source=data_source
        )
        
        if result:
            return ok(data=result,
                message="Obtain the latest financial data successfully"
            )
        else:
            return ok(success=False, data=None,
                message="No financial data found"
            )
        
    except Exception as e:
        logger.error(f"❌ Failed to get latest financial data {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get latest financial data: {str(e)}")


@router.get("/statistics", summary="Get financial statistics")
async def get_financial_statistics() -> dict:
    """
    Get financial data statistics
    
    Returns financial data statistics from each data source, including:
    - Total number of records
    - Total number of shares
    - Statistics grouped by data source and report type
    """
    try:
        service = await get_financial_data_service()
        
        stats = await service.get_financial_statistics()
        
        return ok(data=stats,
            message="Obtain financial data statistics successfully"
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to obtain financial data statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to obtain financial data statistics: {str(e)}")


@router.post("/sync/start", summary="Start financial data synchronization")
async def start_financial_sync(
    request: FinancialSyncRequest,
    background_tasks: BackgroundTasks
) -> dict:
    """
    Start financial data synchronization task
    
    Supported configurations:
    - Stock code list (if empty, all stocks will be synchronized)
    - Data source selection
    - Report type selection
    - Batch size and delay settings
    """
    try:
        service = await get_financial_sync_service()
        
        # Perform synchronization tasks in the background
        background_tasks.add_task(
            _execute_financial_sync,
            service,
            request
        )
        
        return ok(data={
                "task_started": True,
                "config": request.dict()
            },
            message="Financial data synchronization task has been started"
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to start financial data synchronization: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start financial data synchronization: {str(e)}")


@router.post("/sync/single", summary="Synchronize financial data of a single stock")
async def sync_single_stock_financial(
    request: SingleStockSyncRequest
) -> dict:
    """
    Synchronize financial data for individual stocks
    
    - **symbol**: Stock code (Required)
    - **data_sources**: Data source list, all data sources are used by default
    """
    try:
        service = await get_financial_sync_service()
        
        results = await service.sync_single_stock(
            symbol=request.symbol,
            data_sources=request.data_sources
        )
        
        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)
        
        return ok(
            success=success_count > 0,
            data={
                "symbol": request.symbol,
                "results": results,
                "success_count": success_count,
                "total_count": total_count
            },
            message=f"Single stock financial data synchronization completed: {success_count}/{total_count} success"
        )
        
    except Exception as e:
        logger.error(f"❌ Single stock financial data synchronization failed {request.symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Single stock financial data synchronization failed: {str(e)}")


@router.get("/sync/statistics", summary="Get sync statistics")
async def get_sync_statistics() -> dict:
    """
    Get financial data synchronization statistics
    
    Returns the synchronization statistics of each data source, including the number of records, number of stocks, etc.
    """
    try:
        service = await get_financial_sync_service()
        
        stats = await service.get_sync_statistics()
        
        return ok(data=stats,
            message="Obtain synchronization statistics successfully"
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to obtain synchronization statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to obtain synchronization statistics: {str(e)}")


@router.get("/health", summary="Financial Data Services Health Check")
async def health_check() -> dict:
    """
    Financial Data Services Health Check
    
    Check service status and database connection
    """
    try:
        # Check service initialization status
        service = await get_financial_data_service()
        sync_service = await get_financial_sync_service()
        
        # Simple database connection test
        stats = await service.get_financial_statistics()
        
        return ok(data={
                "service_status": "healthy",
                "database_connected": True,
                "total_records": stats.get("total_records", 0),
                "total_symbols": stats.get("total_symbols", 0)
            },
            message="The financial data service is running normally"
        )
        
    except Exception as e:
        logger.error(f"❌ Financial Data Service health check failed: {e}")
        return ok(success=False, data={
                "service_status": "unhealthy",
                "error": str(e)
            },
            message="Financial data service exception"
        )


# ==================== Background tasks ====================

async def _execute_financial_sync(
    service: Any,
    request: FinancialSyncRequest
):
    """Perform financial data synchronization background tasks"""
    try:
        logger.info(f"🚀 Start the financial data synchronization task: {request.dict()}")
        
        # Generate task ID (use if task_id is present in the request, otherwise generate a new one)
        import uuid
        task_id = getattr(request, 'task_id', None) or f"financial_sync_{uuid.uuid4().hex[:8]}"
        
        results = await service.sync_financial_data(
            symbols=request.symbols,
            data_sources=request.data_sources,
            report_types=request.report_types,
            batch_size=request.batch_size,
            delay_seconds=request.delay_seconds,
            job_id=task_id  # 🔥 Add job_id for progress tracking
        )
        
        # Statistics overall results
        total_success = sum(stats.success_count for stats in results.values())
        total_symbols = sum(stats.total_symbols for stats in results.values())
        
        logger.info(f"✅ Financial data synchronization task completed: {total_success}/{total_symbols} success")
        
        # Here you can add notification logic, such as sending emails or messages
        
    except Exception as e:
        logger.error(f"❌ Financial data synchronization task execution failed: {e}")


# ==================== Batch import interface ====================

@router.post("/save", response_model=dict, dependencies=[Depends(require_pro)])
async def save_financial_data_batch(
    request: FinancialDataBatchRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Save financial data in batches (optimized version)[PRO]

    Allow users to bulk import financial data via API

    **Permission requirements**: This function is exclusive to advanced students and requires PRO authorization

    Performance optimization:
    - Reduce database round-trips using batch queries
    - Use bulk_write bulk operations
    - Data validation prerequisite

    Args:
        request: Bulk save request with ticker, financial data list, and data source identifier

    Returns:
        dict: {
            "saved": Number of successful saves,
            "updated": Update quantity,
            "skipped": skip quantity,
            "failed": Number of failures,
            "errors": error list
        }
    """
    try:
        from app.core.database import get_mongo_db
        from pymongo import UpdateOne, InsertOne

        db = get_mongo_db()
        collection = db.stock_financial_data

        # Data validation and preprocessing
        valid_data = []
        errors = []
        failed_count = 0

        for idx, fin_data in enumerate(request.financial_data):
            try:
                # Validate required fields
                if "report_period" not in fin_data:
                    errors.append({
                        "index": idx,
                        "error": "Missing required field: report_period"
                    })
                    failed_count += 1
                    continue

                # Verify report_period format (YYYYMMDD)
                report_period = fin_data["report_period"]
                if not (isinstance(report_period, str) and report_period.isdigit() and len(report_period) == 8):
                    errors.append({
                        "index": idx,
                        "report_period": report_period,
                        "error": "report_period Must be an 8-digit number (YYYYMMDD format)"
                    })
                    failed_count += 1
                    continue

                # Add stock code and metadata (fixed use of local as local data identifier)
                fin_data["symbol"] = request.symbol
                fin_data["code"] = request.symbol  # Compatible with old fields
                fin_data["data_source"] = "local"
                fin_data["updated_at"] = datetime.utcnow()

                valid_data.append((idx, fin_data))

            except Exception as e:
                errors.append({
                    "index": idx,
                    "report_period": fin_data.get("report_period", "unknown"),
                    "error": f"Data validation failed: {str(e)}"
                })
                failed_count += 1

        if not valid_data:
            return ok(
                data={
                    "saved": 0,
                    "updated": 0,
                    "skipped": 0,
                    "failed": failed_count,
                    "total": len(request.financial_data),
                    "errors": errors[:10]
                },
                message="All data validation failed"
            )

        # Query existing data in batches
        report_periods = [data["report_period"] for _, data in valid_data]
        existing_docs = await collection.find({
            "symbol": request.symbol,
            "report_period": {"$in": report_periods},
            "data_source": "local"
        }).to_list(length=None)

        existing_periods = {doc["report_period"]: doc for doc in existing_docs}

        # Prepare for batch operations
        bulk_operations = []
        saved_count = 0
        updated_count = 0
        skipped_count = 0

        for idx, fin_data in valid_data:
            report_period = fin_data["report_period"]

            if report_period in existing_periods:
                if request.overwrite:
                    # Batch update
                    fin_data["created_at"] = existing_periods[report_period].get("created_at", datetime.utcnow())
                    bulk_operations.append(
                        UpdateOne(
                            {
                                "symbol": request.symbol,
                                "report_period": report_period,
                                "data_source": "local"
                            },
                            {"$set": fin_data}
                        )
                    )
                    updated_count += 1
                else:
                    # Skip existing data
                    skipped_count += 1
            else:
                # Batch insert
                fin_data["created_at"] = datetime.utcnow()
                bulk_operations.append(InsertOne(fin_data))
                saved_count += 1

        # Perform batch operations
        if bulk_operations:
            try:
                result = await collection.bulk_write(bulk_operations, ordered=False)
                logger.info(f"✅ Batch operation completed: Insert{result.inserted_count}, update{result.modified_count}")
            except Exception as e:
                logger.error(f"❌ Batch operation failed: {e}")
                # If the batch operation fails, fall back to inserting items one by one.
                logger.warning("⚠️ Return to item-by-item operation mode")
                saved_count = 0
                updated_count = 0

                for idx, fin_data in valid_data:
                    try:
                        report_period = fin_data["report_period"]
                        if report_period in existing_periods and request.overwrite:
                            await collection.update_one(
                                {
                                    "symbol": request.symbol,
                                    "report_period": report_period,
                                    "data_source": "local"
                                },
                                {"$set": fin_data}
                            )
                            updated_count += 1
                        elif report_period not in existing_periods:
                            await collection.insert_one(fin_data)
                            saved_count += 1
                    except Exception as e2:
                        errors.append({
                            "index": idx,
                            "report_period": fin_data.get("report_period", "unknown"),
                            "error": str(e2)
                        })
                        failed_count += 1

        return ok(
            data={
                "saved": saved_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "failed": failed_count,
                "total": len(request.financial_data),
                "errors": errors[:10]  # Only return the first 10 errors
            },
            message=f"Batch saving completed: success{saved_count}, update{updated_count}, skip{skipped_count}, failed{failed_count}"
        )

    except Exception as e:
        logger.error(f"❌ Failed to save financial data in batches: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save financial data in batches: {str(e)}"
        )
