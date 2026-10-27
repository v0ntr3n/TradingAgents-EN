"""
News data API routing
Provides news data query, synchronization and management interfaces
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query, status
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import logging

from app.routers.auth_db import get_current_user
from app.core.permissions import require_pro
from app.core.response import ok
from app.services.news_data_service import get_news_data_service, NewsQueryParams
from app.worker.news_data_sync_service import get_news_data_sync_service

router = APIRouter(prefix="/api/news-data", tags=["news data"])
logger = logging.getLogger("webapi")


class NewsQueryRequest(BaseModel):
    """News query request"""
    symbol: Optional[str] = Field(None, description="Stock code")
    symbols: Optional[List[str]] = Field(None, description="Multiple tickers")
    start_time: Optional[datetime] = Field(None, description="start time")
    end_time: Optional[datetime] = Field(None, description="end time")
    category: Optional[str] = Field(None, description="News category")
    sentiment: Optional[str] = Field(None, description="sentiment analysis")
    importance: Optional[str] = Field(None, description="importance")
    data_source: Optional[str] = Field(None, description="data source")
    keywords: Optional[List[str]] = Field(None, description="keywords")
    limit: int = Field(50, description="Return quantity limit")
    skip: int = Field(0, description="skip quantity")


class NewsSyncRequest(BaseModel):
    """News sync request"""
    symbol: Optional[str] = Field(None, description="Stock code, if empty, market news will be synchronized")
    data_sources: Optional[List[str]] = Field(None, description="Data source list")
    hours_back: int = Field(24, description="Lookback hours")
    max_news_per_source: int = Field(50, description="Maximum number of news per data source")


class NewsDataBatchRequest(BaseModel):
    """Batch save news data requests"""
    symbol: Optional[str] = Field(None, description="Main relevant stock symbols")
    news_list: List[Dict[str, Any]] = Field(..., description="News data list")
    overwrite: bool = Field(False, description="Whether to overwrite existing data")


@router.get("/query/{symbol}", response_model=dict)
async def query_stock_news(
    symbol: str,
    hours_back: int = Query(24, description="Lookback hours"),
    limit: int = Query(20, description="Return quantity limit"),
    category: Optional[str] = Query(None, description="News category"),
    sentiment: Optional[str] = Query(None, description="sentiment analysis"),
    current_user: dict = Depends(get_current_user)
):
    """
    Query stock news (intelligent acquisition: priority database, real-time acquisition when no data is available)

    Args:
        symbol: Stock code
        hours_back: Lookback hours
        limit: Return quantity limit
        category: News category filtering
        sentiment: Sentiment analysis filter

    Returns:
        dict: News data list
    """
    try:
        service = await get_news_data_service()

        # Build query parameters
        start_time = datetime.utcnow() - timedelta(hours=hours_back)

        params = NewsQueryParams(
            symbol=symbol,
            start_time=start_time,
            category=category,
            sentiment=sentiment,
            limit=limit,
            sort_by="publish_time",
            sort_order=-1
        )

        # 1. First query from the database
        news_list = await service.query_news(params)
        data_source = "database"

        # 2. If there is no data in the database, obtain it in real time
        if not news_list:
            logger.info(f"📰 There is no news data in the database, which can be obtained in real time.: {symbol}")
            try:
                from app.worker.akshare_sync_service import get_akshare_sync_service
                sync_service = await get_akshare_sync_service()

                # Get news in real time
                news_data = await sync_service.provider.get_stock_news(
                    symbol=symbol,
                    limit=limit
                )

                if news_data:
                    # Save to database
                    saved_count = await service.save_news_data(
                        news_data=news_data,
                        data_source="akshare",
                        market="CN"
                    )
                    logger.info(f"✅ Get and save in real time {saved_count} news")

                    # Query again
                    news_list = await service.query_news(params)
                    data_source = "realtime"
                else:
                    logger.warning(f"⚠️ Failed to get news in real time: {symbol}")

            except Exception as e:
                logger.error(f"❌ Get news exceptions in real time: {e}")

        return ok(data={
                "symbol": symbol,
                "hours_back": hours_back,
                "total_count": len(news_list),
                "news": news_list,
                "data_source": data_source
            },
            message=f"The query is successful and returns {len(news_list)} news (source:{data_source}) "
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query stock news: {str(e)}"
        )


@router.post("/query", response_model=dict)
async def query_news_advanced(
    request: NewsQueryRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Advanced news query
    
    Args:
        request: Query request parameters
        
    Returns:
        dict: News data list
    """
    try:
        service = await get_news_data_service()
        
        # Build query parameters
        params = NewsQueryParams(
            symbol=request.symbol,
            symbols=request.symbols,
            start_time=request.start_time,
            end_time=request.end_time,
            category=request.category,
            sentiment=request.sentiment,
            importance=request.importance,
            data_source=request.data_source,
            keywords=request.keywords,
            limit=request.limit,
            skip=request.skip
        )
        
        # Query news
        news_list = await service.query_news(params)
        
        return ok(data={
                "query_params": request.dict(),
                "total_count": len(news_list),
                "news": news_list
            },
            message=f"Advanced query successful, return {len(news_list)} news"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Advanced news query failed: {str(e)}"
        )


@router.get("/latest", response_model=dict)
async def get_latest_news(
    symbol: Optional[str] = Query(None, description="Stock code, if empty, get all news"),
    limit: int = Query(10, description="Return quantity limit"),
    hours_back: int = Query(24, description="Lookback hours"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get the latest news
    
    Args:
        symbol: Stock code, if empty, get all news
        limit: Return quantity limit
        hours_back: Lookback hours
        
    Returns:
        dict: Latest news list
    """
    try:
        service = await get_news_data_service()
        
        # Get the latest news
        news_list = await service.get_latest_news(
            symbol=symbol,
            limit=limit,
            hours_back=hours_back
        )
        
        return ok(data={
                "symbol": symbol,
                "limit": limit,
                "hours_back": hours_back,
                "total_count": len(news_list),
                "news": news_list
            },
            message=f"Get the latest news successfully, return {len(news_list)} Article"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get latest news: {str(e)}"
        )


@router.get("/search", response_model=dict)
async def search_news(
    query: str = Query(..., description="Search keywords"),
    symbol: Optional[str] = Query(None, description="Stock code filter"),
    limit: int = Query(20, description="Return quantity limit"),
    current_user: dict = Depends(get_current_user)
):
    """
    Search news in full text
    
    Args:
        query: Search keywords
        symbol: Stock code filter
        limit: Return quantity limit
        
    Returns:
        dict: Search result list
    """
    try:
        service = await get_news_data_service()
        
        # Full text search
        news_list = await service.search_news(
            query_text=query,
            symbol=symbol,
            limit=limit
        )
        
        return ok(data={
                "query": query,
                "symbol": symbol,
                "total_count": len(news_list),
                "news": news_list
            },
            message=f"Search successful, return {len(news_list)} results"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"News search failed: {str(e)}"
        )


@router.get("/statistics", response_model=dict)
async def get_news_statistics(
    symbol: Optional[str] = Query(None, description="Stock code"),
    days_back: int = Query(7, description="Lookback days"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get news statistics
    
    Args:
        symbol: Stock code
        days_back: Lookback days
        
    Returns:
        dict: News statistics
    """
    try:
        service = await get_news_data_service()
        
        # Calculation time range
        start_time = datetime.utcnow() - timedelta(days=days_back)
        
        # Get statistics
        stats = await service.get_news_statistics(
            symbol=symbol,
            start_time=start_time
        )
        
        return ok(data={
                "symbol": symbol,
                "days_back": days_back,
                "statistics": {
                    "total_count": stats.total_count,
                    "sentiment_distribution": {
                        "positive": stats.positive_count,
                        "negative": stats.negative_count,
                        "neutral": stats.neutral_count
                    },
                    "importance_distribution": {
                        "high": stats.high_importance_count,
                        "medium": stats.medium_importance_count,
                        "low": stats.low_importance_count
                    },
                    "categories": stats.categories,
                    "sources": stats.sources
                }
            },
            message="Obtain news statistics successfully"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain news statistics: {str(e)}"
        )


@router.post("/sync/start", response_model=dict)
async def start_news_sync(
    request: NewsSyncRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    Start news synchronization task
    
    Args:
        request: Synchronous request parameters
        background_tasks: Background tasks
        
    Returns:
        dict: Task start result
    """
    try:
        sync_service = await get_news_data_sync_service()
        
        # Add background sync task
        if request.symbol:
            background_tasks.add_task(
                _execute_stock_news_sync,
                sync_service,
                request
            )
            message = f"stocks {request.symbol} News synchronization task has been started"
        else:
            background_tasks.add_task(
                _execute_market_news_sync,
                sync_service,
                request
            )
            message = "Market news synchronization task has been started"
        
        return ok(data={
                "sync_type": "stock" if request.symbol else "market",
                "symbol": request.symbol,
                "data_sources": request.data_sources,
                "hours_back": request.hours_back,
                "max_news_per_source": request.max_news_per_source
            },
            message=message
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start news sync: {str(e)}"
        )


@router.post("/sync/single", response_model=dict)
async def sync_single_stock_news(
    symbol: str,
    data_sources: Optional[List[str]] = None,
    hours_back: int = 24,
    max_news_per_source: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """
    Synchronize single stock news (synchronous execution)
    
    Args:
        symbol: Stock code
        data_sources: Data source list
        hours_back: Lookback hours
        max_news_per_source: Maximum number of news per data source
        
    Returns:
        dict: Synchronization results
    """
    try:
        sync_service = await get_news_data_sync_service()
        
        # Perform synchronization
        stats = await sync_service.sync_stock_news(
            symbol=symbol,
            data_sources=data_sources,
            hours_back=hours_back,
            max_news_per_source=max_news_per_source
        )
        
        return ok(data={
                "symbol": symbol,
                "sync_stats": {
                    "total_processed": stats.total_processed,
                    "successful_saves": stats.successful_saves,
                    "failed_saves": stats.failed_saves,
                    "duplicate_skipped": stats.duplicate_skipped,
                    "sources_used": stats.sources_used,
                    "duration_seconds": stats.duration_seconds,
                    "success_rate": stats.success_rate
                }
            },
            message=f"stocks {symbol} News synchronization completed and saved successfully {stats.successful_saves} Article"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync stock news: {str(e)}"
        )


@router.delete("/cleanup", response_model=dict)
async def cleanup_old_news(
    days_to_keep: int = Query(90, description="retention days"),
    current_user: dict = Depends(get_current_user)
):
    """
    Clean up expired news
    
    Args:
        days_to_keep: retention days
        
    Returns:
        dict: Clean results
    """
    try:
        service = await get_news_data_service()
        
        # Delete expired news
        deleted_count = await service.delete_old_news(days_to_keep)
        
        return ok(data={
                "days_to_keep": days_to_keep,
                "deleted_count": deleted_count
            },
            message=f"Cleanup completed, delete {deleted_count} expired news"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clean up expired news: {str(e)}"
        )


@router.get("/health", response_model=dict)
async def health_check():
    """health check"""
    try:
        service = await get_news_data_service()
        sync_service = await get_news_data_sync_service()
        
        return ok(data={
                "service_status": "healthy",
                "timestamp": datetime.utcnow().isoformat()
            },
            message="News data service is running normally"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Health check failed: {str(e)}"
        )


# Background task execution function
async def _execute_stock_news_sync(sync_service, request: NewsSyncRequest):
    """Perform stock news synchronization"""
    try:
        await sync_service.sync_stock_news(
            symbol=request.symbol,
            data_sources=request.data_sources,
            hours_back=request.hours_back,
            max_news_per_source=request.max_news_per_source
        )
    except Exception as e:
        logger.error(f"❌ Backend stock news synchronization failed: {e}")


async def _execute_market_news_sync(sync_service, request: NewsSyncRequest):
    """Perform market news synchronization"""
    try:
        await sync_service.sync_market_news(
            data_sources=request.data_sources,
            hours_back=request.hours_back,
            max_news_per_source=request.max_news_per_source
        )
    except Exception as e:
        logger.error(f"❌ Backstage market news synchronization failed: {e}")


# ==================== Batch import interface ====================

@router.post("/save", response_model=dict, dependencies=[Depends(require_pro)])
async def save_news_data_batch(
    request: NewsDataBatchRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Save news data in batches (optimized version)[PRO]

    Allow users to import news data in batches via API

    **Permission requirements**: This function is exclusive to advanced students and requires PRO authorization

    Performance optimization:
    - Reduce database round-trips using batch queries
    - Use bulk_write bulk operations
    - Data validation prerequisite

    Args:
        request: Batch save request, including news list and data source identification

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
        collection = db.stock_news

        # Data validation and preprocessing
        valid_news = []
        errors = []
        failed_count = 0

        for idx, news_data in enumerate(request.news_list):
            try:
                # Validate required fields
                required_fields = ["title", "url", "publish_time"]
                missing_fields = [f for f in required_fields if f not in news_data]

                if missing_fields:
                    errors.append({
                        "index": idx,
                        "error": f"Missing required field: {', '.join(missing_fields)}"
                    })
                    failed_count += 1
                    continue

                # Verify URL format
                url = news_data["url"]
                if not (isinstance(url, str) and (url.startswith("http://") or url.startswith("https://"))):
                    errors.append({
                        "index": idx,
                        "url": url,
                        "error": "url Must be a valid HTTP/HTTPS link"
                    })
                    failed_count += 1
                    continue

                # Add ticker and metadata
                if request.symbol:
                    news_data["symbol"] = request.symbol
                    if "symbols" not in news_data:
                        news_data["symbols"] = [request.symbol]

                # Fixed use of local as local data identifier
                news_data["data_source"] = "local"
                news_data["updated_at"] = datetime.utcnow()

                # Convert publish_time to datetime object (if string)
                if isinstance(news_data.get("publish_time"), str):
                    try:
                        news_data["publish_time"] = datetime.fromisoformat(
                            news_data["publish_time"].replace("Z", "+00:00")
                        )
                    except Exception as e:
                        errors.append({
                            "index": idx,
                            "error": f"Unable to parse publish_time: {str(e)}"
                        })
                        failed_count += 1
                        continue

                valid_news.append((idx, news_data))

            except Exception as e:
                errors.append({
                    "index": idx,
                    "title": news_data.get("title", "unknown"),
                    "error": f"Data validation failed: {str(e)}"
                })
                failed_count += 1

        if not valid_news:
            return ok(
                data={
                    "saved": 0,
                    "updated": 0,
                    "skipped": 0,
                    "failed": failed_count,
                    "total": len(request.news_list),
                    "errors": errors[:10]
                },
                message="All data validation failed"
            )

        # Batch query for existing data (based on URL)
        urls = [news["url"] for _, news in valid_news]
        existing_docs = await collection.find({
            "url": {"$in": urls}
        }).to_list(length=None)

        existing_urls = {doc["url"]: doc for doc in existing_docs}

        # Prepare for batch operations
        bulk_operations = []
        saved_count = 0
        updated_count = 0
        skipped_count = 0

        for idx, news_data in valid_news:
            url = news_data["url"]

            if url in existing_urls:
                if request.overwrite:
                    # Batch update
                    news_data["created_at"] = existing_urls[url].get("created_at", datetime.utcnow())
                    bulk_operations.append(
                        UpdateOne(
                            {"url": url},
                            {"$set": news_data}
                        )
                    )
                    updated_count += 1
                else:
                    # Skip existing data
                    skipped_count += 1
            else:
                # Batch insert
                news_data["created_at"] = datetime.utcnow()
                bulk_operations.append(InsertOne(news_data))
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

                for idx, news_data in valid_news:
                    try:
                        url = news_data["url"]
                        if url in existing_urls and request.overwrite:
                            await collection.update_one(
                                {"url": url},
                                {"$set": news_data}
                            )
                            updated_count += 1
                        elif url not in existing_urls:
                            await collection.insert_one(news_data)
                            saved_count += 1
                    except Exception as e2:
                        errors.append({
                            "index": idx,
                            "title": news_data.get("title", "unknown"),
                            "error": str(e2)
                        })
                        failed_count += 1

        return ok(
            data={
                "saved": saved_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "failed": failed_count,
                "total": len(request.news_list),
                "errors": errors[:10]  # Only return the first 10 errors
            },
            message=f"Batch saving completed: success{saved_count}, update{updated_count}, skip{skipped_count}, failed{failed_count}"
        )

    except Exception as e:
        logger.error(f"❌ Failed to save news data in batches: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save news data in batches: {str(e)}"
        )
