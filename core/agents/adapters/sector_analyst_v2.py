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
            posteriors = state.get("analyst_posteriors", {})
            if self.agent_id in posteriors:
                return {}
            parsed = self._parse_response(existing_report)
            return {
                "analyst_posteriors": {
                    self.agent_id: parsed["posterior"]
                }
            }

        # ⚠️ Industry reports do not support caching: industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
        # Therefore, each analysis must be regenerated and caching cannot be used (caching is also skipped in debug mode)
        logger.info(f"🏭 [Sector Analyst v2] Skip the cache check (industry reports do not support caching) and directly generate a new report")

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

