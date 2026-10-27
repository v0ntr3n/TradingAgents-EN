"""
sentiment analyst v2.0 (Review analysis)

Sentiment analyst implemented based on ResearcherAgent base class
"""

import logging
from typing import Dict, Any, List

from ...researcher import ResearcherAgent
from ...config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ...registry import register_agent

logger = logging.getLogger(__name__)

# Try importing the template system
try:
    from tradingagents.utils.template_client import get_agent_prompt, get_user_prompt
except (ImportError, KeyError) as e:
    logger.warning(f"Unable to import template system: {e}")
    get_agent_prompt = None
    get_user_prompt = None

# It is no longer necessary to import get_agent_prompt/get_user_prompt directly, use the _get_prompt_from_template method of the base class


@register_agent
class EmotionAnalystV2(ResearcherAgent):
    """
    sentiment analyst v2.0 (Review analysis)
    
    Function:
    - Analyzing Emotional Operations in Trading
    - Evaluate the execution of trading disciplines
    - Identify the behavior of chasing the rise and killing the fall
    
    Workflow:
    1. Read trading information and market data
    2. Analyzing emotional control using LLM
    3. Generate sentiment analysis report
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("emotion_analyst_v2", llm)

        result = agent.execute({
            "trade_info": {...},
            "market_data": {...}
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="emotion_analyst_v2",
        name="sentiment analyst v2.0",
        description="Analyze emotional operations and discipline execution in trading",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="trade_records", type="string", description="transaction history"),
            AgentInput(name="trade_info", type="object", description="Transaction information details", required=False),
            AgentInput(name="market_data", type="object", description="market data", required=False),
            AgentInput(name="benchmark_data", type="object", description="Benchmark data", required=False),
        ],
        outputs=[
            AgentOutput(name="emotion_analysis", type="string", description="Sentiment analysis results"),
        ],
        growth_role="extractor",
        growth_outputs=["emotion_analysis"],
        memory_scope_hint="pattern",
        review_level="manual_required",
        growth_source_type="review_report",
    )

    researcher_type = "review_emotion"
    stance = "neutral"
    output_field = "emotion_analysis"

    def _build_system_prompt(self, stance: str, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words
        
        Args:
            stance: research stance
            state: Workflow status (optional, used to extract variables such as company_name, ticker etc.)
        """
        # Use the base class's general method to obtain prompt words from the template system (refer to research_manager_v2)
        logger.info("🔍 [EmotionAnalystV2] Start building system prompt words")
        
        prompt = self._get_prompt_from_template(
            agent_type="reviewers_v2",
            agent_name="emotion_analyst_v2",
            variables={},  # System prompt words do not require variables (refer to research_manager_v2)
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if state else None,  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        
        logger.info(f"📝 System prompt word length: {len(prompt)} character")
        if prompt:
            logger.info(f"✅ Get sentiment analyst prompt words from template system (length: {len(prompt)})")
            return prompt
        
        return """You are a professional sentiment analyst.

Your role is to analyze emotional control and disciplined execution in trading.

Analysis points:
1. Chasing the rise and killing the fall - Is there any behavior of chasing the rise and killing the fall?
2. Panic Selling - Is Selling Due to Panic?
3. Greedy Holding - Whether you are over-holding due to greed
4. Trading Discipline – Implementation of Trading Discipline
5. Emotional and disciplinary points that need to be strengthened - what constraints, records or triggers should be added after this review

Strict requirements: Improvement suggestions can only be written as emotion recognition, discipline restraint and review habit optimization, and may not be written as future buying and selling instructions.

**important constraints**: 
- The real data provided in the user prompts must be used (stock code, stock name, income amount, rate of return, etc.)
- Don t make up or hardcode any data in your reports
- All numbers in the report must exactly match the data provided in the prompt word
- Do not generate date information (e.g."Analysis date: April 5, 2025") , The date is automatically generated by the system

Please use Chinese and conduct analysis based on real data."""

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        reports: Dict[str, str],
        historical_context: str,
        state: Dict[str, Any]
    ) -> str:
        """Construct user prompt words (obtained from template system and rendered)"""
        trade_info = state.get("trade_info", {})
        market_data = state.get("market_data", {})
        code = trade_info.get("code", ticker)
        name = trade_info.get("name", code)  # Get the stock name, or ticker if not available
        trades = trade_info.get("trades", [])

        # Analyze trading behavior patterns
        trade_patterns = []
        for t in trades:
            price_change = t.get("price_change_before", 0)
            pattern = "Rising" if price_change > 0 else "Falling" if price_change < 0 else "In shock"
            trade_patterns.append(
                f"- {t.get('date', 'N/A')}: {t.get('side', 'N/A')} "
                f"(pre-trade market{pattern}, change{price_change:.2%})"
            )
        pattern_str = "\n".join(trade_patterns) if trade_patterns else "Unable to analyze trading patterns"

        # Format revenue information
        realized_pnl = trade_info.get('realized_pnl', 0)
        realized_pnl_pct = trade_info.get('realized_pnl_pct', 0)
        # 🆕 Obtain floating profit and loss (when holding a position)
        unrealized_pnl = trade_info.get('unrealized_pnl', 0)
        unrealized_pnl_pct = trade_info.get('unrealized_pnl_pct', 0)
        is_holding = trade_info.get('is_holding', False)
        
        # 🆕 Calculate total profit and loss (realized + float)
        total_pnl = realized_pnl + unrealized_pnl if is_holding else realized_pnl
        total_pnl_pct = realized_pnl_pct + unrealized_pnl_pct if is_holding else realized_pnl_pct
        
        pnl_sign = "+" if total_pnl >= 0 else ""
        unrealized_sign = "+" if unrealized_pnl >= 0 else ""

        # Prepare template variables
        template_variables = {
            'code': code,
            'name': name,
            'trade_count': len(trades),
            'buy_count': len([t for t in trades if t.get('side') == 'buy']),
            'sell_count': len([t for t in trades if t.get('side') == 'sell']),
            'pnl_sign': pnl_sign,
            'realized_pnl': f"{realized_pnl:.2f}",
            'realized_pnl_pct': f"{realized_pnl_pct:.2f}",
            # 🆕 Add floating profit and loss and total profit and loss
            'unrealized_pnl': f"{unrealized_pnl:.2f}",
            'unrealized_pnl_pct': f"{unrealized_pnl_pct:.2f}",
            'unrealized_sign': unrealized_sign,
            'total_pnl': f"{total_pnl:.2f}",
            'total_pnl_pct': f"{total_pnl_pct:.2f}",
            'is_holding': "Yes" if is_holding else "No",
            'first_buy_date': trade_info.get('first_buy_date', 'N/A'),
            'last_sell_date': trade_info.get('last_sell_date', 'N/A'),
            'holding_days': trade_info.get('holding_days', 0),
            'trade_patterns': pattern_str,
            'market_summary': market_data.get('summary', 'No market data')
        }

        # 🆕 Construct profit information text (including floating profit and loss) - used for template variables
        if is_holding and unrealized_pnl != 0:
            pnl_info_text = f"total revenue: {pnl_sign}{total_pnl:.2f}Yuan ({pnl_sign}{total_pnl_pct:.2f}%) \n  - Realized: {realized_pnl:+.2f}Yuan ({realized_pnl_pct:+.2f}%) \n  - float: {unrealized_sign}{unrealized_pnl:.2f}Yuan ({unrealized_sign}{unrealized_pnl_pct:.2f}%) "
        else:
            pnl_info_text = f"total revenue: {pnl_sign}{total_pnl:.2f}Yuan ({pnl_sign}{total_pnl_pct:.2f}%) "
        
        template_variables['pnl_info'] = pnl_info_text
        template_variables['holding_status'] = f"{'In position' if is_holding else 'Position closed'}"
        
        # Downgrade prompt word (if template system is not available)
        fallback_prompt = f"""Please analyze the emotional control of the following transactions:

=== transaction information ===
- Stock code: {code}
- Stock name: {name}
- Number of transactions: {len(trades)} times ({len([t for t in trades if t.get('side') == 'buy'])} times purchased,{len([t for t in trades if t.get('side') == 'sell'])} sold)
- {pnl_info_text}
- Position period: {trade_info.get('first_buy_date', 'N/A')} to {trade_info.get('last_sell_date', 'N/A')} (Appointment {trade_info.get('holding_days', 0)} days)
- Position status: {'In position' if is_holding else 'Position closed'}

=== trading behavior patterns ===
{pattern_str}

=== market environment ===
{market_data.get('summary', 'No market data')}

**Important tips**: 
- Please use the ticker symbol and stock name provided above in the report title
- All data in the report (income amount, rate of return, holding period, etc.) must be completely consistent with the data provided above
- Do not make up or modify any data

Please write a detailed sentiment analysis report, including:
1. Identification of behavior of chasing the rise and killing the fall
2. Panic selling analysis
3. Greedy holding analysis
4. Trading Discipline Assessment
5. Emotional and discipline points that need reinforcement

It is prohibited to output future buying and selling orders, stop-loss and take-profit or position adjustment suggestions."""

        # Print template variables (for debugging)
        logger.info(f"📊 [sentiment analyst] Template variables:")
        for key, value in template_variables.items():
            logger.info(f"  - {key}: {value}")

        # Use the general method of the base class to obtain the user prompt word
        prompt = self._get_prompt_from_template(
            agent_type="reviewers_v2",
            agent_name="emotion_analyst_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if isinstance(state, dict) else state,  # Get from state context
            fallback_prompt=fallback_prompt,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        if prompt:
            logger.info(f"✅ Obtain sentiment analyst user prompt words from the template system (length: {len(prompt)})")
            logger.info(f"📝 [sentiment analyst] end user prompts:\n{prompt}")
            return prompt

        # Downgrade: Use hardcoded prompt words
        logger.info(f"📝 [sentiment analyst] Use demotion prompts:\n{fallback_prompt}")
        return fallback_prompt

    def _get_required_reports(self) -> List[str]:
        """Get the required data list"""
        return ["trade_info", "market_data"]

