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
        logger.info(f"[news analyst] Use unified news tools to automatically identify stock types and obtain corresponding news")
   # Create a unified news tool
        unified_news_tool = create_unified_news_tool(toolkit)
        unified_news_tool.name = "get_stock_news_unified"
        
        tools = [unified_news_tool]
        logger.info(f"[news analyst] Unified news tool loaded: get_stock_news_unified")

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
        except:
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
                logger.info(f"[news analyst] 🔧 Preprocessing: Forced call of unified news tool...")
                logger.info(f"[news analyst] 📊 Call parameters: stock_code={ticker}, max_news=10, model_info={model_info}")

                pre_fetched_news = unified_news_tool(stock_code=ticker, max_news=10, model_info=model_info)

                logger.info(f"[news analyst] 📋 Preprocessing return result length: {len(pre_fetched_news) if pre_fetched_news else 0} character")
                logger.info(f"[news analyst] 📄 Preprocessing return result preview (first 500 characters): {pre_fetched_news[:500] if pre_fetched_news else 'None'}")

                if pre_fetched_news and len(pre_fetched_news.strip()) > 100:
                    logger.info(f"[news analyst] ✅ Preprocessing successfully obtained news: {len(pre_fetched_news)} character")

                    # Generate analysis directly based on pre-fetched news, skipping tool calls
                    # 🔧 Important: Build system prompts that do not include tool invocation guidance
                    analysis_system_prompt = f"""You are a professional financial news analyst.

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

                    logger.info(f"[news analyst] 🔄 Generate analysis directly using pre-fetched news data...")
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
                        logger.warning(f"[news analyst] ⚠️ LLM The return result is empty and falls back to standard mode.")

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
            logger.info(f"📊 [news analyst] Google model detected, processor invoked using unified tools")
            
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
                    logger.info(f"[news analyst] 🔧 Forcibly call the unified news tool to obtain news data...")
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

                        logger.info(f"[news analyst] 🔄 Regenerate full analysis based on force-fetched news data...")
                        logger.info(f"[news analyst] 📝 Forced prompt word length: {len(forced_prompt)} character")

                        forced_result = llm.invoke([{"role": "user", "content": forced_prompt}])

                        if hasattr(forced_result, 'content') and forced_result.content:
                            report = forced_result.content
                            logger.info(f"[news analyst] ✅ Force remediation successful, generate report based on real data, length: {len(report)} character")
                            logger.info(f"[news analyst] 📄 Report preview (first 300 characters): {report[:300]}")
                        else:
                            logger.warning(f"[news analyst] ⚠️ Force the remediation LLM to return null, use the original result")
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
