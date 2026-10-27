"""
Single agent workflow template

Workflow for debugging or executing a single Agent
"""

from typing import Any, Dict, Optional
from ..models import (
    WorkflowDefinition,
    NodeDefinition,
    EdgeDefinition,
    NodeType,
    EdgeType,
    Position,
)


def SingleAgentWorkflow(
    agent_id: str,
    config: Optional[Dict[str, Any]] = None
) -> WorkflowDefinition:
    """
    Create a single-agent workflow template
    
    Args:
        agent_id: agent ID
        config: Workflow configuration
        
    Returns:
        WorkflowDefinition: Workflow definition
    """
    config = config or {}
    
    # Extract the Agent name as part of the workflow name
    agent_name = agent_id.replace("_", " ").title()
    
    return WorkflowDefinition(
        id=f"single_agent_{agent_id}",
        name=f"{agent_name} Workflow",
        description=f"Single agent workflow for {agent_id}",
        version="1.0.0",
        is_template=False,
        tags=["single", "debug", agent_id],
        config=config,
        
        nodes=[
            # start node
            NodeDefinition(
                id="start",
                type=NodeType.START,
                label="start",
                position=Position(x=0, y=0),
            ),
            
            # Agent node
            NodeDefinition(
                id=agent_id,
                type=NodeType.ANALYST,  # Assume they are all analysts, if not it may need to be adjusted
                agent_id=agent_id,
                label=agent_name,
                position=Position(x=200, y=0),
                config=config.get("agent_config", {})
            ),
            
            # end node
            NodeDefinition(
                id="end",
                type=NodeType.END,
                label="end",
                position=Position(x=400, y=0),
            )
        ],
        
        edges=[
            # Start -> Agent
            EdgeDefinition(
                id="edge_1",
                source="start",
                target=agent_id,
                type=EdgeType.NORMAL
            ),
            
            # Agent -> End
            EdgeDefinition(
                id="edge_2",
                source=agent_id,
                target="end",
                type=EdgeType.NORMAL
            )
        ]
    )
