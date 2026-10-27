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
        logger.info(f"[social media analyst] Use unified sentiment analysis tools to automatically identify stock types")
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
            logger.info(f"📊 [social media analyst] Google model detected, processor invoked using unified tools")
            
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
