"""
Trading review agent adapter

Contains the following dedicated agents for review:
- timing_analyst: timing analyst (v1 & v2)
- position_analyst: Position Analyst (v1 & v2)
- emotion_analyst: sentiment analyst (v1 & v2)
- attribution_analyst: attribution analyst (v1 & v2)
- review_manager: Review summary expert (v1 & v2)
"""

# v1.0 Agents (Based on BaseAgent)
from .timing_analyst import TimingAnalystAgent
from .position_analyst import PositionAnalystAgent
from .emotion_analyst import EmotionAnalystAgent
from .attribution_analyst import AttributionAnalystAgent
from .review_manager import ReviewManagerAgent

# v2.0 Agents (Based on ResearcherAgent/ManagerAgent)
from .timing_analyst_v2 import TimingAnalystV2
from .position_analyst_v2 import PositionAnalystV2
from .emotion_analyst_v2 import EmotionAnalystV2
from .attribution_analyst_v2 import AttributionAnalystV2
from .review_manager_v2 import ReviewManagerV2

__all__ = [
    # v1.0
    "TimingAnalystAgent",
    "PositionAnalystAgent",
    "EmotionAnalystAgent",
    "AttributionAnalystAgent",
    "ReviewManagerAgent",
    # v2.0
    "TimingAnalystV2",
    "PositionAnalystV2",
    "EmotionAnalystV2",
    "AttributionAnalystV2",
    "ReviewManagerV2",
]

