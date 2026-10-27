#!/usr/bin/env python3
"""
Alibaba Bailian Tool Call Optimization Test
Solve the problem of LLM not actively calling tools
"""

import os
import sys
from datetime import datetime, timedelta

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_basic_tool_calling():
    """Test basic tool calls"""
    print("🔧 Test basic tool calls")
    print("=" * 50)
    
    try:
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        from langchain_core.tools import tool
        from langchain_core.messages import HumanMessage
        
        # Define simple tools
        @tool
        def get_stock_price(symbol: str) -> str:
            """Get stock price information"""
            return f"stocks{symbol}The current price is 100 yuan"
        
        # Create LLM
        llm = ChatDashScopeOpenAI(
            model="qwen-plus-latest",
            temperature=0.1,
            max_tokens=500
        )
        
        # binding tool
        llm_with_tools = llm.bind_tools([get_stock_price])
        
        # Test different prompt strategies
        prompts = [
            # Strategy 1: direct instruction
            "Please call the get_stock_price tool to query the stock price of AAPL",
            
            # Strategy 2: clear requirements
            "I need to check the price information of AAPL stock. Please use available tools to obtain this information.",
            
            # Strategy 3: Mandatory instructions
            "You must use the get_stock_price tool to query the AAPL stock price. Don t answer directly, you must call the tool.",
            
            # Strategy 4: clear instructions in chinese
            "Please be sure to call the get_stock_price tool and set the parameter symbol to'AAPL', Get stock price information."
        ]
        
        for i, prompt in enumerate(prompts, 1):
            print(f"\n🔄 testing strategy{i}: {prompt[:30]}...")
            
            try:
                response = llm_with_tools.invoke([HumanMessage(content=prompt)])
                
                tool_calls = getattr(response, 'tool_calls', [])
                print(f"   Number of tool calls: {len(tool_calls)}")
                print(f"   response length: {len(response.content)}character")
                
                if len(tool_calls) > 0:
                    print(f"   ✅ Strategy{i}success: Tool call triggered")
                    for j, tool_call in enumerate(tool_calls):
                        print(f"      Tools{j+1}: {tool_call.get('name', 'unknown')}")
                    return True
                else:
                    print(f"   ❌ Strategy{i}failed: Tool call not triggered")
                    print(f"   direct response: {response.content[:100]}...")
                    
            except Exception as e:
                print(f"   ❌ Strategy{i}Abnormal: {e}")
        
        return False
        
    except Exception as e:
        print(f"❌ Basic tool call test failed: {e}")
        return False


def test_stock_analysis_tool_calling():
    """Test stock analysis tool calls"""
    print("\n🔧 Test stock analysis tool calls")
    print("=" * 50)
    
    try:
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        from tradingagents.agents.utils.agent_utils import Toolkit
        from langchain_core.messages import HumanMessage
        
        # Create LLM
        llm = ChatDashScopeOpenAI(
            model="qwen-plus-latest",
            temperature=0.0,  # Lowering the temperature increases certainty
            max_tokens=1000
        )
        
        # Get stock analysis tools
        toolkit = Toolkit()
        tools = [
            toolkit.get_china_stock_data,
            toolkit.get_china_fundamentals
        ]
        
        # binding tool
        llm_with_tools = llm.bind_tools(tools)
        
        # Test specialized stock analysis prompt
        stock_prompts = [
            # Strategy 1: Explicit tool calling instructions
            """Please analyze stock 688656.

Steps:
1. First call the get_china_stock_data tool to obtain stock data, parameters:stock_code='688656', start_date='2025-06-01', end_date='2025-07-11'
2. Then call the get_china_fundamentals tool to obtain fundamental data, parameters:ticker='688656', curr_date='2025-07-11'

Please strictly follow the above steps and the tool must be called.""",

            # Strategy 2: problem oriented
            """I would like to know the details of the stock 688656, including:
- Recent price action and trading data
- Fundamental Analysis and Financial Conditions

Please use the tools available to obtain this information.""",

            # Strategy 3: Force tool call
            """688656 stocks analyzed. Note: You must use tools to obtain data, you cannot answer in a vacuum. Please call relevant tools to obtain stock data and fundamental information."""
        ]
        
        for i, prompt in enumerate(stock_prompts, 1):
            print(f"\n🔄 Test stock analysis strategies{i}...")
            
            try:
                response = llm_with_tools.invoke([HumanMessage(content=prompt)])
                
                tool_calls = getattr(response, 'tool_calls', [])
                print(f"   Number of tool calls: {len(tool_calls)}")
                print(f"   response length: {len(response.content)}character")
                
                if len(tool_calls) > 0:
                    print(f"   ✅ Stock Analysis Strategies{i}success")
                    for j, tool_call in enumerate(tool_calls):
                        tool_name = tool_call.get('name', 'unknown')
                        tool_args = tool_call.get('args', {})
                        print(f"      Tools{j+1}: {tool_name}({tool_args})")
                    return True
                else:
                    print(f"   ❌ Stock Analysis Strategies{i}failed")
                    print(f"   direct response: {response.content[:150]}...")
                    
            except Exception as e:
                print(f"   ❌ Stock Analysis Strategies{i}Abnormal: {e}")
        
        return False
        
    except Exception as e:
        print(f"❌ Stock analysis tool call test failed: {e}")
        return False


def test_parameter_optimization():
    """Test parameter optimization"""
    print("\n🔧 Test parameter optimization")
    print("=" * 50)
    
    try:
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        from langchain_core.tools import tool
        from langchain_core.messages import HumanMessage
        
        # Define testing tools
        @tool
        def analyze_stock(symbol: str, period: str) -> str:
            """Analyze stocks"""
            return f"analysis{symbol}stocks, time period{period}"
        
        # Test different parameter configurations
        configs = [
            {"temperature": 0.0, "max_tokens": 500, "description": "low temperature"},
            {"temperature": 0.1, "max_tokens": 500, "description": "Default temperature"},
            {"temperature": 0.3, "max_tokens": 500, "description": "medium temperature"},
        ]
        
        prompt = "Please call the analyze_stock tool to analyze AAPL stock, and the time period is set to'1month'"
        
        for config in configs:
            print(f"\n🔄 test{config['description']}Configuration...")
            
            try:
                llm = ChatDashScopeOpenAI(
                    model="qwen-plus-latest",
                    temperature=config["temperature"],
                    max_tokens=config["max_tokens"]
                )
                
                llm_with_tools = llm.bind_tools([analyze_stock])
                response = llm_with_tools.invoke([HumanMessage(content=prompt)])
                
                tool_calls = getattr(response, 'tool_calls', [])
                print(f"   Number of tool calls: {len(tool_calls)}")
                
                if len(tool_calls) > 0:
                    print(f"   ✅ {config['description']}Configuration successful")
                    return config
                else:
                    print(f"   ❌ {config['description']}Configuration failed")
                    
            except Exception as e:
                print(f"   ❌ {config['description']}Configuration exception: {e}")
        
        return None
        
    except Exception as e:
        print(f"❌ Parameter optimization test failed: {e}")
        return None


def test_model_comparison():
    """Test the tool calling capabilities of different models"""
    print("\n🔧 Test the tool calling capabilities of different models")
    print("=" * 50)
    
    try:
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        from langchain_core.tools import tool
        from langchain_core.messages import HumanMessage
        
        # Define testing tools
        @tool
        def get_info(query: str) -> str:
            """Get information"""
            return f"Query results: {query}"
        
        # Test different models
        models = [
            "qwen-turbo",
            "qwen-plus",
            "qwen-plus-latest",
            "qwen-max-latest"
        ]
        
        prompt = "Please call the get_info tool to query'Stock market performance today'"
        
        for model in models:
            print(f"\n🔄 test model: {model}...")
            
            try:
                llm = ChatDashScopeOpenAI(
                    model=model,
                    temperature=0.1,
                    max_tokens=300
                )
                
                llm_with_tools = llm.bind_tools([get_info])
                response = llm_with_tools.invoke([HumanMessage(content=prompt)])
                
                tool_calls = getattr(response, 'tool_calls', [])
                print(f"   Number of tool calls: {len(tool_calls)}")
                
                if len(tool_calls) > 0:
                    print(f"   ✅ {model}: Support tool calling")
                else:
                    print(f"   ❌ {model}: Tool calling is not supported")
                    print(f"   response: {response.content[:100]}...")
                    
            except Exception as e:
                print(f"   ❌ {model}: Test exception - {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Model comparison test failed: {e}")
        return False


def main():
    """Main test function"""
    print("🔬 Alibaba Bailian Tool Call Optimization Test")
    print("=" * 70)
    print("💡 target: Solve the problem of LLM not actively calling tools")
    print("=" * 70)
    
    # Check API key
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("❌ DASHSCOPE_API_KEY environment variable not found")
        return
    
    # Run tests
    tests = [
        ("Basic tool calls", test_basic_tool_calling),
        ("Stock analysis tool call", test_stock_analysis_tool_calling),
        ("Parameter optimization", test_parameter_optimization),
        ("Model comparison", test_model_comparison)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}Test exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n📋 Tool call optimization test summary")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results:
        if result:
            status = "✅ Pass"
            passed += 1
        else:
            status = "❌ failed"
        print(f"{test_name}: {status}")
    
    total = len(results)
    print(f"\n📊 Test results: {passed}/{total} Pass")
    
    if passed > 0:
        print("\n💡 Suggestions:")
        print("   1. Use more explicit tool calling instructions")
        print("   2. Adjust temperature parameters")
        print("   3. Try different model versions")
        print("   4. Consider using the force tool call pattern")
    else:
        print("\n⚠️ Alibaba Bailian may require special tool call processing")
        print("   It is recommended to use manual tool calls as a fallback")


if __name__ == "__main__":
    main()
