from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['models', 'reducers', 'registry', 'builder']:
    _sys.modules[f"core.state.{_sub}"] = _self_mod
    setattr(_self_mod, _sub, _self_mod)

# === models.py ===
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


# === reducers.py ===
"""
State Reducer Function

Annotated reducer for LangGraph StateGraph that handles state merging when concurrent node executions occur.

Reducer Rules:
- keep_non_empty: String/scalar fields, retain non-null values (new values first)
- merge_dict: Dictionary fields, intelligent merging (special processing of historical fields)
- keep_latest_list: List fields, always take the latest value
"""

from typing import Any


def keep_non_empty(left: Any, right: Any) -> Any:
    """Keep non-null values, use right (new value) first

    Used for string/scalar fields to avoid overwriting existing results when executing parallel nodes.
    """
    if right:
        return right
    return left if left else right


def merge_dict(left: dict, right: dict) -> dict:
    """Smart merge of two dictionaries to handle concurrent updates

    Special handling: for the history field of debate status (*_history) , 
    Prioritize non-null values ​​to avoid being overwritten by empty strings.
    """
    if left is None:
        return right
    if right is None:
        return left

    result = left.copy()

    # Historical fields that require special treatment
    history_fields = [
        'bull_history', 'bear_history', 'history',
        'risky_history', 'safe_history', 'neutral_history'
    ]

    for key, value in right.items():
        # For history fields, only update if the new value is non-null
        if key in history_fields:
            old_value = result.get(key, "")
            # If the new value is null but the old value is not null, keep the old value
            if not value and old_value:
                continue
            # If both are non-empty, keep the longer one (contains more content)
            if value and old_value and len(old_value) > len(value):
                continue
        result[key] = value

    return result


def keep_latest_list(left: Any, right: Any) -> Any:
    """List fields always take the latest value, allowing explicit clearing of message history with an empty list."""
    if right is None:
        return left
    return right

# === registry.py ===
"""
status registry

Manage caching and querying of workflow state schemas
"""

import logging
import threading
from typing import Any, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


class StateRegistry:
    """
    State registry (singleton mode)
    
    Caching and managing workflow state Schema
    
    Usage:
        registry = StateRegistry()
        
        # Get or build status Schema
        schema = registry.get_or_build(
            workflow_id="position_analysis",
            agent_ids=["pa_technical", "pa_fundamental", "pa_risk", "pa_advisor"]
        )
        
        # Get the TypedDict class
        state_class = registry.get_state_class("position_analysis")
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(StateRegistry, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._schemas: Dict[str, WorkflowStateSchema] = {}
            self._state_classes: Dict[str, Type] = {}
            self._builder = StateSchemaBuilder()
            self._initialized = True
    
    def get_or_build(
        self,
        workflow_id: str,
        agent_ids: List[str],
        force_rebuild: bool = False,
        internal_state_fields: Optional[Dict[str, Any]] = None,
    ) -> WorkflowStateSchema:
        """
        Get or build workflow status Schema
        
        Args:
            workflow_id: Workflow ID
            agent_ids: Agent ID list
            force_rebuild: Whether to force rebuild
            
        Returns:
            WorkflowStateSchema Example
        """
        if workflow_id in self._schemas and not force_rebuild:
            schema = self._schemas[workflow_id]
            missing_internal_fields = []
            if internal_state_fields:
                missing_internal_fields = [
                    name for name in internal_state_fields
                    if name not in schema.fields
                ]
            if not missing_internal_fields:
                return schema
            logger.info(
                f"Status Schema is missing internal fields, regenerate: {workflow_id}, missing={missing_internal_fields}"
            )
        
        schema = self._builder.build_from_agents(
            workflow_id,
            agent_ids,
            internal_state_fields=internal_state_fields,
        )
        self._schemas[workflow_id] = schema
        
        # Also generate TypedDict class
        self._state_classes[workflow_id] = self._builder.generate_typed_dict(schema)
        
        return schema
    
    def get_schema(self, workflow_id: str) -> Optional[WorkflowStateSchema]:
        """Get cached status Schema"""
        return self._schemas.get(workflow_id)
    
    def get_state_class(self, workflow_id: str) -> Optional[Type]:
        """Get the TypedDict status class of the workflow"""
        return self._state_classes.get(workflow_id)
    
    def register_schema(self, schema: WorkflowStateSchema) -> None:
        """Manual registration status Schema"""
        self._schemas[schema.workflow_id] = schema
        self._state_classes[schema.workflow_id] = self._builder.generate_typed_dict(schema)
    
    def clear(self, workflow_id: Optional[str] = None) -> None:
        """clear cache"""
        if workflow_id:
            self._schemas.pop(workflow_id, None)
            self._state_classes.pop(workflow_id, None)
        else:
            self._schemas.clear()
            self._state_classes.clear()
    
    def list_workflows(self) -> List[str]:
        """List all registered workflows ID"""
        return list(self._schemas.keys())
    
    def get_field_source(self, workflow_id: str, field_name: str) -> Optional[str]:
        """Get the source of the field Agent"""
        schema = self._schemas.get(workflow_id)
        if schema and field_name in schema.fields:
            return schema.fields[field_name].source_agent
        return None


# Global registry instance
_global_registry: Optional[StateRegistry] = None


def get_state_registry() -> StateRegistry:
    """Get the global status registry"""
    global _global_registry
    if _global_registry is None:
        _global_registry = StateRegistry()
    return _global_registry


# === builder.py ===
"""
State Schema builder

Dynamically generate workflow status based on Agent list Schema
"""

import logging
from typing import Any, Dict, List, Optional, Type
from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)


class StateSchemaBuilder:
    """
    State Schema builder
    
    Dynamically generate status based on the Agent list in the workflow Schema
    
    Usage:
        builder = StateSchemaBuilder()
        schema = builder.build_from_agents(
            workflow_id="position_analysis",
            agent_ids=["pa_technical", "pa_fundamental", "pa_risk", "pa_advisor"]
        )
    """
    
    def __init__(self):
        self._io_cache: Dict[str, AgentIODefinition] = {}
    
    def build_from_agents(
        self,
        workflow_id: str,
        agent_ids: List[str],
        input_fields: Optional[List[StateFieldDefinition]] = None,
        internal_state_fields: Optional[Dict[str, Any]] = None,
    ) -> WorkflowStateSchema:
        """
        Build state from Agent list Schema
        
        Args:
            workflow_id: Workflow ID
            agent_ids: Agent ID list
            input_fields: Additional input field definitions
            
        Returns:
            WorkflowStateSchema Example
        """
        schema = WorkflowStateSchema(workflow_id=workflow_id)
        
        # Add basic fields (messages)
        schema.add_field(StateFieldDefinition(
            name="messages",
            type=FieldType.LIST_MESSAGES,
            description="LangGraph Message list",
            required=True,
            is_input=True,
        ))
        
        # Collect IO definitions of all Agents
        for agent_id in agent_ids:
            io_def = self._get_agent_io(agent_id)
            if io_def is None:
                logger.warning(f"Agent {agent_id} No IO definition, skip")
                continue
            
            # Add input field
            for field in io_def.inputs:
                if field.name not in schema.fields:
                    field.is_input = True
                    schema.add_field(field)
            
            # Add output fields
            for field in io_def.outputs:
                field.source_agent = agent_id
                schema.add_field(field)
            
            # Record dependencies
            if io_def.reads_from:
                schema.agent_dependencies[agent_id] = io_def.reads_from
        
        # Add additional input fields
        if input_fields:
            for field in input_fields:
                field.is_input = True
                schema.add_field(field)

        # Add workflow internal control fields
        if internal_state_fields:
            for name, field_type in internal_state_fields.items():
                if name not in schema.fields:
                    schema.add_field(StateFieldDefinition(
                        name=name,
                        type=field_type,
                        description="Workflow internal control fields",
                    ))
        
        logger.info(
            f"Build status Schema: {workflow_id}, "
            f"Number of fields={len(schema.fields)}, "
            f"input={len(schema.input_fields)}, "
            f"output={len(schema.output_fields)}"
        )
        
        return schema
    
    def _get_agent_io(self, agent_id: str) -> Optional[AgentIODefinition]:
        """Get the IO definition of Agent"""
        if agent_id in self._io_cache:
            return self._io_cache[agent_id]
        
        # Get from BindingManager
        try:
            from core.config import BindingManager
            binding_manager = BindingManager()
            io_dict = binding_manager.get_agent_io_definition(agent_id)
            
            if io_dict:
                io_def = self._dict_to_io_definition(io_dict)
                self._io_cache[agent_id] = io_def
                return io_def
        except Exception as e:
            logger.warning(f"Failed to get IO definition from BindingManager: {e}")
        
        # Get from code configuration
        io_def = self._get_io_from_config(agent_id)
        if io_def:
            self._io_cache[agent_id] = io_def
        
        return io_def
    
    def _get_io_from_config(self, agent_id: str) -> Optional[AgentIODefinition]:
        """Get IO definition from code configuration (BUILTIN_AGENTS → AgentRegistry fallback)"""
        from core.agents.config import BUILTIN_AGENTS

        agent_meta = None

        # 1. Check first BUILTIN_AGENTS
        if agent_id in BUILTIN_AGENTS:
            agent_meta = BUILTIN_AGENTS[agent_id]

        # 2. Fallback to AgentRegistry (v2 adapter via @register_agent Register)
        if agent_meta is None:
            try:
                from core.agents.registry import get_registry
                agent_meta = get_registry().get_metadata(agent_id)
            except Exception as e:
                logger.debug(f"Get from AgentRegistry {agent_id} Metadata failed: {e}")

        if agent_meta is None:
            return None
        
        # Build input fields
        inputs = []
        for inp in agent_meta.inputs:
            inputs.append(StateFieldDefinition(
                name=inp.name,
                type=FieldType(inp.type) if inp.type in FieldType.__members__.values() else FieldType.STRING,
                description=inp.description,
                required=inp.required,
                default=inp.default,
            ))
        
        # Build output fields
        outputs = []
        for out in agent_meta.outputs:
            outputs.append(StateFieldDefinition(
                name=out.name,
                type=FieldType(out.type) if out.type in FieldType.__members__.values() else FieldType.STRING,
                description=out.description,
            ))
        
        # If there is output_field but no outputs, it is added automatically
        if agent_meta.output_field and not outputs:
            outputs.append(StateFieldDefinition(
                name=agent_meta.output_field,
                type=FieldType.STRING,
                description=f"{agent_meta.name} The output of",
            ))
        
        return AgentIODefinition(
            agent_id=agent_id,
            inputs=inputs,
            outputs=outputs,
            reads_from=agent_meta.reads_from,
            description=agent_meta.description,
        )

    def _dict_to_io_definition(self, data: Dict[str, Any]) -> AgentIODefinition:
        """Convert dictionary to AgentIODefinition"""
        inputs = []
        for inp in data.get("inputs", []):
            inputs.append(StateFieldDefinition(
                name=inp.get("name", ""),
                type=FieldType(inp.get("type", "string")),
                description=inp.get("description", ""),
                required=inp.get("required", False),
                default=inp.get("default"),
            ))

        outputs = []
        for out in data.get("outputs", []):
            outputs.append(StateFieldDefinition(
                name=out.get("name", ""),
                type=FieldType(out.get("type", "string")),
                description=out.get("description", ""),
            ))

        return AgentIODefinition(
            agent_id=data.get("agent_id", ""),
            inputs=inputs,
            outputs=outputs,
            reads_from=data.get("reads_from", []),
            description=data.get("description", ""),
        )

    def generate_typed_dict(self, schema: WorkflowStateSchema) -> Type:
        """
        Generate TypedDict class according to Schema (with LangGraph reducer annotation)

        The generated TypedDict has an Annotated reducer for each field,
        Ensure that state is merged correctly when parallel nodes execute:
        - string → Annotated[str, keep_non_empty] (Keep non-null values)
        - object → Annotated[dict, merge_dict] (Smart merge dictionary)
        - array  → Annotated[list, keep_latest_list] (Use the latest list)
        - messages → Annotated[List[BaseMessage], add_messages] (LangGraph built-in)
        """
        from typing import TypedDict, Annotated, List
        import operator
        from langgraph.graph.message import add_messages

        # Dynamically create fields (all with reducer annotations)
        annotations = {}

        for name, field in schema.fields.items():
            if name == "context":
                annotations[name] = Annotated[Any, keep_non_empty]
            elif name.startswith("_debate_") and name.endswith("_count"):
                annotations[name] = Annotated[int, operator.add]
            elif field.type == FieldType.LIST_MESSAGES:
                annotations[name] = Annotated[List[BaseMessage], add_messages]
            elif field.type == FieldType.STRING:
                annotations[name] = Annotated[str, keep_non_empty]
            elif field.type == FieldType.NUMBER:
                annotations[name] = Annotated[float, keep_non_empty]
            elif field.type == FieldType.BOOLEAN:
                annotations[name] = Annotated[bool, keep_non_empty]
            elif field.type == FieldType.OBJECT:
                annotations[name] = Annotated[dict, merge_dict]
            elif field.type == FieldType.ARRAY:
                annotations[name] = Annotated[list, keep_latest_list]
            else:
                annotations[name] = Annotated[str, keep_non_empty]

        # Create TypedDict
        state_class = TypedDict(f"{schema.workflow_id}_State", annotations)

        logger.info(
            f"Generate dynamics TypedDict: {schema.workflow_id}_State, "
            f"Number of fields={len(annotations)} (All with reducer annotations)"
        )

        return state_class


# === __init__.py ===
"""
State layer module

Provide dynamic state Schema generation and management
"""

__all__ = [
    "StateFieldDefinition",
    "AgentIODefinition",
    "StateSchemaBuilder",
    "StateRegistry",
]
