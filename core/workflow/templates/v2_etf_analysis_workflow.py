"""
v2.0 ETF Analysis workflow template

ETF Analysis Process Simplified: ETF Analyst + market analyst + News analysts, bull-bear-free debate, single risk analysis
"""

from ..models import (
    WorkflowDefinition,
    NodeDefinition,
    EdgeDefinition,
    NodeType,
    Position,
)


V2_ETF_ANALYSIS_WORKFLOW = WorkflowDefinition(
    id="v2_etf_analysis",
    name="v2.0 ETF Analysis flow",
    description="ETF Dedicated analysis process. Includes ETF analysts (net value, size, tracking error), market analysts (technical), news analysts. No bull-bear debate, single risk analysis.",
    version="2.0.0",
    is_template=True,
    workflow_type="etf_analysis",
    tags=["v2.0", "ETF", "fund", "Simplify the process"],

    nodes=[
        NodeDefinition(
            id="start",
            type=NodeType.START,
            label="start",
            position=Position(x=400, y=0),
        ),
        NodeDefinition(
            id="parallel_analysts",
            type=NodeType.PARALLEL,
            label="Parallel analysis",
            position=Position(x=400, y=80),
            config={"description": "ETF Analyst, Market Analyst, News Analyst"},
        ),
        NodeDefinition(
            id="etf_analyst_v2",
            type=NodeType.ANALYST,
            agent_id="etf_analyst_v2",
            label="ETF analyst v2",
            position=Position(x=200, y=160),
            config={"focus": "Net worth, scale, fee rate, tracking index, tracking error"},
        ),
        NodeDefinition(
            id="market_analyst_v2",
            type=NodeType.ANALYST,
            agent_id="market_analyst_v2",
            label="market analyst v2",
            position=Position(x=400, y=160),
            config={"focus": "Price trend, technical indicators"},
        ),
        NodeDefinition(
            id="news_analyst_v2",
            type=NodeType.ANALYST,
            agent_id="news_analyst_v2",
            label="news analyst v2",
            position=Position(x=600, y=160),
            config={"focus": "ETF/Index related news"},
        ),
        NodeDefinition(
            id="merge_analysts",
            type=NodeType.MERGE,
            label="Summary analysis",
            position=Position(x=400, y=240),
            config={"description": "Collect ETF, market, news analysis reports"},
        ),
        NodeDefinition(
            id="research_manager_v2",
            type=NodeType.MANAGER,
            agent_id="research_manager_v2",
            label="research manager v2",
            position=Position(x=400, y=320),
            config={"role": "Comprehensive analysis report to form research conclusions"},
        ),
        NodeDefinition(
            id="trader_v2",
            type=NodeType.TRADER,
            agent_id="trader_v2",
            label="research integrator v2",
            position=Position(x=400, y=400),
            config={"role": "Generate a user version of the research brief"},
        ),
        NodeDefinition(
            id="safe_analyst_v2",
            type=NodeType.RISK,
            agent_id="safe_analyst_v2",
            label="risk analyst v2",
            position=Position(x=400, y=480),
            config={"role": "safe", "focus": "Tracking error, liquidity, scale risk"},
        ),
        NodeDefinition(
            id="risk_manager_v2",
            type=NodeType.MANAGER,
            agent_id="risk_manager_v2",
            label="risk assessor v2.0",
            position=Position(x=400, y=560),
            config={"role": "comprehensive risk assessment"},
        ),
        NodeDefinition(
            id="end",
            type=NodeType.END,
            label="end",
            position=Position(x=400, y=640),
        ),
    ],

    edges=[
        EdgeDefinition(id="e_start", source="start", target="parallel_analysts"),
        EdgeDefinition(id="e_p0", source="parallel_analysts", target="etf_analyst_v2"),
        EdgeDefinition(id="e_p1", source="parallel_analysts", target="market_analyst_v2"),
        EdgeDefinition(id="e_p2", source="parallel_analysts", target="news_analyst_v2"),
        EdgeDefinition(id="e_m0", source="etf_analyst_v2", target="merge_analysts"),
        EdgeDefinition(id="e_m1", source="market_analyst_v2", target="merge_analysts"),
        EdgeDefinition(id="e_m2", source="news_analyst_v2", target="merge_analysts"),
        EdgeDefinition(id="e_mgr", source="merge_analysts", target="research_manager_v2"),
        EdgeDefinition(id="e_trader", source="research_manager_v2", target="trader_v2"),
        EdgeDefinition(id="e_risk", source="trader_v2", target="safe_analyst_v2"),
        EdgeDefinition(id="e_risk_mgr", source="safe_analyst_v2", target="risk_manager_v2"),
        EdgeDefinition(id="e_end", source="risk_manager_v2", target="end"),
    ],
)
