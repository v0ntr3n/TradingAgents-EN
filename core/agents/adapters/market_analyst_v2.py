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
