"""
mem0 unified memory layer — data model

Define the externally exposed data structure of MemoryService and decouple it from the internal implementation of mem0.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _compact_text(text: str, max_chars: int = 220) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


class MemoryScope(str, Enum):
    """memory scope — Implement classification filtering through mem0 metadata"""

    CONVERSATION = "conversation"
    USER_PREFERENCE = "user_preference"
    ANALYSIS_INSIGHT = "analysis_insight"
    SKILL_LESSON = "skill_lesson"
    AGENT_BUILDER_LESSON = "agent_builder_lesson"
    AGENT_EXPERIENCE = "agent_experience"
    TRADE_PATTERN = "trade_pattern"


class MemoryObjectType(str, Enum):
    """Types of objects in long-term memory"""

    STOCK = "stock"


class StockAnalysisMemory(BaseModel):
    """Objectized stock analysis memory"""

    object_type: str = MemoryObjectType.STOCK
    memory_kind: str = "stock_analysis"
    symbol: str
    market: str = ""
    analysis_date: str = ""
    summary: str = ""
    recommendation: str = ""
    task_id: str = ""
    source_agent: str = "workflow_analyst"
    evidence: List[str] = Field(default_factory=list)
    next_checks: List[str] = Field(default_factory=list)

    def object_key(self) -> str:
        market = str(self.market or "").strip().lower() or "cn"
        symbol = str(self.symbol or "").strip().upper()
        return f"{market}:{symbol}"

    def to_metadata(self) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "object_type": self.object_type,
            "memory_kind": self.memory_kind,
            "object_key": self.object_key(),
            "symbol": str(self.symbol or "").strip().upper(),
            "market": str(self.market or "").strip().lower() or "cn",
            "analysis_date": str(self.analysis_date or "").strip(),
            "summary": _compact_text(self.summary, 400),
            "recommendation": _compact_text(self.recommendation, 220),
            "task_id": str(self.task_id or "").strip(),
            "source_agent": str(self.source_agent or "").strip() or "workflow_analyst",
        }
        if self.evidence:
            metadata["evidence"] = [
                _compact_text(item, 160)
                for item in self.evidence[:5]
                if str(item or "").strip()
            ]
        if self.next_checks:
            metadata["next_checks"] = [
                _compact_text(item, 160)
                for item in self.next_checks[:5]
                if str(item or "").strip()
            ]
        return metadata

    def to_memory_text(self) -> str:
        parts = [f"object={self.object_key()}"]
        if self.analysis_date:
            parts.append(f"Date={self.analysis_date}")
        if self.summary:
            parts.append(f"Conclusion={_compact_text(self.summary, 220)}")
        if self.recommendation:
            parts.append(f"Suggestions={_compact_text(self.recommendation, 160)}")
        return "；".join(parts)


class MemoryItem(BaseModel):
    """mem0 Single memory returned (normalized)"""

    id: str = ""
    memory: str = ""
    user_id: str = ""
    agent_id: str = ""
    scope: str = ""
    score: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    object_type: str = ""
    object_key: str = ""
    symbol: str = ""
    market: str = ""
    memory_kind: str = ""

    @classmethod
    def from_mem0(cls, raw: dict, default_scope: str = "") -> "MemoryItem":
        """Normalize the dict returned by mem0 SDK to MemoryItem"""
        meta = raw.get("metadata") or {}
        return cls(
            id=str(raw.get("id") or ""),
            memory=str(raw.get("memory") or ""),
            user_id=str(raw.get("user_id") or meta.get("user_id") or ""),
            agent_id=str(raw.get("agent_id") or meta.get("agent_id") or meta.get("source_agent") or ""),
            scope=str(meta.get("scope") or default_scope or ""),
            score=float(raw.get("score") or 0.0),
            metadata=meta,
            created_at=str(raw.get("created_at") or ""),
            updated_at=str(raw.get("updated_at") or ""),
            object_type=str(meta.get("object_type") or ""),
            object_key=str(meta.get("object_key") or ""),
            symbol=str(meta.get("symbol") or ""),
            market=str(meta.get("market") or ""),
            memory_kind=str(meta.get("memory_kind") or ""),
        )


class StoreResult(BaseModel):
    """MemoryService.store return value"""

    memory_ids: List[str] = Field(default_factory=list)
    facts_extracted: int = 0
    success: bool = True
    error: str = ""
