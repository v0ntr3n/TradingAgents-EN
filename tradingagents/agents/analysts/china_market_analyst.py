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
        logger.info(f"📊 [China market analyst] Google model detected, processor invoked using unified tools")

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
