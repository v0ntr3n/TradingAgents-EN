"""
State Schema builder

Dynamically generate workflow status based on Agent list Schema
"""

import logging
from typing import Any, Dict, List, Optional, Type
from langchain_core.messages import BaseMessage

from .models import (
    StateFieldDefinition,
    AgentIODefinition,
    WorkflowStateSchema,
    FieldType,
)

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
        from .reducers import keep_non_empty, merge_dict, keep_latest_list

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

