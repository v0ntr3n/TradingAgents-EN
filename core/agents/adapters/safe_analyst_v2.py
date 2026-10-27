"""
Defense Scenario Analyst v2.0

Defense Scenario Analyst implementation based on the ResearcherAgent base class.
Review comprehensive research conclusions from a conservative perspective, prioritizing the identification of vulnerabilities, failure conditions and downside risks.
Supports multi-round debate and caching system.
"""

import logging
from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage

from ..researcher import ResearcherAgent
from ..registry import register_agent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput

logger = logging.getLogger(__name__)

# Try importing the template system
try:
    from tradingagents.utils.template_client import get_agent_prompt
except (ImportError, KeyError):
    logger.warning("Unable to import get_agent_prompt, default prompt word will be used")
    get_agent_prompt = None

# It is no longer necessary to import get_agent_prompt directly, use the _get_prompt_from_template method of the base class


@register_agent
class SafeAnalystV2(ResearcherAgent):
    """
    Defense Scenario Analyst v2.0

    Function:
    - Review comprehensive research conclusions from a conservative perspective
    - Prioritize identification of vulnerabilities and key sources of risk
    - Focus on failure conditions and downside scenarios
    - Highlight information gaps that need to be clarified first
    - Supports multiple rounds of debate (with aggressive and neutral analysts)
    - Supports caching system (avoids repeated analysis)

    Workflow:
    1. Read comprehensive research conclusions and market analysis
    2. Read debate history and opponents views
    3. Use LLM to review conclusion vulnerabilities from a conservative perspective and refute opponents
    4. Generate defensive scenario views
    5. Update debate status

    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("safe_analyst_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15",
            "investment_plan": "...",
            "bull_opinion": "...",
            "bear_opinion": "...",
            "risk_debate_state": {
                "history": "...",
                "safe_history": "...",
                "current_risky_response": "...",
                "current_neutral_response": "...",
                "count": 0
            }
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="safe_analyst_v2",
        name="Defense Scenario Analyst v2.0",
        description="Review the research conclusions from the perspective that are most likely to fail, and identify fragile premises, risk sources and downward revision triggering conditions",
        category=AgentCategory.RISK,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],  # Risk analysts don't need tools
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="investment_plan", type="string", description="Comprehensive research conclusion", source="state", state_field="investment_plan", source_state_fields=["trader_investment_plan"], producer_hint="research_manager_v2"),
            AgentInput(name="bull_opinion", type="string", description="optimistic scenario view", required=False, source="state", state_field="bull_report", producer_hint="bull_researcher_v2"),
            AgentInput(name="bear_opinion", type="string", description="prudent situational view", required=False, source="state", state_field="bear_report", producer_hint="bear_researcher_v2"),
            AgentInput(name="risk_debate_state", type="dict", description="debate status", required=False, source="state", state_field="risk_debate_state", producer_hint="risk_manager_v2"),
            AgentInput(name="market_report", type="string", description="Market analysis report", required=False, source="state", state_field="market_report", producer_hint="market_analyst_v2"),
            AgentInput(name="fundamentals_report", type="string", description="Fundamental Analysis Report", required=False, source="state", state_field="fundamentals_report", producer_hint="fundamentals_analyst_v2"),
            AgentInput(name="news_report", type="string", description="News analysis report", required=False, source="state", state_field="news_report", producer_hint="news_analyst_v2"),
            AgentInput(name="sentiment_report", type="string", description="Sentiment Analysis Report", required=False, source="state", state_field="sentiment_report", producer_hint="social_analyst_v2"),
            AgentInput(name="index_report", type="string", description="Market analysis report", required=False, source="state", state_field="index_report", producer_hint="index_analyst_v2"),
            AgentInput(name="sector_report", type="string", description="Sector analysis report", required=False, source="state", state_field="sector_report", producer_hint="sector_analyst_v2"),
        ],
        outputs=[
            AgentOutput(name="safe_opinion", type="string", description="defensive situational view"),
            AgentOutput(name="risk_debate_state", type="dict", description="Updated debate status"),
        ],
        requires_tools=False,
        output_field="safe_opinion",
        report_label=" [Defense Scenario Study]",
        workflow_stage="risk",
        growth_role="reviewer",
        growth_outputs=["safe_opinion"],
        memory_scope_hint="pattern",
        review_level="manual_required",
        growth_source_type="manager_decision",
        maturity_level="stable",
        input_mode="upstream-dependent",
        debug_replay_mode="requires_chain_prefill",
        callable_surfaces=["assistant", "workflow", "agent"],
    )

    # research stance (used by risk analysts "safe") 
    stance = "safe"

    # Output field name
    output_field = "safe_opinion"

    # 🆕 Debate history field (for multi-round debates)
    history_field = "safe_history"
    opponent_history_fields = ["risky_history", "neutral_history"]
    
    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words

        Args:
            state: Workflow status (optional, used to extract variables such as company_name, ticker etc.)

        Returns:
            System prompt word
        """
        # Risk analysts do not need template variables (do not rely on stock information)
        # Use the base class's general method to obtain prompt words from the template system (refer to research_manager_v2)
        logger.info("🔍 [SafeAnalystV2] Start building system prompt words")
        
        prompt = self._get_prompt_from_template(
            agent_type="debators_v2",
            agent_name="safe_analyst_v2",
            variables={},  # System prompt words do not require variables (refer to research_manager_v2)
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if state else None,  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        
        logger.info(f"📝 System prompt word length: {len(prompt)} character")
        if prompt:
            logger.debug("✅ Obtain defense scenario analyst system prompt words from the template system")
            return prompt

        # Downgrade: Use default prompt word
        return """You are a defensive scenario analyst.

Your character features:
    - 🛡️ Be robust and conservative and prioritize identifying the vulnerabilities of research conclusions.
    - 🔒 It is better to miss the opportunity than to accept the strengthening of the conclusion with unclear premises or insufficient evidence.
    - 📉 Pay attention to potential risk sources, failure conditions and downside scenarios
    - ⚠️ Emphasize issues that need clarification first rather than giving direct implementation suggestions

Your task is:
    1. Review the weaknesses of current research conclusions from a conservative perspective.
    2. Identify key risk sources, failure conditions and information gaps.
    3. Explain which negative signals would cause the current judgment to be revised downward.
    4. No positions, stops, price ranges or trading recommendations are output.

Assessment points:
    - The most fragile premise for research conclusions
    - Key risk sources and potential impacts
    - Negative public signals that need to be monitored carefully
    - Information gaps not covered by current materials

Requirements:
    - Be conservative but objective
    - Support your opinion with data
    - Write reports in Chinese"""

    def _build_user_prompt(self, ticker: str, analysis_date: str, state: Dict[str, Any]) -> str:
        """Construct user prompt words (obtained from template system and rendered)"""
        # 🆕 Get debate status
        risk_debate_state = state.get("risk_debate_state", {})
        history = risk_debate_state.get("history", "")
        current_risky_response = risk_debate_state.get("current_risky_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        # Prepare template variables (extract all data from state)
        template_variables = {
            "ticker": ticker,
            "analysis_date": analysis_date,
            "investment_plan": state.get("investment_plan", "") or state.get("trader_investment_plan", ""),
            "bull_opinion": state.get("bull_opinion", ""),
            "bear_opinion": state.get("bear_opinion", ""),
            "market_report": state.get("market_report", ""),
            "fundamentals_report": state.get("fundamentals_report", ""),
            "news_report": state.get("news_report", ""),
            "sentiment_report": state.get("sentiment_report", ""),
            "index_report": state.get("index_report", ""),
            "sector_report": state.get("sector_report", ""),
            # 🆕 debate related variables
            "history": history,
            "current_risky_response": current_risky_response,
            "current_neutral_response": current_neutral_response,
        }

        # 📊 Record input data length
        logger.info(f"📊 [Safe Analyst] Input data length statistics:")
        logger.info(f"  - market_report: {len(template_variables['market_report']):,} character")
        logger.info(f"  - sentiment_report: {len(template_variables['sentiment_report']):,} character")
        logger.info(f"  - news_report: {len(template_variables['news_report']):,} character")
        logger.info(f"  - fundamentals_report: {len(template_variables['fundamentals_report']):,} character")
        logger.info(f"  - investment_plan: {len(template_variables['investment_plan']):,} character")
        logger.info(f"  - history: {len(history):,} character")
        total_length = (len(template_variables['market_report']) + len(template_variables['sentiment_report']) +
                       len(template_variables['news_report']) + len(template_variables['fundamentals_report']) +
                       len(template_variables['investment_plan']) + len(history) +
                       len(current_risky_response) + len(current_neutral_response))
        logger.info(f"  - Total prompt length: {total_length:,} character (~{total_length//4:,} tokens)")

        # Downgrade prompt word (if template system is not available)
        fallback_prompt = f"""Please review the following comprehensive research findings from the perspective of a defense scenario analyst and describe the risks that would lead to downward revisions:

     [Comprehensive research conclusion]
    {template_variables['investment_plan'] or 'No comprehensive research conclusion'}

     [Optimistic Scenario View]
    {template_variables['bull_opinion'] or 'No optimistic scenario view'}

     [Prudent Scenario Perspective]
    {template_variables['bear_opinion'] or 'no prudence scenario view'}

     [Market analysis report]
    {template_variables['market_report'] or 'No market analysis report'}

     [Social Media Sentiment Report]
    {template_variables['sentiment_report'] or 'No sentiment analysis report'}

     [News analysis report]
    {template_variables['news_report'] or 'No news analysis report'}

     [Fundamental analysis report]
    {template_variables['fundamentals_report'] or 'No fundamental analysis report'}

     [Current Debate History]
    {history or 'No debate history'}

     [Latest response from highly elastic scenario analysts] 
    {current_risky_response or 'None'}

     [Latest response from base case analysts]
    {current_neutral_response or 'None'}

    Please output your view of the defense scenario, focusing on:
    1. What is the weakest premise for the conclusions of the current study.
    2. What negative signals will cause the current judgment to be revised downwards.
    3. What key information or verification is missing?
    4. Do not output positions, stops, price ranges, or trading recommendations."""

        # Print template variables (for debugging)
        logger.info(f"📊 [Defense Scenario Analyst] Template variables:")
        for key, value in template_variables.items():
            if isinstance(value, str) and len(value) > 100:
                logger.info(f"  - {key}: {value[:100]}...")
            else:
                logger.info(f"  - {key}: {value}")

        # Use the general method of the base class to obtain the user prompt word (preference_id will be extracted from context/state)
        prompt = self._get_prompt_from_template(
            agent_type="debators_v2",
            agent_name="safe_analyst_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if isinstance(state, dict) else state,  # Get from state context
            fallback_prompt=fallback_prompt,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        if prompt:
            logger.info(f"✅ Get defense scenario analyst user prompt words from template system (length: {len(prompt)})")
            return prompt

        # Downgrade: Use hardcoded prompt words
        logger.info(f"📝 [Defense Scenario Analyst] Use demotion prompts (length: {len(fallback_prompt)})")
        return fallback_prompt

    def _get_required_reports(self) -> list:
        """
        Get a list of required reports

        Returns:
            Report field name list
        """
        return [
            # Required reports
            "investment_plan",
            "bull_opinion",
            "bear_opinion",
            # 🆕 Optional analysis report (provides more context)
            "market_report",
            "fundamentals_report",
            "news_report",
            "sentiment_report",
            "index_report",
            "sector_report",
        ]
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform conservative risk review (supports multiple rounds of debate)

        Args:
            state: A status dictionary containing the following keys:
                - ticker: Stock code
                - analysis_date: Analysis date
                - investment_plan: Comprehensive research conclusion
                - bull_opinion: Optimistic Scenario View (optional)
                - bear_opinion: Prudential scenario perspective (optional)
                - risk_debate_state: Debate status (optional)

        Returns:
            The updated status includes:
                - safe_opinion: defensive situational view
                - risk_debate_state: Updated debate status
        """
        ticker = state.get("ticker", "") or state.get("company_of_interest", "")
        analysis_date = state.get("analysis_date", "") or state.get("trade_date", "")

        logger.info(f"🛡️ Defense scenario analysts begin assessment {ticker} @ {analysis_date}")

        # 🆕 Get debate status
        risk_debate_state = state.get("risk_debate_state", {})
        history = risk_debate_state.get("history", "")
        safe_history = risk_debate_state.get("safe_history", "")

        try:
            # Build prompt words
            system_prompt = self._build_system_prompt(state)
            user_prompt = self._build_user_prompt(ticker, analysis_date, state)

            # call LLM
            system_prompt = self._apply_global_trading_advice_guard(system_prompt)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            logger.info(f"System prompt word: {system_prompt}")
            logger.info(f"User prompt words: {user_prompt}")

            logger.info(f"⏱️ [Safe Analyst] Start calling LLM...")
            import time
            llm_start_time = time.time()

            if self._llm:
                response = self._invoke_llm_with_trace(messages)
                opinion = response.content
            else:
                raise ValueError("LLM not initialized")

            llm_elapsed = time.time() - llm_start_time
            logger.info(f"⏱️ [Safe Analyst] LLM The call is completed and takes time: {llm_elapsed:.2f}seconds")

            # 🆕 Formatting arguments (refer to the old version)
            argument = f"Safe Analyst: {opinion}"

            # 🆕 Update debate status
            new_count = risk_debate_state.get("count", 0) + 1
            logger.info(f"🛡️ [Defense Scenario Analyst] Finished speaking, counting: {risk_debate_state.get('count', 0)} -> {new_count}")

            new_risk_debate_state = {
                "history": history + "\n" + argument,
                "risky_history": risk_debate_state.get("risky_history", ""),
                "safe_history": safe_history + "\n" + argument,
                "neutral_history": risk_debate_state.get("neutral_history", ""),
                "latest_speaker": "Safe",
                "current_risky_response": risk_debate_state.get("current_risky_response", ""),
                "current_safe_response": argument,
                "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
                "count": new_count,
            }

            logger.info(f"✅ Conservative risk analysis completed")

            # Return the newly added fields and updated debate status
            return {
                "safe_opinion": opinion,
                "risk_debate_state": new_risk_debate_state
            }

        except Exception as e:
            logger.error(f"❌ Conservative risk analysis failed: {e}", exc_info=True)
            return {
                "safe_opinion": f"Conservative risk analysis failed: {str(e)}",
                "risk_debate_state": risk_debate_state  # Keep it as it is
            }

