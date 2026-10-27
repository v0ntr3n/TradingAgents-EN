"""
Market/Index Analyst Intelligence

Analyze market trends, market environment and systemic risks
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage

from ..base import BaseAgent
from ..config import AgentConfig, BUILTIN_AGENTS
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class IndexAnalystAgent(BaseAgent):
    """
    Market/Index Analyst Intelligence
    
    Responsibilities:
    1. Analyze the trend of major indexes (Shanghai Stock Exchange, Shenzhen Stock Exchange, GEM, etc.)
    2. Assess market width (number of rising and falling stocks, volume, etc.)
    3. Determine market environment and risk levels
    4. Identify market cycles (bull/bear/concussive)
    """
    
    metadata = BUILTIN_AGENTS["index_analyst"]
    
    # System prompt word
    SYSTEM_PROMPT = """You are a professional market analyst who specializes in analyzing the overall market environment and systemic risks.

Your analytical responsibilities include:

1️⃣ **Index trend analysis**
   - Trends of major indexes such as Shanghai Composite Index, Shenzhen Composite Component Index and GEM Index
   - Moving average system judgment (MA5/MA20/MA60)
   - Trend direction judgment

2️⃣ **Market Breadth Analysis**
   - Ratio of gainers and losers
   - The number of daily limit and lower limit
   - Market sentiment judgment

3️⃣ **Market environment assessment**
   - Index valuation level (PE/PB)
   - market volatility
   - Risk level assessment

4️⃣ **Market cycle identification**
   - Bull market/bear market/shock market judgment
   - Location analysis during the year
   - Operation suggestions

📊 Output requirements:
- Market trend: up/down/concussive
- Risk level: high/medium/low
- Market cycle: bull market/bear market/shock market
- Operational suggestions: Positive/Neutral/Defensive
"""
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._llm = None
        self._toolkit = None
    
    def set_dependencies(self, llm: Any, toolkit: Any) -> "IndexAnalystAgent":
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
        pass
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform broad market analysis
        
        Args:
            state: A status dictionary containing the following keys:
                - trade_date: transaction date
                - messages: Message history
                
        Returns:
            The updated status includes:
                - index_report: Market analysis report
                - messages: Updated message history
        """
        trade_date = state.get("trade_date", "")
        
        logger.info(f"🌐 Market analysts begin to analyze @ {trade_date}")
        
        try:
            # Import and call market analysis tools
            from core.tools.index_tools import analyze_index_sync
            
            # Get comprehensive market analysis report
            index_report = analyze_index_sync(trade_date)
            
            # If you have an LLM, you can have the LLM summarize the report
            if self._llm is not None:
                index_report = self._enhance_with_llm(index_report)
            
            logger.info(f"✅ Market analysis completed")
            
            # update status
            messages = state.get("messages", [])
            messages.append(HumanMessage(content=index_report, name="index_analyst"))
            
            return {
                **state,
                "index_report": index_report,
                "messages": messages,
            }
            
        except Exception as e:
            logger.error(f"❌ Market analysis failed: {e}")
            error_report = f"Market analysis failed: {e}"
            
            messages = state.get("messages", [])
            messages.append(HumanMessage(content=error_report, name="index_analyst"))
            
            return {
                **state,
                "index_report": error_report,
                "messages": messages,
            }
    
    def _enhance_with_llm(self, data_report: str) -> str:
        """
        Enhance analytical reporting with LLM
        """
        try:
            full_prompt = f"{self.SYSTEM_PROMPT}\n\n The following is the market data:\n\n{data_report}\n\n Please provide a professional market analysis report based on the above data."
            
            response = self._llm.invoke(full_prompt)
            
            if hasattr(response, 'content'):
                return response.content
            return str(response)
            
        except Exception as e:
            logger.warning(f"LLM Enhanced analysis failed, returning original report: {e}")
            return data_report

