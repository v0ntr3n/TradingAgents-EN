"""
market analyst agent

Market analyst implementation based on BaseAgent
"""

from typing import Any, Dict, Optional

from ..base import BaseAgent
from ..config import AgentMetadata, AgentConfig, AgentCategory, LicenseTier, BUILTIN_AGENTS
from ..registry import register_agent


@register_agent
class MarketAnalystAgent(BaseAgent):
    """
    market analyst agent
    
    Analyze market data, price trends, technical indicators, etc. for stocks
    """
    
    metadata = BUILTIN_AGENTS["market_analyst"]
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._legacy_node = None
        self._llm = None
        self._toolkit = None
    
    def set_dependencies(self, llm: Any, toolkit: Any) -> "MarketAnalystAgent":
        """
        Set dependencies
        
        Args:
            llm: LLM Example
            toolkit: Toolkit Example
            
        Returns:
            self (Support chain calls)
        """
        self._llm = llm
        self._toolkit = toolkit
        return self
    
    def initialize(self) -> None:
        """Initialize the agent"""
        if self._llm is None or self._toolkit is None:
            raise ValueError("must be called first set_dependencies() Set up LLM and toolkit")
        
        # Import and create legacy node functions
        from tradingagents.agents.analysts.market_analyst import create_market_analyst
        self._legacy_node = create_market_analyst(self._llm, self._toolkit)
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform market analysis
        
        Args:
            state: A status dictionary containing the following keys:
                - company_of_interest: Stock code
                - trade_date: transaction date
                - messages: Message history
                
        Returns:
            The updated status includes:
                - market_report: Market analysis report
                - messages: Updated message history
        """
        if self._legacy_node is None:
            self.initialize()
        
        return self._legacy_node(state)

