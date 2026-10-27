#!/usr/bin/env python3
"""
Debugging tool selection issue - check list of tools actually seen by LLM
"""

import os
import sys

def test_llm_tool_binding():
    """Actual tool list when testing LLM tool binding"""
    print("🔧 Test LLM tool binding...")
    
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
        
        # Check out all the tools in the toolkit
        print(f"\n📋 All tools in the toolkit:")
        all_tools = []
        for attr_name in dir(toolkit):
            if not attr_name.startswith('_') and callable(getattr(toolkit, attr_name)):
                attr = getattr(toolkit, attr_name)
                if hasattr(attr, 'name'):
                    all_tools.append((attr_name, attr.name))
                    print(f"  {attr_name}: {attr.name}")
        
        # Check Hong Kong stock related tools
        hk_related_tools = [tool for tool in all_tools if 'hk' in tool[0].lower() or 'hk' in tool[1].lower()]
        print(f"\n🇭🇰 Hong Kong stock related tools:")
        for attr_name, tool_name in hk_related_tools:
            print(f"  {attr_name}: {tool_name}")
        
        # Check Fundamentals Related Tools
        fundamentals_tools = [tool for tool in all_tools if 'fundamental' in tool[0].lower() or 'fundamental' in tool[1].lower()]
        print(f"\n📊 Fundamentals related tools:")
        for attr_name, tool_name in fundamentals_tools:
            print(f"  {attr_name}: {tool_name}")
        
        return True
        
    except Exception as e:
        print(f"❌ Tool binding test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tool_descriptions():
    """Test tool description content"""
    print("\n🔧 Test tool description...")
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Check the description of key tools
        key_tools = [
            'get_hk_stock_data_unified',
            'get_fundamentals_openai',
            'get_china_stock_data'
        ]
        
        for tool_name in key_tools:
            if hasattr(toolkit, tool_name):
                tool = getattr(toolkit, tool_name)
                print(f"\n📋 {tool_name}:")
                print(f"  Name: {getattr(tool, 'name', 'N/A')}")
                print(f"  Description: {getattr(tool, 'description', 'N/A')}")
                
                # Check if the description mentions Hong Kong stocks
                desc = getattr(tool, 'description', '')
                if 'Hong Kong stocks' in desc or 'HK' in desc or 'Hong Kong' in desc:
                    print(f"  ✅ The description contains content related to Hong Kong stocks")
                else:
                    print(f"  ⚠️ The description does not contain content related to Hong Kong stocks")
        
        return True
        
    except Exception as e:
        print(f"❌ Tool description test failed: {e}")
        return False


def test_fundamentals_analyst_tool_selection():
    """Testing the Real Tool Choices of Fundamental Analysts"""
    print("\n🔧 Testing Fundamental Analyst Tool Selection...")
    
    try:
        # Simulating the tool selection logic of fundamental analysts
        from tradingagents.utils.stock_utils import StockUtils
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Test Hong Kong stocks
        ticker = "0700.HK"
        market_info = StockUtils.get_market_info(ticker)
        is_china = market_info['is_china']
        is_hk = market_info['is_hk']
        is_us = market_info['is_us']
        
        print(f"\n📊 stocks: {ticker}")
        print(f"  market information: {market_info['market_name']}")
        print(f"  is_china: {is_china}")
        print(f"  is_hk: {is_hk}")
        print(f"  is_us: {is_us}")
        
        # Simulation tool selection logic
        if toolkit.config["online_tools"]:
            if is_china:
                tools = [
                    toolkit.get_china_stock_data,
                    toolkit.get_china_fundamentals
                ]
                print(f"  Instrument of choice (A shares): {[tool.name for tool in tools]}")
            elif is_hk:
                tools = [toolkit.get_hk_stock_data_unified]
                print(f"  Instrument of choice (Hong Kong stocks): {[tool.name for tool in tools]}")
            else:
                tools = [toolkit.get_fundamentals_openai]
                print(f"  Instrument of choice (US stocks): {[tool.name for tool in tools]}")
        
        # Check for tool name conflicts
        tool_names = [tool.name for tool in tools]
        print(f"  Tool name list: {tool_names}")
        
        # Check tool description
        for tool in tools:
            print(f"  Tools {tool.name} Description: {tool.description[:100]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Fundamental Analyst Tool Selection Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function"""
    print("🔧 Tool selection debugging test")
    print("=" * 60)
    
    tests = [
        test_llm_tool_binding,
        test_tool_descriptions,
        test_fundamentals_analyst_tool_selection,
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
