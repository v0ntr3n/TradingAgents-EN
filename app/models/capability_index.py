from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CapabilityDocument(BaseModel):
    capability_id: str = Field(..., description="Ability unique identifier")
    registry_tool_id: Optional[str] = Field(default=None, description="If it can be bound, the corresponding registry tool_id")
    source_type: str = Field(..., description="builtin_tool / mcp_tool / skill / external_skill")
    status: str = Field(default="active", description="active / draft / disabled")
    bindable: bool = Field(default=False, description="Can it be directly bound?")
    fc_enabled: bool = Field(default=True, description="Is it allowed? function calling")
    category: str = Field(default="", description="Ability classification")
    name: str = Field(default="", description="display name")
    label: str = Field(default="", description="Tags for UI/prompt display")
    description: str = Field(default="", description="Capability description")
    when_to_use: str = Field(default="", description="Applicable scenarios")
    when_not_to_use: str = Field(default="", description="Not applicable scenarios")
    returns: str = Field(default="", description="Return structure description")
    related_tools: List[str] = Field(default_factory=list, description="Relevant abilities")
    coverage_terms: List[str] = Field(default_factory=list, description="Domain coverage keywords")
    retrieval_text: str = Field(default="", description="Write the search text to the vector library")
    data_source: str = Field(default="", description="underlying data source")
    capability_tags: List[str] = Field(default_factory=list, description="Structured capability tags")
    tool_role_hint: str = Field(default="", description="Tool role tips:primary/specialized/supporting/generic/fallback")
    output_shape: str = Field(default="", description="Output form: structured_metrics/report/text, etc.")
    preferred_for: List[str] = Field(default_factory=list, description="Preferred capability primitives")
    not_replacement_for: List[str] = Field(default_factory=list, description="Irreplaceable capability primitives")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class CapabilitySearchHit(BaseModel):
    capability: CapabilityDocument
    score: float = Field(default=0.0, description="Similarity score, the larger the score, the more relevant it is")


class CapabilityIndexSyncResult(BaseModel):
    collection_name: str
    fingerprint: str
    total_documents: int = 0
    indexed_documents: int = 0
    skipped_documents: int = 0
    vector_backend: str = ""
    sync_mode: str = "full_rebuild"
