"""
Fundamental Analyst - Unified Tool Architecture Version
Use unified tools to automatically identify stock types and call corresponding data sources
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage


def create_fundamentals_analyst(llm, toolkit):
    def fundamentals_analyst_node(state):
        print(f"📊 [DEBUG] ===== Fundamental analyst node starts =====")

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        # 🔧 Fundamental analysis data range: Fixed acquisition of 10 days of data (processing weekends/holidays/data delays)
        from datetime import datetime, timedelta
        try:
            end_date_dt = datetime.strptime(current_date, "%Y-%m-%d")
            start_date_dt = end_date_dt - timedelta(days=10)
            start_date = start_date_dt.strftime("%Y-%m-%d")
            print(f"📅 [fundamental analyst] data range: {start_date} to {current_date} (Fixed for 10 days)")
        except Exception as e:
            print(f"⚠️ [fundamental analyst] Date parsing failed, using default range: {e}")
            start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        print(f"📊 [DEBUG] input parameters: ticker={ticker}, date={current_date}")
        print(f"📊 [DEBUG] The number of messages in the current state: {len(state.get('messages', []))}")
        print(f"📊 [DEBUG] Current fundamental reports: {state.get('fundamentals_report', 'None')[:100]}...")

        # Get stock market information
        from tradingagents.utils.stock_utils import StockUtils
        print(f"📊 [fundamental analyst] Analyzing stocks: {ticker}")

        market_info = StockUtils.get_market_info(ticker)
        print(f"📊 [DEBUG] Stock type check: {ticker} -> {market_info['market_name']} ({market_info['currency_name']})")
        print(f"📊 [DEBUG] Detailed market information: is_china={market_info['is_china']}, is_hk={market_info['is_hk']}, is_us={market_info['is_us']}")
        print(f"📊 [DEBUG] Tool configuration check: online_tools={toolkit.config['online_tools']}")

        # Select tool
        if toolkit.config["online_tools"]:
            # Use a unified fundamental analysis tool that automatically identifies stock types within the tool
            print(f"📊 [fundamental analyst] Use unified fundamental analysis tools to automatically identify stock types")
            tools = [toolkit.get_stock_fundamentals_unified]
            print(f"📊 [DEBUG] Tools of choice: {[tool.name for tool in tools]}")
            print(f"📊 [DEBUG] 🔧 Unified tools will automatically handle: {market_info['market_name']}")
        else:
            tools = [
                toolkit.get_finnhub_company_insider_sentiment,
                toolkit.get_finnhub_company_insider_transactions,
                toolkit.get_simfin_balance_sheet,
                toolkit.get_simfin_cashflow,
                toolkit.get_simfin_income_stmt,
            ]

        # Unified system prompts for all stock types
        system_message = (
            f"You are a professional stock fundamental analyst."
            f"⚠️ Absolutely mandatory: you must call the tool to get the real data! No assumptions or fabrications allowed!"
            f"Task: Analyze stock symbols {ticker} ({market_info['market_name']})"
            f"🔴 Call the get_stock_fundamentals_unified tool now"
            f"Parameters:ticker='{ticker}', start_date='{start_date}', end_date='{current_date}', curr_date='{current_date}'"
            "📊 Analysis requirements:"
            "- In-depth fundamental analysis based on real data"
            f"- Calculate and provide a reasonable price range (using{market_info['currency_name']}{market_info['currency_symbol']}) "
            "- Analyze whether the current stock price is undervalued or overvalued"
            "- Provide target price recommendations based on fundamentals"
            "- Includes analysis of valuation indicators such as PE, PB, PEG, etc."
            "- Analyze based on market characteristics"
            "🌍 Language and currency requirements:"
            "- All analysis content must be in Chinese"
            "- Investment advice must be in Chinese: buy, hold, sell"
            "- Absolutely no English is allowed: buy, hold,sell"
            f"- Currency unit used:{market_info['currency_name']} ({market_info['currency_symbol']}) "
            "🚫 Strictly prohibited:"
            "- not allowed to say'I will call the tool'"
            "- No assumptions are allowed about any data"
            "- Fabricating company information is not allowed"
            "- Direct answers without calling the tool are not allowed"
            "- No replies allowed'Unable to determine price'or'need more information'"
            "- English investment advice (buy/hold/sell) is not allowed"
            "✅ You must:"
            "- Call the Unified Fundamental Analysis Tool Now"
            "- Wait for the tool to return real data"
            "- Analysis based on real data"
            "- Provide specific price range and target price"
            "- Use Chinese investment advice (buy/hold/sell)"
            "Start calling tools now! Don t say anything else!"
        )

        # System prompt template
        system_prompt = (
            "🔴 Mandatory requirement: You must call the tool to get real data!"
            "🚫 Absolutely no-no: No assumptions, fabrications, or direct answers to any questions allowed!"
            "✅ You must: Immediately call the provided tools to obtain real data, and then perform analysis based on real data."
            "Available tools:{tool_names}. \n{system_message}"
            "Current date:{current_date}. Analysis goals:{ticker}. "
        )

        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
        ])

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        # Detect Alibaba Bailian model and create a new instance
        if hasattr(llm, '__class__') and 'DashScope' in llm.__class__.__name__:
            print(f"📊 [DEBUG] Alibaba Bailian model is detected and a new instance is created to avoid tool caching")
            from tradingagents.llm_adapters import ChatDashScopeOpenAI

            # Get the base_url and api_key
            original_base_url = getattr(llm, 'openai_api_base', None)
            original_api_key = getattr(llm, 'openai_api_key', None)

            llm = ChatDashScopeOpenAI(
                model=llm.model_name,
                api_key=original_api_key,  # 🔥 Pass the original LLM's API Key
                base_url=original_base_url if original_base_url else None,  # pass on base_url
                temperature=llm.temperature,
                max_tokens=getattr(llm, 'max_tokens', 2000)
            )

            if original_base_url:
                print(f"📊 [DEBUG] The new instance uses the original base_url: {original_base_url}")
            if original_api_key:
                print(f"📊 [DEBUG] The new instance uses the original API Key (from the database configuration)")

        print(f"📊 [DEBUG] Create LLM chain, number of tools: {len(tools)}")
        print(f"📊 [DEBUG] List of bound tools: {[tool.name for tool in tools]}")
        print(f"📊 [DEBUG] Create a tool chain and let the model decide whether to call the tool independently")

        try:
            chain = prompt | llm.bind_tools(tools)
            print(f"📊 [DEBUG] ✅ Tool binding is successful, bound {len(tools)} tools")
        except Exception as e:
            print(f"📊 [DEBUG] ❌ Tool binding failed: {e}")
            raise e

        print(f"📊 [DEBUG] Call LLM chain...")
        result = chain.invoke(state["messages"])
        print(f"📊 [DEBUG] LLM Call completed")

        print(f"📊 [DEBUG] result type: {type(result)}")
        print(f"📊 [DEBUG] Number of tool calls: {len(result.tool_calls) if hasattr(result, 'tool_calls') else 0}")
        print(f"📊 [DEBUG] content length: {len(result.content) if hasattr(result, 'content') else 0}")

        # Check tool calls
        expected_tools = [tool.name for tool in tools]
        actual_tools = [tc['name'] for tc in result.tool_calls] if hasattr(result, 'tool_calls') and result.tool_calls else []
        
        print(f"📊 [DEBUG] Desired Tools: {expected_tools}")
        print(f"📊 [DEBUG] The actual tool called: {actual_tools}")

        # Process fundamental analysis reports
        if hasattr(result, 'tool_calls') and len(result.tool_calls) > 0:
            # If there is a tool call, record tool call information
            tool_calls_info = []
            for tc in result.tool_calls:
                tool_calls_info.append(tc['name'])
                print(f"📊 [DEBUG] Tool call {len(tool_calls_info)}: {tc}")
            
            print(f"📊 [fundamental analyst] Tool call: {tool_calls_info}")
            
            # Return status and let the tool execute
            return {"messages": [result]}
        
        else:
            # There is no tool call, use Ali Bailian to force tool call to fix it
            print(f"📊 [DEBUG] Detected model not calling tools, enable forced tool calling mode")
            
            # Forced call of unified fundamental analysis tool
            try:
                print(f"📊 [DEBUG] Forced call get_stock_fundamentals_unified...")
                unified_tool = next((tool for tool in tools if tool.name == 'get_stock_fundamentals_unified'), None)
                if unified_tool:
                    combined_data = unified_tool.invoke({
                        'ticker': ticker,
                        'start_date': start_date,
                        'end_date': current_date,
                        'curr_date': current_date
                    })
                    print(f"📊 [DEBUG] Unified tool data acquisition successful, length: {len(combined_data)}character")
                else:
                    combined_data = "Unified fundamental analysis tools are not available"
                    print(f"📊 [DEBUG] Unified tool not found")
            except Exception as e:
                combined_data = f"Unified fundamental analysis tool failed to call: {e}"
                print(f"📊 [DEBUG] Unified tool calling exception: {e}")
            
            currency_info = f"{market_info['currency_name']}（{market_info['currency_symbol']}）"
            
            # Generate analysis reports based on real data
            analysis_prompt = f"""Based on the following real data, for stocks{ticker}Conduct detailed fundamental analysis:

{combined_data}

Please provide:
1. Company basic information analysis
2. financial situation assessment
3. Profitability analysis
4. Valuation analysis (using{currency_info}) 
5. Investment advice (buy/hold/sell)

Requirements:
- Analysis based on real data provided
- price use{currency_info}
- Investment advice is in Chinese
- The analysis must be detailed and professional"""

            try:
                # Create a simple analysis chain
                analysis_prompt_template = ChatPromptTemplate.from_messages([
                    ("system", "You are a professional stock fundamental analyst, performing analysis based on real data provided."),
                    ("human", "{analysis_request}")
                ])
                
                analysis_chain = analysis_prompt_template | llm
                analysis_result = analysis_chain.invoke({"analysis_request": analysis_prompt})
                
                if hasattr(analysis_result, 'content'):
                    report = analysis_result.content
                else:
                    report = str(analysis_result)
                    
                print(f"📊 [fundamental analyst] Force tool call to complete, report length: {len(report)}")
                
            except Exception as e:
                print(f"❌ [DEBUG] Force tool call analysis failed: {e}")
                report = f"Fundamental analysis fails:{str(e)}"
            
            return {"fundamentals_report": report}

        # Shouldn't arrive here, but as a backup
        print(f"📊 [DEBUG] return status: fundamentals_report length={len(result.content) if hasattr(result, 'content') else 0}")
        return {"messages": [result]}

    return fundamentals_analyst_node
