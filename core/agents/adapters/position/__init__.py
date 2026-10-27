"""
Position Analysis Agent Adapter

Contains the following agents:
- pa_technical: technical analyst (v1 & v2)
- pa_fundamental: fundamental analyst (v1 & v2)
- pa_risk: risk assessor (v1 & v2)
- pa_advisor: Position Research Observer (v1 & v2)
"""

# v1.0 Agents (Based on BaseAgent)
from .technical_analyst import TechnicalAnalystAgent
from .fundamental_analyst import FundamentalAnalystAgent
from .risk_assessor import RiskAssessorAgent
from .action_advisor import ActionAdvisorAgent

# v2.0 Agents (Based on ResearcherAgent/ManagerAgent)
from .technical_analyst_v2 import TechnicalAnalystV2
from .fundamental_analyst_v2 import FundamentalAnalystV2
from .risk_assessor_v2 import RiskAssessorV2
from .action_advisor_v2 import ActionAdvisorV2

__all__ = [
    # v1.0
    "TechnicalAnalystAgent",
    "FundamentalAnalystAgent",
    "RiskAssessorAgent",
    "ActionAdvisorAgent",
    # v2.0
    "TechnicalAnalystV2",
    "FundamentalAnalystV2",
    "RiskAssessorV2",
    "ActionAdvisorV2",
]

