"""
Position Analyst Agent

Analyze the rationality of position control and position addition and subtraction strategies
"""

import logging
from typing import Any, Dict, Optional

from ...base import BaseAgent
from ...config import AgentConfig, BUILTIN_AGENTS
from ...registry import register_agent

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

        logger.info(f"📊 [Position Analyst] Start analyzing position management...")
        logger.info(f"   📋 stocks: {trade_info.get('code', 'N/A')}, Number of transactions: {len(trade_info.get('trades', []))}")

        # Build prompt words (support user preferences)
        user_id = state.get("user_id")
        preference_id = state.get("preference_id", "neutral")
        prompt = self._build_prompt(trade_info, user_id, preference_id)
        logger.info(f"   📝 Prompt word length: {len(prompt)} character")

        if self._llm:
            try:
                logger.info(f"   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
                logger.info(f"   📄 LLM Return content: {analysis[:100]}..." if len(analysis) > 100 else f"   📄 LLM Return content: {analysis}")
            except Exception as e:
                logger.error(f"   ❌ [Position Analyst] LLM call failed: {e}")
                analysis = f"Position analysis failed: {str(e)}"
        else:
            logger.warning(f"   ⚠️ LLM Not configured")
            analysis = "LLM Not configured, position analysis cannot be performed"

        logger.info(f"📊 [Position Analyst] ✅ Analysis completed")

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
        logger.warning(f"⚠️ [Position Analyst] The template system did not return the prompt word, use the downgrade prompt word")
        return fallback_prompt

