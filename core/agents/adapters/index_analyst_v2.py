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

