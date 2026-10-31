"""
social media analyst v2.0

Social media analyst implemented based on AnalystAgent base class
"""

import logging
from typing import Dict, Any, Optional

from langchain_core.messages import SystemMessage, HumanMessage

from core.agents.analyst import AnalystAgent
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
class SocialMediaAnalystV2(AnalystAgent):
    """
    social media analyst v2.0
    
    Function:
    - Get social media sentiment data
    - Analyze investor sentiment structure and market enthusiasm
    - Identify sentiment divergences, noise and unverified signals
    
    Workflow:
    1. Call the unified sentiment tool to obtain social media data
    2. Analyzing sentiment trends using LLM
    3. Generate social media analysis reports
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("social_analyst_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15"
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="social_analyst_v2",
        name="social media analyst v2.0",
        description="Analyze social media sentiment and refine popularity changes, emotional deviations and noise risks",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=["get_stock_sentiment_unified"],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="sentiment_report", type="string", description="Social media sentiment analysis report"),
        ],
        requires_tools=True,
        output_field="sentiment_report",
        report_label=" [Social Media Analysis v2]",
        workflow_stage="analyst",
    )

    # Analyst type
    analyst_type = "social"
    
    # Output field name
    output_field = "sentiment_report"

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Override execution logic to support dedicated sentiment analysis prompt words."""
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
                if self._langchain_tools:
                    report = self.invoke_with_tools(messages, analysis_prompt=analysis_prompt)
                else:
                    response = self._invoke_llm_with_trace(messages)
                    report = response.content if hasattr(response, "content") else str(response)
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
        logger.info("🔍 [SocialAnalystV2] Start building system prompt words")
        
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
            agent_name="social_analyst_v2",
            variables=template_variables,  # Pass necessary variables
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=context or state.get("context"),  # Priority is given to using the incoming context, otherwise it is obtained from state
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        
        logger.info(f"📝 System prompt word length: {len(prompt)} character")

        if prompt:
            # 🔥 Enhanced constraint: Explicitly ask not to analyze this dimension if there is no data
            data_constraint = """

## ⚠️ Missing data handling rules (important)
**If a tool does not return data for a certain dimension, follow these rules:**
1. **Do not analyze this dimension**: If there is no specific information such as KOL opinions, retail investor sentiment, institutional positions, etc. in the data, do not include analysis of these parts in the report
2. **Or explicitly state that data is missing**: If a dimension must be mentioned, please make it clear"The data in this dimension is missing and will not be analyzed for the time being."
3. **Absolutely prohibited from fabricating**: It is strictly prohibited to make up, assume or speculate on any dimension of analysis without data.
4. **Only analyze data that actually exists**: Carefully examine the data returned by the tool and analyze only the dimensions that actually exist in the data

**Example**: If the data returned by the tool is only news sentiment analysis and no KOL data, then:
- ❌ Error: Made up"Many analysts pointed out...", "Some KOLs think..."Waiting for non-existent content
- ✅ Correct: Skip the KOL opinion summary part, or explain"KOL Data is missing, not analyzed yet"
"""
            return prompt + data_constraint
        
        # Downgrade: Use default prompt word
        return f"""You are a professional social media sentiment analyst.

    Your job will be to analyze the structure of investor sentiment, buzz, and disagreements on social media to identify which sentiment signals are worth tracking and which are just noise.

    Analysis points:
    1. Sentiment direction and intensity - is the discussion more optimistic, pessimistic, or more divisive?
    2. Sentiment source structure - what are the opinions expressed by retail investors, theme communities, KOLs or institutions?
    3. Sentiment divergence - whether sentiment changes are consistent with fundamentals and price action
    4. Noise identification - which claims lack evidence and tend to amplify short-term fluctuations
    5. Follow-up signals - sentiment changes, discussion topics, and verification events that still need to be tracked

    Strict requirements:
    - Buying, selling, holding, adding or subtracting positions, target prices, price ranges, stop-loss, take-profit or position recommendations are not allowed.
    - Quoting real sentiment indicators, buzz, and text snippets returned by the tool is allowed, but may not be rewritten into actionable conclusions.

    Please use Chinese and conduct analysis based on real data."""

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
        logger.info("🔍 [SocialAnalystV2] Start building user prompt words")
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
        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="social_analyst_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context"),  # Get from state context
            fallback_prompt=None,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        
        if prompt:
            logger.info(f"✅ Get social media analyst v2.0 user prompt words from the template system (length: {len(prompt)})")
            logger.info(f"📝 The first 500 characters of the user prompt word:\n{prompt[:500]}...")
            return prompt
        
        # Downgrade: Use default prompt word (tool_data is no longer checked as tool data is passed via ToolMessage)
        logger.warning("⚠️ The user prompt word is not obtained from the template system, and the default prompt word is used.")
        # 🔑 Key: explicitly tell LLM in the default prompt word what date to use to call the tool
        return f"""Please check the stock {ticker} ({company_name}) Conduct detailed emotion studies:

**Analysis date**: {analysis_date_str}

**Important tips**: When calling the tool get_stock_sentiment_unified, the curr_date parameter must be used, with the value:{analysis_date_str}

    Please call the tool to obtain social media data, and then output a Chinese research report based on real results, which at least contains:
    1. Sentiment direction, popularity and main discussion topics
    2. Emotional divergence, divergent views and potential sources of noise
    3. Emotional signals that may strengthen or weaken research judgments
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
        """Sentiment analysis prompt words after building tool invocation."""
        return f"""Based on the obtained data, please generate {ticker} Professional emotion research reports, including:

1. Emotional direction and heat
2. Opinion structure and channel differences
3. Emotional changes and differentiation
4. Noise and risk
5. Impact on overall research conclusions
6. Follow-up observations

If the tool results do not have a certain dimension such as KOL, retail investors, institutions, platform stratification, interaction data or high-impact news, do not analyze this dimension; if it must be mentioned, only write Tool results not provided or This dimension is not analyzed yet . 
If the tool clearly states that the current results come from news retracement sentiment summaries rather than real social media content, the text must clearly state this, and the retracement results must not be written as KOL, retail investors, institutions or community stratified conclusions.
Emotional direction, discussion intensity, platform distribution, interaction strength and high-impact messages should be expressed separately; do not write more messages, more concentrated keywords or higher interaction directly as The market is unanimously bullish  Emotions continue to rise  trend confirmation . 
If the tool only provides the current snapshot, a summary of the last 7 days, or a limited number of messages, you must not write Continue to heat up  Improvement for multiple days in a row  The mood has reversed  The market has formed unanimous expectations Wait for wording that requires longer timing verification.
If the high-impact message is inconsistent with the overall sentiment statistics, this differentiation and its limitations on the strength of the conclusion must be written.
You can quote the sentiment ratings, number of messages, platform distribution, keywords, hashtags, interaction data and high-impact messages returned by the tool to illustrate facts, but you must not rewrite these contents into target prices, price ranges, buying and selling recommendations, long and short conclusions or execution plans.
Please use research caliber to express emotional meaning, priority is given to Positive side  Cautious  Neutral  Increased differentiation  Noise is higher  Limited consistency  Worth continuing to follow and other expressions, do not use The emotional turning point has arrived  Bullish across the board  Buying sentiment heats up  Reversal immediately and other transactional terms.
`## Impact on overall research conclusions` Only explain how emotional signals strengthen, weaken, or neutrally affect the overall research judgment. Do not write emotions directly into trend conclusions.
`## Follow-up observations` You can only write sentiment directions, discussion topics, changes in platform structure, changes in interaction intensity, or cross-verification with news/fundamentals that need to be continued to be tracked, and cannot be written as transaction triggers.
When the tool results are sufficient, the report should be kept sufficiently expanded, normally no less than 700 words.

Do not output investment recommendations, price targets, price ranges, positions, or execution plans.
No byline, author, analyst, date or claim information may be added."""

