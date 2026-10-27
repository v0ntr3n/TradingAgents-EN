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
        logger.debug(f"📊 [DEBUG] ===== Fundamental analyst node starts =====")

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
        logger.info(f"📊 [fundamental analyst] Use unified fundamental analysis tools to automatically identify stock types")
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
            logger.debug(f"📊 [DEBUG] Alibaba Bailian model is detected and a new instance is created to avoid tool caching")
            from tradingagents.llm_adapters import ChatDashScopeOpenAI
            from pydantic import SecretStr

            # Get the base_url and api_key
            original_base_url = getattr(llm, 'openai_api_base', None)
            original_api_key = getattr(llm, 'openai_api_key', None)

            # 🔥 If api_key is a SecretStr object, it needs to be unpacked
            if isinstance(original_api_key, SecretStr):
                original_api_key = original_api_key.get_secret_value()
                logger.debug(f"📊 [DEBUG] API Key is SecretStr, unpacked")

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
                logger.debug(f"📊 [DEBUG] The new instance uses the original API Key (from the database configuration)")
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
        logger.debug(f"📊 [DEBUG] Create a tool chain and let the model decide whether to call the tool independently")

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

        logger.info(f"📊 [fundamental analyst] Start calling LLM...")

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
        logger.info(f"📊 [fundamental analyst] LLM Call completed")
        
        # 🔍 [debug log] Print the details of AIMessage
        logger.info(f"🤖 [fundamental analyst] AIMessage Details:")
        logger.info(f"🤖 [fundamental analyst] - Message type: {type(result).__name__}")
        logger.info(f"🤖 [fundamental analyst] - content length: {len(result.content) if hasattr(result, 'content') else 0}")
        if hasattr(result, 'content') and result.content:
            # 🔥 Debug mode: print the complete content without truncation
            logger.info(f"🤖 [fundamental analyst] - full content:")
            logger.info(f"{result.content}")
        
        # 🔍 [debug log] Print details of tool_calls
        # Detailed records of LLM return results
        logger.info(f"📊 [fundamental analyst] ===== LLM Return result analysis =====")
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
                logger.info(f"🔧 [fundamental analyst] tool_calls Is an empty list")
        else:
            logger.info(f"🔧 [fundamental analyst] No tool_calls attribute")

        logger.info(f"📊 [fundamental analyst] ===== LLM Return result analysis ends =====")

        # Call handlers using unified Google tools
        if GoogleToolCallHandler.is_google_model(fresh_llm):
            logger.info(f"📊 [fundamental analyst] Google model detected, processor invoked using unified tools")
            
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
                    logger.warning(f"⚠️ [Force report generation] The tool has returned data, but LLM still tries to call the tool to force a report based on the existing data")

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

                    logger.info(f"🔧 [Force report generation] Recall using specialized prompt words LLM...")
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
                    logger.info(f"✅ [normal process] ===== LLM First time calling tool =====")
                    tool_calls_info = []
                    for tc in result.tool_calls:
                        tool_calls_info.append(tc['name'])
                        logger.debug(f"📊 [DEBUG] Tool call {len(tool_calls_info)}: {tc}")

                    logger.info(f"📊 [normal process] LLM Request to call tool: {tool_calls_info}")
                    logger.info(f"📊 [normal process] Number of tool calls: {len(tool_calls_info)}")
                    logger.info(f"📊 [normal process] Return status and wait for tool execution")
                    # ⚠️ NOTE: Don't increment the counter here!
                    # The counter should only be incremented after the tool execution is complete (the next time the analyst node is entered)
                    return {
                        "messages": [result]
                    }
            else:
                # There is no tool call, check whether you need to force the tool to be called
                logger.info(f"📊 [fundamental analyst] ===== Force tool call check to start =====")
                logger.debug(f"📊 [DEBUG] It is detected that the model does not call the tool, check whether it needs to be forced to call")

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
                    logger.info(f"⚠️ [content inspection] LLM No content returned or the content is empty")

                # Solution 3: Count the number of tool calls
                tool_call_count = sum(1 for msg in messages if isinstance(msg, ToolMessage))
                logger.info(f"🔍 [statistics] Number of historical tool calls: {tool_call_count}")

                logger.info(f"🔍 [Repeat call check] Summary - Number of tool results: {tool_call_count}, Already have tool results: {has_tool_result}, Already analyzed content: {has_analysis_content}")
                logger.info(f"📊 [fundamental analyst] ===== Force tool call check to end =====")

                # If there are already tool results or analysis content, skip the forced call
                if has_tool_result or has_analysis_content:
                    logger.info(f"🚫 [decision making] ===== Skip force tool call =====")
                    if has_tool_result:
                        logger.info(f"⚠️ [Reasons for decision] Detected {tool_call_count} The result of tool call to avoid repeated calls")
                    if has_analysis_content:
                        logger.info(f"⚠️ [Reasons for decision] LLM Valid analysis content has been returned, no need to force tool calls")

                    # Use the content returned by LLM directly as a report
                    report = str(result.content) if hasattr(result, 'content') else "Fundamental analysis completed"
                    logger.info(f"📊 [Return results] Analysis content returned using LLM, report length: {len(report)}character")
                    logger.info(f"📊 [Return results] Report preview(first 200 characters): {report[:200]}...")
                    logger.info(f"✅ [decision making] Fundamental analysis is completed and repeated calls are skipped successfully")

                    # 🔧 Keep tool call counter unchanged (already updated at start based on ToolMessage)
                    return {
                        "fundamentals_report": report,
                        "messages": [result],
                        "fundamentals_tool_call_count": tool_call_count
                    }

                # If there is no tool result and no analysis content, a forced call will be made.
                logger.info(f"🔧 [decision making] ===== Execute force tool call =====")
                logger.info(f"🔧 [Reasons for decision] No tool results or analysis content detected, fundamental data needs to be obtained")
                logger.info(f"🔧 [decision making] Enable forced tool invocation mode")

                # Forced call of unified fundamental analysis tool
                try:
                    logger.debug(f"📊 [DEBUG] Forced call get_stock_fundamentals_unified...")
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
                        logger.info(f"🔍 [Tool call] Find the unified tool and prepare to force it to be called")
                        logger.info(f"🔍 [Tool call] Pass in parameters - ticker: '{ticker}', start_date: {start_date}, end_date: {current_date}")

                        combined_data = unified_tool.invoke({
                            'ticker': ticker,
                            'start_date': start_date,
                            'end_date': current_date,
                            'curr_date': current_date
                        })

                        logger.info(f"✅ [Tool call] Unified tool call successful")
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
                        logger.debug(f"📊 [DEBUG] Unified tool not found")
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
