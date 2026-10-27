"""
Prudential Scenario Researcher v2.0

Prudent scenario researcher implemented based on ResearcherAgent base class
"""

import logging
from typing import Dict, Any, List

from core.agents.researcher import ResearcherAgent
from core.agents.config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from core.agents.registry import register_agent

logger = logging.getLogger(__name__)

# Try importing the template system
try:
    from tradingagents.utils.template_client import get_agent_prompt, get_user_prompt
except (ImportError, KeyError) as e:
    logger.warning(f"Unable to import template system: {e}")
    get_agent_prompt = None
    get_user_prompt = None

# Try importing stock tools
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    logger.warning("Unable to import StockUtils, some functions may not be available")
    StockUtils = None


@register_agent
class BearResearcherV2(ResearcherAgent):
    """
    Prudential Scenario Researcher v2.0
    
    Function:
    - Comprehensive analysis of multiple reports from a prudential scenario perspective
    - Refining risk factors, vulnerabilities and judgment boundaries
    - Generate prudent scenario research reports
    
    Workflow:
    1. Read market reports, news reports, fundamental reports, etc.
    2. Comprehensive analysis from a prudent scenario perspective
    3. Generate prudent scenario research reports
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("bear_researcher_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15",
            "market_report": "...",
            "news_report": "...",
            "fundamentals_report": "..."
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="bear_researcher_v2",
        name="Prudential Scenario Researcher v2.0",
        description="Construct a prudent research argument based on existing materials and refine risks, vulnerabilities and boundaries of judgment.",
        category=AgentCategory.RESEARCHER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],  # Researchers don't need tools
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="market_report", type="string", description="Market analysis report", required=False, source="state", state_field="market_report", producer_hint="market_analyst_v2"),
            AgentInput(name="news_report", type="string", description="News analysis report", required=False, source="state", state_field="news_report", producer_hint="news_analyst_v2"),
            AgentInput(name="fundamentals_report", type="string", description="Fundamental Analysis Report", required=False, source="state", state_field="fundamentals_report", producer_hint="fundamentals_analyst_v2"),
        ],
        outputs=[
            AgentOutput(name="bear_report", type="string", description="Prudential Scenario Research Report"),
        ],
        requires_tools=False,
        output_field="bear_report",
        report_label=" [Prudential Scenario Study v2]",
        workflow_stage="research",
        growth_role="reviewer",
        growth_outputs=["bear_report"],
        memory_scope_hint="pattern",
        review_level="manual_required",
        growth_source_type="analysis_report",
        maturity_level="stable",
        input_mode="upstream-dependent",
        debug_replay_mode="requires_chain_prefill",
        callable_surfaces=["assistant", "workflow", "agent"],
    )

    # Researcher type
    researcher_type = "bear"

    # stance
    stance = "bear"

    # Output field name
    output_field = "bear_report"

    # debate configuration
    debate_state_field = "investment_debate_state"
    history_field = "bear_history"
    opponent_history_field = "bull_history"

    def _build_system_prompt(self, stance: str, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words
        
        Args:
            stance: Standpoint (bull/bear)
            state: Workflow status (optional, used to extract variables such as company_name, ticker etc.)
            
        Returns:
            System prompt word
        """
        # Use the base class's general method to obtain prompt words from the template system (refer to research_manager_v2)
        logger.info("🔍 [BearResearcherV2] Start building system prompt words")
        
        # Extract the necessary variables from state (if required by the system prompt word template)
        template_variables = {}
        if state:
            # Extract ticker and company_name
            if "ticker" in state:
                template_variables["ticker"] = state["ticker"]
            if "company_name" in state:
                template_variables["company_name"] = state["company_name"]
            # Extraction date
            if "analysis_date" in state or "trade_date" in state:
                analysis_date = state.get("analysis_date") or state.get("trade_date")
                if analysis_date:
                    # Make sure the date is in the correct format
                    if isinstance(analysis_date, str) and len(analysis_date) > 10:
                        analysis_date = analysis_date.split()[0]
                    template_variables["current_date"] = analysis_date
                    template_variables["analysis_date"] = analysis_date
        
        prompt = self._get_prompt_from_template(
            agent_type="researchers_v2",
            agent_name="bear_researcher_v2",
            variables=template_variables,  # Pass necessary variables
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables (current_price, industry etc.)
            context=state.get("context") if state else None,  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        if prompt:
            logger.info(f"✅ Get Prudent Scenario Researcher Prompt Words from Template System (length: {len(prompt)})")
            return prompt
        
        # Downgrade: Use the default prompt word that is semantically consistent with the current template
        company_name = (state or {}).get("company_name") or (state or {}).get("ticker") or "target company"
        ticker = (state or {}).get("ticker") or ""
        market_name = (state or {}).get("market_name") or "current market"
        currency_name = (state or {}).get("currency_name") or "Report original currency"
        currency_symbol = (state or {}).get("currency_symbol") or ""
        company_reference = f"{company_name} (Stock code:{ticker}) " if ticker else company_name
        currency_display = f"{currency_name}（{currency_symbol}）" if currency_symbol else currency_name

        return f"""You are a deliberative scenario researcher responsible for creating {company_reference} Construct cautious research arguments.

    ⚠️ Current Analytical Markets:{market_name}. If the material contains prices, valuations or financial values, please use them uniformly {currency_display} as a unit.
    ⚠️ Please use the company name first when writing. {company_name} , Don t just use ticker symbols {ticker} Refers to the company.

    Your task is:
    1. Describe what evidence weakens the current judgment or supports a more cautious conclusion.
    2. Highlight risks and challenges, competitive disadvantages and negative indicators, but only if they are supported by the material.
    3. Respond to the most critical arguments in the optimistic view, pointing out the shortcomings in the evidence, loopholes in the premise, or unverified aspects.
    4. Combining the history of debates and past reflections, it explains which judgments are prone to distortion and how the boundaries of conclusions should be narrowed currently.
    5. Use language that ordinary users can understand and don t be pretentious.

    Strictly prohibited:
    - Buying and selling, adding or subtracting positions, allocation values, target prices, price ranges, and key prices are not allowed.
    - The downside space, maximum retracement, probability value, and risk-benefit ratio are not allowed to be output.
    - Prudent scenarios must not be written as execution plans.
    - Do not use internal model knowledge, training data, or information outside the material to supplement unprovided content.
    """

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        reports: Dict[str, str],
        historical_context: str,
        state: Dict[str, Any]
    ) -> str:
        """
        Construct user prompt words (obtained from template system)

        Args:
            ticker: Stock code
            analysis_date: Analysis date
            reports: Various analysis reports
            historical_context: historical context
            state: Current status

        Returns:
            User prompt words
        """
        company_name = self._get_company_name(ticker, state)

        # Prepare template variables
        template_variables = {
            "ticker": ticker,
            "company_name": company_name,
            "analysis_date": analysis_date,
        }

        # Add all reports to template variables
        for key, value in reports.items():
            template_variables[key] = str(value) if value else ""

        # Add historical context
        if historical_context:
            template_variables["historical_context"] = historical_context

        # 🔑 Extract system variables from state and merge into template_variables
        if state:
            system_vars = [
                "current_price", "industry", "market_name",
                "currency_name", "currency_symbol", "current_date", "start_date"
            ]
            for var in system_vars:
                if var in state and var not in template_variables:
                    template_variables[var] = state[var]
                    logger.debug(f"📊 [system variables] merge into template variable {var}: {state[var]}")
            
            # Also adds other state fields that may be useful if not present in template_variables
            # but exclude some internal fields
            exclude_fields = {"context", "messages", "prompt_overrides", "skip_cache"}
            for key, value in state.items():
                if key not in template_variables and key not in exclude_fields:
                    # Add only simple types (strings, numbers, booleans), avoid complex objects
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        template_variables[key] = value

        # Use the general method of the base class to obtain user prompt words from the template system (uniformly use _get_prompt_from_template)
        prompt = self._get_prompt_from_template(
            agent_type="researchers_v2",
            agent_name="bear_researcher_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables (as a backup)
            context=state.get("context") if state else None,  # Get from state context
            fallback_prompt=None,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        
        if prompt:
            logger.info(f"✅ Obtain Prudential Scenario Researcher user prompt words from the template system (length: {len(prompt)})")
            return prompt
        
        # Downgrade: use the old way if the template system is not available
        if get_user_prompt:
            try:
                preference_id = state.get("preference_id", "neutral") if state else "neutral"

                prompt = get_user_prompt(
                    agent_type="researchers_v2",
                    agent_name="bear_researcher_v2",
                    variables=template_variables,
                    preference_id=preference_id,
                    fallback_prompt=None,
                    context=state
                )

                if prompt:
                    logger.info(f"✅ Obtain Prudential Scenario Researcher user prompt words from the template system (length: {len(prompt)})")
                    return prompt
            except Exception as e:
                logger.warning(f"⚠️ Failed to obtain user prompt words from template system: {e}, Use demotion prompts")

        # Downgrade: Use hard-coded prompt words that are semantically consistent with the current template
        market_name = state.get("market_name", "current market") if state else "current market"
        currency_name = state.get("currency_name", "Report original currency") if state else "Report original currency"
        currency_symbol = state.get("currency_symbol", "") if state else ""
        currency_display = f"{currency_name}（{currency_symbol}）" if currency_symbol else currency_name

        prompt = """Based on the analysis report provided, please provide {company_name} (Stock code:{ticker}) Construct cautious research arguments.

    Current Analytical Markets:{market_name}
    If the material contains prices, valuations or financial values, please use them uniformly. {currency_display} as a unit.
    Please use the company name first when writing. {company_name} , Don t just use ticker symbols {ticker} Refers to the company.

    Available resources:
    - All analyst reports (including market/fundamentals/news/sentiment/market/sector, etc.):
    {analyst_reports}
    - Debate dialogue history:{historical_context}
    - The latest optimistic argument:{current_response}
    - Reflections and lessons learned from similar situations:{past_memory_str}

    Please use Markdown for output, and preferably include the following headers:
    ## core proposition
    ## main concerns
    ## response to optimistic views
    ## Judgment of weakening condition

    Requirements:
    - If there are new and verifiable public signals in this round, please add ## Follow-up observation signals ; If there are no new observation signals in this round, you can omit the title, or state it directly There are no new observation signals in this round. . 
    - Each key argument must be marked with a source [ ] at the end of the sentence.
    - If a piece of data is missing from the report, it must be written clearly This data is not provided in the report or Unable to determine based on existing reports... . 
    - Respond directly to optimistic arguments, don t just repeat your own point of view.
    - If the historical reflection is relevant to the current case, absorb the lessons learned; if it is not relevant, do not apply it rigidly.
    - When conducting multiple rounds of multi-scenario research, give priority to outputting the 1-2 points that are new in this round or are most worthy of response; if the new evidence is limited, you can clearly write The core judgment continues, and there is no new high-quality risk evidence or premise revision. , Don t repeat extensions to make up the structure.
    - Only analysis dates can be used {analysis_date} Do not cite information that was previously provided and is explicitly provided in the material. last year  last quarter or temporal information in model memory.
    - It is strictly prohibited to output target prices, price ranges, key price points, downside space, probability values and any trading suggestions.
    - It is strictly prohibited to use internal model knowledge, training data or information outside the material to supplement unprovided content.
    """

        # Aggregate all analyst reports
        try:
            from core.workflow.stage_aggregator import aggregate_stage_reports
            analyst_reports_text = aggregate_stage_reports(state or {}, "analyst")
        except Exception:
            analyst_reports_text = ""

        # Substitute variables (using aggregate reporting + Keep individual fields compatible)
        prompt = prompt.format(
            company_name=company_name,
            ticker=ticker,
            market_name=market_name,
            currency_display=currency_display,
            analysis_date=analysis_date,
            analyst_reports=analyst_reports_text or "\n".join([
                f"- Market research report:{reports.get('market_report', '')}",
                f"- Social Media Sentiment Report:{reports.get('sentiment_report', '')}",
                f"- Latest world affairs news:{reports.get('news_report', '')}",
                f"- Company fundamentals report:{reports.get('fundamentals_report', '')}",
            ]),
            historical_context=historical_context or (state.get("history", "") if state else ""),
            current_response=state.get("current_response", "") if state else "",
            past_memory_str=state.get("past_memory_str", "") if state else ""
        )

        return prompt

    def _get_required_reports(self) -> List[str]:
        """
        Get a list of required reports
        
        Returns:
            Report field name list
        """
        return [
            "market_report",        # Market analysis report
            "news_report",          # News analysis report
            "fundamentals_report",  # Fundamental Analysis Report
            "sentiment_report",     # Social media analysis report (market sentiment)
            "sector_report",        # Sector Analysis Report (Industry Analysis)
            "index_report",         # Market analysis report
        ]

    def _get_company_name(self, ticker: str, state: Dict[str, Any]) -> str:
        """Get company name"""
        # Get it from state first
        if "company_name" in state:
            return state["company_name"]
        
        # Get using StockUtils
        if StockUtils:
            try:
                market_info = StockUtils.get_market_info(ticker)
                if market_info.get('is_china'):
                    from tradingagents.dataflows.interface import get_china_stock_info_unified
                    stock_info = get_china_stock_info_unified(ticker)
                    if "Stock name:" in stock_info:
                        return stock_info.split("Stock name:")[1].split("\n")[0].strip()
            except Exception as e:
                logger.debug(f"Failed to get company name: {e}")
        
        return f"stocks{ticker}"

