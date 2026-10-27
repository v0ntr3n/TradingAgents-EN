"""
Sector Analyst Agent

Analyze industry trends, sector rotations and peer comparisons
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage

from ..base import BaseAgent
from ..config import AgentConfig, BUILTIN_AGENTS
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class SectorAnalystAgent(BaseAgent):
    """
    Sector Analyst Agent
    
    Responsibilities:
    1. Analyze the overall performance of the industry to which the target stock belongs
    2. Identify sector rotation trends and capital flows
    3. Conduct comparative analysis of competitors in the same industry
    """
    
    metadata = BUILTIN_AGENTS["sector_analyst"]
    
    # System prompt word
    SYSTEM_PROMPT = """You are a professional sector analyst, focusing on industry research and sector rotation analysis.

Your task is to analyze the target stock {ticker} sector and industry conditions.

🔴 Analysis requirements:

1️⃣ **Sector performance analysis**
   - Which sectors does the target stock belong to?
   - Recent gains and losses of each sector
   - The strength of the sector relative to the broader market

2️⃣ **Sector rotation trend**
   - Current market hot sectors
   - Fund inflow/outflow direction
   - Judgment of sector rotation cycle

3️⃣ **Comparative analysis of peers**
   - The position of the target stock in the industry (market capitalization ranking)
   - Valuation comparison (PE/PB vs industry median)
   - Industry leader identification

📊 Output requirements:
- Sector popularity assessment: popular/general/unpopular
- Rotation direction: capital inflow/outflow/stable
- Individual stock position: leading/second tier/following the trend
- Research observations: Research observations are given based on sector trends
"""
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._llm = None
        self._toolkit = None
    
    def set_dependencies(self, llm: Any, toolkit: Any) -> "SectorAnalystAgent":
        """
        Set dependencies
        
        Args:
            llm: LLM Example (for LangGraph mode)
            toolkit: Toolkit Example (for LangGraph mode)
            
        Returns:
            self (Support chain calls)
        """
        self._llm = llm
        self._toolkit = toolkit
        return self
    
    def initialize(self) -> None:
        """Initialize the agent"""
        pass  # Tool functions are imported directly without initialization.
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform sector analysis
        
        Args:
            state: A status dictionary containing the following keys:
                - company_of_interest: Stock code
                - trade_date: transaction date
                - messages: Message history
                
        Returns:
            The updated status includes:
                - sector_report: Sector analysis report
                - messages: Updated message history
        """
        ticker = state.get("company_of_interest", "")
        trade_date = state.get("trade_date", "")
        
        logger.info(f"🏭 Sector analysts begin to analyze: {ticker} @ {trade_date}")
        
        try:
            # Import and call sector analysis tools
            from core.tools.sector_tools import analyze_sector_sync
            
            # Get comprehensive sector analysis report
            sector_report = analyze_sector_sync(ticker, trade_date)
            
            # If you have an LLM, you can have the LLM summarize the report
            if self._llm is not None:
                sector_report = self._enhance_with_llm(ticker, sector_report)
            
            logger.info(f"✅ Sector analysis completed: {ticker}")
            
            # update status
            messages = state.get("messages", [])
            messages.append(HumanMessage(content=sector_report, name="sector_analyst"))
            
            return {
                **state,
                "sector_report": sector_report,
                "messages": messages,
            }
            
        except Exception as e:
            logger.error(f"❌ Sector analysis failed: {e}")
            error_report = f"Sector analysis failed: {e}"
            
            messages = state.get("messages", [])
            messages.append(HumanMessage(content=error_report, name="sector_analyst"))
            
            return {
                **state,
                "sector_report": error_report,
                "messages": messages,
            }
    
    def _enhance_with_llm(self, ticker: str, data_report: str) -> str:
        """
        Enhance analytical reporting with LLM
        
        Args:
            ticker: Stock code
            data_report: Raw data report
            
        Returns:
            Enhanced analysis reports
        """
        try:
            prompt = self.SYSTEM_PROMPT.format(ticker=ticker)
            full_prompt = f"{prompt}\n\n The following is the sector data:\n\n{data_report}\n\n Please provide a professional sector analysis report based on the above data."
            
            # call LLM
            response = self._llm.invoke(full_prompt)
            
            if hasattr(response, 'content'):
                return response.content
            return str(response)
            
        except Exception as e:
            logger.warning(f"LLM Enhanced analysis failed, returning original report: {e}")
            return data_report

