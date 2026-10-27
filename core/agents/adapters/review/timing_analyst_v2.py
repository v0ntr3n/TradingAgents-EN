"""
timing analyst v2.0 (Review analysis)

Timing analyst implemented based on ResearcherAgent base class
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
class TimingAnalystV2(ResearcherAgent):
    """
    timing analyst v2.0 (Review analysis)
    
    Function:
    - Basis for review entry and exit
    - Evaluate the rationality of trading timing
    - Identify evidence deficiencies and disciplinary deviations
    
    Workflow:
    1. Read trading information and market data
    2. Using LLM to analyze timing selection
    3. Generate opportunity analysis report
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("timing_analyst_v2", llm)

        result = agent.execute({
            "trade_info": {...},
            "market_data": {...}
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="timing_analyst_v2",
        name="timing analyst v2.0",
        description="Review the basis for entry and exit, and evaluate the rationality of trading timing.",
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
            AgentOutput(name="timing_analysis", type="string", description="Timing analysis results"),
        ],
        growth_role="extractor",
        growth_outputs=["timing_analysis"],
        memory_scope_hint="pattern",
        review_level="auto_pending",
        growth_source_type="review_report",
    )

    researcher_type = "review_timing"
    stance = "neutral"
    output_field = "timing_analysis"

    def __init__(self, *args, **kwargs):
        """Initialization timing analyst v2.0"""
        super().__init__(*args, **kwargs)
        self._current_state = None  # used in _build_system_prompt() Visit in state

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execution analysis (rewritten to support trading plan rule injection)"""
        # Save state to instance variables for use in _build_system_prompt() Visit in
        self._current_state = state
        try:
            # Call parent class execute() method
            return super().execute(state)
        finally:
            # Clean up instance variables
            self._current_state = None

    def _build_system_prompt(self, stance: str, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words (including trading plan rules)
        
        Args:
            stance: research stance
            state: Workflow status (optional, used to extract variables such as company_name, ticker etc.)
        """
        # Downgrade prompt word (used when the template system is unavailable)
        fallback_prompt = """You are a professional timing analyst v2.0.

    Your responsibility is to review whether the trading timing is reasonable and to identify whether the basis for entry and exit is sufficient.

    **Analysis points**: 
    1. Basis for operation - whether there is sufficient evidence and pre-verification when opening a position
    2. Basis for operation - whether there is a clear basis for closing a position or continuing to track it
    3. Completeness of evidence - whether there is chasing, panic, noise-driven or insufficient verification
    4. Position holding period - whether the position holding time matches the original judgment
    5. Key points of verification and recording that need to be strengthened - What evidence verification or disciplinary records should be added after this review

    **Strict requirements**: 
    - No output allowed If it happens again, you should buy or sell at a certain price Such implementation suggestions.
    - The best buying and selling points, target prices, key prices, stop loss and profit or future operation plans are not allowed.
    - Improvement suggestions can only be written in the form of evidence verification, discipline enforcement and review process optimization.

    Please use Chinese and conduct objective analysis based on real data."""

        # 🆕 Get the trading plan from state (if any)
        trading_plan = None
        if self._current_state:
            trading_plan = self._current_state.get('trading_plan')

        # 🆕 Construct trading plan rules text
        trading_plan_section = ''
        if trading_plan:
            plan_name = trading_plan.get('plan_name', 'unnamed plan')
            timing_rules = trading_plan.get('rules', {}).get('timing', {})
            entry_signals = timing_rules.get('entry_signals', [])
            exit_signals = timing_rules.get('exit_signals', [])

            # 🔧 Array of processing objects: each signal is {'signal': '...', 'description': '...'}
            def format_signals(signals):
                """Formatted signal list (array of objects -> string list)"""
                if not signals:
                    return 'None'
                formatted = []
                for sig in signals:
                    if isinstance(sig, dict):
                        signal_text = sig.get('signal', '')
                        description = sig.get('description', '')
                        if description:
                            formatted.append(f"{signal_text} ({description})")
                        else:
                            formatted.append(signal_text)
                    else:
                        # If it is a string, use it directly
                        formatted.append(str(sig))
                return '; '.join(formatted) if formatted else 'None'

            if entry_signals or exit_signals:
                trading_plan_section = f"""

=== Associated trading plans ===
This transaction is associated with a trading plan:**{plan_name}**

**timing rules**: 
- Entry signal: {format_signals(entry_signals)}
- Exit signal: {format_signals(exit_signals)}

**Please check the key points in the analysis**: 
1. Whether the entry basis meets the entry signal requirements
2. Exit based on whether it meets the exit signal requirements
3. If there are any violations of the rules, please point them out clearly and explain what verifications should be added."""

        # Use the general method of the base class to obtain prompt words from the template system (supports injecting trading plan rules, refer to research_manager_v2)
        logger.info("🔍 [TimingAnalystV2] Start building system prompt words")
        
        variables = {'trading_plan_section': trading_plan_section} if trading_plan_section else {}
        prompt = self._get_prompt_from_template(
            agent_type="reviewers_v2",
            agent_name="timing_analyst_v2",
            variables=variables,  # Special variable: trading_plan_section (if any)
            state=self._current_state if self._current_state else state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=self._current_state.get("context") if self._current_state else (state.get("context") if state else None),  # Get from state context
            fallback_prompt=fallback_prompt,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        
        logger.info(f"📝 System prompt word length: {len(prompt)} character")
        if prompt:
            has_plan = " (Contains trading plan rules)" if trading_plan else " (No transaction plan)"
            logger.info(f"✅ Get timing analyst prompt words from template system {has_plan} (length: {len(prompt)})")
            return prompt

        # The downgrade prompt word must also include the trading plan rules
        return fallback_prompt + trading_plan_section

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        reports: Dict[str, str],
        historical_context: str,
        state: Dict[str, Any]
    ) -> str:
        """Construct user prompt words (obtained from template system and rendered)

        Note: The trading plan rules have been injected into the system prompt word, and only transaction data needs to be provided here.
        """
        trade_info = state.get("trade_info", {})
        market_data = state.get("market_data", {})

        code = trade_info.get("code", ticker)
        name = trade_info.get("name", code)
        trades = trade_info.get("trades", [])

        # Format transaction records
        trade_list = []
        for t in trades:
            trade_list.append(
                f"- {t.get('date', 'N/A')}: {t.get('side', 'N/A')} "
                f"{t.get('quantity', 0)}shares @ {t.get('price', 0):.2f}"
            )
        trade_str = "\n".join(trade_list) if trade_list else "No transaction history"

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
            'holding_days': trade_info.get('holding_days', 0),
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
            'trade_list': trade_str,
            'market_summary': market_data.get('summary', 'No market data')
        }

        # 🆕 Construct profit information text (including floating profit and loss) - used for template variables
        if is_holding and unrealized_pnl != 0:
            pnl_info_text = f"{pnl_sign}{total_pnl:.2f}Yuan (Realized: {realized_pnl:+.2f}Yuan, float: {unrealized_sign}{unrealized_pnl:.2f}Yuan)"
            return_info_text = f"{pnl_sign}{total_pnl_pct:.2f}% (Realized: {realized_pnl_pct:+.2f}%, float: {unrealized_sign}{unrealized_pnl_pct:.2f}%)"
        else:
            pnl_info_text = f"{pnl_sign}{total_pnl:.2f}Yuan"
            return_info_text = f"{pnl_sign}{total_pnl_pct:.2f}%"
        
        template_variables['pnl_info'] = pnl_info_text
        template_variables['return_info'] = return_info_text
        template_variables['holding_status'] = f"{'In position' if is_holding else 'Position closed'}"
        
        # Downgrade prompt word (if template system is not available)
        fallback_prompt = f"""Please analyze and review the timing of the following transactions:

=== transaction information ===
- Stock code: {code}
- Stock name: {name}
- Position period: {trade_info.get('holding_days', 0)}day
- Profit and loss amount: {pnl_info_text}
- Yield: {return_info_text}
- Position status: {'In position' if is_holding else 'Position closed'}

=== transaction history ===
{trade_str}

=== market data ===
{market_data.get('summary', 'No market data')}

Please write a detailed timing analysis report, including:
1. Admission basis assessment
2. Exit basis assessment
3. Evidence integrity and disciplinary deviations
4. Reasonableness of position holding cycle
5. Verification and recording points that need to be strengthened

It is prohibited to output the optimal buying and selling point, target price, key price, stop loss and profit or future operation plan."""

        # Print template variables (for debugging)
        logger.info(f"📊 [timing analyst] Template variables:")
        for key, value in template_variables.items():
            logger.info(f"  - {key}: {value}")

        # Use the general method of the base class to obtain the user prompt word
        prompt = self._get_prompt_from_template(
            agent_type="reviewers_v2",
            agent_name="timing_analyst_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if isinstance(state, dict) else state,  # Get from state context
            fallback_prompt=fallback_prompt,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        if prompt:
            logger.info(f"✅ Get timing analyst user prompt words from template system (length: {len(prompt)})")
            logger.info(f"📝 [timing analyst] end user prompts:\n{prompt}")
            return prompt

        # Downgrade: Use hardcoded prompt words
        logger.info(f"📝 [timing analyst] Use demotion prompts:\n{fallback_prompt}")
        return fallback_prompt

    def _get_required_reports(self) -> List[str]:
        """Get the required data list"""
        return ["trade_info", "market_data"]

