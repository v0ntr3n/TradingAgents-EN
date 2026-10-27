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

