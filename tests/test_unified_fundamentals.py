#!/usr/bin/env python3
"""
Testing the Unified Fundamental Analysis Tool
Verify that the new unified tool solution is effective
"""

import os
import sys

def test_unified_tool_directly():
    """Direct testing of unified fundamental analysis tools"""
    print("🔧 Direct testing of unified fundamental analysis tools...")
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create toolkit
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Test different types of stocks
        test_cases = [
            ("0700.HK", "Hong Kong stocks"),
            ("9988.HK", "Hong Kong stocks"),
            ("000001", "China A shares"),
            ("AAPL", "US stocks"),
        ]
        
        for ticker, expected_type in test_cases:
            print(f"\n📊 test {ticker} ({expected_type}):")
            
            try:
                result = toolkit.get_stock_fundamentals_unified.invoke({
                    'ticker': ticker,
                    'start_date': '2025-06-14',
                    'end_date': '2025-07-14',
                    'curr_date': '2025-07-14'
                })
                
                print(f"  ✅ Tool call successful")
                print(f"  Result length: {len(result)}")
                print(f"  The first 200 characters of the result: {result[:200]}...")
                
                # Check if the results contain expected content
                if expected_type in result:
                    print(f"  ✅ Results contain the correct stock type")
                else:
                    print(f"  ⚠️ Results did not contain the expected stock type")
                
                # Check if currency information is included
                if any(currency in result for currency in ['¥', 'HK$', '$']):
                    print(f"  ✅ Results contain currency information")
                else:
                    print(f"  ⚠️ Results do not contain currency information")
                    
            except Exception as e:
                print(f"  ❌ Tool call failed: {e}")
                return False
        
        print("✅ The unified tool directly passes the test")
        return True
        
    except Exception as e:
        print(f"❌ Unified tool direct test fails: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fundamentals_analyst_with_unified_tool():
    """Test fundamental analysts using unified tools"""
    print("\n🔧 Test fundamental analysts using unified tools...")
    
    try:
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        
        # Check API key
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            print("⚠️ DASHSCOPE_API_KEY not found, skipping LLM test")
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
        
        # Test Hong Kong stocks
        state = {
            "trade_date": "2025-07-14",
            "company_of_interest": "0700.HK",
            "messages": []
        }
        
        print(f"  Test fundamental analysis of Hong Kong stocks: {state['company_of_interest']}")
        
        # call analyst
        result = analyst(state)
        
        print(f"  ✅ Fundamental analyst call completed")
        print(f"  result type: {type(result)}")
        
        if isinstance(result, dict) and 'fundamentals_report' in result:
            report = result['fundamentals_report']
            print(f"  Report length: {len(report)}")
            print(f"  Report first 200 characters: {report[:200]}...")
            
            # Check report quality
            if len(report) > 200:
                print(f"  ✅ The report length is acceptable (>200 characters)")
            else:
                print(f"  ⚠️ The report length is too short ({len(report)}characters)")
            
            # Check whether it contains Hong Kong dollar related content
            if 'HK$' in report or 'Hong Kong dollar' in report or 'Hong Kong dollar' in report:
                print(f"  ✅ Report includes Hong Kong dollar denominated prices")
            else:
                print(f"  ⚠️ Report does not include Hong Kong dollar pricing")
        else:
            print(f"  ❌ Fundamentals report not found")
            return False
        
        print("✅ Fundamental Analyst Unified Tool Test Passed")
        return True
        
    except Exception as e:
        print(f"❌ Fundamental Analyst Unified Tool Test Fails: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_stock_type_detection():
    """Test stock type detection"""
    print("\n🔧 Test stock type detection...")
    
    try:
        from tradingagents.utils.stock_utils import StockUtils
        
        test_cases = [
            ("0700.HK", "Hong Kong stocks", "Hong Kong dollar", "HK$"),
            ("9988.HK", "Hong Kong stocks", "Hong Kong dollar", "HK$"),
            ("000001", "China A shares", "RMB", "¥"),
            ("600036", "China A shares", "RMB", "¥"),
            ("AAPL", "US stocks", "US dollars", "$"),
        ]
        
        for ticker, expected_market, expected_currency, expected_symbol in test_cases:
            market_info = StockUtils.get_market_info(ticker)
            
            print(f"  {ticker}:")
            print(f"    market: {market_info['market_name']}")
            print(f"    Currency: {market_info['currency_name']} ({market_info['currency_symbol']})")
            
            # Verification results
            if (expected_market in market_info['market_name'] and 
                market_info['currency_name'] == expected_currency and
                market_info['currency_symbol'] == expected_symbol):
                print(f"    ✅ Recognize correctly")
            else:
                print(f"    ❌ Recognition error")
                return False
        
        print("✅ Stock type detection test passed")
        return True
        
    except Exception as e:
        print(f"❌ Stock type detection test failed: {e}")
        return False


def main():
    """Main test function"""
    print("🔧 Unified fundamental analysis tool testing")
    print("=" * 60)
    
    tests = [
        test_stock_type_detection,
        test_unified_tool_directly,
        test_fundamentals_analyst_with_unified_tool,
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
        print("🎉 All tests passed! The unified fundamental analysis tool solution was successful")
        print("\n📋 Solution advantages:")
        print("✅ Simplified tool selection logic")
        print("✅ Automatically identify stock types within the tool")
        print("✅ Avoids LLM tool calling confusion")
        print("✅ Unified system prompts and processing procedures")
        print("✅ Easier to maintain and extend")
        return True
    else:
        print("⚠️ Some tests failed and require further inspection")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
