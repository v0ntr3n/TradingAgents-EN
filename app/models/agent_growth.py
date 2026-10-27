"""
Agent Growth related data model
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field

from .user import PyObjectId
from app.utils.timezone import now_tz


class GrowthMemoryScope(str, Enum):
    """Boundary classification of long-term growth memory"""
    TASK_TEMP = "task_temp"
    OBJECT_TRACKING = "object_tracking"
    USER_PREFERENCE = "user_preference"
    RESEARCH_ASSET = "research_asset"
    PATTERN = "pattern"


class GrowthMemoryStatus(str, Enum):
    """Memory entry status"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class GrowthReviewLevel(str, Enum):
    """Audit level"""
    AUTO_PENDING = "auto_pending"
    MANUAL_REQUIRED = "manual_required"


class GrowthSuggestionStatus(str, Enum):
    """Suggestion status"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class GrowthSuggestionType(str, Enum):
    """Growth advice types"""
    MEMORY_PROMOTION = "memory_promotion"
    RESEARCH_ASSET_PROMOTION = "research_asset_promotion"
    WORKFLOW_OPTIMIZATION = "workflow_optimization"
    WATCH_RULE_SUGGESTION = "watch_rule_suggestion"


class GrowthEvidenceRef(BaseModel):
    """Growth Evidence Citations"""
    type: str
    id: str
    label: Optional[str] = None


class AgentGrowthMemoryItem(BaseModel):
    """Growth memory items"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    memory_id: str
    user_id: str
    scope: GrowthMemoryScope
    status: GrowthMemoryStatus = GrowthMemoryStatus.PENDING
    review_level: GrowthReviewLevel = GrowthReviewLevel.MANUAL_REQUIRED

    source_type: str
    source_id: str
    task_type: Optional[str] = None
    workflow_id: Optional[str] = None

    object_type: Optional[str] = None
    object_key: Optional[str] = None

    title: str
    summary: str = ""
    content: str
    structured_payload: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    evidence_refs: List[GrowthEvidenceRef] = Field(default_factory=list)

    confirmed_by: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    rejected_by: Optional[str] = None
    rejected_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str, datetime: lambda dt: dt.isoformat() if dt else None},
    )


class AgentGrowthSuggestion(BaseModel):
    """Growth advice items"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    suggestion_id: str
    user_id: str
    suggestion_type: GrowthSuggestionType
    status: GrowthSuggestionStatus = GrowthSuggestionStatus.PENDING

    source_type: str
    source_id: str
    task_type: Optional[str] = None
    workflow_id: Optional[str] = None
    object_type: Optional[str] = None
    object_key: Optional[str] = None

    title: str
    summary: str
    suggested_action: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    source_refs: List[GrowthEvidenceRef] = Field(default_factory=list)

    accepted_by: Optional[str] = None
    accepted_at: Optional[datetime] = None
    dismissed_by: Optional[str] = None
    dismissed_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str, datetime: lambda dt: dt.isoformat() if dt else None},
    )


class TaskGrowthContext(BaseModel):
    """Task-level growth extraction summary"""
    memory_items_count: int = 0
    suggestions_count: int = 0
    memory_item_ids: List[str] = Field(default_factory=list)
    suggestion_ids: List[str] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=now_tz)
    source_type: str = "unified_analysis_task"
    source_id: Optional[str] = None

    model_config = ConfigDict(
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None},
    )