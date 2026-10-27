"""
Intelligent system module

Provide unified agent base class, registry and factory

v2.0 new features:
- Support dynamic tool binding
- Supports LangChain LLM integration
"""

from .base import BaseAgent
from .registry import AgentRegistry, get_registry, register_agent
from .factory import AgentFactory, create_agent, create_agent_with_dynamic_tools
from .config import AgentMetadata, AgentConfig, AgentCategory, AgentMaintenanceStatus, LicenseTier, BUILTIN_AGENTS
from .universal import UniversalAgent

# v2.0 New: Agent base class
from .analyst import AnalystAgent
from .researcher import ResearcherAgent
from .manager import ManagerAgent
from .trader import TraderAgent
from .post_processor import PostProcessorAgent

# Import post-processing Agent implementation (trigger registration)
from .post_processors import (
    ReportSaverAgent,
    EmailNotifierAgent,
    SystemNotifierAgent,
    ReportGeneratorV2,
    DataPreparerV2,
)

# Import v2.0 Agent implementation (trigger registration)
from .adapters import (
    # analyst
    FundamentalsAnalystAgentV2,
    NewsAnalystV2,
    SocialMediaAnalystV2,
    SectorAnalystV2,
    IndexAnalystV2,
    # researcher
    BullResearcherV2,
    BearResearcherV2,
    # manager
    ResearchManagerV2,
    RiskManagerV2,
    # research integrator
    TraderV2,
    # risk analyst
    RiskyAnalystV2,
    SafeAnalystV2,
    NeutralAnalystV2,
    # Chip distribution analyst
    ChipDistributionAnalystV2,
)

__all__ = [
    # base class
    "BaseAgent",
    # v2.0 Agent base class
    "AnalystAgent",
    "ResearcherAgent",
    "ManagerAgent",
    "TraderAgent",
    "PostProcessorAgent",
    # Post-processing Agent
    "ReportSaverAgent",
    "EmailNotifierAgent",
    "SystemNotifierAgent",
    "ReportGeneratorV2",
    "DataPreparerV2",
    # Registry
    "AgentRegistry",
    "get_registry",
    "register_agent",
    # factory
    "AgentFactory",
    "create_agent",
    "create_agent_with_dynamic_tools",  # v2.0
    # Configuration
    "AgentMetadata",
    "AgentConfig",
    "AgentCategory",
    "AgentMaintenanceStatus",
    "LicenseTier",
    "BUILTIN_AGENTS",
    # Chip distribution analyst
    "ChipDistributionAnalystV2",
]

