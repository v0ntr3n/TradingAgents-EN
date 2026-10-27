"""
attribution analyst v2.0 (Review analysis)

Attribution analyst implemented based on ResearcherAgent base class
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
class AttributionAnalystV2(ResearcherAgent):
    """
    attribution analyst v2.0 (Review analysis)
    
    Function:
    - Analyze revenue sources
    - Distinguish between market/industry/individual stock Alpha contribution
    - Assessing replicability versus chance
    
    Workflow:
    1. Read transaction information and benchmark data
    2. Analyze revenue attribution using LLM
    3. Generate attribution analysis report
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("attribution_analyst_v2", llm)

        result = agent.execute({
            "trade_info": {...},
            "benchmark_data": {...}
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="attribution_analyst_v2",
        name="attribution analyst v2.0",
        description="Analyze the sources of income and distinguish the Alpha contribution and replicability of the market/industry/individual stocks",
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
            AgentOutput(name="attribution_analysis", type="string", description="Attribution analysis results"),
        ],
        growth_role="extractor",
        growth_outputs=["attribution_analysis"],
        memory_scope_hint="pattern",
        review_level="auto_pending",
        growth_source_type="review_report",
    )

    researcher_type = "review_attribution"
    stance = "neutral"
    output_field = "attribution_analysis"

    def _build_system_prompt(self, stance: str, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words
        
        Args:
            stance: research stance
            state: Workflow status (optional, used to extract variables such as company_name, ticker etc.)
        """
        # Use the base class's general method to obtain prompt words from the template system (refer to research_manager_v2)
        logger.info("🔍 [AttributionAnalystV2] Start building system prompt words")
        
        prompt = self._get_prompt_from_template(
            agent_type="reviewers_v2",
            agent_name="attribution_analyst_v2",
            variables={},  # System prompt words do not require variables (refer to research_manager_v2)
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if state else None,  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        
        logger.info(f"📝 System prompt word length: {len(prompt)} character")
        if prompt:
            logger.info(f"✅ Get attribution analyst prompt words from template system (length: {len(prompt)})")
            return prompt
        
        return """You are a professional attribution analyst.

Your job is to analyze the source mix of gains or losses and identify which factors are replicable and which are just chance.

Analysis points:
1. Beta Earnings – Earnings contributed by the broader market
2. Industry Excess – The industry s excess return relative to the market
3. Individual Stock Alpha - excess returns brought about by stock picking ability
4. Timing Contribution – The contribution of buying and selling timing
5. Replicability - Which experiences can be reused and which should not be over-credited
6. Key points for follow-up research and review - which evidence needs to be strengthened and which conclusions should be cautiously attributed

Strict requirements: Improvement suggestions can only be written as directions for improving research and review capabilities, and may not be written as future trading actions.

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
        benchmark_data = state.get("benchmark_data", {})

        code = trade_info.get("code", ticker)
        name = trade_info.get("name", code)
        # 🆕 Use the total return (realized + floating profit and loss)
        realized_pnl_pct = trade_info.get("realized_pnl_pct", 0)
        unrealized_pnl_pct = trade_info.get("unrealized_pnl_pct", 0)
        is_holding = trade_info.get("is_holding", False)
        
        # 🆕 Calculate total return (including floating profit and loss)
        total_pnl_pct = realized_pnl_pct + unrealized_pnl_pct if is_holding else realized_pnl_pct
        stock_return = total_pnl_pct / 100  # Convert to decimal
        
        market_return = benchmark_data.get("market_return", 0)
        industry_return = benchmark_data.get("industry_return", 0)
        industry_name = benchmark_data.get("industry_name", "unknown industry")

        # Calculate excess returns
        market_excess = stock_return - market_return
        industry_excess = industry_return - market_return
        stock_alpha = stock_return - industry_return

        # Prepare template variables
        template_variables = {
            'code': code,
            'name': name,
            'stock_return': f"{stock_return * 100:.2f}",
            'realized_pnl_pct': f"{realized_pnl_pct:.2f}",
            'unrealized_pnl_pct': f"{unrealized_pnl_pct:.2f}",
            'is_holding': "Yes" if is_holding else "No",
            'holding_days': trade_info.get('holding_days', 0),
            'market_return': f"{market_return * 100:.2f}",
            'industry_name': industry_name,
            'industry_return': f"{industry_return * 100:.2f}",
            'market_excess': f"{market_excess * 100:.2f}",
            'industry_excess': f"{industry_excess * 100:.2f}",
            'stock_alpha': f"{stock_alpha * 100:.2f}"
        }

        # 🆕 Construct profit rate information (including floating profit and loss) - used for template variables
        if is_holding and unrealized_pnl_pct != 0:
            return_info_text = f"{stock_return:.2%} (Realized: {realized_pnl_pct/100:.2%}, float: {unrealized_pnl_pct/100:+.2%})"
        else:
            return_info_text = f"{stock_return:.2%}"
        
        template_variables['return_info'] = return_info_text
        template_variables['holding_status'] = f"{'In position' if is_holding else 'Position closed'}"
        
        # Downgrade prompt word (if template system is not available)
        fallback_prompt = f"""Please analyze the revenue attribution of the following transactions:

=== transaction information ===
- Stock code: {code}
- Stock name: {name}
- total stock return: {return_info_text}
- Position period: {trade_info.get('holding_days', 0)}day
- Position status: {'In position' if is_holding else 'Position closed'}

=== Benchmark data ===
- Market return: {market_return:.2%}
- Industry: {industry_name}
- Industry rate of return: {industry_return:.2%}

=== excess return decomposition ===
- Relative to the market excess: {market_excess:.2%}
- Industry excess returns: {industry_excess:.2%}
- individual stocks Alpha: {stock_alpha:.2%}

Please write a detailed attribution analysis report, including:
1. Beta Income analysis (contribution to the market)
2. Industry excess return analysis
3. Alpha analysis of individual stocks (stock selection ability)
4. Timing contribution analysis
5. Replicability and chance factor analysis
6. Follow-up research and review to strengthen key points

It is prohibited to output future trading actions, target prices, stop-loss and take-profit or position plans."""

        # Print template variables (for debugging)
        logger.info(f"📊 [attribution analyst] Template variables:")
        for key, value in template_variables.items():
            logger.info(f"  - {key}: {value}")

        # Use the general method of the base class to obtain the user prompt word (preference will be extracted from context/state)
        prompt = self._get_prompt_from_template(
            agent_type="reviewers_v2",
            agent_name="attribution_analyst_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if isinstance(state, dict) else state,  # Get from state context
            fallback_prompt=fallback_prompt,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        if prompt:
            logger.info(f"✅ Get attribution analyst user prompt words from template system (length: {len(prompt)})")
            logger.info(f"📝 [attribution analyst] end user prompts:\n{prompt}")
            return prompt

        # Downgrade: Use hardcoded prompt words
        logger.info(f"📝 [attribution analyst] Use demotion prompts:\n{fallback_prompt}")
        return fallback_prompt

    def _get_required_reports(self) -> List[str]:
        """Get the required data list"""
        return ["trade_info", "benchmark_data"]

