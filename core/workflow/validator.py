"""
Workflow validator

Verify the correctness of the workflow definition
"""

from typing import List, Optional

from .models import (
    WorkflowDefinition,
    NodeDefinition,
    NodeType,
    EdgeType,
)


class ValidationError:
    """Validation error"""
    
    def __init__(self, code: str, message: str, node_id: Optional[str] = None):
        self.code = code
        self.message = message
        self.node_id = node_id
    
    def __str__(self):
        if self.node_id:
            return f"[{self.code}] node '{self.node_id}': {self.message}"
        return f"[{self.code}] {self.message}"


class ValidationResult:
    """Verification results"""
    
    def __init__(self):
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []
    
    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0
    
    def add_error(self, code: str, message: str, node_id: Optional[str] = None):
        self.errors.append(ValidationError(code, message, node_id))
    
    def add_warning(self, code: str, message: str, node_id: Optional[str] = None):
        self.warnings.append(ValidationError(code, message, node_id))


class WorkflowValidator:
    """
    Workflow validator

    Check:
    - There must be a start node
    - There must be at least one end node
    - All nodes must be reachable
    - The agent node must have agent_id
    - The conditional node must have a conditional expression
    - The source and target of the edge must exist
    """

    def validate(self, definition: WorkflowDefinition, strict: bool = True) -> ValidationResult:
        """
        Validate workflow definition

        Args:
            definition: Workflow definition
            strict: Whether to strictly verify (verification required before execution) strict=True, Can be saved strict=False) 
        """
        result = ValidationResult()

        self._validate_basic_structure(definition, result, strict)

        # Subsequent verification is only done when there is a node
        if definition.nodes:
            self._validate_nodes(definition, result)
            self._validate_edges(definition, result)
            self._validate_connectivity(definition, result)

        return result

    def validate_for_save(self, definition: WorkflowDefinition) -> ValidationResult:
        """Validate on save (Relaxed mode, allowing empty workflows)"""
        return self.validate(definition, strict=False)

    def validate_for_execute(self, definition: WorkflowDefinition) -> ValidationResult:
        """Verification before execution (Strict mode, must be complete)"""
        return self.validate(definition, strict=True)

    def _validate_basic_structure(
        self,
        definition: WorkflowDefinition,
        result: ValidationResult,
        strict: bool = True
    ) -> None:
        """Verify basic structure"""
        if not definition.id:
            result.add_error("MISSING_ID", "Workflow is missing ID")

        if not definition.name:
            result.add_error("MISSING_NAME", "Workflow is missing name")

        # Empty node check: only reports error in strict mode
        if not definition.nodes:
            if strict:
                result.add_error("NO_NODES", "Workflow has no nodes")
            return

        # Check the start node
        start_nodes = [n for n in definition.nodes if n.type == NodeType.START]
        if len(start_nodes) == 0:
            if strict:
                result.add_error("NO_START", "Workflow is missing start node")
        elif len(start_nodes) > 1:
            result.add_error("MULTIPLE_START", "Workflow has multiple start nodes")

        # Check end node
        end_nodes = [n for n in definition.nodes if n.type == NodeType.END]
        if len(end_nodes) == 0:
            if strict:
                result.add_error("NO_END", "Workflow is missing end node")
    
    def _validate_nodes(
        self,
        definition: WorkflowDefinition,
        result: ValidationResult
    ) -> None:
        """Verification node"""
        node_ids = set()
        
        for node in definition.nodes:
            # Check ID uniqueness
            if node.id in node_ids:
                result.add_error("DUPLICATE_NODE_ID", f"Duplicate nodes ID", node.id)
            node_ids.add(node.id)
            
            # Check the agent node (Excludes the DEBATE node, which is not required for the coordinating node agent_id)
            if node.type in (NodeType.ANALYST, NodeType.RESEARCHER,
                           NodeType.TRADER, NodeType.RISK, NodeType.MANAGER):
                if not node.agent_id:
                    result.add_error("MISSING_AGENT_ID", "Agent node is missing agent_id", node.id)
            
            # Check condition node
            if node.type == NodeType.CONDITION:
                if not node.condition:
                    result.add_warning("MISSING_CONDITION", "Conditional node is missing a conditional expression", node.id)
    
    def _validate_edges(
        self,
        definition: WorkflowDefinition,
        result: ValidationResult
    ) -> None:
        """Verify edge"""
        node_ids = {n.id for n in definition.nodes}
        edge_ids = set()
        
        for edge in definition.edges:
            # Check ID uniqueness
            if edge.id in edge_ids:
                result.add_error("DUPLICATE_EDGE_ID", f"Duplicate edges ID: {edge.id}")
            edge_ids.add(edge.id)
            
            # Check source node exists
            if edge.source not in node_ids:
                result.add_error("INVALID_SOURCE", f"The source node of the edge does not exist: {edge.source}")
            
            # Check that the target node exists
            if edge.target not in node_ids:
                result.add_error("INVALID_TARGET", f"The target node of the edge does not exist: {edge.target}")
            
            # Check conditional edges
            if edge.type == EdgeType.CONDITIONAL and not edge.condition:
                result.add_warning("MISSING_EDGE_CONDITION", f"The conditional edge is missing a condition: {edge.id}")
    
    def _validate_connectivity(
        self,
        definition: WorkflowDefinition,
        result: ValidationResult
    ) -> None:
        """Verify connectivity"""
        if not definition.nodes:
            return
        
        # Start from the starting node BFS
        start_node = definition.get_start_node()
        if not start_node:
            return
        
        visited = set()
        queue = [start_node.id]
        
        while queue:
            node_id = queue.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            
            # Get all outgoing edges
            for edge in definition.get_edges_from(node_id):
                if edge.target not in visited:
                    queue.append(edge.target)
        
        # Check for unvisited nodes (Exclude START and END)
        all_node_ids = {n.id for n in definition.nodes}
        unreachable = all_node_ids - visited
        
        for node_id in unreachable:
            node = definition.get_node(node_id)
            if node and node.type not in (NodeType.START, NodeType.END):
                result.add_warning("UNREACHABLE_NODE", "Node unreachable", node_id)

