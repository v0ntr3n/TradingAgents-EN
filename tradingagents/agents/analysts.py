from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['china_market_analyst', 'fundamentals_analyst', 'index_analyst', 'market_analyst', 'news_analyst', 'sector_analyst', 'social_media_analyst']:
    _sys.modules[f"tradingagents.agents.analysts.{_sub}"] = _self_mod
    setattr(_self_mod, _sub, _self_mod)

# === china_market_analyst.py ===
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# Import Google tool call processor
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler
from tradingagents.agents.utils.compliance_prompting import apply_compliance_guardrails


def _get_company_name_for_china_market(ticker: str, market_info: dict) -> str:
    """
    Get Company Names for China Market Analysts

    Args:
        ticker: Stock code
        market_info: Market Information Dictionary

    Returns:
        str: Company name
    """
    try:
        if market_info['is_china']:
            # China A-shares: Obtain stock information using a unified interface
            from tradingagents.dataflows.interface import get_china_stock_info_unified
            stock_info = get_china_stock_info_unified(ticker)

            logger.debug(f"📊 [China market analyst] Get stock information return: {stock_info[:200] if stock_info else 'None'}...")

            # Parse stock names
            if stock_info and "Stock name:" in stock_info:
                company_name = stock_info.split("Stock name:")[1].split("\n")[0].strip()
                logger.info(f"✅ [China market analyst] Successfully obtained Chinese stock names: {ticker} -> {company_name}")
                return company_name
            else:
                # Downgrade scenario: Try getting it directly from the data source manager
                logger.warning(f"⚠️ [China market analyst] Unable to parse stock name from unified interface: {ticker}, Try a downgrade solution")
                try:
                    from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
                    info_dict = get_info_dict(ticker)
                    if info_dict and info_dict.get('name'):
                        company_name = info_dict['name']
                        logger.info(f"✅ [China market analyst] The downgrade plan successfully obtained the stock name: {ticker} -> {company_name}")
                        return company_name
                except Exception as e:
                    logger.error(f"❌ [China market analyst] Downgrade plan also failed: {e}")

                logger.error(f"❌ [China market analyst] All schemes are unable to obtain the stock name: {ticker}")
                return f"Stock code{ticker}"

        elif market_info['is_hk']:
            # Hong Kong stocks: Use improved Hong Kong stocks tools
            try:
                from tradingagents.dataflows.providers.hk.improved_hk import get_hk_company_name_improved
                company_name = get_hk_company_name_improved(ticker)
                logger.debug(f"📊 [China market analyst] Use the improved Hong Kong stock tool to obtain names: {ticker} -> {company_name}")
                return company_name
            except Exception as e:
                logger.debug(f"📊 [China market analyst] Improved Hong Kong stock tool failed to obtain name: {e}")
                # Downgrade scenario: generate friendly default names
                clean_ticker = ticker.replace('.HK', '').replace('.hk', '')
                return f"Hong Kong stocks{clean_ticker}"

        elif market_info['is_us']:
            # US stocks: use simple mapping or return codes
            us_stock_names = {
                'AAPL': 'apple inc.',
                'TSLA': 'Tesla',
                'NVDA': 'NVIDIA',
                'MSFT': 'Microsoft',
                'GOOGL': 'Google',
                'AMZN': 'Amazon',
                'META': 'Meta',
                'NFLX': 'Netflix'
            }

            company_name = us_stock_names.get(ticker.upper(), f"US stocks{ticker}")
            logger.debug(f"📊 [China market analyst] US stock name mapping: {ticker} -> {company_name}")
            return company_name

        else:
            return f"stocks{ticker}"

    except Exception as e:
        logger.error(f"❌ [China market analyst] Failed to get company name: {e}")
        return f"stocks{ticker}"


def create_china_market_analyst(llm, toolkit):
    """Create China Market Analyst"""
    
    def china_market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        
        # Get stock market information
        from tradingagents.utils.stock_utils import StockUtils
        market_info = StockUtils.get_market_info(ticker)
        
        # Get company name
        company_name = _get_company_name_for_china_market(ticker, market_info)
        logger.info(f"[China market analyst] Company name: {company_name}")
        
        # China stock analysis tools
        tools = [
            toolkit.get_china_stock_data,
            toolkit.get_china_market_overview,
            toolkit.get_YFin_data,  # Alternate data source
        ]
        
        system_message = (
            """You are a professional Chinese stock market analyst, specializing in analyzing A-shares, Hong Kong stocks and other Chinese capital markets. You have in-depth knowledge of the Chinese stock market and rich local investment experience.

Your areas of expertise include:
1. **A stock market analysis**: Deeply understand the uniqueness of A-shares, including the price limit system,T+1 Trading, margin trading, etc.
2. **China economic policy**: Be familiar with the impact mechanism of monetary policy and fiscal policy on the stock market
3. **Industry sector rotation**: Master the plate rotation rules and hotspot switching with Chinese characteristics
4. **regulatory environment**: Understand regulatory changes such as CSRC policies, delisting system, registration system, etc.
5. **market sentiment**: Understand the behavioral characteristics and emotional fluctuations of Chinese investors

Analysis focus:
- **Technical analysis**: Use Tongdaxin data for precise technical indicator analysis
- **fundamental analysis**: Analysis based on Chinese accounting standards and financial reporting characteristics
- **Policy analysis**: Assess the impact of policy changes on individual stocks and sectors
- **Financial analysis**: Analyze capital flows such as northbound funds, margin financing and securities lending, and large transactions
- **market style**: Determine whether growth style or value style is dominant at present

Consider the characteristics of China s stock market:
- The impact of price limit restrictions on market behavior and liquidity
- ST Special Risks and Opportunities of Stocks
- Differentiation Analysis of Science and Technology Innovation Board and GEM
- The impact of state-owned enterprise reform, mixed-ownership reform and other themes on the industry structure
- The impact of Sino-US relations and geopolitics on Chinese concept stocks

Please write a professional Chinese analysis report based on the real-time data and technical indicators provided by the Tushare data interface and combined with the particularity of the Chinese stock market.
Make sure to attach a Markdown table at the end of the report summarizing key findings, risk tips, and follow-up observations."""
        )
    system_message = apply_compliance_guardrails(system_message, "china_market_analyst")

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a professional AI assistant who collaborates with other analysts on stock analysis."
                " Obtain and analyze data using the tools provided."
                " If you can t answer it completely, that s okay; other analysts will complement your analysis."
                " Focus on your area of expertise and deliver high-quality analytical insights."
                " You can access the following tools:{tool_names}. \n{system_message}"
                "Current analysis date:{current_date}, Analysis target:{ticker}. Please write all analysis content in Chinese.",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )

    prompt = prompt.partial(system_message=system_message)
    # Safely obtain tool names, handler functions and tool objects
    tool_names = []
    for tool in tools:
        if hasattr(tool, 'name'):
            tool_names.append(tool.name)
        elif hasattr(tool, '__name__'):
            tool_names.append(tool.__name__)
        else:
            tool_names.append(str(tool))

    prompt = prompt.partial(tool_names=", ".join(tool_names))
    prompt = prompt.partial(current_date=current_date)
    prompt = prompt.partial(ticker=ticker)

    chain = prompt | llm.bind_tools(tools)
    result = chain.invoke(state["messages"])

    # Call handlers using unified Google tools
    if GoogleToolCallHandler.is_google_model(llm):
        logger.info("📊 [China market analyst] Google model detected, processor invoked using unified tools")

        # Create analysis prompt words
        analysis_prompt_template = GoogleToolCallHandler.create_analysis_prompt(
            ticker=ticker,
            company_name=company_name,
            analyst_type="China market analysis",
            specific_requirements="Focus on the characteristics of China s A-share market, policy impact, industry development trends, etc."
        )

        # Handling Google model tool calls
        report, messages = GoogleToolCallHandler.handle_google_tool_calls(
            result=result,
            llm=llm,
            tools=tools,
            state=state,
            analysis_prompt_template=analysis_prompt_template,
            analyst_name="China market analyst"
        )
    else:
        # Processing logic for non-Google models
        logger.debug(f"📊 [DEBUG] Non-Google model ({llm.__class__.__name__}), Use standard processing logic")

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

    return {
        "messages": [result],
        "china_market_report": report,
        "sender": "ChinaMarketAnalyst",
    }
    
    return china_market_analyst_node


def create_china_stock_screener(llm, toolkit):
    """Create a China stock screener"""
    
    def china_stock_screener_node(state):
        current_date = state["trade_date"]
        
        tools = [
            toolkit.get_china_market_overview,
        ]
        
        system_message = (
            """You are a professional Chinese stock screening expert, responsible for screening stocks with investment value from the A-share market.

Filter dimensions include:
1. **Fundamental screening**: 
   - Financial indicators: ROE, ROA, net profit growth rate, revenue growth rate
   - Valuation indicators: PE, PB, PEG, PS ratio
   - Financial health: gearing ratio, current ratio, quick ratio

2. **Technical screening**:
   - Trend indicators: moving average system, MACD,KDJ
   - Momentum indicators: RSI, William indicator,CCI
   - Trading volume indicators: volume-price relationship, turnover rate

3. **Market screening**:
   - Fund flow direction: net inflow of main funds, preference for northbound funds
   - Institutional positions: heavy fund positions, social holdings, QFII positions
   - Market popularity: activity of concept sectors, degree of subject matter hype

4. **Policy screening**:
   - Policy Benefits: National Policy Support Industries
   - Reform dividends: State-owned enterprise reform, mixed ownership reform target
   - Regulatory Impact: Impact of regulatory policy changes

Screening strategy:
- **value investing**: Low valuation, high dividends, stable growth
- **growth investment**: High growth, emerging industries, technological innovation
- **Thematic investment**: Policy driven, event catalyzed, concept hype
- **cycle investment**: Economic cycle, industry cycle, seasonality

Please provide professional stock screening suggestions based on the current market environment and policy background."""
        )
        
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system", 
                    "You are a professional stock screener."
                    " Analyze the market overview using the provided tools."
                    " You can access the following tools:{tool_names}. \n{system_message}"
                    "Current date:{current_date}. Please write the analysis content in Chinese.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        
        prompt = prompt.partial(system_message=system_message)
        # Safely obtain tool names, handler functions and tool objects
        tool_names = []
        for tool in tools:
            if hasattr(tool, 'name'):
                tool_names.append(tool.name)
            elif hasattr(tool, '__name__'):
                tool_names.append(tool.__name__)
            else:
                tool_names.append(str(tool))

        prompt = prompt.partial(tool_names=", ".join(tool_names))
        prompt = prompt.partial(current_date=current_date)
        
        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])
        
        return {
            "messages": [result],
            "stock_screening_report": result.content,
            "sender": "ChinaStockScreener",
        }
    
    return china_stock_screener_node

# === fundamentals_analyst.py ===
"""
Fundamental Analyst - Unified Tool Architecture Version
Use unified tools to automatically identify stock types and call corresponding data sources
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, ToolMessage

# Import analysis module log decorator
from tradingagents.utils.tool_logging import log_analyst_module

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# Import Google tool call processor
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler
from tradingagents.agents.utils.compliance_prompting import apply_compliance_guardrails

# Import template client
from tradingagents.utils.template_client import get_agent_prompt


def _get_company_name_for_fundamentals(ticker: str, market_info: dict) -> str:
    """
    Get company names for fundamental analysts

    Args:
        ticker: Stock code
        market_info: Market Information Dictionary

    Returns:
        str: Company name
    """
    try:
        if market_info['is_china']:
            # China A-shares: Obtain stock information using a unified interface
            from tradingagents.dataflows.interface import get_china_stock_info_unified
            stock_info = get_china_stock_info_unified(ticker)

            logger.debug(f"📊 [fundamental analyst] Get stock information return: {stock_info[:200] if stock_info else 'None'}...")

            # Parse stock names
            if stock_info and "Stock name:" in stock_info:
                company_name = stock_info.split("Stock name:")[1].split("\n")[0].strip()
                logger.info(f"✅ [fundamental analyst] Successfully obtained Chinese stock names: {ticker} -> {company_name}")
                return company_name
            else:
                # Downgrade scenario: Try getting it directly from the data source manager
                logger.warning(f"⚠️ [fundamental analyst] Unable to parse stock name from unified interface: {ticker}, Try a downgrade solution")
                try:
                    from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
                    info_dict = get_info_dict(ticker)
                    if info_dict and info_dict.get('name'):
                        company_name = info_dict['name']
                        logger.info(f"✅ [fundamental analyst] The downgrade plan successfully obtained the stock name: {ticker} -> {company_name}")
                        return company_name
                except Exception as e:
                    logger.error(f"❌ [fundamental analyst] Downgrade plan also failed: {e}")

                logger.error(f"❌ [fundamental analyst] All schemes are unable to obtain the stock name: {ticker}")
                return f"Stock code{ticker}"

        elif market_info['is_hk']:
            # Hong Kong stocks: Use improved Hong Kong stocks tools
            try:
                from tradingagents.dataflows.providers.hk.improved_hk import get_hk_company_name_improved
                company_name = get_hk_company_name_improved(ticker)
                logger.debug(f"📊 [fundamental analyst] Use the improved Hong Kong stock tool to obtain names: {ticker} -> {company_name}")
                return company_name
            except Exception as e:
                logger.debug(f"📊 [fundamental analyst] Improved Hong Kong stock tool failed to obtain name: {e}")
                # Downgrade scenario: generate friendly default names
                clean_ticker = ticker.replace('.HK', '').replace('.hk', '')
                return f"Hong Kong stocks{clean_ticker}"

        elif market_info['is_us']:
            # US stocks: use simple mapping or return codes
            us_stock_names = {
                'AAPL': 'apple inc.',
                'TSLA': 'Tesla',
                'NVDA': 'NVIDIA',
                'MSFT': 'Microsoft',
                'GOOGL': 'Google',
                'AMZN': 'Amazon',
                'META': 'Meta',
                'NFLX': 'Netflix'
            }

            company_name = us_stock_names.get(ticker.upper(), f"US stocks{ticker}")
            logger.debug(f"📊 [fundamental analyst] US stock name mapping: {ticker} -> {company_name}")
            return company_name

        else:
            return f"stocks{ticker}"

    except Exception as e:
        logger.error(f"❌ [fundamental analyst] Failed to get company name: {e}")
        return f"stocks{ticker}"


def create_fundamentals_analyst(llm, toolkit):
    @log_analyst_module("fundamentals")
    def fundamentals_analyst_node(state):
        logger.debug("📊 [DEBUG] ===== Fundamental analyst node starts =====")

        # 🔧 Tool call counter - prevent infinite loops
        # Check if there is a ToolMessage in the message history. If there is, the tool has been executed.
        messages = state.get("messages", [])
        tool_message_count = sum(1 for msg in messages if isinstance(msg, ToolMessage))

        tool_call_count = state.get("fundamentals_tool_call_count", 0)
        max_tool_calls = 1  # Maximum number of tool calls: All data can be obtained with one tool call

        # If there is a new ToolMessage, update the counter
        if tool_message_count > tool_call_count:
            tool_call_count = tool_message_count
            logger.info(f"🔧 [Tool call count] New tool results detected, counter updated: {tool_call_count}")

        logger.info(f"🔧 [Tool call count] Current number of tool calls: {tool_call_count}/{max_tool_calls}")

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        # 🔧 Fundamental analysis data range: Fixed acquisition of 10 days of data (processing weekends/holidays/data delays)
        # Reference documentation:docs/ANALYST_DATA_CONFIGURATION.md
        # Fundamental analysis mainly relies on financial data (PE, PB, ROE, etc.) and only requires the current stock price
        # The purpose of obtaining 10 days of data is to ensure that the data can be obtained, but the actual analysis only uses the last 2 days.
        from datetime import datetime, timedelta
        try:
            end_date_dt = datetime.strptime(current_date, "%Y-%m-%d")
            start_date_dt = end_date_dt - timedelta(days=10)
            start_date = start_date_dt.strftime("%Y-%m-%d")
            logger.info(f"📅 [fundamental analyst] data range: {start_date} to {current_date} (Fixed for 10 days)")
        except Exception as e:
            # If date parsing fails, the default of 10 days ago is used
            logger.warning(f"⚠️ [fundamental analyst] Date parsing failed, using default range: {e}")
            start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        logger.debug(f"📊 [DEBUG] input parameters: ticker={ticker}, date={current_date}")
        logger.debug(f"📊 [DEBUG] The number of messages in the current state: {len(state.get('messages', []))}")
        logger.debug(f"📊 [DEBUG] Current fundamental reports: {state.get('fundamentals_report', 'None')}")

        # Get stock market information
        from tradingagents.utils.stock_utils import StockUtils
        logger.info(f"📊 [fundamental analyst] Analyzing stocks: {ticker}")

        # Add detailed ticker tracking logs
        logger.info(f"🔍 [Stock symbol tracking] Original ticker received by fundamental analysts: '{ticker}' (Type: {type(ticker)})")
        logger.info(f"🔍 [Stock symbol tracking] Stock symbol length: {len(str(ticker))}")
        logger.info(f"🔍 [Stock symbol tracking] ticker character: {list(str(ticker))}")

        market_info = StockUtils.get_market_info(ticker)
        logger.info(f"🔍 [Stock symbol tracking] StockUtils.get_market_info Returned market information: {market_info}")

        logger.debug(f"📊 [DEBUG] Stock type check: {ticker} -> {market_info['market_name']} ({market_info['currency_name']}")
        logger.debug(f"📊 [DEBUG] Detailed market information: is_china={market_info['is_china']}, is_hk={market_info['is_hk']}, is_us={market_info['is_us']}")
        logger.debug(f"📊 [DEBUG] Tool configuration check: online_tools={toolkit.config['online_tools']}")

        # Get company name
        company_name = _get_company_name_for_fundamentals(ticker, market_info)
        logger.debug(f"📊 [DEBUG] Company name: {ticker} -> {company_name}")

        # Unify the use of get_stock_fundamentals_unified tool
        # The tool will automatically identify the stock type (A shares/Hong Kong stocks/US stocks) internally and call the corresponding data source
        # For A shares, it automatically obtains price data and fundamental data without the need for LLM to call multiple tools
        logger.info("📊 [fundamental analyst] Use unified fundamental analysis tools to automatically identify stock types")
        tools = [toolkit.get_stock_fundamentals_unified]

        # Safely obtain tool names for debugging
        tool_names_debug = []
        for tool in tools:
            if hasattr(tool, 'name'):
                tool_names_debug.append(tool.name)
            elif hasattr(tool, '__name__'):
                tool_names_debug.append(tool.__name__)
            else:
                tool_names_debug.append(str(tool))
        logger.info(f"📊 [fundamental analyst] Bound tools: {tool_names_debug}")
        logger.info(f"📊 [fundamental analyst] target market: {market_info['market_name']}")

        # 🆕 Use template system to get prompt words
        try:
            # Prepare template variables
            template_variables = {
                "ticker": ticker,
                "company_name": company_name,
                "market_name": market_info['market_name'],
                "current_date": current_date,
                "start_date": start_date,
                "currency_name": market_info['currency_name'],
                "currency_symbol": market_info['currency_symbol'],
                "tool_names": ", ".join(tool_names_debug)
            }

            from tradingagents.utils.template_client import get_template_client
            ctx = state.get("agent_context") or {}
            logger.info(f"[diagnose] fundamentals ctx_user={ctx.get('user_id')} ctx_pref={ctx.get('preference_id')} agent=analysts/fundamentals_analyst")
            tpl_info = get_template_client().get_effective_template(
                agent_type="analysts",
                agent_name="fundamentals_analyst",
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                context=None
            )
            if tpl_info:
                logger.info(f"📚 [Template selection] source={tpl_info.get('source')} id={tpl_info.get('template_id')} version={tpl_info.get('version')} agent=analysts/fundamentals_analyst")

            # Get prompt words from template system
            system_prompt = get_agent_prompt(
                agent_type="analysts",
                agent_name="fundamentals_analyst",
                variables=template_variables,
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                fallback_prompt=None,
                context=None
            )
            system_prompt = apply_compliance_guardrails(system_prompt, "fundamentals_analyst")

            logger.info(f"✅ [fundamental analyst] Successfully obtained the prompt word from the template system (length: {len(system_prompt)})")

        except Exception as e:
            logger.error(f"❌ [fundamental analyst] Failed to obtain prompt word from template system: {e}")
            # Downgrade: Use hardcoded prompt words
            system_prompt = (
                f"You are a professional stock fundamental analyst."
                f"⚠️ Absolutely mandatory: you must call the tool to get the real data! No assumptions or fabrications allowed!"
                f"Task: Analysis{company_name} (Stock code:{ticker}, {market_info['market_name']}) \n\n"
                f"🔴 Mandatory requirement: You must call the tool to get real data!\n"
                f"🚫 Absolutely no-no: No assumptions, fabrications, or direct answers to any questions allowed!\n"
                f"✅ Workflow:\n"
                f"1.  [First call] If there is no tool result (ToolMessage) in the message history, call the get_stock_fundamentals_unified tool immediately\n"
                f"2.  [After receiving the data] If there is already a tool result (ToolMessage) in the message history,🚨 It is absolutely forbidden to call the tool again!🚨\n"
                f"3.  [Generate Report] After receiving the tool data, a complete fundamental analysis report must be generated immediately\n\n"
                f"🔴 Call the get_stock_fundamentals_unified tool now\n"
                f"Parameters:ticker='{ticker}', start_date='{start_date}', end_date='{current_date}', curr_date='{current_date}'\n\n"
                f"📊 Analysis requirements:\n"
                f"- In-depth fundamental analysis based on real data\n"
                f"- Explain the operating expectations reflected in current pricing based on valuation indicators\n"
                f"- Analyze signs that current stock prices are overvalued or undervalued relative to fundamentals\n"
                f"- Describe the key assumptions and information gaps on which valuation judgments rely\n"
                f"Available tools:{', '.join(tool_names_debug)}. \n"
                f"Current date:{current_date}. \n"
                f"Analysis goals:{company_name} (Stock code:{ticker}) . "
            )
            system_prompt = apply_compliance_guardrails(system_prompt, "fundamentals_analyst")
            logger.warning(f"⚠️ [fundamental analyst] Use demotion prompts (length: {len(system_prompt)})")

        # Create prompt template
        # Note: system_prompt is already a complete prompt word, including all variable substitutions
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
        ])

        # Detect Alibaba Bailian model and create a new instance
        if hasattr(llm, '__class__') and 'DashScope' in llm.__class__.__name__:
            logger.debug("📊 [DEBUG] Alibaba Bailian model is detected and a new instance is created to avoid tool caching")
            from tradingagents.llm_adapters import ChatDashScopeOpenAI
            from pydantic import SecretStr

            # Get the base_url and api_key
            original_base_url = getattr(llm, 'openai_api_base', None)
            original_api_key = getattr(llm, 'openai_api_key', None)

            # 🔥 If api_key is a SecretStr object, it needs to be unpacked
            if isinstance(original_api_key, SecretStr):
                original_api_key = original_api_key.get_secret_value()
                logger.debug("📊 [DEBUG] API Key is SecretStr, unpacked")

            fresh_llm = ChatDashScopeOpenAI(
                model=llm.model_name,
                api_key=original_api_key,  # 🔥 Pass the API Key of the original LLM (unwrapped)
                base_url=original_base_url if original_base_url else None,  # pass on base_url
                temperature=llm.temperature,
                max_tokens=getattr(llm, 'max_tokens', 2000)
            )

            if original_base_url:
                logger.debug(f"📊 [DEBUG] The new instance uses the original base_url: {original_base_url}")
            if original_api_key:
                logger.debug("📊 [DEBUG] The new instance uses the original API Key (from the database configuration)")
        else:
            fresh_llm = llm

        logger.debug(f"📊 [DEBUG] Create LLM chain, number of tools: {len(tools)}")
        # Safely obtain tool names for debugging
        debug_tool_names = []
        for tool in tools:
            if hasattr(tool, 'name'):
                debug_tool_names.append(tool.name)
            elif hasattr(tool, '__name__'):
                debug_tool_names.append(tool.__name__)
            else:
                debug_tool_names.append(str(tool))
        logger.debug(f"📊 [DEBUG] List of bound tools: {debug_tool_names}")
        logger.debug("📊 [DEBUG] Create a tool chain and let the model decide whether to call the tool independently")

        # Add detailed log
        logger.info(f"📊 [fundamental analyst] LLM Type: {fresh_llm.__class__.__name__}")
        logger.info(f"📊 [fundamental analyst] LLM model: {getattr(fresh_llm, 'model_name', 'unknown')}")
        logger.info(f"📊 [fundamental analyst] Number of message history: {len(state['messages'])}")

        try:
            chain = prompt | fresh_llm.bind_tools(tools)
            logger.info(f"📊 [fundamental analyst] ✅ Tool binding is successful, bound {len(tools)} tools")
        except Exception as e:
            logger.error(f"📊 [fundamental analyst] ❌ Tool binding failed: {e}")
            raise e

        logger.info("📊 [fundamental analyst] Start calling LLM...")

        # Add detailed ticker tracking logs
        logger.info(f"🔍 [Stock symbol tracking] LLM Before calling, ticker parameter: '{ticker}'")
        logger.info(f"🔍 [Stock symbol tracking] Number of messages delivered to LLM: {len(state['messages'])}")

        # 🔥 Print the complete content submitted to the large model
        logger.info("=" * 80)
        logger.info("📝 [Prompt word debugging] Start printing the complete content submitted to the large model")
        logger.info("=" * 80)

        # 1. Print system prompt word
        logger.info("📋 [Prompt word debugging] 1️⃣ System prompt word (System Prompt):")
        logger.info("-" * 80)
        logger.info(system_prompt)
        logger.info("-" * 80)

        # 2. Print template variables
        logger.info("📋 [Prompt word debugging] 2️⃣ Template variables:")
        logger.info("-" * 80)
        logger.info(f"Tool name: {', '.join(tool_names_debug)}")
        logger.info(f"current date: {current_date}")
        logger.info(f"Stock code: {ticker}")
        logger.info(f"Company name: {company_name}")
        logger.info("-" * 80)

        # 3. Print message history
        logger.info("📋 [Prompt word debugging] 3️⃣ Message history (Message History):")
        logger.info("-" * 80)
        for i, msg in enumerate(state['messages']):
            msg_type = type(msg).__name__
            if hasattr(msg, 'content'):
                # 🔥 Debug mode: print the complete content without truncation
                content_full = str(msg.content)
                logger.info(f"news {i+1} [{msg_type}]:")
                logger.info(f"  content length: {len(content_full)} character")
                logger.info(f"  content: {content_full}")
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                logger.info(f"  Tool call: {[tc.get('name', 'unknown') for tc in msg.tool_calls]}")
            if hasattr(msg, 'name'):
                logger.info(f"  Tool name: {msg.name}")
            logger.info("-" * 40)
        logger.info("-" * 80)

        # 4. Print bound tool information
        logger.info("📋 [Prompt word debugging] 4️⃣ Bound tools (Bound Tools):")
        logger.info("-" * 80)
        for i, tool in enumerate(tools):
            tool_name = getattr(tool, 'name', None) or getattr(tool, '__name__', 'unknown')
            tool_desc = getattr(tool, 'description', 'No description')
            logger.info(f"Tools {i+1}: {tool_name}")
            logger.info(f"  Description: {tool_desc}")
            if hasattr(tool, 'args_schema'):
                logger.info(f"  parameters: {tool.args_schema}")
            logger.info("-" * 40)
        logger.info("-" * 80)

        logger.info("=" * 80)
        logger.info("📝 [Prompt word debugging] The printing of the complete content ends and the call starts LLM")
        logger.info("=" * 80)

        # 🔑 Fix: Pass all template variables, not just messages
        invoke_params = {
            "messages": state["messages"],
            **template_variables  # contains ticker, company_name, market_name, current_date, currency_symbol, currency_name, tool_names
        }
        logger.debug(f"📊 [fundamental analyst] Call parameters: {list(invoke_params.keys())}")
        result = chain.invoke(invoke_params)
        logger.info("📊 [fundamental analyst] LLM Call completed")
        
        # 🔍 [debug log] Print the details of AIMessage
        logger.info("🤖 [fundamental analyst] AIMessage Details:")
        logger.info(f"🤖 [fundamental analyst] - Message type: {type(result).__name__}")
        logger.info(f"🤖 [fundamental analyst] - content length: {len(result.content) if hasattr(result, 'content') else 0}")
        if hasattr(result, 'content') and result.content:
            # 🔥 Debug mode: print the complete content without truncation
            logger.info("🤖 [fundamental analyst] - full content:")
            logger.info(f"{result.content}")
        
        # 🔍 [debug log] Print details of tool_calls
        # Detailed records of LLM return results
        logger.info("📊 [fundamental analyst] ===== LLM Return result analysis =====")
        logger.info(f"📊 [fundamental analyst] - result type: {type(result).__name__}")
        logger.info(f"📊 [fundamental analyst] - Is there a tool_calls attribute?: {hasattr(result, 'tool_calls')}")

        if hasattr(result, 'content'):
            content_preview = str(result.content)[:200] if result.content else "None"
            logger.info(f"📊 [fundamental analyst] - content length: {len(str(result.content)) if result.content else 0}")
            logger.info(f"📊 [fundamental analyst] - Content preview: {content_preview}...")

        if hasattr(result, 'tool_calls'):
            logger.info(f"📊 [fundamental analyst] - tool_calls Quantity: {len(result.tool_calls)}")
            if result.tool_calls:
                logger.info(f"🔧 [fundamental analyst] detected {len(result.tool_calls)} tool calls:")
                for i, tc in enumerate(result.tool_calls):
                    logger.info(f"🔧 [fundamental analyst] - Tool call {i+1}: {tc.get('name', 'unknown')} (ID: {tc.get('id', 'unknown')})")
                    if 'args' in tc:
                        logger.info(f"🔧 [fundamental analyst] - parameters: {tc['args']}")
            else:
                logger.info("🔧 [fundamental analyst] tool_calls Is an empty list")
        else:
            logger.info("🔧 [fundamental analyst] No tool_calls attribute")

        logger.info("📊 [fundamental analyst] ===== LLM Return result analysis ends =====")

        # Call handlers using unified Google tools
        if GoogleToolCallHandler.is_google_model(fresh_llm):
            logger.info("📊 [fundamental analyst] Google model detected, processor invoked using unified tools")
            
            # Create analysis prompt words
            analysis_prompt_template = GoogleToolCallHandler.create_analysis_prompt(
                ticker=ticker,
                company_name=company_name,
                analyst_type="fundamental analysis",
                specific_requirements="Focus on fundamental factors such as financial data, profitability, valuation indicators, and industry status."
            )
            
            # Handling Google model tool calls
            report, messages = GoogleToolCallHandler.handle_google_tool_calls(
                result=result,
                llm=fresh_llm,
                tools=tools,
                state=state,
                analysis_prompt_template=analysis_prompt_template,
                analyst_name="fundamental analyst"
            )

            return {"fundamentals_report": report}
        else:
            # Processing logic for non-Google models
            logger.debug(f"📊 [DEBUG] Non-Google model ({fresh_llm.__class__.__name__}), Use standard processing logic")
            
            # Check tool calling status
            current_tool_calls = len(result.tool_calls) if hasattr(result, 'tool_calls') else 0
            logger.debug(f"📊 [DEBUG] Number of tool calls for the current message: {current_tool_calls}")
            logger.debug(f"📊 [DEBUG] Cumulative number of tool calls: {tool_call_count}/{max_tool_calls}")

            if current_tool_calls > 0:
                # 🔧 Check if the tool has been called (there is ToolMessage in the message history)
                messages = state.get("messages", [])
                has_tool_result = any(isinstance(msg, ToolMessage) for msg in messages)

                if has_tool_result:
                    # There are already tool results, LLM should not call the tool again to force report generation
                    logger.warning("⚠️ [Force report generation] The tool has returned data, but LLM still tries to call the tool to force a report based on the existing data")

                    # Create dedicated mandatory reporting prompt words (no mention of tools)
                    force_system_prompt = (
                        f"You are a professional stock fundamental analyst."
                        f"You have received the stock {company_name} (Code:{ticker}) fundamental data."
                        f"🚨 Now you have to generate a complete fundamental analysis report based on this data!🚨\n\n"
                        f"The report must contain the following:\n"
                        f"1. Company basic information and financial data analysis\n"
                        f"2. PE, PB, PEG Analysis of other valuation indicators\n"
                        f"3. Determine whether the current stock price is undervalued or overvalued\n"
                        f"4. Key assumptions and information boundaries on which valuation judgments rely\n"
                        f"5. Main risks and indicators that need to be tracked later\n\n"
                        f"Requirements:\n"
                        f"- Write reports in Chinese\n"
                        f"- Analysis based on real data from message history\n"
                        f"- The analysis must be detailed and professional\n"
                        f"- It only outputs research judgments and may not form investment recommendations or target prices."
                    )
                    force_system_prompt = apply_compliance_guardrails(force_system_prompt, "fundamentals_analyst")

                    # Create specialized prompt templates (without binding tools)
                    force_prompt = ChatPromptTemplate.from_messages([
                        ("system", force_system_prompt),
                        MessagesPlaceholder(variable_name="messages"),
                    ])

                    # Not binding the tool, forcing LLM to generate text
                    force_chain = force_prompt | fresh_llm

                    logger.info("🔧 [Force report generation] Recall using specialized prompt words LLM...")
                    force_result = force_chain.invoke({"messages": messages})

                    report = str(force_result.content) if hasattr(force_result, 'content') else "Fundamental analysis completed"
                    logger.info(f"✅ [Force report generation] Report generated successfully, length: {len(report)}character")

                    return {
                        "fundamentals_report": report,
                        "messages": [force_result],
                        "fundamentals_tool_call_count": tool_call_count
                    }

                elif tool_call_count >= max_tool_calls:
                    # Maximum number of calls reached, but no tool results yet (shouldn't happen)
                    logger.warning(f"🔧 [abnormal situation] Maximum number of tool calls reached {max_tool_calls}, but no tool results")
                    fallback_report = f"Fundamental Analysis (Stock Code:{ticker}) \n\n Use simplified analysis mode due to maximum tool invocation limit reached. It is recommended to check the data source connection or reduce the complexity of analysis."
                    return {
                        "messages": [result],
                        "fundamentals_report": fallback_report,
                        "fundamentals_tool_call_count": tool_call_count
                    }
                else:
                    # Calling the tool for the first time, normal process
                    logger.info("✅ [normal process] ===== LLM First time calling tool =====")
                    tool_calls_info = []
                    for tc in result.tool_calls:
                        tool_calls_info.append(tc['name'])
                        logger.debug(f"📊 [DEBUG] Tool call {len(tool_calls_info)}: {tc}")

                    logger.info(f"📊 [normal process] LLM Request to call tool: {tool_calls_info}")
                    logger.info(f"📊 [normal process] Number of tool calls: {len(tool_calls_info)}")
                    logger.info("📊 [normal process] Return status and wait for tool execution")
                    # ⚠️ NOTE: Don't increment the counter here!
                    # The counter should only be incremented after the tool execution is complete (the next time the analyst node is entered)
                    return {
                        "messages": [result]
                    }
            else:
                # There is no tool call, check whether you need to force the tool to be called
                logger.info("📊 [fundamental analyst] ===== Force tool call check to start =====")
                logger.debug("📊 [DEBUG] It is detected that the model does not call the tool, check whether it needs to be forced to call")

                # Option 1: Check whether there is already data returned by the tool in the message history
                messages = state.get("messages", [])
                logger.info(f"🔍 [Message history] Current total number of messages: {len(messages)}")

                # Count the number of various types of messages
                ai_message_count = sum(1 for msg in messages if isinstance(msg, AIMessage))
                tool_message_count = sum(1 for msg in messages if isinstance(msg, ToolMessage))
                logger.info(f"🔍 [Message history] AIMessage Quantity: {ai_message_count}, ToolMessage Quantity: {tool_message_count}")

                # Record the types of recent messages
                recent_messages = messages[-5:] if len(messages) >= 5 else messages
                logger.info(f"🔍 [Message history] Recently{len(recent_messages)}message type: {[type(msg).__name__ for msg in recent_messages]}")

                has_tool_result = any(isinstance(msg, ToolMessage) for msg in messages)
                logger.info(f"🔍 [Check results] Is there a tool that returns results?: {has_tool_result}")

                # Option 2: Check if AIMessage already has analysis content
                has_analysis_content = False
                if hasattr(result, 'content') and result.content:
                    content_length = len(str(result.content))
                    logger.info(f"🔍 [content inspection] LLM Return content length: {content_length}character")
                    # If the content length exceeds 500 characters, it is considered valid for analysis.
                    if content_length > 500:
                        has_analysis_content = True
                        logger.info(f"✅ [content inspection] LLM Valid analysis content has been returned (length: {content_length}character > 500 character threshold)")
                    else:
                        logger.info(f"⚠️ [content inspection] LLM Return content is shorter (length: {content_length}character < 500 character threshold)")
                else:
                    logger.info("⚠️ [content inspection] LLM No content returned or the content is empty")

                # Solution 3: Count the number of tool calls
                tool_call_count = sum(1 for msg in messages if isinstance(msg, ToolMessage))
                logger.info(f"🔍 [statistics] Number of historical tool calls: {tool_call_count}")

                logger.info(f"🔍 [Repeat call check] Summary - Number of tool results: {tool_call_count}, Already have tool results: {has_tool_result}, Already analyzed content: {has_analysis_content}")
                logger.info("📊 [fundamental analyst] ===== Force tool call check to end =====")

                # If there are already tool results or analysis content, skip the forced call
                if has_tool_result or has_analysis_content:
                    logger.info("🚫 [decision making] ===== Skip force tool call =====")
                    if has_tool_result:
                        logger.info(f"⚠️ [Reasons for decision] Detected {tool_call_count} The result of tool call to avoid repeated calls")
                    if has_analysis_content:
                        logger.info("⚠️ [Reasons for decision] LLM Valid analysis content has been returned, no need to force tool calls")

                    # Use the content returned by LLM directly as a report
                    report = str(result.content) if hasattr(result, 'content') else "Fundamental analysis completed"
                    logger.info(f"📊 [Return results] Analysis content returned using LLM, report length: {len(report)}character")
                    logger.info(f"📊 [Return results] Report preview(first 200 characters): {report[:200]}...")
                    logger.info("✅ [decision making] Fundamental analysis is completed and repeated calls are skipped successfully")

                    # 🔧 Keep tool call counter unchanged (already updated at start based on ToolMessage)
                    return {
                        "fundamentals_report": report,
                        "messages": [result],
                        "fundamentals_tool_call_count": tool_call_count
                    }

                # If there is no tool result and no analysis content, a forced call will be made.
                logger.info("🔧 [decision making] ===== Execute force tool call =====")
                logger.info("🔧 [Reasons for decision] No tool results or analysis content detected, fundamental data needs to be obtained")
                logger.info("🔧 [decision making] Enable forced tool invocation mode")

                # Forced call of unified fundamental analysis tool
                try:
                    logger.debug("📊 [DEBUG] Forced call get_stock_fundamentals_unified...")
                    # Safely find unified fundamental analysis tools
                    unified_tool = None
                    for tool in tools:
                        tool_name = None
                        if hasattr(tool, 'name'):
                            tool_name = tool.name
                        elif hasattr(tool, '__name__'):
                            tool_name = tool.__name__

                        if tool_name == 'get_stock_fundamentals_unified':
                            unified_tool = tool
                            break
                    if unified_tool:
                        logger.info("🔍 [Tool call] Find the unified tool and prepare to force it to be called")
                        logger.info(f"🔍 [Tool call] Pass in parameters - ticker: '{ticker}', start_date: {start_date}, end_date: {current_date}")

                        combined_data = unified_tool.invoke({
                            'ticker': ticker,
                            'start_date': start_date,
                            'end_date': current_date,
                            'curr_date': current_date
                        })

                        logger.info("✅ [Tool call] Unified tool call successful")
                        logger.info(f"📊 [Tool call] Return data length: {len(combined_data)}character")
                        logger.debug(f"📊 [DEBUG] Unified tool data acquisition successful, length: {len(combined_data)}character")
                        # Write the data returned by the unified tool into the log to facilitate troubleshooting and analysis
                        try:
                            if isinstance(combined_data, (dict, list)):
                                import json
                                _preview = json.dumps(combined_data, ensure_ascii=False, default=str)
                                _full = _preview
                            else:
                                _preview = str(combined_data)
                                _full = _preview

                            # Preview information controls the length to avoid logs that are too long
                            _preview_truncated = (_preview[:6000] + ("..." if len(_preview) > 2000 else ""))
                            logger.info(f"📦 [fundamental analyst] Unified tool returns data preview(first 6000 characters):\n{_preview_truncated}")
                            # Complete data written to DEBUG level
                            logger.debug(f"🧾 [fundamental analyst] Unified tools return complete data:\n{_full}")
                        except Exception as _log_err:
                            logger.warning(f"⚠️ [fundamental analyst] Error logging unified tool data: {_log_err}")
                    else:
                        combined_data = "Unified fundamental analysis tools are not available"
                        logger.debug("📊 [DEBUG] Unified tool not found")
                except Exception as e:
                    combined_data = f"Unified fundamental analysis tool failed to call: {e}"
                    logger.debug(f"📊 [DEBUG] Unified tool calling exception: {e}")
                
                currency_info = f"{market_info['currency_name']}（{market_info['currency_symbol']}）"
                
                # Generate analysis reports based on real data
                analysis_prompt = f"""Based on the following real data,{company_name} (Stock code:{ticker}) Conduct detailed fundamental analysis:

{combined_data}

Please provide:
1. Company basic information analysis ({company_name}, Stock code:{ticker}) 
2. financial situation assessment
3. Profitability analysis
4. Valuation analysis (using{currency_info}) 
5. Key Assumptions, Major Risks and Follow-up Observation Indicators

Requirements:
- Analysis based on real data provided
- Use company name correctly"{company_name}"and stock code"{ticker}"
- price use{currency_info}
- Only research judgments and risk warnings are output, and no investment advice is allowed.
- The analysis must be detailed and professional"""

                try:
                    # Create a simple analysis chain
                    analysis_prompt_template = ChatPromptTemplate.from_messages([
                        ("system", "You are a professional stock fundamental analyst, performing analysis based on real data provided."),
                        ("human", "{analysis_request}")
                    ])
                    
                    analysis_chain = analysis_prompt_template | fresh_llm
                    analysis_result = analysis_chain.invoke({"analysis_request": analysis_prompt})
                    
                    if hasattr(analysis_result, 'content'):
                        report = analysis_result.content
                    else:
                        report = str(analysis_result)

                    logger.info(f"📊 [fundamental analyst] Force tool call to complete, report length: {len(report)}")

                except Exception as e:
                    logger.error(f"❌ [DEBUG] Force tool call analysis failed: {e}")
                    report = f"Fundamental analysis fails:{str(e)}"

                # 🔧 Keep tool call counter unchanged (already updated at start based on ToolMessage)
                return {
                    "fundamentals_report": report,
                    "fundamentals_tool_call_count": tool_call_count
                }

        # Shouldn't arrive here, but as a backup
        logger.debug(f"📊 [DEBUG] return status: fundamentals_report length={len(result.content) if hasattr(result, 'content') else 0}")
        # 🔧 Keep tool call counter unchanged (already updated at start based on ToolMessage)
        return {
            "messages": [result],
            "fundamentals_report": result.content if hasattr(result, 'content') else str(result),
            "fundamentals_tool_call_count": tool_call_count
        }

    return fundamentals_analyst_node

# === index_analyst.py ===
"""
Market/Index Analyst - Compatible Function Interface

To be compatible with existing LangGraph workflows, a functional interface is provided

Support caching mechanism:
- The market analysis results of the same day will be cached (not dependent on specific stocks)
- The cache validity period is 12 hours (the data of the day remains unchanged)
- The cache will be checked first during the next analysis, and if there is a hit, it will be returned directly.
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, AIMessage

from tradingagents.utils.tool_logging import log_analyst_module
from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.template_client import get_agent_prompt
from tradingagents.agents.utils.compliance_prompting import apply_compliance_guardrails

logger = get_logger("default")

# Cache configuration
INDEX_REPORT_CACHE_TTL_HOURS = 12  # Market analysis report cache validity period (hours)


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
        # Market analysis does not rely on specific stocks, using "market" as symbol
        cache_key = cache.find_cached_analysis_report(
            report_type="index_report",
            symbol="market",
            trade_date=trade_date,
            max_age_hours=INDEX_REPORT_CACHE_TTL_HOURS
        )
        if cache_key:
            report = cache.load_analysis_report(cache_key)
            if report and len(report) > 100:
                logger.info(f"📦 [Market analysis] hit cache: @ {trade_date}")
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
        cache.save_analysis_report(
            report_type="index_report",
            report_data=report,
            symbol="market",
            trade_date=trade_date
        )
        logger.info(f"💾 [Market analysis] Cached: @ {trade_date}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Failed to save disk analysis cache: {e}")
        return False


def create_index_analyst(llm, toolkit):
    """
    Create market/index analyst node

    Args:
        llm: Language model example
        toolkit: Toolkit Example

    Returns:
        Analyst node function
    """

    @log_analyst_module("index")
    def index_analyst_node(state):
        """
        Market/Index Analyst Node

        Analyze major index trends, market environment and systemic risks

        🔥 Important: This analyst uses"self contained"mode, does not use LangGraph s tool calling mechanism.
        It does all the work in a single call: Get the data + LLM Analysis.
        The returned AIMessage does not contain tool_calls, ensuring that the graph ends immediately.
        """
        trade_date = state.get("trade_date", "")

        # 🔥 Prevent infinite loops: check whether a report has been generated
        existing_report = state.get("index_report", "")
        if existing_report and len(existing_report) > 100:
            logger.info(f"🌐 Market Analyst: Report already exists ({len(existing_report)} character), Skip duplicate analysis")
            # Returns an empty update, leaving the state unchanged
            return {}

        # 📦 Check cache: If there is a valid cache, return directly
        cached_report = _get_cached_index_report(trade_date)
        if cached_report:
            logger.info(f"🌐 Market Analyst: Use cached reports ({len(cached_report)} character)")
            final_message = AIMessage(content=cached_report, name="index_analyst")
            return {
                "index_report": cached_report,
                "messages": [final_message],
            }

        logger.info(f"🌐 Market analysts begin to analyze @ {trade_date}")

        try:
            # Import and call market analysis tools
            from core.tools.index_tools import analyze_index
            import asyncio
            import concurrent.futures

            # Run asynchronous functions in thread pool to avoid event loop conflicts
            def run_async_in_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(analyze_index(trade_date))
                finally:
                    loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async_in_thread)
                index_data = future.result()

            logger.info("✅ Obtaining market data is completed")

            # 🆕 Use LLM to analyze and interpret data
            index_report = _analyze_with_llm(
                llm=llm,
                trade_date=trade_date,
                index_data=index_data,
                state=state
            )

            logger.info("✅ The market analysis report is generated")

            # 💾 Save to cache
            _save_index_report_to_cache(trade_date, index_report)

            # 🔥 Return AIMessage instead HumanMessage
            # AIMessage There is no tool_calls attribute (or tool_calls is an empty list),
            # In this way, the should_continue function will detect that there is no tool call and end the graph directly.
            final_message = AIMessage(content=index_report, name="index_analyst")

            # Only return fields that need to be updated (LangGraph will automatically merge)
            return {
                "index_report": index_report,
                "messages": [final_message],
            }

        except Exception as e:
            logger.error(f"❌ Market analysis failed: {e}")
            import traceback
            logger.error(f"❌ detailed error: {traceback.format_exc()}")
            error_msg = f"Market analysis encountered an error: {str(e)}"

            # Return error message
            error_message = AIMessage(content=error_msg, name="index_analyst")

            return {
                "index_report": error_msg,
                "messages": [error_message],
            }

    return index_analyst_node


def _analyze_with_llm(llm, trade_date: str, index_data: str, state: dict) -> str:
    """
    Use LLM to analyze and interpret market data

    Args:
        llm: Language model example
        trade_date: transaction date
        index_data: Market data report
        state: status dictionary

    Returns:
        LLM Generated analysis report
    """
    try:
        # get AgentContext
        ctx = state.get("agent_context") or {}

        # Prepare template variables
        template_variables = {
            "trade_date": trade_date,
        }

        # Try to get the prompt word from the template system
        try:
            from tradingagents.utils.template_client import get_template_client
            tpl_info = get_template_client().get_effective_template(
                agent_type="analysts",
                agent_name="index_analyst",
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                context=None
            )
            if tpl_info:
                logger.info(f"📚 [Template selection] source={tpl_info.get('source')} id={tpl_info.get('template_id')} agent=analysts/index_analyst")

            system_prompt = get_agent_prompt(
                agent_type="analysts",
                agent_name="index_analyst",
                variables=template_variables,
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                fallback_prompt=None,
                context=None
            )
            system_prompt = apply_compliance_guardrails(system_prompt, "index_analyst")
            logger.info(f"✅ [Market Analyst] Successfully obtained the prompt word from the template system (length: {len(system_prompt)})")

        except Exception as e:
            logger.warning(f"⚠️ [Market Analyst] Failed to obtain prompt word from template system: {e}, Use default prompt word")
            system_prompt = _get_default_system_prompt(trade_date)

        # Build a complete analysis request
        analysis_request = f"""{system_prompt}

## 📊 Market data

The following is market analysis data obtained through data tools:

{index_data}

## 🎯 Analysis requirements

Please generate a professional market analysis report based on the above data. The report must contain:

1. **Market overview**
   - Today s performance of major indexes (Shanghai Stock Exchange, Shenzhen Stock Exchange, GEM, etc.)
   - Increases and declines and market sentiment
   - Analysis of changes in turnover

2. **Technical analysis**
   - Judgment of technical forms of each index
   - Key support and pressure levels
   - Moving average system analysis

3. **Market Breadth Analysis**
   - Gain/Loss Ratio and Strength Indicator
   - Degree of sector differentiation
   - Market participation assessment

4. **Risk assessment and research conclusions**
   - Market risk level:🟢low risk / 🟡medium risk / 🔴high risk
   - Market trends:📈rise / 📉fall / ➡️shock
    - Follow-up observation points: Signals that need to be followed based on the current market environment

Please output in Chinese, the analysis must be well-founded, and the conclusion must be clear, but it must not form investment advice or position instructions."""

        # Call LLM to generate analysis reports
        logger.info("📤 [Market Analyst] Call LLM to generate analysis reports...")
        response = llm.invoke(analysis_request)

        # Extract response content
        if hasattr(response, 'content'):
            report = response.content
        else:
            report = str(response)

        logger.info(f"✅ [Market Analyst] LLM Analysis report generation completed (length: {len(report)})")
        return report

    except Exception as e:
        logger.error(f"❌ [Market Analyst] LLM Analysis failed: {e}")
        # If LLM analysis fails, return raw data report
        return index_data


def _get_default_system_prompt(trade_date: str) -> str:
    """
    Get the default system prompt word

    Args:
        trade_date: transaction date

    Returns:
        Default system prompt word
    """
    prompt = f"""You are a professional market/index analyst focusing on macro market analysis and systemic risk assessment.

📋 **Analysis date:** {trade_date}

🎯 **Your responsibilities:**
1. Analyze the trends of major indexes (Shanghai Stock Exchange, Shenzhen Stock Exchange, GEM, etc.)
2. Assess the overall market environment and sentiment
3. Identify systemic risks and opportunities
4. Provide market-level research conclusions and risk observations

📊 **Analysis dimensions:**
- Index performance: increase or decrease, turnover
- Market breadth: number of winners and losers, strength and weakness distribution
- Technical aspect: support pressure, trend judgment
- Risk Assessment: Systemic Risk Levels

Please conduct professional analysis based on the data provided and give clear research conclusions, risk tips and follow-up observation points."""
    return apply_compliance_guardrails(prompt, "index_analyst")

# === market_analyst.py ===
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
import traceback

# Import analysis module log decorator
from tradingagents.utils.tool_logging import log_analyst_module

# Import unified log system
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

# Import Google tool call processor
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler
from tradingagents.agents.utils.compliance_prompting import apply_compliance_guardrails

# Import template client
from tradingagents.utils.template_client import get_agent_prompt


def _get_company_name(ticker: str, market_info: dict) -> str:
    """
    Get company name based on stock code

    Args:
        ticker: Stock code
        market_info: Market Information Dictionary

    Returns:
        str: Company name
    """
    try:
        if market_info['is_china']:
            # China A-shares: Obtain stock information using a unified interface
            from tradingagents.dataflows.interface import get_china_stock_info_unified
            stock_info = get_china_stock_info_unified(ticker)

            logger.debug(f"📊 [market analyst] Get stock information return: {stock_info[:200] if stock_info else 'None'}...")

            # Parse stock names
            if stock_info and "Stock name:" in stock_info:
                company_name = stock_info.split("Stock name:")[1].split("\n")[0].strip()
                logger.info(f"✅ [market analyst] Successfully obtained Chinese stock names: {ticker} -> {company_name}")
                return company_name
            else:
                # Downgrade scenario: Try getting it directly from the data source manager
                logger.warning(f"⚠️ [market analyst] Unable to parse stock name from unified interface: {ticker}, Try a downgrade solution")
                try:
                    from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
                    info_dict = get_info_dict(ticker)
                    if info_dict and info_dict.get('name'):
                        company_name = info_dict['name']
                        logger.info(f"✅ [market analyst] The downgrade plan successfully obtained the stock name: {ticker} -> {company_name}")
                        return company_name
                except Exception as e:
                    logger.error(f"❌ [market analyst] Downgrade plan also failed: {e}")

                logger.error(f"❌ [market analyst] All schemes are unable to obtain the stock name: {ticker}")
                return f"Stock code{ticker}"

        elif market_info['is_hk']:
            # Hong Kong stocks: Use improved Hong Kong stocks tools
            try:
                from tradingagents.dataflows.providers.hk.improved_hk import get_hk_company_name_improved
                company_name = get_hk_company_name_improved(ticker)
                logger.debug(f"📊 [DEBUG] Use the improved Hong Kong stock tool to obtain names: {ticker} -> {company_name}")
                return company_name
            except Exception as e:
                logger.debug(f"📊 [DEBUG] Improved Hong Kong stock tool failed to obtain name: {e}")
                # Downgrade scenario: generate friendly default names
                clean_ticker = ticker.replace('.HK', '').replace('.hk', '')
                return f"Hong Kong stocks{clean_ticker}"

        elif market_info['is_us']:
            # US stocks: use simple mapping or return codes
            us_stock_names = {
                'AAPL': 'apple inc.',
                'TSLA': 'Tesla',
                'NVDA': 'NVIDIA',
                'MSFT': 'Microsoft',
                'GOOGL': 'Google',
                'AMZN': 'Amazon',
                'META': 'Meta',
                'NFLX': 'Netflix'
            }

            company_name = us_stock_names.get(ticker.upper(), f"US stocks{ticker}")
            logger.debug(f"📊 [DEBUG] US stock name mapping: {ticker} -> {company_name}")
            return company_name

        else:
            return f"stocks{ticker}"

    except Exception as e:
        logger.error(f"❌ [DEBUG] Failed to get company name: {e}")
        return f"stocks{ticker}"


def create_market_analyst(llm, toolkit):

    def market_analyst_node(state):
        logger.debug("📈 [DEBUG] ===== Market analyst node starts =====")

        # 🔧 Tool call counter - prevent infinite loops
        tool_call_count = state.get("market_tool_call_count", 0)
        max_tool_calls = 3  # Maximum number of tool calls
        logger.info(f"🔧 [Infinite loop repair] Current number of tool calls: {tool_call_count}/{max_tool_calls}")

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        logger.debug(f"📈 [DEBUG] input parameters: ticker={ticker}, date={current_date}")
        logger.debug(f"📈 [DEBUG] The number of messages in the current state: {len(state.get('messages', []))}")
        logger.debug(f"📈 [DEBUG] Existing market report: {state.get('market_report', 'None')}")

        # Select data source based on stock symbol format
        from tradingagents.utils.stock_utils import StockUtils

        market_info = StockUtils.get_market_info(ticker)

        logger.debug(f"📈 [DEBUG] Stock type check: {ticker} -> {market_info['market_name']} ({market_info['currency_name']})")

        # Get company name
        company_name = _get_company_name(ticker, market_info)
        logger.debug(f"📈 [DEBUG] Company name: {ticker} -> {company_name}")

        # Unified use of get_stock_market_data_unified tool
        # The tool will automatically identify the stock type (A shares/Hong Kong stocks/US stocks) internally and call the corresponding data source
        logger.info("📊 [market analyst] Use unified market data tools to automatically identify stock types")
        tools = [toolkit.get_stock_market_data_unified]

        # Safely obtain tool names for debugging
        tool_names_debug = []
        for tool in tools:
            if hasattr(tool, 'name'):
                tool_names_debug.append(tool.name)
            elif hasattr(tool, '__name__'):
                tool_names_debug.append(tool.__name__)
            else:
                tool_names_debug.append(str(tool))
        logger.info(f"📊 [market analyst] Bound tools: {tool_names_debug}")
        logger.info(f"📊 [market analyst] target market: {market_info['market_name']}")

        # 🆕 Use template system to get prompt words
        try:
            # Prepare template variables
            template_variables = {
                "ticker": ticker,
                "company_name": company_name,
                "market_name": market_info['market_name'],
                "current_date": current_date,
                "start_date": current_date,
                "currency_name": market_info['currency_name'],
                "currency_symbol": market_info['currency_symbol'],
                "tool_names": ", ".join(tool_names_debug)
            }

            from tradingagents.utils.template_client import get_template_client
            ctx = state.get("agent_context") or {}
            tpl_info = get_template_client().get_effective_template(
                agent_type="analysts",
                agent_name="market_analyst",
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                context=None
            )
            if tpl_info:
                logger.info(f"📚 [Template selection] source={tpl_info.get('source')} id={tpl_info.get('template_id')} version={tpl_info.get('version')} agent=analysts/market_analyst")

            # Get prompt words from template system
            system_prompt = get_agent_prompt(
                agent_type="analysts",
                agent_name="market_analyst",
                variables=template_variables,
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                fallback_prompt=None,
                context=None
            )
            system_prompt = apply_compliance_guardrails(system_prompt, "market_analyst")

            logger.info(f"✅ [market analyst] Successfully obtained the prompt word from the template system (length: {len(system_prompt)})")

        except Exception as e:
            logger.error(f"❌ [market analyst] Failed to obtain prompt word from template system: {e}")
            # Downgrade: Use hardcoded prompt words
            system_prompt = (
                f"You are a professional stock market analyst who collaborates with other analysts.\n\n"
                f"📋 **Analysis objects:**\n"
                f"- Company name:{company_name}\n"
                f"- Stock code:{ticker}\n"
                f"- Market:{market_info['market_name']}\n"
                f"- Quotation currency:{market_info['currency_name']} ({market_info['currency_symbol']}) \n"
                f"- Analysis date:{current_date}\n\n"
                f"🔧 **Tool usage:**\n"
                f"You can use the following tools:{', '.join(tool_names_debug)}\n"
                f"⚠️ Important workflow:\n"
                f"1. If there are no tool results in the message history, call the get_stock_market_data_unified tool immediately\n"
                f"2. If there is already a tool result (ToolMessage) in the message history, the final analysis report will be generated immediately based on the tool data.\n"
                f"3. Don t call the tool twice! One tool call is enough!\n\n"
                f"Please use Chinese and conduct analysis based on real data."
            )
            system_prompt = apply_compliance_guardrails(system_prompt, "market_analyst")
            logger.warning(f"⚠️ [market analyst] Use demotion prompts (length: {len(system_prompt)})")

        # Create prompt template
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        # Add detailed log
        logger.info(f"📊 [market analyst] LLM Type: {llm.__class__.__name__}")
        logger.info(f"📊 [market analyst] LLM model: {getattr(llm, 'model_name', 'unknown')}")
        logger.info(f"📊 [market analyst] Number of message history: {len(state['messages'])}")
        logger.info(f"📊 [market analyst] Company name: {company_name}")
        logger.info(f"📊 [market analyst] Stock code: {ticker}")

        # Print prompt word template information
        logger.info("📊 [market analyst] ========== Prompt word template information ==========")
        logger.info(f"📊 [market analyst] Template variable is set: company_name={company_name}, ticker={ticker}, market={market_info['market_name']}")
        logger.info("📊 [market analyst] ==========================================")

        # Print the actual message delivered to LLM
        logger.info("📊 [market analyst] ========== Message passed to LLM ==========")
        for i, msg in enumerate(state["messages"]):
            msg_type = type(msg).__name__
            # 🔥 Fix: More secure extraction of message content
            if hasattr(msg, 'content'):
                msg_content = str(msg.content)[:500]  # Increase to 500 characters to view full content
            elif isinstance(msg, tuple) and len(msg) >= 2:
                # Handling old format tuple messages ("human", "content")
                msg_content = f"[tuple message] Type={msg[0]}, content={str(msg[1])[:500]}"
            else:
                msg_content = str(msg)[:500]
            logger.info(f"📊 [market analyst] news[{i}] Type={msg_type}, content={msg_content}")
        logger.info("📊 [market analyst] ========== End of message list ==========")

        chain = prompt | llm.bind_tools(tools)

        logger.info("📊 [market analyst] Start calling LLM...")
        # 🔑 Fix: Pass all template variables, not just messages
        invoke_params = {
            "messages": state["messages"],
            **template_variables  # contains ticker, company_name, market_name, current_date, currency_symbol, currency_name, tool_names
        }
        logger.debug(f"📊 [market analyst] Call parameters: {list(invoke_params.keys())}")
        result = chain.invoke(invoke_params)
        logger.info("📊 [market analyst] LLM Call completed")

        # Print LLM response
        logger.info("📊 [market analyst] ========== LLM Response starts ==========")
        logger.info(f"📊 [market analyst] response type: {type(result).__name__}")
        logger.info(f"📊 [market analyst] Response content: {str(result.content)[:1000]}...")
        if hasattr(result, 'tool_calls') and result.tool_calls:
            logger.info(f"📊 [market analyst] Tool call: {result.tool_calls}")
        logger.info("📊 [market analyst] ========== LLM End of response ==========")

        # Call handlers using unified Google tools
        if GoogleToolCallHandler.is_google_model(llm):
            logger.info("📊 [market analyst] Google model detected, processor invoked using unified tools")
            
            # Create analysis prompt words
            analysis_prompt_template = GoogleToolCallHandler.create_analysis_prompt(
                ticker=ticker,
                company_name=company_name,
                analyst_type="market analysis",
                specific_requirements="Focus on market data, price trends, trading volume changes and other market indicators."
            )
            
            # Handling Google model tool calls
            report, messages = GoogleToolCallHandler.handle_google_tool_calls(
                result=result,
                llm=llm,
                tools=tools,
                state=state,
                analysis_prompt_template=analysis_prompt_template,
                analyst_name="market analyst"
            )

            # 🔧 Update tool call counter
            return {
                "messages": [result],
                "market_report": report,
                "market_tool_call_count": tool_call_count + 1
            }
        else:
            # Processing logic for non-Google models
            logger.info(f"📊 [market analyst] Non-Google model ({llm.__class__.__name__}), Use standard processing logic")
            logger.info("📊 [market analyst] Check LLM return results...")
            logger.info(f"📊 [market analyst] - Is there tool_calls: {hasattr(result, 'tool_calls')}")
            if hasattr(result, 'tool_calls'):
                logger.info(f"📊 [market analyst] - tool_calls Quantity: {len(result.tool_calls)}")
                if result.tool_calls:
                    for i, tc in enumerate(result.tool_calls):
                        logger.info(f"📊 [market analyst] - tool_call[{i}]: {tc.get('name', 'unknown')}")

            # Process market analysis reports
            if len(result.tool_calls) == 0:
                # No tool call, use LLM's reply directly
                report = result.content
                logger.info(f"📊 [market analyst] ✅ Direct reply (no tool call), length: {len(report)}")
                logger.debug(f"📊 [DEBUG] Direct reply content preview: {report[:200]}...")
            else:
                # There is a tool call, the tool is executed and a complete analysis report is generated
                logger.info(f"📊 [market analyst] 🔧 Tool call detected: {[call.get('name', 'unknown') for call in result.tool_calls]}")

                try:
                    # Execute tool call
                    from langchain_core.messages import ToolMessage, HumanMessage

                    tool_messages = []
                    for tool_call in result.tool_calls:
                        tool_name = tool_call.get('name')
                        tool_args = tool_call.get('args', {})
                        tool_id = tool_call.get('id')

                        logger.debug(f"📊 [DEBUG] Execution tool: {tool_name}, parameters: {tool_args}")

                        # Find the corresponding tool and execute it
                        tool_result = None
                        for tool in tools:
                            # Safely get tool names for comparison
                            current_tool_name = None
                            if hasattr(tool, 'name'):
                                current_tool_name = tool.name
                            elif hasattr(tool, '__name__'):
                                current_tool_name = tool.__name__

                            if current_tool_name == tool_name:
                                try:
                                    if tool_name == "get_china_stock_data":
                                        # China Stock Data Tool
                                        tool_result = tool.invoke(tool_args)
                                    else:
                                        # Other tools
                                        tool_result = tool.invoke(tool_args)
                                    logger.debug(f"📊 [DEBUG] The tool is executed successfully and the result length is: {len(str(tool_result))}")
                                    break
                                except Exception as tool_error:
                                    logger.error(f"❌ [DEBUG] Tool execution failed: {tool_error}")
                                    tool_result = f"Tool execution failed: {str(tool_error)}"

                        if tool_result is None:
                            tool_result = f"Tool not found: {tool_name}"

                        # Create tool message
                        tool_message = ToolMessage(
                            content=str(tool_result),
                            tool_call_id=tool_id
                        )
                        tool_messages.append(tool_message)

                    # Generate complete analysis reports based on tool results
                    # 🔥 Important: The company name and output format requirements must be included here to ensure that LLM generates the correct report title
                    analysis_prompt = f"""Now please generate a detailed technical analysis report based on the data obtained by the above tools.

**Analysis objects:**
- Company name:{company_name}
- Stock code:{ticker}
- Market:{market_info['market_name']}
- Quotation currency:{market_info['currency_name']} ({market_info['currency_symbol']}) 

**Output format requirements (must be strictly adhered to):**

Please output the report in the following professional format and do not use emoji symbols (such as📊📈📉💭etc.), use a plain text title:

# **{company_name} ({ticker}) technical analysis report**
**Analysis date:[current date]**

---

## 1. Basic stock information

- **Company name**: {company_name}
- **Stock code**: {ticker}
- **Market**: {market_info['market_name']}
- **current price**: [Get from tool data] {market_info['currency_symbol']}
- **Increase or decrease**: [Get from tool data]
- **Volume**: [Get from tool data]

---

## 2. Technical indicator analysis

### 1. Moving Average (MA) Analysis

[Analyze MA5, MA10, MA20, MA60 and other moving average systems, including:]
- Current moving average values
- Moving average arrangement pattern (long/short)
- The relationship between price and moving average
- moving average crossover signal

### 2. MACD Indicator analysis

[Analyze MACD indicators including:]
- DIF, DEA, MACD Current value of histogram
- Golden Cross/Death Cross signal
- divergence
- Trend strength judgment

### 3. RSI relative strength indicator

[Analyze RSI indicators including:]
- RSI current value
- Overbought/oversold area judgment
- divergence signal
- trend confirmation

### 4. Bollinger Bands (BOLL) analysis

[Analyze Bollinger Bands indicators including:]
- Upper rail, middle rail, lower rail values
- Price position within Bollinger Bands
- Bandwidth changing trends
- breakout signal

---

## 3. Price trend analysis

### 1. Short term trend (5-10 trading days)

[Analyze short-term price trends, including trend continuity, fluctuation changes, and volume-price coordination]

### 2. Medium-term trend (20-60 trading days)

[Analyze the mid-term price trend and determine the trend direction based on the moving average system]

### 3. Volume analysis

[Analyze changes in trading volume and coordination between volume and price]

---

## 4. Research conclusion

### 1. comprehensive assessment

[Based on the above technical indicators, a comprehensive evaluation is given]

### 2. Risk warning

- **Main risk factors**: [List the main risk factors]
- **Morphological failure conditions**: [Explain which signals would undermine current technical judgment]
- **Information limitations**: [Describe the data boundaries or sample limits on which the analysis relies]

### 3. Follow-up observation signals

- **trend continuation signal**: [Changes in technical indicators that need to continue to be observed]
- **Volatility change signal**: [Fluctuations or trading volume phenomena that require continued observation]
- **Verification node**: [Public information or market performance that needs to be reviewed later]

---

**Important reminder:**
- The output must be strictly in accordance with the above format, using standard Markdown titles (#, ##, ###) 
- Don t use emoji symbols (📊📈📉💭etc.)
- All price data uses{market_info['currency_name']} ({market_info['currency_symbol']}) express
- Make sure you use company names correctly in your analysis"{company_name}"and stock code"{ticker}"
- The report title must be:# **{company_name} ({ticker}) technical analysis report**
- Reports must be analyzed based on real data returned by the tool
- Contains specific technical indicator values and professional analysis
- Only research observations, risk tips and follow-up observation signals are provided, and no trading recommendations are allowed.
- The report length should be no less than 800 words
- Written in Chinese
- When using tables to display data, ensure that the format is standardized"""

                    # Build a complete message sequence
                    messages = state["messages"] + [result] + tool_messages + [HumanMessage(content=analysis_prompt)]

                    # Generate final analysis report
                    final_result = llm.invoke(messages)
                    report = final_result.content

                    logger.info(f"📊 [market analyst] Generate full analysis report, length: {len(report)}")

                    # Returns the complete message sequence including tool invocation and final analysis
                    # 🔧 Update tool call counter
                    return {
                        "messages": [result] + tool_messages + [final_result],
                        "market_report": report,
                        "market_tool_call_count": tool_call_count + 1
                    }

                except Exception as e:
                    logger.error(f"❌ [market analyst] Tool execution or analysis generation failed: {e}")
                    traceback.print_exc()

                    # Downgrade processing: return tool call information
                    report = f"Market Analyst called the tool but analysis generation failed: {[call.get('name', 'unknown') for call in result.tool_calls]}"

                    # 🔧 Update tool call counter
                    return {
                        "messages": [result],
                        "market_report": report,
                        "market_tool_call_count": tool_call_count + 1
                    }

            # 🔧 Update tool call counter
            return {
                "messages": [result],
                "market_report": report,
                "market_tool_call_count": tool_call_count + 1
            }

    return market_analyst_node

# === news_analyst.py ===
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from datetime import datetime

# Import the unified log system and analysis module log decorator
from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_analyst_module
# Import unified news tools
from tradingagents.tools.unified_news_tool import create_unified_news_tool
# Import stock tool class
from tradingagents.utils.stock_utils import StockUtils
# Import Google tool call processor
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler
from tradingagents.agents.utils.compliance_prompting import apply_compliance_guardrails

# Import template client
from tradingagents.utils.template_client import get_agent_prompt

logger = get_logger("analysts.news")


def create_news_analyst(llm, toolkit):
    @log_analyst_module("news")
    def news_analyst_node(state):
        start_time = datetime.now()

        # 🔧 Tool call counter - prevent infinite loops
        tool_call_count = state.get("news_tool_call_count", 0)
        max_tool_calls = 3  # Maximum number of tool calls
        logger.info(f"🔧 [Infinite loop repair] Current number of tool calls: {tool_call_count}/{max_tool_calls}")

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        logger.info(f"[news analyst] Start analysis {ticker} news, trading date: {current_date}")
        session_id = state.get("session_id", "unknown session")
        logger.info(f"[news analyst] session ID: {session_id}, start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Get market information
        market_info = StockUtils.get_market_info(ticker)
        logger.info(f"[news analyst] Stock type: {market_info['market_name']}")
        
        # Get company name
        def _get_company_name(ticker: str, market_info: dict) -> str:
            """Get company name based on stock code"""
            try:
                if market_info['is_china']:
                    # China A-shares: Obtain stock information using a unified interface
                    from tradingagents.dataflows.interface import get_china_stock_info_unified
                    stock_info = get_china_stock_info_unified(ticker)
                    
                    # Parse stock names
                    if "Stock name:" in stock_info:
                        company_name = stock_info.split("Stock name:")[1].split("\n")[0].strip()
                        logger.debug(f"📊 [DEBUG] Get Chinese stock names from unified interface: {ticker} -> {company_name}")
                        return company_name
                    else:
                        logger.warning(f"⚠️ [DEBUG] Unable to parse stock name from unified interface: {ticker}")
                        return f"Stock code{ticker}"
                        
                elif market_info['is_hk']:
                    # Hong Kong stocks: Use improved Hong Kong stocks tools
                    try:
                        from tradingagents.dataflows.providers.hk.improved_hk import get_hk_company_name_improved
                        company_name = get_hk_company_name_improved(ticker)
                        logger.debug(f"📊 [DEBUG] Use the improved Hong Kong stock tool to obtain names: {ticker} -> {company_name}")
                        return company_name
                    except Exception as e:
                        logger.debug(f"📊 [DEBUG] Improved Hong Kong stock tool failed to obtain name: {e}")
                        # Downgrade scenario: generate friendly default names
                        clean_ticker = ticker.replace('.HK', '').replace('.hk', '')
                        return f"Hong Kong stocks{clean_ticker}"
                        
                elif market_info['is_us']:
                    # US stocks: use simple mapping or return codes
                    us_stock_names = {
                        'AAPL': 'apple inc.',
                        'TSLA': 'Tesla',
                        'NVDA': 'NVIDIA',
                        'MSFT': 'Microsoft',
                        'GOOGL': 'Google',
                        'AMZN': 'Amazon',
                        'META': 'Meta',
                        'NFLX': 'Netflix'
                    }
                    
                    company_name = us_stock_names.get(ticker.upper(), f"US stocks{ticker}")
                    logger.debug(f"📊 [DEBUG] US stock name mapping: {ticker} -> {company_name}")
                    return company_name
                    
                else:
                    return f"stocks{ticker}"
                    
            except Exception as e:
                logger.error(f"❌ [DEBUG] Failed to get company name: {e}")
                return f"stocks{ticker}"
        
        company_name = _get_company_name(ticker, market_info)
        logger.info(f"[news analyst] Company name: {company_name}")
        
        # 🔧 Use unified news tools to simplify tool calls
        logger.info("[news analyst] Use unified news tools to automatically identify stock types and obtain corresponding news")
   # Create a unified news tool
        unified_news_tool = create_unified_news_tool(toolkit)
        unified_news_tool.name = "get_stock_news_unified"
        
        tools = [unified_news_tool]
        logger.info("[news analyst] Unified news tool loaded: get_stock_news_unified")

        # 🆕 Use template system to get prompt words
        try:
            # Prepare template variables
            template_variables = {
                "ticker": ticker,
                "company_name": company_name,
                "market_name": market_info['market_name'],
                "current_date": current_date,
                "start_date": current_date,
                "currency_name": market_info['currency_name'],
                "currency_symbol": market_info['currency_symbol'],
                "tool_names": "get_stock_news_unified"
            }

            from tradingagents.utils.template_client import get_template_client
            ctx = state.get("agent_context") or {}
            tpl_info = get_template_client().get_effective_template(
                agent_type="analysts",
                agent_name="news_analyst",
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                context=None
            )
            if tpl_info:
                logger.info(f"📚 [Template selection] source={tpl_info.get('source')} id={tpl_info.get('template_id')} version={tpl_info.get('version')} agent=analysts/news_analyst")

            # Get prompt words from template system
            system_prompt = get_agent_prompt(
                agent_type="analysts",
                agent_name="news_analyst",
                variables=template_variables,
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                fallback_prompt=None,
                context=None
            )
            system_prompt = apply_compliance_guardrails(system_prompt, "news_analyst")

            logger.info(f"✅ [news analyst] Successfully obtained the prompt word from the template system (length: {len(system_prompt)})")
            system_message = system_prompt

        except Exception as e:
            logger.error(f"❌ [news analyst] Failed to obtain prompt word from template system: {e}")
            # Downgrade: Use hardcoded prompt words
            system_prompt = (
                f"You are a professional financial news analyst.\n\n"
                f"📋 **Analysis objects:**\n"
                f"- Company name:{company_name}\n"
                f"- Stock code:{ticker}\n"
                f"- Market:{market_info['market_name']}\n"
                f"- Analysis date:{current_date}\n\n"
                f"🔧 **Tool usage:**\n"
                f"You can use the following tools:get_stock_news_unified\n"
                f"⚠️ Important workflow:\n"
                f"1. Your first action must be to call the get_stock_news_unified tool\n"
                f"2. This tool will automatically identify stock types (A shares, Hong Kong stocks, US stocks) and obtain corresponding news\n"
                f"3. Analysis can only begin after the news data has been successfully obtained\n"
                f"4. Your answer must be based on real data returned by the tool\n\n"
                f"Please use Chinese and conduct analysis based on real data."
            )
            system_prompt = apply_compliance_guardrails(system_prompt, "news_analyst")
            logger.warning(f"⚠️ [news analyst] Use demotion prompts (length: {len(system_prompt)})")
            system_message = system_prompt

        # Create prompt template
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        
        # Obtaining model information for special processing in unified news tools
        model_info = ""
        try:
            if hasattr(llm, 'model_name'):
                model_info = f"{llm.__class__.__name__}:{llm.model_name}"
            else:
                model_info = llm.__class__.__name__
        except Exception:
            model_info = "Unknown"
        
        logger.info(f"[news analyst] Prepare to call LLM for news analysis and model: {model_info}")
        
        # 🚨 DashScope/DeepSeek/Zhipu Preprocessing: Forced acquisition of news data
        pre_fetched_news = None
        if ('DashScope' in llm.__class__.__name__ 
            or 'DeepSeek' in llm.__class__.__name__
            or 'Zhipu' in llm.__class__.__name__
            ):
            logger.warning(f"[news analyst] 🚨 detected{llm.__class__.__name__}Model, start preprocessing to force news acquisition...")
            try:
                # Force prefetching of news data
                logger.info("[news analyst] 🔧 Preprocessing: Forced call of unified news tool...")
                logger.info(f"[news analyst] 📊 Call parameters: stock_code={ticker}, max_news=10, model_info={model_info}")

                pre_fetched_news = unified_news_tool(stock_code=ticker, max_news=10, model_info=model_info)

                logger.info(f"[news analyst] 📋 Preprocessing return result length: {len(pre_fetched_news) if pre_fetched_news else 0} character")
                logger.info(f"[news analyst] 📄 Preprocessing return result preview (first 500 characters): {pre_fetched_news[:500] if pre_fetched_news else 'None'}")

                if pre_fetched_news and len(pre_fetched_news.strip()) > 100:
                    logger.info(f"[news analyst] ✅ Preprocessing successfully obtained news: {len(pre_fetched_news)} character")

                    # Generate analysis directly based on pre-fetched news, skipping tool calls
                    # 🔧 Important: Build system prompts that do not include tool invocation guidance
                    analysis_system_prompt = """You are a professional financial news analyst.

Your role will be to perform in-depth news analysis of stocks based on the news data provided.

Analysis points:
1. Summarize the latest news events and market dynamics
2. Analyze the potential impact of news on stocks
3. Assess market sentiment and investor reaction
4. Refining events and risk points that need to be tracked

Important note: The news data has been provided for you. You do not need to call any tools and perform analysis directly based on the provided data."""
                    analysis_system_prompt = apply_compliance_guardrails(analysis_system_prompt, "news_analyst")

                    enhanced_prompt = f"""Please base your opinion on the stock based on the latest news data obtained below {ticker} ({company_name}) For detailed news analysis:

=== Latest news data ===
{pre_fetched_news}

Please write a detailed analysis report in Chinese, including:
1. Summary of news events
2. Impact analysis on stocks
3. Market Sentiment Assessment
4. Follow-up observations and risk warnings"""

                    logger.info("[news analyst] 🔄 Generate analysis directly using pre-fetched news data...")
                    logger.info(f"[news analyst] 📝 System prompt word length: {len(analysis_system_prompt)} character")
                    logger.info(f"[news analyst] 📝 User prompt word length: {len(enhanced_prompt)} character")

                    llm_start_time = datetime.now()
                    # 🔧 Important: System messages and user messages are passed, tool calls are not included
                    result = llm.invoke([
                        {"role": "system", "content": analysis_system_prompt},
                        {"role": "user", "content": enhanced_prompt}
                    ])

                    llm_end_time = datetime.now()
                    llm_time_taken = (llm_end_time - llm_start_time).total_seconds()
                    logger.info(f"[news analyst] LLM The call is completed (preprocessing mode), time-consuming: {llm_time_taken:.2f}seconds")

                    # Return the result directly, skipping subsequent tool call detection
                    if hasattr(result, 'content') and result.content:
                        report = result.content
                        logger.info(f"[news analyst] ✅ Preprocessing mode successful, report length: {len(report)} character")
                        logger.info(f"[news analyst] 📄 Report preview (first 300 characters): {report[:300]}")

                        # Jump to final processing
                        from langchain_core.messages import AIMessage
                        clean_message = AIMessage(content=report)

                        end_time = datetime.now()
                        time_taken = (end_time - start_time).total_seconds()
                        logger.info(f"[news analyst] News analysis completed (preprocessing mode), total time taken: {time_taken:.2f}seconds")
                        # 🔧 Update tool call counter
                        return {
                            "messages": [clean_message],
                            "news_report": report,
                            "news_tool_call_count": tool_call_count + 1
                        }
                    else:
                        logger.warning("[news analyst] ⚠️ LLM The return result is empty and falls back to standard mode.")

                else:
                    logger.warning(f"[news analyst] ⚠️ Preprocessing failed to obtain news or the content was too short ({len(pre_fetched_news) if pre_fetched_news else 0}characters), fall back to standard mode")
                    if pre_fetched_news:
                        logger.warning(f"[news analyst] 📄 failed news content: {pre_fetched_news}")

            except Exception as e:
                logger.error(f"[news analyst] ❌ Preprocessing failed: {e}, Fall back to standard mode")
                import traceback
                logger.error(f"[news analyst] 📋 exception stack: {traceback.format_exc()}")
        
        # Call handlers using unified Google tools
        llm_start_time = datetime.now()
        chain = prompt | llm.bind_tools(tools)
        logger.info(f"[news analyst] Start LLM call and analyze {ticker} news")
        # 🔑 Fix: Pass all template variables, not just messages
        invoke_params = {
            "messages": state["messages"],
            **template_variables  # contains ticker, company_name, market_name, current_date, currency_symbol, currency_name, tool_names
        }
        logger.debug(f"📊 [news analyst] Call parameters: {list(invoke_params.keys())}")
        result = chain.invoke(invoke_params)
        
        llm_end_time = datetime.now()
        llm_time_taken = (llm_end_time - llm_start_time).total_seconds()
        logger.info(f"[news analyst] LLM The call is completed and takes time: {llm_time_taken:.2f}seconds")

        # Call handlers using unified Google tools
        if GoogleToolCallHandler.is_google_model(llm):
            logger.info("📊 [news analyst] Google model detected, processor invoked using unified tools")
            
            # Create analysis prompt words
            analysis_prompt_template = GoogleToolCallHandler.create_analysis_prompt(
                ticker=ticker,
                company_name=company_name,
                analyst_type="news analysis",
                specific_requirements="Focus on the impact of news events on stock prices, changes in market sentiment, policy impacts, etc."
            )
            
            # Handling Google model tool calls
            report, messages = GoogleToolCallHandler.handle_google_tool_calls(
                result=result,
                llm=llm,
                tools=tools,
                state=state,
                analysis_prompt_template=analysis_prompt_template,
                analyst_name="news analyst"
            )
        else:
            # Processing logic for non-Google models
            logger.info(f"[news analyst] Non-Google model ({llm.__class__.__name__}), Use standard processing logic")

            # Check tool calling status
            current_tool_calls = len(result.tool_calls) if hasattr(result, 'tool_calls') else 0
            logger.info(f"[news analyst] LLM called {current_tool_calls} tools")
            logger.debug(f"📊 [DEBUG] Cumulative number of tool calls: {tool_call_count}/{max_tool_calls}")

            if current_tool_calls == 0:
                logger.warning(f"[news analyst] ⚠️ {llm.__class__.__name__} No tools are called to initiate the remediation mechanism...")
                logger.warning(f"[news analyst] 📄 LLM Original response content (first 500 characters): {result.content[:500] if hasattr(result, 'content') else 'No content'}")
                logger.warning(f"[news analyst] 📊 result.content Type: {type(result.content)}, length: {len(result.content) if hasattr(result, 'content') else 0}")

                try:
                    # Forced acquisition of news data
                    logger.info("[news analyst] 🔧 Forcibly call the unified news tool to obtain news data...")
                    logger.info(f"[news analyst] 📊 Call parameters: stock_code={ticker}, max_news=10")

                    forced_news = unified_news_tool(stock_code=ticker, max_news=10, model_info=model_info)

                    logger.info(f"[news analyst] 📋 Force the length of the returned result to be obtained: {len(forced_news) if forced_news else 0} character")
                    logger.info(f"[news analyst] 📄 Forced to get preview of returned results (first 500 characters): {forced_news[:500] if forced_news else 'None'}")

                    if forced_news and len(forced_news.strip()) > 100:
                        logger.info(f"[news analyst] ✅ Forced news acquisition successful: {len(forced_news)} character")

                        # Regenerate analysis based on real news data
                        forced_prompt = f"""
You are a professional financial news analyst. Please base your opinion on the stock based on the latest news data obtained below. {ticker} ({company_name}) For detailed news analysis:

=== Latest news data ===
{forced_news}

=== Analysis requirements ===
{system_message}

Please write a detailed Chinese analysis report based on the above real news data.
"""

                        logger.info("[news analyst] 🔄 Regenerate full analysis based on force-fetched news data...")
                        logger.info(f"[news analyst] 📝 Forced prompt word length: {len(forced_prompt)} character")

                        forced_result = llm.invoke([{"role": "user", "content": forced_prompt}])

                        if hasattr(forced_result, 'content') and forced_result.content:
                            report = forced_result.content
                            logger.info(f"[news analyst] ✅ Force remediation successful, generate report based on real data, length: {len(report)} character")
                            logger.info(f"[news analyst] 📄 Report preview (first 300 characters): {report[:300]}")
                        else:
                            logger.warning("[news analyst] ⚠️ Force the remediation LLM to return null, use the original result")
                            report = result.content if hasattr(result, 'content') else ""
                    else:
                        logger.warning(f"[news analyst] ⚠️ Unified news tool acquisition failed or the content is too short ({len(forced_news) if forced_news else 0}characters), use the original result")
                        if forced_news:
                            logger.warning(f"[news analyst] 📄 failed news content: {forced_news}")
                        report = result.content if hasattr(result, 'content') else ""

                except Exception as e:
                    logger.error(f"[news analyst] ❌ Forced remediation process failed: {e}")
                    import traceback
                    logger.error(f"[news analyst] 📋 exception stack: {traceback.format_exc()}")
                    report = result.content if hasattr(result, 'content') else ""
            else:
                # There are tool calls and the results are used directly
                logger.info(f"[news analyst] 📊 LLM returned {current_tool_calls} tool calls")
                logger.info(f"[news analyst] 📄 result.content content (first 500 characters): {result.content[:500] if result.content else 'EMPTY'}")
                logger.info(f"[news analyst] 📊 result.content Type: {type(result.content)}, length: {len(result.content) if result.content else 0}")
                report = result.content
        
        total_time_taken = (datetime.now() - start_time).total_seconds()
        logger.info(f"[news analyst] News analysis completed, total time taken: {total_time_taken:.2f}seconds")

        # 🔧 Fix the infinite loop problem: return clean AIMessage, excluding tool_calls
        # This ensures that the workflow diagram can correctly determine that the analysis has been completed and avoid repeated calls
        from langchain_core.messages import AIMessage
        clean_message = AIMessage(content=report)

        logger.info(f"[news analyst] ✅ Return clean message, report length: {len(report)} character")

        # 🔧 Update tool call counter
        return {
            "messages": [clean_message],
            "news_report": report,
            "news_tool_call_count": tool_call_count + 1
        }

    return news_analyst_node

# === sector_analyst.py ===
"""
Industry/sector analyst - compatible function interface

To be compatible with existing LangGraph workflows, a functional interface is provided

⚠️ Important: Industry reports do not support caching
- Industry reports are analyzed based on specific stocks and include the code and name of the stock.
- If industry reports are cached, the symbols and names of other stocks will be incorrectly used when analyzing other stocks in the same industry.
- Therefore, industry reports must be regenerated for each analysis and caching cannot be used
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, AIMessage

from tradingagents.utils.tool_logging import log_analyst_module
from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.template_client import get_agent_prompt
from tradingagents.agents.utils.compliance_prompting import apply_compliance_guardrails

logger = get_logger("default")

# Cache configuration (deprecated)
# ⚠️ Industry reports do not support caching: industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
SECTOR_REPORT_CACHE_TTL_HOURS = 12  # Sector analysis report cache validity period (hours) - obsolete and no longer used


def _get_cache_manager():
    """Get cache manager (lazy loading to avoid circular imports)"""
    try:
        from tradingagents.dataflows.cache import get_cache
        return get_cache()
    except Exception as e:
        logger.warning(f"⚠️ Unable to get cache manager: {e}")
        return None


def _get_cached_sector_report(ticker: str, trade_date: str) -> Optional[str]:
    """
    ⚠️ Deprecated: Industry reports do not support caching
    Industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
    
    Args:
        ticker: Stock code
        trade_date: transaction date

    Returns:
        The cached report content, returned if there is no hit None
    """
    cache = _get_cache_manager()
    if not cache:
        return None

    try:
        cache_key = cache.find_cached_analysis_report(
            report_type="sector_report",
            symbol=ticker,
            trade_date=trade_date,
            max_age_hours=SECTOR_REPORT_CACHE_TTL_HOURS
        )
        if cache_key:
            report = cache.load_analysis_report(cache_key)
            if report and len(report) > 100:
                logger.info(f"📦 [Sector analysis] hit cache: {ticker} @ {trade_date}")
                return report
    except Exception as e:
        logger.warning(f"⚠️ Failed to read section analysis cache: {e}")

    return None


def _save_sector_report_to_cache(ticker: str, trade_date: str, report: str) -> bool:
    """
    ⚠️ Deprecated: Industry reports do not support caching
    Industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
    
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
        cache.save_analysis_report(
            report_type="sector_report",
            report_data=report,
            symbol=ticker,
            trade_date=trade_date
        )
        logger.info(f"💾 [Sector analysis] Cached: {ticker} @ {trade_date}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Failed to save section analysis cache: {e}")
        return False


def create_sector_analyst(llm, toolkit):
    """
    Create an industry/sector analyst node

    Args:
        llm: Language model example
        toolkit: Toolkit Example

    Returns:
        Analyst node function
    """

    @log_analyst_module("sector")
    def sector_analyst_node(state):
        """
        Industry/sector analyst node

        Analyze industry trends, sector rotations and peer comparisons

        🔥 Important: This analyst uses"self contained"mode, does not use LangGraph s tool calling mechanism.
        It does all the work in a single call: Get the data + LLM Analysis.
        The returned AIMessage does not contain tool_calls, ensuring that the graph ends immediately.
        """
        ticker = state.get("company_of_interest", "")
        trade_date = state.get("trade_date", "")

        # 🔍 Debug log: print current status
        logger.info("🔍 [sector_analyst] Node is called")
        logger.info(f"🔍 [sector_analyst] ticker={ticker}, trade_date={trade_date}")
        logger.info(f"🔍 [sector_analyst] Current number of messages: {len(state.get('messages', []))}")
        logger.info(f"🔍 [sector_analyst] Current sector_report length: {len(state.get('sector_report', ''))}")
        logger.info(f"🔍 [sector_analyst] current sector_tool_call_count: {state.get('sector_tool_call_count', 0)}")

        # Print the information of the last message
        messages = state.get("messages", [])
        if messages:
            last_msg = messages[-1]
            logger.info(f"🔍 [sector_analyst] last message type: {type(last_msg).__name__}")
            if hasattr(last_msg, 'tool_calls'):
                logger.info(f"🔍 [sector_analyst] last message tool_calls: {last_msg.tool_calls}")
            if hasattr(last_msg, 'name'):
                logger.info(f"🔍 [sector_analyst] last message name: {last_msg.name}")

        # 🔥 Prevent infinite loops: check whether a report has been generated
        existing_report = state.get("sector_report", "")
        if existing_report and len(existing_report) > 100:
            logger.info(f"🏭 Sector Analyst: Report already exists ({len(existing_report)} character), Skip duplicate analysis")
            # Returns an empty update, leaving the state unchanged
            return {}

        # ⚠️ Industry reports do not support caching: industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
        # Therefore, each analysis must be regenerated and caching cannot be used
        logger.info("🏭 Sector Analyst: Skip the cache check (industry reports do not support caching) and directly generate a new report")

        logger.info(f"🏭 Sector analysts begin to analyze: {ticker} @ {trade_date}")

        try:
            # Import and call sector analysis tools
            from core.tools.sector_tools import analyze_sector
            import asyncio
            import concurrent.futures

            # Run asynchronous functions in thread pool to avoid event loop conflicts
            def run_async_in_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(analyze_sector(ticker, trade_date))
                finally:
                    loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async_in_thread)
                sector_data = future.result()

            logger.info(f"✅ Sector data acquisition completed: {ticker}")

            # 🆕 Use LLM to analyze and interpret data
            sector_report = _analyze_with_llm(
                llm=llm,
                ticker=ticker,
                trade_date=trade_date,
                sector_data=sector_data,
                state=state
            )

            logger.info(f"✅ Sector analysis report generation completed: {ticker}")

            # ⚠️ Industry reports do not support caching: industry reports contain the codes and names of specific stocks, and caching will cause error messages to appear when analyzing other stocks in the same industry.
            # Therefore, it is not saved to cache

            # 🔥 Return AIMessage instead HumanMessage
            # AIMessage There is no tool_calls attribute (or tool_calls is an empty list),
            # In this way, the should_continue function will detect that there is no tool call and end the graph directly.
            final_message = AIMessage(content=sector_report, name="sector_analyst")

            # Only return fields that need to be updated (LangGraph will automatically merge)
            return {
                "sector_report": sector_report,
                "messages": [final_message],
            }

        except Exception as e:
            logger.error(f"❌ Sector analysis failed: {e}")
            import traceback
            logger.error(f"❌ detailed error: {traceback.format_exc()}")
            error_msg = f"Sector analysis encountered an error: {str(e)}"

            # Return error message
            error_message = AIMessage(content=error_msg, name="sector_analyst")

            return {
                "sector_report": error_msg,
                "messages": [error_message],
            }

    return sector_analyst_node


def _analyze_with_llm(llm, ticker: str, trade_date: str, sector_data: str, state: dict) -> str:
    """
    Use LLM to analyze and interpret sector data

    Args:
        llm: Language model example
        ticker: Stock code
        trade_date: transaction date
        sector_data: Sector data report
        state: status dictionary

    Returns:
        LLM Generated analysis report
    """
    try:
        # get AgentContext
        ctx = state.get("agent_context") or {}

        # Prepare template variables
        template_variables = {
            "ticker": ticker,
            "trade_date": trade_date,
        }

        # Try to get the prompt word from the template system
        try:
            from tradingagents.utils.template_client import get_template_client
            tpl_info = get_template_client().get_effective_template(
                agent_type="analysts",
                agent_name="sector_analyst",
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                context=None
            )
            if tpl_info:
                logger.info(f"📚 [Template selection] source={tpl_info.get('source')} id={tpl_info.get('template_id')} agent=analysts/sector_analyst")

            system_prompt = get_agent_prompt(
                agent_type="analysts",
                agent_name="sector_analyst",
                variables=template_variables,
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                fallback_prompt=None,
                context=None
            )
            system_prompt = apply_compliance_guardrails(system_prompt, "sector_analyst")
            logger.info(f"✅ [Sector Analyst] Successfully obtained the prompt word from the template system (length: {len(system_prompt)})")

        except Exception as e:
            logger.warning(f"⚠️ [Sector Analyst] Failed to obtain prompt word from template system: {e}, Use default prompt word")
            system_prompt = _get_default_system_prompt(ticker, trade_date)

        # Build a complete analysis request
        analysis_request = f"""{system_prompt}

## 📊 Sector data

The following is sector analysis data obtained through data tools:

{sector_data}

## 🎯 Analysis requirements

Please generate a professional sector analysis report based on the above data. The report must contain:

1. **Sector Performance Summary**
   - The main sector to which the target stock belongs
   - Recent performance evaluation of each sector
   - The strength of the sector relative to the broader market

2. **Sector rotation analysis**
   - Identification of current market hot sectors
   - Determining the trend of capital flow
   - Judgment of plate rotation stage

3. **Comparative evaluation with peers**
   - The position of the target stock in the industry
   - Valuation level evaluation (PE/PB)
   - The gap with industry leaders

4. **Research conclusion**
   - Sector popularity assessment:🔥Popular / ⚡Average / ❄️Unpopular
   - Funding direction:💰inflow / 💸flow out / ⚖️balance
   - Individual stock position:👑faucet / 🥈Second echelon / 🥉follow
    - Follow-up observation points: Signals that need to be followed based on sector trends

Please output in Chinese, the analysis must be well-founded, and the conclusion must be clear, but it must not form investment recommendations or operating instructions."""

        # Call LLM to generate analysis reports
        logger.info("📤 [Sector Analyst] Call LLM to generate analysis reports...")
        response = llm.invoke(analysis_request)

        # Extract response content
        if hasattr(response, 'content'):
            report = response.content
        else:
            report = str(response)

        logger.info(f"✅ [Sector Analyst] LLM Analysis report generation completed (length: {len(report)})")
        return report

    except Exception as e:
        logger.error(f"❌ [Sector Analyst] LLM Analysis failed: {e}")
        # If LLM analysis fails, return raw data report
        return sector_data


def _get_default_system_prompt(ticker: str, trade_date: str) -> str:
    """
    Get the default system prompt word

    Args:
        ticker: Stock code
        trade_date: transaction date

    Returns:
        Default system prompt word
    """
    prompt = f"""You are a professional industry/sector analyst, focusing on sector rotation and peer comparison analysis.

📋 **Analysis objects:**
- Stock code:{ticker}
- Analysis date:{trade_date}

🎯 **Your responsibilities:**
1. Analyze the overall performance of the industry to which the target stock belongs
2. Identify sector rotation trends and capital flows
3. Conduct comparative analysis of competitors in the same industry
4. Evaluate the position and valuation level of individual stocks in the industry

📊 **Analysis dimensions:**
- Sector performance: rise and fall, relative strength
- Fund flow direction: the main direction of capital entry and exit
- Valuation comparison: PE/PB relative to industry level
- Industry status: market value ranking, leading position

Please conduct professional analysis based on the data provided and give clear research conclusions, risk tips and follow-up observation points."""
    return apply_compliance_guardrails(prompt, "sector_analyst")

# === social_media_analyst.py ===
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json

# Import the unified log system and analysis module log decorator
from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_analyst_module
logger = get_logger("analysts.social_media")

# Import Google tool call processor
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler
from tradingagents.agents.utils.compliance_prompting import apply_compliance_guardrails

# Import template client
from tradingagents.utils.template_client import get_agent_prompt


def _get_company_name_for_social_media(ticker: str, market_info: dict) -> str:
    """
    Get Company Name for Social Media Analyst

    Args:
        ticker: Stock code
        market_info: Market Information Dictionary

    Returns:
        str: Company name
    """
    try:
        if market_info['is_china']:
            # China A-shares: Obtain stock information using a unified interface
            from tradingagents.dataflows.interface import get_china_stock_info_unified
            stock_info = get_china_stock_info_unified(ticker)

            logger.debug(f"📊 [social media analyst] Get stock information return: {stock_info[:200] if stock_info else 'None'}...")

            # Parse stock names
            if stock_info and "Stock name:" in stock_info:
                company_name = stock_info.split("Stock name:")[1].split("\n")[0].strip()
                logger.info(f"✅ [social media analyst] Successfully obtained Chinese stock names: {ticker} -> {company_name}")
                return company_name
            else:
                # Downgrade scenario: Try getting it directly from the data source manager
                logger.warning(f"⚠️ [social media analyst] Unable to parse stock name from unified interface: {ticker}, Try a downgrade solution")
                try:
                    from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
                    info_dict = get_info_dict(ticker)
                    if info_dict and info_dict.get('name'):
                        company_name = info_dict['name']
                        logger.info(f"✅ [social media analyst] The downgrade plan successfully obtained the stock name: {ticker} -> {company_name}")
                        return company_name
                except Exception as e:
                    logger.error(f"❌ [social media analyst] Downgrade plan also failed: {e}")

                logger.error(f"❌ [social media analyst] All schemes are unable to obtain the stock name: {ticker}")
                return f"Stock code{ticker}"

        elif market_info['is_hk']:
            # Hong Kong stocks: Use improved Hong Kong stocks tools
            try:
                from tradingagents.dataflows.providers.hk.improved_hk import get_hk_company_name_improved
                company_name = get_hk_company_name_improved(ticker)
                logger.debug(f"📊 [social media analyst] Use the improved Hong Kong stock tool to obtain names: {ticker} -> {company_name}")
                return company_name
            except Exception as e:
                logger.debug(f"📊 [social media analyst] Improved Hong Kong stock tool failed to obtain name: {e}")
                # Downgrade scenario: generate friendly default names
                clean_ticker = ticker.replace('.HK', '').replace('.hk', '')
                return f"Hong Kong stocks{clean_ticker}"

        elif market_info['is_us']:
            # US stocks: use simple mapping or return codes
            us_stock_names = {
                'AAPL': 'apple inc.',
                'TSLA': 'Tesla',
                'NVDA': 'NVIDIA',
                'MSFT': 'Microsoft',
                'GOOGL': 'Google',
                'AMZN': 'Amazon',
                'META': 'Meta',
                'NFLX': 'Netflix'
            }

            company_name = us_stock_names.get(ticker.upper(), f"US stocks{ticker}")
            logger.debug(f"📊 [social media analyst] US stock name mapping: {ticker} -> {company_name}")
            return company_name

        else:
            return f"stocks{ticker}"

    except Exception as e:
        logger.error(f"❌ [social media analyst] Failed to get company name: {e}")
        return f"stocks{ticker}"


def create_social_media_analyst(llm, toolkit):
    @log_analyst_module("social_media")
    def social_media_analyst_node(state):
        # 🔧 Tool call counter - prevent infinite loops
        tool_call_count = state.get("sentiment_tool_call_count", 0)
        max_tool_calls = 3  # Maximum number of tool calls
        logger.info(f"🔧 [Infinite loop repair] Current number of tool calls: {tool_call_count}/{max_tool_calls}")

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        # Get stock market information
        from tradingagents.utils.stock_utils import StockUtils
        market_info = StockUtils.get_market_info(ticker)

        # Get company name
        company_name = _get_company_name_for_social_media(ticker, market_info)
        logger.info(f"[social media analyst] Company name: {company_name}")

        # Unified use of get_stock_sentiment_unified tool
        # The tool internally automatically identifies the stock type and calls the corresponding sentiment data source
        logger.info("[social media analyst] Use unified sentiment analysis tools to automatically identify stock types")
        tools = [toolkit.get_stock_sentiment_unified]

        # 🆕 Use template system to get prompt words
        try:
            # Prepare template variables
            template_variables = {
                "ticker": ticker,
                "company_name": company_name,
                "market_name": market_info['market_name'],
                "current_date": current_date,
                "start_date": current_date,
                "currency_name": market_info['currency_name'],
                "currency_symbol": market_info['currency_symbol'],
                "tool_names": "get_stock_sentiment_unified"
            }

            from tradingagents.utils.template_client import get_template_client
            ctx = state.get("agent_context") or {}
            tpl_info = get_template_client().get_effective_template(
                agent_type="analysts",
                agent_name="social_media_analyst",
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                context=None
            )
            if tpl_info:
                logger.info(f"📚 [Template selection] source={tpl_info.get('source')} id={tpl_info.get('template_id')} version={tpl_info.get('version')} agent=analysts/social_media_analyst")

            # Get prompt words from template system
            system_prompt = get_agent_prompt(
                agent_type="analysts",
                agent_name="social_media_analyst",
                variables=template_variables,
                user_id=ctx.get("user_id"),
                preference_id=ctx.get("preference_id") or "neutral",
                fallback_prompt=None,
                context=None
            )
            system_prompt = apply_compliance_guardrails(system_prompt, "social_media_analyst")

            logger.info(f"✅ [social media analyst] Successfully obtained the prompt word from the template system (length: {len(system_prompt)})")

        except Exception as e:
            logger.error(f"❌ [social media analyst] Failed to obtain prompt word from template system: {e}")
            # Downgrade: Use hardcoded prompt words
            system_prompt = (
                f"You are a professional social media and investment sentiment analyst.\n\n"
                f"📋 **Analysis objects:**\n"
                f"- Company name:{company_name}\n"
                f"- Stock code:{ticker}\n"
                f"- Market:{market_info['market_name']}\n"
                f"- Analysis date:{current_date}\n\n"
                f"🔧 **Tool usage:**\n"
                f"You can use the following tools:get_stock_sentiment_unified\n"
                f"⚠️ Important workflow:\n"
                f"1. Your first action must be to call the get_stock_sentiment_unified tool\n"
                f"2. The tool automatically identifies stock types and obtains corresponding sentiment data\n"
                f"3. Analysis can only begin after data has been successfully acquired\n"
                f"4. Your answer must be based on real data returned by the tool\n\n"
                f"Please use Chinese and conduct analysis based on real data."
            )
            system_prompt = apply_compliance_guardrails(system_prompt, "social_media_analyst")
            logger.warning(f"⚠️ [social media analyst] Use demotion prompts (length: {len(system_prompt)})")

        # Create prompt template
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        chain = prompt | llm.bind_tools(tools)

        # Fix: Pass dictionary instead of message list directly so that ChatPromptTemplate handles all variables correctly
        result = chain.invoke({"messages": state["messages"]})

        # Call handlers using unified Google tools
        if GoogleToolCallHandler.is_google_model(llm):
            logger.info("📊 [social media analyst] Google model detected, processor invoked using unified tools")
            
            # Create analysis prompt words
            analysis_prompt_template = GoogleToolCallHandler.create_analysis_prompt(
                ticker=ticker,
                company_name=company_name,
                analyst_type="Social media sentiment analysis",
                specific_requirements="Focus on investor sentiment, social media discussion popularity, public opinion influence, etc."
            )
            
            # Handling Google model tool calls
            report, messages = GoogleToolCallHandler.handle_google_tool_calls(
                result=result,
                llm=llm,
                tools=tools,
                state=state,
                analysis_prompt_template=analysis_prompt_template,
                analyst_name="social media analyst"
            )
        else:
            # Processing logic for non-Google models
            logger.debug(f"📊 [DEBUG] Non-Google model ({llm.__class__.__name__}), Use standard processing logic")
            
            report = ""
            if len(result.tool_calls) == 0:
                report = result.content

        # 🔧 Update tool call counter
        return {
            "messages": [result],
            "sentiment_report": report,
            "sentiment_tool_call_count": tool_call_count + 1
        }

    return social_media_analyst_node
