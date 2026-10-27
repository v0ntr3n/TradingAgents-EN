"""
Review summary expert v2.0 (Review analysis)

Review summarizer implemented based on ManagerAgent base class
"""

import logging
from typing import Dict, Any, List

from ...manager import ManagerAgent
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
        logger.info(f"🔍 [Review manager] Check the state in trading_plan...")
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
            logger.warning(f"⚠️ [Review manager] state There is no trading_plan field in!")

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
        logger.info(f"📊 [Review manager] Template variables:")
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

