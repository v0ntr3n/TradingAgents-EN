#!/usr/bin/env python3
"""
Alibaba Bailian OpenAI compatible adapter repair verification test
Verify that new OpenAI compatible adapter resolves tool calling issues
"""

import os
import sys
from datetime import datetime, timedelta

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_openai_adapter_import():
    """Test new adapter import"""
    print("\n🔧 Test new adapter import")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        print("✅ ChatDashScopeOpenAI Import successful")
        
        from tradingagents.llm_adapters.dashscope_openai_adapter import (
            create_dashscope_openai_llm,
            test_dashscope_openai_connection,
            test_dashscope_openai_function_calling
        )
        print("✅ Related functions imported successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_openai_adapter_connection():
    """Test OpenAI Compatible Adapter Connection"""
    print("\n🔧 Test OpenAI Compatible Adapter Connection")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters.dashscope_openai_adapter import test_dashscope_openai_connection
        
        # test connection
        result = test_dashscope_openai_connection(model="qwen-turbo")
        
        if result:
            print("✅ OpenAI Compatible adapter connection test successful")
            return True
        else:
            print("❌ OpenAI Compatible adapter connection test failed")
            return False
            
    except Exception as e:
        print(f"❌ Connection test exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_openai_adapter_function_calling():
    """Testing OpenAI compatible adapters Function Calling"""
    print("\n🔧 Testing OpenAI compatible adapters Function Calling")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters.dashscope_openai_adapter import test_dashscope_openai_function_calling
        
        # test Function Calling
        result = test_dashscope_openai_function_calling(model="qwen-plus-latest")
        
        if result:
            print("✅ OpenAI Compatible adapter Function Calling test successful")
            return True
        else:
            print("❌ OpenAI Compatible adapter Function Calling test failed")
            return False
            
    except Exception as e:
        print(f"❌ Function Calling Test exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_technical_analysis_with_new_adapter():
    """Technical analysis of testing new adapters"""
    print("\n🔧 Technical analysis of testing new adapters")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        from tradingagents.agents.utils.agent_utils import Toolkit
        from langchain_core.messages import HumanMessage
        from langchain_core.tools import tool
        
        # Create a new OpenAI compatible adapter
        llm = ChatDashScopeOpenAI(
            model="qwen-plus-latest",
            temperature=0.1,
            max_tokens=2000
        )
        
        print("✅ New adapter created successfully")
        
        # Define testing tools
        @tool
        def get_test_stock_data(ticker: str, start_date: str, end_date: str) -> str:
            """Get test stock data"""
            return f"""# {ticker} Stock data analysis

## 📊 Real-time quotes
- Stock name: China Merchants Bank
- Stock code: {ticker}
- current price: ¥47.13
- Increase or decrease: -1.03%
- Volume: 61.5 Thousands of hands
- Data source: Tushare

## 📈 Historical data overview
- data period: {start_date} to {end_date}
- Number of data items: 23 Article
- Highest during the period: ¥47.88
- lowest during the period: ¥44.21

## 📋 Technical indicators
- RSI: 45.2 (Neutral)
- MACD: 0.15 (bullish)
- MA20: ¥46.85
- Volume trend: Increase the volume"""
        
        # binding tool
        llm_with_tools = llm.bind_tools([get_test_stock_data])
        
        print("✅ Tool binding successful")
        
        # Test tool call
        print("🔄 Test tool call...")
        
        messages = [HumanMessage(content="""Please analyze the technical aspects of this stock 600036.
        
Please call the get_test_stock_data tool first to obtain the data, parameters:
- ticker: "600036"
- start_date: "2025-06-10"
- end_date: "2025-07-10"

Then a detailed technical analysis report is generated based on the acquired data, requiring:
1. The report length should not be less than 500 words
2. Contains detailed technical indicator analysis
3. Provide clear investment advice
4. Written in Chinese""")]
        
        response = llm_with_tools.invoke(messages)
        
        print(f"📊 response type: {type(response)}")
        print(f"📊 response length: {len(response.content)}character")
        
        # Check if there is a tool call
        if hasattr(response, 'tool_calls') and len(response.tool_calls) > 0:
            print(f"✅ Tool call successful: {len(response.tool_calls)}tool calls")
            for i, tool_call in enumerate(response.tool_calls):
                print(f"   Tools{i+1}: {tool_call.get('name', 'unknown')}")
            
            # Here the tool execution should continue and generate the final analysis
            # But for testing, we only verify whether the tool call is normal
            return True
        else:
            print(f"❌ No tool calls")
            print(f"📋 direct response: {response.content[:200]}...")
            
            # Check response length
            if len(response.content) < 100:
                print("❌ The response is too short, there may be a problem")
                return False
            else:
                print("⚠️ Responsive but no tool calls")
                return False
        
    except Exception as e:
        print(f"❌ Technical analysis test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_trading_graph_integration():
    """Test integration with TradingGraph"""
    print("\n🔧 Test integration with TradingGraph")
    print("=" * 60)
    
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        
        # Create configuration
        config = {
            "llm_provider": "dashscope",
            "deep_think_llm": "qwen-plus-latest",
            "quick_think_llm": "qwen-turbo",
            "max_debate_rounds": 1,
            "online_tools": True,
            "selected_analysts": ["fundamentals_analyst", "market_analyst"]
        }
        
        print("🔄 Create TradingGraph...")
        graph = TradingAgentsGraph(config)
        
        print("✅ TradingGraph Created successfully")
        print(f"   Deep thinking LLM: {type(graph.deep_thinking_llm).__name__}")
        print(f"   Quick thinking LLM: {type(graph.quick_thinking_llm).__name__}")
        
        # Check if new adapter is used
        if "OpenAI" in type(graph.deep_thinking_llm).__name__:
            print("✅ Uses new OpenAI compatible adapter")
            return True
        else:
            print("⚠️ Still using old adapter")
            return False
        
    except Exception as e:
        print(f"❌ TradingGraph Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function"""
    print("🔬 Alibaba Bailian OpenAI compatible adapter repair verification test")
    print("=" * 70)
    print("💡 Test target:")
    print("   - Verify new OpenAI compatible adapter import and connection")
    print("   - Verify Function Calling functionality")
    print("   - Verify technical analysis tool calls")
    print("   - Verify integration with TradingGraph")
    print("=" * 70)
    
    # Check environment variables
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("❌ DASHSCOPE_API_KEY environment variable not found")
        print("Please set environment variables and try again")
        return
    
    # Run all tests
    tests = [
        ("New adapter import", test_openai_adapter_import),
        ("OpenAI Compatible adapter connection", test_openai_adapter_connection),
        ("Function Calling", test_openai_adapter_function_calling),
        ("Technical analysis tool call", test_technical_analysis_with_new_adapter),
        ("TradingGraph Integrate", test_trading_graph_integration)
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
    print("\n📋 Alibaba Bailian OpenAI compatible adapter repair test summary")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\n📊 Test results: {passed}/{total} Pass")
    
    if passed == total:
        print("\n🎉 All tests passed! OpenAI compatible adapter repaired successfully!")
        print("\n💡 Repair effect:")
        print("   ✅ Support native Function Calling")
        print("   ✅ Tool calls are executed normally")
        print("   ✅ Technical analysis no longer has 30 characters")
        print("   ✅ Fully compatible with LangChain")
        print("\n🚀 Now the Ali Bailian model should be able to perform technical analysis normally!")
    else:
        print("\n⚠️ Some tests failed, please check the relevant configuration")
    
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
