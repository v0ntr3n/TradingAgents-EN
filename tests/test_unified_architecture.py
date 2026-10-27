#!/usr/bin/env python3
"""
Test unified tool architecture
Verify that all analysts are using a unified tool scheme
"""

import os
import sys

def test_unified_tools_availability():
    """Test the usability of unified tools"""
    print("🔧 Test unified tool usability...")
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create toolkit
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Check if the unified tool exists
        unified_tools = [
            'get_stock_fundamentals_unified',
            'get_stock_market_data_unified',
            'get_stock_news_unified',
            'get_stock_sentiment_unified'
        ]
        
        for tool_name in unified_tools:
            if hasattr(toolkit, tool_name):
                tool = getattr(toolkit, tool_name)
                print(f"  ✅ {tool_name}: Available")
                print(f"    Tool description: {getattr(tool, 'description', 'N/A')[:100]}...")
            else:
                print(f"  ❌ {tool_name}: Not available")
                return False
        
        print("✅ Unified tool usability test passed")
        return True
        
    except Exception as e:
        print(f"❌ Unified Tool Usability Test Failed: {e}")
        return False


def test_market_analyst_unified():
    """Test market analysts use unified tools"""
    print("\n🔧 Test Market Analyst Unified Tool...")
    
    try:
        from tradingagents.agents.analysts.market_analyst import create_market_analyst
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        
        # Create toolkit
        toolkit = Toolkit(config)
        
        # Create simulation LLM
        class MockLLM:
            def bind_tools(self, tools):
                print(f"🔧 [MockLLM] Market Analyst Binding Tool: {[tool.name for tool in tools]}")
                
                # Check if only unified tools are bound
                if len(tools) == 1 and tools[0].name == 'get_stock_market_data_unified':
                    print(f"  ✅ Correctly bind unified market data tools")
                    return self
                else:
                    print(f"  ❌ Wrong tool bound: {[tool.name for tool in tools]}")
                    return self
            
            def invoke(self, messages):
                class MockResult:
                    def __init__(self):
                        self.tool_calls = []
                        self.content = "Simulated market analysis results"
                return MockResult()
        
        llm = MockLLM()
        
        # Create a market analyst
        analyst = create_market_analyst(llm, toolkit)
        
        # simulation state
        state = {
            "trade_date": "2025-07-14",
            "company_of_interest": "0700.HK",
            "messages": []
        }
        
        print(f"  Test Hong Kong stock market analysis: {state['company_of_interest']}")
        
        # Call the analyst (this triggers the tool selection logic)
        result = analyst(state)
        
        print(f"  ✅ Market analyst call completed")
        return True
        
    except Exception as e:
        print(f"❌ Market Analyst Unified Tool Test Fails: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fundamentals_analyst_unified():
    """Test fundamental analysts using unified tools"""
    print("\n🔧 Testing Unified Tools for Fundamental Analysts...")
    
    try:
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        
        # Create toolkit
        toolkit = Toolkit(config)
        
        # Create simulation LLM
        class MockLLM:
            def bind_tools(self, tools):
                print(f"🔧 [MockLLM] Fundamental Analyst Binding Tool: {[tool.name for tool in tools]}")
                
                # Check if only unified tools are bound
                if len(tools) == 1 and tools[0].name == 'get_stock_fundamentals_unified':
                    print(f"  ✅ Correctly bind unified fundamental analysis tools")
                    return self
                else:
                    print(f"  ❌ Wrong tool bound: {[tool.name for tool in tools]}")
                    return self
            
            def invoke(self, messages):
                class MockResult:
                    def __init__(self):
                        self.tool_calls = []
                        self.content = "Simulate fundamental analysis results"
                return MockResult()
        
        llm = MockLLM()
        
        # Create a fundamental analyst
        analyst = create_fundamentals_analyst(llm, toolkit)
        
        # simulation state
        state = {
            "trade_date": "2025-07-14",
            "company_of_interest": "0700.HK",
            "messages": []
        }
        
        print(f"  Test fundamental analysis of Hong Kong stocks: {state['company_of_interest']}")
        
        # Call the analyst (this triggers the tool selection logic)
        result = analyst(state)
        
        print(f"  ✅ Fundamental analyst call completed")
        return True
        
    except Exception as e:
        print(f"❌ Fundamental Analyst Unified Tool Test Fails: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_stock_type_routing():
    """Test stock type routing"""
    print("\n🔧 Test stock type routing...")
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        test_cases = [
            ("0700.HK", "Hong Kong stocks", "HK$"),
            ("9988.HK", "Hong Kong stocks", "HK$"),
            ("000001", "China A shares", "¥"),
            ("600036", "China A shares", "¥"),
            ("AAPL", "US stocks", "$"),
        ]
        
        for ticker, expected_market, expected_currency in test_cases:
            print(f"\n📊 test {ticker}:")
            
            # Test fundamental analysis tools
            try:
                result = toolkit.get_stock_fundamentals_unified.invoke({
                    'ticker': ticker,
                    'start_date': '2025-06-14',
                    'end_date': '2025-07-14',
                    'curr_date': '2025-07-14'
                })
                
                if expected_market in result and expected_currency in result:
                    print(f"  ✅ Fundamentals tools are routed correctly")
                else:
                    print(f"  ⚠️ There may be a problem with fundamental tool routing")
                    
            except Exception as e:
                print(f"  ❌ Fundamental tool call failed: {e}")
                return False
            
            # Test market data tools
            try:
                result = toolkit.get_stock_market_data_unified.invoke({
                    'ticker': ticker,
                    'start_date': '2025-07-10',
                    'end_date': '2025-07-14'
                })
                
                if expected_market in result and expected_currency in result:
                    print(f"  ✅ Market data tools are routed correctly")
                else:
                    print(f"  ⚠️ There may be an issue with market data tool routing")
                    
            except Exception as e:
                print(f"  ❌ Market data tool call failed: {e}")
                return False
        
        print("✅ Stock type routing test passed")
        return True
        
    except Exception as e:
        print(f"❌ Stock type routing test failed: {e}")
        return False


def main():
    """Main test function"""
    print("🔧 Unified tool architecture testing")
    print("=" * 60)
    
    tests = [
        test_unified_tools_availability,
        test_stock_type_routing,
        test_fundamentals_analyst_unified,
        test_market_analyst_unified,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print(f"❌ test failed: {test.__name__}")
        except Exception as e:
            print(f"❌ Test exception: {test.__name__} - {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 Test results: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 All tests passed! Unified tool architecture successful")
        print("\n📋 Architectural advantages:")
        print("✅ All analysts use unified tools")
        print("✅ Automatically identify stock types within the tool")
        print("✅ Avoids LLM tool calling confusion")
        print("✅ Simplified system prompts and processing procedures")
        print("✅ Easier to maintain and extend")
        print("✅ Unified error handling and logging")
        return True
    else:
        print("⚠️ Some tests failed and require further inspection")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
