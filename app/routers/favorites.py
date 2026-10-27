"""
Stock Watchlist Management API Routing
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import logging

from app.routers.auth_db import get_current_user
from app.models.user import User, FavoriteStock
from app.services.favorites_service import favorites_service
from app.core.response import ok

logger = logging.getLogger("webapi")

router = APIRouter(prefix="/favorites", tags=["Stock watch list management"], redirect_slashes=False)

FAVORITES_SYNC_TASKS_COLLECTION = "favorites_sync_tasks"


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


async def _create_favorites_sync_task(current_user: dict, payload: Dict[str, Any]) -> Dict[str, Any]:
    db = favorites_service.db
    task_doc = {
        "task_id": uuid4().hex,
        "task_type": "favorites_realtime",
        "status": "pending",
        "message": "Stock watch list real-time market synchronization task has been submitted",
        "payload": payload,
        "user_id": current_user["id"],
        "submitted_by": str(current_user.get("username") or current_user.get("id") or "unknown"),
        "created_at": _utc_now_iso(),
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }
    await db[FAVORITES_SYNC_TASKS_COLLECTION].insert_one(task_doc)
    task_doc.pop("_id", None)
    return task_doc


async def _update_favorites_sync_task(task_id: str, updates: Dict[str, Any]) -> None:
    db = favorites_service.db
    await db[FAVORITES_SYNC_TASKS_COLLECTION].update_one(
        {"task_id": task_id},
        {"$set": updates},
        upsert=False,
    )


async def _get_favorites_sync_task(task_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    db = favorites_service.db
    task_doc = await db[FAVORITES_SYNC_TASKS_COLLECTION].find_one({"task_id": task_id, "user_id": user_id})
    if task_doc:
        task_doc.pop("_id", None)
    return task_doc


async def _run_favorites_realtime_sync_task(task_id: str, user_id: str, data_source: str) -> None:
    try:
        await _update_favorites_sync_task(
            task_id,
            {
                "status": "running",
                "message": "Stock watch list real-time quotes are being executed simultaneously",
                "started_at": _utc_now_iso(),
                "error": None,
            },
        )

        favorites = await favorites_service.get_user_favorites(user_id)

        if not favorites:
            result = {
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "message": "No stock watchlists to sync",
                "symbols": [],
                "data_source": data_source,
            }
            await _update_favorites_sync_task(
                task_id,
                {
                    "status": "success",
                    "message": result["message"],
                    "finished_at": _utc_now_iso(),
                    "result": result,
                },
            )
            return

        symbols = [fav.get("stock_code") or fav.get("symbol") for fav in favorites]
        symbols = [s for s in symbols if s]

        if data_source == "tushare":
            from app.worker.tushare_sync_service import get_tushare_sync_service
            service = await get_tushare_sync_service()
        elif data_source == "akshare":
            from app.worker.akshare_sync_service import get_akshare_sync_service
            service = await get_akshare_sync_service()
        else:
            raise RuntimeError(f"Unsupported data source: {data_source}")

        if not service:
            raise RuntimeError(f"{data_source} Service unavailable")

        if data_source == "akshare":
            sync_result = await service.sync_realtime_quotes(
                symbols=symbols,
                force=True,
                manual_mode=True,
            )
        else:
            sync_result = await service.sync_realtime_quotes(
                symbols=symbols,
                force=True,
            )

        success_count = sync_result.get("success_count", 0)
        failed_count = sync_result.get("failed_count", 0)
        result = {
            "total": len(symbols),
            "success_count": success_count,
            "failed_count": failed_count,
            "symbols": symbols,
            "data_source": data_source,
            "message": f"Synchronization completed: success {success_count} Only, failed {failed_count} only",
        }

        await _update_favorites_sync_task(
            task_id,
            {
                "status": "success" if failed_count == 0 else "success_with_errors",
                "message": result["message"],
                "finished_at": _utc_now_iso(),
                "result": result,
            },
        )
    except Exception as e:
        logger.error(f"❌ The real-time quotation synchronization task of the stock watch list failed.: {e}", exc_info=True)
        await _update_favorites_sync_task(
            task_id,
            {
                "status": "failed",
                "message": f"Sync failed: {str(e)}",
                "finished_at": _utc_now_iso(),
                "error": str(e),
            },
        )


class AddFavoriteRequest(BaseModel):
    """Add to study list request"""
    stock_code: Optional[str] = None
    symbol: Optional[str] = None
    stock_name: str
    market: str = "A shares"
    tags: List[str] = []
    notes: str = ""
    alert_price_high: Optional[float] = None
    alert_price_low: Optional[float] = None


class UpdateFavoriteRequest(BaseModel):
    """Update stock watchlist request"""
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    alert_price_high: Optional[float] = None
    alert_price_low: Optional[float] = None


class FavoriteStockResponse(BaseModel):
    """Stock Watchlist Response"""
    stock_code: str
    stock_name: str
    market: str
    added_at: str
    tags: List[str]
    notes: str
    alert_price_high: Optional[float]
    alert_price_low: Optional[float]
    # real time data
    current_price: Optional[float] = None
    change_percent: Optional[float] = None
    volume: Optional[int] = None


@router.get("", response_model=dict)
async def get_favorites(
    current_user: dict = Depends(get_current_user)
):
    """Get the user s stock watchlist list"""
    try:
        favorites = await favorites_service.get_user_favorites(current_user["id"])
        return ok(favorites)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stock watchlist: {str(e)}"
        )


@router.post("", response_model=dict)
async def add_favorite(
    request: AddFavoriteRequest,
    current_user: dict = Depends(get_current_user)
):
    """Add a stock to a stock watchlist"""
    import logging
    logger = logging.getLogger("webapi")

    try:
        stock_code = (request.stock_code or request.symbol or "").strip()
        if not stock_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stock code cannot be empty"
            )

        logger.info(f"📝 Add to study list request: user_id={current_user['id']}, stock_code={stock_code}, stock_name={request.stock_name}")

        # Check if it already exists
        is_fav = await favorites_service.is_favorite(current_user["id"], stock_code)
        logger.info(f"🔍 Check if it already exists: {is_fav}")

        if is_fav:
            logger.warning(f"⚠️ The stock is already in the stock watch list: {stock_code}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The stock is already on the stock watch list"
            )

        # Add to stock watchlist
        logger.info(f"➕ Start adding to research list...")
        success = await favorites_service.add_favorite(
            user_id=current_user["id"],
            stock_code=stock_code,
            stock_name=request.stock_name,
            market=request.market,
            tags=request.tags,
            notes=request.notes,
            alert_price_high=request.alert_price_high,
            alert_price_low=request.alert_price_low
        )

        logger.info(f"✅ Add results: success={success}")

        if success:
            return ok({"stock_code": stock_code}, "Added successfully")
        else:
            logger.error(f"❌ Add failed: success=False")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Add failed"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Add to study list exception: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Add to study list failed: {str(e)}"
        )


@router.put("/{stock_code}", response_model=dict)
async def update_favorite(
    stock_code: str,
    request: UpdateFavoriteRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update stock watchlist information"""
    try:
        success = await favorites_service.update_favorite(
            user_id=current_user["id"],
            stock_code=stock_code,
            tags=request.tags,
            notes=request.notes,
            alert_price_high=request.alert_price_high,
            alert_price_low=request.alert_price_low
        )

        if success:
            return ok({"stock_code": stock_code}, "Update successful")
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stock watch list does not exist"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update stock watchlist: {str(e)}"
        )


@router.delete("/{stock_code}", response_model=dict)
async def remove_favorite(
    stock_code: str,
    current_user: dict = Depends(get_current_user)
):
    """Remove a stock from a stock watchlist"""
    try:
        success = await favorites_service.remove_favorite(current_user["id"], stock_code)

        if success:
            return ok({"stock_code": stock_code}, "Removed successfully")
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stock watch list does not exist"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove stock watchlist: {str(e)}"
        )


@router.get("/check/{stock_code}", response_model=dict)
async def check_favorite(
    stock_code: str,
    current_user: dict = Depends(get_current_user)
):
    """Check if a stock is in the stock watchlist"""
    try:
        is_favorite = await favorites_service.is_favorite(current_user["id"], stock_code)
        return ok({"stock_code": stock_code, "is_favorite": is_favorite})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Checking stock watchlist status failed: {str(e)}"
        )


@router.get("/tags", response_model=dict)
async def get_user_tags(
    current_user: dict = Depends(get_current_user)
):
    """Get all tags used by the user"""
    try:
        tags = await favorites_service.get_user_tags(current_user["id"])
        return ok(tags)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get tags: {str(e)}"
        )


class SyncFavoritesRequest(BaseModel):
    """Synchronize stock watch list real-time quotation request"""
    data_source: str = "tushare"  # tushare/akshare


@router.post("/sync-realtime", response_model=dict)
async def sync_favorites_realtime(
    request: SyncFavoritesRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Synchronize real-time quotes of stock watchlists

    - **data_source**: Data source (tushare/akshare)
    """
    try:
        logger.info(f"📊 Submit stock watch list real-time market synchronization task: user_id={current_user['id']}, data_source={request.data_source}")

        task_doc = await _create_favorites_sync_task(
            current_user,
            {"data_source": request.data_source},
        )
        asyncio.create_task(
            _run_favorites_realtime_sync_task(
                task_doc["task_id"],
                current_user["id"],
                request.data_source,
            )
        )

        return ok(task_doc, "Stock watch list real-time market synchronization task has been submitted")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to synchronize real-time quotes of stock watch list: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}"
        )


@router.get("/sync-realtime/tasks/{task_id}", response_model=dict)
async def get_favorites_realtime_sync_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get the real-time quotation synchronization task status of the stock watch list."""
    try:
        task_doc = await _get_favorites_sync_task(task_id, current_user["id"])
        if not task_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Synchronization task does not exist"
            )
        return ok(task_doc)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to synchronize real-time quotes from stock watch list: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain synchronization task: {str(e)}"
        )
