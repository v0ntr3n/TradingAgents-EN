"""
Multi-market stock API routing
Supports unified query interface for A-shares, Hong Kong stocks, and US stocks

Function:
1. Cross-market stock information query
2. Multiple data source priority query
3. Unified response format

path prefix: /api/markets
"""
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
import logging

from app.routers.auth_db import get_current_user
from app.core.database import get_mongo_db
from app.core.response import ok
from app.services.unified_stock_service import UnifiedStockService

logger = logging.getLogger("webapi")

router = APIRouter(prefix="/markets", tags=["multi-market"])


@router.get("", response_model=dict)
async def get_supported_markets(current_user: dict = Depends(get_current_user)):
    """
    Get a list of supported markets
    
    Returns:
        {
            "success": true,
            "data": {
                "markets": [
                    {
                        "code": "CN",
                        "name": "A shares",
                        "name_en": "China A-Shares",
                        "currency": "CNY",
                        "timezone": "Asia/Shanghai"
                    },
                    ...
                ]
            }
        }
    """
    markets = [
        {
            "code": "CN",
            "name": "A shares",
            "name_en": "China A-Shares",
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
            "trading_hours": "09:30-15:00"
        },
        {
            "code": "HK",
            "name": "Hong Kong stocks",
            "name_en": "Hong Kong Stocks",
            "currency": "HKD",
            "timezone": "Asia/Hong_Kong",
            "trading_hours": "09:30-16:00"
        },
        {
            "code": "US",
            "name": "US stocks",
            "name_en": "US Stocks",
            "currency": "USD",
            "timezone": "America/New_York",
            "trading_hours": "09:30-16:00 EST"
        }
    ]
    
    return ok(data={"markets": markets})


@router.get("/{market}/stocks/search", response_model=dict)
async def search_stocks(
    market: str,
    q: str = Query(..., description="Search keyword (code or name)"),
    limit: int = Query(20, ge=1, le=100, description="Number of results returned"),
    current_user: dict = Depends(get_current_user)
):
    """
    Search for stocks (multi-market supported)
    
    Args:
        market: market type (CN/HK/US)
        q: Search keywords
        limit: Number of results returned
    
    Returns:
        {
            "success": true,
            "data": {
                "stocks": [
                    {
                        "code": "00700",
                        "name": "Tencent Holdings",
                        "name_en": "Tencent Holdings",
                        "market": "HK",
                        "source": "yfinance",
                        ...
                    }
                ],
                "total": 1
            }
        }
    """
    market = market.upper()
    if market not in ["CN", "HK", "US"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported market type: {market}"
        )
    
    db = get_mongo_db()
    service = UnifiedStockService(db)
    
    try:
        results = await service.search_stocks(market, q, limit)
        return ok(data={
            "stocks": results,
            "total": len(results)
        })
    except Exception as e:
        logger.error(f"❌ Stock search failed: market={market}, q={q}, error={e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/{market}/stocks/{code}/info", response_model=dict)
async def get_stock_info(
    market: str,
    code: str,
    source: Optional[str] = Query(None, description="Specify data source (optional)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Obtain basic stock information (supports multiple markets and multiple data sources)
    
    Args:
        market: market type (CN/HK/US)
        code: Stock code
        source: Specify the data source (optional, if not specified, it will be automatically selected according to priority)
    
    Returns:
        {
            "success": true,
            "data": {
                "code": "00700",
                "name": "Tencent Holdings",
                "name_en": "Tencent Holdings",
                "market": "HK",
                "source": "yfinance",
                "total_mv": 32000.0,
                "pe": 25.5,
                "pb": 4.2,
                "lot_size": 100,
                "currency": "HKD",
                ...
            }
        }
    """
    market = market.upper()
    if market not in ["CN", "HK", "US"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported market type: {market}"
        )
    
    db = get_mongo_db()
    service = UnifiedStockService(db)
    
    try:
        stock_info = await service.get_stock_info(market, code, source)
        
        if not stock_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No stock found: {market}:{code}"
            )
        
        return ok(data=stock_info)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to obtain stock information: market={market}, code={code}, error={e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain stock information: {str(e)}"
        )


@router.get("/{market}/stocks/{code}/quote", response_model=dict)
async def get_stock_quote(
    market: str,
    code: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get real-time stock quotes (supports multiple markets)
    
    Args:
        market: market type (CN/HK/US)
        code: Stock code
    
    Returns:
        {
            "success": true,
            "data": {
                "code": "00700",
                "close": 320.50,
                "pct_chg": 2.15,
                "open": 315.00,
                "high": 325.00,
                "low": 312.00,
                "volume": 48500000,
                "amount": 15800000000,
                "trade_date": "2024-01-15",
                "currency": "HKD",
                ...
            }
        }
    """
    market = market.upper()
    if market not in ["CN", "HK", "US"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported market type: {market}"
        )
    
    db = get_mongo_db()
    service = UnifiedStockService(db)
    
    try:
        quote = await service.get_stock_quote(market, code)
        
        if not quote:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No stock quotes found: {market}:{code}"
            )
        
        return ok(data=quote)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get stock quotes: market={market}, code={code}, error={e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stock quotes: {str(e)}"
        )


@router.get("/{market}/stocks/{code}/daily", response_model=dict)
async def get_stock_daily_quotes(
    market: str,
    code: str,
    start_date: Optional[str] = Query(None, description="start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="end date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="Return the number of records"),
    current_user: dict = Depends(get_current_user)
):
    """
    Obtain stock historical K-line data (supports multiple markets)
    
    Args:
        market: market type (CN/HK/US)
        code: Stock code
        start_date: start date
        end_date: end date
        limit: Return the number of records
    
    Returns:
        {
            "success": true,
            "data": {
                "code": "00700",
                "market": "HK",
                "quotes": [
                    {
                        "trade_date": "2024-01-15",
                        "open": 315.00,
                        "high": 325.00,
                        "low": 312.00,
                        "close": 320.50,
                        "volume": 48500000,
                        "amount": 15800000000
                    },
                    ...
                ],
                "total": 100
            }
        }
    """
    market = market.upper()
    if market not in ["CN", "HK", "US"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported market type: {market}"
        )
    
    db = get_mongo_db()
    service = UnifiedStockService(db)
    
    try:
        quotes = await service.get_daily_quotes(
            market, code, start_date, end_date, limit
        )
        
        return ok(data={
            "code": code,
            "market": market,
            "quotes": quotes,
            "total": len(quotes)
        })
    except Exception as e:
        logger.error(f"❌ Failed to obtain historical K-line: market={market}, code={code}, error={e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to obtain historical K-line: {str(e)}"
        )

