"""
Fundamental Analyst Agent v2.0

Implementation of plug-in architecture based on BaseAgent
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from ..analyst import AnalystAgent
from ..base import BaseAgent
from ..config import AgentConfig, AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

# It is no longer necessary to import get_agent_prompt directly, use the _get_prompt_from_template method of the base class

# Import stock tool class
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    StockUtils = None

logger = logging.getLogger(__name__)


@register_agent
class FundamentalsAnalystAgentV2(AnalystAgent):
    """
    Fundamental Analyst Agent v2.0

    Features:
    - Use LangChain LLM
    - Dynamic tool binding (loading from configuration or database)
    - Support tool calling

    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent_with_dynamic_tools

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent_with_dynamic_tools("fundamentals_analyst_v2", llm)

        result = agent.execute({
            "ticker": "000001.SZ",
            "trade_date": "2024-12-01"
        })
    """

    # Create v2-specific metadata (with different IDs)
    metadata = AgentMetadata(
        id="fundamentals_analyst_v2",
        name="fundamental analyst v2.0",
        description="Analyze company financial data, profitability, growth and fundamental indicators, covering moat/competitive advantage assessment and management quality analysis",
        category=AgentCategory.ANALYST,
        license_tier=LicenseTier.FREE,
        default_tools=["get_stock_fundamentals_unified", "get_financial_statements", "get_cash_flow_statement", "get_peer_comparison"],
        max_tool_calls=4,
        version="2.0.0",
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="fundamentals_report", type="string", description="Fundamental Analysis Report"),
        ],
        requires_tools=True,
        output_field="fundamentals_report",
        report_label=" [Fundamental Analysis v2] ",
        workflow_stage="analyst",
        growth_role="extractor",
        growth_outputs=["fundamentals_report"],
        memory_scope_hint="object_tracking",
        review_level="auto_pending",
        growth_source_type="analysis_report",
    )

    # 🔑 Class level attributes (consistent with other adapters for use by execution trace classification)
    analyst_type = "fundamentals"
    output_field = "fundamentals_report"

    def __init__(
        self,
        config: Optional[Any] = None,
        llm: Optional[BaseChatModel] = None,
        tool_ids: Optional[list] = None
    ):
        """
        Initialize fundamental analyst
        
        Args:
            config: Agent Configuration (optional)
            llm: LangChain LLM Example
            tool_ids: List of tool IDs (optional, loaded from configuration if not provided)
        """
        super().__init__(config=config, llm=llm, tool_ids=tool_ids)
        
        # If tool_ids are not provided, load them from configuration
        if tool_ids is None and llm is not None:
            tool_ids = self.load_tools_from_config()
            if tool_ids:
                self._load_tools_v2(tool_ids)
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform fundamental analysis (using BaseAgent standardized tool call loop)

        Args:
            state: A status dictionary containing the following keys:
                - ticker: Stock code
                - trade_date: transaction date
                - messages: Message history (optional)
                - prompt_overrides: Prompt word override (optional, for debugging)

        Returns:
            The updated status includes:
                - fundamentals_report: Fundamental Analysis Report
                - messages: Updated message history
        """
        # P1: Start execution trace collection
        from core.agents.execution_trace_recorder import (
            start_execution_trace, is_trace_enabled
        )
        recorder = None
        if is_trace_enabled():
            try:
                recorder = start_execution_trace(self, state)
                self._last_trace_id = recorder.trace_id
            except Exception as e:
                logger.warning(f"⚠️ [{self.agent_id}] Failed to start trajectory collection (does not affect agent): {e}")
                self._last_trace_id = None

        try:
            ticker, trade_date = self._extract_common_params(state)
            context = state.get("context")

            # Support prompt word coverage (for debugging)
            overrides = state.get("prompt_overrides") or {}
            system_override = overrides.get("system")
            user_override = overrides.get("user")
            analysis_override = overrides.get("analysis")

            if not ticker:
                raise ValueError("Missing required parameter: ticker or company_of_interest")

            logger.info(f"Start fundamental analysis: {ticker} (Date: {trade_date})")

            # Build System Prompt Word (Priority: Override > Template > default)
            system_prompt = system_override
            if not system_prompt:
                system_prompt = self._build_system_prompt(state)

            # Build user prompt words (Priority: Override > default)
            user_prompt = user_override
            if not user_prompt:
                user_prompt = self._build_user_prompt(ticker, trade_date, state)

            system_prompt = self._apply_global_trading_advice_guard(system_prompt)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            # P1: record Prompt
            if recorder:
                try:
                    recorder.record_inputs({"ticker": ticker, "trade_date": trade_date})
                    recorder.record_prompts(system_prompt, user_prompt)
                except Exception as e:
                    logger.debug(f"[{self.agent_id}] Record Prompt failure (does not affect agent): {e}")

            # Standardized tool calling methods using BaseAgent
            if self._llm:
                analysis_prompt = analysis_override or self._build_analysis_prompt(ticker)
                prefetched_message, prefetched_tool_names = self._build_prefetched_tool_message(ticker, trade_date, state)
                if prefetched_message:
                    messages.append(prefetched_message)

                original_tools = list(self._langchain_tools)
                if prefetched_tool_names:
                    self._langchain_tools = [
                        tool for tool in original_tools
                        if getattr(tool, "name", "") not in prefetched_tool_names
                    ]

                # Use default prompt words (detailed analysis requirements and output formats are included in the template)
                # Unless the user overrides via prompt_overrides
                try:
                    analysis = self.invoke_with_tools(messages, analysis_prompt=analysis_prompt)
                finally:
                    self._langchain_tools = original_tools
            else:
                # Downgrade: No LLM or tools
                logger.warning("Without LLM or tools configured, simulation results are returned")
                analysis = self._generate_mock_report(ticker, trade_date)

            # P1: Record parsed output
            if recorder:
                try:
                    recorder.record_parsed_output({"report": analysis[:500] if isinstance(analysis, str) else str(analysis)[:500]})
                except Exception as e:
                    logger.debug(f"[{self.agent_id}] Record parsing output failure (does not affect agent): {e}")

            logger.info(f"✅ Fundamental analysis completed, report length: {len(analysis)} character")

            # Only the newly added fields are returned to avoid overwriting the updates of parallel nodes.
            parsed = self._parse_response(analysis)
            clean_report = parsed.get("report") or parsed.get("content") or analysis
            posterior = parsed.get("posterior") or self._normalize_posterior(parsed)

            result = {
                self.output_field: clean_report,
                "analyst_posteriors": {
                    self.agent_id: posterior
                }
            }
            # 🆕 Comes with tool call summary
            tool_summary = self._format_tool_call_summary()
            if tool_summary:
                result["tool_call_summaries"] = {self.agent_id: tool_summary}
            return result

        except Exception as e:
            logger.error(f"Fundamental analysis execution failed: {e}", exc_info=True)
            # P1: Log exception
            if recorder:
                try:
                    recorder.record_error(e)
                except Exception:
                    pass
            raise
        finally:
            # P1: Complete trajectory collection and write to MongoDB (non-blocking)
            if recorder:
                try:
                    recorder.finish()
                except Exception:
                    pass

    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words (refer to the implementation of research_manager_v2)

        Args:
            state: Workflow status (used to extract template variables)

        Returns:
            System prompt word
        """
        logger.info("🔍 [FundamentalsAnalystV2] Start building system prompt words")
        
        if state is None:
            state = {}

        # Use the base class's general method to obtain prompt words from the template system (refer to research_manager_v2)
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
            agent_type="analysts_v2",
            agent_name="fundamentals_analyst_v2",
            variables=template_variables,  # Pass necessary variables
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables (current_price, industry etc.)
            context=state.get("context") if state else None,  # Get from state context
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )

        logger.info(f"📝 System prompt word length: {len(prompt)} character")
        if prompt:
            logger.info(f"📝 The first 500 characters of the system prompt word:\n{prompt[:500]}...")
            logger.info(f"✅ Obtain fundamental analyst v2.0 system prompt words from the template system")
            return prompt
        
        # Downgrade: Use default prompt word
        logger.warning("⚠️ The system prompt word is not obtained from the template system, and the default prompt word is used.")
        return """You are a professional and objective stock fundamental analyst responsible for providing reviewable financial and operating evidence to the research process and conducting balanced financial analysis.

    Your task is:
    1. Use tools to obtain a company s overall fundamentals, most recent quarterly earnings details, cash flow information, and necessary peer valuation comparisons
    2. Analyze financial health, profitability, operating flexibility, operating quality and cash flow matching based on industry characteristics
    3. The context in which the valuation is assessed, describing the expectations reflected in market pricing and how these factors support or undermine the overall research conclusion
    4. Balance analysis of opportunity factors and risk factors, explain the key premises for establishing the conclusion and give a brief summary

    Requirements:
    - The analysis must be based on real data, and the model s own memory, common sense completion, or data that does not appear in the tool results must not be used to make judgments.
    - If the tool is missing a financial field, valuation field or peer data, you must explicitly write Tool results not provided or This dimension still needs to be verified 
    - By default, fundamental research only uses historical financials, historical valuation ranges and disclosed operating data; even if the tool returns daily snapshots of current stock price, rise and fall, trading volume, current total market capitalization, etc., these fields must not be written into the text or used as the basis for conclusions.
    - The most explanatory indicators should be selected based on industry characteristics and data available from tools, and mechanical coverage of all common financial accounts is not required; if a certain type of indicator is not applicable to the current industry, do not directly write its lack as a risk or data gap
    - As long as the text cites PE,PE(TTM), PB, PS(TTM) or other valuation snapshots, the snapshot date corresponding to the valuation must also be stated; if the dates of different indicators are different, they should be stated separately and cannot be regarded as the same day by default.
    - If the valuation snapshot date in the tool results is earlier than the analysis date, the actual valuation snapshot date returned by the tool must be used and must not be written As of analysis date Or replace the valuation date with the analysis date
    - If the tool explicitly prompts There is currently no daily frequency data after the close of the day. or Executed based on the caliber of the previous available trading day , The text must clearly state that the closing data of the day has not yet stabilized. This valuation or peer analysis is completed based on the data of the previous available trading day. You cannot just change the date without explaining the reason.
    - When the above stable data rollback prompt appears, you must `## core observation` Article 1 or `## Valuation background` Write down this date and caliber description at the beginning, and don t just mention it sporadically later in the article.
    - If get_financial_statements or get_cash_flow_statement is given explicitly Single quarter derivation Fields, use these fields first to describe quarterly changes; Original reporting period cumulative/snapshot The field is mainly used to check the caliber
    - Fields such as operating income, net profit attributable to the parent company, and operating cash flow in the A-share quarterly financial report are understood by default based on the cumulative caliber of the reporting period. Q2/Q3/Q4 are not single-quarter values and cannot be directly added or directly written as quarter-by-quarter improvement in a single quarter.
    - Indicators such as ROE and net interest rate are understood by default as snapshots of indicators during the reporting period; if they are not clearly deduced, do not write them as single-quarter indicators.
    - If you need to discuss valuation, you can only focus on the historical valuation quantiles, historical ranges or peer relative valuations clearly provided by the tool; you are not allowed to write the current stock price and current total market capitalization into the company profile, core observations or summary.
    - Try to break down the valuation background into four layers: absolute valuation, relative valuation, historical quantiles and market expectations. Don t just write Overestimation/Underestimation 
    - When explaining valuation premium or discount, give priority to explaining that it is more likely to correspond to profitability sustainability, cash recovery ability, competitive landscape or prosperous position.
    - It is allowed to quote real numerical values such as revenue growth, gross profit margin, net profit margin, ROE, ROA, operating cash flow, PE, PB, PEG, etc. to illustrate the facts, but it cannot be rewritten into a reasonable price, target price, safety margin or intervention range.
    - You can write: 2025Q4 The operating income and net profit attributable to the parent company belong to the cumulative caliber for the whole year. If we want to observe the changes in a single quarter, we need to further deduce it based on the Q3 cumulative value. 
    - You can write: The current ROE is a snapshot of the reporting period indicator and should not be directly interpreted as a single-quarter ROE. 
    - You can write: Applicable indicators should be selected based on industry characteristics; if a certain type of traditional turnover or liquidity indicator is not suitable for the current industry, there is no need to mechanically list it as a gap. 
    - You can write: The current PE and PB are both higher than the peer median, and the valuation premium is more likely to correspond to the market s pricing of earnings resilience and cash recovery capabilities. 
    - You can write: If the PEG is significantly higher than that of comparable companies, it means that the current valuation is more dependent on growth realization and the continuation of the boom. 
    - You can write: Operating cash flow is weaker than net profit, and the quality of profit realization still needs to be verified. 
    - Do not write: Net profit attributable to the parent company in the single quarter increased from 14.096 billion yuan in Q1 to 42.633 billion yuan in Q4. 
    - Do not write: Due to the lack of several common indicators, the current industry operating quality is weak. 
    - Do not write: The cumulative total for the whole year is approximately 10% after adding the net profits of the four quarters. 1,199.38 billion. 
    - Do not write: There is currently a clear margin of safety. 
    - Do not write: The turning point of the industry s prosperity is approaching, so it is recommended to make arrangements in advance. 
    - Do not write: The reasonable price range is 18-22 yuan. 
    - Do not write: If the valuation falls back to a certain range, it can be gradually laid out. 
    - Prioritize the output of research observations, evidence, risk warnings and matters to be verified
    - Do not output investment recommendations, target prices, price ranges, position recommendations or execution plans
    - Write reports in Chinese"""

    def _build_user_prompt(self, ticker: str, trade_date: str, state: Dict[str, Any] = None) -> str:
        """
        Construct user prompt words (refer to the implementation of research_manager_v2)
        
        Args:
            ticker: Stock code
            trade_date: transaction date
            state: Workflow status (used to extract template variables)
            
        Returns:
            User prompt words
        """
        logger.info("🔍 [FundamentalsAnalystV2] Start building user prompt words")
        logger.info(f"📊 Stock code: {ticker}")
        logger.info(f"📅 Analysis date: {trade_date}")
        
        if state is None:
            state = {}
        
        # Get market information and company name
        market_name = "China A shares"
        company_name = str(
            state.get("company_name")
            or state.get("stock_name")
            or state.get("name")
            or ""
        )
        currency_name = "RMB"
        currency_symbol = "¥"
        
        if StockUtils and ticker:
            try:
                market_info = StockUtils.get_market_info(ticker)
                market_name = market_info.get("market_name", "China A shares")
                currency_name = market_info.get("currency_name", "RMB")
                currency_symbol = market_info.get("currency_symbol", "¥")
                market_company_name = market_info.get("company_name", "")
                if market_company_name:
                    company_name = market_company_name
            except Exception as e:
                logger.warning(f"Failed to obtain market information: {e}")
        
        # Prepare template variables (refer to the implementation of research_manager_v2)
        template_variables = {
            "ticker": ticker,
            "company_name": company_name,
            "market_name": market_name,
            "analysis_date": trade_date,
            "current_date": trade_date,
            "start_date": "",  # Can calculate the date 1 year ago
            "currency_name": currency_name,
            "currency_symbol": currency_symbol,
            "tool_names": ", ".join([t.name for t in self._langchain_tools]) if self._langchain_tools else ""
        }
        
        # Use the general method of the base class to obtain user prompt words (refer to research_manager_v2)
        # The base class will automatically extract system variables (such as current_price, industry, etc.) from state
        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="fundamentals_analyst_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context"),  # Get from state context
            fallback_prompt=None,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        
        if prompt:
            logger.info(f"✅ Get fundamental analyst v2.0 user prompt words from the template system (length: {len(prompt)})")
            logger.info(f"📝 The first 500 characters of the user prompt word:\n{prompt[:500]}...")
            return prompt
        
        # Downgrade: Use default prompt word
        logger.warning("⚠️ The user prompt word is not obtained from the template system, and the default prompt word is used.")
        return f"""Please check the stock {ticker} Conduct objective and neutral fundamental research.

Analysis date:{trade_date}
Currency unit:{currency_name} ({currency_symbol}) 

    Please call the tool to obtain real fundamental data and generate a professional research report according to the following structure:
    1. core observation
    2. Company Profile
    3. Financial and operating signals
    4. Valuation background
    5. Balance of opportunities and risks
    6. Impact on overall research conclusions
    7. Summary

    Recommended calling sequence:
    - First call get_stock_fundamentals_unified to obtain the overall fundamental background, historical valuation range and caliber description. Do not write the real-time snapshot fields that may appear in the text.
    - Then call get_financial_statements to obtain the latest quarter s third statement and profit quality details
    - Then call get_cash_flow_statement to obtain the matching between cash flow and profit.
    - For A shares, if you need to supplement peer valuation positioning, you can call get_peer_comparison(ticker='{ticker}', trade_date='{trade_date}', top_n=10)

    Key coverage:
    - Analyze financial health, solvency, capital structure, liquidity and cash flow safety margin based on industry characteristics
    - Prioritize coverage of profit margins, rates of return, expense ratios, interest spreads or other profitability indicators that are applicable to the current industry and provided by the tool
    - PE, PB, PEG Compare the historical range with peers and explain what expectations the market has factored into
    - The balance between growth and stability, and the objective weighing of opportunities and risks

    If the tool does not return a financial field, valuation field or peer data, please explicitly write Tool results not provided or This dimension still needs to be verified , LLM s own knowledge may not be used to supplement data.
    By default, fundamental research only uses historical financials, historical valuation ranges and disclosed operating data; even if the tool returns daily snapshots of the current stock price, rise and fall, trading volume, current total market value, etc., it must not be written into the text or used as a basis for conclusions.
    As long as the text cites PE,PE(TTM), PB, PS(TTM) or other valuation snapshots, the snapshot date corresponding to the indicator must also be indicated; if the dates of different indicators are different, they should be stated separately.
    If the valuation snapshot date in the tool results is earlier than the analysis date, the actual valuation snapshot date returned by the tool must be used and must not be written As of analysis date Or replace the valuation date with the analysis date.
    If the tool explicitly prompts There is currently no daily frequency data after the close of the day. or Executed based on the caliber of the previous available trading day , must be in core observation Article 1 or Valuation background Let me state it at the beginning: There is currently no stable post-closing daily frequency data corresponding to the analysis day, so this historical valuation quantile and peer valuation are analyzed based on the previous available trading day; you cannot just change the date without explaining the reason.
    Please select the most explanatory indicators based on industry characteristics and data available from tools. It is not required to mechanically cover all common financial indicators. If a certain type of indicator is not applicable to the current industry, do not directly write its lack as a risk or data gap.
    If the tool is explicitly given Single quarter derivation Fields, use these fields first to describe quarterly changes; Original reporting period cumulative/snapshot The field is mainly used to check the caliber.
    Fields such as operating income, net profit attributable to parent companies, and operating cash flow in A-share quarterly financial reports are interpreted by default based on the cumulative caliber of the reporting period. They are not allowed to be directly written as quarter-by-quarter improvement in a single quarter, nor are Q1-Q4 directly added up.
    For indicators such as ROE and net interest rate, the default interpretation is based on the snapshot of the indicator during the reporting period; if it is not clearly deduced, do not write it as a single-quarter indicator.
    If you need to discuss valuation, you can only focus on the historical valuation quantiles, historical ranges or peer relative valuations provided by the tool. The current stock price and current total market capitalization are not allowed to be included in the company profile, core observations or summary.
    If there are matters that still need to be verified, they can be explained in the corresponding paragraph in passing, and do not need to be listed separately. Questions to be verified . 
    You can write: Applicable indicators should be selected based on industry characteristics; if a certain type of traditional turnover or liquidity indicator is not suitable for the current industry, there is no need to mechanically list it as a gap. 
    You can write: ROE is currently recovering, but the improvement in operating cash flow has not yet been synchronized, indicating that the quality of earnings repair still needs to be verified. 
    You can write: The current PB is at a position above the historical center, reflecting that the market s expectations for improvement are not low. 
    You can write: The current PE/PB premium reflects the market s higher requirements for profitability sustainability and cash flow quality. 
    You can write: If the prosperity position is still weak, the current high valuation means that the threshold for subsequent redemption will be higher. 
    You can write: If a single-quarter profit judgment is required, it should be derived separately based on the difference in cumulative values between adjacent reporting periods. 
    Do not write: Single-quarter revenue and net profit have increased quarter by quarter for four consecutive quarters. 
    Do not write: Due to the lack of several common indicators, the current industry operating quality is weak. 
    Do not write: There is currently a clear margin of safety. 
    Do not write: The turning point of the industry s prosperity is approaching, and you can ambush in advance. 
    Do not write: The reasonable price range is 18-22 yuan. 
    Do not write: If the valuation falls back to a certain range, it can be laid out. 

    Do not give trading recommendations, price targets, price ranges, position recommendations or trade triggers.
    No byline, author, analyst, date or claim information may be added."""

    def _build_analysis_prompt(self, ticker: str) -> str:
        """Build analysis prompt words"""
        return f"""Based on the obtained data, please generate {ticker} Professional fundamental research reports, including:

    1. core observation
    2. Company profile and current operating characteristics
    3. Analyze financial health, profitability, operating quality and cash flow matching based on industry characteristics
    4. Market expectations reflected in valuation background, historical range and comparison with peers
    5. Balanced assessment of opportunities and risks
    6. Support or weaken the overall research conclusion
    7. Summary

    If a piece of data is missing, please write directly Tool results not provided or This dimension still needs to be verified , Don t complete it yourself.
    By default, fundamental research only uses historical financials, historical valuation ranges, and disclosed operating data; even if the tool results include daily snapshots of current stock price, increase or decrease, trading volume, current total market value, etc., do not write these fields into the text or use them as the basis for conclusions.
    As long as the text cites PE,PE(TTM), PB, PS(TTM) or other valuation snapshots, the snapshot date corresponding to the indicator must also be indicated; if the dates of different indicators are different, they should be stated separately.
    If the valuation snapshot date in the tool results is earlier than the analysis date, the actual valuation snapshot date returned by the tool must be used and must not be written As of analysis date Or replace the valuation date with the analysis date.
    If the tool explicitly prompts There is currently no daily frequency data after the close of the day. or Executed based on the caliber of the previous available trading day , must be in core observation Article 1 or Valuation background Let me state it at the beginning: There is currently no stable post-closing daily frequency data corresponding to the analysis day, so this historical valuation quantile and peer valuation are analyzed based on the previous available trading day; you cannot just change the date without explaining the reason.
    Please select the most explanatory indicators based on industry characteristics and data available from tools. It is not required to mechanically cover all common financial indicators. If a certain type of indicator is not applicable to the current industry, do not directly write its lack as a risk or data gap.
    If the tool is explicitly given Single quarter derivation fields, preferentially use these fields to describe quarterly changes; do not use Original reporting period cumulative/snapshot Field incorrectly written as single quarter change.
    If there are matters that still need to be verified, they can be explained in the relevant paragraphs in passing, rather than in separate chapters.
    The valuation background should be broken down into absolute valuation, relative valuation, historical quantiles and market expectations as much as possible.
    If you need to discuss valuation, you can only focus on historical valuation quantiles, historical ranges, or relative valuations of peers. Do not write about the current stock price, current total market capitalization, or other real-time snapshot fields.
    It is allowed to quote real numerical values for factual explanations, but do not write the numerical values as reasonable prices, target prices, price ranges, safety margins, business turning point layouts, or transaction trigger conditions.

    Do not output price ranges, price targets, positions, or execution recommendations.
    No byline, author, analyst, date or claim information may be added."""

    def _get_market_characteristics(self, ticker: str) -> Dict[str, Any]:
        default_market_info = {
            "is_china": True,
            "market_name": "China A shares",
        }

        if not StockUtils or not ticker:
            return default_market_info

        try:
            market_info = StockUtils.get_market_info(ticker)
            if isinstance(market_info, dict):
                return {**default_market_info, **market_info}
        except Exception as exc:
            logger.warning(f"Failed to obtain stock market information, fallback to default A shares: {exc}")

        return default_market_info

    def _get_langchain_tool_by_name(self, tool_name: str):
        for tool in self._langchain_tools:
            if getattr(tool, "name", "") == tool_name:
                return tool
        return None

    def _invoke_prefetch_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Optional[str]:
        tool = self._get_langchain_tool_by_name(tool_name)
        if tool is None:
            logger.warning(f"Prefetch tool not found, skipped: {tool_name}")
            return None

        try:
            result = tool.invoke(tool_args)
        except Exception as exc:
            logger.warning(f"Prefetch tool execution failed {tool_name}: {exc}")
            return None

        result_text = str(result or "").strip()
        return result_text or None

    def _build_prefetched_tool_message(
        self,
        ticker: str,
        trade_date: Optional[str],
        state: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[HumanMessage], List[str]]:
        if not self._langchain_tools:
            return None, []

        effective_trade_date = trade_date or (state or {}).get("analysis_date") or datetime.now().strftime("%Y-%m-%d")
        # 🔧 Make sure curr_date is of type str (trade_date in state may be a datetime object)
        if isinstance(effective_trade_date, datetime):
            effective_trade_date = effective_trade_date.strftime("%Y-%m-%d")
        market_info = self._get_market_characteristics(ticker)
        is_china = bool(market_info.get("is_china"))

        tool_plan: List[Tuple[str, Dict[str, Any], str]] = [
            (
                "get_stock_fundamentals_unified",
                {"ticker": ticker, "curr_date": effective_trade_date},
                "Overall fundamental background",
            ),
        ]
        if is_china:
            tool_plan.extend(
                [
                    (
                        "get_financial_statements",
                        {"ticker": ticker, "limit": 4},
                        "Recent quarterly financial report details",
                    ),
                    (
                        "get_cash_flow_statement",
                        {"ticker": ticker, "limit": 4},
                        "Cash flow statement for most recent quarter",
                    ),
                ]
            )

        sections: List[str] = []
        consumed_tool_names: List[str] = []
        for tool_name, tool_args, section_title in tool_plan:
            result_text = self._invoke_prefetch_tool(tool_name, tool_args)
            if not result_text:
                continue

            sections.append(f"### {section_title}（{tool_name}）\n{result_text}")
            consumed_tool_names.append(tool_name)

        if not sections:
            return None, []

        content = (
            "The following required tool results are pre-fetched. Please give priority to completing the analysis based on these results, and do not call the tool with the same name repeatedly;"
            "If peer valuations or other supplementary evidence are still lacking, then call the remaining optional instruments.\n\n"
            + "\n\n".join(sections)
        )
        return HumanMessage(content=content), consumed_tool_names

    def _generate_mock_report(self, ticker: str, trade_date: str) -> str:
        """Generate simulation report (downgrade scenario)"""
        return f"""This is a simulated fundamental analysis report.

Stock code: {ticker}
Analysis date: {trade_date}

Financial status: good
Profitability: stable
Valuation level: reasonable
Research conclusion: Please continue to follow up with detailed evidence."""

