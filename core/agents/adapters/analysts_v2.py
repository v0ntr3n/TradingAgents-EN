from __future__ import annotations
import sys as _sys

# === market_analyst_v2 ===
from core.agents.analyst import AnalystAgent
from core.agents.base import GENERIC_REPORT_FALLBACK
"""
market analyst Agent v2.0

Market analyst implemented based on AnalystAgent base class
Use configuration-driven approach to support dynamic tool binding
"""

import logging
import re
from typing import Any, Dict, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from ..analyst import AnalystAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)

_MARKET_REPORT_SANITIZE_RULES = [
    (r"price range", "Fluctuation range"),
    (r"support level", "supporting relationship"),
    (r"resistance level", "stress relationship"),
    (r"key price", "key price relationships"),
    (r"risk control position", "risk observation location"),
    (r"price analysis range", "historical fluctuation range"),
    (r"Not on site yet\s*(MA\d+)", r"still below\1"),
    (r"Not yet broken through\s*(MA\d+)", r"still below\1"),
    (r"Stand again\s*(MA\d+)", r"return to\1 above"),
    (r"stand on\s*(MA\d+)", r"higher than\1"),
    (r"not yet established in\s*(MA\d+)(?:above|above)?", r"still below\1"),
    (r"Failure to effectively stand on top of it", "The relationship with this moving average still needs to be improved"),
    (r"failed to effectively stand firm on\s*(MA\d+)(?:above|above)?", r"with\1 relations still need to be improved"),
    (r"stand firm\s*(MA\d+)", r"higher than\1"),
    (r"stand firm on\s*(MA\d+)(?:above|above)?", r"higher than\1"),
    (r"Stand firm signal", "Signs of relationship improvement"),
    (r"Whether it is possible to achieve effective standing", "Is the short-term moving average relationship improving?"),
    (r"No effective breakthrough has yet been made(?:signal|support)", "There is still insufficient basis for an upward break"),
    (r"No effective breakthrough signal has been formed", "There is still insufficient basis for an upward break"),
    (r"No effective breakthrough support has been formed", "There is still insufficient basis for an upward break"),
    (r"No effective breakthrough has been formed", "There is still insufficient basis for an upward break"),
    (r"Effective breakthrough", "clear break"),
    (r"Strong breakthrough", "Obvious break"),
    (r"A breakout of key short-term moving averages", "Improvements to key short-term moving average relationships"),
    (r"Confirmation above short-term moving average", "Confirmation of improved relationship with short-term moving averages"),
    (r"Upward breakout momentum", "Basis for further strengthening"),
    (r"Has not broken through the Bollinger Band track", "Still below the Bollinger Band track"),
    (r"Breaking through the Bollinger Band track", "Above the Bollinger Band track"),
    (r"Continuously running on", "located in"),
    (r"Is the histogram(?:appear)?Continuously enlarge or shrink", "Whether kinetic energy consistency increases or decreases"),
    (r"Is the histogram(?:appear)?Keep zooming in", "Is the consistency of kinetic energy enhanced?"),
    (r"MACD If the histogram continues to zoom in", "MACD If kinetic energy further increases"),
    (r"Keep zooming in", "further enhance"),
    (r"continued contraction", "weaken further"),
    (r"Unable to maintain firm footing", "Relations still need to be improved"),
    (r"Upside is limited", "Limited short-term flexibility"),
    (r"Upside support", "Positive support"),
    (r"Upward support", "Positive support"),
    (r"Upside", "Further improve flexibility"),
    (r"It has narrowed compared with the previous period, indicating that short-term fluctuations tend to converge.", "Shows that short-term fluctuations are concentrated within the current range"),
    (r"Sort trends upwards", "strong-biased arrangement"),
    (r"No clear upward trend has formed", "Whether a clear upward direction will form in the future remains to be verified."),
    (r"Enhanced market confidence", "Provide certain technical support for research and judgment"),
]

# Try importing utility functions
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    logger.warning("Unable to import StockUtils, some functions may not be available")
    StockUtils = None

# It is no longer necessary to import get_agent_prompt directly, use the _get_prompt_from_template method of the base class


@register_agent
class MarketAnalystV2(AnalystAgent):
    """
    market analyst v2.0

    Function:
    - Analyze stock price trends
    - Analyze technical indicators
    - Analyze trading volume
    - Generate market analysis report

    Workflow:
    1. Call tools to obtain price data, technical indicators, and trading volume data
    2. Analyze data using LLM
    3. Generate market analysis report

    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent_with_dynamic_tools

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent_with_dynamic_tools("market_analyst_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15"
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="market_analyst_v2",
        name="market analyst v2.0",
        description="Analyze stock price trends, technical indicators and trading volume, and generate market analysis reports",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=[
            "get_stock_market_data_unified"
        ],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="market_report", type="string", description="Market analysis report"),
        ],
        requires_tools=True,
        output_field="market_report",
        report_label=" [Market Analysis v2]",
        workflow_stage="analyst",
    )

    # Analyst type
    analyst_type = "market"

    # Output field name
    output_field = "market_report"

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Override execution logic to support template debugging and prompt word coverage
        """
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

            system_prompt = system_override
            if not system_prompt:
                # 🔑 Extract necessary variables from state (system variables should be prepared when the workflow is created)
                template_variables = {}
                
                # base variables
                if "ticker" in state:
                    template_variables["ticker"] = state["ticker"]
                else:
                    template_variables["ticker"] = ticker
                
                # Date related
                if "analysis_date" in state or "trade_date" in state:
                    analysis_date = state.get("analysis_date") or state.get("trade_date")
                    if analysis_date:
                        if isinstance(analysis_date, str) and len(analysis_date) > 10:
                            analysis_date = analysis_date.split()[0]
                        template_variables["current_date"] = analysis_date
                        template_variables["analysis_date"] = analysis_date
                else:
                    current_date = state.get("current_date", analysis_date)
                    template_variables["current_date"] = current_date
                    template_variables["analysis_date"] = analysis_date
                    template_variables["start_date"] = state.get("start_date", current_date)
                
                # Company information (obtained from state, the workflow engine should be ready)
                template_variables["company_name"] = state.get("company_name", "")
                template_variables["market_name"] = state.get("market_name", market_type)
                template_variables["currency_name"] = state.get("currency_name", "RMB")
                template_variables["currency_symbol"] = state.get("currency_symbol", "¥")
                template_variables["tool_names"] = ", ".join([t.name for t in self._langchain_tools]) if self._langchain_tools else ""
                
                system_prompt = self._get_prompt_from_template(
                    agent_type="analysts_v2",
                    agent_name="market_analyst_v2",
                    variables=template_variables,  # Pass necessary variables
                    state=state,  # 🔑 Pass state and the base class will automatically extract system variables
                    context=context,
                    fallback_prompt=None,
                    prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
                )

            if not system_prompt:
                # 🔑 Pass state to _build_system_prompt to extract variables from state to complete the template
                system_prompt = self._build_system_prompt(market_type, context=context, state=state)

            user_prompt = user_override
            if not user_prompt:
                user_prompt = self._build_user_prompt(ticker, analysis_date, state)

            analysis_prompt = analysis_override or self._build_analysis_prompt(ticker)

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            logger.info(f"System prompt word: {system_prompt}")
            logger.info(f"User prompt words: {user_prompt}")            

            if self._llm:
                if self._langchain_tools:
                    report = self.invoke_with_tools(messages, analysis_prompt=analysis_prompt)
                else:
                    response = self._invoke_llm_with_trace(messages)
                    report = response.content if hasattr(response, 'content') else str(response)
            else:
                raise ValueError("LLM not initialized")

            report = self._sanitize_report(report)

            result = {self.output_field: report}
            # 🆕 Comes with tool call summary
            tool_summary = self._format_tool_call_summary()
            if tool_summary:
                result["tool_call_summaries"] = {self.analyst_type: tool_summary}
            return result

        except Exception as e:
            logger.error(f"[{self.agent_id}] Execution failed: {e}", exc_info=True)
            return {self.output_field: GENERIC_REPORT_FALLBACK}

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
        logger.info("🔍 [MarketAnalystV2] Start building system prompt words")
        
        if state is None:
            state = {}
        
        # Extract the necessary variables from state (if required by the system prompt word template)
        # Note: Although system prompt words usually do not require variables, some templates may require ticker, current_date, etc.
        # The base class will automatically extract system variables (such as current_price, industry, etc.) from state
        template_variables = {}
        
        # If there are ticker and analysis_date in state, extract them (the system prompt word template may be required)
        if "ticker" in state:
            template_variables["ticker"] = state["ticker"]
        if "company_name" in state:
            template_variables["company_name"] = state["company_name"]
        if "analysis_date" in state or "trade_date" in state:
            analysis_date = state.get("analysis_date") or state.get("trade_date")
            if analysis_date:
                # Make sure the date is in the correct format
                if isinstance(analysis_date, str) and len(analysis_date) > 10:
                    analysis_date = analysis_date.split()[0]
                template_variables["current_date"] = analysis_date
                template_variables["analysis_date"] = analysis_date
        if state.get("market_name"):
            template_variables["market_name"] = state["market_name"]
        if state.get("currency_name"):
            template_variables["currency_name"] = state["currency_name"]
        if state.get("currency_symbol"):
            template_variables["currency_symbol"] = state["currency_symbol"]
        if self._langchain_tools:
            template_variables["tool_names"] = ", ".join([t.name for t in self._langchain_tools])
        
        # Use the base class's general method to obtain prompt words from the template system (refer to research_manager_v2)
        # The base class will automatically extract system variables (such as current_price, industry, etc.) from state
        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="market_analyst_v2",
            variables=template_variables,  # Pass necessary variables
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=context or state.get("context"),  # Priority is given to using the incoming context, otherwise it is obtained from state
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )

        if prompt:
            return prompt

        # Default prompt word
        return f"""you are a professional{market_type}Market analyst, good at technical analysis.

Your responsibilities:
1. Analyze stock price trends (increases and decreases, trend direction)
2. Analyze technical indicators (MA, MACD, RSI, KDJ, etc.)
3. Analyze trading volume (increasing volume, shrinking volume, volume-price relationship)
4. Comprehensively judge market sentiment and trends

Analysis requirements:
- Objective, professional and data-based
- Point out key technical signals
- Give clear trend judgments
- Use Chinese output

Output format:
Please output the analysis report in a structured manner, including:
- Price trend analysis
- Technical indicator analysis
- Volume analysis
- Comprehensive judgment
"""

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        state: Dict[str, Any]
    ) -> str:
        """
        Construct user prompt words (refer to the implementation of research_manager_v2 and fundamentals_analyst_v2)

        Args:
            ticker: Stock code
            analysis_date: Analysis date
            state: Workflow status (used to extract template variables)

        Returns:
            User prompt words
        """
        logger.info("🔍 [MarketAnalystV2] Start building user prompt words")
        logger.info(f"📊 Stock code: {ticker}")
        logger.info(f"📅 Analysis date: {analysis_date}")
        
        if state is None:
            state = {}
        
        # Get company name and market information
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
                market_name = market_info.get('market_name', "China A shares")
                currency_name = market_info.get('currency_name', "RMB")
                currency_symbol = market_info.get('currency_symbol', "¥")
                market_company_name = str(market_info.get("company_name") or "").strip()
                lookup_company_name = ""
                if not market_company_name:
                    lookup_company_name = str(self._get_company_name(ticker, market_info) or "").strip()

                if market_company_name:
                    company_name = market_company_name
                elif lookup_company_name and (not company_name or company_name == ticker or company_name.isdigit()):
                    # company_name When it is empty, equal to ticker code or pure number, the real name found by DB should be used.
                    company_name = lookup_company_name
            except Exception as e:
                logger.warning(f"Failed to obtain market information: {e}")

        if not company_name:
            company_name = ticker
        if not market_name:
            market_name = "unknown market"
        
        # Prepare template variables (refer to the implementation of research_manager_v2)
        template_variables = {
            "ticker": ticker,
            "company_name": company_name,
            "market_name": market_name,
            "analysis_date": analysis_date,
            "current_date": analysis_date,
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
            agent_name="market_analyst_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context"),  # Get from state context
            fallback_prompt=None,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        
        if prompt:
            logger.info(f"✅ Obtain market analyst v2.0 user prompt words from the template system (length: {len(prompt)})")
            logger.info(f"📝 The first 500 characters of the user prompt word:\n{prompt[:500]}...")
            return prompt
        
        # Downgrade: Use default prompt word (tool_data is no longer checked as tool data is passed via ToolMessage)
        logger.warning("⚠️ The user prompt word is not obtained from the template system, and the default prompt word is used.")
        return f"""Please analyze {company_name} ({ticker}) in {analysis_date} market performance:

Stock code:{ticker}
Company name:{company_name}
Analysis date:{analysis_date}
Market type:{market_name}

Please call the tool to obtain market data and then generate a detailed market analysis report."""

    def _build_analysis_prompt(self, ticker: str) -> str:
        """Professional analysis prompt words after the build tool is called."""
        return f"""Based on the obtained data, please generate {ticker} Professional market structure research reports, including:

1. Basic stock information
2. Technical indicator analysis
    - Moving Average (MA) Analysis
    - MACD Indicator analysis
    - RSI relative strength indicator
    - Bollinger Bands (BOLL) analysis
3. Price trend analysis
    - Short term trend (5-10 trading days)
    - Medium-term trend (20-60 trading days)
    - Volume analysis
4. comprehensive assessment
5. Impact on overall research conclusions
6. Follow-up observation points

If the actual data date returned by the tool differs from the analysis date, the actual data date must be clearly stated in the text.
The actual data dates in the stock basic information can only refer to those explicitly returned by the tool. actual data date or Latest effective daily date ; If the analysis date is today but the tool shows that the latest valid daily line is still an earlier date, it is prohibited to write the analysis date directly as the actual data date.
If a price, indicator or transaction field is missing, please write directly Tool results not provided or This dimension still needs to be verified , Don t complete it yourself.
If short-term and medium-term signals conflict, the point of conflict must be clearly written and why a stronger conclusion cannot be drawn.
The basic stock information part must state the company name, stock code, market, actual data date, current price, increase or decrease, and trading volume.
The technical indicator analysis part should try to fully cover the content returned by the tools in MA, MACD, RSI, and BOLL. Do not just write a general summary.
The price trend analysis part should cover short-term trends, medium-term trends and trading volume analysis, and retain factual data such as high and low points, average prices or changes in price center of the last 5 days.
If the tool only provides current values, statistics for the last 5 days, or a single snapshot, you must not write Keep zooming in  continue to expand  Multiple consecutive trading days  always run on  stand firm  Effective breakthrough  Fall below Wait for wording that requires longer timing verification.
The moving average arrangement relationship and the moving average slope direction should be expressed separately; if there is no longer historical sequence, do not MA20 higher than MA60 written directly as MA60 run upward or The medium-term trend has reversed . 
If the tool results include Moving average direction conclusion (deterministic calculation on tool end) , This conclusion must be quoted directly, and do not calculate the MA slope or turning head twice by yourself.
If tool results include MACHINE_READABLE_MA_CONCLUSIONS For field blocks, priority should be given to directly quoting the direction and turning conclusions of MA5/MA10/MA20/MA60 according to this field block, and do not deduce it from the original price.
If tool results include MACHINE_READABLE_MACD_CONCLUSIONS Field blocks, which should be referenced first `macd.cross_signal`, `macd.dif_dea_relation`, `macd.hist_trend`, Don t judge the golden cross/dead cross by yourself.
Anyone who writes about prices, moving averages or the size patterns of high and low points in the last 5 days must first check them against the real values given by the tool; subsequent text must be consistent with the table and values. If you cannot ensure that the complete sorting is correct, just write the item-by-item above/below relationship, and do not force a chain arrangement.
Comparative formulas that are opposite to the real values must not be written; for example, when MA20 is higher than MA60, it cannot be written as MA60 higher than MA20 . 
It can only be used if the tool clearly provides the corresponding relationship between price and indicator turning points or directly identifies the results. departure one word; otherwise rewrite as signal differentiation or No consensus has been verified yet . 
You can write the historical fluctuation range formed by the historical highs and lows of the last 5 days, but you are not allowed to write the future price analysis range, key trigger range or execution threshold.
If the tool only provides the highest price, lowest price, average price or current price and moving average position in the last 5 days, you can only write The highest price is  touch  located in  above/below  close and other facts, shall not be rewritten as brief breakthrough  regain a foothold  Continuously running on Confirmatory wording.
If the tool does not directly return daily crossing or threshold verification facts, do not write once had a breakthrough MA5  Unable to maintain firm footing  Effectively stabilize key short-term moving averages and other procedural expressions; rewritten as the relative relationship between the current price and the moving average and matters that still need to be verified.
As long as the relative relationship between price and moving averages, Bollinger Bands or historical ranges is described, it is preferred to use above/below  located in  close  In the upper middle of the range  Relations still need to be improved and other expressions, do not use stand on  stand firm  Strong breakthrough  Effective breakthrough  Continuously running on  Keep zooming in  Upside This kind of threshold or spatialized wording.
It is allowed to quote real numerical values for factual explanations, but do not write the numerical values as investment ratings, target prices, price analysis ranges, support and resistance levels, key execution levels, risk control levels or trading trigger conditions.
Please use research methods to explain trends, structures, momentum and volume-price relationships, and do not Breakthrough, fall below, stand firm, fall, step back to confirm, heavy volume breakthrough Write an execution plan.
`comprehensive assessment` Only summarize the technical status, main strong and weak signals and conflict points, do not repeat the previous indicator explanations paragraph by paragraph;`Impact on overall research conclusions` Simply describe how these signals strengthen, weaken, or neutralize the overall study and avoid restating the entire set of indicators.
Do not write follow-up observation points as Is it standing firmly above MA5?  Whether it continues to operate above MA10 and MA20  Divergence if price reaches new highs Wait for the threshold sentence; rewrite it as a reviewable direction such as whether the relationship is improved, whether the volume and price continue to be consistent, whether the synchronization of indicators is enhanced or weakened, etc.
Even if it is a negative sentence, do not write it No effective breakthrough has been formed  Not firmly above MA5  MACD The histogram does not continue to zoom in ; rewritten as There is still insufficient evidence to break through  The relationship between price and MA5 still needs to be improved  MACD Currently positive but continuity remains to be verified . 
Do not write the main text or subsequent observation points. Not yet firmly above MA5  Failure to effectively stabilize key short-term moving averages  Whether it is possible to achieve effective standing  Does the histogram appear to be continuously enlarged? ; rewritten as Price is below MA5, short-term moving average relationship still needs to be improved  MACD Currently positive, but momentum consistency remains to be verified . 
If the price is in the middle and upper part of the Bollinger Bands or higher than some moving averages, it can only explain the current position relationship, do not write There is some room for upside  There s still room above or other spatial judgments.
A word-by-word self-check must be done before output: it must not appear in the final report stand on  stand firm  Effective breakthrough  Strong breakthrough  Continuously running on  Keep zooming in  Breaking through the Bollinger Band track  Upside If these original words appear, they must all be rewritten before outputting.
When the tool results are sufficient, the report should be kept sufficiently expanded, normally no less than 800 words.

Do not output trading recommendations, price targets, price ranges, positions, or execution plans.
No byline, author, analyst, date or claim information may be added."""

    def _sanitize_report(self, report: str) -> str:
        if not isinstance(report, str) or not report:
            return report

        sanitized = report
        for pattern, replacement in _MARKET_REPORT_SANITIZE_RULES:
            sanitized = re.sub(pattern, replacement, sanitized)

        if sanitized != report:
            logger.info("[market_analyst_v2] Report has been sanitized for compliance")

        return sanitized

    def _get_company_name(self, ticker: str, market_info: dict) -> str:
        """
        Get company name

        Args:
            ticker: Stock code
            market_info: market information

        Returns:
            Company name
        """
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

# === fundamentals_analyst_v2 ===
"""
Fundamental Analyst Agent v2.0

Implementation of plug-in architecture based on BaseAgent
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

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
class FundamentalsAnalystAgentV2(BaseAgent):
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
            result = {"fundamentals_report": analysis}
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
            logger.info("✅ Obtain fundamental analyst v2.0 system prompt words from the template system")
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


# === news_analyst_v2 ===
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

            result = {self.output_field: report}
            # 🆕 Comes with tool call summary
            tool_summary = self._format_tool_call_summary()
            if tool_summary:
                result["tool_call_summaries"] = {self.analyst_type: tool_summary}
            return result

        except Exception as e:
            logger.error(f"[{self.agent_id}] Execution failed: {e}", exc_info=True)
            return {self.output_field: GENERIC_REPORT_FALLBACK}

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
        logger.info("🔍 [NewsAnalystV2] Prepare variables to be passed to the template system:")
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


# === social_analyst_v2 ===
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

            result = {self.output_field: report}
            # 🆕 Comes with tool call summary
            tool_summary = self._format_tool_call_summary()
            if tool_summary:
                result["tool_call_summaries"] = {self.analyst_type: tool_summary}
            return result

        except Exception as e:
            logger.error(f"[{self.agent_id}] Execution failed: {e}", exc_info=True)
            return {self.output_field: GENERIC_REPORT_FALLBACK}

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
        return """You are a professional social media sentiment analyst.

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


# === sector_analyst_v2 ===
"""
Sector Analyst v2.0

Sector analyst implemented based on AnalystAgent base class
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

from core.agents.analyst import AnalystAgent
from core.agents.config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from core.agents.registry import register_agent
from core.agents.utils.data_source_mode import resolve_market_data_mode

logger = logging.getLogger(__name__)

# ==================== Cache configuration (deprecated) ====================
# ⚠️ Industry reports do not support caching: industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
# Therefore, the following cache-related functions are deprecated and no longer used
SECTOR_REPORT_CACHE_TTL_HOURS = 1  # Sector analysis report cache validity period (hours) - obsolete and no longer used


def _get_cache_manager():
    """Get cache manager (lazy loading to avoid circular imports)"""
    try:
        from tradingagents.dataflows.cache import get_cache
        return get_cache()
    except Exception as e:
        logger.warning(f"⚠️ Unable to get cache manager: {e}")
        return None


def _get_sector_name(ticker: str) -> Optional[str]:
    """
    Get the name of the sector to which the stock belongs

    Args:
        ticker: Stock code

    Returns:
        Section name, returned if acquisition fails None
    """
    try:
        from tradingagents.utils.stock_utils import StockUtils
        market_info = StockUtils.get_market_info(ticker)
        if market_info.get('is_china'):
            from tradingagents.dataflows.interface import get_china_stock_info_unified
            stock_info = get_china_stock_info_unified(ticker)
            # Try to extract industry information
            if "Industry:" in stock_info:
                return stock_info.split("Industry:")[1].split("\n")[0].strip()
            elif "Industry:" in stock_info:
                return stock_info.split("Industry:")[1].split("\n")[0].strip()
    except Exception as e:
        logger.debug(f"Failed to get section name: {e}")
    return None


def _get_cached_sector_report(ticker: str, trade_date: str) -> Optional[str]:
    """
    ⚠️ Deprecated: Industry reports do not support caching
    Industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
    """
    """
    Get sector analysis report from cache

    Args:
        ticker: Stock code (used to determine the sector it belongs to)
        trade_date: transaction date

    Returns:
        The cached report content, returned if there is no hit None
    """
    cache = _get_cache_manager()
    if not cache:
        return None

    try:
        # Get the sector to which the stock belongs as a cache key
        sector_name = _get_sector_name(ticker)
        if not sector_name:
            # If the sector name cannot be obtained, use the stock code
            sector_name = ticker

        # Use sector_{Section name} as symbol
        cache_symbol = f"sector_{sector_name}"

        # 🔑 Make sure max_age_hours is an integer
        max_age_hours = int(SECTOR_REPORT_CACHE_TTL_HOURS) if SECTOR_REPORT_CACHE_TTL_HOURS else 1
        
        cache_key = cache.find_cached_analysis_report(
            report_type="sector_report",
            symbol=cache_symbol,
            trade_date=trade_date,
            max_age_hours=max_age_hours
        )
        if cache_key:
            report = cache.load_analysis_report(cache_key)
            if report and len(report) > 100:
                logger.info(f"📦 [Sector Analyst v2] hit cache: {sector_name} @ {trade_date}")
                return report
    except Exception as e:
        logger.warning(f"⚠️ Failed to read section analysis cache: {e}")

    return None


def _save_sector_report_to_cache(ticker: str, trade_date: str, report: str) -> bool:
    """
    ⚠️ Deprecated: Industry reports do not support caching
    Industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
    """
    """
    Save sector analysis report to cache

    Args:
        ticker: Stock code
        trade_date: transaction date
        report: Report content

    Returns:
        Is the save successful?
    """
    cache = _get_cache_manager()
    if not cache:
        return False

    try:
        # Get the sector to which the stock belongs as a cache key
        sector_name = _get_sector_name(ticker)
        if not sector_name:
            sector_name = ticker

        cache_symbol = f"sector_{sector_name}"

        # 🔍 Debug log: record cache parameters
        logger.debug(f"💾 [Sector Analyst v2] Prepare cache: symbol={cache_symbol}, trade_date={trade_date}, "
                     f"trade_date_type={type(trade_date).__name__}, report_len={len(report)}")

        cache.save_analysis_report(
            report_type="sector_report",
            report_data=report,
            symbol=cache_symbol,
            trade_date=trade_date
        )
        logger.info(f"💾 [Sector Analyst v2] Report cached: {sector_name} @ {trade_date} ({SECTOR_REPORT_CACHE_TTL_HOURS}Valid for hours)")
        return True
    except Exception as e:
        # 🔍 Enhanced error log: record the complete stack
        import traceback
        logger.warning(f"⚠️ Failed to save section analysis cache: {e}\n parameters: ticker={ticker}, trade_date={trade_date}, "
                       f"trade_date_type={type(trade_date).__name__}\n stack: {traceback.format_exc()}")
        return False


# Try importing stock tools
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    logger.warning("Unable to import StockUtils, some functions may not be available")
    StockUtils = None


@register_agent
class SectorAnalystV2(AnalystAgent):
    """
    Sector Analyst v2.0
    
    Function:
    - Analyze industry trends and sector rotations
    - Assess peer comparisons and competitive landscape
    - Analyze the flow of funds
    
    Workflow:
    1. Call the sector data tool to obtain industry data
    2. Use LLM to analyze sector trends
    3. Generate sector analysis report
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("sector_analyst_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15"
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="sector_analyst_v2",
        name="Sector Analyst v2.0",
        description="Analyze industry trends, sector rotation and peer comparison, and refine structural changes and risk sources",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=["get_sector_analysis"],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="sector_report", type="string", description="Sector analysis report"),
        ],
        requires_tools=True,
        output_field="sector_report",
        report_label=" [Sector analysis v2]",
        workflow_stage="analyst",
        growth_role="extractor",
        growth_outputs=["sector_report"],
        memory_scope_hint="object_tracking",
        review_level="auto_pending",
        growth_source_type="analysis_report",
    )

    # Analyst type
    analyst_type = "sector"

    # Output field name
    output_field = "sector_report"

    def _get_tool_ids_for_mode(self, mode: str) -> list[str]:
        return ["get_sector_analysis"]

    def _prepare_analysis_mode(self, state: Dict[str, Any]) -> str:
        mode = resolve_market_data_mode(state)
        state["_analysis_data_source"] = mode
        state["analysis_method"] = "qmt_sector_structure" if mode == "qmt" else "tushare_sector_full"
        self._load_tools_v2(self._get_tool_ids_for_mode(mode))
        return mode

    def _apply_mode_prompt_suffix(self, prompt: str, mode: str, prompt_type: str) -> str:
        if mode != "qmt":
            return prompt

        suffix = """

## QMT Schema constraints
The current analysis data source is QMT, please follow the following requirements:
1. Focus on analyzing the industry s internal strength, leading role, diffusion and transaction activity.
2. Do not require or assume the existence of Tushare exclusive statistics such as net capital inflows in the flush sector, official rankings in the concept sector, etc.
3. If the industry classification is from the local stock_basic_info, this must be explicitly stated Industry mapping comes from local and market trends come from QMT . 
4. Prioritize using get_sector_analysis to obtain complete sector structure analysis data.
"""
        if prompt_type == "user":
            suffix += "\n5. The report should highlight the strength of the structure and the spread of leaders, and should not express proxy indicators as official sector capital flows.\n"
        return f"{prompt}{suffix}"

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform sector analysis (with caching)

        The analysis results of the same section will be cached for 1 hour to avoid repeated analysis.
        Skip caching in debug mode and generate new reports directly.

        Args:
            state: Workflow status dictionary

        Returns:
            The updated status dictionary contains sector_report
        """
        analysis_mode = self._prepare_analysis_mode(state)

        # Extract parameters
        ticker = state.get("ticker") or state.get("company_of_interest")
        if not ticker and "trade_info" in state:
            trade_info = state.get("trade_info", {})
            if isinstance(trade_info, dict):
                ticker = trade_info.get("code")

        # Get analysis date
        raw_date = (
            state.get("analysis_date") or
            state.get("trade_date") or
            state.get("end_date") or
            datetime.now()
        )
        # Make sure it is in string format YYYY-MM-DD
        if hasattr(raw_date, 'strftime'):
            analysis_date = raw_date.strftime("%Y-%m-%d")
        else:
            # may be "2026-01-14 00:00:00" or "2026-01-14T00:00:00"
            analysis_date = str(raw_date).split()[0].split('T')[0]

        # 🔥 Check if it is in debug mode
        is_debug_mode = False
        context = state.get("context") or state.get("agent_context")
        if context:
            if hasattr(context, 'is_debug_mode'):
                is_debug_mode = context.is_debug_mode
            elif isinstance(context, dict):
                is_debug_mode = context.get('is_debug_mode', False)

        # 🔥 Prevent infinite loops: Check whether a report has been generated (also check in debug mode)
        existing_report = state.get("sector_report", "")
        if existing_report and len(existing_report) > 100:
            logger.info(f"🏭 [Sector Analyst v2] Report already exists ({len(existing_report)} character), Skip duplicate analysis")
            return {}

        # ⚠️ Industry reports do not support caching: industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
        # Therefore, each analysis must be regenerated and caching cannot be used (caching is also skipped in debug mode)
        logger.info("🏭 [Sector Analyst v2] Skip the cache check (industry reports do not support caching) and directly generate a new report")

        logger.info(f"🏭 [Sector Analyst v2] Start analysis {ticker} @ {analysis_date}, mode={analysis_mode}")

        # Call the execute method of the parent class to perform the actual analysis
        result = super().execute(state)

        # ⚠️ Industry reports do not support caching: industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
        # Therefore, it is not saved to cache

        return result

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
        logger.info("🔍 [SectorAnalystV2] Start building system prompt words")
        
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
            agent_name="sector_analyst_v2",
            variables=template_variables,  # Pass necessary variables
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=context or state.get("context"),  # Priority is given to using the incoming context, otherwise it is obtained from state
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        mode = state.get("_analysis_data_source", "tushare")
        prompt = self._apply_mode_prompt_suffix(prompt, mode, "system")
        
        logger.info(f"📝 System prompt word length: {len(prompt)} character")

        if prompt:
            return prompt

        # Downgrade: Use default prompt word (contains tool information)
        mode = state.get("_analysis_data_source", "tushare")
        if mode == "qmt":
            return f"""you are a professional{market_type}Sector/Industry Analyst.

## Your responsibilities
Based on the QMT market and local industry mapping, the industry s internal strength, leadership, diffusion and activity changes are analyzed.

## Available tools
You can call the following tools to obtain real sector data:
{tool_descriptions}

## ⚠️ Important rules
1. Tools must be called and do not invent fund flows in the Flush sector or official concept sector rankings.
2. The conclusion must clearly state which ones come from QMT quotes and which ones come from local industry mapping.
3. Focus on the analysis of leading, diffusion, structural stratification and transaction activity.

## Output format
Please use Chinese to output the structured report, and clarify the difference between proxy indicators and official statistical calibers."""

        return f"""you are a professional{market_type}Sector/Industry Analyst.

## Your responsibilities
Analyze the overall trend of the industry to which the stock belongs, sector rotation, and comparative analysis with peers.

## Available tools
You can call the following tools to obtain industry and sector data:
{tool_descriptions}

## ⚠️ Important rules
1. **Tools must be called**: Before analysis, relevant tools must be called to obtain real data.
2. **Based on data analysis**: All conclusions must be based on real data returned by the tool, do not make up data
3. **Focus on industry perspectives**: Analyze from an industry/sector perspective rather than a single stock

## Analysis points
1. Overall trends and trends in the industry
2. The relative strength of a sector in the market
3. Performance comparison of major companies in the industry
4. Sector capital flows and changes in popularity
5. Industry policies and event impact

## Output format
Please write the analysis report in Chinese with clear structure, accurate data and clear conclusions."""

    def _get_tool_descriptions(self) -> str:
        """Get tool description information"""
        if not self._langchain_tools:
            return " (No tools available)"

        descriptions = []
        for tool in self._langchain_tools:
            name = getattr(tool, 'name', 'unknown')
            desc = getattr(tool, 'description', 'No description')
            # Extract the first 100 characters of the description
            if len(desc) > 100:
                desc = desc[:100] + "..."
            descriptions.append(f"- **{name}**: {desc}")

        return "\n".join(descriptions)

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
        logger.info("🔍 [SectorAnalystV2] Start building user prompt words")
        logger.info(f"📊 Stock code: {ticker}")
        logger.info(f"📅 Analysis date: {analysis_date}")
        
        if state is None:
            state = {}
        
        # Get company name and market information
        company_name = self._get_company_name(ticker, state)
        market_type = state.get("market_type", "A shares")
        market_name = market_type
        currency_name = "RMB"
        currency_symbol = "¥"
        
        if StockUtils and ticker:
            try:
                market_info = StockUtils.get_market_info(ticker)
                market_name = market_info.get('market_name', market_type)
                currency_name = market_info.get('currency_name', "RMB")
                currency_symbol = market_info.get('currency_symbol', "¥")
            except Exception as e:
                logger.warning(f"Failed to obtain market information: {e}")
        
        # Prepare template variables (refer to the implementation of research_manager_v2)
        template_variables = {
            "ticker": ticker,
            "company_name": company_name,
            "market_name": market_name,
            "market_type": market_type,
            "analysis_date": analysis_date,
            "current_date": analysis_date,
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
            agent_name="sector_analyst_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context"),  # Get from state context
            fallback_prompt=None,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        mode = state.get("_analysis_data_source", "tushare")
        prompt = self._apply_mode_prompt_suffix(prompt, mode, "user")
        
        if prompt:
            logger.info(f"✅ Get sector analyst v2.0 user prompt words from the template system (length: {len(prompt)})")
            logger.info(f"📝 The first 500 characters of the user prompt word:\n{prompt[:500]}...")
            return prompt
        
        # Downgrade: Use default prompt word (tool_data is no longer checked as tool data is passed via ToolMessage)
        logger.warning("⚠️ The user prompt word is not obtained from the template system, and the default prompt word is used.")
        # 🔑 Key: clearly tell LLM in the default prompt word what parameters to use to call the tool
        if mode == "qmt":
            return f"""## Analysis tasks

    please **{ticker} ({company_name}) ** Conduct research and analysis on the industry/sector to which it belongs.

    **Analysis date**: {analysis_date}
    **Stock code**: {ticker}
    **market**: {market_type}
    **data source schema**: QMT

    **Important tips**: When calling the tool, the following parameters must be used:
    - get_sector_analysis: ticker='{ticker}', trade_date='{analysis_date}', lookback_days=20, top_n=10

    **The above parameter values must be used**, Do not make up sector capital flows, concept rankings, or official sector index statistics.

    Please output a Chinese research report based on QMT market and industry internal structure data, at least including:
    1. Industry/segment status and structural characteristics
    2. Tap strength, spread and activity
    3. Main supporting factors, main risks and data gaps
    4. Follow-up observations

    It is prohibited to output allocation value judgments, hedging arrangements, position allocations, buying and selling recommendations, target prices, price ranges or any execution instructions."""

        return f"""## Analysis tasks

    please **{ticker} ({company_name}) ** Conduct research and analysis on the industry/sector to which it belongs.

    **Analysis date**: {analysis_date}
    **Stock code**: {ticker}
    **market**: {market_type}

    **Important tips**: When calling the tool, the following parameters must be used:
    - get_sector_analysis: ticker='{ticker}', trade_date='{analysis_date}', lookback_days=20, top_n=10

    **The above parameter values must be used**, Do not use other stock symbols or dates.

    Please call the tool to obtain sector data, and then output a Chinese research report based on the real results, which at least contains:
    1. Industry/segment status and structural characteristics
    2. Clues about sector strength, funding or relative performance
    3. Main supporting factors, main risks and data gaps related to individual stock research
    4. Follow-up observations

    It is prohibited to output allocation value judgments, hedging arrangements, position allocations, buying and selling recommendations, target prices, price ranges or any execution instructions."""

    def _get_tool_suggestions(self) -> str:
        """Generate tool call suggestions"""
        if not self.tool_names:
            return " (No tools available, please analyze based on existing knowledge)"

        suggestions = ["Please call the following tools according to your analysis needs:"]

        # Give calling suggestions based on tool name
        tool_hints = {
            "get_sector_analysis": "Automatically obtain complete industry analysis data based on current data sources",
        }

        for tool_name in self.tool_names:
            hint = tool_hints.get(tool_name, "Get relevant data")
            suggestions.append(f"- `{tool_name}`: {hint}")

        return "\n".join(suggestions)

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


# === index_analyst_v2 ===
"""
Market Analyst v2.0

Market analyst implemented based on AnalystAgent base class
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from core.agents.analyst import AnalystAgent
from core.agents.config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from core.agents.registry import register_agent
from core.agents.utils.data_source_mode import resolve_market_data_mode

logger = logging.getLogger(__name__)

# ==================== Cache configuration ====================
INDEX_REPORT_CACHE_TTL_HOURS = 1  # Market analysis report cache validity period (hours)


def _get_cache_manager():
    """Get cache manager (lazy loading to avoid circular imports)"""
    try:
        from tradingagents.dataflows.cache import get_cache
        return get_cache()
    except Exception as e:
        logger.warning(f"⚠️ Unable to get cache manager: {e}")
        return None


def _get_cached_index_report(trade_date: str) -> Optional[str]:
    """
    Get market analysis report from cache

    Args:
        trade_date: transaction date

    Returns:
        The cached report content, returned if there is no hit None
    """
    cache = _get_cache_manager()
    if not cache:
        return None

    try:
        # Market analysis does not rely on specific stocks, using "market_v2" as symbol distinction v1.x
        # 🔑 Make sure max_age_hours is an integer
        max_age_hours = int(INDEX_REPORT_CACHE_TTL_HOURS) if INDEX_REPORT_CACHE_TTL_HOURS else 1
        
        cache_key = cache.find_cached_analysis_report(
            report_type="index_report",
            symbol="market_v2",
            trade_date=trade_date,
            max_age_hours=max_age_hours
        )
        if cache_key:
            report = cache.load_analysis_report(cache_key)
            if report and len(report) > 100:
                logger.info(f"📦 [Market Analyst v2] hit cache: @ {trade_date}")
                return report
    except Exception as e:
        logger.warning(f"⚠️ Failed to read large disk analysis cache: {e}")

    return None


def _save_index_report_to_cache(trade_date: str, report: str) -> bool:
    """
    Save market analysis report to cache

    Args:
        trade_date: transaction date
        report: Report content

    Returns:
        Is the save successful?
    """
    cache = _get_cache_manager()
    if not cache:
        return False

    try:
        # 🔍 Debug log: record cache parameters
        logger.debug(f"💾 [Market Analyst v2] Prepare cache: trade_date={trade_date}, "
                     f"trade_date_type={type(trade_date).__name__}, report_len={len(report)}")

        cache.save_analysis_report(
            report_type="index_report",
            report_data=report,
            symbol="market_v2",
            trade_date=trade_date
        )
        logger.info(f"💾 [Market Analyst v2] Report cached: @ {trade_date} ({INDEX_REPORT_CACHE_TTL_HOURS}Valid for hours)")
        return True
    except Exception as e:
        # 🔍 Enhanced error log: record the complete stack
        import traceback
        logger.warning(f"⚠️ Failed to save disk analysis cache: {e}\n parameters: trade_date={trade_date}, "
                       f"trade_date_type={type(trade_date).__name__}\n stack: {traceback.format_exc()}")
        return False

# Try importing stock tools
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    logger.warning("Unable to import StockUtils, some functions may not be available")
    StockUtils = None


@register_agent
class IndexAnalystV2(AnalystAgent):
    """
    Market Analyst v2.0
    
    Function:
    - Analyze market index trends
    - Assess the overall market environment
    - Analyze market risks and opportunities
    
    Workflow:
    1. Call the index data tool to obtain market data
    2. Use LLM to analyze market trends
    3. Generate market analysis report
    
    Example:
        from langchain_openai import ChatOpenAI
        from core.agents import create_agent

        llm = ChatOpenAI(model="gpt-4")
        agent = create_agent("index_analyst_v2", llm)

        result = agent.execute({
            "ticker": "AAPL",
            "analysis_date": "2024-12-15"
        })
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="index_analyst_v2",
        name="Market Analyst v2.0",
        description="Analyze market index trends and market environment, and refine systemic risks and key observation signals",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        default_tools=["get_market_analysis"],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="index_report", type="string", description="Market analysis report"),
        ],
        requires_tools=True,
        output_field="index_report",
        report_label=" [Market analysis v2]",
        workflow_stage="analyst",
        growth_role="extractor",
        growth_outputs=["index_report"],
        memory_scope_hint="object_tracking",
        review_level="auto_pending",
        growth_source_type="analysis_report",
    )

    # Analyst type
    analyst_type = "index"

    # Output field name
    output_field = "index_report"

    # Tool list (consistent with the tools listed in the prompt word template, common to all data source modes)
    _TOOL_IDS = [
        "get_china_market_overview",
        "get_index_data",
        "get_market_breadth",
        "get_market_environment",
        "identify_market_cycle",
        "get_north_flow",
        "get_margin_trading",
        "get_limit_stats",
        "get_index_technical",
        "get_market_analysis",
    ]

    def _get_tool_ids_for_mode(self, mode: str) -> list[str]:
        return self._TOOL_IDS

    def _prepare_analysis_mode(self, state: Dict[str, Any]) -> str:
        mode = resolve_market_data_mode(state)
        state["_analysis_data_source"] = mode
        state["analysis_method"] = "qmt_market_structure" if mode == "qmt" else "tushare_market_full"
        self._load_tools_v2(self._get_tool_ids_for_mode(mode))
        return mode

    def _apply_mode_prompt_suffix(self, prompt: str, mode: str, prompt_type: str) -> str:
        if mode != "qmt":
            return prompt

        suffix = """

## QMT Schema constraints
The current analysis data source is QMT, please follow the following requirements:
1. Prioritize calling get_market_analysis to obtain complete market analysis data of QMT market caliber.
2. For dimensions such as northbound funds, margin financing balance, and price limit statistics, you can call corresponding tools to obtain Tushare data as a supplement.
3. If there is no official statistical caliber, it must be clearly stated that the current conclusion is based on QMT market caliber and snapshot proxy indicators.
4. The report should highlight the trading disk perspective and do not express QMT proxy indicators as Tushare official statistics.
"""
        return f"{prompt}{suffix}"

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform broad market analysis (with caching)

        The market analysis results will be cached for 1 hour to avoid repeated analysis.
        Skip caching in debug mode and generate new reports directly.

        Args:
            state: Workflow status dictionary

        Returns:
            The updated status dictionary contains index_report
        """
        analysis_mode = self._prepare_analysis_mode(state)

        # Extract analysis date
        raw_date = (
            state.get("analysis_date") or
            state.get("trade_date") or
            state.get("end_date") or
            datetime.now()
        )
        # Make sure it is in string format YYYY-MM-DD
        if hasattr(raw_date, 'strftime'):
            analysis_date = raw_date.strftime("%Y-%m-%d")
        else:
            # may be "2026-01-14 00:00:00" or "2026-01-14T00:00:00"
            analysis_date = str(raw_date).split()[0].split('T')[0]

        # 🔥 Check if it is debug mode or skip cache
        is_debug_mode = False
        skip_cache = state.get("skip_cache", False)  # 🆕 Support explicit cache skipping
        context = state.get("context") or state.get("agent_context")

        # 🔍 Debugging: print context information
        logger.info(f"🔍 [Market Analyst v2] state keys: {list(state.keys())}")
        logger.info(f"🔍 [Market Analyst v2] skip_cache from state: {skip_cache}")
        logger.info(f"🔍 [Market Analyst v2] context={context}, type={type(context)}")

        if context:
            if hasattr(context, 'is_debug_mode'):
                is_debug_mode = context.is_debug_mode
                logger.info(f"🔍 [Market Analyst v2] is_debug_mode from context (object): {is_debug_mode}")
            elif isinstance(context, dict):
                is_debug_mode = context.get('is_debug_mode', False)
                logger.info(f"🔍 [Market Analyst v2] is_debug_mode from context (dict): {is_debug_mode}")

        # 🔥 Prevent infinite loops: Check whether a report has been generated (also check in debug mode)
        existing_report = state.get("index_report", "")
        if existing_report and len(existing_report) > 100:
            logger.info(f"🌐 [Market Analyst v2] Report already exists ({len(existing_report)} character), Skip duplicate analysis")
            return {}

        # 📦 Check cache: skip cache in debug mode or skip_cache
        if is_debug_mode or skip_cache:
            logger.info(f"🔧 [Market Analyst v2] Skip cache (debug={is_debug_mode}, skip_cache={skip_cache})")
        else:
            cached_report = _get_cached_index_report(analysis_date)
            if cached_report:
                logger.info(f"🌐 [Market Analyst v2] Use cached reports ({len(cached_report)} character)")
                return {
                    "index_report": cached_report,
                }

        logger.info(f"🌐 [Market Analyst v2] Start analysis @ {analysis_date}, mode={analysis_mode}")

        # Call the execute method of the parent class to perform the actual analysis
        result = super().execute(state)

        # 💾 Save to cache
        report = result.get("index_report", "")
        if report and isinstance(report, str) and len(report) > 100:
            _save_index_report_to_cache(analysis_date, report)

        return result

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
        logger.info("🔍 [IndexAnalystV2] Start building system prompt words")
        
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
            agent_name="index_analyst_v2",
            variables=template_variables,  # Pass necessary variables
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=context or state.get("context"),  # Priority is given to using the incoming context, otherwise it is obtained from state
            fallback_prompt=None,
            prompt_type="system"  # 🔑 Key: Explicitly specify the acquisition system prompt word
        )
        mode = state.get("_analysis_data_source", "tushare")
        prompt = self._apply_mode_prompt_suffix(prompt, mode, "system")
        
        logger.info(f"📝 System prompt word length: {len(prompt)} character")

        if prompt:
            return prompt

        # Downgrade: Use default prompt word (contains tool information)
        mode = state.get("_analysis_data_source", "tushare")
        if mode == "qmt":
            return f"""you are a professional{market_type}Market analyst.

    ## Your responsibilities
    Based on QMT market caliber analysis of index trends, market diffusion, activity and style switching, it provides disk-level background judgment for trading decisions.

    ## Available tools
    You can call the following tools to obtain real market data:
    {tool_descriptions}

    ## ⚠️ Important rules
    1. Tools must be called and do not invent data such as northbound funds, margin financing, official statistics on price limits, etc. that QMT does not provide.
    2. Conclusions must be clearly labeled as QMT Quotation caliber or Snapshot Agent Metrics . 
    3. Focus on trend, diffusion, activity, large and small cap/growth style switching analysis.

    ## Output format
    Please use Chinese to output the structured report and make it clear which judgments are based on proxy indicators."""

        return f"""you are a professional{market_type}Market analyst.

## Your responsibilities
Analyze market index trends, assess the overall market environment, and provide macro background analysis for investment decisions.

## Available tools
You can call the following tools to get real-time market data:
{tool_descriptions}

## ⚠️ Important rules
1. **Tools must be called**: Before analysis, relevant tools must be called to obtain real data.
2. **Based on data analysis**: All conclusions must be based on real data returned by the tool, do not make up data
3. **multidimensional analysis**: Try to use multiple tools to analyze the market status from different dimensions

## Analysis points
1. Market index movements and trends (Shanghai Stock Exchange, Shenzhen Stock Exchange, GEM, etc.)
2. Market technical analysis (MACD, RSI, KDJ and other technical indicators)
3. Fund flow analysis (northbound funds, balance of financing and financing)
4. Market sentiment and risk appetite (price limit statistics, market width)
5. Market cycle judgment (bull and bear phases, valuation levels)

## Output format
Please write the analysis report in Chinese with clear structure, accurate data and clear conclusions."""

    def _get_tool_descriptions(self) -> str:
        """Get tool description information"""
        if not self._langchain_tools:
            return " (No tools available)"

        descriptions = []
        for tool in self._langchain_tools:
            name = getattr(tool, 'name', 'unknown')
            desc = getattr(tool, 'description', 'No description')
            # Extract the first 100 characters of the description
            if len(desc) > 100:
                desc = desc[:100] + "..."
            descriptions.append(f"- **{name}**: {desc}")

        return "\n".join(descriptions)

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
        logger.info("🔍 [IndexAnalystV2] Start building user prompt words")
        logger.info(f"📊 Stock code: {ticker}")
        logger.info(f"📅 Analysis date: {analysis_date}")
        
        if state is None:
            state = {}
        
        # Get company name and market information
        company_name = self._get_company_name(ticker, state)
        market_type = state.get("market_type", "A shares")
        market_name = market_type
        currency_name = "RMB"
        currency_symbol = "¥"
        
        if StockUtils and ticker:
            try:
                market_info = StockUtils.get_market_info(ticker)
                market_name = market_info.get('market_name', market_type)
                currency_name = market_info.get('currency_name', "RMB")
                currency_symbol = market_info.get('currency_symbol', "¥")
            except Exception as e:
                logger.warning(f"Failed to obtain market information: {e}")
        
        # Prepare template variables (refer to the implementation of research_manager_v2)
        template_variables = {
            "ticker": ticker,
            "company_name": company_name,
            "market_name": market_name,
            "market_type": market_type,
            "analysis_date": analysis_date,
            "current_date": analysis_date,
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
            agent_name="index_analyst_v2",
            variables=template_variables,
            state=state,  # 🔑 Pass state and the base class will automatically extract system variables
            context=state.get("context"),  # Get from state context
            fallback_prompt=None,
            prompt_type="user"  # 🔑 Explicitly specify the user prompt word to obtain
        )
        mode = state.get("_analysis_data_source", "tushare")
        prompt = self._apply_mode_prompt_suffix(prompt, mode, "user")
        
        if prompt:
            logger.info(f"✅ Obtain market analyst v2.0 user prompt words from the template system (length: {len(prompt)})")
            logger.info(f"📝 The first 500 characters of the user prompt word:\n{prompt[:500]}...")
            return prompt
        
        # Downgrade: Use default prompt word (tool_data is no longer checked as tool data is passed via ToolMessage)
        logger.warning("⚠️ The user prompt word is not obtained from the template system, and the default prompt word is used.")
        # 🔑 Key: clearly tell LLM in the default prompt word what parameters to use to call the tool
        if mode == "qmt":
            return f"""## Analysis tasks

    please **{ticker} ({company_name}) ** where{market_type}The market conducts macro-environmental research and market structure analysis.

    **Analysis date**: {analysis_date}
    **data source schema**: QMT

    **Important tips**: When calling the tool, the following parameters must be used:
    - get_market_analysis: trade_date='{analysis_date}', lookback_days=60

    **The above parameter values must be used**, Do not make up official statistics on northbound funds, secondary financing, price limits or index valuation data.

    Please output a Chinese research report based on QMT index trends, snapshot proxy indicators, style switching and market diffusion, containing at least:
    1. Macro environment research
    2. Index and market structure status quo
    3. Main supporting factors, main risks and data gaps
    4. Follow-up observations

    It is prohibited to output hot spot chasing statements, hedging arrangements, position allocations, buying and selling recommendations, target prices, price ranges or any execution instructions."""

        return f"""## Analysis tasks

    please **{ticker} ({company_name}) ** where{market_type}The market conducts macro-environment research and market structure analysis.

    **Analysis date**: {analysis_date}

    **Important tips**: When calling the tool, the following parameters must be used:
    - get_market_analysis: trade_date='{analysis_date}', lookback_days=60

    **The above parameter values must be used**, Do not use other dates.

    Please call the tool to obtain market data, and then output a Chinese research report based on real results, which at least contains:
    1. Macro environment research
    2. Index and market structure status quo
    3. Main supporting factors, main risks and data gaps
    4. Follow-up observations

    It is prohibited to output hot spot chasing statements, hedging arrangements, position allocations, buying and selling recommendations, target prices, price ranges or any execution instructions."""

    def _get_tool_suggestions(self, market_type: str) -> str:
        """Generate tool call suggestions based on market type"""
        if not self.tool_names:
            return " (No tools available, please analyze based on existing knowledge)"

        suggestions = ["Please call the following tools according to your analysis needs:"]

        # Give calling suggestions based on tool name
        tool_hints = {
            "get_market_analysis": "Automatically obtain complete market analysis data based on current data source",
        }

        for tool_name in self.tool_names:
            hint = tool_hints.get(tool_name, "Get relevant data")
            suggestions.append(f"- `{tool_name}`: {hint}")

        return "\n".join(suggestions)

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


# === etf_analyst_v2 ===
"""
ETF Analyst Agent v2.0

Analyze ETF net value, size, fee rate, tracking error, etc. (ETF has no PE/PB/ROE)
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from ..base import BaseAgent
from ..config import AgentConfig, AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class EtfAnalystAgentV2(BaseAgent):
    """
    ETF Analyst Agent v2.0

    Analyze ETF s net value, size, expense ratio, tracking index, tracking error, etc.
    ETF No PE/PB/ROE, use proprietary metrics.
    """

    metadata = AgentMetadata(
        id="etf_analyst_v2",
        name="ETF analyst v2.0",
        description="Analyze ETF net worth, size, expense ratio, tracking error, and more. ETFs have no PE/PB/ROE.",
        category=AgentCategory.ANALYST,
        license_tier=LicenseTier.FREE,
        default_tools=["get_etf_fundamentals"],
        version="2.0.0",
        inputs=[
            AgentInput(name="ticker", type="string", description="ETF code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="fundamentals_report", type="string", description="ETF analysis report"),
        ],
        requires_tools=True,
        output_field="fundamentals_report",
        report_label=" [ETF Analysis v2]",
        workflow_stage="analyst",
        growth_role="extractor",
        growth_outputs=["fundamentals_report"],
        memory_scope_hint="object_tracking",
        review_level="auto_pending",
        growth_source_type="analysis_report",
    )

    def __init__(
        self,
        config: Optional[Any] = None,
        llm: Optional[BaseChatModel] = None,
        tool_ids: Optional[list] = None
    ):
        super().__init__(config=config, llm=llm, tool_ids=tool_ids)
        if tool_ids is None and llm is not None:
            tool_ids = self.load_tools_from_config()
            if tool_ids:
                self._load_tools_v2(tool_ids)

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state.get("ticker") or state.get("company_of_interest")
        trade_date = state.get("trade_date") or state.get("end_date") or state.get("analysis_date")

        if not ticker:
            raise ValueError("Missing required parameter: ticker")

        logger.info(f"Start ETF Analysis: {ticker} (Date: {trade_date})")

        system_prompt = self._build_system_prompt(state)
        user_prompt = self._build_user_prompt(ticker, trade_date, state)

        system_prompt = self._apply_global_trading_advice_guard(system_prompt)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        if self._llm and self.tools:
            analysis = self.invoke_with_tools(messages, analysis_prompt=self._build_analysis_prompt(ticker))
        else:
            logger.warning("Without LLM or tools configured, simulation results are returned")
            analysis = self._generate_mock_report(ticker, trade_date)

        return {"fundamentals_report": analysis}

    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        template_variables = {}
        if state:
            template_variables["ticker"] = state.get("ticker", "")
            template_variables["company_name"] = state.get("company_name", "")
            analysis_date = state.get("analysis_date") or state.get("trade_date")
            if analysis_date:
                template_variables["current_date"] = str(analysis_date)[:10]
                template_variables["analysis_date"] = str(analysis_date)[:10]

        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="etf_analyst_v2",
            variables=template_variables,
            state=state or {},
            context=state.get("context") if state else None,
            fallback_prompt=None,
            prompt_type="system"
        )

        if prompt:
            return prompt

        return """You are a professional ETF analyst. ETFs are funds that track indexes and do not have individual stock valuation indicators such as PE/PB/ROE.

Your task:
1. Call get_etf_fundamentals to get ETF data
2. Analyze net worth, size, tracking index, rise and fall
3. Assess tracking error, liquidity risk
4. Provide research observations

The use of PE/PB/ROE to analyze ETFs is prohibited."""

    def _build_user_prompt(self, ticker: str, trade_date: str, state: Dict[str, Any] = None) -> str:
        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="etf_analyst_v2",
            variables={"ticker": ticker, "analysis_date": trade_date or "", "current_date": trade_date or ""},
            state=state or {},
            context=state.get("context") if state else None,
            fallback_prompt=None,
            prompt_type="user"
        )
        if prompt:
            return prompt
        return f"Please analyze ETF {ticker}. Analysis date:{trade_date}. Please call the tool to obtain data and generate a report."

    def _build_analysis_prompt(self, ticker: str) -> str:
        return f"""Based on the obtained data, generate {ticker} ETF analysis reports, including:
1. Net worth and size
2. Track index performance
3. Liquidity assessment
4. research observation
Use of PE/PB/ROE is prohibited."""

    def _generate_mock_report(self, ticker: str, trade_date: str) -> str:
        return f"""ETF Analysis Report (Simulation)

code: {ticker}
Date: {trade_date}

Net worth trend: data to be obtained
Scale: data to be obtained
Tracking index: data to be obtained
Suggestion: Please configure the data source and then analyze again."""

# === chip_distribution_analyst_v2 ===
"""
Chip distribution analyst Agent v2.0

A chip distribution analyst implemented based on the AnalystAgent base class.
Analyze the distribution of stock chips and evaluate the profit ratio, average cost and chip concentration.
The prompt words are configured in the database template and can be modified by the user.
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from ..analyst import AnalystAgent
from ..config import AgentMetadata, AgentCategory, LicenseTier, AgentInput, AgentOutput
from ..registry import register_agent

logger = logging.getLogger(__name__)

# Try importing utility functions
try:
    from tradingagents.utils.stock_utils import StockUtils
except ImportError:
    logger.warning("Unable to import StockUtils, some functions may not be available")
    StockUtils = None


@register_agent
class ChipDistributionAnalystV2(AnalystAgent):
    """
    Chip distribution analyst v2.0

    Function:
    - Get stock chip distribution data
    - Analyze profit ratio (floating profit/floating loss situation)
    - Analyze average holding costs
    - Assess chip concentration (90%/70% range)
    - Generate chip distribution analysis report

    Workflow:
    1. Call the chip distribution tool to obtain data (AkShare is preferred, Tushare is used as backup)
    2. Use LLM to deeply analyze the meaning of chip distribution
    3. Generate chip distribution analysis report
    """

    # Agent metadata
    metadata = AgentMetadata(
        id="chip_distribution_analyst_v2",
        name="Chip distribution analyst v2.0",
        description="Analyze stock chip distribution, evaluate profit ratio, average cost and chip concentration, and generate chip distribution analysis report",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
        icon="🧮",
        color="#e74c3c",
        tags=["Chip distribution", "Holding cost", "Profit ratio", "v2.0"],
        default_tools=["get_chip_distribution"],
        inputs=[
            AgentInput(name="ticker", type="string", description="Stock code"),
            AgentInput(name="analysis_date", type="string", description="Analysis date"),
        ],
        outputs=[
            AgentOutput(name="chip_report", type="string", description="Chip distribution analysis report"),
        ],
        requires_tools=True,
        output_field="chip_report",
        report_label=" [Chip distribution analysis v2]",
        workflow_stage="analyst",
        execution_order=15,
    )

    # Analyst type
    analyst_type = "chip_distribution"

    # Output field name
    output_field = "chip_report"

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Perform chip distribution analysis"""
        try:
            ticker, analysis_date = self._extract_common_params(state)
            context = state.get("context")
            overrides = state.get("prompt_overrides") or {}
            system_override = overrides.get("system")
            user_override = overrides.get("user")
            analysis_override = overrides.get("analysis")

            if not ticker:
                raise ValueError("Missing required parameters: ticker")

            # Build system prompt words
            system_prompt = system_override
            if not system_prompt:
                template_variables = {
                    "ticker": ticker,
                    "analysis_date": analysis_date,
                    "current_date": analysis_date,
                    "tool_names": ", ".join([t.name for t in self._langchain_tools]) if self._langchain_tools else "",
                }
                # Inject company name
                company_name = state.get("company_name", "")
                if not company_name and StockUtils and ticker:
                    try:
                        market_info = StockUtils.get_market_info(ticker)
                        template_variables["company_name"] = market_info.get("company_name", ticker)
                        template_variables["market_name"] = market_info.get("market_name", "China A shares")
                    except Exception:
                        template_variables["company_name"] = ticker
                        template_variables["market_name"] = "China A shares"
                else:
                    template_variables["company_name"] = company_name or ticker
                    template_variables["market_name"] = state.get("market_name", "China A shares")

                system_prompt = self._get_prompt_from_template(
                    agent_type="analysts_v2",
                    agent_name="chip_distribution_analyst_v2",
                    variables=template_variables,
                    state=state,
                    context=context,
                    fallback_prompt=None,
                    prompt_type="system"
                )

            if not system_prompt:
                system_prompt = self._build_system_prompt(state=state)

            # Build user prompt words
            user_prompt = user_override
            if not user_prompt:
                user_prompt = self._build_user_prompt(ticker, analysis_date, state)

            system_prompt = self._apply_global_trading_advice_guard(system_prompt)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            if self._llm:
                if self._langchain_tools:
                    analysis_prompt = analysis_override or self._build_analysis_prompt(ticker, analysis_date)
                    report = self.invoke_with_tools(messages, analysis_prompt=analysis_prompt)
                    tool_summary = self._format_tool_call_summary()
                    if self._chip_tool_unavailable():
                        report = self._build_unavailable_report(ticker, analysis_date)
                else:
                    response = self._invoke_llm_with_trace(messages)
                    report = response.content if hasattr(response, "content") else str(response)
                    tool_summary = ""
            else:
                raise ValueError("LLM not initialized")

            result = {self.output_field: report}
            if tool_summary:
                result["tool_call_summaries"] = {self.analyst_type: tool_summary}
            return result

        except Exception as e:
            logger.error(f"[{self.agent_id}] Execution failed: {e}", exc_info=True)
            return {self.output_field: f"Chip distribution analysis failed: {str(e)}"}

    def _chip_tool_unavailable(self) -> bool:
        summaries = getattr(self, "_tool_call_summaries_collected", []) or []
        chip_calls = [s for s in summaries if s.get("tool_name") == "get_chip_distribution"]
        if not chip_calls:
            return False

        last_call = chip_calls[-1]
        result = str(last_call.get("result_preview") or "")
        error_markers = ("❌", "Tool execution failed", "Unable to obtain", "Failed to obtain")
        return (not last_call.get("success")) or any(marker in result for marker in error_markers)

    def _build_unavailable_report(self, ticker: str, analysis_date: str) -> str:
        summaries = getattr(self, "_tool_call_summaries_collected", []) or []
        chip_calls = [s for s in summaries if s.get("tool_name") == "get_chip_distribution"]
        reason = "The chip distribution tool did not return valid data"
        if chip_calls:
            last_call = chip_calls[-1]
            reason = last_call.get("error") or last_call.get("result_preview") or reason

        return f"""⚠️ **Chip distribution data is temporarily unavailable**

Stock code:{ticker}  
Analysis date:{analysis_date}

A valid chip distribution analysis report could not be generated this time because the chip distribution tool did not return analyzable data.

**Tool return information**: {reason}

In order to avoid misleading conclusions, this node does not guess or fill in the chip structure, profit ratio, average cost, support pressure level and other indicators based on the model. Please try again later, or check the AkShare/Tushare data source, network connection, and native socket resource status."""

    def _build_analysis_prompt(self, ticker: str, analysis_date: str) -> str:
        return f"""Based on the real data returned by the chip distribution tool, generate {ticker} in {analysis_date} Chip distribution analysis report.

Requirements:
1. Only the data actually returned in the ToolMessage can be used, and model knowledge must not be used to determine whether the current year or date exists.
2. If the tool returns with ❌ begins, or contains Tool execution failed  Unable to obtain  Failed to obtain , Please explain directly Chip distribution data is temporarily unavailable , And cite the reason why the tool failed.
3. When a tool fails, it is prohibited to make up profit ratios, average costs, chip ranges, and support pressure levels, and do not make inferences that future dates cannot be analyzed.
4. When the tool is successful, analysis will be conducted around the profit ratio, average cost, 90%/70% chip range, concentration, and support and pressure relationships.
5. Use Chinese Markdown output."""

    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """Build default system prompt words (database template takes priority)"""
        if state is None:
            state = {}

        template_variables = {}
        if "ticker" in state:
            template_variables["ticker"] = state["ticker"]
        analysis_date = state.get("analysis_date") or state.get("trade_date")
        if analysis_date:
            if isinstance(analysis_date, str) and len(analysis_date) > 10:
                analysis_date = analysis_date.split()[0]
            template_variables["current_date"] = analysis_date
            template_variables["analysis_date"] = analysis_date

        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="chip_distribution_analyst_v2",
            variables=template_variables,
            state=state,
            context=state.get("context"),
            fallback_prompt=None,
            prompt_type="system"
        )
        if prompt:
            return prompt

        return """You are a professional A-share chip distribution analyst who is good at gaining insight into the market game pattern through chip distribution data.

Your responsibilities:
1. Interpret the profit ratio of chips (the proportion of chips with floating profit under the current price)
2. Analyze the relationship between average holding costs and current prices
3. Evaluate the 90%/70% chip concentration range and concentration ratio
4. Determine the upper pressure and lower support
5. Comprehensive study and judgment of main position intentions and trends

Analysis requirements:
- Objectively interpret chip data to avoid subjective assumptions
- Determine the severity of selling pressure based on profit ratio
- Judging trend stability based on concentration
- Provide clear support/pressure level judgments
- Use Chinese output

Output format:
Please output the chip distribution analysis report in a structured manner, including:
- Chip profit status
- cost structure analysis
- Chip concentration assessment
- Support pressure level analysis
- Comprehensive research and judgment
"""

    def _build_user_prompt(self, ticker: str, analysis_date: str, state: Dict[str, Any]) -> str:
        """Construct user prompt words (database template is preferred)"""
        if state is None:
            state = {}

        company_name = state.get("company_name", ticker)
        market_name = state.get("market_name", "China A shares")

        template_variables = {
            "ticker": ticker,
            "company_name": company_name,
            "market_name": market_name,
            "analysis_date": analysis_date,
            "current_date": analysis_date,
            "tool_names": ", ".join([t.name for t in self._langchain_tools]) if self._langchain_tools else "",
        }

        prompt = self._get_prompt_from_template(
            agent_type="analysts_v2",
            agent_name="chip_distribution_analyst_v2",
            variables=template_variables,
            state=state,
            context=state.get("context"),
            fallback_prompt=None,
            prompt_type="user"
        )
        if prompt:
            return prompt

        return f"""Please analyze {company_name} ({ticker}) in {analysis_date} Distribution of chips:

Stock code:{ticker}
Company name:{company_name}
Analysis date:{analysis_date}
Market:{market_name}

Please call the chip distribution tool to obtain data, and then generate a detailed chip distribution analysis report.
Key analysis: profit ratio, average cost, chip concentration, support and pressure level."""


_self_mod = _sys.modules[__name__]
for _sub in ['market_analyst_v2', 'fundamentals_analyst_v2', 'news_analyst_v2', 'social_analyst_v2', 'sector_analyst_v2', 'index_analyst_v2', 'etf_analyst_v2', 'chip_distribution_analyst_v2']:
    _sys.modules[f"core.agents.adapters.{_sub}"] = _self_mod