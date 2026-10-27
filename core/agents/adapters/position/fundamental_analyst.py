"""
Fundamental Analyst Agent

Analyze financial data, valuation levels, industry status, and evaluate fundamental value
"""

import logging
from typing import Any, Dict, Optional

from ...base import BaseAgent
from ...config import AgentConfig, BUILTIN_AGENTS
from ...registry import register_agent

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
        logger.info(f"📊 [fundamental analyst] Start analysis...")

        position_info = state.get("position_info", {})
        stock_report = state.get("stock_analysis_report", {})

        logger.info(f"   📋 stocks: {position_info.get('code', 'N/A')}")

        user_id = state.get("user_id")
        preference_id = state.get("preference_id", "neutral")
        prompt = self._build_prompt(position_info, stock_report, user_id, preference_id)
        logger.info(f"   📝 Prompt word length: {len(prompt)} character")

        if self._llm:
            try:
                logger.info(f"   🤖 Call LLM analysis...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
            except Exception as e:
                logger.error(f"   ❌ LLM call failed: {e}")
                analysis = f"Fundamental analysis failed: {str(e)}"
        else:
            logger.warning(f"   ⚠️ LLM Not configured")
            analysis = "LLM Not configured, fundamental analysis is not possible"

        logger.info(f"📊 [fundamental analyst] ✅ Analysis completed")
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
            logger.info(f"✅ [fundamental analyst] Successfully obtained the prompt word from the template system")
            return prompt
        logger.warning(f"⚠️ [fundamental analyst] The template system did not return the prompt word, use the downgrade prompt word")
        return fallback_prompt

