"""
Agent registry

Manage registration and discovery of all available agents
"""

import threading
from typing import Dict, List, Optional, Type

from .base import BaseAgent
from .config import AgentCategory, AgentMetadata, LicenseTier, BUILTIN_AGENTS


class AgentRegistry:
    """
    Agent registry (Singleton pattern)
    
    Usage:
        registry = AgentRegistry()
        
        # Register agent
        registry.register(MyAgent)
        
        # Get the agent
        agent_class = registry.get("market_analyst")
        
        # List all agents
        all_agents = registry.list_all()
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(AgentRegistry, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._agents: Dict[str, Type[BaseAgent]] = {}
            self._metadata: Dict[str, AgentMetadata] = {}
            self._load_builtin_metadata()
            self._initialized = True
    
    def _load_builtin_metadata(self) -> None:
        """Load built-in agent metadata"""
        for agent_id, metadata in BUILTIN_AGENTS.items():
            self._metadata[agent_id] = metadata
    
    def register(
        self,
        agent_class: Type[BaseAgent],
        override: bool = False
    ) -> None:
        """
        Register agent class
        
        Args:
            agent_class: Agent class
            override: Whether to overwrite existing registrations
        """
        metadata = agent_class.get_metadata()
        agent_id = metadata.id
        
        if agent_id in self._agents and not override:
            raise ValueError(f"agent '{agent_id}' Registered, using override=True Cover")
        
        self._agents[agent_id] = agent_class
        self._metadata[agent_id] = metadata
    
    def unregister(self, agent_id: str) -> None:
        """Log out of the agent"""
        self._agents.pop(agent_id, None)
        # Does not remove metadata, retains metadata of built-in agents
    
    def get(self, agent_id: str) -> Optional[Type[BaseAgent]]:
        """Get the agent class"""
        return self._agents.get(agent_id)
    
    def get_metadata(self, agent_id: str) -> Optional[AgentMetadata]:
        """Get agent metadata"""
        return self._metadata.get(agent_id)
    
    def list_all(self) -> List[AgentMetadata]:
        """List all agent metadata"""
        return list(self._metadata.values())
    
    def list_by_category(self, category: AgentCategory) -> List[AgentMetadata]:
        """List agents by category"""
        cat_str = category.value if hasattr(category, 'value') else category
        return [
            m for m in self._metadata.values()
            if (m.category.value if hasattr(m.category, 'value') else m.category) == cat_str
        ]
    
    def list_by_tier(self, tier: LicenseTier) -> List[AgentMetadata]:
        """List agents by license level"""
        tier_str = tier.value if hasattr(tier, 'value') else tier
        return [
            m for m in self._metadata.values()
            if (m.license_tier.value if hasattr(m.license_tier, 'value') else m.license_tier) == tier_str
        ]
    
    def list_available(self, current_tier: LicenseTier) -> List[AgentMetadata]:
        """
        List the agents available for the current license level
        
        Args:
            current_tier: Current license level
            
        Returns:
            List of available agent metadata
        """
        tier_order = ["free", "basic", "pro", "enterprise"]
        current_tier_str = current_tier.value if hasattr(current_tier, 'value') else current_tier
        current_index = tier_order.index(current_tier_str)

        def get_tier_index(metadata):
            tier = metadata.license_tier
            tier_str = tier.value if hasattr(tier, 'value') else tier
            return tier_order.index(tier_str)

        return [
            m for m in self._metadata.values()
            if get_tier_index(m) <= current_index
        ]
    
    def is_registered(self, agent_id: str) -> bool:
        """Check if the agent has registered implementation"""
        return agent_id in self._agents
    
    def has_metadata(self, agent_id: str) -> bool:
        """Check if agent metadata exists"""
        return agent_id in self._metadata
    
    def get_categories(self) -> List[AgentCategory]:
        """Get all categories"""
        return list(set(m.category for m in self._metadata.values()))
    
    def clear(self) -> None:
        """Clear registry (Preserve built-in metadata)"""
        self._agents.clear()
        self._metadata.clear()
        self._load_builtin_metadata()


# Global registry instance
_global_registry: Optional[AgentRegistry] = None


def get_registry() -> AgentRegistry:
    """Get global registry instance"""
    global _global_registry
    if _global_registry is None:
        _global_registry = AgentRegistry()
    return _global_registry


def register_agent(agent_class: Type[BaseAgent]) -> Type[BaseAgent]:
    """
    Decorator: Register agent class
    
    Usage:
        @register_agent
        class MyAgent(BaseAgent):
            metadata = AgentMetadata(...)
    """
    get_registry().register(agent_class)
    return agent_class

