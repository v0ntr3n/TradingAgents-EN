"""
Collaborative runtime model

Unified description of internal call requests and results among Assistant, Workflow, and Agent.
Provide a minimally consistent runtime contract for subsequent cross-module collaboration.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Returns UTC time, the unified internal runtime time base."""
    return datetime.now(timezone.utc)


class CollaborationRuntimeModel(BaseModel):
    """Compatible with the basic serialization capabilities of Pydantic v1/v2."""

    def to_python_dict(self) -> Dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump(mode="python")
        return self.dict()


class InvocationSourceType(str, Enum):
    """Internal call source type."""

    EXTERNAL_USER = "external_user"
    ASSISTANT = "assistant"
    WORKFLOW = "workflow"
    AGENT = "agent"
    SYSTEM = "system"


class InvocationTargetType(str, Enum):
    """Internal call target type."""

    AGENT = "agent"
    WORKFLOW = "workflow"
    TOOL = "tool"


class InvocationStatus(str, Enum):
    """Internal call execution status."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class InvocationProvenance(CollaborationRuntimeModel):
    """Call source context."""

    source_type: InvocationSourceType
    source_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    thread_id: Optional[str] = None
    workflow_id: Optional[str] = None
    step_id: Optional[str] = None
    trigger: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InvocationPolicy(CollaborationRuntimeModel):
    """Execute strategy."""

    idempotency_key: str
    timeout_seconds: int = 180
    lane: str = "default"
    allow_partial: bool = False
    visible_to_caller: bool = True


class InvocationRequest(CollaborationRuntimeModel):
    """Unified internal call requests."""

    invocation_id: str
    target_type: InvocationTargetType
    target_id: str
    action: str = "execute"
    payload: Dict[str, Any] = Field(default_factory=dict)
    provenance: InvocationProvenance
    policy: InvocationPolicy
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class InvocationArtifactRef(CollaborationRuntimeModel):
    """Call product reference."""

    ref_type: str
    artifact_key: str
    title: str
    summary: str = ""
    source_collection: str = ""
    symbol: Optional[str] = None
    output_field: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_report_ref(self, status: Optional[str] = None) -> Dict[str, Any]:
        return {
            "ref_type": self.ref_type,
            "report_key": self.artifact_key,
            "source_collection": self.source_collection,
            "title": self.title,
            "symbol": self.symbol,
            "summary": self.summary,
            "status": status,
            "metadata": self.metadata,
            "created_at": utc_now(),
        }


class InvocationResult(CollaborationRuntimeModel):
    """Unified internal call results."""

    invocation_id: str
    target_type: InvocationTargetType
    target_id: str
    status: InvocationStatus
    started_at: datetime
    completed_at: datetime = Field(default_factory=utc_now)
    output_text: str = ""
    structured_output: Dict[str, Any] = Field(default_factory=dict)
    output_field: Optional[str] = None
    artifacts: List[InvocationArtifactRef] = Field(default_factory=list)
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status == InvocationStatus.SUCCEEDED
