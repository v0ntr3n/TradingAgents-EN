#!/usr/bin/env python3
"""
Debugging tool selection issues for fundamental analysts
"""

import os
import sys

def test_fundamentals_analyst_directly():
    """Directly test fundamental analyst functions"""
    print("🔧 Direct testing from fundamental analysts...")
    
    try:
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.llm_adapters.dashscope_openai_adapter import ChatDashScopeOpenAI
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        
        # Create toolkit
        toolkit = Toolkit(config)
        
        # Create LLM (simulation)
        class MockLLM:
            def bind_tools(self, tools):
                return self
            
            def invoke(self, messages):
                class MockResult:
                    def __init__(self):
                        self.tool_calls = []
                        self.content = "Simulation analysis results"
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
        
        print(f"  Test Hong Kong stocks: {state['company_of_interest']}")
        print(f"  Call a fundamental analyst...")
        
        # Call the analyst (this triggers the tool selection logic)
        result = analyst(state)
        
        print(f"  ✅ Fundamental analyst call completed")
        print(f"  result type: {type(result)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Direct test fails: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_stock_utils_import():
    """Test StockUtils imports and functionality"""
    print("\n🔧 Test StockUtils import...")
    
    try:
        from tradingagents.utils.stock_utils import StockUtils
        
        # Test Hong Kong stock identification
        ticker = "0700.HK"
        market_info = StockUtils.get_market_info(ticker)
        
        print(f"  stocks: {ticker}")
        print(f"  market information: {market_info}")
        print(f"  Is it Hong Kong stocks?: {market_info['is_hk']}")
        print(f"  Is it A-share?: {market_info['is_china']}")
        print(f"  Is it US stocks?: {market_info['is_us']}")
        
        if market_info['is_hk']:
            print(f"  ✅ StockUtils Correctly identify Hong Kong stocks")
            return True
        else:
            print(f"  ❌ StockUtils Unable to identify Hong Kong stocks")
            return False
        
    except Exception as e:
        print(f"❌ StockUtils test failed: {e}")
        return False


def test_toolkit_hk_tools():
    """Hong Kong stock tools in the testing toolkit"""
    print("\n🔧 Test tool kit Hong Kong stock tools...")
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Check whether the Hong Kong stock instrument exists
        hk_tools = [
            'get_hk_stock_data_unified',
            'get_china_stock_data',
            'get_fundamentals_openai'
        ]
        
        for tool_name in hk_tools:
            has_tool = hasattr(toolkit, tool_name)
            print(f"  {tool_name}: {'✅' if has_tool else '❌'}")
            
            if has_tool:
                tool = getattr(toolkit, tool_name)
                print(f"    Tool type: {type(tool)}")
                print(f"    Tool name: {getattr(tool, 'name', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Kit test failed: {e}")
        return False


def test_import_paths():
    """Test import path"""
    print("\n🔧 Test import path...")
    
    imports_to_test = [
        "tradingagents.agents.analysts.fundamentals_analyst",
        "tradingagents.utils.stock_utils",
        "tradingagents.agents.utils.agent_utils",
        "tradingagents.default_config"
    ]
    
    for import_path in imports_to_test:
        try:
            __import__(import_path)
            print(f"  {import_path}: ✅")
        except Exception as e:
            print(f"  {import_path}: ❌ - {e}")
            return False
    
    return True


def main():
    """Main test function"""
    print("🔧 Fundamental Analyst Debugging Test")
    print("=" * 60)
    
    tests = [
        test_import_paths,
        test_stock_utils_import,
        test_toolkit_hk_tools,
        test_fundamentals_analyst_directly,
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
        print("🎉 All tests passed!")
        return True
    else:
        print("⚠️ Some tests failed and require further inspection")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
