"""
Transaction review API routing
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from app.routers.auth_db import get_current_user
from app.core.permissions import get_license_info
from app.core.response import ok
from app.services.license_service import LicenseInfo, get_license_service
from app.services.trade_review_service import get_trade_review_service
from app.models.review import (
    CreateTradeReviewRequest, CreatePeriodicReviewRequest,
    SaveAsCaseRequest, ReviewType
)

router = APIRouter(
    prefix="/review",
    tags=["review"]
)
logger = logging.getLogger("webapi.review")


# ==================== Transaction review ====================

@router.post("/trade", response_model=Dict[str, Any])
async def create_trade_review(
    request: CreateTradeReviewRequest,
    current_user: dict = Depends(get_current_user),
    license_info: LicenseInfo = Depends(get_license_info)
):
    """
    Create a transaction review task (uniformly use the task center mode)

    - **trade_ids**: List of transaction IDs to be reviewed
    - **review_type**: Review type (single_trade/complete_trade)
    - **code**: Stock code (optional, if not passed, it will be inferred from transaction records)
    - **use_workflow**: Whether to use workflow engine (default True, recommended)

    Mission Center Mode Features:
    - Immediately return the task ID and perform review in the background
    - The front end can pass GET /api/v1/analysis/tasks/{task_id} Query progress
    - Supports real-time progress tracking
    - Multi-agent collaborative analysis using workflow engines

    Reference: analyze_position_by_code implementation of app/routers/portfolio.py
    """
    import asyncio

    import asyncio

    try:
        logger.info(f"📝 [Transaction review routing] Receive review request: code={request.code}, trade_ids={request.trade_ids}")
        logger.info(f"🔧 [Transaction review routing] Unified use of task center mode")

        if request.trading_system_id:
            license_service = get_license_service()
            if not license_service.has_feature(license_info, "trading_plan_check"):
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "FEATURE_REQUIRED",
                        "message": "Trading plan consistency check is exclusive for advanced students",
                        "feature": "trading_plan_check",
                        "plan": license_info.plan,
                        "upgrade_url": "/settings/license"
                    }
                )

        # 🆕 Unified use of task center mode (supports progress query)
        logger.info(f"=" * 60)
        logger.info(f"🎯 [Transaction review routing] Enter mission center mode")
        logger.info(f"=" * 60)

        from app.services.unified_analysis_service import get_unified_analysis_service

        logger.info(f"🔄 [Transaction review routing] Get UnifiedAnalysisService instance...")
        unified_service = get_unified_analysis_service()
        logger.info(f"✅ [Transaction review routing] Get the UnifiedAnalysisService instance")

        # Create task (return immediately)
        logger.info(f"🔄 [Transaction review routing] Start creating tasks...")
        logger.info(f"   📋 user_id: {current_user['id']}")
        logger.info(f"   📋 code: {request.code}")
        logger.info(f"   📋 trade_ids: {request.trade_ids}")
        logger.info(f"   📋 review_type: {request.review_type}")

        result = await unified_service.create_trade_review_task(
            user_id=current_user["id"],
            request=request
        )
        logger.info(f"✅ [Transaction review routing] Task created successfully")
        logger.info(f"   📋 task_id: {result['task_id']}")
        logger.info(f"   📋 status: {result['status']}")
        logger.info(f"   📋 message: {result['message']}")

        # In order to be compatible with the front end, the review_id field (equal to task_id) is also returned.
        result["review_id"] = result["task_id"]
        logger.info(f"   📋 review_id (Compatible fields): {result['review_id']}")

        # Perform review in the background
        logger.info(f"🚀 [Transaction review routing] Start background task execution...")
        logger.info(f"   📋 This will be executed asynchronously in the background without blocking the current request")

        asyncio.create_task(
            unified_service.execute_trade_review(
                task_id=result["task_id"],
                user_id=current_user["id"],
                request=request
            )
        )
        logger.info(f"✅ [Transaction review routing] Background task started")
        logger.info(f"   📋 The client can pass /api/v1/analysis/tasks/{result['task_id']} Query progress")
        logger.info(f"=" * 60)

        return ok(data=result, message="The transaction review task has been submitted and is expected to take 1-3 minutes to complete.")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create transaction review: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create a replica: {str(e)}")


@router.get("/trade/history", response_model=Dict[str, Any])
async def get_review_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    code: Optional[str] = Query(None, description="Stock code filter"),
    start_date: Optional[str] = Query(None, description="start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="end date YYYY-MM-DD"),
    review_type: Optional[str] = Query(None, description="Review type filter"),
    source: Optional[str] = Query(None, description="Data source filtering: paper(simulated trading) or position(Position operation)"),
    current_user: dict = Depends(get_current_user)
):
    """Obtain the review history list and support filtering by stock code, time period, review type, and data source."""
    try:
        service = get_trade_review_service()
        result = await service.get_review_history(
            user_id=current_user["id"],
            page=page,
            page_size=page_size,
            code=code,
            start_date=start_date,
            end_date=end_date,
            review_type=review_type,
            source=source
        )
        return ok(result)
    except Exception as e:
        logger.error(f"Failed to obtain review history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trade/{review_id}", response_model=Dict[str, Any])
async def get_review_detail(
    review_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get review details"""
    try:
        service = get_trade_review_service()
        result = await service.get_review_detail(
            user_id=current_user["id"],
            review_id=review_id
        )
        if not result:
            raise HTTPException(status_code=404, detail="The review report does not exist")
        
        return ok({
            "review_id": result.review_id,
            "review_type": result.review_type.value,
            "status": result.status.value,
            "trade_info": result.trade_info.model_dump(),
            "market_snapshot": result.market_snapshot.model_dump(),
            "ai_review": result.ai_review.model_dump(),
            "is_case_study": result.is_case_study,
            "tags": result.tags,
            "execution_time": result.execution_time,
            "created_at": result.created_at.isoformat() if result.created_at else None,
            "trading_system_id": result.trading_system_id,  # 🆕 Add trading plan ID
            "trading_system_name": result.trading_system_name  # 🆕 Add trading plan name
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to obtain review details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Review summary (for stock details page use) ====================

@router.get("/summary", response_model=Dict[str, Any])
async def get_review_summary(
    code: str = Query(..., description="Stock code (e.g. 601919)"),
    current_user: dict = Depends(get_current_user)
):
    """Get the latest review summary by stock code (for display on the stock details page)"""
    try:
        logger.info(f"[review.py] get_review_summary called: code={code}, user_id={current_user.get('id')}")
        service = get_trade_review_service()
        result = await service.get_review_summary_by_stock(
            user_id=current_user["id"],
            stock_code=code
        )
        return ok(result or {"has": False})
    except Exception as e:
        logger.error(f"Failed to obtain review summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Case library ====================

@router.post("/case", response_model=Dict[str, Any])
async def save_as_case(
    request: SaveAsCaseRequest,
    current_user: dict = Depends(get_current_user)
):
    """Save as case"""
    try:
        logger.info(f"📝 [save case] Request received: review_id={request.review_id}, user_id={current_user.get('id')}, tags={request.tags}, source={request.source}")
        service = get_trade_review_service()
        success = await service.save_as_case(
            user_id=current_user["id"],
            review_id=request.review_id,
            tags=request.tags,
            source=request.source  # Pass the source parameter
        )
        if not success:
            logger.warning(f"⚠️ [save case] The review report does not exist: review_id={request.review_id}")
            raise HTTPException(status_code=404, detail="The review report does not exist")
        logger.info(f"✅ [save case] success: review_id={request.review_id}")
        return ok({"message": "Saved as case"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [save case] failed: review_id={request.review_id}, error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases", response_model=Dict[str, Any])
async def get_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    source: str = Query(None, description="Data source filtering: paper(simulated trading) or position(Position operation)"),
    current_user: dict = Depends(get_current_user)
):
    """Get case library"""
    try:
        service = get_trade_review_service()
        result = await service.get_cases(
            user_id=current_user["id"],
            page=page,
            page_size=page_size,
            source=source
        )
        return ok(result)
    except Exception as e:
        logger.error(f"Failed to obtain case library: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/case/{review_id}", response_model=Dict[str, Any])
async def delete_case(
    review_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Remove from case library"""
    try:
        service = get_trade_review_service()
        success = await service.delete_case(
            user_id=current_user["id"],
            review_id=review_id
        )
        if not success:
            raise HTTPException(status_code=404, detail="Case does not exist")
        return ok({"message": "Removed from case library"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete case failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/trade/{review_id}", response_model=Dict[str, Any])
async def delete_review(
    review_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete review record"""
    try:
        service = get_trade_review_service()
        success = await service.delete_review(
            user_id=current_user["id"],
            review_id=review_id
        )
        if not success:
            raise HTTPException(status_code=404, detail="The review record does not exist")
        return ok({"message": "The review record has been deleted"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete redo record: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Transaction statistics ====================

@router.get("/statistics", response_model=Dict[str, Any])
async def get_trading_statistics(
    start_date: Optional[str] = Query(None, description="start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="end date YYYY-MM-DD"),
    current_user: dict = Depends(get_current_user)
):
    """Get transaction statistics"""
    try:
        service = get_trade_review_service()
        stats = await service.get_trading_statistics(
            user_id=current_user["id"],
            start_date=start_date,
            end_date=end_date
        )
        return ok(stats.model_dump())
    except Exception as e:
        logger.error(f"Failed to obtain transaction statistics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Periodic review ====================

@router.post("/periodic", response_model=Dict[str, Any])
async def create_periodic_review(
    request: CreatePeriodicReviewRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a staged review

    - **period_type**: Review cycle type (week/month/quarter/year)
    - **start_date**: start date YYYY-MM-DD
    - **end_date**: end date YYYY-MM-DD
    """
    try:
        service = get_trade_review_service()
        result = await service.create_periodic_review(
            user_id=current_user["id"],
            request=request
        )
        return ok({
            "review_id": result.review_id,
            "status": result.status.value,
            "period_type": result.period_type.value,
            "period_start": result.period_start.isoformat() if result.period_start else None,
            "period_end": result.period_end.isoformat() if result.period_end else None,
            "statistics": result.statistics.model_dump() if result.statistics else None,
            "ai_review": result.ai_review.model_dump() if result.ai_review else None,
            "execution_time": result.execution_time,
            "created_at": result.created_at.isoformat() if result.created_at else None
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create staged review: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create staged review: {str(e)}")


@router.get("/periodic/history", response_model=Dict[str, Any])
async def get_periodic_review_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    source: str = Query(None, description="Data source filtering: paper(simulated trading) or position(Position operation)"),
    current_user: dict = Depends(get_current_user)
):
    """Get the periodic review history list"""
    try:
        service = get_trade_review_service()
        result = await service.get_periodic_review_history(
            user_id=current_user["id"],
            page=page,
            page_size=page_size,
            source=source
        )
        return ok(result)
    except Exception as e:
        logger.error(f"Failed to obtain phased review history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodic/{review_id}", response_model=Dict[str, Any])
async def get_periodic_review_detail(
    review_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get details of periodic review"""
    try:
        service = get_trade_review_service()
        result = await service.get_periodic_review_detail(
            user_id=current_user["id"],
            review_id=review_id
        )
        if not result:
            raise HTTPException(status_code=404, detail="The periodic review report does not exist")

        return ok({
            "review_id": result.review_id,
            "period_type": result.period_type.value,
            "period_start": result.period_start.isoformat() if result.period_start else None,
            "period_end": result.period_end.isoformat() if result.period_end else None,
            "statistics": result.statistics.model_dump() if result.statistics else None,
            "trades_summary": [t.model_dump() for t in result.trades_summary],
            "ai_review": result.ai_review.model_dump() if result.ai_review else None,
            "status": result.status.value,
            "execution_time": result.execution_time,
            "created_at": result.created_at.isoformat() if result.created_at else None
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to obtain phased review details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Reviewable transaction inquiry ====================

@router.get("/reviewable-trades", response_model=Dict[str, Any])
async def get_reviewable_trades(
    code: Optional[str] = Query(None, description="Stock code filter"),
    start_date: Optional[str] = Query(None, description="start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="end date YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a list of transactions that can be reviewed

    Returns the user s selling transaction record, which can be used to select a review
    Supports filtering by stock code and time period
    """
    try:
        from app.core.database import get_mongo_db
        from datetime import datetime
        db = get_mongo_db()

        # Build query conditions
        query = {"user_id": current_user["id"]}
        if code:
            query["code"] = code

        # Time period filter
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
            if end_date:
                # The end date includes today, so add one day
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
                query["timestamp"]["$lte"] = end_dt

        skip = (page - 1) * page_size

        # Get transaction records
        cursor = db["paper_trades"].find(query).sort("timestamp", -1).skip(skip).limit(page_size)
        trades = await cursor.to_list(None)
        total = await db["paper_trades"].count_documents(query)

        # Format results
        items = []
        for t in trades:
            items.append({
                "trade_id": str(t.get("_id")),
                "code": t.get("code"),
                "market": t.get("market", "CN"),
                "side": t.get("side"),
                "quantity": t.get("quantity"),
                "price": t.get("price"),
                "amount": t.get("amount"),
                "pnl": t.get("pnl", 0),
                "timestamp": t.get("timestamp")
            })

        # Statistics grouped by stocks (using the same filters)
        code_stats = {}
        all_trades = await db["paper_trades"].find(query).to_list(None)
        for t in all_trades:
            c = t.get("code")
            if c not in code_stats:
                code_stats[c] = {
                    "name": "",
                    "market": t.get("market", "CN"),
                    "buy_count": 0,
                    "sell_count": 0,
                    "total_pnl": 0,
                    "total_buy_amount": 0,
                    "total_sell_amount": 0,
                    "last_trade_time": None
                }
            if t.get("side") == "buy":
                code_stats[c]["buy_count"] += 1
                code_stats[c]["total_buy_amount"] += t.get("amount", 0)
            else:
                code_stats[c]["sell_count"] += 1
                code_stats[c]["total_sell_amount"] += t.get("amount", 0)
                code_stats[c]["total_pnl"] += t.get("pnl", 0)

            # Update last transaction time
            trade_time = t.get("timestamp")
            if trade_time:
                # 🔥 Handle dates of string type (MongoDB may return strings)
                if isinstance(trade_time, str):
                    trade_time = datetime.fromisoformat(trade_time.replace('Z', '+00:00'))
                
                # Make sure last_trade_time is also of type datetime
                last_trade_time = code_stats[c]["last_trade_time"]
                if last_trade_time and isinstance(last_trade_time, str):
                    last_trade_time = datetime.fromisoformat(last_trade_time.replace('Z', '+00:00'))
                
                if not last_trade_time or trade_time > last_trade_time:
                    code_stats[c]["last_trade_time"] = trade_time

        # Get the stock name (first from stock_basic_info, secondly from paper_positions)
        for c in code_stats.keys():
            # 1. Get it from stock_basic_info first (most reliable)
            stock_info = await db["stock_basic_info"].find_one({"code": c})
            if stock_info and stock_info.get("name"):
                code_stats[c]["name"] = stock_info.get("name", "")
            else:
                # 2. Downgrade: obtained from paper_positions
                pos = await db["paper_positions"].find_one({"user_id": current_user["id"], "code": c})
                if pos and pos.get("name"):
                    code_stats[c]["name"] = pos.get("name", "")

        # Find stocks that have completed transactions (bought and sold)
        completed_stocks = [
            {"code": c, **stats}
            for c, stats in code_stats.items()
            if stats["buy_count"] > 0 and stats["sell_count"] > 0
        ]

        # All traded stocks (including those that have only been bought but not sold)
        # status Judgment: Only when the selling quantity >= The position is considered to be completely closed when the quantity is purchased.
        all_stocks = [
            {"code": c, "status": "completed" if stats["sell_count"] >= stats["buy_count"] and stats["sell_count"] > 0 else "holding", **stats}
            for c, stats in code_stats.items()
            if stats["buy_count"] > 0
        ]

        return ok({
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "completed_stocks": completed_stocks,
            "all_stocks": all_stocks  # New: All traded stocks
        })

    except Exception as e:
        logger.error(f"Failed to obtain resumable transactions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades-by-code/{code}", response_model=Dict[str, Any])
async def get_trades_by_code(
    code: str,
    source: str = Query("real", description="data source: real(User positions) or paper(Simulated position)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all transaction records of a certain stock

    Used to select transactions to be reviewed
    - source=real: Get user position operation records from position_changes
    - source=paper: Get simulated trading records from paper_trades
    """
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()

        items = []

        if source == "paper":
            # Simulated position: obtained from paper_trades
            logger.info(f"📊 Get simulated transaction records: {code}")
            cursor = db["paper_trades"].find({
                "user_id": current_user["id"],
                "code": code
            }).sort("timestamp", 1)

            trades = await cursor.to_list(None)

            for t in trades:
                items.append({
                    "trade_id": str(t.get("_id")),
                    "code": t.get("code"),
                    "market": t.get("market", "CN"),
                    "side": t.get("side"),
                    "quantity": t.get("quantity"),
                    "price": t.get("price"),
                    "amount": t.get("amount"),
                    "pnl": t.get("pnl", 0),
                    "commission": t.get("commission", 0),
                    "timestamp": t.get("timestamp")
                })
        else:
            # User positions: conversion from position_changes
            logger.info(f"📊 Obtain user position operation records: {code}")
            cursor = db["position_changes"].find({
                "user_id": current_user["id"],
                "code": code
            }).sort("created_at", 1)

            changes = await cursor.to_list(None)
            for c in changes:
                # Convert position_change to trade format
                change_type = c.get("change_type")
                side = "buy" if change_type in ["buy", "add"] else "sell"
                quantity = abs(c.get("quantity_change", 0))
                price = c.get("trade_price") or c.get("cost_price_after", 0)

                # Handle timestamp: use trade_time (actual trade time)
                trade_time = c.get("trade_time")
                if trade_time:
                    # 🔥 Handling type: trade_time may be a string or datetime object
                    if isinstance(trade_time, str):
                        try:
                            # Try to parse ISO format string
                            trade_time = datetime.fromisoformat(trade_time.replace('Z', '+00:00'))
                        except (ValueError, AttributeError):
                            # If parsing fails, try other formats
                            try:
                                trade_time = datetime.strptime(trade_time, "%Y-%m-%d %H:%M:%S")
                            except ValueError:
                                logger.warning(f"⚠️ Unable to parse trade_time format: {trade_time}")
                                trade_time = None
                    # If it is a datetime object, convert it to an ISO format string
                    if isinstance(trade_time, datetime):
                        timestamp_str = trade_time.isoformat()
                    else:
                        timestamp_str = None
                else:
                    timestamp_str = None

                # Handling pnl: Make sure it is a number, it cannot be None
                pnl = c.get("realized_profit")
                if pnl is None:
                    pnl = 0.0

                items.append({
                    "trade_id": str(c.get("_id")),
                    "code": c.get("code"),
                    "market": c.get("market", "CN"),
                    "side": side,
                    "quantity": quantity,
                    "price": price,
                    "amount": quantity * price,
                    "pnl": float(pnl),
                    "commission": 0.0,
                    "timestamp": timestamp_str,
                    "change_type": change_type,
                    "quantity_after": c.get("quantity_after"),
                    "created_at": c.get("created_at").isoformat() if c.get("created_at") else None
                })

        # Calculate summary
        total_buy_qty = sum(t["quantity"] for t in items if t["side"] == "buy")
        total_sell_qty = sum(t["quantity"] for t in items if t["side"] == "sell")
        total_pnl = sum(t["pnl"] or 0 for t in items)  # Handling None values

        return ok({
            "code": code,
            "trades": items,
            "summary": {
                "total_trades": len(items),
                "total_buy_quantity": total_buy_qty,
                "total_sell_quantity": total_sell_qty,
                "total_pnl": round(total_pnl, 2),
                "is_closed": total_sell_qty >= total_buy_qty and total_buy_qty > 0
            }
        })

    except Exception as e:
        logger.error(f"Failed to obtain stock transaction records: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
