"""
Technical Analyst Agent

Analyze K-line trends, technical indicators, support and resistance levels, and evaluate technical status
"""

import logging
from typing import Any, Dict, Optional

from ...base import BaseAgent
from ...config import AgentConfig, BUILTIN_AGENTS
from ...registry import register_agent

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
        logger.info(f"📈 [technical analyst] Start analysis...")

        position_info = state.get("position_info", {})
        market_data = state.get("market_data", {})

        logger.info(f"   📋 stocks: {position_info.get('code', 'N/A')}")

        user_id = state.get("user_id")
        preference_id = state.get("preference_id", "neutral")
        prompt = self._build_prompt(position_info, market_data, user_id, preference_id)
        logger.info(f"   📝 Prompt word length: {len(prompt)} character")

        if self._llm:
            try:
                logger.info(f"   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
            except Exception as e:
                logger.error(f"   ❌ LLM call failed: {e}")
                analysis = f"Technical analysis failed: {str(e)}"
        else:
            logger.warning(f"   ⚠️ LLM Not configured")
            analysis = "LLM Not configured, technical analysis cannot be performed"

        logger.info(f"📈 [technical analyst] ✅ Analysis completed")
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
            logger.info(f"✅ [technical analyst] Successfully obtained the prompt word from the template system")
            return prompt
        logger.warning(f"⚠️ [technical analyst] The template system did not return the prompt word, use the downgrade prompt word")
        return fallback_prompt

