"""
Workflow data model definition
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Node type"""
    START = "start"
    END = "end"
    ANALYST = "analyst"
    RESEARCHER = "researcher"
    TRADER = "trader"
    RISK = "risk"
    MANAGER = "manager"
    CONDITION = "condition"
    PARALLEL = "parallel"       # Start in parallel
    MERGE = "merge"             # Parallel merge
    DEBATE = "debate"           # Debate nodes (multiple rounds of confrontation)
    POST_PROCESSOR = "post_processor"  # Post-processor (report generation, etc.)


class EdgeType(str, Enum):
    """edge type"""
    NORMAL = "normal"
    CONDITIONAL = "conditional"


class Position(BaseModel):
    """Node position"""
    x: float = 0
    y: float = 0


class NodeDefinition(BaseModel):
    """
    Workflow node definition
    """
    id: str                          # Node is unique ID
    type: NodeType                   # Node type
    agent_id: Optional[str] = None   # associated agents ID
    label: str = ""                  # show label
    
    # location (for front-end rendering)
    position: Position = Field(default_factory=Position)
    
    # Node configuration
    config: Dict[str, Any] = Field(default_factory=dict)
    
    # Special for conditional nodes
    condition: Optional[str] = None  # conditional expression
    
    class Config:
        use_enum_values = True


class EdgeDefinition(BaseModel):
    """
    Workflow edge definition
    """
    id: str                          # Bian Weiwei ID
    source: str                      # source node ID
    target: str                      # target node ID
    type: EdgeType = EdgeType.NORMAL
    
    # Special for conditional edges
    condition: Optional[str] = None  # conditional tag (Such as "true", "false")
    
    # style
    label: Optional[str] = None
    animated: bool = False
    
    class Config:
        use_enum_values = True


class OutputStrategy(str, Enum):
    """Output assembly strategy"""
    AUTO = "auto"
    COLLECT_ALL = "collect_all"
    SPECIFIED = "specified"
    LAST_NODE = "last_node"


class OutputFieldConfig(BaseModel):
    """Configuration of individual output fields"""
    field_name: str
    display_name: str = ""
    category: str = ""
    order: int = 0
    is_primary: bool = False
    format_hint: str = "markdown"    # markdown | json_to_markdown | plain


class WorkflowOutputConfig(BaseModel):
    """Workflow output configuration"""
    strategy: OutputStrategy = OutputStrategy.AUTO
    fields: List[OutputFieldConfig] = Field(default_factory=list)
    primary_field: str = ""

    class Config:
        use_enum_values = True


# ==================== Input parameter definition ====================

class InputFieldType(str, Enum):
    """Input parameter control type"""
    STRING = "string"          # single line of text
    TEXTAREA = "textarea"      # multiline text
    NUMBER = "number"          # numbers
    BOOLEAN = "boolean"        # switch
    DATE = "date"              # date selection
    SELECT = "select"          # drop down selection
    MULTISELECT = "multiselect"  # Multiple choice


class InputFieldConfig(BaseModel):
    """Single input parameter definition"""
    name: str                                # Parameter name (key passed to the backend)
    label: str = ""                          # form display label
    type: InputFieldType = InputFieldType.STRING
    required: bool = False
    default: Optional[Any] = None            # Default value
    description: str = ""                    # Parameter description/tips
    placeholder: str = ""                    # Input box placeholder prompt
    options: Optional[List[Any]] = None      # Option list (used when selecting/multiselect)
    option_labels: Optional[List[str]] = None  # Option display name (one-to-one correspondence with options)
    min: Optional[float] = None              # numerical minimum
    max: Optional[float] = None              # numerical maximum
    group: str = ""                          # grouping labels (e.g."Basic parameters"/"Advanced parameters") 
    order: int = 0                           # sort

    class Config:
        use_enum_values = True


class WorkflowInputConfig(BaseModel):
    """Workflow input parameter configuration"""
    fields: List[InputFieldConfig] = Field(default_factory=list)

    class Config:
        use_enum_values = True


class WorkflowDefinition(BaseModel):
    """
    Workflow definition
    
    Describes a complete analysis workflow that can be serialized to JSON storage
    """
    id: str                          # workflow unique ID
    name: str                        # Workflow name
    description: str = ""            # Description
    version: str = "1.0.0"
    
    # nodes and edges
    nodes: List[NodeDefinition] = Field(default_factory=list)
    edges: List[EdgeDefinition] = Field(default_factory=list)
    
    # metadata
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[str] = None
    
    # Configuration
    config: Dict[str, Any] = Field(default_factory=dict)
    
    # Output configuration
    output_config: WorkflowOutputConfig = Field(
        default_factory=WorkflowOutputConfig
    )

    # 🆕 Input parameter configuration (define what input parameters are required for the workflow and used to dynamically generate execution forms)
    input_config: WorkflowInputConfig = Field(
        default_factory=WorkflowInputConfig
    )
    
    # label
    tags: List[str] = Field(default_factory=list)
    is_template: bool = False        # Whether it is a template
    workflow_type: Optional[str] = None  # Process type (stock_analysis/etf_analysis/position_analysis/trade_review/portfolio_health/general)
    
    def get_node(self, node_id: str) -> Optional[NodeDefinition]:
        """Get node"""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None
    
    def get_edges_from(self, node_id: str) -> List[EdgeDefinition]:
        """Get the edges starting from the specified node"""
        return [e for e in self.edges if e.source == node_id]
    
    def get_edges_to(self, node_id: str) -> List[EdgeDefinition]:
        """Get the edge pointing to the specified node"""
        return [e for e in self.edges if e.target == node_id]
    
    def get_start_node(self) -> Optional[NodeDefinition]:
        """Get the starting node"""
        for node in self.nodes:
            if node.type == NodeType.START:
                return node
        return None
    
    def get_end_nodes(self) -> List[NodeDefinition]:
        """Get the end node"""
        return [n for n in self.nodes if n.type == NodeType.END]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return self.model_dump()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowDefinition":
        """Create from dictionary"""
        return cls.model_validate(data)
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return self.model_dump_json(indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "WorkflowDefinition":
        """Create from JSON string"""
        return cls.model_validate_json(json_str)


class WorkflowExecutionState(str, Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowExecution(BaseModel):
    """
    Workflow execution record
    """
    id: str                          # execute ID
    workflow_id: str                 # Workflow ID
    state: WorkflowExecutionState = WorkflowExecutionState.PENDING
    
    # Input and output
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    
    # Node execution status
    node_states: Dict[str, str] = Field(default_factory=dict)
    current_node: Optional[str] = None
    
    # Timestamp
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # error message
    error: Optional[str] = None
    
    class Config:
        use_enum_values = True

