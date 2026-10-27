"""
Analyst Workflow Extensions

Provides the ability to dynamically add analyst nodes to the workflow,
No modification required tradingagents/graph/setup.py

Usage:
    from core.workflow.analyst_extension import AnalystWorkflowExtension
    from core.agents.analyst_registry import get_analyst_registry
    
    # Register a new analyst
    registry = get_analyst_registry()
    registry.register("sector", SectorAnalystAgent)
    
    # Create extension
    extension = AnalystWorkflowExtension(registry)
    
    # Apply extensions at workflow build time
    extension.extend_workflow(workflow, selected_analysts=["sector", "index"])
"""

from typing import Dict, List, Optional, Callable, Any, Set
from langgraph.graph import StateGraph, END

from ..agents.analyst_registry import AnalystRegistry, get_analyst_registry
from ..agents.config import AgentMetadata

# Import logs
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")


class AnalystWorkflowExtension:
    """
    Analyst workflow extender
    
    Dynamically add analysts from the registry to the workflow
    """
    
    def __init__(
        self,
        registry: Optional[AnalystRegistry] = None,
        llm = None,
        toolkit = None
    ):
        self.registry = registry or get_analyst_registry()
        self.llm = llm
        self.toolkit = toolkit
        self._created_nodes: Dict[str, Callable] = {}
    
    def set_dependencies(self, llm, toolkit):
        """Set up LLM and Toolkit dependencies"""
        self.llm = llm
        self.toolkit = toolkit
    
    def extend_workflow(
        self,
        workflow: StateGraph,
        selected_analysts: List[str],
        existing_nodes: Set[str],
        delete_node_factory: Callable,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Extend the workflow to add an analyst node in the registry
        
        Args:
            workflow: LangGraph StateGraph Example
            selected_analysts: List of selected analysts (e.g. ["sector", "index"]) 
            existing_nodes: Existing node collection (to avoid repeated addition)
            delete_node_factory: Factory function to create message deletion node
            
        Returns:
            Added analyst information {analyst_id: {node_name, metadata, requires_tools}}
        """
        added_analysts = {}
        
        for analyst_id in selected_analysts:
            # Check if it already exists
            if analyst_id in existing_nodes:
                logger.debug(f"📋 [Expand] analyst {analyst_id} Already exists, skip")
                continue
            
            # Check if the implementation is registered in the registry
            if not self.registry.is_registered(analyst_id):
                logger.debug(f"📋 [Expand] analyst {analyst_id} Unregistered implementation, skip")
                continue
            
            # Get metadata
            metadata = self.registry.get_analyst_metadata(analyst_id)
            if not metadata:
                logger.warning(f"⚠️ [Expand] analyst {analyst_id} No metadata")
                continue
            
            # Create node
            node_func = self._create_analyst_node(analyst_id, metadata)
            if node_func is None:
                continue
            
            # Add to workflow
            node_name = metadata.node_name or f"{analyst_id.capitalize()} Analyst"
            workflow.add_node(node_name, node_func)
            
            # Add message to delete node
            clear_name = f"Msg Clear {analyst_id.capitalize()}"
            workflow.add_node(clear_name, delete_node_factory())
            
            logger.info(f"✅ [Expand] Add analyst node: {node_name}")
            
            added_analysts[analyst_id] = {
                "node_name": node_name,
                "clear_name": clear_name,
                "metadata": metadata,
                "requires_tools": metadata.requires_tools,
                "output_field": metadata.output_field,
                "execution_order": metadata.execution_order,
            }
        
        return added_analysts
    
    def _create_analyst_node(
        self, 
        analyst_id: str, 
        metadata: AgentMetadata
    ) -> Optional[Callable]:
        """
        Create analyst node function
        """
        # Try to get the factory function from the registry
        factory = self.registry.get_analyst_factory(analyst_id)
        if factory:
            return factory(self.llm, self.toolkit)
        
        # Try to get the class from the registry
        agent_class = self.registry.get_analyst_class(analyst_id)
        if agent_class:
            agent = agent_class()
            if hasattr(agent, 'set_dependencies'):
                agent.set_dependencies(self.llm, self.toolkit)
            return lambda state, a=agent: a.execute(state)
        
        logger.warning(f"⚠️ [Expand] Unable to create analyst {analyst_id} node")
        return None
    
    def connect_analysts(
        self,
        workflow: StateGraph,
        added_analysts: Dict[str, Dict[str, Any]],
        entry_point: str,
        exit_point: str,
    ):
        """
        Connect analyst nodes (concatenated in order of execution)
        
        Args:
            workflow: LangGraph StateGraph Example
            added_analysts: extend_workflow Returned analyst information
            entry_point: Entry node (connect to first analyst)
            exit_point: Exit node (the last analyst connected to this)
        """
        if not added_analysts:
            return
        
        # Sort by execution order
        sorted_analysts = sorted(
            added_analysts.items(),
            key=lambda x: x[1]["execution_order"]
        )
        
        # Connect nodes
        prev_clear = entry_point
        for i, (analyst_id, info) in enumerate(sorted_analysts):
            node_name = info["node_name"]
            clear_name = info["clear_name"]
            requires_tools = info["requires_tools"]
            
            # Entrance connection
            if prev_clear != entry_point:
                workflow.add_edge(prev_clear, node_name)
            
            # Analyst without tool invocation: connect directly to cleanup node
            if not requires_tools:
                workflow.add_edge(node_name, clear_name)
            # Analysts with tool calls: tool loop required (handled by original setup.py)
            
            prev_clear = clear_name
        
        # The last cleanup node is connected to the outlet
        if sorted_analysts:
            last_clear = sorted_analysts[-1][1]["clear_name"]
            workflow.add_edge(last_clear, exit_point)

