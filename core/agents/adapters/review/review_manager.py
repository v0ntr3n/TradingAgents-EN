"""
Review summary expert agent

Comprehensive all analysis dimensions to generate a complete review report and improvement suggestions
"""

import logging
from typing import Any, Dict, Optional

from ...base import BaseAgent
from ...config import AgentConfig, BUILTIN_AGENTS
from ...registry import register_agent

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

        logger.info(f"📝 [Review summary expert] Start generating review report...")
        logger.info(f"   📋 stocks: {trade_info.get('code', 'N/A')}")
        logger.info(f"   📊 Analysis collected:")
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
                logger.info(f"   🤖 Call LLM to generate a summary...")
                response = self._llm.invoke(prompt)
                analysis = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"   ✅ LLM Return success, response length: {len(analysis)} character")
            except Exception as e:
                logger.error(f"   ❌ [Review summary expert] LLM call failed: {e}")
                analysis = f"Review summary failed: {str(e)}"
        else:
            logger.warning(f"   ⚠️ LLM Not configured")
            analysis = "LLM Not configured, review summary cannot be performed"

        logger.info(f"📝 [Review summary expert] ✅ Report generation completed")

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
        logger.warning(f"⚠️ [Review summary expert] The template system did not return the prompt word, use the downgrade prompt word")
        return fallback_prompt

