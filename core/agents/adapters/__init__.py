"""
agent adapter

Adapt an existing functional agent to a BaseAgent subclass

⚠️ Obsolete warning:
- All v1.0 Agents (without the _v2 suffix) are deprecated and will be removed in a future release.
- Please use the corresponding v2 version (such as MarketAnalystV2 instead of MarketAnalystAgent).
- v1 Agent Still retained to support backward compatibility, but should not be used in new code.
"""

import logging
import warnings
from .legacy_adapter import LegacyAgentAdapter

logger = logging.getLogger(__name__)

# 🔥 Issue module-level deprecation warnings
warnings.warn(
    "v1.0 Agent (without _v2 suffix) is deprecated, please use v2 version."
    "v1 Agent Will be removed in TradingAgentsCN v4.0.",
    DeprecationWarning,
    stacklevel=2
)
from .market_analyst import MarketAnalystAgent
from .market_analyst_v2 import MarketAnalystV2
from .news_analyst import NewsAnalystAgent
from .fundamentals_analyst import FundamentalsAnalystAgent
from .fundamentals_analyst_v2 import FundamentalsAnalystAgentV2
from .etf_analyst_v2 import EtfAnalystAgentV2
from .social_analyst import SocialMediaAnalystAgent
from .sector_analyst import SectorAnalystAgent
from .index_analyst import IndexAnalystAgent

# v2.0 Based on base class Agent
from .bull_researcher_v2 import BullResearcherV2
from .bear_researcher_v2 import BearResearcherV2
from .research_manager_v2 import ResearchManagerV2
from .risk_manager_v2 import RiskManagerV2
from .trader_v2 import TraderV2
from .news_analyst_v2 import NewsAnalystV2
from .social_analyst_v2 import SocialMediaAnalystV2
from .sector_analyst_v2 import SectorAnalystV2
from .index_analyst_v2 import IndexAnalystV2
from .risky_analyst_v2 import RiskyAnalystV2
from .safe_analyst_v2 import SafeAnalystV2
from .neutral_analyst_v2 import NeutralAnalystV2
from .risk_self_debate_v2 import RiskSelfDebateV2
from .chip_distribution_analyst_v2 import ChipDistributionAnalystV2

# Review related intelligence agents (v1 & v2)
from .review import (
    # v1.0
    TimingAnalystAgent,
    PositionAnalystAgent,
    EmotionAnalystAgent,
    AttributionAnalystAgent,
    ReviewManagerAgent,
    # v2.0
    TimingAnalystV2,
    PositionAnalystV2,
    EmotionAnalystV2,
    AttributionAnalystV2,
    ReviewManagerV2,
)

# Intelligent agents related to position analysis (v1 & v2)
from .position import (
    # v1.0
    TechnicalAnalystAgent,
    FundamentalAnalystAgent,
    RiskAssessorAgent,
    ActionAdvisorAgent,
    # v2.0
    TechnicalAnalystV2,
    FundamentalAnalystV2,
    RiskAssessorV2,
    ActionAdvisorV2,
)

__all__ = [
    "LegacyAgentAdapter",
    "MarketAnalystAgent",
    "MarketAnalystV2",
    "NewsAnalystAgent",
    "FundamentalsAnalystAgent",
    "FundamentalsAnalystAgentV2",
    "SocialMediaAnalystAgent",
    "SectorAnalystAgent",
    "IndexAnalystAgent",
    # v2.0 Based on base class Agent
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
    "RiskSelfDebateV2",
    # Review related (v1)
    "TimingAnalystAgent",
    "PositionAnalystAgent",
    "EmotionAnalystAgent",
    "AttributionAnalystAgent",
    "ReviewManagerAgent",
    # Review related (v2)
    "TimingAnalystV2",
    "PositionAnalystV2",
    "EmotionAnalystV2",
    "AttributionAnalystV2",
    "ReviewManagerV2",
    # Position analysis related (v1)
    "TechnicalAnalystAgent",
    "FundamentalAnalystAgent",
    "RiskAssessorAgent",
    "ActionAdvisorAgent",
    # Position analysis related (v2)
    "TechnicalAnalystV2",
    "FundamentalAnalystV2",
    "RiskAssessorV2",
    "ActionAdvisorV2",
]


# ============================================================
# Automatically register new analysts to AnalystRegistry
# ============================================================

def _register_new_analysts():
    """
    Register new analyst to AnalystRegistry

    These analysts do not require tool call loops, execute directly and return results
    
    🔥 v3.0: Unified use of BUILTIN_AGENTS metadata registration with _v2 suffix,
    v1 DEPRECATED is no longer used agent_id
    """
    from ..analyst_registry import get_analyst_registry
    from ..config import BUILTIN_AGENTS

    registry = get_analyst_registry()

    # Registered sector analyst v2
    if "sector_analyst_v2" in BUILTIN_AGENTS:
        registry.register(
            "sector_analyst_v2",
            agent_class=SectorAnalystAgent,
            metadata=BUILTIN_AGENTS["sector_analyst_v2"],
            override=True
        )

    # Register as a market analyst v2
    if "index_analyst_v2" in BUILTIN_AGENTS:
        registry.register(
            "index_analyst_v2",
            agent_class=IndexAnalystAgent,
            metadata=BUILTIN_AGENTS["index_analyst_v2"],
            override=True
        )

    # Register review related intelligent agent v2 to AnalystRegistry
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
                override=True
            )

    # Register position analysis related intelligent agent v2 to AnalystRegistry
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
                override=True
            )

    # Also registered to AgentRegistry (for workflow engine)
    from ..registry import get_registry
    agent_registry = get_registry()

    all_workflow_agents = review_agents + position_agents
    for agent_id, agent_class in all_workflow_agents:
        if agent_id in BUILTIN_AGENTS:
            try:
                agent_registry.register(agent_class, override=True)
                logger.info(f"✅ [AgentRegistry] Register agent: {agent_id}")
            except Exception as e:
                logger.warning(f"⚠️ [AgentRegistry] Registration failed {agent_id}: {e}")


# Automatically register when module is loaded
_register_new_analysts()

