"""
Risk Assessor Agent

Assess position risks, analyze position rationality, and provide reference for risk and return concerns
"""

import logging
from typing import Any, Dict, Optional

from ...base import BaseAgent
from ...config import AgentConfig, BUILTIN_AGENTS
from ...registry import register_agent

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
        logger.info(f"⚠️ [risk assessor] Start assessment...")

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
                logger.info(f"   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
            except Exception as e:
                logger.error(f"   ❌ LLM call failed: {e}")
                analysis = f"Risk assessment failed: {str(e)}"
        else:
            logger.warning(f"   ⚠️ LLM Not configured")
            analysis = "LLM Not configured for risk assessment"

        logger.info(f"⚠️ [risk assessor] ✅ Assessment completed")
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
            logger.info(f"✅ [risk assessor] Successfully obtained the prompt word from the template system")
            return prompt
        logger.warning(f"⚠️ [risk assessor] The template system did not return the prompt word, use the downgrade prompt word")
        return fallback_prompt

