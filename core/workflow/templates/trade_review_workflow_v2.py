"""
Transaction review workflow template v2.0

Multi-dimensional analysis and transaction review, including:
1. Timing Analyst v2.0 - Review entry and exit basis
2. Position Analyst v2.0 - Review position management and risk exposure
3. Emotional Analyst v2.0 - Review of emotional control and discipline execution
4. Attribution Analyst v2.0 - Analyze revenue sources and replicability
5. Review Summarizer v2.0 - Comprehensive summary of review conclusions and improvement directions
"""

from ..models import (
    WorkflowDefinition,
    NodeDefinition,
    EdgeDefinition,
    NodeType,
    EdgeType,
    Position,
)


TRADE_REVIEW_WORKFLOW_V2 = WorkflowDefinition(
    id="trade_review_v2",
    name="Transaction review process v2.0",
    description="Transaction review process based on v2.0 Agent architecture. The timing review, position review, emotional review and attribution review are performed in parallel. Finally, the review summary expert summarizes the review conclusions and improvement items.",
    version="2.0.0",
    is_template=True,
    tags=["v2.0", "Review", "multidimensional", "Parallel review"],
    config={
        "workflow_type": "trade_review",
        "parallel_analysts": True,
        "output_format": "structured_report",
    },
    nodes=[
        # start node
        NodeDefinition(
            id="start",
            type=NodeType.START,
            label="start",
            position=Position(x=400, y=50),
        ),
        # parallel start node
        NodeDefinition(
            id="parallel_start",
            type=NodeType.PARALLEL,
            label="Parallel analysis begins",
            position=Position(x=400, y=150),
        ),
        # timing analyst v2.0
        NodeDefinition(
            id="timing_analyst_v2",
            type=NodeType.ANALYST,
            agent_id="timing_analyst_v2",
            label="timing analyst v2.0",
            position=Position(x=100, y=300),
            config={"output_field": "timing_analysis"},
        ),
        # Position Analyst v2.0
        NodeDefinition(
            id="position_analyst_v2",
            type=NodeType.ANALYST,
            agent_id="position_analyst_v2",
            label="Position Analyst v2.0",
            position=Position(x=300, y=300),
            config={"output_field": "position_analysis"},
        ),
        # sentiment analyst v2.0
        NodeDefinition(
            id="emotion_analyst_v2",
            type=NodeType.ANALYST,
            agent_id="emotion_analyst_v2",
            label="sentiment analyst v2.0",
            position=Position(x=500, y=300),
            config={"output_field": "emotion_analysis"},
        ),
        # attribution analyst v2.0
        NodeDefinition(
            id="attribution_analyst_v2",
            type=NodeType.ANALYST,
            agent_id="attribution_analyst_v2",
            label="attribution analyst v2.0",
            position=Position(x=700, y=300),
            config={"output_field": "attribution_analysis"},
        ),
        # Merge nodes
        NodeDefinition(
            id="merge",
            type=NodeType.MERGE,
            label="Combine analysis results",
            position=Position(x=400, y=450),
        ),
        # Review summary expert v2.0
        NodeDefinition(
            id="review_manager_v2",
            type=NodeType.MANAGER,
            agent_id="review_manager_v2",
            label="Review summary expert v2.0",
            position=Position(x=400, y=550),
            config={"output_field": "review_summary"},
        ),
        # end node
        NodeDefinition(
            id="end",
            type=NodeType.END,
            label="end",
            position=Position(x=400, y=650),
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
        # Start in parallel -> four analysts
        EdgeDefinition(
            id="edge_parallel_timing",
            source="parallel_start",
            target="timing_analyst_v2",
            type=EdgeType.NORMAL,
        ),
        EdgeDefinition(
            id="edge_parallel_position",
            source="parallel_start",
            target="position_analyst_v2",
            type=EdgeType.NORMAL,
        ),
        EdgeDefinition(
            id="edge_parallel_emotion",
            source="parallel_start",
            target="emotion_analyst_v2",
            type=EdgeType.NORMAL,
        ),
        EdgeDefinition(
            id="edge_parallel_attribution",
            source="parallel_start",
            target="attribution_analyst_v2",
            type=EdgeType.NORMAL,
        ),
        # four analysts -> merge
        EdgeDefinition(
            id="edge_timing_merge",
            source="timing_analyst_v2",
            target="merge",
            type=EdgeType.NORMAL,
        ),
        EdgeDefinition(
            id="edge_position_merge",
            source="position_analyst_v2",
            target="merge",
            type=EdgeType.NORMAL,
        ),
        EdgeDefinition(
            id="edge_emotion_merge",
            source="emotion_analyst_v2",
            target="merge",
            type=EdgeType.NORMAL,
        ),
        EdgeDefinition(
            id="edge_attribution_merge",
            source="attribution_analyst_v2",
            target="merge",
            type=EdgeType.NORMAL,
        ),
        # merge -> Review summary expert
        EdgeDefinition(
            id="edge_merge_manager",
            source="merge",
            target="review_manager_v2",
            type=EdgeType.NORMAL,
        ),
        # Review summary expert -> end
        EdgeDefinition(
            id="edge_manager_end",
            source="review_manager_v2",
            target="end",
            type=EdgeType.NORMAL,
        ),
    ],
)
