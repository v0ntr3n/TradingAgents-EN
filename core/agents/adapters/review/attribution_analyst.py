"""
Attribution Analyst Agent

Analyze the sources of income and distinguish the Alpha contribution of the market/industry/individual stocks
"""

import logging
from typing import Any, Dict, Optional

from ...base import BaseAgent
from ...config import AgentConfig, BUILTIN_AGENTS
from ...registry import register_agent

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

        logger.info(f"📈 [attribution analyst] Start analyzing revenue attribution...")
        logger.info(f"   📋 stocks: {trade_info.get('code', 'N/A')}, Yield: {trade_info.get('return_rate', 0):.2%}")
        logger.info(f"   📊 benchmark: Market={benchmark_data.get('market_return', 0):.2%}, Industry={benchmark_data.get('industry_name', 'N/A')}")

        # Build prompt words (support user preferences)
        user_id = state.get("user_id")
        preference_id = state.get("preference_id", "neutral")
        prompt = self._build_prompt(trade_info, benchmark_data, user_id, preference_id)
        logger.info(f"   📝 Prompt word length: {len(prompt)} character")

        if self._llm:
            try:
                logger.info(f"   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
                logger.info(f"   📄 LLM Return content: {analysis[:100]}..." if len(analysis) > 100 else f"   📄 LLM Return content: {analysis}")
            except Exception as e:
                logger.error(f"   ❌ [attribution analyst] LLM call failed: {e}")
                analysis = f"Attribution analysis failed: {str(e)}"
        else:
            logger.warning(f"   ⚠️ LLM Not configured")
            analysis = "LLM Not configured for attribution analysis"

        logger.info(f"📈 [attribution analyst] ✅ Analysis completed")

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

