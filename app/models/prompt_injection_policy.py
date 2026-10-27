"""
Prompt Inject strategy data model

press Agent + Scenario fine control context injection rules:
- Whether to inject industry/stock portraits
- Injection granularity (none/summary/full)
- Whether to inherit the industry portrait (individual stock scenario)
- Does it come with ability blocks?
- Which field to inject into the template
"""

from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict

from app.utils.timezone import now_tz


class PromptInjectionPolicy(BaseModel):
    """
    Prompt Injection strategy
    
    Corresponding design documents §7.2, Control how different Agents inject context in different scenarios.
    """
    agent_type: str = Field(..., description="Agent Type, such as analysts_v2")
    agent_name: str = Field(..., description="Agent name, such as market_analyst_v2")
    scope: str = Field(
        default="general",
        description="scene: general / industry / stock"
    )
    enabled: bool = Field(default=True, description="Whether to enable")
    injection_mode: str = Field(
        default="summary",
        description="Injection granularity: none / summary / full"
    )
    inherit_industry_for_stock: bool = Field(
        default=True,
        description="Whether to inherit industry portraits when analyzing individual stocks"
    )
    include_capability_block: bool = Field(
        default=True,
        description="Whether to include a capability boundary description block"
    )
    include_external_gap_notice: bool = Field(
        default=True,
        description="Whether it comes with external dependency reminder"
    )
    include_comparable_companies: bool = Field(
        default=True,
        description="Whether to inject comparable companies"
    )
    inject_position: str = Field(
        default="analysis_requirements",
        description="Which template field to inject into: system_prompt / analysis_requirements / constraints"
    )
    version: int = Field(default=1, description="version number")
    created_at: Optional[datetime] = Field(default_factory=now_tz)
    updated_at: Optional[datetime] = Field(default_factory=now_tz)

    model_config = ConfigDict(populate_by_name=True)


# === Request/Response model ===

class PromptInjectionPolicyCreate(BaseModel):
    """Create policy request"""
    agent_type: str = Field(..., description="Agent Type")
    agent_name: str = Field(..., description="Agent Name")
    scope: str = Field(default="general", description="scene")
    enabled: bool = True
    injection_mode: str = "summary"
    inherit_industry_for_stock: bool = True
    include_capability_block: bool = True
    include_external_gap_notice: bool = True
    include_comparable_companies: bool = True
    inject_position: str = "analysis_requirements"


class PromptInjectionPolicyUpdate(BaseModel):
    """Update policy request (all fields optional)"""
    enabled: Optional[bool] = None
    injection_mode: Optional[str] = None
    inherit_industry_for_stock: Optional[bool] = None
    include_capability_block: Optional[bool] = None
    include_external_gap_notice: Optional[bool] = None
    include_comparable_companies: Optional[bool] = None
    inject_position: Optional[str] = None
