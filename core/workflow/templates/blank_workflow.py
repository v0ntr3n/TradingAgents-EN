"""
Blank workflow template

The simplest blank process contains only start and end nodes.
Users can freely add custom nodes on this basis to build a personalized analysis process.

Applicable scenarios:
- Custom analysis process
- Learning workflow construction
- rapid prototyping
"""

from ..models import (
    WorkflowDefinition,
    NodeDefinition,
    EdgeDefinition,
    NodeType,
    EdgeType,
    Position,
)


BLANK_WORKFLOW = WorkflowDefinition(
    id="blank_workflow",
    name="Blank process",
    description="The simplest blank workflow template, containing only start and end nodes. Users can freely add custom nodes on this basis to build a personalized analysis process. Ideal for learning workflow building or rapid prototyping.",
    version="2.0.0",  # Using v2.0 version, support v2.0 Agent
    is_template=True,
    tags=["blank", "Customize", "Template", "v2.0"],  # Add v2.0 tag to display on frontend
    
    config={
        "description": "This is a blank workflow template, you can add any nodes",
        "usage": "Click on the canvas to add nodes, drag and drop to connect the node creation process",
    },
    
    nodes=[
        # start node
        NodeDefinition(
            id="start",
            type=NodeType.START,
            label="start",
            position=Position(x=400, y=50),
            config={
                "description": "Workflow starting point",
            }
        ),
        
        # end node
        NodeDefinition(
            id="end",
            type=NodeType.END,
            label="end",
            position=Position(x=400, y=500),
            config={
                "description": "Workflow end point",
            }
        ),
    ],
    
    edges=[
        # start -> end (Direct connection by default, user can delete this edge and add intermediate nodes)
        EdgeDefinition(
            id="e_start_end",
            source="start",
            target="end",
            type=EdgeType.NORMAL,
            config={
                "description": "Default connection, intermediate nodes can be removed and added",
                "style": "dashed",  # The dotted line indicates that this is a temporary connection
            }
        ),
    ],
)

