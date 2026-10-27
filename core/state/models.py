"""
State layer data model

Data structures that define Agent IO and status fields
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class FieldType(str, Enum):
    """Field type"""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"
    LIST_MESSAGES = "list[BaseMessage]"  # LangGraph Message list


class StateFieldDefinition(BaseModel):
    """
    Status field definition
    
    Used to describe a single field in a workflow state
    """
    name: str                           # Field name
    type: FieldType = FieldType.STRING  # Field type
    description: str = ""               # Field description
    required: bool = False              # Is it necessary
    default: Optional[Any] = None       # Default value
    
    # Source information
    source_agent: Optional[str] = None  # generate this field Agent ID
    is_input: bool = False              # Whether to enter the field for workflow
    is_output: bool = False             # Whether it is a workflow output field


class AgentIODefinition(BaseModel):
    """
    Agent Input and output definition
    
    Declare the fields that the Agent needs to read and output
    """
    agent_id: str                       # Agent ID
    
    # input definition
    inputs: List[StateFieldDefinition] = Field(default_factory=list)
    
    # Output definition
    outputs: List[StateFieldDefinition] = Field(default_factory=list)
    
    # Read the output of other agents
    reads_from: List[str] = Field(default_factory=list)  # Field name list
    
    # metadata
    version: str = "1.0.0"
    description: str = ""
    
    def get_required_fields(self) -> List[str]:
        """Get the required input field name"""
        return [f.name for f in self.inputs if f.required]
    
    def get_output_field_names(self) -> List[str]:
        """Get output field name"""
        return [f.name for f in self.outputs]
    
    def validate_state(self, state: Dict[str, Any]) -> List[str]:
        """
        Verify whether the status meets the Agent s input requirements
        
        Returns:
            Missing field list
        """
        missing = []
        
        # Check required input
        for field in self.inputs:
            if field.required and field.name not in state:
                missing.append(field.name)
        
        # Check reads_from field
        for field_name in self.reads_from:
            if field_name not in state:
                missing.append(field_name)
        
        return missing


class WorkflowStateSchema(BaseModel):
    """
    Workflow status Schema
    
    Describe the status structure of the entire workflow
    """
    workflow_id: str                    # Workflow ID
    fields: Dict[str, StateFieldDefinition] = Field(default_factory=dict)
    
    # Field classification
    input_fields: List[str] = Field(default_factory=list)   # input field
    output_fields: List[str] = Field(default_factory=list)  # output fields
    intermediate_fields: List[str] = Field(default_factory=list)  # middle field
    
    # Agent dependency graph
    agent_dependencies: Dict[str, List[str]] = Field(default_factory=dict)
    
    def get_field(self, name: str) -> Optional[StateFieldDefinition]:
        """Get field definition"""
        return self.fields.get(name)

    def add_field(self, field: StateFieldDefinition) -> None:
        """Add field"""
        self.fields[field.name] = field

        if field.is_input:
            self.input_fields.append(field.name)
        if field.is_output:
            self.output_fields.append(field.name)
        if not field.is_input and not field.is_output:
            self.intermediate_fields.append(field.name)

    def get_input_field_objects(self) -> List[StateFieldDefinition]:
        """Get a list of input field objects"""
        return [self.fields[name] for name in self.input_fields if name in self.fields]

    def get_output_field_objects(self) -> List[StateFieldDefinition]:
        """Get a list of output field objects"""
        return [self.fields[name] for name in self.output_fields if name in self.fields]

    def get_intermediate_field_objects(self) -> List[StateFieldDefinition]:
        """Get the list of intermediate field objects"""
        return [self.fields[name] for name in self.intermediate_fields if name in self.fields]
    
    def get_execution_order(self, agent_ids: List[str]) -> List[str]:
        """
        Calculate execution order based on dependencies (topological sorting)

        Args:
            agent_ids: List of participating Agent IDs

        Returns:
            Sorted list of Agent IDs
        """
        # Topological sorting using Kahn's algorithm
        from collections import defaultdict, deque

        # Build dependency graph and in-degree table
        in_degree = {agent_id: 0 for agent_id in agent_ids}
        graph = defaultdict(list)  # agent_id -> [dependent on it agent_ids]

        # Build a reverse dependency graph (who depends on whom)
        for agent_id in agent_ids:
            deps = self.agent_dependencies.get(agent_id, [])
            # deps is a list of field names, you need to find the source of these fields agent
            for dep_field in deps:
                # Find the occurrence of this field agent
                dep_agent = None
                for field_name, field_def in self.fields.items():
                    if field_name == dep_field and field_def.source_agent:
                        dep_agent = field_def.source_agent
                        break

                # If the dependent agent is found, establish the dependency relationship
                if dep_agent and dep_agent in agent_ids:
                    graph[dep_agent].append(agent_id)
                    in_degree[agent_id] += 1

        # Kahn algorithm
        queue = deque([agent_id for agent_id in agent_ids if in_degree[agent_id] == 0])
        result = []

        while queue:
            agent_id = queue.popleft()
            result.append(agent_id)

            # Reduce the in-degree of other agents that depend on this agent
            for dependent in graph[agent_id]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        # If the result length is not equal to the input length, there is a circular dependency.
        if len(result) != len(agent_ids):
            # Fallback to simple sort
            return sorted(agent_ids, key=lambda x: len(self.agent_dependencies.get(x, [])))

        return result

