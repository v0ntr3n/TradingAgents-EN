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

