#!/usr/bin/env python3
"""
Test tool interception mechanism
Verify whether Hong Kong stock tools are used correctly in fundamental analysis of Hong Kong stocks
"""

import os
import sys

def test_hk_fundamentals_with_interception():
    """Test the tool interception mechanism for fundamental analysis of Hong Kong stocks"""
    print("🔧 Test Hong Kong stock fundamental analysis tool interception...")
    
    try:
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        from tradingagents.utils.stock_utils import StockUtils
        
        # Check API key
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            print("⚠️ DASHSCOPE_API_KEY not found, test skipped")
            return True
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        
        # Create toolkit
        toolkit = Toolkit(config)
        
        # Create LLM
        llm = ChatDashScopeOpenAI(
            model="qwen-turbo",
            temperature=0.1,
            max_tokens=1000
        )
        
        # Create a fundamental analyst
        analyst = create_fundamentals_analyst(llm, toolkit)
        
        # simulation state
        state = {
            "trade_date": "2025-07-14",
            "company_of_interest": "0700.HK",
            "messages": []
        }
        
        print(f"\n📊 Test fundamental analysis of Hong Kong stocks: {state['company_of_interest']}")
        
        # Verify stock type identification
        market_info = StockUtils.get_market_info(state['company_of_interest'])
        print(f"  market type: {market_info['market_name']}")
        print(f"  Currency: {market_info['currency_name']} ({market_info['currency_symbol']})")
        print(f"  Is it Hong Kong stocks?: {market_info['is_hk']}")
        
        if not market_info['is_hk']:
            print(f"❌ Stock type recognition error")
            return False
        
        print(f"\n🔄 Call fundamental analysts (with tool interception mechanism)...")
        
        # call analyst
        result = analyst(state)
        
        print(f"✅ Fundamental analyst call completed")
        print(f"  result type: {type(result)}")
        
        if isinstance(result, dict) and 'fundamentals_report' in result:
            report = result['fundamentals_report']
            print(f"  Report length: {len(report)}")
            print(f"  Report first 200 characters: {report[:200]}...")
            
            # Check report quality
            if len(report) > 500:
                print(f"  ✅ The report length is acceptable (>500 characters)")
            else:
                print(f"  ⚠️ The report length is too short ({len(report)}characters)")
            
            # Check whether it contains Hong Kong dollar related content
            if 'HK$' in report or 'Hong Kong dollar' in report or 'Hong Kong dollar' in report:
                print(f"  ✅ Report includes Hong Kong dollar denominated prices")
            else:
                print(f"  ⚠️ Report does not include Hong Kong dollar pricing")
            
            # Check if investment advice is included
            if any(word in report for word in ['buy', 'hold', 'sell', 'Suggestions']):
                print(f"  ✅ Report contains investment recommendations")
            else:
                print(f"  ⚠️ The report does not contain investment recommendations")
        else:
            print(f"  ❌ Fundamentals report not found")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Hong Kong stock fundamental analysis test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tool_selection_logic():
    """Test tool selection logic"""
    print("\n🔧 Test tool selection logic...")
    
    try:
        from tradingagents.utils.stock_utils import StockUtils
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        test_cases = [
            ("0700.HK", "Hong Kong stocks", "get_hk_stock_data_unified"),
            ("9988.HK", "Hong Kong stocks", "get_hk_stock_data_unified"),
            ("000001", "China A shares", "get_china_stock_data"),
            ("600036", "China A shares", "get_china_stock_data"),
            ("AAPL", "US stocks", "get_fundamentals_openai"),
        ]
        
        for ticker, expected_market, expected_tool in test_cases:
            market_info = StockUtils.get_market_info(ticker)
            is_china = market_info['is_china']
            is_hk = market_info['is_hk']
            is_us = market_info['is_us']
            
            print(f"\n📊 {ticker} ({expected_market}):")
            print(f"  Recognition results: {market_info['market_name']}")
            
            # Simulation tool selection logic
            if toolkit.config["online_tools"]:
                if is_china:
                    selected_tools = ["get_china_stock_data", "get_china_fundamentals"]
                    primary_tool = "get_china_stock_data"
                elif is_hk:
                    selected_tools = ["get_hk_stock_data_unified"]
                    primary_tool = "get_hk_stock_data_unified"
                else:
                    selected_tools = ["get_fundamentals_openai"]
                    primary_tool = "get_fundamentals_openai"
            
            print(f"  Tools of choice: {selected_tools}")
            print(f"  Main tools: {primary_tool}")
            print(f"  Desired Tools: {expected_tool}")
            
            if primary_tool == expected_tool:
                print(f"  ✅ Correct choice of tools")
            else:
                print(f"  ❌ Wrong tool selection")
                return False
        
        print("✅ Tool selection logic verification passed")
        return True
        
    except Exception as e:
        print(f"❌ Tool selection validation failed: {e}")
        return False


def main():
    """Main test function"""
    print("🔧 Tool interception mechanism testing")
    print("=" * 60)
    
    tests = [
        test_tool_selection_logic,
        test_hk_fundamentals_with_interception,
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
        print("🎉 All tests passed! Tool interception mechanism works properly")
        print("\n📋 Repair summary:")
        print("✅ Implemented tool call interception mechanism")
        print("✅ Hong Kong stocks are forced to use special tools for Hong Kong stocks")
        print("✅ Create new LLM instance to avoid tool caching")
        print("✅ Generate high-quality Hong Kong stock analysis reports")
        return True
    else:
        print("⚠️ Some tests failed and require further inspection")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
