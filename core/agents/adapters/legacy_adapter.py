"""
Legacy agent adapter

Wrap an existing functional agent into a BaseAgent subclass
"""

from typing import Any, Callable, Dict, Optional

from ..base import BaseAgent
from ..config import AgentMetadata, AgentConfig


class LegacyAgentAdapter(BaseAgent):
    """
    Legacy agent adapter
    
    Wrap existing functional agents (such as create_market_analyst) as BaseAgent subclasses
    
    Usage:
        from tradingagents.agents.analysts.market_analyst import create_market_analyst
        
        adapter = LegacyAgentAdapter(
            metadata=BUILTIN_AGENTS["market_analyst"],
            factory_func=create_market_analyst,
            llm=my_llm,
            toolkit=my_toolkit
        )
        
        result = adapter.execute(state)
    """
    
    def __init__(
        self,
        metadata: AgentMetadata,
        factory_func: Callable,
        llm: Any,
        toolkit: Any,
        config: Optional[AgentConfig] = None
    ):
        """
        Initialize adapter
        
        Args:
            metadata: Agent metadata
            factory_func: original factory function (Such as create_market_analyst)
            llm: LLM Example
            toolkit: Toolkit Example
            config: Agent configuration
        """
        super().__init__(config)
        self._metadata = metadata
        self._factory_func = factory_func
        self._llm = llm
        self._toolkit = toolkit
        self._node_func: Optional[Callable] = None
    
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        """Get metadata - provided by the instance"""
        raise NotImplementedError("LegacyAgentAdapter The metadata for is provided by the instance")
    
    def get_instance_metadata(self) -> AgentMetadata:
        """Get instance metadata"""
        return self._metadata
    
    def initialize(self) -> None:
        """Initialize adapter"""
        # Call the original factory function to create the node function
        self._node_func = self._factory_func(self._llm, self._toolkit)
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute agent logic
        
        Args:
            state: current state dictionary
            
        Returns:
            Updated status dictionary
        """
        if self._node_func is None:
            self.initialize()
        
        return self._node_func(state)
    
    @property
    def agent_id(self) -> str:
        """agent ID"""
        return self._metadata.id
    
    @property
    def agent_name(self) -> str:
        """Agent name"""
        return self._metadata.name


def create_legacy_adapter(
    agent_id: str,
    llm: Any,
    toolkit: Any,
    config: Optional[AgentConfig] = None
) -> LegacyAgentAdapter:
    """
    Convenience function: Create a legacy agent adapter
    
    Args:
        agent_id: agent ID (Such as "market_analyst")
        llm: LLM Example
        toolkit: Toolkit Example
        config: Agent configuration
        
    Returns:
        Configured adapter instance
    """
    from ..config import BUILTIN_AGENTS
    
    # Get metadata
    metadata = BUILTIN_AGENTS.get(agent_id)
    if metadata is None:
        raise ValueError(f"unknown agent ID: {agent_id}")
    
    # Get factory function
    factory_func = _get_factory_func(agent_id)
    
    # Create adapter
    adapter = LegacyAgentAdapter(
        metadata=metadata,
        factory_func=factory_func,
        llm=llm,
        toolkit=toolkit,
        config=config
    )
    
    adapter.initialize()
    return adapter


def _get_factory_func(agent_id: str) -> Callable:
    """Get the factory function of the agent"""
    factory_map = {
        "market_analyst": "tradingagents.agents.analysts.market_analyst:create_market_analyst",
        "news_analyst": "tradingagents.agents.analysts.news_analyst:create_news_analyst",
        "fundamentals_analyst": "tradingagents.agents.analysts.fundamentals_analyst:create_fundamentals_analyst",
        "social_analyst": "tradingagents.agents.analysts.social_media_analyst:create_social_media_analyst",
        "bull_researcher": "tradingagents.agents.researchers.bull_researcher:create_bull_researcher",
        "bear_researcher": "tradingagents.agents.researchers.bear_researcher:create_bear_researcher",
        "trader": "tradingagents.agents.trader.trader:create_trader",
        "risk_manager": "tradingagents.agents.managers.risk_manager:create_risk_manager",
        "research_manager": "tradingagents.agents.managers.research_manager:create_research_manager",
    }
    
    if agent_id not in factory_map:
        raise ValueError(f"Agent not found '{agent_id}' factory function")
    
    module_path, func_name = factory_map[agent_id].rsplit(":", 1)
    
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, func_name)

