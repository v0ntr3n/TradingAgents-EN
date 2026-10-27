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
        logger.debug(f"📈 [DEBUG] ===== Market analyst node starts =====")

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
        logger.info(f"📊 [market analyst] Use unified market data tools to automatically identify stock types")
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
        logger.info(f"📊 [market analyst] ========== Message passed to LLM ==========")
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
        logger.info(f"📊 [market analyst] ========== End of message list ==========")

        chain = prompt | llm.bind_tools(tools)

        logger.info(f"📊 [market analyst] Start calling LLM...")
        # 🔑 Fix: Pass all template variables, not just messages
        invoke_params = {
            "messages": state["messages"],
            **template_variables  # contains ticker, company_name, market_name, current_date, currency_symbol, currency_name, tool_names
        }
        logger.debug(f"📊 [market analyst] Call parameters: {list(invoke_params.keys())}")
        result = chain.invoke(invoke_params)
        logger.info(f"📊 [market analyst] LLM Call completed")

        # Print LLM response
        logger.info(f"📊 [market analyst] ========== LLM Response starts ==========")
        logger.info(f"📊 [market analyst] response type: {type(result).__name__}")
        logger.info(f"📊 [market analyst] Response content: {str(result.content)[:1000]}...")
        if hasattr(result, 'tool_calls') and result.tool_calls:
            logger.info(f"📊 [market analyst] Tool call: {result.tool_calls}")
        logger.info(f"📊 [market analyst] ========== LLM End of response ==========")

        # Call handlers using unified Google tools
        if GoogleToolCallHandler.is_google_model(llm):
            logger.info(f"📊 [market analyst] Google model detected, processor invoked using unified tools")
            
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
            logger.info(f"📊 [market analyst] Check LLM return results...")
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
