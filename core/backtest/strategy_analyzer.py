"""
LLM Strategic feasibility analysis
Users describe strategy ideas in natural language → AI Analyze feasibility
"""
import json
import logging
from typing import Any, Dict, Optional

from core.llm import UnifiedLLMClient
from core.llm.models import Message, MessageRole

logger = logging.getLogger(__name__)

ANALYZE_SYSTEM = """You are a professional quantitative backtesting analyst. The user will describe an investment strategy idea, and you need to analyze its feasibility.

 [Analysis Dimensions]
1. Is the strategy logic clear and back-testable?
2. Data availability (A-share daily line, financial indicators, etc.)
3. Risk points (overfitting, survivor bias, etc.)
4. Implementability of backtesting (can it be converted into a regularized strategy)

 [Output]
Answer in concise Chinese, including: feasibility conclusion, main risks, recommended backtest parameter range (such as backtest interval, number of positions, etc.).
No need to output JSON, natural language will do."""


async def analyze_strategy_feasibility(
    user_description: str,
    llm_client: Optional[UnifiedLLMClient] = None,
) -> str:
    """
    Analyze strategy feasibility
    Args:
        user_description: User natural language description
        llm_client: LLM Client, if not passed, it will be created from the database configuration.
    Returns:
        feasibility analysis text
    """
    client = llm_client
    if not client:
        from app.services.intelligent_assistant_service import get_coding_llm_config

        cfg = await get_coding_llm_config()
        if not cfg:
            return "LLM is not currently configured and policy analysis is not possible. Please configure the model in system settings."
        client = UnifiedLLMClient.from_config(cfg)

    messages = [
        Message(role=MessageRole.SYSTEM, content=ANALYZE_SYSTEM),
        Message(role=MessageRole.USER, content=user_description),
    ]
    try:
        response = await client.achat(messages)
        return response.content or ""
    except Exception as e:
        logger.exception("Strategy analysis failed")
        return f"Analysis error: {e}"
