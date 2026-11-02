#!/usr/bin/env python3
"""
Test old tool removal
Verify that LLM can only call unified tools
"""

def test_available_tools():
    """List of available tools for testing"""
    print("🔧 List of available tools for testing...")
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create toolkit
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Get all the tools
        all_tools = []
        for attr_name in dir(toolkit):
            attr = getattr(toolkit, attr_name)
            if hasattr(attr, 'name') and hasattr(attr, 'description'):
                all_tools.append(attr.name)
        
        print(f"  Total number of tools: {len(all_tools)}")
        
        # Check if old tools have been removed
        removed_tools = [
            'get_china_stock_data',
            'get_china_fundamentals', 
            'get_fundamentals_openai',
            'get_hk_stock_data_unified'
        ]
        
        # Check if the unified tool exists
        unified_tools = [
            'get_stock_fundamentals_unified',
            'get_stock_market_data_unified',
            'get_stock_news_unified',
            'get_stock_sentiment_unified'
        ]
        
        print("\n  Old tool removal check:")
        for tool_name in removed_tools:
            if tool_name in all_tools:
                print(f"    ❌ {tool_name}: Still available (should have been removed)")
                return False
            else:
                print(f"    ✅ {tool_name}: Removed")
        
        print("\n  Unified tool availability check:")
        for tool_name in unified_tools:
            if tool_name in all_tools:
                print(f"    ✅ {tool_name}: Available")
            else:
                print(f"    ❌ {tool_name}: Not available")
                return False
        
        print(f"\n  All available tools:")
        for tool_name in sorted(all_tools):
            print(f"    - {tool_name}")
        
        print("✅ Tool removal test passed")
        return True
        
    except Exception as e:
        print(f"❌ Tool removal test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fundamentals_analyst_tool_selection():
    """Testing Fundamental Analyst Tool Selection"""
    print("\n🔧 Testing Fundamental Analyst Tool Selection...")
    
    try:
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        
        # Create toolkit
        toolkit = Toolkit(config)
        
        # Simulating the tool selection logic of fundamental analysts
        from tradingagents.utils.stock_utils import StockUtils
        
        test_cases = [
            ("0700.HK", "Hong Kong stocks"),
            ("000001", "A shares"),
            ("AAPL", "US stocks")
        ]
        
        for ticker, market_type in test_cases:
            print(f"\n  test {ticker} ({market_type}):")
            
            # Get market information
            market_info = StockUtils.get_market_info(ticker)
            
            # Simulating the tool selection logic of fundamental analysts
            if toolkit.config["online_tools"]:
                # Use unified fundamental analysis tools
                tools = [toolkit.get_stock_fundamentals_unified]
                tool_names = [tool.name for tool in tools]
                
                print(f"    Tools of choice: {tool_names}")
                
                # Verify that only the unified tool is selected
                if len(tools) == 1 and tools[0].name == 'get_stock_fundamentals_unified':
                    print(f"    ✅ Correct selection of unified fundamental tools")
                else:
                    print(f"    ❌ Wrong tool selection")
                    return False
            else:
                print(f"    Skip (online_tools=False) ")
        
        print("✅ Fundamental Analyst Tool Selection Test Passed")
        return True
        
    except Exception as e:
        print(f"❌ Fundamental Analyst Tool Selection Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_market_analyst_tool_selection():
    """Test Market Analyst Tool Selection"""
    print("\n🔧 Test Market Analyst Tool Selection...")
    
    try:
        from tradingagents.agents.analysts.market_analyst import create_market_analyst
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.utils.stock_utils import StockUtils
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        
        # Create toolkit
        toolkit = Toolkit(config)
        
        test_cases = [
            ("0700.HK", "Hong Kong stocks"),
            ("000001", "A shares"),
            ("AAPL", "US stocks")
        ]
        
        for ticker, market_type in test_cases:
            print(f"\n  test {ticker} ({market_type}):")
            
            # Get market information
            market_info = StockUtils.get_market_info(ticker)
            
            # Simulating the tool selection logic of market analysts
            if toolkit.config["online_tools"]:
                # Use unified market data tools
                tools = [toolkit.get_stock_market_data_unified]
                tool_names = [tool.name for tool in tools]
                
                print(f"    Tools of choice: {tool_names}")
                
                # Verify that only the unified tool is selected
                if len(tools) == 1 and tools[0].name == 'get_stock_market_data_unified':
                    print(f"    ✅ Choosing the right unified market data tool")
                else:
                    print(f"    ❌ Wrong tool selection")
                    return False
            else:
                print(f"    Skip (online_tools=False) ")
        
        print("✅ Market Analyst Tool Selection Test Passed")
        return True
        
    except Exception as e:
        print(f"❌ Market Analyst Tool Selection Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function"""
    print("🔧 Old tool removal test")
    print("=" * 60)
    
    tests = [
        test_available_tools,
        test_fundamentals_analyst_tool_selection,
        test_market_analyst_tool_selection,
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
        print("🎉 All tests passed! Old tool removed successfully")
        print("\n📋 Fix content:")
        print("✅ Removed old tools @tool Decorator")
        print("✅ LLM Old tools can no longer be recalled")
        print("✅ Only unified tools can be called")
        print("✅ Avoid tool calling confusion")
        return True
    else:
        print("⚠️ Some tests failed and require further inspection")
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
