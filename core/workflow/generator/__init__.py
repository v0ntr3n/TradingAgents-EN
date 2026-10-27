"""
AI Smart Workflow Builder

Through natural language dialogue, combined with the Agent, Tool, Skill and prompt word templates available in the system,
Automatically generate a complete WorkflowDefinition and related bindings.
"""

from .workflow_spec import (
    WorkflowGenerationSession,
    WorkflowBlueprint,
    GenerationSessionStatus,
    ConversationRound,
    PlannedNode,
    PlannedEdge,
    AgentReshapingPlan,
    SkillCreationRequest,
    GapAnalysisResult,
)
from .resource_collector import ResourceCollector
from .workflow_planner import WorkflowPlanner
from .prompt_generator import PromptGenerator
from .skill_orchestrator import SkillOrchestrator

__all__ = [
    # data model
    "WorkflowGenerationSession",
    "WorkflowBlueprint",
    "GenerationSessionStatus",
    "ConversationRound",
    "PlannedNode",
    "PlannedEdge",
    "AgentReshapingPlan",
    "SkillCreationRequest",
    "GapAnalysisResult",
    # core module
    "ResourceCollector",
    "WorkflowPlanner",
    "PromptGenerator",
    "SkillOrchestrator",
]

