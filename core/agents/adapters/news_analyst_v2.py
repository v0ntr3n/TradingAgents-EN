"""
news analyst v2.0

News analyst implemented based on AnalystAgent base class
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple

from langchain_core.messages import SystemMessage, HumanMessage

from core.agents.analyst import AnalystAgent
from core.agents.base import GENERIC_REPORT_FALLBACK
from core.agents.config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from core.agents.registry import register_agent

logger = logging.getLogger(__name__)

# Try importing stock tools
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    logger.warning("Unable to import StockUtils, some functions may not be available")
    StockUtils = None


@register_agent
class NewsAnalystV2(AnalystAgent):
    """
    news analyst v2.0
    
    Function:
    - Get stock-related news and announcements
    - Identify the impact path and timeliness of events
    - Refining catalysts, risks and matters to be verified
    
    Workflow:
    1. Call the unified news tool to obtain news data
    2. Using LLM to analyze news content
    3. Generate news analysis reports
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("news_analyst_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15"
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="news_analyst_v2",
        name="news analyst v2.0",
        description="Analyze stock-related news and announcements, and refine event impact paths, catalysts, and risk warnings",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=["get_stock_news_headlines_unified", "get_stock_news_details_unified"],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="news_report", type="string", description="News analysis report"),
        ],
        requires_tools=True,
        output_field="news_report",
        report_label=" [News Analysis v2]",
        workflow_stage="analyst",
    )

    # Analyst type
    analyst_type = "news"
    
    # Output field name
    output_field = "news_report"

    def load_tools_from_config(self) -> list:
        """Force news analysts to use split headline/detail tools."""
        tool_ids = super().load_tools_from_config()
        filtered_tool_ids = [
            tool_id
            for tool_id in tool_ids
            if tool_id != "get_stock_news_unified"
        ]

        for required_tool in ["get_stock_news_headlines_unified", "get_stock_news_details_unified"]:
            if required_tool not in filtered_tool_ids:
                filtered_tool_ids.append(required_tool)

        return filtered_tool_ids

    @staticmethod
    def _build_news_tool_workflow_prompt(analysis_date: str) -> str:
        """Returns the fixed calling order description of the news tool."""
        return f"""
Tool workflow requirements:
1. The first step must be to call get_stock_news_headlines_unified, curr_date must be passed {analysis_date}. 
2. First, do duplication screening based on the title, source, relevance, and detailed suggestions. Do not start writing analysis directly.
3. In the second step, call get_stock_news_details_unified and pass in the selected 1 to 3 news_ids at once.
4. If title tooltip Can not be expanded temporarily , Don t go into detail unless the news is essential to your core argument.
5. Do not call get_stock_news_unified; this tool is a compatibility interface and is not the default process for this analyst.
""".strip()

    @staticmethod
    def _sanitize_template_prompt(prompt: Optional[str]) -> str:
        """Removed legacy unified news tools directives from templates to avoid conflicts with the two-stage workflow."""
        prompt_text = str(prompt or "").strip()
        if not prompt_text:
            return ""

        sanitized_lines = []
        skip_next_param_line = False
        for raw_line in prompt_text.splitlines():
            line = raw_line.rstrip()
            if "get_stock_news_unified" in line:
                skip_next_param_line = True
                continue

            if skip_next_param_line and line.strip().startswith("parameters:"):
                skip_next_param_line = False
                continue

            skip_next_param_line = False
            sanitized_lines.append(line)

        sanitized_prompt = "\n".join(sanitized_lines)
        sanitized_prompt = re.sub(r"\n{3,}", "\n\n", sanitized_prompt).strip()
        return sanitized_prompt

    @staticmethod
    def _has_two_stage_news_workflow(prompt: Optional[str]) -> bool:
        """Determine whether the template already comes with a two-stage news tool workflow."""
        prompt_text = str(prompt or "")
        return (
            "get_stock_news_headlines_unified" in prompt_text
            and "get_stock_news_details_unified" in prompt_text
        )

    def _get_langchain_tool_by_name(self, tool_name: str):
        for tool in self._langchain_tools:
            if getattr(tool, "name", "") == tool_name:
                return tool
        return None

    def _invoke_prefetch_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Optional[str]:
        tool = self._get_langchain_tool_by_name(tool_name)
        if tool is None:
            logger.warning(f"[NewsAnalystV2] Prefetch tool not found, skipped: {tool_name}")
            return None

        try:
            result = tool.invoke(tool_args)
        except Exception as exc:
            logger.warning(f"[NewsAnalystV2] Prefetch tool execution failed {tool_name}: {exc}")
            return None

        result_text = str(result or "").strip()
        return result_text or None

    @staticmethod
    def _select_news_ids_for_details(ticker: str, analysis_date: str, limit: int = 3) -> List[str]:
        """Select the news_id that needs to be expanded according to the recommended action of the headline tool."""
        try:
            from core.tools.implementations.news import stock_news as stock_news_module

            bundle = stock_news_module._build_stock_news_bundle(ticker, analysis_date, limit=12)
        except Exception as exc:
            logger.warning(f"[NewsAnalystV2] Failed to read the news candidate set, unable to select news_id: {exc}")
            return []

        items = bundle.get("items") or []
        selected_ids: List[str] = []
        for desired_action in ["Recommended to view", "View on demand"]:
            for item in items:
                if item.get("detail_action") != desired_action:
                    continue

                news_id = str(item.get("news_id") or "").strip()
                if not news_id or news_id in selected_ids:
                    continue

                selected_ids.append(news_id)
                if len(selected_ids) >= limit:
                    return selected_ids

        return selected_ids

    def _build_prefetched_tool_message(
        self,
        ticker: str,
        analysis_date: Optional[str],
    ) -> Tuple[Optional[HumanMessage], List[str]]:
        """Explicitly execute the two-step tool of news title and news details to avoid LLM getting stuck in fake tool call text under live."""
        if not self._langchain_tools:
            return None, []

        from datetime import datetime

        _raw_date = analysis_date or datetime.now().strftime("%Y-%m-%d")
        if isinstance(_raw_date, datetime):
            effective_date = _raw_date.strftime("%Y-%m-%d")
        else:
            effective_date = str(_raw_date)
        sections: List[str] = []
        consumed_tool_names: List[str] = []

        headline_result = self._invoke_prefetch_tool(
            "get_stock_news_headlines_unified",
            {"ticker": ticker, "curr_date": effective_date, "limit": 12},
        )
        if headline_result:
            sections.append(f"### News headlines after deduplication (get_stock_news_headlines_unified)\n{headline_result}")
            consumed_tool_names.append("get_stock_news_headlines_unified")

        selected_news_ids = self._select_news_ids_for_details(ticker, effective_date, limit=3)
        if selected_news_ids:
            details_result = self._invoke_prefetch_tool(
                "get_stock_news_details_unified",
                {
                    "ticker": ticker,
                    "curr_date": effective_date,
                    "news_ids": ",".join(selected_news_ids),
                },
            )
            if details_result:
                sections.append(f"### Expanded news details (get_stock_news_details_unified)\n{details_result}")
                consumed_tool_names.append("get_stock_news_details_unified")
        elif headline_result:
            sections.append(
                "### Detailed selection instructions\n There are no high-priority news that must be developed among the current headline candidates, and subsequent analysis needs to be carried out carefully based on headline-level evidence."
            )

        if not sections:
            return None, []

        content = (
            "The following news tool results have been pre-fetched. Please write your analysis directly based on these titles and details, and do not call the tool with the same name repeatedly;"
            "If longer details are not available for a particular story, please make sure that the writing tool results in no longer text.\n\n"
            + "\n\n".join(sections)
        )
        return HumanMessage(content=content), consumed_tool_names

    def _invoke_prefetched_analysis(self, messages: List[Any], analysis_prompt: str) -> str:
        """After the news tool prefetching is completed, let LLM generate the final analysis report directly."""
        final_messages = list(messages)
        final_messages.append(
            HumanMessage(
                content=(
                    "News titles and details have been provided. Do not output tool calls, JSON or XML tags,"
                    "Directly output the final Chinese Markdown research report.\n\n"
                    + analysis_prompt
                )
            )
        )

        response = self._invoke_llm_with_trace(final_messages)
        report = response.content if hasattr(response, "content") else str(response)

        if "```" in report or '"name": "get_stock_news_' in report:
            logger.warning("[NewsAnalystV2] The prefetch analysis phase still returns pseudo tool calls, add strong constraints and try again.")
            final_messages.append(
                HumanMessage(
                    content=(
                        "Do not request any more tool calls. Titles and details have been given. Now only the final Markdown report body is output,"
                        "Must include: latest news summary, news impact analysis, market sentiment assessment, and analytical opinions."
                    )
                )
            )
            response = self._invoke_llm_with_trace(final_messages)
            report = response.content if hasattr(response, "content") else str(response)

        # Bottom line: If the report is still JSON/XML that the tool calls after two retries, it will be downgraded to a text description instead of storing the original JSON
        if "</tool_call>" in report or '"name": "get_stock_news_' in report:
            logger.error("[NewsAnalystV2] After two retries, the pseudo tool call is still returned, and the process is downgraded.")
            report = "The current news data has been obtained but the analysis model cannot be deployed normally, and news research conclusions are temporarily unavailable. Please refer to other dimension reports."

        return report

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Override execution logic to support dedicated news analysis prompt words."""
        try:
            ticker, analysis_date = self._extract_common_params(state)

            market_type = state.get("market_type", "A shares")
            context = state.get("context")
            overrides = state.get("prompt_overrides") or {}
            system_override = overrides.get("system")
            user_override = overrides.get("user")
            analysis_override = overrides.get("analysis")

            if not ticker:
                raise ValueError("Missing required parameters: ticker")

            system_prompt = system_override or self._build_system_prompt(market_type, context=context, state=state)
            user_prompt = user_override or self._build_user_prompt(ticker, analysis_date, {}, state)
            analysis_prompt = analysis_override or self._build_analysis_prompt(ticker)

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            if self._llm:
                prefetched_message = None
                prefetched_tool_names: List[str] = []
                if self._langchain_tools:
                    prefetched_message, prefetched_tool_names = self._build_prefetched_tool_message(
                        ticker,
                        analysis_date,
                    )
                    if prefetched_message:
                        messages.append(prefetched_message)

                original_tools = list(self._langchain_tools)
                try:
                    if prefetched_tool_names:
                        self._langchain_tools = [
                            tool for tool in original_tools
                            if getattr(tool, "name", "") not in prefetched_tool_names
                        ]

                        # When there is prefetched data (prefetched_message has been appended to messages), enter the analysis directly.
                        # Avoid LLM calling residual tools and then saving the tool calls in JSON as a report
                        if not self._langchain_tools or prefetched_message is not None:
                            report = self._invoke_prefetched_analysis(messages, analysis_prompt)
                        else:
                            report = self.invoke_with_tools(messages, analysis_prompt=analysis_prompt)
                    elif self._langchain_tools:
                        report = self.invoke_with_tools(messages, analysis_prompt=analysis_prompt)
                    else:
                        response = self._invoke_llm_with_trace(messages)
                        report = response.content if hasattr(response, "content") else str(response)
                finally:
                    self._langchain_tools = original_tools
            else:
                raise ValueError("LLM not initialized")

            parsed = self._parse_response(report)
            clean_report = parsed.get("report") or parsed.get("content") or report
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
                result["tool_call_summaries"] = {self.analyst_type: tool_summary}
            return result

        except Exception as e:
            logger.error(f"[{self.agent_id}] Execution failed: {e}", exc_info=True)
            return {
                self.output_field: GENERIC_REPORT_FALLBACK,
                "analyst_posteriors": {
                    self.agent_id: self._get_default_posterior()
                }
            }

    def _build_system_prompt(self, market_type: str = None, context=None, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words (refer to the implementation of fundamentals_analyst_v2)
        
        Args:
            market_type: Market type (A shares/Hong Kong stocks/US stocks) (reserved to be compatible with the base class)
            context: AgentContext Object (for debug mode)
            state: Workflow status (used to extract template variables)
            
        Returns:
            System prompt word
        """
        logger.info("🔍 [NewsAnalystV2] Start building system prompt words")
        
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
        
        # Use the base class's general method to obtain prompt words from the template system (refer to research_manager_v2)
        # The base class will automatically extract system variables (such as current_price, industry, etc.) from state
        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="news_analyst_v2",
            variables=template_variables,  # Pass necessary variables
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=context or state.get("context"),  # Priority is given to using the incoming context, otherwise it is obtained from state
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        prompt = self._sanitize_template_prompt(prompt)
        
        logger.info(f"📝 System prompt word length: {len(prompt)} character")

        workflow_prompt = self._build_news_tool_workflow_prompt(
            template_variables.get("analysis_date") or template_variables.get("current_date") or ""
        )

        if prompt:
            prompt_text = prompt.rstrip()
            if self._has_two_stage_news_workflow(prompt_text):
                return prompt_text
            return f"{prompt_text}\n\n{workflow_prompt}"
        
        # Downgrade: Use default prompt word
        return f"""You are a professional financial news analyst.

    Your responsibility is to identify event clues that are meaningful to company research and judgment based on real news, announcements and regulatory information, and to distinguish short-term noise from medium-term variables.

    Analysis points:
    1. Core Event Facts - key information on recent announcements, news, and regulatory changes
    2. Event impact path - will these events affect operations, valuation expectations, industry position, or risk exposure?
    3. Timeliness and credibility - whether the event is out of date and comes from a reliable source
    4. Catalysts and risks - what factors are likely to strengthen judgment and what factors may weaken it
    5. Follow-up Watch – Disclosures, data points or validation signals that still need to be tracked

    Strict requirements:
    - Buying, selling, holding, adding or subtracting positions, target prices, price ranges, stop-loss, take-profit or position recommendations are not allowed.
    - References to real times, events and numbers returned by the tool are allowed, but may not be rewritten into execution recommendations or price triggers.

    Please use Chinese and conduct analysis based on real data.

    {workflow_prompt}"""

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        tool_data: Dict[str, Any],  # Parameters are retained for compatibility with base classes, but tool data is passed via ToolMessage
        state: Dict[str, Any]
    ) -> str:
        """
        Construct user prompt words (refer to the implementation of research_manager_v2 and fundamentals_analyst_v2)
        
        Args:
            ticker: Stock code
            analysis_date: Analysis date
            tool_data: Data returned by the tool (retained for compatibility with base class, but tool data is passed via ToolMessage)
            state: Workflow status (used to extract template variables)
            
        Returns:
            User prompt words
        """
        logger.info("🔍 [NewsAnalystV2] Start building user prompt words")
        logger.info(f"📊 Stock code: {ticker}")
        logger.info(f"📅 Analysis date: {analysis_date}")
        
        if state is None:
            state = {}
        
        # Get company name and market information
        company_name = self._get_company_name(ticker, state)
        market_name = "China A shares"
        currency_name = "RMB"
        currency_symbol = "¥"
        
        if StockUtils and ticker:
            try:
                market_info = StockUtils.get_market_info(ticker)
                market_name = market_info.get('market_name', "China A shares")
                currency_name = market_info.get('currency_name', "RMB")
                currency_symbol = market_info.get('currency_symbol', "¥")
            except Exception as e:
                logger.warning(f"Failed to obtain market information: {e}")
        
        # Prepare template variables (refer to the implementation of research_manager_v2)
        # 🔑 Key: Make sure the date is in the correct format (YYYY-MM-DD), not a datetime object
        if isinstance(analysis_date, str):
            # If it is already a string, make sure the format is correct
            if len(analysis_date) > 10:
                # If it is a datetime string (such as "2026-01-14 00:00:00") , Get only the date part
                analysis_date_str = analysis_date.split()[0]
            else:
                analysis_date_str = analysis_date
        else:
            # If it is a datetime object, convert it to a string
            from datetime import datetime
            if isinstance(analysis_date, datetime):
                analysis_date_str = analysis_date.strftime("%Y-%m-%d")
            else:
                analysis_date_str = str(analysis_date)
        
        template_variables = {
            "ticker": ticker,
            "company_name": company_name,
            "market_name": market_name,
            "analysis_date": analysis_date_str,  # 🔑 Make sure it is in string format YYYY-MM-DD
            "current_date": analysis_date_str,  # 🔑 Make sure it is in string format YYYY-MM-DD
            "start_date": "",  # Can calculate the date 1 year ago
            "currency_name": currency_name,
            "currency_symbol": currency_symbol,
            "tool_names": ", ".join([t.name for t in self._langchain_tools]) if self._langchain_tools else ""
        }
        
        # Use the general method of the base class to obtain user prompt words (refer to research_manager_v2)
        # The base class will automatically extract system variables (such as current_price, industry, etc.) from state
        # 🔑 Note: The data returned by the tool will be passed through ToolMessage and does not need to be checked in user_prompt
        
        # 🔍 Debugging: printing template variables
        logger.info(f"🔍 [NewsAnalystV2] Prepare variables to be passed to the template system:")
        for k, v in template_variables.items():
            logger.info(f"  - {k}: {v}")
        
        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="news_analyst_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context"),  # Get from state context
            fallback_prompt=None,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        prompt = self._sanitize_template_prompt(prompt)
        
        workflow_prompt = self._build_news_tool_workflow_prompt(analysis_date_str)

        if prompt:
            logger.info(f"✅ Get news analyst v2.0 user prompt words from the template system (length: {len(prompt)})")
            logger.info(f"📝 The first 500 characters of the user prompt word:\n{prompt[:500]}...")
            prompt_text = prompt.rstrip()
            if self._has_two_stage_news_workflow(prompt_text):
                return prompt_text
            return f"{prompt_text}\n\n{workflow_prompt}"
        
        # Downgrade: Use default prompt word (tool_data is no longer checked as tool data is passed via ToolMessage)
        logger.warning("⚠️ The user prompt word is not obtained from the template system, and the default prompt word is used.")
        # 🔑 Key: explicitly tell LLM in the default prompt word what date to use to call the tool
        return f"""Please check the stock {ticker} ({company_name}) Conduct detailed news event research:

**Analysis date**: {analysis_date_str}

    {workflow_prompt}

    Please call the tool to obtain news data, and then output a Chinese research report based on the real results, which at least contains:
    1. Core news and announcement facts
    2. Event impact path and timeliness judgment
    3. Main Catalysts, Main Risks and Information Gaps
    4. Follow-up observations that need to be followed up

    It is prohibited to output buying and selling recommendations, target prices, price ranges, stop-loss and take-profit, position plans or any execution instructions."""

    def _get_company_name(self, ticker: str, state: Dict[str, Any]) -> str:
        """Get company name"""
        company_name = str(
            state.get("company_name")
            or state.get("stock_name")
            or state.get("name")
            or ""
        )
        if company_name:
            return company_name
        
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

    def _build_analysis_prompt(self, ticker: str) -> str:
        """News analysis prompt words after building tool call."""
        return f"""Based on the obtained data, please generate {ticker} Professional news analysis reports, including:

    1. Latest news summary
    2. News impact analysis
    3. Market Sentiment Assessment
    4. analysis point of view

    If multiple headlines essentially describe different retellings, reprints or follow-ups of the same event, they must be combined into the same core event and may not be repeated and accumulated into multiple independent pieces of evidence.
    If the tool only provides the title, publication time, source or link, but no text details, amounts, performance values or regulatory conclusions, it can only explain the event category and research relevance based on explicit information, and is not allowed to make up the details.
    Timeliness and source credibility should be explained separately, and the certainty of the event should not be magnified just because the release time is relatively recent.
    If there is a conflict of direction between news, the point of conflict must be clearly written and why a stronger conclusion cannot be drawn.
    If the tool does not return details of an event, market feedback or subsequent progress, please write directly Tool results not provided or This link still needs to be verified , Don t complete it yourself.
    analysis `News impact analysis` When reporting, a table can be used to summarize the news, type and impact level; the type should be written as positive, cautious or neutral first, and do not write as buying point, exhaustion of bad news or trading opportunity.
    `Market Sentiment Assessment` Only explain the possible impact of news on market sentiment and its limitations. Do not directly write down changes in sentiment as conclusions on stock prices.
    `analysis point of view` The news assessment, short-term reaction expectations and the impact on the overall research conclusion must be given simultaneously; short-term reaction expectations can only write the direction and reasons for expected changes, but not stock price point predictions.
    If there are any information gaps or matters that still need to be verified, they can be explained in the corresponding paragraph in passing, without the need for a separate chapter.
    You can quote the real time, source, title, and numbers returned by the tool for factual explanations, but you must not rewrite these contents into target prices, price ranges, short-term stock price forecasts, support and resistance levels, or execution plans.
    Please use research caliber to express the meaning of the event, priority is given to Positive side  Cautious  Neutral  reinforce an expectation  increase some uncertainty  Still to be verified and other expressions, do not use major benefits  major negative  short-term catalysis  Open up room for growth  Clear buying point and other transactional terms.
    When the tool results are sufficient, the report should be kept sufficiently expanded, normally no less than 700 words.

    Do not output investment recommendations, price targets, price ranges, positions, or execution plans.
    No byline, author, analyst, date or claim information may be added."""

