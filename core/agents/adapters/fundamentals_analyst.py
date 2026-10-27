"""
Fundamental Analyst Agent

Implementation of fundamental analysts based on BaseAgent
"""

from typing import Any, Dict, Optional

from ..base import BaseAgent
from ..config import AgentConfig, BUILTIN_AGENTS
from ..registry import register_agent


@register_agent
class FundamentalsAnalystAgent(BaseAgent):
    """
    Fundamental Analyst Agent
    
    Analyze the company s financial data, fundamental indicators, etc.
    """
    
    metadata = BUILTIN_AGENTS["fundamentals_analyst"]
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._legacy_node = None
        self._llm = None
        self._toolkit = None
    
    def set_dependencies(self, llm: Any, toolkit: Any) -> "FundamentalsAnalystAgent":
        """Set dependencies"""
        self._llm = llm
        self._toolkit = toolkit
        return self
    
    def initialize(self) -> None:
        """Initialize the agent"""
        if self._llm is None or self._toolkit is None:
            raise ValueError("must be called first set_dependencies() Set up LLM and toolkit")
        
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        self._legacy_node = create_fundamentals_analyst(self._llm, self._toolkit)
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform fundamental analysis
        
        Args:
            state: A status dictionary containing the following keys:
                - company_of_interest: Stock code
                - trade_date: transaction date
                - messages: Message history
                
        Returns:
            The updated status includes:
                - fundamentals_report: Fundamental Analysis Report
                - messages: Updated message history
        """
        if self._legacy_node is None:
            self.initialize()
        
        return self._legacy_node(state)

