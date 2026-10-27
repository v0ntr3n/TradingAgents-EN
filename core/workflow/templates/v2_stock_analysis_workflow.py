"""
v2.0 Stock Analysis Workflow Template

Complete stock analysis process using v2.0 Agent base class architecture
"""

from ..models import (
    WorkflowDefinition,
    NodeDefinition,
    EdgeDefinition,
    NodeType,
    EdgeType,
    Position,
)


V2_STOCK_ANALYSIS_WORKFLOW = WorkflowDefinition(
    id="v2_stock_analysis",
    name="v2.0 Complete analysis flow",
    description="Single stock research and analysis process based on v2.0 Agent architecture. It includes six professional analysts who collect evidence in parallel. Two scenario researchers, optimistic and cautious, conduct multi-scenario research around the core arguments. The research manager forms a balanced research conclusion, the research integrator organizes user-readable integration opinions, the risk team adds scenarios and constraints, and finally the risk assessor gives the risk review conclusion and follow-up observation list.",
    version="2.0.0",
    is_template=True,
    workflow_type="stock_analysis",
    tags=["v2.0", "full analysis", "multi-agent", "multi-scenario research"],

    nodes=[
        # === stage 1: start ===
        NodeDefinition(
            id="start",
            type=NodeType.START,
            label="start",
            position=Position(x=400, y=0),
        ),

        # === stage 2: Parallel analysis (6 analysts working simultaneously)===
        NodeDefinition(
            id="parallel_analysts",
            type=NodeType.PARALLEL,
            label="Parallel analysis begins",
            position=Position(x=400, y=80),
            config={"description": "6 Individual v2.0 analysts analyze macro, industry, price, financial, news and sentiment evidence in parallel"},
        ),

        # 🆕 Macro Analyst (preferred position)
        NodeDefinition(
            id="index_analyst_v2",
            type=NodeType.ANALYST,
            agent_id="index_analyst_v2",
            label="Market Analyst v2.0",
            position=Position(x=50, y=160),
            config={"focus": "Market index trends, market environment, systemic risks"},
        ),
        NodeDefinition(
            id="sector_analyst_v2",
            type=NodeType.ANALYST,
            agent_id="sector_analyst_v2",
            label="Sector Analyst v2.0",
            position=Position(x=200, y=160),
            config={"focus": "Industry trends, sector rotation, peer comparison"},
        ),

        # individual stock analyst
        NodeDefinition(
            id="market_analyst_v2",
            type=NodeType.ANALYST,
            agent_id="market_analyst_v2",
            label="market analyst v2.0",
            position=Position(x=350, y=160),
            config={"focus": "Price trend, technical indicators, trading volume"},
        ),
        NodeDefinition(
            id="fundamentals_analyst_v2",
            type=NodeType.ANALYST,
            agent_id="fundamentals_analyst_v2",
            label="fundamental analyst v2.0",
            position=Position(x=500, y=160),
            config={"focus": "Financial statements, valuation metrics, profitability"},
        ),
        NodeDefinition(
            id="news_analyst_v2",
            type=NodeType.ANALYST,
            agent_id="news_analyst_v2",
            label="news analyst v2.0",
            position=Position(x=650, y=160),
            config={"focus": "Financial news, announcements, industry trends"},
        ),
        NodeDefinition(
            id="social_analyst_v2",
            type=NodeType.ANALYST,
            agent_id="social_analyst_v2",
            label="social media analyst v2.0",
            position=Position(x=800, y=160),
            config={"focus": "Social media sentiment and public opinion popularity"},
        ),

        # Combine analysis results
        NodeDefinition(
            id="merge_analysts",
            type=NodeType.MERGE,
            label="Summary analysis results",
            position=Position(x=400, y=240),
            config={"description": "Collect all analyst evidence and enter the multi-scenario research phase"},
        ),

        # === stage 3: Multi-scenario research (core innovation points)===
        NodeDefinition(
            id="debate",
            type=NodeType.DEBATE,
            label="multi-scenario research",
            position=Position(x=400, y=320),
            config={
                "rounds": "auto",
                "rounds_ref": "config.depth_rounds_mapping.{analysis_depth}.debate",
                "description": "Optimistic scenario researchers and cautious scenario researchers conduct multiple rounds of debate around research evidence, assumptions, and failure conditions",
                "participants": ["bull_researcher_v2", "bear_researcher_v2"],
            },
        ),

        NodeDefinition(
            id="bull_researcher_v2",
            type=NodeType.RESEARCHER,
            agent_id="bull_researcher_v2",
            label="Optimistic Scenario Researcher v2.0",
            position=Position(x=250, y=400),
            config={"stance": "bullish", "focus": "Construct a bullish argument and explain the premise, evidence chain and potential catalysts"},
        ),

        NodeDefinition(
            id="bear_researcher_v2",
            type=NodeType.RESEARCHER,
            agent_id="bear_researcher_v2",
            label="Prudential Scenario Researcher v2.0",
            position=Position(x=550, y=400),
            config={"stance": "bearish", "focus": "Construct prudent arguments and identify vulnerabilities, counter-evidence and failure conditions"},
        ),

        # === stage 4: Research Manager Comprehensive Assessment ===
        NodeDefinition(
            id="research_manager_v2",
            type=NodeType.MANAGER,
            agent_id="research_manager_v2",
            label="research manager v2.0",
            position=Position(x=400, y=480),
            config={
                "role": "Integrate multi-scenario evidence to formulate balanced research conclusions, key disagreements, and key observations",
                "delegated_agent_ids": ["chip_distribution_analyst_v2"],
            },
        ),

        # === stage 5: Risk scenario study (3 risk analysts debate)===
        NodeDefinition(
            id="risk_debate",
            type=NodeType.DEBATE,
            label="risk scenario research",
            position=Position(x=400, y=560),
            config={
                "rounds": "auto",
                "rounds_ref": "config.depth_rounds_mapping.{analysis_depth}.risk",
                "description": "Three risk analysts, namely highly resilient, defensive and benchmark, review research conclusions from different robustness frameworks.",
                "participants": ["risky_analyst_v2", "safe_analyst_v2", "neutral_analyst_v2"],
            },
        ),

        NodeDefinition(
            id="risky_analyst_v2",
            type=NodeType.RISK,
            agent_id="risky_analyst_v2",
            label="Highly Resilient Scenario Analyst v2.0 🔥",
            position=Position(x=200, y=640),
            config={"role": "risky", "focus": "Emphasis on the strengthening conditions, catalytic evidence and high requirements for upward revision of research conclusions."},
        ),

        NodeDefinition(
            id="safe_analyst_v2",
            type=NodeType.RISK,
            agent_id="safe_analyst_v2",
            label="Defense Scenario Analyst v2.0 🛡️",
            position=Position(x=400, y=640),
            config={"role": "safe", "focus": "Emphasize the most fragile premises, key risk sources and failure conditions of research conclusions"},
        ),

        NodeDefinition(
            id="neutral_analyst_v2",
            type=NodeType.RISK,
            agent_id="neutral_analyst_v2",
            label="Baseline Scenario Analyst v2.0 ⚖️",
            position=Position(x=600, y=640),
            config={"role": "neutral", "focus": "Compare the quality of evidence, information gaps and the most secure current baseline scenario"},
        ),

        # === stage 6: Risk Assessor (Adjudication)===
        NodeDefinition(
            id="risk_manager_v2",
            type=NodeType.MANAGER,
            agent_id="risk_manager_v2",
            label="risk assessor v2.0",
            position=Position(x=400, y=720),
            config={"role": "Comprehensive three-party robustness review to form risk review conclusions, judgment constraints and adjustment conditions"},
        ),

        # === stage 7: Research integrator (generates user version conclusions after risk review)===
        NodeDefinition(
            id="trader_v2",
            type=NodeType.TRADER,
            agent_id="trader_v2",
            label="research integrator v2.0",
            position=Position(x=400, y=800),
            config={"role": "Organize the comprehensive research conclusions from the risk review into a final user-readable briefing"},
        ),

        # === stage 8: end ===
        NodeDefinition(
            id="end",
            type=NodeType.END,
            label="end",
            position=Position(x=400, y=880),
        ),
    ],
    
    edges=[
        # === stage 1: start -> Parallel analysis ===
        EdgeDefinition(id="e_start", source="start", target="parallel_analysts"),

        # === stage 2: Parallel analysis -> 6 analysts ===
        EdgeDefinition(id="e_p0", source="parallel_analysts", target="index_analyst_v2"),
        EdgeDefinition(id="e_p1", source="parallel_analysts", target="sector_analyst_v2"),
        EdgeDefinition(id="e_p2", source="parallel_analysts", target="market_analyst_v2"),
        EdgeDefinition(id="e_p3", source="parallel_analysts", target="fundamentals_analyst_v2"),
        EdgeDefinition(id="e_p4", source="parallel_analysts", target="news_analyst_v2"),
        EdgeDefinition(id="e_p5", source="parallel_analysts", target="social_analyst_v2"),

        # === stage 2: analyst -> Merge nodes ===
        EdgeDefinition(id="e_m0", source="index_analyst_v2", target="merge_analysts"),
        EdgeDefinition(id="e_m1", source="sector_analyst_v2", target="merge_analysts"),
        EdgeDefinition(id="e_m2", source="market_analyst_v2", target="merge_analysts"),
        EdgeDefinition(id="e_m3", source="fundamentals_analyst_v2", target="merge_analysts"),
        EdgeDefinition(id="e_m4", source="news_analyst_v2", target="merge_analysts"),
        EdgeDefinition(id="e_m5", source="social_analyst_v2", target="merge_analysts"),

        # === stage 3: merge -> debate node ===
        EdgeDefinition(id="e_debate", source="merge_analysts", target="debate"),

        # === stage 3: debate node <-> Researcher (two-way, indicating multiple rounds of debate)===
        EdgeDefinition(
            id="e_d1",
            source="debate",
            target="bull_researcher_v2",
            label="Debate",
            animated=True,
        ),
        EdgeDefinition(
            id="e_d2",
            source="debate",
            target="bear_researcher_v2",
            label="Debate",
            animated=True,
        ),
        EdgeDefinition(
            id="e_d3",
            source="bull_researcher_v2",
            target="debate",
            label="respond",
            animated=True,
        ),
        EdgeDefinition(
            id="e_d4",
            source="bear_researcher_v2",
            target="debate",
            label="respond",
            animated=True,
        ),

        # === stage 4: Debate ended -> research manager ===
        EdgeDefinition(id="e_mgr", source="debate", target="research_manager_v2"),

        # === stage 5: research manager -> risk debate ===
        EdgeDefinition(id="e_to_risk_debate", source="research_manager_v2", target="risk_debate"),

        # === stage 6: risk debate <-> Three risk analysts (multiple rounds of discussions)===
        EdgeDefinition(
            id="e_rd1",
            source="risk_debate",
            target="risky_analyst_v2",
            label="high elasticity scenario",
            animated=True,
        ),
        EdgeDefinition(
            id="e_rd2",
            source="risk_debate",
            target="safe_analyst_v2",
            label="defense scenario",
            animated=True,
        ),
        EdgeDefinition(
            id="e_rd3",
            source="risk_debate",
            target="neutral_analyst_v2",
            label="neutral point of view",
            animated=True,
        ),
        EdgeDefinition(
            id="e_rd4",
            source="risky_analyst_v2",
            target="risk_debate",
            label="Refute",
            animated=True,
        ),
        EdgeDefinition(
            id="e_rd5",
            source="safe_analyst_v2",
            target="risk_debate",
            label="Refute",
            animated=True,
        ),
        EdgeDefinition(
            id="e_rd6",
            source="neutral_analyst_v2",
            target="risk_debate",
            label="Refute",
            animated=True,
        ),

        # === stage 6: Risk Scenario Study Ended -> risk assessor ruling ===
        EdgeDefinition(id="e_risk_judge", source="risk_debate", target="risk_manager_v2"),

        # === stage 7: risk assessor -> research integrator ===
        EdgeDefinition(id="e_trader", source="risk_manager_v2", target="trader_v2"),

        # === stage 8: research integrator -> end ===
        EdgeDefinition(id="e_end", source="trader_v2", target="end"),
    ],
)

