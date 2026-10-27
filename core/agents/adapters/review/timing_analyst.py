"""
Timing Analyst Agent

Analyze buying and selling timing and evaluate the rationality of trading timing selection
"""

import logging
from typing import Any, Dict, Optional

from ...base import BaseAgent
from ...config import AgentConfig, BUILTIN_AGENTS
from ...registry import register_agent

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
        logger.info(f"⏰ [timing analyst] Start analyzing trading opportunities...")

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
                logger.info(f"   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
                logger.info(f"   📄 LLM Return content: {analysis[:100]}..." if len(analysis) > 100 else f"   📄 LLM Return content: {analysis}")
            except Exception as e:
                logger.error(f"   ❌ [timing analyst] LLM call failed: {e}")
                analysis = f"Timing analysis failed: {str(e)}"
        else:
            logger.warning(f"   ⚠️ LLM Not configured")
            analysis = "LLM Not configured, timing analysis cannot be performed"

        logger.info(f"⏰ [timing analyst] ✅ Analysis completed")

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

