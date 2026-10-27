"""
Optimistic Scenario Researcher v2.0

Optimistic scenario researcher implemented based on ResearcherAgent base class
Comprehensive analysis of multiple reports from an optimistic scenario perspective
"""

import logging
from typing import Any, Dict, List, Optional

from ..researcher import ResearcherAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)

# Try importing utility functions
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    logger.warning("Unable to import StockUtils, some functions may not be available")
    StockUtils = None

try:
    from tradingagents.utils.template_client import get_agent_prompt, get_user_prompt
except (ImportError, KeyError):
    logger.warning("Unable to import template system function, default prompt word will be used")
    get_agent_prompt = None
    get_user_prompt = None

# It is no longer necessary to import get_agent_prompt directly, use the _get_prompt_from_template method of the base class


@register_agent
class BullResearcherV2(ResearcherAgent):
    """
    Optimistic Scenario Researcher v2.0
    
    Function:
    - Comprehensive analysis of multiple reports from an optimistic scenario perspective
    - Refining the premise, evidence chain and potential catalyst
    - Generate optimistic scenario research reports
    
    Workflow:
    1. Read market reports, news reports, fundamental reports, etc.
    2. Comprehensive analysis from an optimistic scenario perspective
    3. Generate optimistic scenario research reports
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("bull_researcher_v2", llm)

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
        id="bull_researcher_v2",
        name="Optimistic Scenario Researcher v2.0",
        description="Construct an optimistic but restrained research argument based on existing materials, and refine the premise, evidence chain and observation signals",
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
            AgentOutput(name="bull_report", type="string", description="Optimistic Scenario Research Report"),
        ],
        requires_tools=False,
        output_field="bull_report",
        report_label=" [Optimistic Scenario Study v2]",
        workflow_stage="research",
        growth_role="reviewer",
        growth_outputs=["bull_report"],
        memory_scope_hint="pattern",
        review_level="manual_required",
        growth_source_type="analysis_report",
        maturity_level="stable",
        input_mode="upstream-dependent",
        debug_replay_mode="requires_chain_prefill",
        callable_surfaces=["assistant", "workflow", "agent"],
    )
    
    # Researcher type
    researcher_type = "bull"

    # Output field name
    output_field = "bull_report"

    # research stance
    stance = "bull"

    # debate configuration
    debate_state_field = "investment_debate_state"
    history_field = "bull_history"
    opponent_history_field = "bear_history"
    
    def _build_system_prompt(self, stance: str, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words
        
        Args:
            stance: Research stance (bull)
            state: Workflow status (optional, used to extract variables such as company_name, ticker etc.)
            
        Returns:
            System prompt word
        """
        # Use the base class's general method to obtain prompt words from the template system (refer to research_manager_v2)
        logger.info("🔍 [BullResearcherV2] Start building system prompt words")
        
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
            agent_name="bull_researcher_v2",
            variables=template_variables,  # Pass necessary variables
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables (current_price, industry etc.)
            context=state.get("context") if state else None,  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        if prompt:
            logger.debug("✅ Get the optimistic scenario researcher system prompt word from the template system")
            return prompt
        
        # Downgrade: Use the old version of the default prompt word (consistent with the database template)
        return """You are an optimistic scenario researcher, responsible for constructing optimistic but restrained research arguments based on available material.

    Your task is:
    1. Describe what evidence supports a more positive research judgment.
    2. Respond to the most critical arguments from opposing viewpoints rather than avoiding the issue.
    3. It points out the premise for the establishment of the optimistic scenario, the most vulnerable link and a public signal to continue observation.
    4. Output in language that ordinary users can understand, without overlapping terminology.

    Strictly prohibited:
    - Buying and selling, adding or subtracting positions, allocation values, reverse investment opportunities, target prices, price ranges, and key price points are not allowed.
    - The profit space, retracement range, probability value, and risk-benefit ratio are not allowed to be output.
    - Optimistic scenarios must not be written as execution plans.
    """
    
    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        reports: Dict[str, Any],
        historical_context: Optional[str],
        state: Dict[str, Any]
    ) -> str:
        """
        Construct user prompt words (obtained from template system)

        Args:
            ticker: Stock code
            analysis_date: Analysis date
            reports: Collected report dictionary
            historical_context: historical context
            state: Workflow status

        Returns:
            User prompt words
        """
        # Get company name
        if StockUtils:
            market_info = StockUtils.get_market_info(ticker)
            company_name = self._get_company_name(ticker, market_info)
        else:
            company_name = ticker

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
            agent_name="bull_researcher_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables (as a backup)
            context=state.get("context") if state else None,  # Get from state context
            fallback_prompt=None,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        
        if prompt:
            logger.info(f"✅ Obtain optimistic scenario researcher user prompt words from template system (length: {len(prompt)})")
            return prompt
        
        # Downgrade: use the old way if the template system is not available
        if get_user_prompt:
            try:
                preference_id = state.get("preference_id", "neutral") if state else "neutral"

                prompt = get_user_prompt(
                    agent_type="researchers_v2",
                    agent_name="bull_researcher_v2",
                    variables=template_variables,
                    preference_id=preference_id,
                    fallback_prompt=None,
                    context=state
                )

                if prompt:
                    logger.info(f"✅ Obtain optimistic scenario researcher user prompt words from template system (length: {len(prompt)})")
                    return prompt
            except Exception as e:
                logger.warning(f"⚠️ Failed to obtain user prompt words from template system: {e}, Use demotion prompts")

        # Downgrade: Use hard-coded prompt words that are semantically consistent with the current template
        market_name = state.get("market_name", "current market") if state else "current market"
        currency_name = state.get("currency_name", "Report original currency") if state else "Report original currency"
        currency_symbol = state.get("currency_symbol", "") if state else ""
        currency_display = f"{currency_name}（{currency_symbol}）" if currency_symbol else currency_name

        prompt = """Based on the analysis report provided, please provide {company_name} (Stock code:{ticker}) Construct an optimistic research argument.

    Current Analytical Markets:{market_name}
    If the material contains prices, valuations or financial values, please use them uniformly. {currency_display} as a unit.
    Please use the company name first when writing. {company_name} , Don t just use ticker symbols {ticker} Refers to the company.

    Available resources:
    - All analyst reports (including market/fundamentals/news/sentiment/market/sector, etc.):
    {analyst_reports}
    - Debate dialogue history:{historical_context}
    - Final Cautionary Evidence Argument:{current_response}
    - Reflections and lessons learned from similar situations:{past_memory_str}

    Please use Markdown for output, and preferably include the following headers:
    ## core proposition
    ## supporting evidence
    ## response to opposing views
    ## premise

    Requirements:
    - If there are new and verifiable public signals in this round, please add ## Follow-up observation signals ; If there are no new observation signals in this round, you can omit the title, or state it directly There are no new observation signals in this round. . 
    - When conducting multiple rounds of multi-scenario research, give priority to outputting the 1-2 points that are new in this round or are most worthy of response; if the new evidence is limited, you can clearly write The core judgment continues, and there is no new high-quality supporting evidence or premise revision. , Don t repeat extensions to make up the structure.
    It is strictly prohibited to output target prices, price ranges, key price points, profit margins, probability values and any trading suggestions.
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
    
    def _get_company_name(self, ticker: str, market_info: dict) -> str:
        """Get company name"""
        try:
            if market_info['is_china']:
                from tradingagents.dataflows.interface import get_china_stock_info_unified
                stock_info = get_china_stock_info_unified(ticker)
                if stock_info and "Stock name:" in stock_info:
                    return stock_info.split("Stock name:")[1].split("\n")[0].strip()
            elif market_info['is_hk']:
                from tradingagents.dataflows.providers.hk.improved_hk import get_hk_company_name_improved
                return get_hk_company_name_improved(ticker)
            elif market_info['is_us']:
                us_stock_names = {
                    'AAPL': 'apple inc.', 'TSLA': 'Tesla', 'NVDA': 'NVIDIA',
                    'MSFT': 'Microsoft', 'GOOGL': 'Google', 'AMZN': 'Amazon',
                }
                return us_stock_names.get(ticker.upper(), f"US stocks{ticker}")
        except Exception as e:
            logger.warning(f"Failed to get company name: {e}")
        
        return f"stocks{ticker}"

