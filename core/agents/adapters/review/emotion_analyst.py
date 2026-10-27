"""
Sentiment Analyst Agent

Analyze emotional operations and discipline execution in trading
"""

import logging
from typing import Any, Dict, Optional

from ...base import BaseAgent
from ...config import AgentConfig, BUILTIN_AGENTS
from ...registry import register_agent

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

        logger.info(f"😤 [sentiment analyst] Start analyzing emotional control...")
        logger.info(f"   📋 stocks: {trade_info.get('code', 'N/A')}, Number of transactions: {len(trade_info.get('trades', []))}")

        # Build prompt words (support user preferences)
        user_id = state.get("user_id")
        preference_id = state.get("preference_id", "neutral")
        prompt = self._build_prompt(trade_info, market_data, user_id, preference_id)
        logger.info(f"   📝 Prompt word length: {len(prompt)} character")

        if self._llm:
            try:
                logger.info(f"   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
                logger.info(f"   📄 LLM Return content: {analysis[:100]}..." if len(analysis) > 100 else f"   📄 LLM Return content: {analysis}")
            except Exception as e:
                logger.error(f"   ❌ [sentiment analyst] LLM call failed: {e}")
                analysis = f"Sentiment analysis failed: {str(e)}"
        else:
            logger.warning(f"   ⚠️ LLM Not configured")
            analysis = "LLM Not configured, sentiment analysis cannot be performed"

        logger.info(f"😤 [sentiment analyst] ✅ Analysis completed")

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

