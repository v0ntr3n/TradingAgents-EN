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

