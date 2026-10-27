"""
Position Research Observer Agent

Comprehensive technical aspects, fundamentals, and risk assessments, and provide position research observations (non-trading suggestions)
"""

import logging
from typing import Any, Dict, Optional

from ...base import BaseAgent
from ...config import AgentConfig, BUILTIN_AGENTS
from ...registry import register_agent

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
        logger.info(f"💡 [Position Research Observer] Start comprehensive analysis...")

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
                logger.info(f"   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
            except Exception as e:
                logger.error(f"   ❌ LLM call failed: {e}")
                analysis = f"Research observation generation failed: {str(e)}"
        else:
            logger.warning(f"   ⚠️ LLM Not configured")
            analysis = "LLM Not configured, cannot generate research observations"

        logger.info(f"💡 [Position Research Observer] ✅ Analysis completed")
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
            logger.info(f"✅ [Position Research Observer] Successfully obtained the prompt word from the template system")
            return prompt
        logger.warning(f"⚠️ [Position Research Observer] The template system did not return the prompt word, use the downgrade prompt word")
        return fallback_prompt

