"""
Industry/Stock Analysis Configuration Management API

Provides CRUD operations and AI generation capabilities
"""

import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.analysis_profile_service import AnalysisProfileService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis-profiles", tags=["analysis-profiles"])

_service = AnalysisProfileService()


# ── Request / Response Schemas ──

class IndustryProfileCreate(BaseModel):
    industry: str = Field(..., description="Industry name")
    display_name: Optional[str] = Field(None, description="display name")
    analysis_dimensions: list = Field(default_factory=list)
    analysis_focus: str = Field("", description="Analysis focus")
    key_metrics: list = Field(default_factory=list)
    comparable_companies: list = Field(default_factory=list)
    is_active: bool = True


class AIGenerateRequest(BaseModel):
    industry: str = Field(..., description="Industry name, such as'bank', 'New energy vehicles'")
    user_request: Optional[str] = Field(default="", description="Supplementary requirements from users or revised instructions for this round")
    existing_profile: Optional[Dict[str, Any]] = Field(default=None, description="Current draft, used for multiple rounds of revisions")


# ── Industry configuration CRUD ──

@router.get("/industries")
async def list_industry_profiles(is_active: Optional[bool] = Query(None)):
    """Get a list of all industry configurations"""
    profiles = await _service.get_industry_profiles(is_active=is_active)
    return {"success": True, "data": profiles, "total": len(profiles)}


@router.get("/industries/{profile_id}")
async def get_industry_profile(profile_id: str):
    """Get configuration details of a single industry"""
    profile = await _service.get_industry_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Industry configuration does not exist")
    return {"success": True, "data": profile}


@router.post("/industries")
async def create_industry_profile(body: IndustryProfileCreate):
    """Create industry configuration"""
    data = body.model_dump()
    if not data.get("display_name"):
        data["display_name"] = f"{data['industry']}Industry"
    # Check if it already exists
    existing = await _service.get_industry_profile_by_name(data["industry"])
    if existing:
        raise HTTPException(status_code=409, detail=f"Industry '{data['industry']}' The configuration already exists, please use the update interface")
    result = await _service.create_industry_profile(data)
    return {"success": True, "data": result}


@router.put("/industries/{profile_id}")
async def update_industry_profile(profile_id: str, body: IndustryProfileCreate):
    """Update industry configuration"""
    data = body.model_dump()
    result = await _service.update_industry_profile(profile_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="The industry configuration does not exist or has not been modified.")
    return {"success": True, "data": result}


@router.delete("/industries/{profile_id}")
async def delete_industry_profile(profile_id: str):
    """Delete industry configuration"""
    deleted = await _service.delete_industry_profile(profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Industry configuration does not exist")
    return {"success": True, "message": "Deleted"}


# ── AI generate ──

@router.post("/industries/generate")
async def generate_industry_profile(body: AIGenerateRequest):
    """
    Use AI to generate industry analysis configurations

    Returns the generated configuration (unsaved), which can be saved via POST /industries after user preview
    """
    try:
        profile = await _service.generate_industry_profile_with_ai(
            body.industry,
            user_request=body.user_request or "",
            existing_profile=body.existing_profile,
        )
        return {"success": True, "data": profile}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"❌ AI Failed to generate industry configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Build failed: {str(e)}")


# ── Industry list (from stock_basic_info) ──

@router.get("/industry-list")
async def get_industry_list():
    """
    Get the industry list of all stocks in the database (from stock_basic_info.industry)

    Select matching industry names when used for front-end industry configuration to ensure alignment with actual stock data
    """
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()
        industries = await db.stock_basic_info.distinct("industry")
        # filter null values, sort
        industries = sorted([i for i in industries if i and i.strip()])
        return {"success": True, "data": industries, "total": len(industries)}
    except Exception as e:
        logger.error(f"Failed to obtain industry list: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to obtain industry list: {str(e)}")


# ── Individual stock allocation (basic CRUD) ──

@router.get("/stocks")
async def list_stock_profiles(industry: Optional[str] = Query(None)):
    """Get the stock allocation list"""
    profiles = await _service.get_stock_profiles(industry=industry)
    return {"success": True, "data": profiles, "total": len(profiles)}


@router.get("/stocks/{stock_symbol}")
async def get_stock_profile_by_symbol(stock_symbol: str):
    """Get individual stock allocation based on stock code"""
    profile = await _service.get_stock_profile_by_symbol(stock_symbol)
    if not profile:
        raise HTTPException(status_code=404, detail="Individual stock allocation does not exist")
    return {"success": True, "data": profile}

