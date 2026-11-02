from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['analysts', 'researchers', 'traders']:
    _sys.modules[f"tradingagents.core.contracts.{_sub}"] = _self_mod
    setattr(_self_mod, _sub, _self_mod)

# === analysts.py ===
# tradingagents/core/contracts/analysts.py
"""
Analyst Data Contract Definition

Define the input/output fields and dependencies of various analyst Agents
"""

from tradingagents.core.engine.data_contract import (
    AgentDataContract,
    DataAccess,
    DataLayer,
)


# =========================================
# market analyst (Market Analyst)
# =========================================
MARKET_ANALYST_CONTRACT = AgentDataContract(
    agent_id="market_analyst",
    description="Technical Analyst - Analyze price trends, technical indicators",
    inputs=[
        DataAccess(
            layer=DataLayer.CONTEXT,
            fields=["ticker", "company_name", "trade_date"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.RAW_DATA,
            fields=["price_data"],
            required=True
        ),
    ],
    outputs=[
        DataAccess(
            layer=DataLayer.ANALYSIS_DATA,
            fields=["technical"]
        ),
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=["market_report"]
        ),
    ],
    depends_on=set()  # The first stage, no dependence
)


# =========================================
# news analyst (News Analyst)
# =========================================
NEWS_ANALYST_CONTRACT = AgentDataContract(
    agent_id="news_analyst",
    description="News Analyst - Analyze news public opinion and market hot spots",
    inputs=[
        DataAccess(
            layer=DataLayer.CONTEXT,
            fields=["ticker", "company_name", "trade_date"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.RAW_DATA,
            fields=["news_data"],
            required=False  # News may not be
        ),
    ],
    outputs=[
        DataAccess(
            layer=DataLayer.ANALYSIS_DATA,
            fields=["news_sentiment"]
        ),
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=["news_report"]
        ),
    ],
    depends_on=set()
)


# =========================================
# Social Media/Sentiment Analyst (Sentiment Analyst)
# =========================================
SENTIMENT_ANALYST_CONTRACT = AgentDataContract(
    agent_id="sentiment_analyst",
    description="Sentiment Analyst - Analyze social media sentiment, investor sentiment",
    inputs=[
        DataAccess(
            layer=DataLayer.CONTEXT,
            fields=["ticker", "company_name", "trade_date"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.RAW_DATA,
            fields=["social_data"],
            required=False
        ),
    ],
    outputs=[
        DataAccess(
            layer=DataLayer.ANALYSIS_DATA,
            fields=["sentiment"]
        ),
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=["sentiment_report"]
        ),
    ],
    depends_on=set()
)


# =========================================
# fundamental analyst (Fundamentals Analyst)
# =========================================
FUNDAMENTALS_ANALYST_CONTRACT = AgentDataContract(
    agent_id="fundamentals_analyst",
    description="Fundamental Analyst - Analyzes financial data, valuation metrics",
    inputs=[
        DataAccess(
            layer=DataLayer.CONTEXT,
            fields=["ticker", "company_name", "trade_date"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.RAW_DATA,
            fields=["financial_data"],
            required=True
        ),
    ],
    outputs=[
        DataAccess(
            layer=DataLayer.ANALYSIS_DATA,
            fields=["valuation"]
        ),
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=["fundamentals_report"]
        ),
    ],
    depends_on=set()
)


# =========================================
# Sector Analyst (Sector Analyst)
# =========================================
SECTOR_ANALYST_CONTRACT = AgentDataContract(
    agent_id="sector_analyst",
    description="Sector Analyst - Analyze industry trends, sector rotation, and peer comparisons",
    inputs=[
        DataAccess(
            layer=DataLayer.CONTEXT,
            fields=["ticker", "company_name", "trade_date"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.RAW_DATA,
            fields=["sector_data", "fund_flow_data"],
            required=False
        ),
    ],
    outputs=[
        DataAccess(
            layer=DataLayer.ANALYSIS_DATA,
            fields=["sector_ranking", "fund_flow_metrics"]
        ),
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=["sector_report"]
        ),
    ],
    depends_on=set()
)


# =========================================
# Market/Index Analyst (Index Analyst)
# =========================================
INDEX_ANALYST_CONTRACT = AgentDataContract(
    agent_id="index_analyst",
    description="Market Analyst - Analyze index trends, market environment, and systemic risks",
    inputs=[
        DataAccess(
            layer=DataLayer.CONTEXT,
            fields=["trade_date", "market_type"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.RAW_DATA,
            fields=["index_data"],
            required=False
        ),
    ],
    outputs=[
        DataAccess(
            layer=DataLayer.ANALYSIS_DATA,
            fields=["market_breadth"]
        ),
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=["index_report"]
        ),
    ],
    depends_on=set()
)


# =========================================
# Analyst Contract Summary
# =========================================
ANALYST_CONTRACTS = {
    "market_analyst": MARKET_ANALYST_CONTRACT,
    "news_analyst": NEWS_ANALYST_CONTRACT,
    "sentiment_analyst": SENTIMENT_ANALYST_CONTRACT,
    "fundamentals_analyst": FUNDAMENTALS_ANALYST_CONTRACT,
    "sector_analyst": SECTOR_ANALYST_CONTRACT,
    "index_analyst": INDEX_ANALYST_CONTRACT,
}


# === researchers.py ===
# tradingagents/core/contracts/researchers.py
"""
Researcher Data Contract Definition

Define the input/output fields and dependencies of the researcher agent
Researchers need to read all analyst reports for comprehensive analysis and judgment
"""

from tradingagents.core.engine.data_contract import (
    AgentDataContract,
    DataAccess,
    DataLayer,
)


# =========================================
# See more researchers (Bull Researcher)
# =========================================
BULL_RESEARCHER_CONTRACT = AgentDataContract(
    agent_id="bull_researcher",
    description="Be bullish on researchers - comprehensively analyze reports from an optimistic perspective and find reasons to buy",
    inputs=[
        DataAccess(
            layer=DataLayer.CONTEXT,
            fields=["ticker", "company_name", "trade_date"],
            required=True
        ),
        # Read all analyst reports
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=[
                "market_report",
                "news_report",
                "sentiment_report",
                "fundamentals_report",
                "sector_report",
                "index_report",
            ],
            required=False  # Some reports may not exist
        ),
        # Read structured analysis data
        DataAccess(
            layer=DataLayer.ANALYSIS_DATA,
            fields=["technical", "valuation", "sentiment"],
            required=False
        ),
    ],
    outputs=[
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=["bull_report"]
        ),
    ],
    depends_on={
        "market_analyst",
        "news_analyst",
        "sentiment_analyst",
        "fundamentals_analyst",
    }
)


# =========================================
# bearish researcher (Bear Researcher)
# =========================================
BEAR_RESEARCHER_CONTRACT = AgentDataContract(
    agent_id="bear_researcher",
    description="Bearish researcher - Comprehensive analysis report from a cautious perspective to identify risk factors",
    inputs=[
        DataAccess(
            layer=DataLayer.CONTEXT,
            fields=["ticker", "company_name", "trade_date"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=[
                "market_report",
                "news_report",
                "sentiment_report",
                "fundamentals_report",
                "sector_report",
                "index_report",
            ],
            required=False
        ),
        DataAccess(
            layer=DataLayer.ANALYSIS_DATA,
            fields=["technical", "valuation", "sentiment"],
            required=False
        ),
    ],
    outputs=[
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=["bear_report"]
        ),
    ],
    depends_on={
        "market_analyst",
        "news_analyst",
        "sentiment_analyst",
        "fundamentals_analyst",
    }
)


# =========================================
# research manager (Research Manager)
# =========================================
RESEARCH_MANAGER_CONTRACT = AgentDataContract(
    agent_id="research_manager",
    description="Research Manager - Host long-short debates, conduct comprehensive research and judgment, and formulate investment recommendations",
    inputs=[
        DataAccess(
            layer=DataLayer.CONTEXT,
            fields=["ticker", "company_name", "trade_date"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=["bull_report", "bear_report"],
            required=True
        ),
    ],
    outputs=[
        DataAccess(
            layer=DataLayer.DECISIONS,
            fields=["investment_debate", "investment_plan"]
        ),
    ],
    depends_on={"bull_researcher", "bear_researcher"}
)


# =========================================
# Researcher Contract Summary
# =========================================
RESEARCHER_CONTRACTS = {
    "bull_researcher": BULL_RESEARCHER_CONTRACT,
    "bear_researcher": BEAR_RESEARCHER_CONTRACT,
    "research_manager": RESEARCH_MANAGER_CONTRACT,
}


# === traders.py ===
# tradingagents/core/contracts/traders.py
"""
Trader and Risk Control Data Contract Definition

Define input/output fields and dependencies for traders and risk management agents
"""

from tradingagents.core.engine.data_contract import (
    AgentDataContract,
    DataAccess,
    DataLayer,
)


# =========================================
# trader (Trader)
# =========================================
TRADER_CONTRACT = AgentDataContract(
    agent_id="trader",
    description="Research Integrator - Generates research integration opinions based on study conclusions and risk assessments",
    inputs=[
        DataAccess(
            layer=DataLayer.CONTEXT,
            fields=["ticker", "company_name", "trade_date"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.DECISIONS,
            fields=["investment_plan"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.ANALYSIS_DATA,
            fields=["technical", "valuation"],
            required=False
        ),
    ],
    outputs=[
        DataAccess(
            layer=DataLayer.DECISIONS,
            fields=["trade_signal"]
        ),
    ],
    depends_on={"research_manager"}
)


# =========================================
# Radical risk control (Risky Risk Manager)
# =========================================
RISKY_RISK_CONTRACT = AgentDataContract(
    agent_id="risky_risk",
    description="Aggressive risk control - high risk tolerance, inclined to larger positions and more aggressive operations",
    inputs=[
        DataAccess(
            layer=DataLayer.CONTEXT,
            fields=["ticker", "company_name", "trade_date"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.DECISIONS,
            fields=["trade_signal", "investment_plan"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.ANALYSIS_DATA,
            fields=["technical"],
            required=False
        ),
    ],
    outputs=[
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=["risky_risk_report"]
        ),
    ],
    depends_on={"trader"}
)


# =========================================
# Robust risk control (Safe Risk Manager)
# =========================================
SAFE_RISK_CONTRACT = AgentDataContract(
    agent_id="safe_risk",
    description="Robust risk control - low risk tolerance, leaning towards conservative positions and prudent operations",
    inputs=[
        DataAccess(
            layer=DataLayer.CONTEXT,
            fields=["ticker", "company_name", "trade_date"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.DECISIONS,
            fields=["trade_signal", "investment_plan"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.ANALYSIS_DATA,
            fields=["technical"],
            required=False
        ),
    ],
    outputs=[
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=["safe_risk_report"]
        ),
    ],
    depends_on={"trader"}
)


# =========================================
# Neutral risk control (Neutral Risk Manager)
# =========================================
NEUTRAL_RISK_CONTRACT = AgentDataContract(
    agent_id="neutral_risk",
    description="Neutral risk control - balances risk and return, favoring moderate positions",
    inputs=[
        DataAccess(
            layer=DataLayer.CONTEXT,
            fields=["ticker", "company_name", "trade_date"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.DECISIONS,
            fields=["trade_signal", "investment_plan"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.ANALYSIS_DATA,
            fields=["technical"],
            required=False
        ),
    ],
    outputs=[
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=["neutral_risk_report"]
        ),
    ],
    depends_on={"trader"}
)


# =========================================
# Risk Control Manager (Risk Manager)
# =========================================
RISK_MANAGER_CONTRACT = AgentDataContract(
    agent_id="risk_manager",
    description="Risk Control Manager - Comprehensive three risk control opinions to form the final risk assessment",
    inputs=[
        DataAccess(
            layer=DataLayer.CONTEXT,
            fields=["ticker", "company_name", "trade_date"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.REPORTS,
            fields=["risky_risk_report", "safe_risk_report", "neutral_risk_report"],
            required=True
        ),
        DataAccess(
            layer=DataLayer.DECISIONS,
            fields=["trade_signal"],
            required=True
        ),
    ],
    outputs=[
        DataAccess(
            layer=DataLayer.DECISIONS,
            fields=["risk_assessment", "final_decision"]
        ),
    ],
    depends_on={"risky_risk", "safe_risk", "neutral_risk"}
)


# =========================================
# Summary of traders and risk control contracts
# =========================================
TRADER_CONTRACTS = {
    "trader": TRADER_CONTRACT,
    "risky_risk": RISKY_RISK_CONTRACT,
    "safe_risk": SAFE_RISK_CONTRACT,
    "neutral_risk": NEUTRAL_RISK_CONTRACT,
    "risk_manager": RISK_MANAGER_CONTRACT,
}


# === __init__.py ===
# tradingagents/core/contracts/__init__.py
"""
Data contract definition module

Define data contracts for all Agents, including:
- analyst contract (analysts)
- Researcher Contract (researchers)
- Trader and Risk Control Contract (traders, risk_managers)
"""

from tradingagents.core.contracts.analysts import (
    MARKET_ANALYST_CONTRACT,
    NEWS_ANALYST_CONTRACT,
    SENTIMENT_ANALYST_CONTRACT,
    FUNDAMENTALS_ANALYST_CONTRACT,
    SECTOR_ANALYST_CONTRACT,
    INDEX_ANALYST_CONTRACT,
    ANALYST_CONTRACTS,
)
from tradingagents.core.contracts.researchers import (
    BULL_RESEARCHER_CONTRACT,
    BEAR_RESEARCHER_CONTRACT,
    RESEARCH_MANAGER_CONTRACT,
    RESEARCHER_CONTRACTS,
)
from tradingagents.core.contracts.traders import (
    TRADER_CONTRACT,
    RISKY_RISK_CONTRACT,
    SAFE_RISK_CONTRACT,
    NEUTRAL_RISK_CONTRACT,
    RISK_MANAGER_CONTRACT,
    TRADER_CONTRACTS,
)

# Summary of all contracts
ALL_CONTRACTS = {
    **ANALYST_CONTRACTS,
    **RESEARCHER_CONTRACTS,
    **TRADER_CONTRACTS,
}

__all__ = [
    # analyst contract
    "MARKET_ANALYST_CONTRACT",
    "NEWS_ANALYST_CONTRACT",
    "SENTIMENT_ANALYST_CONTRACT",
    "FUNDAMENTALS_ANALYST_CONTRACT",
    "SECTOR_ANALYST_CONTRACT",
    "INDEX_ANALYST_CONTRACT",
    "ANALYST_CONTRACTS",
    # Researcher Contract
    "BULL_RESEARCHER_CONTRACT",
    "BEAR_RESEARCHER_CONTRACT",
    "RESEARCH_MANAGER_CONTRACT",
    "RESEARCHER_CONTRACTS",
    # Trader and Risk Control Contract
    "TRADER_CONTRACT",
    "RISKY_RISK_CONTRACT",
    "SAFE_RISK_CONTRACT",
    "NEUTRAL_RISK_CONTRACT",
    "RISK_MANAGER_CONTRACT",
    "TRADER_CONTRACTS",
    # Summary
    "ALL_CONTRACTS",
]
