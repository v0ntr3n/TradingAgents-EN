"""
Stock Data API Routing - Based on Extended Data Model
Provide standardized stock data access interface
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status
from pydantic import BaseModel, Field

from app.routers.auth_db import get_current_user
from app.core.permissions import require_pro
from app.services.stock_data_service import get_stock_data_service
from app.models import (
    StockBasicInfoResponse,
    MarketQuotesResponse,
    StockListResponse,
    StockBasicInfoExtended,
    MarketQuotesExtended,
    MarketType
)
from app.core.response import ok

router = APIRouter(prefix="/api/stock-data", tags=["stock data"])


# ==================== Batch import request model ====================

class StockBasicInfoBatchRequest(BaseModel):
    """Save basic stock information requests in batches"""
    stocks: List[Dict[str, Any]] = Field(..., description="List of basic stock information")
    overwrite: bool = Field(False, description="Whether to overwrite existing data")


class MarketQuotesBatchRequest(BaseModel):
    """Save real-time quotation requests in batches"""
    quotes: List[Dict[str, Any]] = Field(..., description="Market data list")
    overwrite: bool = Field(True, description="Whether to overwrite existing data (the market overwrites it by default)")


# ==================== Query interface ====================

@router.get("/basic-info/{symbol}", response_model=StockBasicInfoResponse)
async def get_stock_basic_info(
    symbol: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get basic stock information

    Args:
        symbol: Stock code (Supports 6-digit A-share code)

    Returns:
        StockBasicInfoResponse: Basic stock information including extended fields
    """
    try:
        service = get_stock_data_service()
        stock_info = await service.get_stock_basic_info(symbol)

        if not stock_info:
            return StockBasicInfoResponse(
                success=False,
                message=f"Stock symbol not found {symbol} basic information"
            )

        return StockBasicInfoResponse(
            success=True,
            data=stock_info,
            message="get success"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain basic stock information: {str(e)}"
        )


@router.get("/quotes/{symbol}", response_model=MarketQuotesResponse)
async def get_market_quotes(
    symbol: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get real-time market data

    Args:
        symbol: Stock code (Supports 6-digit A-share code)

    Returns:
        MarketQuotesResponse: Real-time market data including extended fields
    """
    try:
        service = get_stock_data_service()
        quotes = await service.get_market_quotes(symbol)

        if not quotes:
            return MarketQuotesResponse(
                success=False,
                message=f"Stock symbol not found {symbol} market data"
            )

        return MarketQuotesResponse(
            success=True,
            data=quotes,
            message="get success"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain real-time quotes: {str(e)}"
        )


@router.get("/list", response_model=StockListResponse)
async def get_stock_list(
    market: Optional[str] = Query(None, description="Market screening"),
    industry: Optional[str] = Query(None, description="Industry screening"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="page size"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a list of stocks
    
    Args:
        market: Market screening (Optional)
        industry: Industry screening (Optional)
        page: Page number (Start from 1)
        page_size: page size (1-100)
        
    Returns:
        StockListResponse: Stock list data
    """
    try:
        service = get_stock_data_service()
        stock_list = await service.get_stock_list(
            market=market,
            industry=industry,
            page=page,
            page_size=page_size
        )
        
        # Calculate the total (Simplify the implementation, in fact it should be queried separately)
        total = len(stock_list)
        
        return StockListResponse(
            success=True,
            data=stock_list,
            total=total,
            page=page,
            page_size=page_size,
            message="get success"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stock list: {str(e)}"
        )


@router.get("/combined/{symbol}")
async def get_combined_stock_data(
    symbol: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get comprehensive stock data (Basic information + Real-time quotes)

    Args:
        symbol: Stock code

    Returns:
        dict: Comprehensive data including basic information and real-time market conditions
    """
    try:
        service = get_stock_data_service()

        # Obtain basic information and market data in parallel
        import asyncio
        basic_info_task = service.get_stock_basic_info(symbol)
        quotes_task = service.get_market_quotes(symbol)

        basic_info, quotes = await asyncio.gather(
            basic_info_task,
            quotes_task,
            return_exceptions=True
        )

        # Handle exceptions
        if isinstance(basic_info, Exception):
            basic_info = None
        if isinstance(quotes, Exception):
            quotes = None

        if not basic_info and not quotes:
            return {
                "success": False,
                "message": f"Stock symbol not found {symbol} any data of"
            }

        return {
            "success": True,
            "data": {
                "basic_info": basic_info.dict() if basic_info else None,
                "quotes": quotes.dict() if quotes else None,
                "symbol": symbol,
                "timestamp": quotes.updated_at if quotes else None
            },
            "message": "get success"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain comprehensive stock data: {str(e)}"
        )


@router.get("/search")
async def search_stocks(
    keyword: str = Query(..., min_length=1, description="Search keywords"),
    limit: int = Query(10, ge=1, le=50, description="Return quantity limit"),
    current_user: dict = Depends(get_current_user)
):
    """
    Search stocks
    
    Args:
        keyword: Search keywords (Stock code or name)
        limit: Return quantity limit
        
    Returns:
        dict: Search results
    """
    try:
        from app.core.database import get_mongo_db
        from app.core.data_source_priority import get_preferred_data_source_async

        db = get_mongo_db()
        collection = db.stock_basic_info

        # 🔥 Use unified data source priority management functions
        preferred_source = await get_preferred_data_source_async(market_category="a_shares")

        # Build search criteria
        search_conditions = []

        # If it is a 6-digit number, match it exactly according to the code
        if keyword.isdigit() and len(keyword) == 6:
            search_conditions.append({"symbol": keyword})
        else:
            # Fuzzy match by name
            search_conditions.append({"name": {"$regex": keyword, "$options": "i"}})
            # Also attempts code matching if numbers are included
            if any(c.isdigit() for c in keyword):
                search_conditions.append({"symbol": {"$regex": keyword}})

        # 🔥 Add data source filtering: only query the data source with the highest priority
        query = {
            "$and": [
                {"$or": search_conditions},
                {"source": preferred_source}
            ]
        }

        # Perform a search
        cursor = collection.find(query, {"_id": 0}).limit(limit)

        results = await cursor.to_list(length=limit)

        # Data normalization
        service = get_stock_data_service()
        standardized_results = []
        for doc in results:
            standardized_doc = service._standardize_basic_info(doc)
            standardized_results.append(standardized_doc)

        return {
            "success": True,
            "data": standardized_results,
            "total": len(standardized_results),
            "keyword": keyword,
            "source": preferred_source,  # 🔥 Return data source
            "message": "Search completed"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stock search failed: {str(e)}"
        )


@router.get("/markets")
async def get_market_summary(
    current_user: dict = Depends(get_current_user)
):
    """
    Get a market overview

    Returns:
        dict: Statistics on the number of stocks in each market
    """
    try:
        from app.core.database import get_mongo_db

        db = get_mongo_db()
        collection = db.stock_basic_info

        # Count the number of stocks in each market
        pipeline = [
            {
                "$group": {
                    "_id": "$market",
                    "count": {"$sum": 1}
                }
            },
            {
                "$sort": {"count": -1}
            }
        ]

        cursor = collection.aggregate(pipeline)
        market_stats = await cursor.to_list(length=None)

        # Total statistics
        total_count = await collection.count_documents({})

        return {
            "success": True,
            "data": {
                "total_stocks": total_count,
                "market_breakdown": market_stats,
                "supported_markets": ["CN"],  # Currently supported markets
                "last_updated": None  # The latest update time can be obtained from the data
            },
            "message": "get success"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get market overview: {str(e)}"
        )


@router.get("/sync-status/quotes")
async def get_quotes_sync_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get real-time market synchronization status

    Returns:
        dict: {
            "success": True,
            "data": {
                "last_sync_time": "2025-10-28 15:06:00",
                "last_sync_time_iso": "2025-10-28T15:06:00+08:00",
                "interval_seconds": 360,
                "interval_minutes": 6,
                "data_source": "tushare",
                "success": True,
                "records_count": 5440,
                "error_message": None
            },
            "message": "get success"
        }
    """
    try:
        from app.services.quotes_ingestion_service import QuotesIngestionService

        service = QuotesIngestionService()
        status_data = await service.get_sync_status()

        return {
            "success": True,
            "data": status_data,
            "message": "get success"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sync status: {str(e)}"
        )


# ==================== Batch import interface ====================

@router.post("/save-basic-info", response_model=dict, dependencies=[Depends(require_pro)])
async def save_basic_info_batch(
    request: StockBasicInfoBatchRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Save basic stock information in batches (optimized version)[PRO]

    Allow users to import basic stock information data in batches through API

    **Permission requirements**: This function is exclusive to advanced students and requires PRO authorization

    Performance optimization:
    - Reduce database round-trips using batch queries
    - Use bulk_write bulk operations
    - Data validation prerequisite

    Args:
        request: Batch save request with stock list and data source ID

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
        from datetime import datetime
        from pymongo import UpdateOne, InsertOne
        import logging

        logger = logging.getLogger(__name__)
        db = get_mongo_db()
        collection = db.stock_basic_info

        # Data validation and preprocessing
        valid_stocks = []
        errors = []
        failed_count = 0

        for idx, stock_data in enumerate(request.stocks):
            try:
                # ==================== 1. Validate required fields ====================
                if "symbol" not in stock_data or "name" not in stock_data:
                    errors.append({
                        "index": idx,
                        "error": "Missing required field: symbol or name"
                    })
                    failed_count += 1
                    continue

                # Verify symbol format (6 digits)
                symbol = stock_data["symbol"]
                if not (isinstance(symbol, str) and symbol.isdigit() and len(symbol) == 6):
                    errors.append({
                        "index": idx,
                        "symbol": symbol,
                        "error": "symbol Must be 6 digits"
                    })
                    failed_count += 1
                    continue

                # ==================== 2. Validate core business fields (must have values) ====================
                # These fields are the basis for analysis and must be provided
                required_fields = {
                    "area": "area",
                    "industry": "Industry",
                    "list_date": "Listing date"
                }

                missing_fields = []
                for field, field_name in required_fields.items():
                    if field not in stock_data or not stock_data[field]:
                        missing_fields.append(field_name)

                if missing_fields:
                    errors.append({
                        "index": idx,
                        "symbol": symbol,
                        "error": f"Missing core business fields: {', '.join(missing_fields)}"
                    })
                    failed_count += 1
                    continue

                # ==================== 3. Validate financial data fields (provide at least one set) ====================
                # Market capitalization data group
                has_market_cap = ("total_mv" in stock_data and stock_data["total_mv"]) or \
                                ("circ_mv" in stock_data and stock_data["circ_mv"])

                # financial ratio group
                has_financial_ratios = any(
                    field in stock_data and stock_data[field]
                    for field in ["pe", "pb", "ps", "pe_ttm", "pb_mrq", "ps_ttm", "roe"]
                )

                # Equity data group
                has_share_capital = ("total_share" in stock_data and stock_data["total_share"]) or \
                                   ("float_share" in stock_data and stock_data["float_share"])

                # There must be at least one set of financial data
                if not (has_market_cap or has_financial_ratios or has_share_capital):
                    errors.append({
                        "index": idx,
                        "symbol": symbol,
                        "error": "Missing financial data: Must provide at least market capitalization(total_mv/circ_mv), financial ratios(pe/pb/ps Wait)or share capital(total_share/float_share)a set of data in"
                    })
                    failed_count += 1
                    continue

                # ==================== 4. Standardized field handling ====================
                # Make sure both code and symbol fields exist
                if "code" not in stock_data:
                    stock_data["code"] = symbol
                stock_data["symbol"] = symbol  # Standardized fields

                # Generate full_symbol if not provided
                if "full_symbol" not in stock_data:
                    # Determine the exchange based on the code prefix
                    if symbol.startswith(('6', '5')):  # Shanghai
                        stock_data["full_symbol"] = f"{symbol}.SH"
                    elif symbol.startswith(('0', '3', '2')):  # Shenzhen
                        stock_data["full_symbol"] = f"{symbol}.SZ"
                    elif symbol.startswith('8'):  # Beijing
                        stock_data["full_symbol"] = f"{symbol}.BJ"
                    else:
                        stock_data["full_symbol"] = symbol

                # Make sure the sse (exchange) field exists
                if "sse" not in stock_data:
                    if symbol.startswith(('6', '5')):
                        stock_data["sse"] = "Shanghai Stock Exchange"
                    elif symbol.startswith(('0', '3', '2')):
                        stock_data["sse"] = "Shenzhen Stock Exchange"
                    elif symbol.startswith('8'):
                        stock_data["sse"] = "Beijing Stock Exchange"
                    else:
                        stock_data["sse"] = "unknown"

                # Make sure the sec (classification) field exists
                if "sec" not in stock_data:
                    stock_data["sec"] = "stock_cn"

                # Make sure the category field exists
                if "category" not in stock_data:
                    stock_data["category"] = "stock_cn"

                # Add metadata (fixed use local as local data identifier)
                stock_data["source"] = "local"
                stock_data["updated_at"] = datetime.utcnow()

                valid_stocks.append((idx, stock_data))

            except Exception as e:
                errors.append({
                    "index": idx,
                    "symbol": stock_data.get("symbol", "unknown"),
                    "error": f"Data validation failed: {str(e)}"
                })
                failed_count += 1

        if not valid_stocks:
            return ok(
                data={
                    "saved": 0,
                    "updated": 0,
                    "skipped": 0,
                    "failed": failed_count,
                    "total": len(request.stocks),
                    "errors": errors[:10]
                },
                message="All data validation failed"
            )

        # Query existing data in batches
        symbols = [stock["symbol"] for _, stock in valid_stocks]
        existing_docs = await collection.find({
            "symbol": {"$in": symbols},
            "source": "local"
        }).to_list(length=None)

        existing_symbols = {doc["symbol"]: doc for doc in existing_docs}

        # Prepare for batch operations
        bulk_operations = []
        saved_count = 0
        updated_count = 0
        skipped_count = 0

        for idx, stock_data in valid_stocks:
            symbol = stock_data["symbol"]

            if symbol in existing_symbols:
                if request.overwrite:
                    # Batch update
                    stock_data["created_at"] = existing_symbols[symbol].get("created_at", datetime.utcnow())
                    bulk_operations.append(
                        UpdateOne(
                            {"symbol": symbol, "source": "local"},
                            {"$set": stock_data}
                        )
                    )
                    updated_count += 1
                else:
                    # Skip existing data
                    skipped_count += 1
            else:
                # Batch insert
                stock_data["created_at"] = datetime.utcnow()
                bulk_operations.append(InsertOne(stock_data))
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

                for idx, stock_data in valid_stocks:
                    try:
                        symbol = stock_data["symbol"]
                        if symbol in existing_symbols and request.overwrite:
                            await collection.update_one(
                                {"symbol": symbol, "source": "local"},
                                {"$set": stock_data}
                            )
                            updated_count += 1
                        elif symbol not in existing_symbols:
                            await collection.insert_one(stock_data)
                            saved_count += 1
                    except Exception as e2:
                        errors.append({
                            "index": idx,
                            "symbol": stock_data.get("symbol", "unknown"),
                            "error": str(e2)
                        })
                        failed_count += 1

        return ok(
            data={
                "saved": saved_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "failed": failed_count,
                "total": len(request.stocks),
                "errors": errors[:10]  # Only return the first 10 errors
            },
            message=f"Batch saving completed: success{saved_count}, update{updated_count}, skip{skipped_count}, failed{failed_count}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save basic stock information in batches: {str(e)}"
        )


@router.post("/save-quotes", response_model=dict, dependencies=[Depends(require_pro)])
async def save_quotes_batch(
    request: MarketQuotesBatchRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Save real-time market data in batches (optimized version)[PRO]

    Allow users to import real-time market data in batches through API

    **Permission requirements**: This function is exclusive to advanced students and requires PRO authorization

    Performance optimization:
    - Reduce database round-trips using batch queries
    - Use bulk_write bulk operations
    - Data validation prerequisite

    Args:
        request: Batch save request, including market list and data source identifier

    Returns:
        dict: {
            "saved": Number of successful saves,
            "updated": Update quantity,
            "failed": Number of failures,
            "errors": error list
        }
    """
    try:
        from app.core.database import get_mongo_db
        from datetime import datetime
        from pymongo import UpdateOne, InsertOne
        import logging

        logger = logging.getLogger(__name__)
        db = get_mongo_db()
        collection = db.market_quotes

        # Data validation and preprocessing
        valid_quotes = []
        errors = []
        failed_count = 0

        for idx, quote_data in enumerate(request.quotes):
            try:
                # Validate required fields
                if "symbol" not in quote_data:
                    errors.append({
                        "index": idx,
                        "error": "Missing required field: symbol"
                    })
                    failed_count += 1
                    continue

                # Verify symbol format (6 digits)
                symbol = quote_data["symbol"]
                if not (isinstance(symbol, str) and symbol.isdigit() and len(symbol) == 6):
                    errors.append({
                        "index": idx,
                        "symbol": symbol,
                        "error": "symbol Must be 6 digits"
                    })
                    failed_count += 1
                    continue

                # Add metadata (fixed use local as local data identifier)
                quote_data["data_source"] = "local"
                quote_data["updated_at"] = datetime.utcnow()

                valid_quotes.append((idx, quote_data))

            except Exception as e:
                errors.append({
                    "index": idx,
                    "symbol": quote_data.get("symbol", "unknown"),
                    "error": f"Data validation failed: {str(e)}"
                })
                failed_count += 1

        if not valid_quotes:
            return ok(
                data={
                    "saved": 0,
                    "updated": 0,
                    "failed": failed_count,
                    "total": len(request.quotes),
                    "errors": errors[:10]
                },
                message="All data validation failed"
            )

        # Query existing data in batches
        symbols = [quote["symbol"] for _, quote in valid_quotes]
        existing_docs = await collection.find({
            "symbol": {"$in": symbols}
        }).to_list(length=None)

        existing_symbols = {doc["symbol"] for doc in existing_docs}

        # Prepare for batch operations
        bulk_operations = []
        saved_count = 0
        updated_count = 0

        for idx, quote_data in valid_quotes:
            symbol = quote_data["symbol"]

            if symbol in existing_symbols:
                # Batch update
                bulk_operations.append(
                    UpdateOne(
                        {"symbol": symbol},
                        {"$set": quote_data}
                    )
                )
                updated_count += 1
            else:
                # Batch insert
                quote_data["created_at"] = datetime.utcnow()
                bulk_operations.append(InsertOne(quote_data))
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

                for idx, quote_data in valid_quotes:
                    try:
                        symbol = quote_data["symbol"]
                        result = await collection.update_one(
                            {"symbol": symbol},
                            {"$set": quote_data},
                            upsert=True
                        )
                        if result.upserted_id:
                            saved_count += 1
                        else:
                            updated_count += 1
                    except Exception as e2:
                        errors.append({
                            "index": idx,
                            "symbol": quote_data.get("symbol", "unknown"),
                            "error": str(e2)
                        })
                        failed_count += 1

        return ok(
            data={
                "saved": saved_count,
                "updated": updated_count,
                "failed": failed_count,
                "total": len(request.quotes),
                "errors": errors[:10]  # Only return the first 10 errors
            },
            message=f"Batch saving completed: New{saved_count}, update{updated_count}, failed{failed_count}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save real-time quotes in batches: {str(e)}"
        )


# ==================== API Guide interface ====================

@router.get("/api-guide-content")
async def get_api_guide_content():
    """Get the Markdown raw content of the Stock Data Bulk Import API Guide (for front-end rendering)"""
    from fastapi.responses import Response
    from pathlib import Path

    try:
        # Read Markdown files
        guide_path = Path("docs/03-development/api/stock-data-import.md")

        if not guide_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API Guide file does not exist"
            )

        with open(guide_path, "r", encoding="utf-8") as f:
            content = f.read()

        return Response(
            content=content,
            media_type="text/plain; charset=utf-8"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read API guide content: {str(e)}"
        )


@router.get("/download-test-program")
async def download_test_program():
    """Download stock data batch import test program"""
    from fastapi.responses import FileResponse
    from pathlib import Path

    try:
        project_root = Path(__file__).parent.parent.parent
        candidate_paths = [
            project_root / "docs" / "api" / "examples" / "stock_data_import_examples.py",
            project_root / "scripts" / "test_batch_import_apis.py",
        ]

        test_program_path = next((path for path in candidate_paths if path.exists()), None)

        if not test_program_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test program file does not exist"
            )

        return FileResponse(
            path=str(test_program_path),
            filename=test_program_path.name,
            media_type="text/x-python"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Download test program failed: {str(e)}"
        )
