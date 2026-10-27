"""
Internal message data API routing
Provide query, search and management interface for internal messages
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field

from app.services.internal_message_service import (
    get_internal_message_service,
    InternalMessageQueryParams,
    InternalMessageStats
)
from app.core.response import ok

router = APIRouter(prefix="/api/internal-messages", tags=["internal-messages"])


class InternalMessage(BaseModel):
    """Internal message model"""
    message_id: str
    message_type: str  # research_report/insider_info/analyst_note/meeting_minutes/internal_analysis
    title: str
    content: str
    summary: Optional[str] = ""
    source: Dict[str, Any]
    category: str
    subcategory: Optional[str] = ""
    tags: Optional[List[str]] = []
    importance: str = "medium"
    impact_scope: str = "stock_specific"
    time_sensitivity: str = "medium_term"
    confidence_level: float = Field(0.5, ge=0.0, le=1.0)
    sentiment: Optional[str] = "neutral"
    sentiment_score: Optional[float] = 0.0
    keywords: Optional[List[str]] = []
    risk_factors: Optional[List[str]] = []
    opportunities: Optional[List[str]] = []
    related_data: Optional[Dict[str, Any]] = {}
    access_level: str = "internal"
    permissions: Optional[List[str]] = []
    created_time: datetime
    effective_time: Optional[datetime] = None
    expiry_time: Optional[datetime] = None
    language: str = "zh-CN"
    data_source: str = "internal_system"


class InternalMessageBatchRequest(BaseModel):
    """Save internal message requests in batches"""
    symbol: str = Field(..., description="Stock code")
    messages: List[InternalMessage] = Field(..., description="Internal message list")


class InternalMessageQueryRequest(BaseModel):
    """Internal message query request"""
    symbol: Optional[str] = None
    symbols: Optional[List[str]] = None
    message_type: Optional[str] = None
    category: Optional[str] = None
    source_type: Optional[str] = None
    department: Optional[str] = None
    author: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    importance: Optional[str] = None
    access_level: Optional[str] = None
    min_confidence: Optional[float] = None
    rating: Optional[str] = None
    keywords: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    limit: int = Field(50, ge=1, le=1000)
    skip: int = Field(0, ge=0)


@router.post("/save", response_model=dict)
async def save_internal_messages(request: InternalMessageBatchRequest):
    """Save internal messages in batches"""
    try:
        service = await get_internal_message_service()
        
        # Convert message format and add stock symbol
        messages = []
        for msg in request.messages:
            message_dict = msg.dict()
            message_dict["symbol"] = request.symbol
            messages.append(message_dict)
        
        # save message
        result = await service.save_internal_messages(messages)
        
        return ok(data=result,
            message=f"Saved successfully {result['saved']} internal news"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save internal message: {str(e)}")


@router.post("/query", response_model=dict)
async def query_internal_messages(request: InternalMessageQueryRequest):
    """Check inside information"""
    try:
        service = await get_internal_message_service()
        
        # Build query parameters
        params = InternalMessageQueryParams(
            symbol=request.symbol,
            symbols=request.symbols,
            message_type=request.message_type,
            category=request.category,
            source_type=request.source_type,
            department=request.department,
            author=request.author,
            start_time=request.start_time,
            end_time=request.end_time,
            importance=request.importance,
            access_level=request.access_level,
            min_confidence=request.min_confidence,
            rating=request.rating,
            keywords=request.keywords,
            tags=request.tags,
            limit=request.limit,
            skip=request.skip
        )
        
        # Execute query
        messages = await service.query_internal_messages(params)
        
        return ok(data={
                "messages": messages,
                "count": len(messages),
                "params": request.dict()
            },
            message=f"Found {len(messages)} internal news"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query internal information: {str(e)}")


@router.get("/latest/{symbol}", response_model=dict)
async def get_latest_messages(
    symbol: str,
    message_type: Optional[str] = Query(None, description="Message type"),
    access_level: Optional[str] = Query(None, description="access level"),
    limit: int = Query(20, ge=1, le=100, description="Return quantity")
):
    """Get the latest inside news"""
    try:
        service = await get_internal_message_service()
        messages = await service.get_latest_messages(symbol, message_type, access_level, limit)
        
        return ok(data={
                "messages": messages,
                "count": len(messages),
                "symbol": symbol,
                "message_type": message_type,
                "access_level": access_level
            },
            message=f"Get {len(messages)} latest news"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get latest news: {str(e)}")


@router.get("/search", response_model=dict)
async def search_messages(
    query: str = Query(..., description="Search keywords"),
    symbol: Optional[str] = Query(None, description="Stock code"),
    access_level: Optional[str] = Query(None, description="access level"),
    limit: int = Query(50, ge=1, le=200, description="Return quantity")
):
    """Full-text search for inside information"""
    try:
        service = await get_internal_message_service()
        messages = await service.search_messages(query, symbol, access_level, limit)
        
        return ok(data={
                "messages": messages,
                "count": len(messages),
                "query": query,
                "symbol": symbol,
                "access_level": access_level
            },
            message=f"Searched for {len(messages)} related news"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search message failed: {str(e)}")


@router.get("/research-reports/{symbol}", response_model=dict)
async def get_research_reports(
    symbol: str,
    department: Optional[str] = Query(None, description="Department"),
    limit: int = Query(20, ge=1, le=100, description="Return quantity")
):
    """Get research report"""
    try:
        service = await get_internal_message_service()
        reports = await service.get_research_reports(symbol, department, limit)
        
        return ok(data={
                "reports": reports,
                "count": len(reports),
                "symbol": symbol,
                "department": department
            },
            message=f"Get {len(reports)} research reports"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to obtain research report: {str(e)}")


@router.get("/analyst-notes/{symbol}", response_model=dict)
async def get_analyst_notes(
    symbol: str,
    author: Optional[str] = Query(None, description="analyst"),
    limit: int = Query(20, ge=1, le=100, description="Return quantity")
):
    """Get analyst notes"""
    try:
        service = await get_internal_message_service()
        notes = await service.get_analyst_notes(symbol, author, limit)
        
        return ok(data={
                "notes": notes,
                "count": len(notes),
                "symbol": symbol,
                "author": author
            },
            message=f"Get {len(notes)} analyst notes"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get analyst notes: {str(e)}")


@router.get("/statistics", response_model=dict)
async def get_statistics(
    symbol: Optional[str] = Query(None, description="Stock code"),
    hours_back: int = Query(24, ge=1, le=168, description="Lookback hours")
):
    """Get internal message statistics"""
    try:
        service = await get_internal_message_service()
        
        # Calculation time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)
        
        stats = await service.get_internal_statistics(symbol, start_time, end_time)
        
        return ok(data={
                "statistics": stats.__dict__,
                "symbol": symbol,
                "time_range": {
                    "start_time": start_time,
                    "end_time": end_time,
                    "hours_back": hours_back
                }
            },
            message="Statistics obtained successfully"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to obtain statistics: {str(e)}")


@router.get("/message-types", response_model=dict)
async def get_message_types():
    """Get a list of supported message types"""
    message_types = [
        {
            "code": "research_report",
            "name": "research report",
            "description": "In-depth research analysis report"
        },
        {
            "code": "insider_info",
            "name": "Insider information",
            "description": "Important information obtained internally"
        },
        {
            "code": "analyst_note",
            "name": "Analyst Notes",
            "description": "Analyst views and notes"
        },
        {
            "code": "meeting_minutes",
            "name": "meeting minutes",
            "description": "Minutes of important meetings"
        },
        {
            "code": "internal_analysis",
            "name": "internal analysis",
            "description": "Analytical results from internal team"
        }
    ]
    
    return ok(data={
            "message_types": message_types,
            "count": len(message_types)
        },
        message="Message type list obtained successfully"
    )


@router.get("/categories", response_model=dict)
async def get_categories():
    """Get a list of supported categories"""
    categories = [
        {
            "code": "fundamental_analysis",
            "name": "fundamental analysis",
            "description": "Analysis related to company fundamentals"
        },
        {
            "code": "technical_analysis",
            "name": "technical analysis",
            "description": "Technical indicators and chart analysis"
        },
        {
            "code": "market_sentiment",
            "name": "market sentiment",
            "description": "Market sentiment and investor behavior analysis"
        },
        {
            "code": "risk_assessment",
            "name": "risk assessment",
            "description": "Investment risk assessment and management"
        }
    ]
    
    return ok(data={
            "categories": categories,
            "count": len(categories)
        },
        message="Category list obtained successfully"
    )


@router.get("/health", response_model=dict)
async def health_check():
    """health check"""
    try:
        service = await get_internal_message_service()
        
        # Simple connection test
        collection = await service._get_collection()
        count = await collection.estimated_document_count()
        
        return ok(data={
                "status": "healthy",
                "total_messages": count,
                "service": "internal_message_service"
            },
            message="Internal messaging service is running normally"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")
