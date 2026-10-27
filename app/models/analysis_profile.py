"""
Industry/Stock Analysis Configuration Data Model

For context-aware prompt word injection:
- IndustryAnalysisProfile: Industry-level analysis dimensions (such as banks focusing on NIM, NPL ratio)
- StockAnalysisProfile: Dimensions of individual stock-level analysis (for example, BYD focuses on monthly sales and DM-i proportion)
"""

from datetime import datetime
from typing import Optional, List, Any, Annotated
from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer, ConfigDict
from bson import ObjectId
from app.utils.timezone import now_tz


def validate_object_id(v: Any) -> ObjectId:
    """Verify ObjectId"""
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str):
        if ObjectId.is_valid(v):
            return ObjectId(v)
    raise ValueError("Invalid ObjectId")


def serialize_object_id(v: ObjectId) -> str:
    """Serialize ObjectId to string"""
    return str(v)


PyObjectId = Annotated[
    ObjectId,
    BeforeValidator(validate_object_id),
    PlainSerializer(serialize_object_id, return_type=str),
]


class AnalysisDimension(BaseModel):
    """Analysis Dimensions"""
    name: str = Field(..., description="Dimension name, such as'net interest margin(NIM)'")
    description: str = Field(..., description="Dimension description, such as'Bank core profitability indicators'")
    importance: str = Field(default="high", description="importance: critical, high, medium, low")
    data_source: str = Field(default="fundamentals", description="Data source: fundamentals, news, technical, mixed")


class IndustryAnalysisProfile(BaseModel):
    """Industry analysis configuration"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    industry: str = Field(..., description="Industry name (aligned with the industry field of stock_basic_info)")
    display_name: str = Field(default="", description="Industry display name")
    analysis_dimensions: List[AnalysisDimension] = Field(default_factory=list, description="Industry core analysis dimensions")
    analysis_focus: str = Field(default="", description="Industry analysis highlights")
    key_metrics: List[str] = Field(default_factory=list, description="List of key indicators")
    comparable_companies: List[str] = Field(default_factory=list, description="Comparable companies in the industry")
    source: str = Field(default="system", description="Source: system, ai_generated, user")
    is_active: bool = Field(default=True, description="Whether to enable")
    created_at: datetime = Field(default_factory=now_tz, description="creation time")
    updated_at: datetime = Field(default_factory=now_tz, description="Update time")

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


class StockAnalysisProfile(BaseModel):
    """Individual stock analysis configuration (covering industry default configuration)"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    stock_symbol: str = Field(..., description="Stock code, such as 002594.SZ")
    company_name: str = Field(default="", description="Company name")
    industry: str = Field(default="", description="Industry")
    analysis_dimensions: List[AnalysisDimension] = Field(default_factory=list, description="Exclusive analysis dimensions for individual stocks")
    special_notes: str = Field(default="", description="Special instructions for individual stocks")
    source: str = Field(default="user", description="Source: system, ai_generated, user")
    is_active: bool = Field(default=True, description="Whether to enable")
    created_at: datetime = Field(default_factory=now_tz, description="creation time")
    updated_at: datetime = Field(default_factory=now_tz, description="Update time")

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


# === Request/Response model ===

class AnalysisDimensionCreate(BaseModel):
    """Create an analysis dimension request"""
    name: str
    description: str
    importance: str = "high"
    data_source: str = "fundamentals"


class IndustryProfileCreate(BaseModel):
    """Create an industry configuration request"""
    industry: str
    display_name: str = ""
    analysis_dimensions: List[AnalysisDimensionCreate] = []
    analysis_focus: str = ""
    key_metrics: List[str] = []
    comparable_companies: List[str] = []
    source: str = "user"


class IndustryProfileUpdate(BaseModel):
    """Update Industry Configuration Request"""
    display_name: Optional[str] = None
    analysis_dimensions: Optional[List[AnalysisDimensionCreate]] = None
    analysis_focus: Optional[str] = None
    key_metrics: Optional[List[str]] = None
    comparable_companies: Optional[List[str]] = None
    is_active: Optional[bool] = None


class StockProfileCreate(BaseModel):
    """Create a stock allocation request"""
    stock_symbol: str
    company_name: str = ""
    industry: str = ""
    analysis_dimensions: List[AnalysisDimensionCreate] = []
    special_notes: str = ""
    source: str = "user"


class StockProfileUpdate(BaseModel):
    """Update individual stock allocation request"""
    company_name: Optional[str] = None
    industry: Optional[str] = None
    analysis_dimensions: Optional[List[AnalysisDimensionCreate]] = None
    special_notes: Optional[str] = None
    is_active: Optional[bool] = None


class IndustryProfileResponse(BaseModel):
    """Industry configuration response"""
    id: str
    industry: str
    display_name: str
    analysis_dimensions: List[AnalysisDimension]
    analysis_focus: str
    key_metrics: List[str]
    comparable_companies: List[str]
    source: str
    is_active: bool
    created_at: str
    updated_at: str


class StockProfileResponse(BaseModel):
    """Individual stock allocation response"""
    id: str
    stock_symbol: str
    company_name: str
    industry: str
    analysis_dimensions: List[AnalysisDimension]
    special_notes: str
    source: str
    is_active: bool
    created_at: str
    updated_at: str

