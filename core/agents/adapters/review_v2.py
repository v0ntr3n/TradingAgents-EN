from __future__ import annotations
import sys as _sys

# === review.timing_analyst_v2 ===
"""
timing analyst v2.0 (Review analysis)

Timing analyst implemented based on ResearcherAgent base class
"""

import logging
from typing import Dict, Any, List

from ..researcher import ResearcherAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

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
        logger.info("📊 [timing analyst] Template variables:")
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


# === review.position_analyst_v2 ===
"""
Position Analyst v2.0 (Review analysis)

Position analyst implemented based on ResearcherAgent base class
"""

import logging
from typing import Dict, Any, List

from ..researcher import ResearcherAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)

# Try importing the template system
try:
    from tradingagents.utils.template_client import get_agent_prompt, get_user_prompt
except (ImportError, KeyError) as e:
    logger.warning(f"Unable to import template system: {e}")
    get_agent_prompt = None
    get_user_prompt = None


@register_agent
class PositionAnalystV2(ResearcherAgent):
    """
    Position Analyst v2.0 (Review analysis)
    
    Function:
    - Review position control and position change basis
    - Assess position compatibility with risk
    - Analyze capital utilization efficiency and concentration risks
    
    Workflow:
    1. Read transaction information and position history
    2. Analyze position management using LLM
    3. Generate position analysis report
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("position_analyst_v2", llm)

        result = agent.execute({
            "trade_info": {...}
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="position_analyst_v2",
        name="Position Analyst v2.0",
        description="The rationality of review position control and position change basis",
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
            AgentOutput(name="position_analysis", type="string", description="Position analysis results"),
        ],
        growth_role="extractor",
        growth_outputs=["position_analysis"],
        memory_scope_hint="pattern",
        review_level="auto_pending",
        growth_source_type="review_report",
    )

    researcher_type = "review_position"
    stance = "neutral"
    output_field = "position_analysis"

    def __init__(self, *args, **kwargs):
        """Initialize position analyst v2.0"""
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
        fallback_prompt = """You are a professional position analyst v2.0.

    Your responsibility is to review the rationale of position management and identify position basis, risk exposure and discipline enforcement issues.

    **Analysis points**: 
    1. Initial position - Is the ratio of opening a position for the first time reasonable?
    2. Basis for position changes - Is there a clear basis for each position change?
    3. Risk matching - the match between position and risk
    4. Fund Efficiency - Fund Utilization Efficiency and Concentration Risk
    5. Key points of position discipline that need to be strengthened - What evidence records and risk constraints should be added after this review

**important constraints**: 
- The real data provided in the user prompts must be used (stock code, stock name, income amount, rate of return, etc.)
- Don t make up or hardcode any data in your reports
- All numbers in the report must exactly match the data provided in the prompt word
- Do not generate date information (e.g."Analysis date: April 5, 2025") , The date is automatically generated by the system

Please use Chinese and conduct objective analysis based on real data."""

        # 🆕 Get the trading plan from state (if any)
        trading_plan = None
        if self._current_state:
            trading_plan = self._current_state.get('trading_plan')

        # 🆕 Construct trading plan rules text
        trading_plan_section = ''
        if trading_plan:
            plan_name = trading_plan.get('plan_name', 'unnamed plan')
            position_rules = trading_plan.get('rules', {}).get('position', {})
            single_stock_limit = position_rules.get('single_stock_limit')
            max_stocks = position_rules.get('max_stocks')

            if single_stock_limit or max_stocks:
                trading_plan_section = f"""

=== Associated trading plans ===
This transaction is associated with a trading plan:**{plan_name}**

**Position rules**: 
- Single stock upper limit: {single_stock_limit}%
- Maximum number of shares held: {max_stocks}only

**Please check the key points in the analysis**: 
1. Whether the position exceeds the upper limit of a single stock
2. Is there a clear basis for position changes?
3. If there are any violations of the rules, please clearly point them out and explain how position discipline should be improved."""

        # Use the general method of the base class to obtain prompt words from the template system (supports injecting trading plan rules, refer to research_manager_v2)
        logger.info("🔍 [PositionAnalystV2] Start building system prompt words")
        
        variables = {'trading_plan_section': trading_plan_section} if trading_plan_section else {}
        prompt = self._get_prompt_from_template(
            agent_type="reviewers_v2",
            agent_name="position_analyst_v2",
            variables=variables,  # Special variable: trading_plan_section (if any)
            state=self._current_state if self._current_state else state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=self._current_state.get("context") if self._current_state else (state.get("context") if state else None),  # Get from state context
            fallback_prompt=fallback_prompt,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        
        logger.info(f"📝 System prompt word length: {len(prompt)} character")
        if prompt:
            has_plan = " (Contains trading plan rules)" if trading_plan else " (No transaction plan)"
            logger.info(f"✅ Obtain position analyst prompt words from the template system {has_plan} (length: {len(prompt)})")
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
        code = trade_info.get("code", ticker)
        name = trade_info.get("name", code)  # Get the stock name, or ticker if not available
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
        position_str = "\n".join(position_changes) if position_changes else "No position changes"

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
            'position_changes': position_str
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
        fallback_prompt = f"""Please analyze the position review of the following transactions:

=== transaction information ===
- Stock code: {code}
- Stock name: {name}
- Number of transactions: {len(trades)}
- Profit and loss amount: {pnl_info_text}
- Yield: {return_info_text}
- Position status: {'In position' if is_holding else 'Position closed'}

=== Position changes ===
{position_str}

**Important tips**: 
- Please use the ticker symbol and stock name provided above in the report title
- All data in the report (profit amount, rate of return, etc.) must be exactly consistent with the data provided above
- Do not make up or modify any data

Please write a detailed position analysis report, including:
1. Initial position evaluation
2. Position change basis analysis
3. Position and risk matching
4. Fund Utilization Efficiency and Concentration Risk
5. Key points of position discipline that need to be strengthened

It is prohibited to output future positions increase or decrease plans, target positions or specific execution actions."""

        # Print template variables (for debugging)
        logger.info("📊 [Position Analyst] Template variables:")
        for key, value in template_variables.items():
            logger.info(f"  - {key}: {value}")

        # Try to get the user prompt word from the template system
        if get_user_prompt:
            try:
                prompt = get_user_prompt(
                    agent_type="reviewers_v2",
                    agent_name="position_analyst_v2",
                    variables=template_variables,
                    preference_id="neutral",
                    fallback_prompt=fallback_prompt
                )
                if prompt:
                    logger.info(f"✅ Obtain position analyst user prompt words from the template system (length: {len(prompt)})")
                    logger.info(f"📝 [Position Analyst] end user prompts:\n{prompt}")
                    return prompt
            except Exception as e:
                logger.warning(f"Failed to obtain user prompt words from template system: {e}")

        # Downgrade: Use hardcoded prompt words
        logger.info(f"📝 [Position Analyst] Use demotion prompts:\n{fallback_prompt}")
        return fallback_prompt

    def _get_required_reports(self) -> List[str]:
        """Get the required data list"""
        return ["trade_info"]


# === review.emotion_analyst_v2 ===
"""
sentiment analyst v2.0 (Review analysis)

Sentiment analyst implemented based on ResearcherAgent base class
"""

import logging
from typing import Dict, Any, List

from ..researcher import ResearcherAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

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
        logger.info("📊 [sentiment analyst] Template variables:")
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


# === review.attribution_analyst_v2 ===
"""
attribution analyst v2.0 (Review analysis)

Attribution analyst implemented based on ResearcherAgent base class
"""

import logging
from typing import Dict, Any, List

from ..researcher import ResearcherAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

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
        logger.info("📊 [attribution analyst] Template variables:")
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


# === review.review_manager_v2 ===
"""
Review summary expert v2.0 (Review analysis)

Review summarizer implemented based on ManagerAgent base class
"""

import logging
from typing import Dict, Any, List

from ..manager import ManagerAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)

# Try importing the template system
try:
    from tradingagents.utils.template_client import get_agent_prompt, get_user_prompt
except (ImportError, KeyError) as e:
    logger.warning(f"Unable to import template system: {e}")
    get_agent_prompt = None
    get_user_prompt = None


@register_agent
class ReviewManagerV2(ManagerAgent):
    """
    Review summary expert v2.0 (Review analysis)
    
    Function:
    - Integrating all dimensions of analysis
    - Generate a complete review report
    - Provide non-executive improvement directions
    
    Workflow:
    1. Read the analysis results of each dimension
    2. Comprehensive summary using LLM
    3. Generate review reports and improvement suggestions
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("review_manager_v2", llm)

        result = agent.execute({
            "trade_info": {...},
            "timing_analysis": "...",
            "position_analysis": "...",
            "emotion_analysis": "...",
            "attribution_analysis": "..."
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="review_manager_v2",
        name="Review summary expert v2.0",
        description="Comprehensive all analysis dimensions to generate a complete review report and improvement directions",
        category=AgentCategory.MANAGER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="trade_records", type="string", description="transaction history"),
            AgentInput(name="trade_info", type="object", description="Transaction information details", required=False),
            AgentInput(name="market_data", type="object", description="market data", required=False),
            AgentInput(name="benchmark_data", type="object", description="Benchmark data", required=False),
            AgentInput(name="timing_analysis", type="string", description="Timing analysis results", required=False),
            AgentInput(name="position_analysis", type="string", description="Position analysis results", required=False),
            AgentInput(name="emotion_analysis", type="string", description="Sentiment analysis results", required=False),
            AgentInput(name="attribution_analysis", type="string", description="Attribution analysis results", required=False),
        ],
        outputs=[
            AgentOutput(name="review_summary", type="string", description="Review summary report"),
        ],
        growth_role="optimizer",
        growth_outputs=["review_summary"],
        memory_scope_hint="research_asset",
        review_level="manual_required",
        growth_source_type="manager_decision",
    )

    manager_type = "review_manager"
    output_field = "review_summary"
    enable_debate = False

    def __init__(self, *args, **kwargs):
        """Initial review summary division v2.0"""
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

    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words (including trading plan rules)
        
        Args:
            state: Workflow status (optional, used to extract variables such as company_name, ticker etc.)
        """
        fallback_prompt = """You are a professional review summarizer v2.0.

Your responsibility is to comprehensively analyze all dimensions and generate a complete review report and improvement directions.

**Summary points**: 
1. Review conclusion - summarize the core gains and losses of this transaction in straightforward language
2. Strengths Identification – What did this transaction do right?
3. Weakness Analysis - What problems were exposed in this transaction?
4. Directions for improvement - Focus on discipline, research and optimization of processes
5. Experience Summary - Reusable Lessons Learned

Please use Chinese and make an objective summary based on real data.

Output format requirements:
Please provide the review report in JSON format:
```json
{
    "summary": "2-3 A review conclusion of one sentence, highlighting the core gains and losses and key issues (must be a string, not an object)",
    "strengths": ["Advantages 1", "Advantages 2", "Advantages 3"],
    "weaknesses": ["Insufficient 1", "Insufficient 2", "Insufficient 3"],
    "suggestions": ["Improvement points 1", "Improvement points 2", "Improvement points 3"],
    "lessons": "Summary of lessons learned (must be a string)"
}
```

**Important tips**: 
1. If the compatible link still requires overall_score, timing_score, position_score, discipline_score, you can optionally fill in an integer from 0 to 100, but do not let the narrative revolve around the score.
2. summary and lessons must be strings, not objects or arrays
3. strengths, weaknesses, suggestions Must be a string array
4. suggestions It can only be written as review improvement directions, research reinforcement points or process optimization points. It is not allowed to be written as future execution actions such as buying and selling, increasing or decreasing positions, stop loss and profit.
5. Do not include dates in the output (e.g."2025 April 5") , The date is automatically generated by the system"""

        # 🆕 Get the trading plan from state (if any)
        trading_plan = None
        if self._current_state:
            trading_plan = self._current_state.get('trading_plan')

        # 🆕 Construct trading plan rules text
        trading_plan_section = ''
        if trading_plan:
            plan_name = trading_plan.get('plan_name', 'unnamed plan')
            trading_plan_section = f"""

=== Trading Plan Compliance ===
This transaction is associated with a trading plan:**{plan_name}**

Please add it to the review report"Trading Plan Compliance"Part, summary:
1. Rule violations found in each dimension analysis
2. Overall Compliance Rating
3. Improvement directions for rule violations shall not be written as future trading instructions."""

        # Use the general method of the base class to obtain prompt words from the template system (supports injecting trading plan rules)
        variables = {'trading_plan_section': trading_plan_section}
        prompt = self._get_prompt_from_template(
            agent_type="reviewers_v2",
            agent_name="review_manager_v2",
            variables=variables,
            state=self._current_state if self._current_state else state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=self._current_state.get("context") if self._current_state else (state.get("context") if state else None),  # Get from state context
            fallback_prompt=fallback_prompt,
            prompt_type="system"  # ✅ Key: Specify to obtain system prompt words (including output_format)
        )
        if prompt:
            has_plan = " (Contains trading plan rules)" if trading_plan else " (No transaction plan)"
            logger.info(f"✅ Obtain the review summary expert s prompt words from the template system {has_plan} (length: {len(prompt)})")
            logger.info(f"📝 [System prompt word] full content:\n{prompt}")
            return prompt

        logger.info(f"⚠️ Use demotion prompts (length: {len(fallback_prompt + trading_plan_section)})")
        logger.info(f"📝 [Downgrade prompt word] full content:\n{fallback_prompt + trading_plan_section}")
        return fallback_prompt + trading_plan_section

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        inputs: Dict[str, str],
        debate_summary: str,
        state: Dict[str, Any]
    ) -> str:
        """Construct user prompt words (obtained from template system and rendered)

        Note: The trading plan rules have been injected into the system prompt words, and only the analysis data needs to be provided here.
        """
        trade_info = state.get("trade_info", {})
        code = trade_info.get("code", ticker)
        name = trade_info.get("name", code)

        # Extract analysis of each dimension (slicing outside the f-string)
        timing = state.get("timing_analysis", "No opportunity analysis")
        position = state.get("position_analysis", "No position analysis")
        emotion = state.get("emotion_analysis", "No sentiment analysis")
        attribution = state.get("attribution_analysis", "No attribution analysis")

        # 🔧 Extract the content field from the dictionary (ResearcherAgent returns a dictionary)
        def extract_content(data):
            """Extract content from analysis results"""
            if isinstance(data, dict):
                return data.get('content', str(data))
            return str(data)

        # Truncate long text (to avoid too many tokens)
        timing_text = extract_content(timing)[:1500]
        position_text = extract_content(position)[:1500]
        emotion_text = extract_content(emotion)[:1500]
        attribution_text = extract_content(attribution)[:1500]

        # Format revenue information (using correct field names)
        realized_pnl = trade_info.get('realized_pnl', 0)
        realized_pnl_pct = trade_info.get('realized_pnl_pct', 0)
        # 🆕 Obtain floating profit and loss (when holding a position)
        unrealized_pnl = trade_info.get('unrealized_pnl', 0)
        unrealized_pnl_pct = trade_info.get('unrealized_pnl_pct', 0)
        is_holding = trade_info.get('is_holding', False)
        current_price = trade_info.get('current_price')
        
        # 🆕 Calculate total profit and loss (realized + float)
        total_pnl = realized_pnl + unrealized_pnl if is_holding else realized_pnl
        total_pnl_pct = realized_pnl_pct + unrealized_pnl_pct if is_holding else realized_pnl_pct
        
        pnl_sign = "+" if total_pnl >= 0 else ""
        unrealized_sign = "+" if unrealized_pnl >= 0 else ""

        # Prepare template variables
        template_variables = {
            'code': code,
            'name': name,
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
            'current_price': f"{current_price:.2f}" if current_price else "N/A",
            'holding_days': trade_info.get('holding_days', 0),
            'timing_analysis': timing_text,
            'position_analysis': position_text,
            'emotion_analysis': emotion_text,
            'attribution_analysis': attribution_text
        }

        # 🆕 If there is a trading plan, add trading plan variables
        logger.info("🔍 [Review manager] Check the state in trading_plan...")
        logger.info(f"🔍 [Review manager] state all keys of: {list(state.keys())}")

        trading_plan = state.get('trading_plan')
        if trading_plan:
            # 🔧 Templates use nested variable references (such as {{trading_plan.plan_name}}) 
            # The entire trading_plan dictionary needs to be passed, but make sure all values are strings or primitive types
            template_variables['trading_plan'] = {
                'plan_name': str(trading_plan.get('plan_name', '')),
                'style': str(trading_plan.get('style', '')),
                'rules_text': str(trading_plan.get('rules_text', ''))
            }
            template_variables['trading_analysis_plan'] = dict(template_variables['trading_plan'])

            logger.info(f"✅ [Review manager] Trading plan detected: {trading_plan.get('plan_name', 'N/A')}")
            logger.info(f"   - plan_id: {trading_plan.get('plan_id', 'N/A')}")
            logger.info(f"   - style: {trading_plan.get('style', 'N/A')}")
            logger.info(f"   - rules_text length: {len(trading_plan.get('rules_text', ''))}")
        else:
            logger.warning("⚠️ [Review manager] state There is no trading_plan field in!")

        # 🆕 Construct profit information text (including floating profit and loss) - used for template variables
        # Build the complete text based on the condition instead of letting the template handle the condition
        if is_holding and unrealized_pnl != 0:
            pnl_info_text = f"{pnl_sign}{total_pnl:.2f}Yuan (Realized: {realized_pnl:+.2f}Yuan, float: {unrealized_sign}{unrealized_pnl:.2f}Yuan)"
            return_info_text = f"{pnl_sign}{total_pnl_pct:.2f}% (Realized: {realized_pnl_pct:+.2f}%, float: {unrealized_sign}{unrealized_pnl_pct:.2f}%)"
        else:
            pnl_info_text = f"{pnl_sign}{total_pnl:.2f}Yuan"
            return_info_text = f"{pnl_sign}{total_pnl_pct:.2f}%"
        
        holding_status_text = f"{'In position' if is_holding else 'Position closed'}"
        if is_holding and current_price:
            holding_status_text += f" (current price: {current_price:.2f})"
        
        # Add to template variables
        template_variables['pnl_info'] = pnl_info_text
        template_variables['return_info'] = return_info_text
        template_variables['holding_status'] = holding_status_text
        
        # Downgrade prompt word (if template system is not available)
        fallback_prompt = f"""Please combine the following analysis to generate a review report:

=== transaction information ===
- Stock code: {code}
- Stock name: {name}
- Profit and loss amount: {pnl_info_text}
- Yield: {return_info_text}
- Position status: {holding_status_text}
- Position period: {trade_info.get('holding_days', 0)}day

=== Timing analysis ===
{timing_text}

=== Position analysis ===
{position_text}

=== sentiment analysis ===
{emotion_text}

=== attribution analysis ===
{attribution_text}

**Important tips**: 
- If the trade is still open, please consider the realized profit and loss and floating profit and loss to evaluate the overall performance.
- Floating profit and loss reflects the potential profit/loss of the current position and is an important indicator for evaluating trading decisions.
- Don t think of a trade solely based on realized P&L (which may be 0)"Return to zero", Comprehensive evaluation should be conducted based on floating profits and losses

Please provide the review report in JSON format.

Note: The score field is reserved for compatibility only. The review conclusion should focus on problem identification, experience summary and subsequent research and improvement.
It is prohibited to write suggestions as buying or selling, adding or subtracting positions, stop loss and take profit, position adjustment or It should be executed at a certain price next time Such future actions."""

        # Print template variables (for debugging)
        logger.info("📊 [Review manager] Template variables:")
        for key, value in template_variables.items():
            # The analysis report content is too long, only the first 100 characters are printed.
            if key.endswith('_analysis'):
                logger.info(f"  - {key}: {str(value)[:100]}...")
            else:
                logger.info(f"  - {key}: {value}")

        # Try to get the user prompt word from the template system
        if get_user_prompt:
            try:
                # 🆕 Choose different ones depending on whether you have a trading plan preference_id
                preference_id = "with_plan" if trading_plan else "neutral"
                logger.info(f"📋 [Review manager] Use preference_id: {preference_id}")

                prompt = get_user_prompt(
                    agent_type="reviewers_v2",
                    agent_name="review_manager_v2",
                    variables=template_variables,
                    preference_id=preference_id,
                    fallback_prompt=fallback_prompt
                )
                if prompt:
                    has_plan_tag = " ((Including trading plan)" if trading_plan else " (No transaction plan)"
                    logger.info(f"✅ Obtain the review manager user prompt word from the template system {has_plan_tag} (length: {len(prompt)})")
                    logger.info(f"📝 [Review manager] end user prompts:\n{prompt}")
                    return prompt
            except Exception as e:
                logger.warning(f"Failed to obtain user prompt words from template system: {e}")

        # Downgrade: Use hardcoded prompt words
        logger.info(f"📝 [Review manager] Use demotion prompts:\n{fallback_prompt}")
        return fallback_prompt

    def _get_required_inputs(self) -> List[str]:
        """Get the required input list"""
        return [
            "timing_analysis",
            "position_analysis",
            "emotion_analysis",
            "attribution_analysis"
        ]


_self_mod = _sys.modules[__name__]
for _sub in ['review.timing_analyst_v2', 'review.position_analyst_v2', 'review.emotion_analyst_v2', 'review.attribution_analyst_v2', 'review.review_manager_v2']:
    _sys.modules[f"core.agents.adapters.{_sub}"] = _self_mod