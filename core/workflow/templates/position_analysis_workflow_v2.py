"""
Position analysis workflow template v2.0

Multi-dimensional analysis of position status, including:
1. Technical Analyst v2.0 - Analyze trend structure, technical signals and verification points
2. Fundamental Analyst v2.0 - Analyze financial data, valuation levels, industry status
3. Risk Assessor v2.0 - Assess position risks and scenario changes
4. Position Research Integrator v2.0 - Comprehensive analysis to form research judgments and observations
"""

from ..models import (
    WorkflowDefinition,
    NodeDefinition,
    EdgeDefinition,
    NodeType,
    EdgeType,
    Position,
)


POSITION_ANALYSIS_WORKFLOW_V2 = WorkflowDefinition(
    id="position_analysis_v2",
    name="Position research process v2.0",
    description="Position research process based on v2.0 Agent architecture. Technical research and fundamental research are performed in parallel, followed by risk review, and finally compiled by research integrators to form position research observations.",
    version="2.0.0",
    is_template=True,
    tags=["v2.0", "Position", "Research", "multidimensional", "risk review"],
    config={
        "workflow_type": "position_analysis",
        "parallel_analysts": True,
        "output_format": "structured_report",
    },
    nodes=[
        # start node
        NodeDefinition(
            id="start",
            type=NodeType.START,
            label="start",
            position=Position(x=300, y=50),
        ),
        # parallel start node
        NodeDefinition(
            id="parallel_start",
            type=NodeType.PARALLEL,
            label="Parallel analysis begins",
            position=Position(x=300, y=150),
        ),
        # technical analyst v2.0
        NodeDefinition(
            id="pa_technical_v2",
            type=NodeType.ANALYST,
            agent_id="pa_technical_v2",
            label="Position Technical Analyst v2.0",
            position=Position(x=100, y=300),
            config={"output_field": "technical_analysis"},
        ),
        # fundamental analyst v2.0
        NodeDefinition(
            id="pa_fundamental_v2",
            type=NodeType.ANALYST,
            agent_id="pa_fundamental_v2",
            label="Fundamental Analyst v2.0",
            position=Position(x=300, y=300),
            config={"output_field": "fundamental_analysis"},
        ),
        # Merge nodes (merge technical and fundamental analysis results)
        NodeDefinition(
            id="merge",
            type=NodeType.MERGE,
            label="Combine analysis results",
            position=Position(x=300, y=450),
        ),
        # Risk Assessor v2.0 (performed after technical and fundamental analysis)
        NodeDefinition(
            id="pa_risk_v2",
            type=NodeType.ANALYST,
            agent_id="pa_risk_v2",
            label="Position risk assessor v2.0",
            position=Position(x=300, y=550),
            config={"output_field": "risk_analysis"},
        ),
        # Position research integrator v2.0
        NodeDefinition(
            id="pa_advisor_v2",
            type=NodeType.MANAGER,
            agent_id="pa_advisor_v2",
            label="Position research integrator v2.0",
            position=Position(x=300, y=650),
            config={"output_field": "action_advice"},
        ),
        # end node
        NodeDefinition(
            id="end",
            type=NodeType.END,
            label="end",
            position=Position(x=300, y=750),
        ),
    ],
    edges=[
        # start -> Start in parallel
        EdgeDefinition(
            id="edge_start_parallel",
            source="start",
            target="parallel_start",
            type=EdgeType.NORMAL,
        ),
        # Start in parallel -> three analysts
        EdgeDefinition(
            id="edge_parallel_technical",
            source="parallel_start",
            target="pa_technical_v2",
            type=EdgeType.NORMAL,
        ),
        EdgeDefinition(
            id="edge_parallel_fundamental",
            source="parallel_start",
            target="pa_fundamental_v2",
            type=EdgeType.NORMAL,
        ),
        # two analysts -> Merger (technical and fundamental aspects are executed in parallel and then merged)
        EdgeDefinition(
            id="edge_technical_merge",
            source="pa_technical_v2",
            target="merge",
            type=EdgeType.NORMAL,
        ),
        EdgeDefinition(
            id="edge_fundamental_merge",
            source="pa_fundamental_v2",
            target="merge",
            type=EdgeType.NORMAL,
        ),
        # merge -> Risk Assessor (performed after technical and fundamental analysis)
        EdgeDefinition(
            id="edge_merge_risk",
            source="merge",
            target="pa_risk_v2",
            type=EdgeType.NORMAL,
        ),
        # risk assessor -> Position research integrator
        EdgeDefinition(
            id="edge_risk_advisor",
            source="pa_risk_v2",
            target="pa_advisor_v2",
            type=EdgeType.NORMAL,
        ),
        # Position research integrator -> end
        EdgeDefinition(
            id="edge_advisor_end",
            source="pa_advisor_v2",
            target="end",
            type=EdgeType.NORMAL,
        ),
    ],
)
