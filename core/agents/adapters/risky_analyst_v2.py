"""
Highly Resilient Scenario Analyst v2.0

A highly resilient scenario analyst implementation based on the ResearcherAgent base class.
Review comprehensive research conclusions from a radical perspective, paying attention to conditions for upward revision of conclusions and strengthening catalysis.
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
class RiskyAnalystV2(ResearcherAgent):
    """
    Highly Resilient Scenario Analyst v2.0

    Function:
    - Review comprehensive research conclusions from a radical perspective
    - Pay attention to the conditions for upward revision of conclusions and strengthen catalysis
    - Tolerate high uncertainty but require clear premises
    - Identify additional validations needed to enhance conclusions
    - Supports multiple rounds of debate (with conservative and neutral analysts)
    - Supports caching system (avoids repeated analysis)

    Workflow:
    1. Read comprehensive research conclusions and market analysis
    2. Read debate history and opponents views
    3. Use LLM to review conclusion revision conditions from a radical perspective and refute opponents
    4. Generate highly resilient situational perspectives
    5. Update debate status

    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("risky_analyst_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15",
            "investment_plan": "...",
            "bull_opinion": "...",
            "bear_opinion": "...",
            "risk_debate_state": {
                "history": "...",
                "risky_history": "...",
                "current_safe_response": "...",
                "current_neutral_response": "...",
                "count": 0
            }
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="risky_analyst_v2",
        name="Highly Resilient Scenario Analyst v2.0",
        description="Review the research conclusions from the perspective of whether they can be revised upward, and identify strengthened catalysts, high-requirement prerequisites and additional verification signals",
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
            AgentOutput(name="risky_opinion", type="string", description="Highly resilient scenario perspective"),
            AgentOutput(name="risk_debate_state", type="dict", description="Updated debate status"),
        ],
        requires_tools=False,
        output_field="risky_opinion",
        report_label=" [Highly elastic scenario research]",
        workflow_stage="risk",
        growth_role="reviewer",
        growth_outputs=["risky_opinion"],
        memory_scope_hint="pattern",
        review_level="manual_required",
        growth_source_type="manager_decision",
        maturity_level="stable",
        input_mode="upstream-dependent",
        debug_replay_mode="requires_chain_prefill",
        callable_surfaces=["assistant", "workflow", "agent"],
    )

    # research stance (used by risk analysts "risky") 
    stance = "risky"

    # Output field name
    output_field = "risky_opinion"

    # 🆕 Debate history field (for multi-round debates)
    history_field = "risky_history"
    opponent_history_fields = ["safe_history", "neutral_history"]
    
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
        logger.info("🔍 [RiskyAnalystV2] Start building system prompt words")
        
        prompt = self._get_prompt_from_template(
            agent_type="debators_v2",
            agent_name="risky_analyst_v2",
            variables={},  # System prompt words do not require variables (refer to research_manager_v2)
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if state else None,  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        
        logger.info(f"📝 System prompt word length: {len(prompt)} character")
        if prompt:
            logger.debug("✅ Obtain highly elastic scenario analyst system prompt words from the template system")
            return prompt

        # Downgrade: Use default prompt word
        return """You are a high-resilience scenario analyst.

Your character features:
    - 🔥 Pay more attention to the strengthening conditions and catalysts on which the upward revision of research conclusions depends.
    - 💰 Accept higher uncertainty, but must explain the premise and evidence threshold
    - 🚀 Which public signals should be taken seriously to make current conclusions more positive?
    - ⚡ Emphasis on external validation needed to strengthen conclusions

Your task is:
    1. A radical review of the conditions for upward revision of current research conclusions.
    2. Describe what catalytic, confirming signals, and market feedback would enhance current conclusions.
    3. Point out what high-level prerequisites need to be met in order to be more active.
    4. Does not output positions, target prices, profit margins or trading recommendations.

Assessment points:
    - Catalysis and evidence for upward revision of conclusions
    - The parts of the current material that most support the optimistic scenario
    - Are there triggers for repricing in the market?
    - Verification information that still needs to be completed

Requirements:
    - Be radical but rational
    - Support your opinion with data
    - Write reports in Chinese"""

    def _build_user_prompt(self, ticker: str, analysis_date: str, state: Dict[str, Any]) -> str:
        """Construct user prompt words (obtained from template system and rendered)"""
        # 🆕 Get debate status
        risk_debate_state = state.get("risk_debate_state", {})
        history = risk_debate_state.get("history", "")
        current_safe_response = risk_debate_state.get("current_safe_response", "")
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
            "current_safe_response": current_safe_response,
            "current_neutral_response": current_neutral_response,
        }

        # 📊 Record input data length
        logger.info(f"📊 [Risky Analyst] Input data length statistics:")
        logger.info(f"  - market_report: {len(template_variables['market_report']):,} character")
        logger.info(f"  - sentiment_report: {len(template_variables['sentiment_report']):,} character")
        logger.info(f"  - news_report: {len(template_variables['news_report']):,} character")
        logger.info(f"  - fundamentals_report: {len(template_variables['fundamentals_report']):,} character")
        logger.info(f"  - investment_plan: {len(template_variables['investment_plan']):,} character")
        logger.info(f"  - history: {len(history):,} character")
        total_length = (len(template_variables['market_report']) + len(template_variables['sentiment_report']) +
                       len(template_variables['news_report']) + len(template_variables['fundamentals_report']) +
                       len(template_variables['investment_plan']) + len(history) +
                       len(current_safe_response) + len(current_neutral_response))
        logger.info(f"  - Total prompt length: {total_length:,} character (~{total_length//4:,} tokens)")

        # Downgrade prompt word (if template system is not available)
        fallback_prompt = f"""Please review the following comprehensive research conclusions from the perspective of a high-resilience scenario analyst and explain what conditions would support an upward revision of the conclusions:

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

     [Latest response from defense scenario analysts]
    {current_safe_response or 'None'}

     [Latest response from base case analysts]
    {current_neutral_response or 'None'}

    Please output your highly elastic scenario view, focusing on:
    1. What catalytic, validating signals or market feedback would enhance current conclusions.
    2. What are the high requirements that need to be met if you want to be more active.
    3. What is the evidence in the current material that most supports the upward revision of the conclusion?
    4. Do not output positions, target prices, profit margins or trading recommendations."""

        # Print template variables (for debugging)
        logger.info(f"📊 [Highly Resilient Scenario Analyst] Template variables:")
        for key, value in template_variables.items():
            if isinstance(value, str) and len(value) > 100:
                logger.info(f"  - {key}: {value[:100]}...")
            else:
                logger.info(f"  - {key}: {value}")

        # Use the general method of the base class to obtain the user prompt word (preference_id will be extracted from context/state)
        prompt = self._get_prompt_from_template(
            agent_type="debators_v2",
            agent_name="risky_analyst_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if isinstance(state, dict) else state,  # Get from state context
            fallback_prompt=fallback_prompt,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        if prompt:
            logger.info(f"✅ Obtain highly elastic scenario analyst user prompt words from the template system (length: {len(prompt)})")
            return prompt

        # Downgrade: Use hardcoded prompt words
        logger.info(f"📝 [Highly Resilient Scenario Analyst] Use demotion prompts (length: {len(fallback_prompt)})")
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
        Perform aggressive risk reviews (supports multiple rounds of debate)

        Args:
            state: A status dictionary containing the following keys:
                - ticker: Stock code
                - analysis_date: Analysis date
                - investment_plan: Comprehensive research conclusion
                - bull_opinion: Optimistic Scenario View (optional)
                - bear_opinion: Prudential scenario perspective (optional)
                - risk_debate_state: Debate status (optional)
                    - history: Full debate history
                    - risky_history: Highly Resilient Scenario Fellows History
                    - safe_history: Defense Scenario Fellows History
                    - neutral_history: Baseline Scenario Researcher History
                    - current_safe_response: Latest response from Defense Scenario Researchers
                    - current_neutral_response: Latest responses from neutral analysts
                    - count: Debate round count

        Returns:
            The updated status includes:
                - risky_opinion: Highly resilient scenario perspective
                - risk_debate_state: Updated debate status
        """
        ticker = state.get("ticker", "") or state.get("company_of_interest", "")
        analysis_date = state.get("analysis_date", "") or state.get("trade_date", "")

        logger.info(f"🔥 High-resilience scenario analysts begin their assessment {ticker} @ {analysis_date}")

        # 🆕 Get debate status
        risk_debate_state = state.get("risk_debate_state", {})
        history = risk_debate_state.get("history", "")
        risky_history = risk_debate_state.get("risky_history", "")

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

            logger.info(f"⏱️ [Risky Analyst] Start calling LLM...")
            import time
            llm_start_time = time.time()

            if self._llm:
                response = self._invoke_llm_with_trace(messages)
                opinion = response.content
            else:
                raise ValueError("LLM not initialized")

            llm_elapsed = time.time() - llm_start_time
            logger.info(f"⏱️ [Risky Analyst] LLM The call is completed and takes time: {llm_elapsed:.2f}seconds")

            # 🆕 Formatting arguments (refer to the old version)
            argument = f"Risky Analyst: {opinion}"

            # 🆕 Update debate status
            new_count = risk_debate_state.get("count", 0) + 1
            logger.info(f"🔥 [Highly Resilient Scenario Analyst] Finished speaking, counting: {risk_debate_state.get('count', 0)} -> {new_count}")

            new_risk_debate_state = {
                "history": history + "\n" + argument,
                "risky_history": risky_history + "\n" + argument,
                "safe_history": risk_debate_state.get("safe_history", ""),
                "neutral_history": risk_debate_state.get("neutral_history", ""),
                "latest_speaker": "Risky",
                "current_risky_response": argument,
                "current_safe_response": risk_debate_state.get("current_safe_response", ""),
                "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
                "count": new_count,
            }

            logger.info(f"✅ Aggressive risk analysis completed")

            # Return the newly added fields and updated debate status
            return {
                "risky_opinion": opinion,
                "risk_debate_state": new_risk_debate_state
            }

        except Exception as e:
            logger.error(f"❌ Aggressive risk analysis fails: {e}", exc_info=True)
            return {
                "risky_opinion": f"Aggressive risk analysis fails: {str(e)}",
                "risk_debate_state": risk_debate_state  # Keep it as it is
            }

