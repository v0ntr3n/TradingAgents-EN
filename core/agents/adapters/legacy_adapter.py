from __future__ import annotations
import sys as _sys

# === legacy_adapter ===
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


# === market_analyst ===
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


# === news_analyst ===
"""
News Analyst Agent

News analyst implementation based on BaseAgent
"""

from typing import Any, Dict, Optional

from ..base import BaseAgent
from ..config import AgentConfig, BUILTIN_AGENTS
from ..registry import register_agent


@register_agent
class NewsAnalystAgent(BaseAgent):
    """
    News Analyst Agent
    
    Analyze stock-related news, announcements, events, and more
    """
    
    metadata = BUILTIN_AGENTS["news_analyst"]
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._legacy_node = None
        self._llm = None
        self._toolkit = None
    
    def set_dependencies(self, llm: Any, toolkit: Any) -> "NewsAnalystAgent":
        """Set dependencies"""
        self._llm = llm
        self._toolkit = toolkit
        return self
    
    def initialize(self) -> None:
        """Initialize the agent"""
        if self._llm is None or self._toolkit is None:
            raise ValueError("must be called first set_dependencies() Set up LLM and toolkit")
        
        from tradingagents.agents.analysts.news_analyst import create_news_analyst
        self._legacy_node = create_news_analyst(self._llm, self._toolkit)
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform news analysis
        
        Args:
            state: A status dictionary containing the following keys:
                - company_of_interest: Stock code
                - trade_date: transaction date
                - messages: Message history
                
        Returns:
            The updated status includes:
                - news_report: News analysis report
                - messages: Updated message history
        """
        if self._legacy_node is None:
            self.initialize()
        
        return self._legacy_node(state)


# === fundamentals_analyst ===
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


# === social_analyst ===
"""
Social Media Analyst Agent

Social media analyst implementation based on BaseAgent
"""

from typing import Any, Dict, Optional

from ..base import BaseAgent
from ..config import AgentConfig, BUILTIN_AGENTS
from ..registry import register_agent


@register_agent
class SocialMediaAnalystAgent(BaseAgent):
    """
    Social Media Analyst Agent
    
    Analyze public opinion, sentiment, etc. on social media
    """
    
    metadata = BUILTIN_AGENTS["social_analyst"]
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._legacy_node = None
        self._llm = None
        self._toolkit = None
    
    def set_dependencies(self, llm: Any, toolkit: Any) -> "SocialMediaAnalystAgent":
        """Set dependencies"""
        self._llm = llm
        self._toolkit = toolkit
        return self
    
    def initialize(self) -> None:
        """Initialize the agent"""
        if self._llm is None or self._toolkit is None:
            raise ValueError("must be called first set_dependencies() Set up LLM and toolkit")
        
        from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst
        self._legacy_node = create_social_media_analyst(self._llm, self._toolkit)
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform social media analysis
        
        Args:
            state: A status dictionary containing the following keys:
                - company_of_interest: Stock code
                - trade_date: transaction date
                - messages: Message history
                
        Returns:
            The updated status includes:
                - sentiment_report: Social media sentiment analysis report
                - messages: Updated message history
        """
        if self._legacy_node is None:
            self.initialize()
        
        return self._legacy_node(state)


# === sector_analyst ===
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


# === index_analyst ===
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
            
            logger.info("✅ Market analysis completed")
            
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


# === review.timing_analyst ===
"""
Timing Analyst Agent

Analyze buying and selling timing and evaluate the rationality of trading timing selection
"""

import logging
from typing import Any, Dict, Optional

from ..base import BaseAgent
from ..config import AgentConfig, BUILTIN_AGENTS
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class TimingAnalystAgent(BaseAgent):
    """
    Timing Analyst Agent
    
    Analyze buying and selling timing, including:
    - Is it at a relatively low level when buying?
    - Is it at a relatively high level when selling?
    - The gap between the theoretical optimal buying and selling point
    - Is the holding period reasonable?
    """
    
    metadata = BUILTIN_AGENTS["timing_analyst"]
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._llm = None
    
    def set_dependencies(self, llm: Any, toolkit: Any = None) -> "TimingAnalystAgent":
        """Set dependencies"""
        self._llm = llm
        return self
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execution timing analysis
        
        Args:
            state: A status dictionary containing the following keys:
                - trade_info: transaction information (trades, holding_period, pnl Wait)
                - market_data: Market K-line data
                - benchmark_data: Benchmark data
                
        Returns:
            The updated status includes:
                - timing_analysis: Timing Analysis Report
        """
        logger.info("⏰ [timing analyst] Start analyzing trading opportunities...")

        # Extract input data
        trade_info = state.get("trade_info", {})
        market_data = state.get("market_data", {})

        logger.info(f"   📋 stocks: {trade_info.get('code', 'N/A')}, Number of transactions: {len(trade_info.get('trades', []))}")

        # Build prompt words (support user preferences)
        user_id = state.get("user_id")
        preference_id = state.get("preference_id", "neutral")
        prompt = self._build_prompt(trade_info, market_data, user_id, preference_id)
        logger.info(f"   📝 Prompt word length: {len(prompt)} character")

        # call LLM
        if self._llm:
            try:
                logger.info("   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
                logger.info(f"   📄 LLM Return content: {analysis[:100]}..." if len(analysis) > 100 else f"   📄 LLM Return content: {analysis}")
            except Exception as e:
                logger.error(f"   ❌ [timing analyst] LLM call failed: {e}")
                analysis = f"Timing analysis failed: {str(e)}"
        else:
            logger.warning("   ⚠️ LLM Not configured")
            analysis = "LLM Not configured, timing analysis cannot be performed"

        logger.info("⏰ [timing analyst] ✅ Analysis completed")

        # Only the newly added fields are returned, not the entire state (to avoid concurrent update conflicts)
        return {
            "timing_analysis": analysis,
        }
    
    def _build_prompt(self, trade_info: Dict, market_data: Dict, user_id: str = None, preference_id: str = "neutral") -> str:
        """Build timing analysis prompt words"""
        trades = trade_info.get("trades", [])

        # Format transaction records
        trade_list = []
        for t in trades:
            trade_list.append(
                f"- {t.get('date', 'N/A')}: {t.get('side', 'N/A')} "
                f"{t.get('quantity', 0)}shares @ {t.get('price', 0):.2f}"
            )
        trades_str = "\n".join(trade_list) if trade_list else "No transaction history"

        # Extract K-line data summary
        kline_summary = market_data.get("summary", "No K line data")

        # Prepare template variables
        template_variables = {
            "trades_str": trades_str,
            "kline_summary": kline_summary,
            "holding_period": trade_info.get('holding_period', 'N/A'),
            "avg_buy_price": trade_info.get('avg_buy_price', 0),
            "avg_sell_price": trade_info.get('avg_sell_price', 0),
            "return_rate": trade_info.get('return_rate', 0)
        }

        # Hardcoded downgrade prompt word
        fallback_prompt = f"""You are a professional trade timing analyst. Please analyze the timing of the following transactions:

## transaction history
{trades_str}

## Market data summary
{kline_summary}

## Transaction statistics
- Position period: {trade_info.get('holding_period', 'N/A')}day
- average buying price: {trade_info.get('avg_buy_price', 0):.2f}
- average selling price: {trade_info.get('avg_sell_price', 0):.2f}
- real rate of return: {trade_info.get('return_rate', 0):.2%}

## Analysis requirements
Please analyze timing selection from the following perspectives:
1. **Buying time assessment**: Was it at a relatively low level when buying? Chasing high?
2. **Assessing the timing of selling**: Was it at a relatively high level when selling? Cut the meat?
3. **Position cycle assessment**: Is the holding period reasonable? Is it too long or too short?
4. **Theoretical optimal comparison**: How big is the gap compared with the theoretical optimal buying and selling point?
5. **timing score**: Give your timing a score from 1-100

Please answer in concise and professional language."""

        # Try to get the prompt word from the template system
        try:
            from tradingagents.utils.template_client import get_agent_prompt

            prompt = get_agent_prompt(
                agent_type="reviewers",
                agent_name="timing_analyst",
                variables=template_variables,
                user_id=user_id,
                preference_id=preference_id,
                fallback_prompt=fallback_prompt,
                context=None
            )
            logger.info(f"✅ [timing analyst] Successfully obtained the prompt word from the template system (length: {len(prompt)})")
            return prompt

        except Exception as e:
            logger.warning(f"⚠️ [timing analyst] Template system acquisition failed, using the downgrade prompt word: {e}")
            return fallback_prompt


# === review.position_analyst ===
"""
Position Analyst Agent

Analyze the rationality of position control and position addition and subtraction strategies
"""

import logging
from typing import Any, Dict, Optional

from ..base import BaseAgent
from ..config import AgentConfig, BUILTIN_AGENTS
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class PositionAnalystAgent(BaseAgent):
    """
    Position Analyst Agent
    
    Analyze position management, including:
    - Is the initial position reasonable?
    - Timing and proportion of adding or subtracting positions
    - Matching position and risk
    - Fund utilization efficiency
    """
    
    metadata = BUILTIN_AGENTS["position_analyst"]
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._llm = None
    
    def set_dependencies(self, llm: Any, toolkit: Any = None) -> "PositionAnalystAgent":
        """Set dependencies"""
        self._llm = llm
        return self
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform position analysis
        
        Args:
            state: A status dictionary containing the following keys:
                - trade_info: transaction information
                - position_history: Position change history
                
        Returns:
            The updated status includes:
                - position_analysis: Position analysis report
        """
        trade_info = state.get("trade_info", {})

        logger.info("📊 [Position Analyst] Start analyzing position management...")
        logger.info(f"   📋 stocks: {trade_info.get('code', 'N/A')}, Number of transactions: {len(trade_info.get('trades', []))}")

        # Build prompt words (support user preferences)
        user_id = state.get("user_id")
        preference_id = state.get("preference_id", "neutral")
        prompt = self._build_prompt(trade_info, user_id, preference_id)
        logger.info(f"   📝 Prompt word length: {len(prompt)} character")

        if self._llm:
            try:
                logger.info("   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
                logger.info(f"   📄 LLM Return content: {analysis[:100]}..." if len(analysis) > 100 else f"   📄 LLM Return content: {analysis}")
            except Exception as e:
                logger.error(f"   ❌ [Position Analyst] LLM call failed: {e}")
                analysis = f"Position analysis failed: {str(e)}"
        else:
            logger.warning("   ⚠️ LLM Not configured")
            analysis = "LLM Not configured, position analysis cannot be performed"

        logger.info("📊 [Position Analyst] ✅ Analysis completed")

        # Only the newly added fields are returned, not the entire state (to avoid concurrent update conflicts)
        return {
            "position_analysis": analysis,
        }
    
    def _build_prompt(self, trade_info: Dict, user_id: str = None, preference_id: str = "neutral") -> str:
        """Construct position analysis prompt words"""
        trades = trade_info.get("trades", [])

        # Analyze position changes
        position_changes = []
        current_position = 0
        for t in trades:
            side = t.get("side", "")
            qty = t.get("quantity", 0)
            if side == "buy":
                current_position += qty
            else:
                current_position -= qty
            position_changes.append(
                f"- {t.get('date', 'N/A')}: {side} {qty}shares, Current position: {current_position}shares"
            )

        position_str = "\n".join(position_changes) if position_changes else "No position change record"

        # Prepare template variables
        template_variables = {
            "position_str": position_str,
            "total_buy_quantity": trade_info.get('total_buy_quantity', 0),
            "total_sell_quantity": trade_info.get('total_sell_quantity', 0),
            "total_cost": trade_info.get('total_cost', 0),
            "pnl": trade_info.get('pnl', 0)
        }

        # Hardcoded downgrade prompt word
        fallback_prompt = f"""You are a professional position management analyst. Please analyze the position control of the following transactions:

## Position change record
{position_str}

## Transaction statistics
- Total purchase quantity: {trade_info.get('total_buy_quantity', 0)}shares
- total sold quantity: {trade_info.get('total_sell_quantity', 0)}shares
- total investment capital: {trade_info.get('total_cost', 0):.2f}Yuan
- Actual profit and loss: {trade_info.get('pnl', 0):.2f}Yuan

## Analysis requirements
Please analyze position management from the following perspectives:
1. **Initial position evaluation**: Is the ratio of opening a position for the first time reasonable?
2. **Evaluation of position adding strategies**: Are the timing and proportion of adding positions appropriate? Do you buy more when it falls?
3. **Evaluation of position reduction strategy**: Are the timing and proportion of position reduction reasonable? Too early/too late?
4. **Risk control assessment**: Is the maximum position too heavy? Do you want to set a stop loss?
5. **Position score**: Give a position management score of 1-100

Please answer in concise and professional language."""

        prompt = self._get_prompt_from_template(
            agent_type="reviewers",
            agent_name="position_analyst",
            variables=template_variables,
            context={"user_id": user_id, "preference_id": preference_id},
            fallback_prompt=fallback_prompt
        )
        if prompt:
            logger.info(f"✅ [Position Analyst] Successfully obtained the prompt word from the template system (length: {len(prompt)})")
            return prompt
        logger.warning("⚠️ [Position Analyst] The template system did not return the prompt word, use the downgrade prompt word")
        return fallback_prompt


# === review.emotion_analyst ===
"""
Sentiment Analyst Agent

Analyze emotional operations and discipline execution in trading
"""

import logging
from typing import Any, Dict, Optional

from ..base import BaseAgent
from ..config import AgentConfig, BUILTIN_AGENTS
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class EmotionAnalystAgent(BaseAgent):
    """
    Sentiment Analyst Agent
    
    Analyze trading sentiment and discipline, including:
    - Is there any behavior of chasing the rise and killing the fall?
    - Is selling out of panic?
    - Is it excessive due to greed?
    - Implementation of trading disciplines
    """
    
    metadata = BUILTIN_AGENTS["emotion_analyst"]
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._llm = None
    
    def set_dependencies(self, llm: Any, toolkit: Any = None) -> "EmotionAnalystAgent":
        """Set dependencies"""
        self._llm = llm
        return self
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform sentiment analysis
        
        Args:
            state: A status dictionary containing the following keys:
                - trade_info: transaction information
                - market_data: market data (Used to judge whether to chase the rise or kill the fall)
                
        Returns:
            The updated status includes:
                - emotion_analysis: Sentiment Analysis Report
        """
        trade_info = state.get("trade_info", {})
        market_data = state.get("market_data", {})

        logger.info("😤 [sentiment analyst] Start analyzing emotional control...")
        logger.info(f"   📋 stocks: {trade_info.get('code', 'N/A')}, Number of transactions: {len(trade_info.get('trades', []))}")

        # Build prompt words (support user preferences)
        user_id = state.get("user_id")
        preference_id = state.get("preference_id", "neutral")
        prompt = self._build_prompt(trade_info, market_data, user_id, preference_id)
        logger.info(f"   📝 Prompt word length: {len(prompt)} character")

        if self._llm:
            try:
                logger.info("   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
                logger.info(f"   📄 LLM Return content: {analysis[:100]}..." if len(analysis) > 100 else f"   📄 LLM Return content: {analysis}")
            except Exception as e:
                logger.error(f"   ❌ [sentiment analyst] LLM call failed: {e}")
                analysis = f"Sentiment analysis failed: {str(e)}"
        else:
            logger.warning("   ⚠️ LLM Not configured")
            analysis = "LLM Not configured, sentiment analysis cannot be performed"

        logger.info("😤 [sentiment analyst] ✅ Analysis completed")

        # Only the newly added fields are returned, not the entire state (to avoid concurrent update conflicts)
        return {
            "emotion_analysis": analysis,
        }
    
    def _build_prompt(self, trade_info: Dict, market_data: Dict, user_id: str = None, preference_id: str = "neutral") -> str:
        """Construct sentiment analysis prompt words"""
        trades = trade_info.get("trades", [])

        # Analyze trading behavior patterns
        trade_patterns = []
        for t in trades:
            price_change = t.get("price_change_before", 0)  # Pre-trade price changes
            pattern = "Rising" if price_change > 0 else "Falling" if price_change < 0 else "In shock"
            trade_patterns.append(
                f"- {t.get('date', 'N/A')}: {t.get('side', 'N/A')} "
                f"(pre-trade market{pattern}, change{price_change:.2%})"
            )

        pattern_str = "\n".join(trade_patterns) if trade_patterns else "Unable to analyze trading patterns"

        # Prepare template variables
        template_variables = {
            "pattern_str": pattern_str,
            "return_rate": trade_info.get('return_rate', 0),
            "max_profit": trade_info.get('max_profit', 0),
            "max_loss": trade_info.get('max_loss', 0),
            "holding_period": trade_info.get('holding_period', 0)
        }

        # Hardcoded downgrade prompt word
        fallback_prompt = f"""You are a professional trading psychoanalyst. Please analyze the emotional factors in the following transactions:

## Trading behavior analysis
{pattern_str}

## Transaction results
- real rate of return: {trade_info.get('return_rate', 0):.2%}
- Maximum floating profit: {trade_info.get('max_profit', 0):.2%}
- Maximum floating loss: {trade_info.get('max_loss', 0):.2%}
- Position period: {trade_info.get('holding_period', 0)}day

## Analysis requirements
Please analyze trading sentiment from the following perspectives:
1. **Analysis of chasing the rise and killing the fall**: Do you want to buy when the price rises? Panic selling on dips?
2. **greed and fear**: Are you missing out on the best selling points due to greed? Are you taking profits/stops too early out of fear?
3. **Discipline Enforcement Assessment**: Do you have a clear trading plan? Is it strictly enforced?
4. **Emotional operation recognition**: Point out possible emotional manipulation and its impact
5. **sentiment score**: Give an emotional control score of 1-100

Please answer in concise and professional language and give suggestions for improvement."""

        # Try to get the prompt word from the template system
        try:
            from tradingagents.utils.template_client import get_agent_prompt

            prompt = get_agent_prompt(
                agent_type="reviewers",
                agent_name="emotion_analyst",
                variables=template_variables,
                user_id=user_id,
                preference_id=preference_id,
                fallback_prompt=fallback_prompt,
                context=None
            )
            logger.info(f"✅ [sentiment analyst] Successfully obtained the prompt word from the template system (length: {len(prompt)})")
            return prompt

        except Exception as e:
            logger.warning(f"⚠️ [sentiment analyst] Template system acquisition failed, using the downgrade prompt word: {e}")
            return fallback_prompt


# === review.attribution_analyst ===
"""
Attribution Analyst Agent

Analyze the sources of income and distinguish the Alpha contribution of the market/industry/individual stocks
"""

import logging
from typing import Any, Dict, Optional

from ..base import BaseAgent
from ..config import AgentConfig, BUILTIN_AGENTS
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class AttributionAnalystAgent(BaseAgent):
    """
    Attribution Analyst Agent
    
    Analyze revenue attribution, including:
    - Beta income (Market contribution)
    - Industry excess returns
    - individual stocks Alpha (Stock picking ability)
    - timely contribution
    """
    
    metadata = BUILTIN_AGENTS["attribution_analyst"]
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._llm = None
    
    def set_dependencies(self, llm: Any, toolkit: Any = None) -> "AttributionAnalystAgent":
        """Set dependencies"""
        self._llm = llm
        return self
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform attribution analysis
        
        Args:
            state: A status dictionary containing the following keys:
                - trade_info: transaction information
                - benchmark_data: Benchmark data (Market and industry indexes)
                
        Returns:
            The updated status includes:
                - attribution_analysis: Attribution analysis report
        """
        trade_info = state.get("trade_info", {})
        benchmark_data = state.get("benchmark_data", {})

        logger.info("📈 [attribution analyst] Start analyzing revenue attribution...")
        logger.info(f"   📋 stocks: {trade_info.get('code', 'N/A')}, Yield: {trade_info.get('return_rate', 0):.2%}")
        logger.info(f"   📊 benchmark: Market={benchmark_data.get('market_return', 0):.2%}, Industry={benchmark_data.get('industry_name', 'N/A')}")

        # Build prompt words (support user preferences)
        user_id = state.get("user_id")
        preference_id = state.get("preference_id", "neutral")
        prompt = self._build_prompt(trade_info, benchmark_data, user_id, preference_id)
        logger.info(f"   📝 Prompt word length: {len(prompt)} character")

        if self._llm:
            try:
                logger.info("   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
                logger.info(f"   📄 LLM Return content: {analysis[:100]}..." if len(analysis) > 100 else f"   📄 LLM Return content: {analysis}")
            except Exception as e:
                logger.error(f"   ❌ [attribution analyst] LLM call failed: {e}")
                analysis = f"Attribution analysis failed: {str(e)}"
        else:
            logger.warning("   ⚠️ LLM Not configured")
            analysis = "LLM Not configured for attribution analysis"

        logger.info("📈 [attribution analyst] ✅ Analysis completed")

        # Only the newly added fields are returned, not the entire state (to avoid concurrent update conflicts)
        return {
            "attribution_analysis": analysis,
        }
    
    def _build_prompt(self, trade_info: Dict, benchmark_data: Dict, user_id: str = None, preference_id: str = "neutral") -> str:
        """Build attribution analysis prompts"""
        # Extract benchmark data
        market_return = benchmark_data.get("market_return", 0)
        industry_return = benchmark_data.get("industry_return", 0)
        industry_name = benchmark_data.get("industry_name", "unknown industry")

        # Calculate excess returns
        stock_return = trade_info.get("return_rate", 0)

        # Prepare template variables
        template_variables = {
            "stock_return": stock_return,
            "market_return": market_return,
            "industry_name": industry_name,
            "industry_return": industry_return,
            "market_excess": stock_return - market_return,
            "industry_excess": stock_return - industry_return,
            "holding_period": trade_info.get('holding_period', 0),
            "avg_buy_price": trade_info.get('avg_buy_price', 0),
            "avg_sell_price": trade_info.get('avg_sell_price', 0)
        }

        # Hardcoded downgrade prompt word
        fallback_prompt = f"""You are a professional revenue attribution analyst. Please analyze the revenue sources of the following transactions:

## Revenue data
- individual stock return: {stock_return:.2%}
- Market returns over the same period: {market_return:.2%}
- Industry: {industry_name}
- Industry income during the same period: {industry_return:.2%}

## excess return calculation
- Relative to the market excess: {(stock_return - market_return):.2%}
- Relative to industry excess: {(stock_return - industry_return):.2%}

## transaction information
- Position period: {trade_info.get('holding_period', 0)}day
- average buying price: {trade_info.get('avg_buy_price', 0):.2f}
- average selling price: {trade_info.get('avg_sell_price', 0):.2f}

## Analysis requirements
Please perform revenue attribution from the following perspectives:
1. **Beta Revenue analysis**: How much revenue did the market contribute?
2. **Industry contribution analysis**: How much do industry factors contribute?
3. **Individual Stock Alpha Analysis**: How much does stock picking ability contribute?
4. **Timing contribution analysis**: How much does the timing of buying and selling contribute?
5. **Attribution score**: Give an investment ability score of 1-100

Please quantify the contribution of each factor and answer in concise and professional language."""

        # Try to get the prompt word from the template system
        try:
            from tradingagents.utils.template_client import get_agent_prompt

            prompt = get_agent_prompt(
                agent_type="reviewers",
                agent_name="attribution_analyst",
                variables=template_variables,
                user_id=user_id,
                preference_id=preference_id,
                fallback_prompt=fallback_prompt,
                context=None
            )
            logger.info(f"✅ [attribution analyst] Successfully obtained the prompt word from the template system (length: {len(prompt)})")
            return prompt

        except Exception as e:
            logger.warning(f"⚠️ [attribution analyst] Template system acquisition failed, using the downgrade prompt word: {e}")
            return fallback_prompt


# === review.review_manager ===
"""
Review summary expert agent

Comprehensive all analysis dimensions to generate a complete review report and improvement suggestions
"""

import logging
from typing import Any, Dict, Optional

from ..base import BaseAgent
from ..config import AgentConfig, BUILTIN_AGENTS
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class ReviewManagerAgent(BaseAgent):
    """
    Review summary expert agent
    
    Combining all analysis results, including:
    - Integrate timing, position, sentiment, and attribution analysis
    - Give an overall rating
    - Identify strengths and weaknesses
    - Make suggestions for improvements
    """
    
    metadata = BUILTIN_AGENTS["review_manager"]
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._llm = None
    
    def set_dependencies(self, llm: Any, toolkit: Any = None) -> "ReviewManagerAgent":
        """Set dependencies"""
        self._llm = llm
        return self
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute review summary
        
        Args:
            state: A status dictionary containing the following keys:
                - trade_info: transaction information
                - timing_analysis: Timing analysis results
                - position_analysis: Position analysis results
                - emotion_analysis: Sentiment analysis results
                - attribution_analysis: Attribution analysis results
                
        Returns:
            The updated status includes:
                - review_summary: Review summary report
                - overall_score: Overall rating
                - strengths: Advantage list
                - weaknesses: Deficiency list
                - suggestions: Improvement suggestions list
        """
        trade_info = state.get("trade_info", {})
        timing_analysis = state.get("timing_analysis", "No opportunity analysis")
        position_analysis = state.get("position_analysis", "No position analysis")
        emotion_analysis = state.get("emotion_analysis", "No sentiment analysis")
        attribution_analysis = state.get("attribution_analysis", "No attribution analysis")

        logger.info("📝 [Review summary expert] Start generating review report...")
        logger.info(f"   📋 stocks: {trade_info.get('code', 'N/A')}")
        logger.info("   📊 Analysis collected:")
        logger.info(f"      - Timing analysis: {len(timing_analysis)}character")
        logger.info(f"      - Position analysis: {len(position_analysis)}character")
        logger.info(f"      - sentiment analysis: {len(emotion_analysis)}character")
        logger.info(f"      - attribution analysis: {len(attribution_analysis)}character")

        # Build prompt words (support user preferences)
        user_id = state.get("user_id")
        preference_id = state.get("preference_id", "neutral")
        prompt = self._build_prompt(
            trade_info, timing_analysis, position_analysis,
            emotion_analysis, attribution_analysis, user_id, preference_id
        )
        logger.info(f"   📝 Prompt word length: {len(prompt)} character")

        if self._llm:
            try:
                logger.info("   🤖 Call LLM to generate a summary...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
            except Exception as e:
                logger.error(f"   ❌ [Review summary expert] LLM call failed: {e}")
                analysis = f"Review summary failed: {str(e)}"
        else:
            logger.warning("   ⚠️ LLM Not configured")
            analysis = "LLM Not configured, review summary cannot be performed"

        logger.info("📝 [Review summary expert] ✅ Report generation completed")

        # Only return new fields
        return {
            "review_summary": analysis,
        }
    
    def _build_prompt(
        self,
        trade_info: Dict,
        timing_analysis: str,
        position_analysis: str,
        emotion_analysis: str,
        attribution_analysis: str,
        user_id: str = None,
        preference_id: str = "neutral"
    ) -> str:
        """Construct review summary prompt words"""

        # Prepare template variables
        template_variables = {
            "ticker": trade_info.get('code', 'N/A'),
            "trade_period": f"{trade_info.get('holding_period', 0)}day",
            "total_return": trade_info.get('return_rate', 0),
            "total_pnl": trade_info.get('pnl', 0),
            "timing_analysis": timing_analysis,
            "position_analysis": position_analysis,
            "emotion_analysis": emotion_analysis,
            "attribution_analysis": attribution_analysis
        }

        # Hardcoded downgrade prompt word
        fallback_prompt = f"""You are a senior transaction review expert. Please comprehensively analyze the following dimensions to generate a complete review report:

## Transaction Overview
- stocks: {trade_info.get('code', 'N/A')} {trade_info.get('name', '')}
- Position period: {trade_info.get('holding_period', 0)}day
- real rate of return: {trade_info.get('return_rate', 0):.2%}
- Actual profit and loss: {trade_info.get('pnl', 0):.2f}Yuan

## Timing analysis
{timing_analysis}

## Position analysis
{position_analysis}

## sentiment analysis
{emotion_analysis}

## attribution analysis
{attribution_analysis}

## Output requirements
Please generate a structured review report,**Must be output in JSON format**: 

```json
{{
  "overall_score": 75,
  "timing_score": 80,
  "position_score": 70,
  "discipline_score": 75,
  "summary": "2-3 Summarize the overall performance of this transaction in one sentence",
  "strengths": [
    "Things done well 1",
    "Things done well 2",
    "Things done well 3"
  ],
  "weaknesses": [
    "areas for improvement 1",
    "areas for improvement 2",
    "areas for improvement 3"
  ],
  "suggestions": [
    "Specific and actionable improvement suggestions 1",
    "Specific and actionable improvement suggestions 2",
    "Specific and actionable improvement suggestions 3"
  ],
  "lesson": "Key lessons from this transaction"
}}
```

Scoring instructions:
- overall_score: total score (1-100)
- timing_score: timing score (1-100)
- position_score: Position management score (1-100)
- discipline_score: Discipline enforcement score (1-100)

Please make sure the output is in valid JSON format, use```json and```package."""

        prompt = self._get_prompt_from_template(
            agent_type="reviewers_v2",
            agent_name="review_manager_v2",
            variables=template_variables,
            context={"user_id": user_id, "preference_id": preference_id},
            fallback_prompt=fallback_prompt
        )
        if prompt:
            logger.info(f"✅ [Review summary expert] Successfully obtained the prompt word from the template system (length: {len(prompt)})")
            return prompt
        logger.warning("⚠️ [Review summary expert] The template system did not return the prompt word, use the downgrade prompt word")
        return fallback_prompt


# === position.technical_analyst ===
"""
Technical Analyst Agent

Analyze K-line trends, technical indicators, support and resistance levels, and evaluate technical status
"""

import logging
from typing import Any, Dict, Optional

from ..base import BaseAgent
from ..config import AgentConfig, BUILTIN_AGENTS
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class TechnicalAnalystAgent(BaseAgent):
    """
    Technical Analyst Agent
    
    Analyze the technical aspects of stock holdings, including:
    - K Line patterns and trends
    - Technical indicator status
    - Support and resistance level analysis
    - Short-term trend prediction
    """
    
    metadata = BUILTIN_AGENTS["pa_technical"]
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._llm = None
    
    def set_dependencies(self, llm: Any, toolkit: Any = None) -> "TechnicalAnalystAgent":
        """Set dependencies"""
        self._llm = llm
        return self
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Perform technical analysis"""
        logger.info("📈 [technical analyst] Start analysis...")

        position_info = state.get("position_info", {})
        market_data = state.get("market_data", {})

        logger.info(f"   📋 stocks: {position_info.get('code', 'N/A')}")

        user_id = state.get("user_id")
        preference_id = state.get("preference_id", "neutral")
        prompt = self._build_prompt(position_info, market_data, user_id, preference_id)
        logger.info(f"   📝 Prompt word length: {len(prompt)} character")

        if self._llm:
            try:
                logger.info("   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
            except Exception as e:
                logger.error(f"   ❌ LLM call failed: {e}")
                analysis = f"Technical analysis failed: {str(e)}"
        else:
            logger.warning("   ⚠️ LLM Not configured")
            analysis = "LLM Not configured, technical analysis cannot be performed"

        logger.info("📈 [technical analyst] ✅ Analysis completed")
        return {"technical_analysis": analysis}
    
    def _build_prompt(self, position_info: Dict, market_data: Dict, 
                      user_id: str = None, preference_id: str = "neutral") -> str:
        """Construct technical analysis prompt words"""
        template_variables = {
            "code": position_info.get("code", "N/A"),
            "name": position_info.get("name", "N/A"),
            "current_price": position_info.get("current_price", 0),
            "cost_price": position_info.get("cost_price", 0),
            "quantity": position_info.get("quantity", 0),
            "unrealized_pnl_pct": position_info.get("unrealized_pnl_pct", 0),
            "kline_summary": market_data.get("summary", "No K line data"),
            "technical_indicators": market_data.get("technical_indicators", "No technical indicator data"),
        }

        fallback_prompt = f"""You are a professional technical analyst. Please analyze the technical aspects of the following stocks::

## Position information
- Stock code: {position_info.get('code', 'N/A')}
- Stock name: {position_info.get('name', 'N/A')}
- cost price: {position_info.get('cost_price', 0):.2f}
- Current price: {position_info.get('current_price', 0):.2f}
- floating profit and loss: {position_info.get('unrealized_pnl_pct', 0):.2%}

## market data
{market_data.get('summary', 'No K line data')}

## Technical indicators
{market_data.get('technical_indicators', 'No technical indicator data')}

## Analysis requirements
1. **Trend judgment**: Currently in an upward/downward/oscillating trend
2. **support resistance**: Key support and resistance levels
3. **Technical indicators**: MACD/KDJ/RSI Waiting for indicator status
4. **short term prediction**: Possible trends in the next 3-5 days
5. **Technical rating**: 1-10 technical score

Please answer in concise and professional language."""

        prompt = self._get_prompt_from_template(
            agent_type="position_analysis",
            agent_name="pa_technical",
            variables=template_variables,
            context={"user_id": user_id, "preference_id": preference_id},
            fallback_prompt=fallback_prompt
        )
        if prompt:
            logger.info("✅ [technical analyst] Successfully obtained the prompt word from the template system")
            return prompt
        logger.warning("⚠️ [technical analyst] The template system did not return the prompt word, use the downgrade prompt word")
        return fallback_prompt


# === position.fundamental_analyst ===
"""
Fundamental Analyst Agent

Analyze financial data, valuation levels, industry status, and evaluate fundamental value
"""

import logging
from typing import Any, Dict, Optional

from ..base import BaseAgent
from ..config import AgentConfig, BUILTIN_AGENTS
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class FundamentalAnalystAgent(BaseAgent):
    """
    Fundamental Analyst Agent
    
    Analyze the fundamentals of stock holdings, including:
    - financial data analysis
    - Valuation level assessment
    - Industry status analysis
    - growth judgment
    """
    
    metadata = BUILTIN_AGENTS["pa_fundamental"]
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._llm = None
    
    def set_dependencies(self, llm: Any, toolkit: Any = None) -> "FundamentalAnalystAgent":
        """Set dependencies"""
        self._llm = llm
        return self
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Perform fundamental analysis"""
        logger.info("📊 [fundamental analyst] Start analysis...")

        position_info = state.get("position_info", {})
        stock_report = state.get("stock_analysis_report", {})

        logger.info(f"   📋 stocks: {position_info.get('code', 'N/A')}")

        user_id = state.get("user_id")
        preference_id = state.get("preference_id", "neutral")
        prompt = self._build_prompt(position_info, stock_report, user_id, preference_id)
        logger.info(f"   📝 Prompt word length: {len(prompt)} character")

        if self._llm:
            try:
                logger.info("   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
            except Exception as e:
                logger.error(f"   ❌ LLM call failed: {e}")
                analysis = f"Fundamental analysis failed: {str(e)}"
        else:
            logger.warning("   ⚠️ LLM Not configured")
            analysis = "LLM Not configured, fundamental analysis is not possible"

        logger.info("📊 [fundamental analyst] ✅ Analysis completed")
        return {"fundamental_analysis": analysis}
    
    def _build_prompt(self, position_info: Dict, stock_report: Dict,
                      user_id: str = None, preference_id: str = "neutral") -> str:
        """Construct fundamental analysis prompt words"""
        reports = stock_report.get("reports", {})
        fundamentals_report = reports.get("fundamentals_report", "No fundamental report yet")[:2000]
        
        template_variables = {
            "code": position_info.get("code", "N/A"),
            "name": position_info.get("name", "N/A"),
            "current_price": position_info.get("current_price", 0),
            "cost_price": position_info.get("cost_price", 0),
            "industry": position_info.get("industry", "unknown"),
            "fundamentals_report": fundamentals_report,
        }

        fallback_prompt = f"""You are a professional fundamental analyst. Please analyze the fundamentals of the following stocks::

## Position information
- Stock code: {position_info.get('code', 'N/A')}
- Stock name: {position_info.get('name', 'N/A')}
- Industry: {position_info.get('industry', 'unknown')}
- cost price: {position_info.get('cost_price', 0):.2f}
- Current price: {position_info.get('current_price', 0):.2f}

## fundamental report
{fundamentals_report}

## Analysis requirements
1. **financial condition**: Revenue, profit, cash flow analysis
2. **Valuation level**: PE/PB/PEG Valuation indicators such as
3. **Industry status**: Competitive advantage and market share
4. **Growth**: future growth potential
5. **fundamental score**: 1-10 fundamental score

Please answer in concise and professional language."""

        prompt = self._get_prompt_from_template(
            agent_type="position_analysis",
            agent_name="pa_fundamental",
            variables=template_variables,
            context={"user_id": user_id, "preference_id": preference_id},
            fallback_prompt=fallback_prompt
        )
        if prompt:
            logger.info("✅ [fundamental analyst] Successfully obtained the prompt word from the template system")
            return prompt
        logger.warning("⚠️ [fundamental analyst] The template system did not return the prompt word, use the downgrade prompt word")
        return fallback_prompt


# === position.risk_assessor ===
"""
Risk Assessor Agent

Assess position risks, analyze position rationality, and provide reference for risk and return concerns
"""

import logging
from typing import Any, Dict, Optional

from ..base import BaseAgent
from ..config import AgentConfig, BUILTIN_AGENTS
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class RiskAssessorAgent(BaseAgent):
    """
    Risk Assessor Agent
    
    Assess position risks, including:
    - Position risk assessment
    - Risk concerns and return concerns reference
    - Volatility analysis
    - Maximum drawdown estimate
    """
    
    metadata = BUILTIN_AGENTS["pa_risk"]
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._llm = None
    
    def set_dependencies(self, llm: Any, toolkit: Any = None) -> "RiskAssessorAgent":
        """Set dependencies"""
        self._llm = llm
        return self
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Perform risk assessment"""
        logger.info("⚠️ [risk assessor] Start assessment...")

        position_info = state.get("position_info", {})
        capital_info = state.get("capital_info", {})
        market_data = state.get("market_data", {})

        logger.info(f"   📋 stocks: {position_info.get('code', 'N/A')}")

        user_id = state.get("user_id")
        preference_id = state.get("preference_id", "neutral")
        prompt = self._build_prompt(position_info, capital_info, market_data, user_id, preference_id)
        logger.info(f"   📝 Prompt word length: {len(prompt)} character")

        if self._llm:
            try:
                logger.info("   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
            except Exception as e:
                logger.error(f"   ❌ LLM call failed: {e}")
                analysis = f"Risk assessment failed: {str(e)}"
        else:
            logger.warning("   ⚠️ LLM Not configured")
            analysis = "LLM Not configured for risk assessment"

        logger.info("⚠️ [risk assessor] ✅ Assessment completed")
        return {"risk_analysis": analysis}
    
    def _build_prompt(self, position_info: Dict, capital_info: Dict, market_data: Dict,
                      user_id: str = None, preference_id: str = "neutral") -> str:
        """Construct risk assessment prompt words"""
        # Calculate position proportion
        market_value = position_info.get("market_value", 0)
        total_assets = capital_info.get("total_assets", 0)
        position_ratio = (market_value / total_assets * 100) if total_assets > 0 else 0
        
        template_variables = {
            "code": position_info.get("code", "N/A"),
            "name": position_info.get("name", "N/A"),
            "current_price": position_info.get("current_price", 0),
            "cost_price": position_info.get("cost_price", 0),
            "quantity": position_info.get("quantity", 0),
            "market_value": market_value,
            "unrealized_pnl": position_info.get("unrealized_pnl", 0),
            "unrealized_pnl_pct": position_info.get("unrealized_pnl_pct", 0),
            "position_ratio": position_ratio,
            "total_assets": total_assets,
            "volatility": market_data.get("volatility", "unknown"),
        }

        fallback_prompt = f"""You are a professional risk assessor. Please evaluate the risk of the following positions:

## Position information
- Stock code: {position_info.get('code', 'N/A')}
- Stock name: {position_info.get('name', 'N/A')}
- Position quantity: {position_info.get('quantity', 0)} shares
- cost price: {position_info.get('cost_price', 0):.2f}
- Current price: {position_info.get('current_price', 0):.2f}
- Position market value: {market_value:.2f}
- floating profit and loss: {position_info.get('unrealized_pnl', 0):.2f} ({position_info.get('unrealized_pnl_pct', 0):.2%})

## Funding information
- total assets: {total_assets:.2f}
- Position proportion: {position_ratio:.2f}%

## Analysis requirements
1. **Position risk**: Is the current position overweight?
2. **Risk focus settings**: It is recommended to pay attention to the risk level
3. **Revenue focus settings**: It is recommended to pay attention to the price for income
4. **volatility risk**: Stock Volatility Assessment
5. **risk level**: Low/Medium/High Risk Rating

Please answer in concise and professional language."""

        prompt = self._get_prompt_from_template(
            agent_type="position_analysis",
            agent_name="pa_risk",
            variables=template_variables,
            context={"user_id": user_id, "preference_id": preference_id},
            fallback_prompt=fallback_prompt
        )
        if prompt:
            logger.info("✅ [risk assessor] Successfully obtained the prompt word from the template system")
            return prompt
        logger.warning("⚠️ [risk assessor] The template system did not return the prompt word, use the downgrade prompt word")
        return fallback_prompt


# === position.action_advisor ===
"""
Position Research Observer Agent

Comprehensive technical aspects, fundamentals, and risk assessments, and provide position research observations (non-trading suggestions)
"""

import logging
from typing import Any, Dict, Optional

from ..base import BaseAgent
from ..config import AgentConfig, BUILTIN_AGENTS
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class ActionAdvisorAgent(BaseAgent):
    """
    Position Research Observer Agent
    
    Comprehensive analysis of various dimensions, giving research observations on position positions:
    - Research conclusion tendency (optimistic/cautious/neutral)
    - Key verification price range
    - Risk concerns and return concerns reference
    - Risk warning
    """
    
    metadata = BUILTIN_AGENTS["pa_advisor"]
    
    def __init__(self, config: Optional[AgentConfig] = None):
        super().__init__(config)
        self._llm = None
    
    def set_dependencies(self, llm: Any, toolkit: Any = None) -> "ActionAdvisorAgent":
        """Set dependencies"""
        self._llm = llm
        return self
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Perform position research and observation analysis"""
        logger.info("💡 [Position Research Observer] Start comprehensive analysis...")

        position_info = state.get("position_info", {})
        technical_analysis = state.get("technical_analysis", "")
        fundamental_analysis = state.get("fundamental_analysis", "")
        risk_analysis = state.get("risk_analysis", "")
        user_goal = state.get("user_goal", {})

        logger.info(f"   📋 stocks: {position_info.get('code', 'N/A')}")

        user_id = state.get("user_id")
        preference_id = state.get("preference_id", "neutral")
        prompt = self._build_prompt(
            position_info, technical_analysis, fundamental_analysis, 
            risk_analysis, user_goal, user_id, preference_id
        )
        logger.info(f"   📝 Prompt word length: {len(prompt)} character")

        if self._llm:
            try:
                logger.info("   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
            except Exception as e:
                logger.error(f"   ❌ LLM call failed: {e}")
                analysis = f"Research observation generation failed: {str(e)}"
        else:
            logger.warning("   ⚠️ LLM Not configured")
            analysis = "LLM Not configured, cannot generate research observations"

        logger.info("💡 [Position Research Observer] ✅ Analysis completed")
        return {"action_advice": analysis}
    
    def _build_prompt(self, position_info: Dict, technical: str, fundamental: str,
                      risk: str, user_goal: Dict, user_id: str = None, 
                      preference_id: str = "neutral") -> str:
        """Construct position research observation prompt words"""
        template_variables = {
            "code": position_info.get("code", "N/A"),
            "name": position_info.get("name", "N/A"),
            "current_price": position_info.get("current_price", 0),
            "cost_price": position_info.get("cost_price", 0),
            "unrealized_pnl_pct": position_info.get("unrealized_pnl_pct", 0),
            "technical_analysis": technical[:1500] if technical else "No technical analysis",
            "fundamental_analysis": fundamental[:1500] if fundamental else "No fundamental analysis",
            "risk_analysis": risk[:1500] if risk else "Risk-free review",
            "target_return": user_goal.get("target_return", 10),
            "stop_loss": user_goal.get("stop_loss", -10),
        }

        fallback_prompt = f"""You are a professional investment analyst. Please provide a position analysis perspective based on the following analysis.:

## Position information
- stocks: {position_info.get('code', 'N/A')} {position_info.get('name', 'N/A')}
- cost price: {position_info.get('cost_price', 0):.2f}
- Current price: {position_info.get('current_price', 0):.2f}
- floating profit and loss: {position_info.get('unrealized_pnl_pct', 0):.2%}

## Technical analysis
{technical[:1500] if technical else 'None'}

## fundamental analysis
{fundamental[:1500] if fundamental else 'None'}

## risk review
{risk[:1500] if risk else 'None'}

## user goals
- target income: {user_goal.get('target_return', 10)}%
- price floor: {user_goal.get('stop_loss', -10)}%

## Output requirements
Please provide position research observations in JSON format:
```json
{{
    "analysis_view": "optimistic|Prudence|Neutral",
    "position_analysis": "Analysis of current positions (e.g.: attention/caution/wait-and-see)",
    "price_analysis_range": {{
        "lower_bound": Price range lower limit,
        "upper_bound": Upper price range,
        "current_position": "Analysis of the current price position in the range"
    }},
    "risk_reference_price": "Risk control reference price (for reference only, does not constitute trading advice)",
    "confidence": 0-100 degree of confidence,
    "risk_level": "low|in|high",
    "summary": "Comprehensive evaluation",
    "reasoning": "Analysis basis",
    "risk_warning": "Risk warning",
    "disclaimer": "This analysis is for reference only and does not constitute investment advice. Investment is risky and decisions need to be made with caution."
}}
```

**Disclaimer**: 
This analysis report is for reference only and does not constitute investment advice. All price ranges and market views are for analysis reference only.
It does not constitute buying or selling advice. Investment is risky and decisions need to be made with caution. Investors should consider the following based on their own circumstances:
Make investment decisions independently with the advice of professional investment consultants."""

        prompt = self._get_prompt_from_template(
            agent_type="position_analysis",
            agent_name="pa_advisor",
            variables=template_variables,
            context={"user_id": user_id, "preference_id": preference_id},
            fallback_prompt=fallback_prompt
        )
        if prompt:
            logger.info("✅ [Position Research Observer] Successfully obtained the prompt word from the template system")
            return prompt
        logger.warning("⚠️ [Position Research Observer] The template system did not return the prompt word, use the downgrade prompt word")
        return fallback_prompt


_self_mod = _sys.modules[__name__]
for _sub in ['legacy_adapter', 'market_analyst', 'news_analyst', 'fundamentals_analyst', 'social_analyst', 'sector_analyst', 'index_analyst', 'review.timing_analyst', 'review.position_analyst', 'review.emotion_analyst', 'review.attribution_analyst', 'review.review_manager', 'position.technical_analyst', 'position.fundamental_analyst', 'position.risk_assessor', 'position.action_advisor']:
    _sys.modules[f"core.agents.adapters.{_sub}"] = _self_mod