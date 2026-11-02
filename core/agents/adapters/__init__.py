"""
Agent adapter module (consolidated)

All v2.0 BaseAgent subclasses and legacy compatibility adapters.
"""

import logging
import warnings

from .analysts_v2 import (
    ChipDistributionAnalystV2,
    EtfAnalystAgentV2,
    FundamentalsAnalystAgentV2,
    IndexAnalystV2,
    MarketAnalystV2,
    NewsAnalystV2,
    SectorAnalystV2,
    SocialMediaAnalystV2,
)
from .legacy_adapter import (
    ActionAdvisorAgent,
    AttributionAnalystAgent,
    EmotionAnalystAgent,
    FundamentalAnalystAgent,
    FundamentalsAnalystAgent,
    IndexAnalystAgent,
    LegacyAgentAdapter,
    MarketAnalystAgent,
    NewsAnalystAgent,
    PositionAnalystAgent,
    ReviewManagerAgent,
    RiskAssessorAgent,
    SectorAnalystAgent,
    SocialMediaAnalystAgent,
    TechnicalAnalystAgent,
    TimingAnalystAgent,
)
from .position_v2 import (
    ActionAdvisorV2,
    FundamentalAnalystV2,
    RiskAssessorV2,
    TechnicalAnalystV2,
)
from .research_and_risk_v2 import (
    BearResearcherV2,
    BullResearcherV2,
    NeutralAnalystV2,
    ResearchManagerV2,
    RiskManagerV2,
    RiskSelfDebateV2,
    RiskyAnalystV2,
    SafeAnalystV2,
    TraderV2,
)
from .review_v2 import (
    AttributionAnalystV2,
    EmotionAnalystV2,
    PositionAnalystV2,
    ReviewManagerV2,
    TimingAnalystV2,
)

logger = logging.getLogger(__name__)

warnings.warn(
    "v1.0 Agent (without _v2 suffix) is deprecated, please use v2 version."
    "v1 Agent Will be removed in TradingAgentsCN v4.0.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "LegacyAgentAdapter",
    "MarketAnalystAgent",
    "MarketAnalystV2",
    "NewsAnalystAgent",
    "FundamentalsAnalystAgent",
    "FundamentalsAnalystAgentV2",
    "EtfAnalystAgentV2",
    "SocialMediaAnalystAgent",
    "SectorAnalystAgent",
    "IndexAnalystAgent",
    "BullResearcherV2",
    "BearResearcherV2",
    "ResearchManagerV2",
    "RiskManagerV2",
    "TraderV2",
    "NewsAnalystV2",
    "SocialMediaAnalystV2",
    "SectorAnalystV2",
    "IndexAnalystV2",
    "ChipDistributionAnalystV2",
    "RiskyAnalystV2",
    "SafeAnalystV2",
    "NeutralAnalystV2",
    "RiskSelfDebateV2",
    "TimingAnalystAgent",
    "PositionAnalystAgent",
    "EmotionAnalystAgent",
    "AttributionAnalystAgent",
    "ReviewManagerAgent",
    "TimingAnalystV2",
    "PositionAnalystV2",
    "EmotionAnalystV2",
    "AttributionAnalystV2",
    "ReviewManagerV2",
    "TechnicalAnalystAgent",
    "FundamentalAnalystAgent",
    "RiskAssessorAgent",
    "ActionAdvisorAgent",
    "TechnicalAnalystV2",
    "FundamentalAnalystV2",
    "RiskAssessorV2",
    "ActionAdvisorV2",
]


def _register_new_analysts():
    """Register analysts to AnalystRegistry and AgentRegistry."""
    from ..analyst_registry import get_analyst_registry
    from ..config import BUILTIN_AGENTS
    from ..registry import get_registry

    registry = get_analyst_registry()

    if "sector_analyst_v2" in BUILTIN_AGENTS:
        registry.register(
            "sector_analyst_v2",
            agent_class=SectorAnalystAgent,
            metadata=BUILTIN_AGENTS["sector_analyst_v2"],
            override=True,
        )

    if "index_analyst_v2" in BUILTIN_AGENTS:
        registry.register(
            "index_analyst_v2",
            agent_class=IndexAnalystAgent,
            metadata=BUILTIN_AGENTS["index_analyst_v2"],
            override=True,
        )

    review_agents = [
        ("timing_analyst_v2", TimingAnalystAgent),
        ("position_analyst_v2", PositionAnalystAgent),
        ("emotion_analyst_v2", EmotionAnalystAgent),
        ("attribution_analyst_v2", AttributionAnalystAgent),
        ("review_manager_v2", ReviewManagerAgent),
    ]

    for agent_id, agent_class in review_agents:
        if agent_id in BUILTIN_AGENTS:
            registry.register(
                agent_id,
                agent_class=agent_class,
                metadata=BUILTIN_AGENTS[agent_id],
                override=True,
            )

    position_agents = [
        ("pa_technical_v2", TechnicalAnalystAgent),
        ("pa_fundamental_v2", FundamentalAnalystAgent),
        ("pa_risk_v2", RiskAssessorAgent),
        ("pa_advisor_v2", ActionAdvisorAgent),
    ]

    for agent_id, agent_class in position_agents:
        if agent_id in BUILTIN_AGENTS:
            registry.register(
                agent_id,
                agent_class=agent_class,
                metadata=BUILTIN_AGENTS[agent_id],
                override=True,
            )

    agent_registry = get_registry()
    for agent_id, agent_class in review_agents + position_agents:
        if agent_id in BUILTIN_AGENTS:
            try:
                agent_registry.register(agent_class, override=True)
            except Exception as e:
                logger.warning(f"⚠️ [AgentRegistry] Registration failed {agent_id}: {e}")


_register_new_analysts()
