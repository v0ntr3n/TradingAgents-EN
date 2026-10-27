"""
Analyze Preference Data Model
"""

from datetime import datetime
from typing import Optional, Any, Annotated
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


# Create custom ObjectId type
PyObjectId = Annotated[
    ObjectId,
    BeforeValidator(validate_object_id),
    PlainSerializer(serialize_object_id, return_type=str),
]


class AnalysisPreference(BaseModel):
    """Analytical preference model"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: PyObjectId = Field(..., description="User ID")
    preference_type: str = Field(..., description="Preference type: aggressive, neutral, conservative")
    risk_level: float = Field(default=0.5, ge=0.0, le=1.0, description="risk level 0.0-1.0")
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="confidence threshold 0.0-1.0")
    position_size_multiplier: float = Field(default=1.0, ge=0.5, le=2.0, description="Position multiple 0.5-2.0")
    decision_speed: str = Field(default="normal", description="decision speed: fast, normal, slow")
    is_default: bool = Field(default=False, description="Is it the default preference?")
    created_at: datetime = Field(default_factory=now_tz, description="creation time")
    updated_at: datetime = Field(default_factory=now_tz, description="Update time")
    
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


class AnalysisPreferenceCreate(BaseModel):
    """Create preference request"""
    preference_type: str
    risk_level: float = 0.5
    confidence_threshold: float = 0.7
    position_size_multiplier: float = 1.0
    decision_speed: str = "normal"
    is_default: bool = False


class AnalysisPreferenceUpdate(BaseModel):
    """Update preference request"""
    risk_level: Optional[float] = None
    confidence_threshold: Optional[float] = None
    position_size_multiplier: Optional[float] = None
    decision_speed: Optional[str] = None
    is_default: Optional[bool] = None


class AnalysisPreferenceResponse(BaseModel):
    """preferred response"""
    id: str
    user_id: str
    preference_type: str
    risk_level: float
    confidence_threshold: float
    position_size_multiplier: float
    decision_speed: str
    is_default: bool
    created_at: str
    updated_at: str

