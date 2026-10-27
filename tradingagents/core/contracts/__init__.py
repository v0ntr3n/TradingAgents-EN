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

