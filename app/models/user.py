"""
User data model
"""

from datetime import datetime, timezone
from app.utils.timezone import now_tz
from typing import Optional, Dict, Any, Annotated, List, Union
from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer, ConfigDict, field_serializer
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema
from bson import ObjectId


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


class AssistantSettings(BaseModel):
    """Assistant personalization"""
    name: str = Field(default="Analysis Assistant", description="Assistant name")
    tone: str = Field(default="professional", description="tone style: professional/friendly/concise")
    custom_instructions: str = Field(default="", description="User-defined instructions", max_length=500)


class UserPreferences(BaseModel):
    """User preferences"""
    # Assistant personalization
    assistant_settings: AssistantSettings = Field(default_factory=AssistantSettings)

    # Analyze preferences
    default_market: str = "A shares"
    default_depth: str = "3"  # 1-5 level, level 3 is standard analysis (recommended)
    default_analysts: List[str] = Field(default_factory=lambda: ["market analyst", "fundamental analyst"])
    auto_refresh: bool = True
    refresh_interval: int = 30  # seconds
    risk_preference: str = "neutral"  # Risk Appetite:conservative(conservative) / neutral(Neutral) / aggressive(Radical)

    # Appearance settings
    ui_theme: str = "light"
    sidebar_width: int = 240

    # language and region
    language: str = "zh-CN"

    # Notification settings
    notifications_enabled: bool = True
    email_notifications: Union[bool, Dict[str, Any]] = False  # Compatible with old boolean and new dictionary formats
    desktop_notifications: bool = True
    analysis_complete_notification: bool = True
    system_maintenance_notification: bool = True


class FavoriteStock(BaseModel):
    """Stock watch list information"""
    stock_code: str = Field(..., description="Stock code")
    stock_name: str = Field(..., description="Stock name")
    market: str = Field(..., description="market type")
    added_at: datetime = Field(default_factory=now_tz, description="Add time")
    tags: List[str] = Field(default_factory=list, description="User tag")
    notes: str = Field(default="", description="User remarks")
    alert_price_high: Optional[float] = Field(None, description="price cap reminder")
    alert_price_low: Optional[float] = Field(None, description="Price lower limit reminder")


class User(BaseModel):
    """user model"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')
    hashed_password: str
    is_active: bool = True
    is_verified: bool = False
    is_admin: bool = False
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)
    last_login: Optional[datetime] = None
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    
    # Quotas and limits
    daily_quota: int = 1000
    concurrent_limit: int = 3
    
    # Statistics
    total_analyses: int = 0
    successful_analyses: int = 0
    failed_analyses: int = 0

    # Stock Watchlist
    favorite_stocks: List[FavoriteStock] = Field(default_factory=list, description="User stock watch list list")
    
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


class UserCreate(BaseModel):
    """Create user request model"""
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')
    password: str = Field(..., min_length=6, max_length=100)


class UserUpdate(BaseModel):
    """Update user request model"""
    email: Optional[str] = Field(None, pattern=r'^[^@]+@[^@]+\.[^@]+$')
    preferences: Optional[UserPreferences] = None
    daily_quota: Optional[int] = None
    concurrent_limit: Optional[int] = None


class UserResponse(BaseModel):
    """User response model"""
    id: str
    username: str
    email: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login: Optional[datetime]
    preferences: UserPreferences
    daily_quota: int
    concurrent_limit: int
    total_analyses: int
    successful_analyses: int
    failed_analyses: int

    @field_serializer('created_at', 'last_login')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        """Serialize datetime to ISO 8601 format, preserving time zone information"""
        if dt:
            return dt.isoformat()
        return None


class UserLogin(BaseModel):
    """User login request model"""
    username: str
    password: str


class UserSession(BaseModel):
    """User session model"""
    session_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    last_activity: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    @field_serializer('created_at', 'expires_at', 'last_activity')
    def serialize_datetime(self, dt: Optional[datetime], _info) -> Optional[str]:
        """Serialize datetime to ISO 8601 format, preserving time zone information"""
        if dt:
            return dt.isoformat()
        return None


class TokenResponse(BaseModel):
    """Token response model"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    user: UserResponse
