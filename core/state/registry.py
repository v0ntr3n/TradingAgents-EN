"""
status registry

Manage caching and querying of workflow state schemas
"""

import logging
import threading
from typing import Any, Dict, List, Optional, Type

from .models import WorkflowStateSchema, AgentIODefinition
from .builder import StateSchemaBuilder

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

