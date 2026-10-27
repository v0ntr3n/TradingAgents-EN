"""
Workflow generation data model

Define all data structures used during AI workflow generation.
Including session status, dialogue turns, gap analysis, blueprint structure, etc.

Reference: docs/05-design/v3.0/ai-workflow-generation.md
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, PrivateAttr


# ==================== enumeration type ====================

class GenerationSessionStatus(str, Enum):
    """Workflow generates session state"""
    GATHERING = "gathering"              # Collecting requirements (conversation in progress)
    PLANNING = "planning"                # AI Planning (generating blueprint)
    BLUEPRINT_READY = "blueprint_ready"  # The blueprint has been generated and is waiting for user confirmation
    CONFIRMED = "confirmed"              # User confirmed
    COMPLETING = "completing"            # Autocomplete in progress (create Skill + Generate prompt words)
    CREATING = "creating"                # Creating workflow
    COMPLETED = "completed"              # Creation completed (draft status, needs to be published)
    PUBLISHED = "published"              # Published (the resource has been activated as the official version)
    OPTIMIZING = "optimizing"            # Iterative optimization in progress
    FAILED = "failed"                    # failed


# ==================== Basic data model ====================

class ConversationRound(BaseModel):
    """dialogue turns"""
    round_num: int = 0
    user_message: str = ""
    ai_message: str = ""
    phase: str = "gathering"             # gathering / optimizing (distinguish between creation and optimization phases)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PlannedNode(BaseModel):
    """planned node"""
    id: str
    type: str                            # start, end, analyst, researcher, trader, risk, manager,
    #                                      parallel, merge, debate, post_processor, condition
    agent_id: Optional[str] = None       # Associated Agent ID (from BUILTIN_AGENTS)
    label: str = ""
    position_x: float = 0
    position_y: float = 0
    config: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""                # AI A description of the node (displayed to the user)


class PlannedEdge(BaseModel):
    """planning edge"""
    id: str
    source: str                          # source node ID
    target: str                          # target node ID
    label: Optional[str] = None
    animated: bool = False
    type: Optional[str] = "normal"       # edge Type (normal/conditional)
    condition: Optional[str] = None      # conditional expression ("true"/"false") 


# ==================== gap analysis model ====================

class AgentReshapingPlan(BaseModel):
    """Agent Capacity reshaping plan — Change the Agent s role in the workflow through prompt words"""
    agent_id: str                        # Selected existing Agent (such as market_analyst)
    node_id: str = ""                    # 🆕 Corresponding workflow node ID (the same agent has different prompt words on different nodes)
    original_role: str = ""              # Original character description
    new_role: str = ""                   # New roles in this workflow (e.g."Convertible bond market analyst") 
    reshaping_direction: str = ""        # Briefly describe the customization direction (one sentence)
    key_focus_areas: List[str] = Field(default_factory=list)  # Key analysis dimensions (3-6 items)
    prompt_changes: Dict[str, str] = Field(default_factory=dict)  # Compatible with old formats: complete prompt word draft
    additional_tools: List[str] = Field(default_factory=list)     # Requires additional binding tools ID


class SkillCreationRequest(BaseModel):
    """Skill Automatically create requests"""
    skill_name: str                      # Desired Skill Name
    skill_description: str = ""          # Function description
    target_agent_id: str = ""            # Which to bind to Agent
    priority: str = "required"           # required / optional
    generated_skill_id: Optional[str] = None  # Backfill after successful creation
    status: str = "pending"              # pending / creating / completed / failed
    error: Optional[str] = None          # Reason for failure


class GapAnalysisResult(BaseModel):
    """Gap analysis results — AI Generated after automatic detection"""

    # Agent Capability gap (no need to create a new Agent, solved through prompt word reshaping)
    agent_reshaping: List[AgentReshapingPlan] = Field(default_factory=list)

    # Agent using default prompt words (no customization required)
    agents_using_default: List[Dict[str, str]] = Field(default_factory=list)  # [{id, name, reason}]

    # Tool/Skill gap (requires automatic creation of new Skills)
    missing_skills: List[SkillCreationRequest] = Field(default_factory=list)

    # Existing resources can be used directly
    available_agents: List[Dict[str, str]] = Field(default_factory=list)  # [{id, name, role_in_workflow}]
    available_tools: List[Dict[str, str]] = Field(default_factory=list)   # [{id, name, used_by_agent}]

    # Analysis instructions
    analysis_summary: str = ""


# ==================== blueprint model ====================

class WorkflowBlueprint(BaseModel):
    """
    AI Generated workflow blueprint — Contains structure + gap analysis + Completion plan

    After the user confirms, the system automatically generates prompt words and creates skills.
    Then convert the blueprint to WorkflowDefinition and save it.
    """

    # Basic information
    name: str = ""
    description: str = ""
    tags: List[str] = Field(default_factory=list)

    # 🛡️ Anti-hallucination: record the illegal agent_id found in the whitelist verification and its recommended replacement (PrivateAttr, does not participate in serialization)
    _invalid_agent_ids: Dict[str, str] = PrivateAttr(default_factory=dict)

    # Workflow structure
    nodes: List[PlannedNode] = Field(default_factory=list)
    edges: List[PlannedEdge] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict)

    # 🆕 Input parameter definition (the front end dynamically generates an execution form based on this field)
    input_config: Dict[str, Any] = Field(default_factory=lambda: {"fields": []})

    # AI Solution description
    summary: str = ""                    # Program overview
    rationale: str = ""                  # design ideas

    # gap analysis
    gap_analysis: Optional[GapAnalysisResult] = None

    # prompt word generation plan — Prompt word draft for each Agent that needs to be customized
    prompt_plans: List[Dict[str, Any]] = Field(default_factory=list)

    # Create progress tracking
    creation_progress: Dict[str, Any] = Field(default_factory=lambda: {
        "skills_total": 0,
        "skills_completed": 0,
        "prompts_total": 0,
        "prompts_completed": 0,
        "workflow_created": False,
    })


# ==================== session model ====================

class WorkflowGenerationSession(BaseModel):
    """
    Workflow generation session — Corresponds to the MongoDB workflow_generation_sessions collection

    Record the complete process from requirement communication to completion of workflow creation,
    Supports iterative optimization.
    """
    session_id: str
    user_id: str = ""
    status: GenerationSessionStatus = GenerationSessionStatus.GATHERING

    # Conversation record
    rounds: List[ConversationRound] = Field(default_factory=list)
    current_round: int = 0

    # AI generated blueprint
    blueprint: Optional[WorkflowBlueprint] = None
    blueprint_confirmed: bool = False

    # Create results
    workflow_id: Optional[str] = None          # Workflow after successful creation ID
    created_prompt_ids: List[str] = Field(default_factory=list)  # Prompt word template created ID
    created_skill_ids: List[str] = Field(default_factory=list)   # Created Skill ID
    creation_report: Optional[Dict[str, Any]] = None  # Create reports (persistent for display during recovery)
    error: Optional[str] = None

    # Optimize records
    optimize_rounds: List[ConversationRound] = Field(default_factory=list)
    optimize_count: int = 0

    # time
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

