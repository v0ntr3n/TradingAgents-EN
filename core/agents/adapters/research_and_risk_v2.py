from __future__ import annotations
import sys as _sys

# === bull_researcher_v2 ===
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


# === bear_researcher_v2 ===
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


# === research_manager_v2 ===
"""
research integrator v2.0

Research integrator implemented based on ManagerAgent base class
Comprehensive research on optimistic and cautious scenarios to form balanced research conclusions
"""

import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from ..manager import ManagerAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)


# ==================== Schema contract definition ====================
# Purpose: Let LLM start from"discretionary decision output format"downgraded to"Translate a predefined schema", 
# Eliminate format inconsistencies at the source (refer to Bridgewater Pat's"Specification driven"Idea, isomorphic to risk_manager_v2).
# Compliance requirements: analysis_view can only take values "optimistic"/"Prudence"/"Neutral", 
# Prohibited use"Call/Put/Buy/Sell"Such as trading instructions or market view terms.


class ResearchManagerOutput(BaseModel):
    """Research integrator balances research conclusions schema"""
    # Compliance Terms: Optimistic/Cautious/Neutral (Prohibited"Call/Put/Buy/Sell"such as trading instructions or market view terms)
    analysis_view: Literal["乐观", "审慎", "中性"]
    confidence: float = Field(ge=0, le=1)
    risk_score: float = Field(ge=0, le=1)
    summary: str
    reasoning: str
    core_evidence: List[str] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)
    invalidation_conditions: List[str] = Field(default_factory=list)
    watch_items: List[str] = Field(default_factory=list)
    risk_warning: str = ""


# Research Integrator Output Format Contract.
# According to hard constraints"system prompt Formatting requirements must be placed first", This constant will be prepended to
# _build_system_prompt Returning the value first ensures that LLM sees formatting and compliance constraints first.
RESEARCH_MANAGER_SCHEMA_PROMPT = """ [output format contract·Must be strictly followed]
Your output must be a JSON object with the following fields. Just output JSON, don t wrap it in a markdown block, don t have any extra text.

{
  "analysis_view": "optimistic" | "Prudence" | "Neutral",
  "confidence": 0.0-1.0 floating point number between,
  "risk_score": 0.0-1.0 floating point number between,
  "summary": "50-120 Summary of the conclusion of the word, indicating which side is currently more preferred and the main reasons",
  "reasoning": "200-500 words, it is recommended to explain how to weigh the evidence according to the strongest basis for the optimistic scenario, the strongest basis for the cautious scenario, points of consensus, sources of disagreement, and final judgment.",
  "core_evidence": ["core basis 1", "core basis 2", "core basis 3"],
  "uncertainties": ["key uncertainties 1", "key uncertainties 2"],
  "invalidation_conditions": ["Judgment of downward revision or failure premise 1", "Judgment of downward revision or failure premise 2"],
  "watch_items": ["Follow-up observations 1", "Follow-up observations 2", "Follow-up observations 3"],
  "risk_warning": "100 Key risk warnings or major counter-evidence within 1 word"
}

 [Compliance Constraints·Must comply]
1. analysis_view Fields can only take values "optimistic" / "Prudence" / "Neutral". 
2. Prohibited use "bullish" / "Bearish" / "buy" / "sell" / "Add to position" / "Reduce positions" / "hold" / "Clearance" Such as trading instructions or market view terms.
3. "Optimistic/cautious/neutral" The opinions expressed are the tendencies of research conclusions and do not constitute any trading advice or operating instructions.
4. It is prohibited to give specific target prices or stop-loss prices, and may not extend to price ranges, upside/downside spaces, risk-benefit ratios or operational recommendations.
5. It is prohibited to promise profits or guarantee profits, and risks must be disclosed.
6. All conclusions must be strictly based on the content of the report provided and no falsification of information is allowed.

Field constraints:
- analysis_view: The tendency of research conclusions can only be"optimistic"/"Prudence"/"Neutral"
- confidence: 0-1 Floating point number between (do not write 0-100)
- risk_score: 0-1 Floating point number between (do not write 0-100)
- core_evidence / uncertainties / invalidation_conditions / watch_items: String array, try to provide 2-5 items
- reasoning It should be clearly reflected: the strongest basis for the optimistic scenario, the strongest basis for the cautious scenario, the consensus between both parties, the key sources of disagreement, and why the current judgment is biased towards one side or remains neutral.
- All fields must serve research and judgment, and transaction execution language cannot appear.

The output must be valid JSON, do not add any text or code block tags before or after the JSON.

"""

# Try importing utility functions
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    logger.warning("Unable to import StockUtils, some functions may not be available")
    StockUtils = None

try:
    from tradingagents.utils.template_client import get_agent_prompt, get_user_prompt
except (ImportError, KeyError):
    logger.warning("Unable to import get_agent_prompt/get_user_prompt, the default prompt word will be used")
    get_agent_prompt = None
    get_user_prompt = None

# It is no longer necessary to import get_agent_prompt/get_user_prompt directly, use the _get_prompt_from_template method of the base class


@register_agent
class ResearchManagerV2(ManagerAgent):
    """
    research integrator v2.0
    
    Function:
    - Comprehensive optimistic and cautious scenario research
    - Moderate debate (optional)
    - Make balanced research conclusions
    - Generate comprehensive research conclusions
    
    Workflow:
    1. Read the Optimistic and Cautious Scenario Research Report
    2. Moderate debate (optional)
    3. Comprehensive research and judgment
    4. Generate balanced research conclusions and key observations
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("research_manager_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15",
            "bull_report": "...",
            "bear_report": "..."
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="research_manager_v2",
        name="research integrator v2.0",
        description="Comprehensive research on optimistic and cautious scenarios to form balanced research conclusions and key observations",
        category=AgentCategory.MANAGER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],  # Managers don't need tools
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="bull_report", type="string", description="Optimistic Scenario Research Report", source="state", state_field="bull_report", producer_hint="bull_researcher_v2"),
            AgentInput(name="bear_report", type="string", description="Prudential Scenario Research Report", source="state", state_field="bear_report", producer_hint="bear_researcher_v2"),
        ],
        outputs=[
            AgentOutput(name="investment_advice", type="string", description="Balanced Study Conclusions"),
        ],
        requires_tools=False,
        output_field="investment_advice",
        report_label=" [Balanced research conclusion v2]",
        workflow_stage="manager",
        growth_role="optimizer",
        growth_outputs=["investment_plan", "investment_debate_state"],
        memory_scope_hint="research_asset",
        review_level="manual_required",
        growth_source_type="manager_decision",
        maturity_level="stable",
        input_mode="upstream-dependent",
        debug_replay_mode="requires_chain_prefill",
        callable_surfaces=["assistant", "workflow", "agent"],
    )
    
    # manager type
    manager_type = "research"
    
    # Output field name
    output_field = "investment_plan"

    # Whether to enable debate
    enable_debate = True

    def _run_delegated_research_agents(self, state: Dict[str, Any]) -> Dict[str, Any]:
        node_config = state.get("node_config") or {}
        delegated_agent_ids = node_config.get("delegated_agent_ids") or []
        if not isinstance(delegated_agent_ids, list):
            return {}

        delegated_outputs: Dict[str, Any] = {}
        for target_agent_id in delegated_agent_ids:
            normalized_target = str(target_agent_id or "").strip()
            if not normalized_target or normalized_target == self.agent_id:
                continue

            if normalized_target == "chip_distribution_analyst_v2" and (state.get("chip_report") or delegated_outputs.get("chip_report")):
                logger.info("[ResearchManagerV2] chip_report already exists, skip delegation chip_distribution_analyst_v2")
                continue

            logger.info("[ResearchManagerV2] Commission additional research Agent: %s", normalized_target)
            delegate_result = self.delegate_to_agent(
                normalized_target,
                {**state, **delegated_outputs},
                payload={
                    "task_description": "Supplement the context of chip distribution and position cost structure for research integrators to make comprehensive research judgments",
                },
                metadata={
                    "delegation_role": "research_enrichment",
                },
            )
            if isinstance(delegate_result, dict):
                delegated_outputs.update(delegate_result)

        return delegated_outputs

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform research integrator analysis

        Override the parent class method to add investment_debate_state output,
        Ensure compatibility with report formatters
        """
        logger.info("=" * 80)
        logger.info("🔍 [ResearchManagerV2] Start executing investment decisions")
        logger.info("=" * 80)

        # 🔍 Check input data
        ticker = state.get("ticker", "unknown")
        bull_report = state.get("bull_report", "")
        bear_report = state.get("bear_report", "")

        logger.info(f"📊 Stock code: {ticker}")
        logger.info(f"📈 Positive Evidence Report Type: {type(bull_report)}, length: {len(str(bull_report))} character")
        logger.info(f"📉 Cautionary Evidence Report Type: {type(bear_report)}, length: {len(str(bear_report))} character")

        # Convert to string if not
        bull_report_str = str(bull_report) if bull_report else ""
        bear_report_str = str(bear_report) if bear_report else ""

        if bull_report_str and len(bull_report_str) > 10:
            logger.info(f"📈 First 200 characters of positive evidence report: {bull_report_str[:200]}...")
        else:
            logger.warning("⚠️ Positive evidence report is empty or too short!")

        if bear_report_str and len(bear_report_str) > 10:
            logger.info(f"📉 Be careful with the first 200 characters of your evidence report: {bear_report_str[:200]}...")
        else:
            logger.warning("⚠️ Be careful if the evidence report is empty or too short!")

        # 🔥 ETF Workflow summary: If there is no debate report, synthesize three analyst reports into research materials
        if not bull_report_str and not bear_report_str:
            market_report = state.get("market_report", "")
            news_report = state.get("news_report", "")
            fundamentals_report = state.get("fundamentals_report", "")
            parts = []
            if fundamentals_report:
                parts.append(f"### ETF/fundamental analysis\n{fundamentals_report}")
            if market_report:
                parts.append(f"### Market and technical analysis\n{market_report}")
            if news_report:
                parts.append(f"### News analysis\n{news_report}")
            if parts:
                combined = "\n\n".join(parts)
                state = {
                    **state,
                    "bull_report": combined,
                    "bear_report": (
                        " (This workflow is a debate-free single-channel analysis mode."
                        "From the above comprehensive analysis materials, please identify factors supporting the upward trend and factors supporting the downward trend at the same time, and make a balanced judgment. )"
                    ),
                }
                logger.info(
                    f"[ResearchManagerV2] No debate report, analyst reports have been synthesized into research materials ({len(combined)} character)"
                )

        delegated_outputs = self._run_delegated_research_agents(state)
        if delegated_outputs:
            logger.info(f"🔗 [ResearchManagerV2] Delegate result field received: {list(delegated_outputs.keys())}")
            state = {**state, **delegated_outputs}

        # Call the parent class method to get basic output
        logger.info("🚀 Call the parent class execute method...")
        result = super().execute(state)
        logger.info("✅ The execution of the parent class execute method is completed")

        # Extract decision content
        decision_value = result.get(self.output_field, "")
        logger.info(f"📝 Decision output fields: {self.output_field}")
        logger.info(f"📝 Decision content type: {type(decision_value)}")
        logger.info(f"📝 Decision content length: {len(str(decision_value))} character")

        # Extract plain text for verification (compatible with both dictionary/string output formats)
        if isinstance(decision_value, dict):
            decision_text = decision_value.get("content", "") or decision_value.get("markdown", "") or str(decision_value)
        else:
            decision_text = str(decision_value) if decision_value else ""

        # 🔥 New: schema verification (make errors explicit, no longer silently cover up)
        import json
        validated_dict, validation_error = self._validate_research_output(decision_text)

        if validation_error is None:
            # ✅ Verification passed: stored as JSON string (keep type=string Compatible with downstream consumers)
            logger.info("✅ [ResearchManagerV2] schema Verification passed")
            result[self.output_field] = json.dumps(validated_dict, ensure_ascii=False)

            # 🔥 P2: Execute the assertion (non-blocking) and merge the results into validation_status
            assertion_result = self._run_assertions(
                raw_text=decision_text, parsed=validated_dict
            )
            assertion_violations_dump = [v.model_dump() for v in assertion_result.violations]
            if assertion_violations_dump:
                result["investment_plan_assertion_violations"] = assertion_violations_dump

            if assertion_result.has_error_violation:
                logger.warning(
                    f"⚠️ [ResearchManagerV2] Assert error violation {assertion_result.error_count} article, downgrade validation_status"
                )
                result["investment_plan_validation_status"] = "failed"
                result["investment_plan_validation_error"] = (
                    f"assert violation: {assertion_result.error_count} Article error"
                )
                self._record_trace_validation(
                    validation_status="failed",
                    validation_error=result["investment_plan_validation_error"],
                    validation_details={
                        "analysis_view": validated_dict.get("analysis_view"),
                        "confidence": validated_dict.get("confidence"),
                        "assertion_violations": assertion_violations_dump,
                    },
                )
            else:
                result["investment_plan_validation_status"] = "passed"
                self._record_trace_validation(
                    validation_status="passed",
                    validation_details={
                        "analysis_view": validated_dict.get("analysis_view"),
                        "confidence": validated_dict.get("confidence"),
                        "assertion_violations": assertion_violations_dump,
                    },
                )
            decision_content = result[self.output_field]
        else:
            # ❌ Verification failure: report explicitly (not silently report), retain the original output for troubleshooting
            logger.error(f"❌ [ResearchManagerV2] schema Verification failed: {validation_error}")
            logger.error(f"❌ [ResearchManagerV2] First 500 characters of raw output: {decision_text[:500]}")
            result[self.output_field] = decision_text
            result["investment_plan_validation_status"] = "failed"
            result["investment_plan_validation_error"] = validation_error

            # 🔥 P2: Assertions are also executed when verification fails (used to accumulate hit statistics)
            assertion_result = self._run_assertions(
                raw_text=decision_text, parsed=None
            )
            assertion_violations_dump = [v.model_dump() for v in assertion_result.violations]
            self._record_trace_validation(
                validation_status="failed",
                validation_error=validation_error,
                validation_details={
                    "raw_output_preview": decision_text[:500],
                    "assertion_violations": assertion_violations_dump,
                },
            )
            decision_content = decision_text

        # Get the existing investment_debate_state from state (if any)
        existing_debate_state = state.get("investment_debate_state", {})

        # Build a new investment_debate_state containing judge_decision
        new_debate_state = {
            "judge_decision": decision_content,  # ✅ Key: Preserve LLM output (JSON string or raw text)
            "history": existing_debate_state.get("history", ""),
            "bull_history": existing_debate_state.get("bull_history", ""),
            "bear_history": existing_debate_state.get("bear_history", ""),
            "current_response": decision_content,
            "count": existing_debate_state.get("count", 0),
        }

        logger.info("✅ [ResearchManagerV2] Investment decision execution completed")
        logger.info("=" * 80)

        # Return results containing investment_debate_state
        return {
            **delegated_outputs,
            **result,
            "investment_debate_state": new_debate_state,
        }

    def _validate_research_output(self, text: str) -> tuple:
        """
        Verify that the LLM output conforms to the ResearchManagerOutput schema.

        Args:
            text: LLM Output research conclusion text (may be plain JSON, JSON wrapped in markdown code blocks, or plain text)

        Returns:
            (validated_dict, None): If the verification passes, dict can be directly serialized as JSON
            (None, error_msg): Verification failed, error_msg describes the reason for the failure
        """
        import json
        import re

        if not text or not text.strip():
            return None, "Output is empty"

        # Compatible with JSON wrapped in markdown code blocks (```json ... ``` or ``` ... ```) 
        text = text.strip()
        json_str = text
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()

        # parse JSON
        try:
            json_obj = json.loads(json_str)
        except json.JSONDecodeError as e:
            return None, f"JSON Parsing failed: {e}"

        if not isinstance(json_obj, dict):
            return None, f"JSON The top level is not an object, the actual type: {type(json_obj).__name__}"

        # pydantic schema Verification (including compliance term enumeration constraints and numerical range constraints)
        try:
            validated = ResearchManagerOutput(**json_obj)
            return validated.model_dump(), None
        except ValidationError as e:
            return None, f"Schema Verification failed: {e}"

    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words (refer to the implementation of fundamentals_analyst_v2)

        Args:
            state: Workflow status (used to extract template variables)

        Returns:
            System prompt word
        """
        logger.info("🔍 [ResearchManagerV2] Start building system prompt words")
        
        if state is None:
            state = {}
        
        # Extract the necessary variables from state (if required by the system prompt word template)
        # Note: Although system prompt words usually do not require variables, some templates may require ticker, current_date, etc.
        # The base class will automatically extract system variables (such as current_price, industry, etc.) from state
        template_variables = {}
        
        # If there are ticker and analysis_date in state, extract them (the system prompt word template may be required)
        if "ticker" in state:
            template_variables["ticker"] = state["ticker"]
        if "analysis_date" in state or "trade_date" in state:
            analysis_date = state.get("analysis_date") or state.get("trade_date")
            if analysis_date:
                # Make sure the date is in the correct format
                if isinstance(analysis_date, str) and len(analysis_date) > 10:
                    analysis_date = analysis_date.split()[0]
                template_variables["current_date"] = analysis_date
                template_variables["analysis_date"] = analysis_date

        # Use the base class's general method to get the prompt word from the template system
        prompt = self._get_prompt_from_template(
            agent_type="managers_v2",  # ✅ Fix: use v2 types
            agent_name="research_manager_v2",  # ✅ Fix: use v2 names
            variables=template_variables,  # Pass necessary variables
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context"),  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # ✅ Key: Specify to obtain system prompt words (including output_format)
        )

        # Check whether the prompt word was successfully obtained
        if prompt:
            # 🔥 According to hard constraints"system prompt Formatting requirements must be placed first", 
            # Place the schema contract at the front of prompt to ensure that LLM sees the format and compliance constraints first.
            # It takes effect immediately without relying on database migration.
            prompt = RESEARCH_MANAGER_SCHEMA_PROMPT + prompt
            logger.info(f"📝 System prompt word length: {len(prompt)} Character (including schema contract)")
            logger.info(f"📝 The first 500 characters of the system prompt word:\n{prompt[:500]}...")

            # Check if new research brief structure guidance is included
            if "core_evidence" in prompt or "Follow-up observations" in prompt:
                logger.info("✅ The system prompt includes [Research Briefing Structure] guidance.")
            else:
                logger.warning("⚠️ The system prompt words do not contain [Research Briefing Structure] guidance (old version of the prompt words may be used)")

            logger.debug("✅ Obtain research integrator system prompt words from the template system")
            return prompt
        else:
            logger.warning("⚠️ Failed to obtain the system prompt word from the template system, use the default prompt word")

        # Default prompt word (compliant version)— Also prefix the schema contract to ensure that the fallback path is also constrained
        return RESEARCH_MANAGER_SCHEMA_PROMPT + """You are a neutral research integrator, responsible for organizing optimistic and cautious scenario research into balanced research conclusions.

    **Analytical style**: Be objective, restrained, and evidence-based, emphasizing strongest case comparisons, sources of disagreement, information gaps, and follow-up observations.

    **Core responsibilities**:
    1. First use the strongest establishment logic of both parties to understand the two types of arguments, optimistic and cautious, and then form the current research judgment.
    2. Explain the consensus, key differences, and sources of disagreement between the two parties, rather than just labeling the outcome.
    3. Point out the core basis supporting the judgment, key uncertainties, conditions under which the judgment may fail, and key points for subsequent observation.
    4. Output balanced research conclusions for downstream integration and risk review to help subsequent nodes understand Why do you think so and What to observe next . 

    **Analysis principles**:
    - The strongest arguments of both parties should be reviewed first with equal weight, and then the current tendency should be determined based on the quality of the evidence without presupposing conclusions.
    - Only research judgments are output, but buying, selling, holding, adding or subtracting positions, position ratio, target price, stop loss and profit or execution rhythm are not output.
    - Upward or downward drivers can be described, but only as research hypotheses, weights of evidence, and matters to be verified.
    - If the material involves current prices, valuations, or market expectations, it can explain how this information affects research judgment, but it cannot be extended to target prices, price ranges, upside/downsides, risk-benefit ratios, or operational recommendations.
    - All conclusions must be strictly based on the content of the report provided and no falsification of information is allowed.
    - Use Chinese output.

    **Output target**:
    - Allow users to understand which judgment is more supported by the current evidence and why the other side is not currently dominant.
    - Let users know the key basis, key risks, prerequisites for upgrading or downgrading, and follow-up observations.
    - Provide clear, reusable input to research conclusions to research integrators and risk teams.

    **Disclaimer**: 
    This research briefing is for informational purposes only and does not constitute trading advice or investment commitment. Please make independent judgment based on your own situation."""

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        inputs: Dict[str, Any],
        debate_summary: Optional[str],
        state: Dict[str, Any]
    ) -> str:
        """
        Build user prompt words

        Args:
            ticker: Stock code
            analysis_date: Analysis date
            inputs: Collection of input dictionaries
            debate_summary: Debate summary
            state: Workflow status

        Returns:
            User prompt words
        """
        logger.info("🔍 [ResearchManagerV2] Start building user prompt words")
        logger.info(f"📊 Stock code: {ticker}")
        logger.info(f"📅 Analysis date: {analysis_date}")
        logger.info(f"📝 input field: {list(inputs.keys())}")

        # Check positive and caution reports
        bull_report = inputs.get("bull_report", "")
        bear_report = inputs.get("bear_report", "")

        # Convert to string if not
        bull_report_str = str(bull_report) if bull_report else ""
        bear_report_str = str(bear_report) if bear_report else ""

        logger.info(f"📈 Positive Evidence Report Type: {type(bull_report)}, length: {len(bull_report_str)} character")
        logger.info(f"📉 Cautionary Evidence Report Type: {type(bear_report)}, length: {len(bear_report_str)} character")

        if bull_report_str and len(bull_report_str) > 10:
            # Check if price information is included
            if "price" in bull_report_str or "price" in bull_report_str or "¥" in bull_report_str:
                logger.info("✅ Positive evidence reports contain pricing information")
            else:
                logger.warning("⚠️ Positive evidence reports may not contain pricing information")
        else:
            logger.warning("⚠️ Positive evidence report is empty or too short!")

        if bear_report_str and len(bear_report_str) > 10:
            # Check if price information is included
            if "price" in bear_report_str or "price" in bear_report_str or "¥" in bear_report_str:
                logger.info("✅ Prudence Evidence reports contain pricing information")
            else:
                logger.warning("⚠️ Cautionary evidence reports may not contain pricing information")
        else:
            logger.warning("⚠️ Be careful if the evidence report is empty or too short!")

        # Get company name
        if StockUtils:
            market_info = StockUtils.get_market_info(ticker)
            company_name = self._get_company_name(ticker, market_info)
        else:
            company_name = ticker
        
        # Get the current price from state
        current_price = state.get("current_price", "unknown")
        logger.info(f"💰 current price: {current_price} (Source: state)")

        # 🆕 Extract the report content (if it is a dictionary, take the content field)
        def extract_content(report):
            """Extract plain text content from reports"""
            if isinstance(report, dict):
                return report.get('content', str(report))
            return str(report) if report else "None"

        bull_report_content = extract_content(inputs.get("bull_report"))
        bear_report_content = extract_content(inputs.get("bear_report"))

        logger.info(f"📈 Positive Evidence Report Content Length: {len(bull_report_content)} character")
        logger.info(f"📉 Be careful about the length of evidence report content: {len(bear_report_content)} character")

        # 🆕 Detect debate patterns and get debate history
        debate_history = ""
        is_debate_mode = "investment_debate_state" in state and isinstance(state.get("investment_debate_state"), dict)

        if is_debate_mode:
            debate_state = state.get("investment_debate_state", {})
            full_history = debate_state.get("history", "")
            bull_history = debate_state.get("bull_history", "")
            bear_history = debate_state.get("bear_history", "")

            if full_history:
                debate_history = f"\n [Full debate history]\n{full_history}\n"
                logger.info(f"💬 [debate mode] Read debate history, length: {len(full_history)} character")
            else:
                logger.info("💬 [debate mode] Debate history is empty")
        else:
            logger.info("📝 [Single analysis mode] No debate history")

        # Prepare template variables
        template_variables = {
            "ticker": ticker,
            "company_name": company_name,
            "analysis_date": analysis_date,
            "current_price": current_price,  # ✅ Add current price
            "bull_report": bull_report_content,  # ✅ Only the content is passed, not the dictionary
            "bear_report": bear_report_content,  # ✅ Only the content is passed, not the dictionary
            "debate_summary": debate_summary or "No debate summary",
            "debate_history": debate_history,  # 🆕 Add debate history
        }

        # Add other inputs to template variables
        for key, value in inputs.items():
            if key not in ["bull_report", "bear_report"]:
                template_variables[key] = str(value) if value else ""

        # Use the general method of the base class to obtain the user prompt word (the base class will automatically extract system variables from state)
        prompt = self._get_prompt_from_template(
            agent_type="managers_v2",  # ✅ Fix: use v2 types
            agent_name="research_manager_v2",  # ✅ Fix: use v2 names
            variables=template_variables,
            state=state,  # 🆕 Pass state and the base class will automatically extract system variables
            context=state,
            fallback_prompt=None,
            prompt_type="user"  # 🆕 Specify to obtain user prompt words
        )
        if prompt:
            logger.info(f"✅ Get research integrator user prompt words from template system (length: {len(prompt)})")
            return prompt
        
        market_name = state.get("market_name", "")
        currency_name = state.get("currency_name", "")
        currency_symbol = state.get("currency_symbol", "")

        target_line = f"{company_name}（{ticker}）"
        if market_name:
            target_line = f"{company_name}（{ticker}，{market_name}）"

        prompt = (
            "Make comprehensive research judgments based on the research materials provided.\n"
            "Available resources:\n"
            f"- Analysis goals:{target_line}\n"
            f"- Analysis date:{analysis_date}\n"
            f"- Currency unit:{currency_name} ({currency_symbol}) \n"
            f"- Current price context:{current_price}\n"
            f"- Optimistic scenario view:{bull_report_content}\n"
            f"- Prudent Scenario View:{bear_report_content}\n"
            f"- Debate summary:{debate_summary or 'Material not provided'}\n"
        )

        for key, value in inputs.items():
            if key not in ["bull_report", "bear_report"]:
                prompt += f"- Supplementary material {key}: {value}\n"

        prompt += """

Mission focus:
- Use the strongest version to summarize the reasons for the optimistic scenario first, and then use the strongest version to summarize the reasons for the cautious scenario. Don t write either side out as a straw man.
- Objectively weigh optimistic and cautious views, summarize the consensus first, and then write down the most critical disagreements to form the current research judgment: optimistic / cautious / neutral.
- Make it clear which content is the consensus of both parties and which is the key disagreement, and whether the disagreement mainly comes from data interpretation, premise assumptions, time dimension or the degree of market pricing reflection.
- Indicate the side that currently has more support; if remaining neutral, explain why the evidence on both sides is still balanced or has not been fully verified.
- Refining the core evidence supporting the judgment, highlighting the most critical evidence rather than listing all the information.
- Identify key uncertainties and which additional facts would revise up, downgrade or invalidate current judgments.
- List matters for follow-up observation, giving priority to verifiable matters such as financial reports, announcements, operating indicators, industry data, policy changes, etc.
- If the material involves current prices or valuations, it can state whether the market has factored in some optimistic/pessimistic expectations, but it cannot be written as target price, price range, upside/downside, or risk-benefit ratio.
- If any material is empty or the evidence is insufficient, you must explicitly write Material not provided or Still to be verified , Model memory completion must not be used.
- If you mention waiting for financial or annual reports, don t specify the year out of date, just write Waiting for the next financial report or Waiting for the annual report to be released . 

Strictly prohibited:
- Action suggestions such as buying, selling, holding, adding positions, reducing positions, clearing positions, etc. are not allowed.
- Target prices, price ranges, key prices, risk control reference prices, position ratios, and profit expectations are not allowed to be output.
- Observation conditions must not be written as execution actions after the price is triggered.

Output format:
Please use JSON output with the following fields:
```json
{
    "analysis_view": "optimistic|Prudence|Neutral",
    "confidence": 0.0-1.0,
    "risk_score": 0.0-1.0,
    "summary": "50-120 Summary of the conclusion of the word, indicating which side is currently more preferred and the main reasons",
    "reasoning": "200-500 words, it is recommended to explain how to weigh the evidence according to the strongest basis for the optimistic scenario, the strongest basis for the cautious scenario, points of consensus, sources of disagreement, and final judgment.",
    "core_evidence": ["core basis 1", "core basis 2", "core basis 3"],
    "uncertainties": ["key uncertainties 1", "key uncertainties 2"],
    "invalidation_conditions": ["Judgment of downward revision or failure premise 1", "Judgment of downward revision or failure premise 2"],
    "watch_items": ["Follow-up observations 1", "Follow-up observations 2", "Follow-up observations 3"],
    "risk_warning": "100 Key risk warnings or major counter-evidence within 1 word"
}
```

Field requirements:
- `analysis_view`, `confidence`, `summary`, `reasoning` is required.
- `core_evidence`, `uncertainties`, `invalidation_conditions`, `watch_items` For arrays, try to provide 2-5 items.
- `analysis_view` Can only take value"optimistic"/"Prudence"/"Neutral", Prohibited use"Call/Put/Buy/Sell"and other terms.
- `reasoning` It should be clearly reflected: the strongest basis for the optimistic scenario, the strongest basis for the cautious scenario, the consensus of both parties, the key sources of disagreement, and why the current judgment is biased towards one side or remains neutral.
- All fields must serve research judgment, and transaction execution language cannot appear.
"""

        logger.info(f"📝 Total length of user prompt words: {len(prompt)} character")
        logger.info(f"📝 The first 500 characters of the user prompt word:\n{prompt[:500]}...")

        if "Available resources" in prompt and "Mission focus" in prompt:
            logger.info("✅ The user prompt words include [Available Resources] and [Task Focus] guidance.")
        else:
            logger.warning("⚠️ The user prompt words do not include [Available Resources] and [Task Focus] guidance.")

        return prompt
    
    def _get_required_inputs(self) -> List[str]:
        """
        Get the required input list
        
        Returns:
            Enter a list of field names
        """
        return [
            "bull_report",
            "bear_report",
            "chip_report",
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


# === risk_manager_v2 ===
"""
risk assessor v2.0

Risk assessor implemented based on ManagerAgent base class
"""

import logging
from typing import Dict, Any, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from core.agents.manager import ManagerAgent
from core.agents.config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from core.agents.registry import register_agent

logger = logging.getLogger(__name__)


# ==================== Schema contract definition ====================
# Purpose: Let LLM start from"discretionary decision output format"downgraded to"Translate a predefined schema", 
# Eliminate format inconsistencies at the source (refer to Bridgewater Pat's"Specification driven"ideas).
# Compliance requirements: action/investment_adjustment can only take values "optimistic"/"Prudence"/"Neutral", 
# Prohibited use"Call/Put/Buy/Sell"Such as trading instructions or market view terms.


class FinalTradeDecision(BaseModel):
    """final research conclusion schema"""
    # Compliance Terms: Optimistic/Cautious/Neutral (Prohibited"Call/Put/Buy/Sell"such as trading instructions or market view terms)
    action: Literal["乐观", "审慎", "中性"]
    confidence: float = Field(ge=0, le=1)
    price_analysis_range: Optional[str] = None
    risk_reference_price: Optional[str] = None
    risk_exposure_ratio: Optional[str] = None
    reasoning: str = ""
    summary: str = ""
    risk_warning: str = ""


class RiskAssessmentOutput(BaseModel):
    """Risk review conclusion schema"""
    risk_level: Literal["低", "中", "高"]
    risk_score: float = Field(ge=0, le=1)
    reasoning: str
    key_risks: List[str] = Field(default_factory=list)
    risk_control: str = ""
    # Compliance terms: optimistic/cautious/neutral (same as action field)
    investment_adjustment: Literal["乐观", "审慎", "中性"]
    final_trade_decision: FinalTradeDecision


# Risk review conclusion output format contract.
# According to hard constraints"system prompt Formatting requirements must be placed first", This constant will be prepended to
# _build_system_prompt Returning the value first ensures that LLM sees formatting and compliance constraints first.
RISK_ASSESSMENT_SCHEMA_PROMPT = """ [output format contract·Must be strictly followed]
Your output must be a JSON object with the following fields. Just output JSON, don t wrap it in a markdown block, don t have any extra text.

{
  "risk_level": "low" | "in" | "high",
  "risk_score": 0.0-1.0 floating point number between,
  "reasoning": "Evaluation conclusion (string)",
  "key_risks": ["core risk 1", "core risk 2"],
  "risk_control": "Risk control suggestions (string)",
  "investment_adjustment": "optimistic" | "Prudence" | "Neutral",
  "final_trade_decision": {
    "action": "optimistic" | "Prudence" | "Neutral",
    "confidence": 0.0-1.0 floating point number between,
    "price_analysis_range": "Price analysis range (optional, fill in null if not available)",
    "risk_reference_price": "Risk control reference price (optional, fill in null if not available)",
    "risk_exposure_ratio": "Risk exposure analysis (optional, fill in null if not)",
    "reasoning": "analytical reasoning",
    "summary": "Analysis summary",
    "risk_warning": "Risk warning"
  }
}

 [Compliance Constraints·Must comply]
1. investment_adjustment and action fields can only take values "optimistic" / "Prudence" / "Neutral". 
2. Prohibited use "bullish" / "Bearish" / "buy" / "sell" / "Add to position" / "Reduce positions" / "hold" / "Clearance" Such as trading instructions or market view terms.
3. "Optimistic/cautious/neutral" The opinions expressed are the tendencies of research conclusions and do not constitute any trading advice or operating instructions.
4. It is forbidden to give a specific target price or stop loss price, and it can be output. "price analysis range" and label uncertainty.
5. It is prohibited to promise profits or guarantee profits, and risks must be disclosed.
6. All conclusions must be based on obtained data and no fabricated data or indicators are allowed.

Field constraints:
- risk_level: The risk level can only be"low"/"in"/"high"one of the three
- risk_score: 0-1 Floating point number between (do not write 0-100)
- investment_adjustment / action: can only be"optimistic"/"Prudence"/"Neutral"
- confidence: 0-1 Floating point number between (do not write 0-100)
- key_risks: String array, each item is a core risk
- If the optional field has no content, fill in null and do not omit the field name.

The output must be valid JSON, do not add any text or code block tags before or after the JSON.

"""

# Try importing the template system
try:
    from tradingagents.utils.template_client import get_agent_prompt
except (ImportError, KeyError) as e:
    logger.warning(f"Unable to import template system: {e}")
    get_agent_prompt = None

# It is no longer necessary to import get_agent_prompt directly, use the _get_prompt_from_template method of the base class

# Try importing stock tools
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    logger.warning("Unable to import StockUtils, some functions may not be available")
    StockUtils = None


@register_agent
class RiskManagerV2(ManagerAgent):
    """
    risk assessor v2.0
    
    Function:
    - Host risk robustness review
    - Comprehensive risk research evidence
    - Form a summary of risk research observations (does not constitute investment advice)
    
    Workflow:
    1. Read research plans and risk perspectives from all parties
    2. Host risk scenario review (optional)
    3. Comprehensive risk analysis and judgment
    4. Generate risk study observation reports
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("risk_manager_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15",
            "investment_plan": "...",
            "risky_opinion": "...",
            "safe_opinion": "..."
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="risk_manager_v2",
        name="risk assessor v2.0",
        description="Host the robustness review, integrate multiple perspectives, and formulate comprehensive research conclusions after the risk review (outputting research observations does not constitute investment advice)",
        category=AgentCategory.MANAGER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],  # Managers don't need tools
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="investment_plan", type="string", description="Comprehensive research conclusion", source="state", state_field="investment_plan", producer_hint="research_manager_v2"),
            AgentInput(name="risky_opinion", type="string", description="Highly elastic scenario research observations", required=False, source="state", state_field="risky_opinion", producer_hint="risky_analyst_v2"),
            AgentInput(name="safe_opinion", type="string", description="Defense Scenario Research Observations", required=False, source="state", state_field="safe_opinion", producer_hint="safe_analyst_v2"),
            AgentInput(name="neutral_opinion", type="string", description="Baseline Scenario Research Observations", required=False, source="state", state_field="neutral_opinion", producer_hint="neutral_analyst_v2"),
        ],
        outputs=[
            AgentOutput(name="risk_assessment", type="string", description="Robustness review and risk review report"),
            AgentOutput(name="risk_debate_state", type="dict", description="Risk multi-scenario research status (including judge_decision)"),
        ],
        requires_tools=False,
        output_field="risk_assessment",
        report_label=" [Risk review conclusion v2] ",
        workflow_stage="manager",
        growth_role="optimizer",
        growth_outputs=["risk_assessment", "risk_debate_state", "final_trade_decision"],
        memory_scope_hint="pattern",
        review_level="manual_required",
        growth_source_type="manager_decision",
        maturity_level="stable",
        input_mode="upstream-dependent",
        debug_replay_mode="requires_chain_prefill",
        callable_surfaces=["assistant", "workflow", "agent"],
    )

    # manager type
    manager_type = "risk"
    
    # Output field name
    output_field = "risk_assessment"
    
    # Is it necessary to debate
    enable_debate = True

    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words (refer to the implementation of fundamentals_analyst_v2)
        
        Args:
            state: Workflow status (used to extract template variables)
        
        Returns:
            System prompt word
        """
        logger.info("🔍 [RiskManagerV2] Start building system prompt words")
        
        if state is None:
            state = {}
        
        # Extract the necessary variables from state (if required by the system prompt word template)
        # Note: Although system prompt words usually do not require variables, some templates may require ticker, current_date, etc.
        # The base class will automatically extract system variables (such as current_price, industry, etc.) from state
        template_variables = {}
        
        # If there are ticker and analysis_date in state, extract them (the system prompt word template may be required)
        if "ticker" in state:
            template_variables["ticker"] = state["ticker"]
        if "analysis_date" in state or "trade_date" in state:
            analysis_date = state.get("analysis_date") or state.get("trade_date")
            if analysis_date:
                # Make sure the date is in the correct format
                if isinstance(analysis_date, str) and len(analysis_date) > 10:
                    analysis_date = analysis_date.split()[0]
                template_variables["current_date"] = analysis_date
                template_variables["analysis_date"] = analysis_date
        
        # Use the base class's general method to get the prompt word from the template system
        prompt = self._get_prompt_from_template(
            agent_type="managers_v2",
            agent_name="risk_manager_v2",
            variables=template_variables,  # Pass necessary variables
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context"),  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # ✅ Key: Specify to obtain system prompt words (including output_format)
        )

        if prompt:
            # 🔥 According to hard constraints"system prompt Formatting requirements must be placed first", 
            # Place the schema contract at the front of prompt to ensure that LLM sees the format and compliance constraints first.
            # It takes effect immediately without relying on database migration.
            prompt = RISK_ASSESSMENT_SCHEMA_PROMPT + prompt
            logger.info(f"📝 System prompt word length: {len(prompt)} Character (including schema contract)")
            logger.info(f"📝 The first 500 characters of the system prompt word:\n{prompt[:500]}...")

            # Check if output format requirements are included
            if "output_format" in prompt.lower() or "JSON Format" in prompt or "json" in prompt.lower():
                logger.info("✅ The system prompt includes [output format requirements]")
            else:
                logger.warning("⚠️ The system prompt word may not contain [output format requirements] (old version of the prompt word may be used)")

            logger.debug("✅ Get the risk assessor system prompt words from the template system")
            return prompt

        logger.warning("⚠️ Failed to obtain the system prompt word from the template system, use the default prompt word")

        # Default prompt word (compliant version)— Also prefix the schema contract to ensure that the fallback path is also constrained
        return RISK_ASSESSMENT_SCHEMA_PROMPT + """You are a risk assessor responsible for integrating the robustness reviews of all parties and forming risk review conclusions.

    **Analytical style**: Objectivity, restraint, and robustness as the core, emphasizing judgment boundaries, constraints, failure triggers, and follow-up observations.

**Core responsibilities**:
    1. Comprehensive review of the robustness of high resilience, defense, and baseline scenarios.
    2. Identify key risks, vulnerabilities, and information gaps in current research conclusions.
    3. Explain what conditions would support an upward revision, maintenance, or downward revision of the conclusion.
    4. Form risk review conclusions and follow-up observation points.
    5. Give judgment constraints rather than specific operation suggestions.

**Analysis principles**:
    - Objectively synthesize the views of three parties and explain whether the current conclusion is robust enough based on evidence.
    - It does not output buying and selling, adding or subtracting positions, position ratio, target price, price range, stop loss and profit or execution rhythm.
    - Risk sources, observation signals, and conclusion invalidation conditions may be described, but shall not be extended to operational recommendations.
    - All conclusions must be strictly based on the materials provided and information must not be fabricated.
    - Use Chinese output.

**Tool usage guide**:

    Conduct a risk review review based on the risk perspective provided and comprehensive research conclusions.
    Evaluate all risk information from a robustness perspective.

**Disclaimer**: 
    This risk review conclusion is for information purposes only and does not constitute investment advice or transaction commitment. Please make independent judgment based on your own situation."""

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        inputs: Dict[str, Any],
        debate_summary: Optional[str],
        state: Dict[str, Any]
    ) -> str:
        """
        Build user prompt words
        
        Args:
            ticker: Stock code
            analysis_date: Analysis date
            inputs: Enter data (investment plan, views of various parties, etc.)
            debate_summary: Debate summary
            state: Current status
            
        Returns:
            User prompt words
        """
        logger.info("🔍 [RiskManagerV2] Start building user prompt words")
        logger.info(f"📊 Stock code: {ticker}")
        logger.info(f"📅 Analysis date: {analysis_date}")
        logger.info(f"📝 input field: {list(inputs.keys())}")
        
        # Examine all parties' risk perspectives
        risky_opinion = inputs.get("risky_opinion", "")
        safe_opinion = inputs.get("safe_opinion", "")
        neutral_opinion = inputs.get("neutral_opinion", "")
        investment_plan = inputs.get("investment_plan", "")
        
        # Convert to string if not
        risky_opinion_str = str(risky_opinion) if risky_opinion else ""
        safe_opinion_str = str(safe_opinion) if safe_opinion else ""
        neutral_opinion_str = str(neutral_opinion) if neutral_opinion else ""
        investment_plan_str = str(investment_plan) if investment_plan else ""
        
        logger.info(f"🔥 Highly elastic scenario perspective type: {type(risky_opinion)}, length: {len(risky_opinion_str)} character")
        logger.info(f"🛡️ Defense Scenario View Type: {type(safe_opinion)}, length: {len(safe_opinion_str)} character")
        logger.info(f"⚖️ Baseline scenario perspective type: {type(neutral_opinion)}, length: {len(neutral_opinion_str)} character")
        logger.info(f"📋 Investment plan type: {type(investment_plan)}, length: {len(investment_plan_str)} character")
        
        # Get company name
        company_name = self._get_company_name(ticker, state)
        logger.info(f"🏢 Company name: {company_name}")
        
        # 🆕 Extract the report content (if it is a dictionary, take the content field)
        def extract_content(report):
            """Extract plain text content from reports"""
            if isinstance(report, dict):
                return report.get('content', str(report))
            return str(report) if report else ""
        
        risky_opinion_content = extract_content(inputs.get("risky_opinion"))
        safe_opinion_content = extract_content(inputs.get("safe_opinion"))
        neutral_opinion_content = extract_content(inputs.get("neutral_opinion"))
        investment_plan_content = extract_content(inputs.get("investment_plan"))
        
        logger.info(f"🔥 Highly elastic situational viewpoint content length: {len(risky_opinion_content)} character")
        logger.info(f"🛡️ Defense Scenario Viewpoint Content Length: {len(safe_opinion_content)} character")
        logger.info(f"⚖️ Baseline Scenario Viewpoint Content Length: {len(neutral_opinion_content)} character")
        logger.info(f"📋 Investment plan content length: {len(investment_plan_content)} character")
        
        # Prepare template variables
        template_variables = {
            "ticker": ticker,
            "company_name": company_name,
            "analysis_date": analysis_date,
            "investment_plan": investment_plan_content,  # ✅ Only the content is passed, not the dictionary
            "risky_opinion": risky_opinion_content,  # ✅ Only the content is passed, not the dictionary
            "safe_opinion": safe_opinion_content,  # ✅ Only the content is passed, not the dictionary
            "neutral_opinion": neutral_opinion_content,  # ✅ Only the content is passed, not the dictionary
            "debate_summary": debate_summary or "",
        }
        
        # Add other inputs to template variables
        for key, value in inputs.items():
            if key not in ["investment_plan", "risky_opinion", "safe_opinion", "neutral_opinion"]:
                template_variables[key] = extract_content(value) if value else ""
        
        # Use the general method of the base class to obtain the user prompt word (the base class will automatically extract system variables from state)
        prompt = self._get_prompt_from_template(
            agent_type="managers_v2",
            agent_name="risk_manager_v2",
            variables=template_variables,
            state=state,  # 🆕 Pass state and the base class will automatically extract system variables
            context=state,
            fallback_prompt=None,
            prompt_type="user"  # 🆕 Specify to obtain user prompt words
        )
        
        if prompt:
            logger.info(f"✅ Obtain risk assessor user prompt words from the template system (length: {len(prompt)})")
            return prompt
        
        # Downgrade: Use default user prompt word
        logger.info("⚠️ Use downgraded user prompt words")
        return f"""Please base on {company_name} ({ticker}) The comprehensive research conclusions and the three-party robustness review opinions form a risk review conclusion:

📊 **Basic information**: 
- Stock code:{ticker}
- Company name:{company_name}
- Analysis date:{analysis_date}

     [Comprehensive research conclusion after risk review]
{investment_plan_content}

 [Highly elastic scenario research observation] 
{risky_opinion_content}

 [Defense Scenario Research Observation]
{safe_opinion_content}

 [Baseline Scenario Research Observation]
{neutral_opinion_content}

 [Summary of multi-scenario research]
{debate_summary or ''}

Based on the above information please:

1. Refining whether the current research conclusions are robust enough.
2. Explain key risks, judgment boundaries, and trigger conditions for upward or downward revisions of conclusions.
3. Follow-up observations and data gaps are given.
4. Make it clear not to directly give specific operation suggestions, position arrangements, target prices, price ranges, stop losses and profits, or execution rhythms.

The output goal is to formulate risk review conclusions rather than specific operational recommendations."""

    def _get_required_inputs(self) -> List[str]:
        """
        Get the required input list
        
        Returns:
            Enter a list of field names
        """
        return [
            "investment_plan",
            "risky_opinion",
            "safe_opinion",
            "neutral_opinion"
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

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute risk management decisions (including schema validation)

        Override parent class methods to add risk_debate_state and final_trade_decision outputs.
        This method uses RiskAssessmentOutput schema to verify the LLM output immediately after the parent class outputs:
        - Verification passed: Serialize the dict into a JSON string and store it in risk_assessment (the downstream consumer remains unchanged),
          And take final_trade_decision directly from validated dict (skipping _extract_final_trade_decision).
        - Validation failed: keep the original text as risk_assessment while writing
          risk_assessment_validation_status / risk_assessment_validation_error Fields are reported explicitly,
          final_trade_decision Use _extract_final_trade_decision to ensure logical compatibility.
        """
        import json

        # Call the parent class method to get basic output
        result = super().execute(state)

        # 🛡️ Q1: When the execution of the parent class fails (except exception packaging dict such as timeout/null response), it is directly transmitted transparently.
        # No schema verification and textualization——Otherwise {'error','success':False} will be _extract_text
        # After stringification, write back the state, and finally mix it into the report in the form of bare dict (see the failure form processing of engine/report_formatter)
        _raw_output = result.get(self.output_field)
        if isinstance(_raw_output, dict) and (
            _raw_output.get("success") is False
            or (
                _raw_output.get("success") is True
                and not str(_raw_output.get("content") or "").strip()
            )
        ):
            logger.warning(
                f"⚠️ [RiskManagerV2] The execution of the parent class failed ({_raw_output.get('error')}) , "
                f"Skip schema verification, and the failure status is directly transmitted to the downstream rendering layer"
            )
            return result

        # Extract the original text of the risk assessment
        risk_assessment_raw = result.get(self.output_field)
        risk_assessment_text = self._extract_text(risk_assessment_raw)

        # 🔥 New: schema verification (make errors explicit, no longer silently cover up)
        validated_dict, validation_error = self._validate_risk_assessment(risk_assessment_text)

        if validation_error is None:
            # ✅ Verification passed: stored as JSON string (keep type=string Compatible with downstream consumers)
            logger.info("✅ [RiskManagerV2] schema Verification passed")
            result[self.output_field] = json.dumps(validated_dict, ensure_ascii=False)
            # Take final_trade_decision directly from validated dict (schema has ensured that the field exists and is compliant)
            final_trade_decision_dict = validated_dict.get("final_trade_decision", {})
            final_trade_decision_markdown = self._format_final_trade_decision_markdown(final_trade_decision_dict)
            # risk_score At the top level of JSON, hang it to final_trade_decision for front-end display
            final_trade_decision = {
                **final_trade_decision_dict,
                "risk_score": validated_dict.get("risk_score"),
                "content": final_trade_decision_markdown,
            }

            # 🔥 P2: Execute the assertion (non-blocking) and merge the results into validation_status
            assertion_result = self._run_assertions(
                raw_text=risk_assessment_text, parsed=validated_dict
            )
            assertion_violations_dump = [v.model_dump() for v in assertion_result.violations]
            if assertion_violations_dump:
                result["risk_assessment_assertion_violations"] = assertion_violations_dump

            if assertion_result.has_error_violation:
                # error Level assertion violation → Downgrade validation_status to failed
                logger.warning(
                    f"⚠️ [RiskManagerV2] Assert error violation {assertion_result.error_count} article, downgrade validation_status"
                )
                result["risk_assessment_validation_status"] = "failed"
                result["risk_assessment_validation_error"] = (
                    f"assert violation: {assertion_result.error_count} Article error"
                )
                self._record_trace_validation(
                    validation_status="failed",
                    validation_error=result["risk_assessment_validation_error"],
                    validation_details={
                        "risk_level": validated_dict.get("risk_level"),
                        "risk_score": validated_dict.get("risk_score"),
                        "assertion_violations": assertion_violations_dump,
                    },
                )
            else:
                # only warning or no violation → keep passed
                result["risk_assessment_validation_status"] = "passed"
                self._record_trace_validation(
                    validation_status="passed",
                    validation_details={
                        "risk_level": validated_dict.get("risk_level"),
                        "risk_score": validated_dict.get("risk_score"),
                        "assertion_violations": assertion_violations_dump,
                    },
                )
        else:
            # ❌ Verification failure: report explicitly (not silently report), retain the original output for troubleshooting
            logger.error(f"❌ [RiskManagerV2] schema Verification failed: {validation_error}")
            logger.error(f"❌ [RiskManagerV2] First 500 characters of raw output: {risk_assessment_text[:500]}")
            result[self.output_field] = risk_assessment_text
            result["risk_assessment_validation_status"] = "failed"
            result["risk_assessment_validation_error"] = validation_error

            # 🔥 P2: Assertion is also executed when verification fails (used to accumulate hit statistics, but does not change the failed status)
            assertion_result = self._run_assertions(
                raw_text=risk_assessment_text, parsed=None
            )
            assertion_violations_dump = [v.model_dump() for v in assertion_result.violations]
            self._record_trace_validation(
                validation_status="failed",
                validation_error=validation_error,
                validation_details={
                    "raw_output_preview": risk_assessment_text[:500],
                    "assertion_violations": assertion_violations_dump,
                },
            )
            # Follow the original _extract_final_trade_decision logic (compatible with historical LLM output format)
            final_trade_decision_dict = self._extract_final_trade_decision(risk_assessment_text)
            final_trade_decision_markdown = self._format_final_trade_decision_markdown(final_trade_decision_dict)
            final_trade_decision = {
                **final_trade_decision_dict,
                "content": final_trade_decision_markdown,
            }

        # Get the existing risk_debate_state from state (keep the original logic unchanged)
        existing_risk_state = state.get("risk_debate_state", {})

        # Build a new risk_debate_state containing judge_decision
        new_risk_state = {
            "judge_decision": risk_assessment_text,  # ✅ Key: Preserve original LLM output text
            "history": existing_risk_state.get("history", ""),
            "risky_history": existing_risk_state.get("risky_history", ""),
            "safe_history": existing_risk_state.get("safe_history", ""),
            "neutral_history": existing_risk_state.get("neutral_history", ""),
            "latest_speaker": "Judge",
            "current_risky_response": existing_risk_state.get("current_risky_response", ""),
            "current_safe_response": existing_risk_state.get("current_safe_response", ""),
            "current_neutral_response": existing_risk_state.get("current_neutral_response", ""),
            "count": existing_risk_state.get("count", 0),
        }

        return {
            **result,
            "risk_debate_state": new_risk_state,
            "final_trade_decision": final_trade_decision,  # ✅ Final research conclusion (including dictionary fields + Markdown content) 
        }

    def _validate_risk_assessment(self, text: str) -> tuple:
        """
        Verify that the LLM output conforms to the RiskAssessmentOutput schema.

        Args:
            text: LLM Output risk assessment text (may be plain JSON, JSON wrapped in markdown code blocks, or plain text)

        Returns:
            (validated_dict, None): If the verification passes, dict can be directly serialized as JSON
            (None, error_msg): Verification failed, error_msg describes the reason for the failure
        """
        import json
        import re

        if not text or not text.strip():
            return None, "Output is empty"

        # Compatible with JSON wrapped in markdown code blocks (```json ... ``` or ``` ... ```) 
        text = text.strip()
        json_str = text
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()

        # parse JSON
        try:
            json_obj = json.loads(json_str)
        except json.JSONDecodeError as e:
            return None, f"JSON Parsing failed: {e}"

        if not isinstance(json_obj, dict):
            return None, f"JSON The top level is not an object, the actual type: {type(json_obj).__name__}"

        # pydantic schema Verification (including compliance term enumeration constraints and numerical range constraints)
        try:
            validated = RiskAssessmentOutput(**json_obj)
            return validated.model_dump(), None
        except ValidationError as e:
            return None, f"Schema Verification failed: {e}"

    def _extract_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for k in ("content", "markdown", "text", "message", "report"):
                v = value.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        return str(value).strip()

    def _extract_final_trade_decision(self, risk_assessment_text: str) -> Dict[str, Any]:
        """
        Extract final_trade_decision field from LLM output JSON

        Args:
            risk_assessment_text: LLM Output risk assessment text (may contain JSON)

        Returns:
            final_trade_decision Dictionary, returning default value if extraction fails
        """
        import json
        import re

        if not risk_assessment_text:
            logger.warning("⚠️ [RiskManagerV2] risk_assessment_text Empty and cannot be extracted final_trade_decision")
            return self._get_default_final_decision()

        try:
            # Try to extract JSON code block
            json_obj = None

            if "```json" in risk_assessment_text:
                json_match = re.search(r'```json\s*(.*?)\s*```', risk_assessment_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1).strip()
                    json_obj = json.loads(json_str)
            elif risk_assessment_text.strip().startswith("{"):
                json_obj = json.loads(risk_assessment_text)

            if json_obj and isinstance(json_obj, dict):
                # Extract final_trade_decision field
                final_decision = json_obj.get("final_trade_decision", {})

                if final_decision and isinstance(final_decision, dict):
                    # Make sure confidence is a decimal between 0-1 (expected by the front end)
                    confidence = final_decision.get("confidence", 0.5)
                    if isinstance(confidence, (int, float)) and confidence > 1:
                        # If LLM returns an integer from 0 to 100, convert it to a decimal from 0 to 1
                        final_decision["confidence"] = confidence / 100.0
                    
                    # 🔥🔥🔥 Key fix: Extract risk_score from top-level JSON and add to final_decision
                    # risk_score At the top level of JSON, not in final_trade_decision
                    risk_score = json_obj.get("risk_score")
                    if risk_score is not None:
                        # Make sure risk_score is a float in the range 0-1
                        if isinstance(risk_score, (int, float)):
                            if risk_score > 1:
                                # If it is an integer from 0 to 100, convert it to a decimal from 0 to 1
                                risk_score = risk_score / 100.0
                            final_decision["risk_score"] = float(risk_score)
                            logger.info(f"✅✅✅ [RiskManagerV2] Extract risk_score from top-level JSON and add to final_trade_decision: {final_decision['risk_score']}")
                        else:
                            logger.warning(f"⚠️ [RiskManagerV2] risk_score Incorrect format: {risk_score}")
                    else:
                        logger.warning("⚠️ [RiskManagerV2] There is no risk_score field in the top-level JSON")
                    
                    # 🔥 Fix: Get it from the action field first, if not, get it from the analysis_view field
                    action = final_decision.get("action")
                    if not action:
                        # If action does not exist, try to get it from analysis_view
                        analysis_view = final_decision.get("analysis_view", "")
                        if analysis_view:
                            # analysis_view May be old terms (bullish/put/neutral) or compliance terms, which are uniformly mapped by action_mapping below when used directly
                            action = analysis_view
                            final_decision["action"] = action
                            logger.info(f"📝 [RiskManagerV2] Extract from analysis_view field action: {action}")
                    
                    if action:
                        # Compliance term mapping: unified mapping to"Optimistic/cautious/neutral"
                        # Prohibited use"Call/Put/Buy/Sell"Terms such as trading instructions or market views
                        action_mapping = {
                            "buy": "optimistic",
                            "sell": "Prudence",
                            "hold": "Neutral",
                            "Add to position": "optimistic",
                            "Reduce positions": "Prudence",
                            "Clearance": "Prudence",
                            "bullish": "optimistic",  # Compatible LLM may still output old terms
                            "Bearish": "Prudence",
                            "optimistic": "optimistic",  # Already a compliance term and remains unchanged
                            "Prudence": "Prudence",
                            "Neutral": "Neutral",
                        }
                        # Make sure to use compliant research conclusion terminology
                        if action in action_mapping:
                            final_decision["action"] = action_mapping[action]
                            logger.info(f"📝 [RiskManagerV2] mapping action: {action} -> {action_mapping[action]}")
                        # If already a compliance term (optimistic/cautious/neutral), leave it unchanged
                    else:
                        # If neither, use default value
                        final_decision["action"] = "Neutral"
                        logger.warning("⚠️ [RiskManagerV2] final_trade_decision There is no action or analysis_view field, use the default value'Neutral'")
                    
                    logger.info(f"✅ [RiskManagerV2] successfully extracted final_trade_decision: action={final_decision.get('action')}, confidence={final_decision.get('confidence')}, risk_score={final_decision.get('risk_score')}")
                    return final_decision
                else:
                    # If there is no final_trade_decision field, build from top-level fields
                    logger.warning("⚠️ [RiskManagerV2] JSON There is no final_trade_decision field in , built from top-level fields")
                    # confidence Returns a decimal between 0-1 (expected by the front end)
                    risk_score = json_obj.get("risk_score", 0.5)
                    investment_adjustment = json_obj.get("investment_adjustment", "Neutral")
                    # Compliance term mapping: unified mapping to"Optimistic/cautious/neutral"
                    action_mapping = {
                        "buy": "optimistic",
                        "sell": "Prudence",
                        "hold": "Neutral",
                        "bullish": "optimistic",
                        "Bearish": "Prudence",
                        "optimistic": "optimistic",
                        "Prudence": "Prudence",
                        "Neutral": "Neutral",
                    }
                    market_view = action_mapping.get(investment_adjustment, investment_adjustment)
                    return {
                        "action": market_view,  # Use Compliance Study Conclusion Terminology
                        "confidence": 1.0 - risk_score if risk_score <= 1 else (100 - risk_score) / 100.0,
                        "price_analysis_range": None,
                        "risk_reference_price": None,
                        "risk_exposure_ratio": "5%",
                        "reasoning": json_obj.get("reasoning", ""),
                        "summary": f"risk level: {json_obj.get('risk_level', 'in')}",
                        "risk_warning": ", ".join(json_obj.get("key_risks", [])[:3]) if json_obj.get("key_risks") else ""
                    }
            else:
                logger.warning("⚠️ [RiskManagerV2] Unable to parse JSON, return to default final_trade_decision")
                return self._get_default_final_decision()

        except Exception as e:
            logger.warning(f"⚠️ [RiskManagerV2] Failed to extract final_trade_decision: {e}")
            return self._get_default_final_decision()

    def _get_default_final_decision(self) -> Dict[str, Any]:
        """Returns the default final_trade_decision (compliant version)"""
        return {
            "action": "Neutral",  # Compliance Study Conclusion Terminology
            "confidence": 0.5,  # 0-1 of decimals (expected by the front end)
            "price_analysis_range": None,
            "risk_reference_price": None,
            "risk_exposure_ratio": "5%",
            "reasoning": "Insufficient risk assessment data, it is recommended to wait and see with caution",
            "summary": "Insufficient data, it is recommended to wait and see",
            "risk_warning": "Please wait for more analysis data"
        }
    
    def _format_final_trade_decision_markdown(self, decision: Dict[str, Any]) -> str:
        """
        Format final_trade_decision dictionary into Markdown format
        
        Args:
            decision: final_trade_decision dictionary
            
        Returns:
            Formatted Markdown string, each field is displayed on a separate line
        """
        if not decision:
            return "## final research conclusion\n\n Insufficient data are available to generate research conclusions."
        
        lines = ["## final research conclusion\n"]
        
        # Field mapping (Chinese name, compliance version)
        field_names = {
            "action": "**research conclusion tendency**",
            "confidence": "**Confidence**",
            "price_analysis_range": "**price analysis range**",
            "risk_reference_price": "**Risk control reference price**",
            "risk_exposure_ratio": "**Risk exposure analysis**",
            "reasoning": "**analytical reasoning**",
            "summary": "**Analysis summary**",
            "risk_warning": "**Risk warning**"
        }

        # Format each field
        action = decision.get("action", "")
        if action:
            # Compliance term mapping: unified mapping to"Optimistic/cautious/neutral", Prohibited use"Call/Put/Buy/Sell"terms such as
            action_mapping = {
                "buy": "optimistic",
                "sell": "Prudence",
                "hold": "Neutral",
                "bullish": "optimistic",
                "Bearish": "Prudence",
                "optimistic": "optimistic",
                "Prudence": "Prudence",
                "Neutral": "Neutral",
            }
            market_view = action_mapping.get(action, action)
            lines.append(f"{field_names.get('action', '**research conclusion tendency**')}: {market_view} (For reference only and does not constitute trading advice)")
        
        confidence = decision.get("confidence")
        if confidence is not None:
            # If it is a decimal between 0 and 1, convert it to a percentage and display it.
            if isinstance(confidence, float) and 0 <= confidence <= 1:
                confidence_display = f"{confidence * 100:.0f}%"
            elif isinstance(confidence, (int, float)) and confidence > 1:
                # If it is an integer from 0 to 100, the percentage is displayed directly.
                confidence_display = f"{int(confidence)}%"
            else:
                confidence_display = str(confidence)
            lines.append(f"{field_names.get('confidence', '**Confidence**')}: {confidence_display}")
        
        price_analysis_range = decision.get("price_analysis_range") or decision.get("target_price")
        if price_analysis_range is not None:
            lines.append(f"{field_names.get('price_analysis_range', '**price analysis range**')}: ¥{price_analysis_range} (For reference only and does not constitute a price prediction)")

        risk_reference_price = decision.get("risk_reference_price") or decision.get("stop_loss")
        if risk_reference_price is not None:
            lines.append(f"{field_names.get('risk_reference_price', '**Risk control reference price**')}: ¥{risk_reference_price} (For reference only and does not constitute trading advice)")

        risk_exposure_ratio = decision.get("risk_exposure_ratio") or decision.get("position_ratio")
        if risk_exposure_ratio:
            lines.append(f"{field_names.get('risk_exposure_ratio', '**Risk exposure analysis**')}: {risk_exposure_ratio} (For reference only and does not constitute trading advice)")
        
        reasoning = decision.get("reasoning")
        if reasoning:
            lines.append(f"\n{field_names.get('reasoning', '**analytical reasoning**')}:\n\n{reasoning}")
        
        summary = decision.get("summary")
        if summary:
            lines.append(f"\n{field_names.get('summary', '**Analysis summary**')}:\n\n{summary}")
        
        risk_warning = decision.get("risk_warning")
        if risk_warning:
            lines.append(f"\n{field_names.get('risk_warning', '**Risk warning**')}:\n\n{risk_warning}")
        
        # Add disclaimer
        lines.append("\n**Disclaimer**: ")
        lines.append("This analysis report is for reference only and does not constitute trading advice. All market views, price ranges, and risk assessments are for analysis reference only.")
        lines.append("It does not constitute specific operational recommendations. Investment is risky and decisions need to be made with caution. Investors should consider the following based on their own circumstances:")
        lines.append("Professional investment consultant opinions and independent investment judgments.")
        
        return "\n".join(lines)

# === trader_v2 ===
"""
research integrator v2.0

Research integrator implemented based on TraderAgent base class
Generate user-friendly research briefs based on comprehensive research evidence
 (System output is a summary of research observations and does not constitute investment advice)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..trader import TraderAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)


# ==================== Compliance constraints & Verify contract definition ====================
# Purpose: to form isomorphism with risk_manager_v2 / research_manager_v2"Specification driven"closed loop,
# Let LLM output from"free decision making"downgraded to"Translate according to predefined structure", Eliminate compliance risks at the source.
# Since the trader_v2 output is a user-readable Markdown presentation (unstructured JSON decision),
# Used here"Compliance constraints prompt prefix + term scan verification"lightweight mode,
# JSON schema is not enforced, but compliance violations are reported explicitly to facilitate monitoring and troubleshooting.


# Research Integrator Compliance Constraints & Briefing Structure Contract.
# According to hard constraints"system prompt Formatting requirements must be placed first", This constant will be prepended to
# _build_system_prompt Returning values first ensures that LLM sees compliance and structural constraints first.
TRADER_COMPLIANCE_PROMPT = """ [Compliance Constraints·Must be strictly followed]
1. Prohibited use "bullish" / "Bearish" / "buy" / "sell" / "Add to position" / "Reduce positions" / "hold" / "Clearance" Such as trading instructions or market view terms.
2. Use uniformly "optimistic" / "Prudence" / "Neutral" Express the tendency of research conclusions ("Optimistic/cautious/neutral" It expresses research tendencies and does not constitute trading advice).
3. It is prohibited to give a specific target price or risk attention price, and it cannot be extended to price range, upside/downside space, risk-benefit ratio or operation suggestions.
4. It is prohibited to promise profits or guarantee profits, and risks must be disclosed.
5. All conclusions must be strictly based on the content of the report provided, and no artificial information or internal knowledge of the model may be introduced.

 [Briefing Structure Contract·Must comply]
Please output the Markdown user version of the research report according to the following structure. Each chapter title must appear in the same order:

## One sentence conclusion
 (Summarize the current research judgment in one sentence, using"Optimistic/cautious/neutral"expression tendency)

## Why do you think so
 (Summarize the most critical 2-4 pieces of evidence, each on its own line)

## Limitations of current judgment
 (Explain information gaps, fragile premises, and conclusion boundaries)

## Follow up
 (List the public signals that are most worth following)

## Data boundary description
 (If the report does not provide key information, this must be clearly stated)

## Disclaimer
This research briefing is for informational purposes only and does not constitute investment advice or a trading commitment. Please make independent judgment based on your own situation.

"""


# Compliance disabled glossary (validation pipeline usage, consistent with prompt constraints)
TRADER_FORBIDDEN_TERMS: Tuple[str, ...] = (
    "bullish", "Bearish", "buy", "sell", "Add to position", "Reduce positions", "Clearance",
)

# Note:"hold" May appear in presentations at"hold this view"In non-trading contexts, separate verification will produce false positives.
# Therefore, the forced disable table is not placed, and the constraint is only at the prompt level. If you need more stringent verification, you can add it here.

# Necessary chapter mark for the briefing (used by the verification pipeline, consistent with the chapter name of the database template version 14)
TRADER_REQUIRED_SECTIONS: Tuple[str, ...] = (
    "One sentence conclusion", "Why do you think so",
)


# Try importing utility functions
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    logger.warning("Unable to import StockUtils, some functions may not be available")
    StockUtils = None

try:
    from tradingagents.utils.template_client import get_agent_prompt
except (ImportError, KeyError):
    logger.warning("Unable to import get_agent_prompt, default prompt word will be used")
    get_agent_prompt = None

# It is no longer necessary to import get_agent_prompt directly, use the _get_prompt_from_template method of the base class


@register_agent
class TraderV2(TraderAgent):
    """
    research integrator v2.0
    
    Function:
    - Generate user version of research briefing based on comprehensive research conclusions
    - Refining core basis, judgment boundaries and follow-up observations
    - Unify user-readable representations of upstream reports
    
    Workflow:
    1. Read comprehensive research conclusions and all analysis reports
    2. Refining the core information that users care about most
    3. Generate a user version of the research brief
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("trader_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15",
            "investment_plan": {...},
            "market_report": "...",
            "risk_assessment": "..."
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="trader_v2",
        name="research integrator v2.0",
        description="Generate user version of research briefing based on comprehensive research conclusions after risk review",
        category=AgentCategory.TRADER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],  # Research integrators don't need tools
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="investment_plan", type="string", description="Comprehensive research conclusion", source="state", state_field="investment_advice", source_state_fields=["investment_plan"], producer_hint="research_manager_v2"),
            AgentInput(name="market_report", type="string", description="Market analysis report", required=False, source="state", state_field="market_report", producer_hint="market_analyst_v2"),
            AgentInput(name="fundamentals_report", type="string", description="Fundamental Analysis Report", required=False, source="state", state_field="fundamentals_report", producer_hint="fundamentals_analyst_v2"),
            AgentInput(name="news_report", type="string", description="News analysis report", required=False, source="state", state_field="news_report", producer_hint="news_analyst_v2"),
            AgentInput(name="sentiment_report", type="string", description="Sentiment Analysis Report", required=False, source="state", state_field="sentiment_report", producer_hint="social_analyst_v2"),
            AgentInput(name="index_report", type="string", description="Market analysis report", required=False, source="state", state_field="index_report", producer_hint="index_analyst_v2"),
            AgentInput(name="sector_report", type="string", description="Sector analysis report", required=False, source="state", state_field="sector_report", producer_hint="sector_analyst_v2"),
            AgentInput(name="bull_report", type="string", description="Optimistic Scenario Research Report", required=False, source="state", state_field="bull_report", producer_hint="bull_researcher_v2"),
            AgentInput(name="bear_report", type="string", description="Prudential Scenario Research Report", required=False, source="state", state_field="bear_report", producer_hint="bear_researcher_v2"),
        ],
        outputs=[
            AgentOutput(name="trader_investment_plan", type="string", description="User version research briefing"),
        ],
        requires_tools=False,
        output_field="trader_investment_plan",
        report_label=" [User version research briefing v2]",
        workflow_stage="trader",
        growth_role="optimizer",
        growth_outputs=["trader_investment_plan"],
        memory_scope_hint="pattern",
        review_level="manual_required",
        growth_source_type="manager_decision",
        maturity_level="stable",
        input_mode="upstream-dependent",
        debug_replay_mode="requires_chain_prefill",
        callable_surfaces=["assistant", "workflow", "agent"],
    )

    # Output field names (consistent with field names expected by the report formatter)
    output_field = "trader_investment_plan"
    
    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words (refer to the implementation of fundamentals_analyst_v2)
        
        Args:
            state: Workflow status (used to extract template variables)
        
        Returns:
            System prompt word
        """
        # Use the base class's general method to obtain prompt words from the template system (refer to research_manager_v2)
        logger.info("🔍 [TraderV2] Start building system prompt words")
        
        if state is None:
            state = {}
        
        # Extract the necessary variables from state (if required by the system prompt word template)
        # Note: Although system prompt words usually do not require variables, some templates may require ticker, current_date, etc.
        # The base class will automatically extract system variables (such as current_price, industry, etc.) from state
        template_variables = {}
        
        # If there are ticker and analysis_date in state, extract them (the system prompt word template may be required)
        if "ticker" in state:
            template_variables["ticker"] = state["ticker"]
        if "analysis_date" in state or "trade_date" in state:
            analysis_date = state.get("analysis_date") or state.get("trade_date")
            if analysis_date:
                # Make sure the date is in the correct format
                if isinstance(analysis_date, str) and len(analysis_date) > 10:
                    analysis_date = analysis_date.split()[0]
                template_variables["current_date"] = analysis_date
                template_variables["analysis_date"] = analysis_date
        
        prompt = self._get_prompt_from_template(
            agent_type="trader_v2",
            agent_name="trader_v2",
            variables=template_variables,  # Pass necessary variables
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context"),  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )

        # 🔥 According to hard constraints"system prompt Formatting requirements must be placed first", 
        # constrain compliance & The briefing structure contract is placed at the front of prompt to ensure that LLM sees the compliance constraints first.
        # It takes effect immediately without relying on database migration.
        if prompt:
            prompt = TRADER_COMPLIANCE_PROMPT + prompt
            logger.info(f"📝 System prompt word length: {len(prompt)} Characters (including compliance constraints)")
            logger.debug("✅ Obtain research integrator system prompt words from the template system (compliance constraints are preset)")
            return prompt

        logger.warning("⚠️ Failed to obtain the system prompt word from the template system, use the default prompt word")

        # Default system prompt word (compliant version)— Also pre-compliance constraints ensure that the fallback path is also subject to constraints
        return TRADER_COMPLIANCE_PROMPT + """You are a research integrator responsible for generating user-generated research briefs based on comprehensive research findings from risk reviews.

## your responsibilities

    1. **Integrating research conclusions**: Translate comprehensive research findings into a presentation readable by ordinary users
    2. **Refining key information**: Summarize why we think so, key differences, uncertainties and follow-up concerns
    3. **Preserve research boundaries**: Explain the prerequisites for the current judgment to be established and the conditions under which it may fail.
    4. **unified expression caliber**: Organize multiple upstream reports into a consistent, clear, and readable final brief

## Analysis principles

    - **Based on research conclusions**: Organize content based on the research manager s comprehensive research conclusions and risk review conclusions.
    - **Does not extend to trading plan**: It is not allowed to output buying and selling, adding or subtracting positions, position ratio, target price, price range, risk focus and return focus price or execution rhythm.
    - **Objective presentation of evidence**: Clearly explain the basis supporting the judgment, key uncertainties and follow-up observations.
    - **Maintain user readability**: Use concise Chinese, do not stack jargon, and do not create information that is not provided

## Important note

    - **Based on existing data**: You can only use the provided analysis reports and upstream research conclusions to generate a user version of the research briefing
    - **Risk review is completed upstream**: This stage is responsible for integrating expressions and no longer regenerating trading plans or risk control plans.
    - **No external inferences are introduced**: Do not use internal knowledge of the model, information outside the material, or additional price deductions to supplement conclusions.

**Disclaimer**: 
    This research briefing is for informational purposes only and does not constitute investment advice or a trading commitment. Please make independent judgment based on your own situation."""

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the generation of research briefings and add explicit reporting of compliance verification.

        Override parent class method to add compliance term scanning and structural integrity check after LLM output,
        Make errors explicit (see risk_manager_v2 / research_manager_v2 s validation pipeline mode).

        Verification strategy:
        - Verification passed: Settings trader_plan_validation_status="passed"
        - Verification failed: retain the original output (the user-readable briefing is not automatically modified to avoid introducing errors),
          settings trader_plan_validation_status="failed" + trader_plan_validation_warning
        """
        logger.info("=" * 80)
        logger.info("📝 [TraderV2] Start executing user version research briefing generation")
        logger.info("=" * 80)

        # P1: Start execution trace collection (TraderV2 manages it by itself, because the parent class TraderAgent is not within the scope of ManagerAgent transformation)
        from core.agents.execution_trace_recorder import (
            start_execution_trace, is_trace_enabled
        )
        recorder = None
        if is_trace_enabled():
            try:
                recorder = start_execution_trace(self, state)
            except Exception as e:
                logger.warning(f"⚠️ [TraderV2] Failed to start trajectory collection: {e}")

        try:
            # record input
            if recorder:
                _input_keys = [
                    "investment_plan", "market_report", "fundamentals_report",
                    "news_report", "sentiment_report", "index_report", "sector_report",
                    "bull_report", "bear_report", "risk_assessment",
                ]
                _inputs = {k: state.get(k) for k in _input_keys if state.get(k)}
                recorder.record_inputs(_inputs)

            # Call the parent class method to get basic output
            import time as _time
            _t0 = _time.time()
            result = super().execute(state)
            _llm_duration_ms = int((_time.time() - _t0) * 1000)

            # Extract briefing content (compatible with both dictionary/string output formats)
            decision_value = result.get(self.output_field, "")
            if isinstance(decision_value, dict):
                decision_text = (
                    decision_value.get("content", "")
                    or decision_value.get("markdown", "")
                    or str(decision_value)
                )
            else:
                decision_text = str(decision_value) if decision_value else ""

            # P1: Logging output snapshot and token_usage (extracted from TraderAgent stash's _last_llm_response)
            if recorder:
                _llm_response = getattr(self, "_last_llm_response", None)
                if _llm_response is not None:
                    recorder.record_llm_response(_llm_response, llm_duration_ms=_llm_duration_ms)
                else:
                    # response When unreachable, only output snapshots are recorded (no token_usage)
                    from app.pro.models.execution_trace import OutputSnapshot
                    recorder.trace.output = OutputSnapshot(
                        output_raw_length=len(decision_text),
                        output_raw_preview=decision_text[:500] if decision_text else None,
                        output_parsed_keys=list(decision_value.keys()) if isinstance(decision_value, dict) else [],
                        output_parsed_success=decision_value.get("success", True) if isinstance(decision_value, dict) else True,
                        output_parsed_type="dict" if isinstance(decision_value, dict) else type(decision_value).__name__,
                    )
                    recorder.trace.llm_duration_ms = _llm_duration_ms
                recorder.record_parsed_output(decision_value if isinstance(decision_value, dict) else decision_text)

            # 🔥 Compliance verification (make errors explicit, don't hide behind them silently)
            validation_warning = self._validate_trader_output(decision_text)

            # 🔥 P2: Execution assertion (non-blocking). TraderV2 inherits TraderAgent (not ManagerAgent),
            # Directly call the assertion_executor singleton (parsed=None, Because the output is Markdown).
            from app.core.config import settings as _settings
            assertion_violations_dump: list = []
            assertion_has_error = False
            assertion_error_count = 0
            if getattr(_settings, "AGENT_ASSERTION_ENABLED", True):
                try:
                    from core.agents.assertion_executor import assertion_executor
                    assertion_result = assertion_executor.run_assertions_sync(
                        agent_id=self.agent_id,
                        raw_text=decision_text,
                        parsed=None,
                    )
                    assertion_violations_dump = [v.model_dump() for v in assertion_result.violations]
                    assertion_has_error = assertion_result.has_error_violation
                    assertion_error_count = assertion_result.error_count
                    if assertion_violations_dump:
                        result["trader_plan_assertion_violations"] = assertion_violations_dump
                except Exception as assertion_exc:
                    logger.warning(f"⚠️ [TraderV2] Assertion execution failed (does not affect agent): {assertion_exc}")

            # Merge assertion results into validation_status
            if validation_warning is None and not assertion_has_error:
                logger.info("✅ [TraderV2] Compliance verification passed")
                result["trader_plan_validation_status"] = "passed"
                if recorder:
                    # Update the memory object with set_validation, ensuring finish() The insert carries validation
                    #  (trader_v2 The finish is later than this call in finally, if using record_trace_validation
                    #  The DB update will be no-op because the document is not inserted, and then overwritten by finish to None)
                    recorder.set_validation(
                        validation_status="passed",
                        validation_details={"assertion_violations": assertion_violations_dump},
                    )
            else:
                # Either compliance check or assertion error or violation fails. → failed
                if validation_warning:
                    logger.warning(f"⚠️ [TraderV2] Compliance verification found problems: {validation_warning}")
                    logger.warning(f"⚠️ [TraderV2] First 500 characters of raw output: {decision_text[:500]}")
                if assertion_has_error:
                    logger.warning(
                        f"⚠️ [TraderV2] Assert error violation {assertion_error_count} Article"
                    )
                result["trader_plan_validation_status"] = "failed"
                if validation_warning:
                    result["trader_plan_validation_warning"] = validation_warning
                if assertion_has_error:
                    result["trader_plan_validation_error"] = (
                        f"assert violation: {assertion_error_count} Article error"
                    )
                if recorder:
                    recorder.set_validation(
                        validation_status="failed",
                        validation_error=validation_warning or f"assert violation: {assertion_error_count} Article error",
                        validation_details={
                            "raw_output_preview": decision_text[:500],
                            "assertion_violations": assertion_violations_dump,
                        },
                    )

            logger.info("✅ [TraderV2] The user version of the research briefing is generated")
            logger.info("=" * 80)
            return result

        except Exception as e:
            if recorder:
                recorder.record_error(e)
            raise
        finally:
            if recorder:
                recorder.finish()

    def _validate_trader_output(self, text: str) -> Optional[str]:
        """
        Verify LLM output for compliance and structural integrity.

        Since the trader_v2 output is a user-readable Markdown presentation (unstructured JSON),
        This method uses"Compliance terminology scan + Structural integrity check"lightweight mode,
        Returns a warning string (preserving the original output) if a violation is detected, or None if a violation is detected.

        Args:
            text: LLM Output research briefing text

        Returns:
            None: Verification passed
            str: Verification warning description (including violation details) for explicit reporting
        """
        if not text or not text.strip():
            return "Output is empty"

        warnings: List[str] = []

        # 1. Compliance term scanning (detecting trading order or market opinion terms)
        found_forbidden = [term for term in TRADER_FORBIDDEN_TERMS if term in text]
        if found_forbidden:
            warnings.append(f"Non-compliant term detected: {found_forbidden}")

        # 2. Structural integrity checks (required section markers)
        missing_sections = [s for s in TRADER_REQUIRED_SECTIONS if s not in text]
        if missing_sections:
            warnings.append(f"Missing required chapters: {missing_sections}")

        if warnings:
            return "; ".join(warnings)
        return None

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        investment_plan: Dict[str, Any],
        all_reports: Dict[str, Any],
        historical_trades: Optional[List[Dict[str, Any]]],
        state: Dict[str, Any]
    ) -> str:
        """
        Construct user prompt words (refer to the implementation of research_manager_v2)
        
        Args:
            ticker: Stock code
            analysis_date: Analysis date
            investment_plan: investment plan
            all_reports: All report dictionaries
            historical_trades: Historical transaction records
            state: Workflow status
            
        Returns:
            User prompt words
        """
        logger.info("🔍 [TraderV2] Start building user prompt words")
        logger.info(f"📊 Stock code: {ticker}")
        logger.info(f"📅 Analysis date: {analysis_date}")
        
        if state is None:
            state = {}
        
        # Get company name and market information
        company_name = ticker
        currency_name = "RMB"
        currency_symbol = "¥"
        
        if StockUtils and ticker:
            try:
                market_info = StockUtils.get_market_info(ticker)
                company_name = self._get_company_name(ticker, market_info)
                currency_name = market_info.get('currency_name', "RMB")
                currency_symbol = market_info.get('currency_symbol', "¥")
            except Exception as e:
                logger.warning(f"Failed to obtain market information: {e}")
        
        # 🆕 Extract the report content (if it is a dictionary, take the content field)
        def extract_content(report):
            """Extract plain text content from reports"""
            if isinstance(report, dict):
                return report.get('content', str(report))
            return str(report) if report else ""
        
        # Prepare template variables (refer to the implementation of research_manager_v2)
        # 🔑 Note: The risk review has been completed upstream, and this stage is responsible for integrating and presenting comprehensive research conclusions.
        template_variables = {
            "ticker": ticker,
            "company_name": company_name,
            "analysis_date": analysis_date,
            "current_date": analysis_date,
            "currency_name": currency_name,
            "currency_symbol": currency_symbol,
            # Investment plan (convert to string)
            "investment_plan": extract_content(investment_plan) if investment_plan else "",
            # 🔑 Available analysis reports (excluding risk_assessment)
            "market_report": extract_content(all_reports.get("market_report", "")),
            "fundamentals_report": extract_content(all_reports.get("fundamentals_report", "")),
            "news_report": extract_content(all_reports.get("news_report", "")),
            "sentiment_report": extract_content(all_reports.get("sentiment_report", "")),
            # Historical transaction records (converted to string)
            "historical_trades": "\n".join([str(trade) for trade in historical_trades[:3]]) if historical_trades else "",
        }
        
        # 🔑 Add other reports to template variables (excluding risk_assessment)
        # These reports include:sector_report, index_report, bull_report, bear_report Wait
        excluded_keys = ["risk_assessment", "market_report", "fundamentals_report", "news_report", "sentiment_report"]
        for key, value in all_reports.items():
            if key not in excluded_keys:
                template_variables[f"report_{key}"] = extract_content(value)
        
        # Use the general method of the base class to obtain user prompt words (refer to research_manager_v2)
        # The base class will automatically extract system variables (such as current_price, industry, etc.) from state
        prompt = self._get_prompt_from_template(
            agent_type="trader_v2",
            agent_name="trader_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context"),  # Get from state context
            fallback_prompt=None,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        
        if prompt:
            logger.info(f"✅ Get research integrator v2.0 user prompt words from the template system (length: {len(prompt)})")
            logger.info(f"📝 The first 500 characters of the user prompt word:\n{prompt[:500]}...")
            return prompt
        
        # Downgrade: Use default user prompt word
        logger.warning("⚠️ The user prompt word is not obtained from the template system, and the default prompt word is used.")

        summary_source = extract_content(all_reports.get("final_trade_decision", "")) or extract_content(all_reports.get("risk_management_decision", "")) or extract_content(investment_plan)
        prompt = f"""please for {company_name} ({ticker}) Generate a user version of the research brief:

## Basic information
- **Stock code**: {ticker}
- **Company name**: {company_name}
- **Analysis date**: {analysis_date}
- **currency unit**: {currency_name} ({currency_symbol}) 

    ## Comprehensive research conclusion after risk review

    {extract_content(investment_plan) if investment_plan else "No comprehensive research conclusion"}

    ## One sentence conclusion

    {summary_source or "Please refine a conclusion based on the following materials."}

## Available analysis reports

### 1. Market analysis report
{extract_content(all_reports.get("market_report", "")) or "No market analysis report"}

### 2. Fundamental Analysis Report
{extract_content(all_reports.get("fundamentals_report", "")) or "No fundamental analysis report"}

### 3. News analysis report
{extract_content(all_reports.get("news_report", "")) or "No news analysis report"}

### 4. Sector analysis report
{extract_content(all_reports.get("sector_report", "")) or "No sector analysis report"}

### 5. Market analysis report
{extract_content(all_reports.get("index_report", "")) or "No market analysis report"}

### 6. Optimistic Scenario Research Report
{extract_content(all_reports.get("bull_report", "")) or "No optimistic scenario research report"}

### 7. Prudential Scenario Research Report
{extract_content(all_reports.get("bear_report", "")) or "No prudent scenario research report"}

## Historical transaction records (if any)

{chr(10).join([str(trade) for trade in historical_trades[:3]]) if historical_trades else "No historical transaction record"}

## Mission requirements

Please generate a user-readable research briefing based on the above comprehensive research conclusions and various analysis reports, preferably including the following structure:

1. **One sentence conclusion**: Summarize the current research judgment in one sentence.
2. **Why do you think so**: Summarize the most critical 2-4 pieces of evidence.
3. **Limitations of current judgment**: Explain information gaps, fragile premises, and conclusion boundaries.
4. **Follow up**: Make a list of the public signals that are most worth continuing to track.
5. **Data boundary description**: If the report does not provide critical information, this must be clearly stated.

**Important tips**: 
- It is not allowed to output buying and selling, adding or subtracting positions, position ratio, target price, price range, risk focus and return focus price or execution rhythm.
- Can explain how prices, valuations and financial data influence research judgments, but may not extend to operational recommendations
- Must use {currency_name} ({currency_symbol}) as a monetary unit
- The language must be understandable by ordinary users, and information outside of the material must not be reproduced.

**Disclaimer**: 
This research briefing is for informational purposes only and does not constitute investment advice or a trading commitment. Please make independent judgment based on your own situation."""
        
        return prompt
    
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


# === risky_analyst_v2 ===
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
        logger.info("📊 [Risky Analyst] Input data length statistics:")
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
        logger.info("📊 [Highly Resilient Scenario Analyst] Template variables:")
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

            logger.info("⏱️ [Risky Analyst] Start calling LLM...")
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

            logger.info("✅ Aggressive risk analysis completed")

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


# === safe_analyst_v2 ===
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
        logger.info("📊 [Safe Analyst] Input data length statistics:")
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
        logger.info("📊 [Defense Scenario Analyst] Template variables:")
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

            logger.info("⏱️ [Safe Analyst] Start calling LLM...")
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

            logger.info("✅ Conservative risk analysis completed")

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


# === neutral_analyst_v2 ===
"""
Baseline Scenario Analyst v2.0

Baseline scenario analyst implementation based on the ResearcherAgent base class.
Review comprehensive research conclusions from a neutral perspective and compare evidence quality, judgment boundaries and baseline scenarios.
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
class NeutralAnalystV2(ResearcherAgent):
    """
    Baseline Scenario Analyst v2.0

    Function:
    - Review comprehensive research conclusions from a neutral perspective
    - Comparing the quality of evidence relied upon by the highly resilient versus defensive scenario views
    - Refining the most reliable current baseline scenario
    - Point out information gaps and matters to be verified
    - Supports multiple rounds of discussions (discussions with highly resilient, defensive scenario researchers)
    - Supports caching system (avoids repeated analysis)

    Workflow:
    1. Read comprehensive research conclusions and market analysis
    2. Read debate history and opponents views
    3. Use LLM to review baseline scenarios from a neutral perspective and balance both perspectives
    4. Generate a baseline scenario perspective
    5. Update debate status

    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("neutral_analyst_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15",
            "investment_plan": "...",
            "bull_opinion": "...",
            "bear_opinion": "...",
            "risk_debate_state": {
                "history": "...",
                "neutral_history": "...",
                "current_risky_response": "...",
                "current_safe_response": "...",
                "count": 0
            }
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="neutral_analyst_v2",
        name="Baseline Scenario Analyst v2.0",
        description="Balance optimistic and cautious materials, determine the most stable baseline scenario at present, and identify consensus, conflict points and information gaps",
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
            AgentInput(name="risky_opinion", type="string", description="Highly resilient scenario perspective", required=False, source="state", state_field="risky_opinion", producer_hint="risky_analyst_v2"),
            AgentInput(name="safe_opinion", type="string", description="defensive situational view", required=False, source="state", state_field="safe_opinion", producer_hint="safe_analyst_v2"),
            AgentInput(name="risk_debate_state", type="dict", description="debate status", required=False, source="state", state_field="risk_debate_state", producer_hint="risk_manager_v2"),
            AgentInput(name="market_report", type="string", description="Market analysis report", required=False, source="state", state_field="market_report", producer_hint="market_analyst_v2"),
            AgentInput(name="fundamentals_report", type="string", description="Fundamental Analysis Report", required=False, source="state", state_field="fundamentals_report", producer_hint="fundamentals_analyst_v2"),
            AgentInput(name="news_report", type="string", description="News analysis report", required=False, source="state", state_field="news_report", producer_hint="news_analyst_v2"),
            AgentInput(name="sentiment_report", type="string", description="Sentiment Analysis Report", required=False, source="state", state_field="sentiment_report", producer_hint="social_analyst_v2"),
            AgentInput(name="index_report", type="string", description="Market analysis report", required=False, source="state", state_field="index_report", producer_hint="index_analyst_v2"),
            AgentInput(name="sector_report", type="string", description="Sector analysis report", required=False, source="state", state_field="sector_report", producer_hint="sector_analyst_v2"),
        ],
        outputs=[
            AgentOutput(name="neutral_opinion", type="string", description="base case view"),
            AgentOutput(name="risk_debate_state", type="dict", description="Updated debate status"),
        ],
        requires_tools=False,
        output_field="neutral_opinion",
        report_label=" [Neutral risk assessment]",
        workflow_stage="risk",
        growth_role="reviewer",
        growth_outputs=["neutral_opinion"],
        memory_scope_hint="pattern",
        review_level="manual_required",
        growth_source_type="manager_decision",
        maturity_level="stable",
        input_mode="upstream-dependent",
        debug_replay_mode="requires_chain_prefill",
        callable_surfaces=["assistant", "workflow", "agent"],
    )

    # research stance (used by risk analysts "neutral") 
    stance = "neutral"

    # Output field name
    output_field = "neutral_opinion"

    # 🆕 Debate history field (for multi-round debates)
    history_field = "neutral_history"
    opponent_history_fields = ["risky_history", "safe_history"]
    
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
        logger.info("🔍 [NeutralAnalystV2] Start building system prompt words")
        
        prompt = self._get_prompt_from_template(
            agent_type="debators_v2",
            agent_name="neutral_analyst_v2",
            variables={},  # System prompt words do not require variables (refer to research_manager_v2)
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if state else None,  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        
        logger.info(f"📝 System prompt word length: {len(prompt)} character")
        if prompt:
            logger.debug("✅ Get the baseline scenario analyst system prompt words from the template system")
            return prompt

        # Downgrade: Use default prompt word
        return """You are a baseline scenario analyst.

Your character features:
    - ⚖️ Be objective and neutral, compare the quality of evidence and the boundaries of judgment
    - 📊 Data-driven, focusing on information gaps and premise integrity
    - 🎯 Organize analysis around the most secure current baseline scenario
    - 🔍 Comprehensively consider strengthening conditions, vulnerabilities, and unverified parts

Your task is:
    1. Baseline scenarios that review the current study s conclusions from a neutral perspective.
    2. Compare the quality of evidence on which the highly resilient and defensive scenario views each rely.
    3. Point out the most reliable judgment at present, the main information gaps and matters to be verified.
    4. Does not output positions, price ranges, risk-to-benefit ratios, or trading recommendations.

Assessment points:
    - Quality of evidence and robustness of conclusions
    - The most credible current baseline scenario
    - Information and verification paths that still need to be completed
    - The key premise behind the divergence of views

Requirements:
    - remain objective and neutral
    - Support your opinions with data and logic
    - Taking multiple factors into consideration
    - Write reports in Chinese"""

    def _build_user_prompt(self, ticker: str, analysis_date: str, state: Dict[str, Any]) -> str:
        """Construct user prompt words (obtained from template system and rendered)"""
        # 🆕 Get debate status
        risk_debate_state = state.get("risk_debate_state", {})
        history = risk_debate_state.get("history", "")
        current_risky_response = risk_debate_state.get("current_risky_response", "")
        current_safe_response = risk_debate_state.get("current_safe_response", "")

        # Prepare template variables (extract all data from state)
        template_variables = {
            "ticker": ticker,
            "analysis_date": analysis_date,
            "investment_plan": state.get("investment_plan", "") or state.get("trader_investment_plan", ""),
            "bull_opinion": state.get("bull_opinion", ""),
            "bear_opinion": state.get("bear_opinion", ""),
            "risky_opinion": state.get("risky_opinion", ""),
            "safe_opinion": state.get("safe_opinion", ""),
            "market_report": state.get("market_report", ""),
            "fundamentals_report": state.get("fundamentals_report", ""),
            "news_report": state.get("news_report", ""),
            "sentiment_report": state.get("sentiment_report", ""),
            "index_report": state.get("index_report", ""),
            "sector_report": state.get("sector_report", ""),
            # 🆕 debate related variables
            "history": history,
            "current_risky_response": current_risky_response,
            "current_safe_response": current_safe_response,
        }

        # 📊 Record input data length
        logger.info("📊 [Neutral Analyst] Input data length statistics:")
        logger.info(f"  - market_report: {len(template_variables['market_report']):,} character")
        logger.info(f"  - sentiment_report: {len(template_variables['sentiment_report']):,} character")
        logger.info(f"  - news_report: {len(template_variables['news_report']):,} character")
        logger.info(f"  - fundamentals_report: {len(template_variables['fundamentals_report']):,} character")
        logger.info(f"  - investment_plan: {len(template_variables['investment_plan']):,} character")
        logger.info(f"  - history: {len(history):,} character")
        total_length = (len(template_variables['market_report']) + len(template_variables['sentiment_report']) +
                       len(template_variables['news_report']) + len(template_variables['fundamentals_report']) +
                       len(template_variables['investment_plan']) + len(history) +
                       len(current_risky_response) + len(current_safe_response))
        logger.info(f"  - Total prompt length: {total_length:,} character (~{total_length//4:,} tokens)")

        # Downgrade prompt word (if template system is not available)
        fallback_prompt = f"""Please review the following comprehensive research conclusions from the perspective of a baseline scenario analyst and refine the current most reliable baseline scenario:

     [Comprehensive research conclusion]
    {template_variables['investment_plan'] or 'No comprehensive research conclusion'}

     [Optimistic Scenario View]
    {template_variables['bull_opinion'] or 'No optimistic scenario view'}

     [Prudent Scenario Perspective]
    {template_variables['bear_opinion'] or 'no prudence scenario view'}

     [Highly elastic scenario perspective]
    {template_variables['risky_opinion'] or 'No highly elastic scenario view'}

     [Defense Scenario Perspective]
    {template_variables['safe_opinion'] or 'defenseless situation perspective'}

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

     [Latest response from defense scenario analysts]
    {current_safe_response or 'None'}

    Please output your views on the baseline scenario, focusing on:
    1. What is the most credible current baseline scenario?
    2. What key premises do the highly resilient and defensive scenario perspectives respectively rely on?
    3. What verification information is missing?
    4. Do not output positions, price ranges, risk-reward ratios, or trading recommendations."""


        # Print template variables (for debugging)
        logger.info("📊 [Baseline Scenario Analyst] Template variables:")
        for key, value in template_variables.items():
            if isinstance(value, str) and len(value) > 100:
                logger.info(f"  - {key}: {value[:100]}...")
            else:
                logger.info(f"  - {key}: {value}")

        # Use the general method of the base class to obtain the user prompt word (preference_id will be extracted from context/state)
        prompt = self._get_prompt_from_template(
            agent_type="debators_v2",
            agent_name="neutral_analyst_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context") if isinstance(state, dict) else state,  # Get from state context
            fallback_prompt=fallback_prompt,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        if prompt:
            logger.info(f"✅ Get the baseline scenario analyst user prompt words from the template system (length: {len(prompt)})")
            return prompt

        # Downgrade: Use hardcoded prompt words
        logger.info(f"📝 [Baseline Scenario Analyst] Use demotion prompts (length: {len(fallback_prompt)})")
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
            "risky_opinion",
            "safe_opinion",
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
        Perform risk-neutral reviews (supports multiple rounds of debate)

        Args:
            state: A status dictionary containing the following keys:
                - ticker: Stock code
                - analysis_date: Analysis date
                - investment_plan: Comprehensive research conclusion
                - bull_opinion: Optimistic Scenario View (optional)
                - bear_opinion: Prudential scenario perspective (optional)
                - risky_opinion: Highly resilient scenario perspective (optional)
                - safe_opinion: Defense scenario perspective (optional)
                - risk_debate_state: Debate status (optional)

        Returns:
            The updated status includes:
                - neutral_opinion: base case view
                - risk_debate_state: Updated debate status
        """
        ticker = state.get("ticker", "") or state.get("company_of_interest", "")
        analysis_date = state.get("analysis_date", "") or state.get("trade_date", "")

        logger.info(f"⚖️ Baseline scenario analysts begin their assessment {ticker} @ {analysis_date}")

        # 🆕 Get debate status
        risk_debate_state = state.get("risk_debate_state", {})
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

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

            logger.info("⏱️ [Neutral Analyst] Start calling LLM...")
            import time
            llm_start_time = time.time()

            if self._llm:
                response = self._invoke_llm_with_trace(messages)
                opinion = response.content
            else:
                raise ValueError("LLM not initialized")

            llm_elapsed = time.time() - llm_start_time
            logger.info(f"⏱️ [Neutral Analyst] LLM The call is completed and takes time: {llm_elapsed:.2f}seconds")
            logger.info(f"📝 [Neutral Analyst] response length: {len(opinion):,} character")

            # 🆕 Formatting arguments (refer to the old version)
            argument = f"Neutral Analyst: {opinion}"

            # 🆕 Update debate status
            new_count = risk_debate_state.get("count", 0) + 1
            logger.info(f"⚖️ [Baseline Scenario Analyst] Finished speaking, counting: {risk_debate_state.get('count', 0)} -> {new_count}")

            new_risk_debate_state = {
                "history": history + "\n" + argument,
                "risky_history": risk_debate_state.get("risky_history", ""),
                "safe_history": risk_debate_state.get("safe_history", ""),
                "neutral_history": neutral_history + "\n" + argument,
                "latest_speaker": "Neutral",
                "current_risky_response": risk_debate_state.get("current_risky_response", ""),
                "current_safe_response": risk_debate_state.get("current_safe_response", ""),
                "current_neutral_response": argument,
                "count": new_count,
            }

            logger.info("✅ Neutral risk analysis completed")

            # Return the newly added fields and updated debate status
            return {
                "neutral_opinion": opinion,
                "risk_debate_state": new_risk_debate_state
            }

        except Exception as e:
            logger.error(f"❌ Neutral risk analysis failed: {e}", exc_info=True)
            return {
                "neutral_opinion": f"Neutral risk analysis failed: {str(e)}",
                "risk_debate_state": risk_debate_state  # Keep it as it is
            }


# === risk_self_debate_v2 ===
"""
Risk Self Debate Analyst v2.0 (A9-P1)

Complete the position statement and cross-examination from the three risk review perspectives of high elasticity/defense/baseline within a single node.
Alternative risk triangle (risky/safe/neutral_analyst_v2) multiple rounds of debate,
Changed LLM calls for deep/full profile risk debate sessions from rounds×3 times reduced to 1 time.

Design points:
- only if state["_risk_self_debate"]=True (depth/full range and the switch is on) is routed to,
  The fast/basic/standard files continue to follow the original risk triangle multi-agent path without affecting each other.
- The output is fully compatible with the original risk triangle:
  * risky_opinion / safe_opinion / neutral_opinion Three state fields
  * risk_debate_state structure (histories / current_*_response / count) 
  Render layer has zero changes from risk_manager_v2.
- Parse LLM output through three-part markup; when parsing fails, the full text is downgraded and filled to ensure that the field is not empty.
"""

import logging
import re
from typing import Any, Dict, List, Tuple

from langchain_core.messages import SystemMessage, HumanMessage

from ..researcher import ResearcherAgent
from ..registry import register_agent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput

logger = logging.getLogger(__name__)

# Three-perspective section markers (for output parsing, the order is the expected output order)
_SECTION_LABELS: Tuple[str, str, str] = ("Highly resilient scenario perspective", "defensive situational view", "base case view")

# Strict mode: Markers occupy one line ([X]/ ## X / **X** and other variants)
_MARKER_STRICT_RE = re.compile(
    r"(?m)^[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*)?[【\[]?\s*"
    r"(Highly resilient scenario perspective|defensive situational view|base case view)"
    r"\s*[】\]]?(?:\*\*)?[ \t]*[:：]?\s*$"
)

# Relaxed mode: mark at the beginning of the line, allow peers and content (enabled when strict mode parsing fails)
_MARKER_LOOSE_RE = re.compile(
    r"(?m)^[ \t]*(?:#{1,6}[ \t]*)?(?:\*\*)?[【\[]?\s*"
    r"(Highly resilient scenario perspective|defensive situational view|base case view)"
    r"\s*[】\]]?(?:\*\*)?[ \t]*[:：]?"
)


def _extract_sections(text: str, marker_re: re.Pattern) -> Dict[str, str]:
    """Split text by mark and return {label: Section content} (Only the first occurrence of each tag is taken)"""
    matches = list(marker_re.finditer(text))
    sections: Dict[str, str] = {}
    for i, m in enumerate(matches):
        label = m.group(1)
        if label in sections:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[label] = text[start:end].strip()
    return sections


def parse_self_debate_response(response: str) -> Tuple[str, str, str]:
    """
    The output of parsing self-argument is (risky, safe, neutral) Three paragraphs of opinion.

    Parsing strategy: strict (marks occupy one line)→ Loose (peer content)→ Full text downgraded.
    When downgrading the full text, three fields are filled with complete output to ensure downstream risk_manager and report rendering.
    Get non-empty content (a guaranteed behavior in extreme cases, it will not be triggered normally).
    """
    if not response or not response.strip():
        return "", "", ""

    sections = _extract_sections(response, _MARKER_STRICT_RE)
    if len(sections) < 3:
        sections = _extract_sections(response, _MARKER_LOOSE_RE)

    risky = sections.get(_SECTION_LABELS[0], "")
    safe = sections.get(_SECTION_LABELS[1], "")
    neutral = sections.get(_SECTION_LABELS[2], "")

    if risky and safe and neutral:
        return risky, safe, neutral

    logger.warning(
        f"[RiskSelfDebateV2] Output is not fully segmented by three segment markers "
        f"(risky={bool(risky)}, safe={bool(safe)}, neutral={bool(neutral)}), Downgrade to full text padding"
    )
    full = response.strip()
    return full, full, full


@register_agent
class RiskSelfDebateV2(ResearcherAgent):
    """
    risk self debate analyst v2.0

    Workflow:
    1. Read comprehensive research conclusions (investment_plan) and all upstream analysis reports
    2. Complete three-perspective self-debate in a single LLM call:
       position statement → Cross-examination → final output
    3. Parsed into risky/safe/neutral three-part view
    4. update risk_debate_state(histories / current_*_response / count) 

    The output is fully compatible with the original risk triangle (risky/safe/neutral_analyst_v2).
    """

    metadata = AgentMetadata(
        id="risk_self_debate_v2",
        name="risk self debate analyst v2.0",
        description="Single node completes risk review and cross-examination from three perspectives of high elasticity/defense/baseline (A9-P1 in-depth file path)",
        category=AgentCategory.RISK,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
            AgentInput(name="investment_plan", type="string", description="Comprehensive research conclusion", source="state", state_field="investment_plan", source_state_fields=["trader_investment_plan"], producer_hint="research_manager_v2"),
            AgentInput(name="bull_opinion", type="string", description="optimistic scenario view", required=False, source="state", state_field="bull_report", producer_hint="bull_researcher_v2"),
            AgentInput(name="bear_opinion", type="string", description="prudent situational view", required=False, source="state", state_field="bear_report", producer_hint="bear_researcher_v2"),
            AgentInput(name="market_report", type="string", description="Market analysis report", required=False, source="state", state_field="market_report", producer_hint="market_analyst_v2"),
            AgentInput(name="fundamentals_report", type="string", description="Fundamental Analysis Report", required=False, source="state", state_field="fundamentals_report", producer_hint="fundamentals_analyst_v2"),
            AgentInput(name="news_report", type="string", description="News analysis report", required=False, source="state", state_field="news_report", producer_hint="news_analyst_v2"),
            AgentInput(name="sentiment_report", type="string", description="Sentiment Analysis Report", required=False, source="state", state_field="sentiment_report", producer_hint="social_analyst_v2"),
            AgentInput(name="index_report", type="string", description="Market analysis report", required=False, source="state", state_field="index_report", producer_hint="index_analyst_v2"),
            AgentInput(name="sector_report", type="string", description="Sector analysis report", required=False, source="state", state_field="sector_report", producer_hint="sector_analyst_v2"),
        ],
        outputs=[
            AgentOutput(name="risky_opinion", type="string", description="Highly resilient scenario perspective"),
            AgentOutput(name="safe_opinion", type="string", description="defensive situational view"),
            AgentOutput(name="neutral_opinion", type="string", description="base case view"),
            AgentOutput(name="risk_debate_state", type="dict", description="Updated status of the risk debate"),
        ],
        requires_tools=False,
        output_field="risky_opinion",
        report_label=" [Self-debate from three perspectives of risk]",
        workflow_stage="risk",
        growth_role="reviewer",
        growth_outputs=["risky_opinion", "safe_opinion", "neutral_opinion"],
        memory_scope_hint="pattern",
        review_level="manual_required",
        growth_source_type="manager_decision",
        maturity_level="experimental",
        input_mode="upstream-dependent",
        debug_replay_mode="requires_chain_prefill",
        callable_surfaces=["workflow"],
    )

    # Self-debate does not take a single position
    stance = "self_debate"

    # Output field name (for status display, three opinion fields are actually output)
    output_field = "risky_opinion"

    debate_state_field = "risk_debate_state"

    # ==================== prompt word ====================

    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """Build system prompt word (template system takes priority, failure downgrade is hard-coded)"""
        prompt = self._get_prompt_from_template(
            agent_type="debators_v2",
            agent_name="risk_self_debate_v2",
            variables={},
            state=state,
            context=state.get("context") if state else None,
            fallback_prompt=None,
            prompt_type="system",
        )
        if prompt:
            logger.debug("✅ Obtain risk self-debate system prompt words from the template system")
            return prompt

        return """You are a senior risk research expert. Your task: In an in-depth thinking, complete the self-debate from three risk review perspectives and output only three final opinions.

Thinking method (completed during the thinking process, strictly prohibited from being written into the text):
1. Independently review the comprehensive research conclusions from three perspectives in turn and form judgments respectively;
2. Cross-examination: The high-resilience perspective points out where the defensive perspective is overly conservative and ignores proven positive signals; the defensive perspective points out which unverified assumptions the high-resilience perspective relies on and which evidence is flawed; the baseline perspective evaluates the evidence strength of both sides arguments and points out which disagreements stem from information gaps;
3. After absorbing reasonable doubts from the other party, a finalized view from three perspectives is formed.

Three perspectives (the name is fixed and cannot be changed)"Optimistic/cautious"and other names):
1. Highly elastic scenario: strengthening conditions, catalytic evidence, and high-requirement premise that upward revision of conclusions depends on
2. Defensive Scenario: Conclusion s weakest premises, key sources of risk, and failure conditions
3. Baseline scenario: Comparison of the quality of evidence for both sides arguments, information gaps and the current most reliable baseline scenario

Output requirements (highest priority, followed verbatim):
- The body of the text must and can only contain the following three sections, each beginning with the specified tag line
- Output is strictly prohibited"position statement""Cross-examination""final output"Any procedural title, number or content
- The three tags must occupy one line and be output as they are (retain [ ])

Output format (strictly follow this structure):
 [Highly elastic scenario perspective]
 (Final opinions from this perspective, 300-500 words: the strengthening conditions and catalysts on which the upward revision of the conclusion depends; what high-requirement prerequisites need to be met in order to be more positive; the evidence in the current materials that most supports the upward revision)
 [Defense Scenario Perspective]
 (Final opinions from this perspective, 300-500 words: the most fragile premise of the conclusion and key risk sources; failure conditions; which evidence is insufficient to support the current conclusion)
 [Baseline Scenario View]
 (Final opinions from this perspective, 300-500 words: Comparison of the evidence quality of both sides arguments; information gaps; the current most reliable baseline scenario and verification signals that need to be tracked)

Other requirements:
- The three perspectives must reflect the differences in conclusions after cross-examination and must not simply repeat the same conclusion.
- Does not output positions, target prices, profit margins or trading recommendations
- Written in Chinese"""

    @staticmethod
    def _report_text(value: Any) -> str:
        """Extract the plain text of the report (researcher output is dict{'content': ...}, compatible with str)"""
        if isinstance(value, dict):
            return str(value.get("content") or value.get("markdown") or "")
        return str(value) if value else ""

    def _build_user_prompt(self, ticker: str, analysis_date: str, state: Dict[str, Any]) -> str:
        """Construct user prompt words (template system takes priority, failure downgrade is hard-coded)"""
        investment_plan = state.get("investment_plan", "") or state.get("trader_investment_plan", "")
        # 🔑 Upstream bull/bear_researcher_v2 writes bull_report/bear_report (dict contains content);
        # state bull_opinion/bear_opinion are historical fields and are always empty.
        bull_opinion = self._report_text(state.get("bull_report"))
        bear_opinion = self._report_text(state.get("bear_report"))
        template_variables = {
            "ticker": ticker,
            "analysis_date": analysis_date,
            "investment_plan": investment_plan,
            "bull_opinion": bull_opinion,
            "bear_opinion": bear_opinion,
            "market_report": state.get("market_report", ""),
            "fundamentals_report": state.get("fundamentals_report", ""),
            "news_report": state.get("news_report", ""),
            "sentiment_report": state.get("sentiment_report", ""),
            "index_report": state.get("index_report", ""),
            "sector_report": state.get("sector_report", ""),
        }

        logger.info(
            f"📊 [RiskSelfDebate] Input data length: "
            f"investment_plan={len(template_variables['investment_plan']):,}, "
            f"bull_opinion={len(template_variables['bull_opinion']):,}, "
            f"bear_opinion={len(template_variables['bear_opinion']):,}, "
            f"market_report={len(template_variables['market_report']):,}, "
            f"news_report={len(template_variables['news_report']):,}, "
            f"fundamentals_report={len(template_variables['fundamentals_report']):,} character"
        )

        fallback_prompt = f"""Please complete the self-debate from the three perspectives of risk in an in-depth thinking, and directly output the three final opinions (the process content is only left in the thinking).

Analysis objects:{ticker or 'unspecified'} @ {analysis_date or 'unspecified'}

 [Comprehensive research conclusion]
{investment_plan or 'No comprehensive research conclusion'}

 [Optimistic researcher report]
{template_variables['bull_opinion'] or 'No optimistic researcher report'}

 [Prudential Researcher Report]
{template_variables['bear_opinion'] or 'No Prudential Researcher Report'}

 [Market analysis report]
{template_variables['market_report'] or 'No market analysis report'}

 [News analysis report]
{template_variables['news_report'] or 'No news analysis report'}

 [Fundamental analysis report]
{template_variables['fundamentals_report'] or 'No fundamental analysis report'}

 [Social Media Sentiment Report]
{template_variables['sentiment_report'] or 'No sentiment analysis report'}

 [Market analysis report]
{template_variables['index_report'] or 'No market analysis report'}

 [Sector analysis report]
{template_variables['sector_report'] or 'No sector analysis report'}

Please output strictly according to the three-paragraph mark format specified by the system prompt words: the main text only contains three final opinion sections ([Highly elastic scenario perspective]/[Defense scenario perspective]/[Baseline scenario perspective] each have their own line). Do not output any process content such as position statements, cross-examinations, etc."""

        prompt = self._get_prompt_from_template(
            agent_type="debators_v2",
            agent_name="risk_self_debate_v2",
            variables=template_variables,
            state=state,
            context=state.get("context") if isinstance(state, dict) else state,
            fallback_prompt=fallback_prompt,
            prompt_type="user",
        )
        if prompt:
            logger.info(f"✅ Obtain risk self-debate user prompt words from the template system (length: {len(prompt)})")
            return prompt
        logger.info(f"📝 [RiskSelfDebate] Use demotion prompts (length: {len(fallback_prompt)})")
        return fallback_prompt

    def _get_required_reports(self) -> list:
        return [
            "investment_plan",
            "bull_report",
            "bear_report",
            "market_report",
            "fundamentals_report",
            "news_report",
            "sentiment_report",
            "index_report",
            "sector_report",
        ]

    # ==================== execute ====================

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execution risk three-perspective self-debate (single LLM call)

        Returns:
            The updated status includes:
                - risky_opinion / safe_opinion / neutral_opinion: tripartite perspective
                - risk_debate_state: Updated debate status
        """
        ticker = state.get("ticker", "") or state.get("company_of_interest", "")
        analysis_date = state.get("analysis_date", "") or state.get("trade_date", "")

        logger.info(f"🧠 Risk Self Debate Analyst Begins Assessment {ticker} @ {analysis_date}")

        risk_debate_state = state.get("risk_debate_state", {}) or {}

        try:
            system_prompt = self._apply_global_trading_advice_guard(
                self._build_system_prompt(state)
            )
            user_prompt = self._build_user_prompt(ticker, analysis_date, state)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            import time
            llm_start_time = time.time()
            logger.info("⏱️ [RiskSelfDebate] Start calling LLM (single call instead of multiple rounds of risk triangle debate)...")

            if self._llm:
                response = self._invoke_llm_with_trace(messages)
                raw = response.content
            else:
                raise ValueError("LLM not initialized")

            # Some models return segmented content lists
            if isinstance(raw, list):
                raw = "".join(str(c) for c in raw)
            raw = str(raw)

            llm_elapsed = time.time() - llm_start_time
            logger.info(
                f"⏱️ [RiskSelfDebate] LLM The call is completed and takes time: {llm_elapsed:.2f}seconds,"
                f"Output length: {len(raw):,} character"
            )

            risky, safe, neutral = parse_self_debate_response(raw)
            logger.info(
                f"✅ Three-perspective analysis completed: risky={len(risky):,}, safe={len(safe):,}, "
                f"neutral={len(neutral):,} character"
            )

            # Updated debate status (compatible with original Risk Triangle)
            risky_arg = f"Risky Analyst: {risky}"
            safe_arg = f"Safe Analyst: {safe}"
            neutral_arg = f"Neutral Analyst: {neutral}"
            full_history = "\n".join([risky_arg, safe_arg, neutral_arg])
            old_history = risk_debate_state.get("history", "")
            old_count = risk_debate_state.get("count", 0)

            new_risk_debate_state = {
                "history": (old_history + "\n" + full_history).strip("\n"),
                "risky_history": (risk_debate_state.get("risky_history", "") + "\n" + risky_arg).strip("\n"),
                "safe_history": (risk_debate_state.get("safe_history", "") + "\n" + safe_arg).strip("\n"),
                "neutral_history": (risk_debate_state.get("neutral_history", "") + "\n" + neutral_arg).strip("\n"),
                "latest_speaker": "SelfDebate",
                "current_risky_response": risky_arg,
                "current_safe_response": safe_arg,
                "current_neutral_response": neutral_arg,
                "count": old_count + 3,  # Each of the three perspectives counts as one speech.
            }

            logger.info("✅ Risk self-debate completed (single node replaces risk triangle multi-round debate)")

            return {
                "risky_opinion": risky,
                "safe_opinion": safe,
                "neutral_opinion": neutral,
                "risk_debate_state": new_risk_debate_state,
            }

        except Exception as e:
            logger.error(f"❌ risk self debate failure: {e}", exc_info=True)
            error_text = f"risk self debate failure: {str(e)}"
            return {
                "risky_opinion": error_text,
                "safe_opinion": error_text,
                "neutral_opinion": error_text,
                "risk_debate_state": risk_debate_state,  # Keep it as it is
            }

_self_mod = _sys.modules[__name__]
for _sub in ['bull_researcher_v2', 'bear_researcher_v2', 'research_manager_v2', 'risk_manager_v2', 'trader_v2', 'risky_analyst_v2', 'safe_analyst_v2', 'neutral_analyst_v2', 'risk_self_debate_v2']:
    _sys.modules[f"core.agents.adapters.{_sub}"] = _self_mod