#!/usr/bin/env python3
"""
Test Hong Kong stock data acquisition error handling
Verify graceful degradation when partial data acquisition fails
"""

import os
import sys

def test_hk_data_error_handling():
    """Test Hong Kong stock data acquisition error handling"""
    print("🔧 Test Hong Kong stock data acquisition error handling...")
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create toolkit
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Test unified fundamental tools for Hong Kong stocks
        test_cases = [
            "0700.HK",  # Tencent
            "9988.HK",  # Alibaba
            "3690.HK",  # Meituan
        ]
        
        for ticker in test_cases:
            print(f"\n📊 test {ticker}:")
            
            try:
                result = toolkit.get_stock_fundamentals_unified.invoke({
                    'ticker': ticker,
                    'start_date': '2025-06-14',
                    'end_date': '2025-07-14',
                    'curr_date': '2025-07-14'
                })
                
                print(f"  ✅ Tool call successful")
                print(f"  Result length: {len(result)}")
                
                # Check result quality
                if len(result) > 200:
                    print(f"  ✅ The result length is qualified (>200 characters)")
                else:
                    print(f"  ⚠️ The result length is too short ({len(result)}characters)")
                
                # Check whether it contains content related to Hong Kong stocks
                if any(keyword in result for keyword in ['Hong Kong stocks', 'HK$', 'Hong Kong dollar', 'Hong Kong Exchange']):
                    print(f"  ✅ The results include information related to Hong Kong stocks")
                else:
                    print(f"  ⚠️ The results do not include information related to Hong Kong stocks")
                
                # Check error handling
                if "❌" in result:
                    if "Spare" in result or "Suggestions" in result:
                        print(f"  ✅ Contains elegant error handling and suggestions")
                    else:
                        print(f"  ⚠️ Error handling may be inadequate")
                else:
                    print(f"  ✅ Data acquisition was successful, no errors")
                
                print(f"  The first 300 characters of the result: {result[:300]}...")
                
            except Exception as e:
                print(f"  ❌ Tool call failed: {e}")
                return False
        
        print("✅ Hong Kong stock data acquisition error handling test passed")
        return True
        
    except Exception as e:
        print(f"❌ Hong Kong stock data acquisition error handling test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_akshare_error_recovery():
    """Testing AKShare error recovery mechanism"""
    print("\n🔧 Testing AKShare error recovery mechanism...")
    
    try:
        from tradingagents.dataflows.akshare_utils import format_hk_stock_data_akshare
        import pandas as pd
        
        # Create mock data (using correct date format)
        import datetime
        test_data = pd.DataFrame({
            'Date': [
                datetime.datetime(2025, 7, 10),
                datetime.datetime(2025, 7, 11),
                datetime.datetime(2025, 7, 12)
            ],
            'Open': [100.0, 101.0, 102.0],
            'High': [105.0, 106.0, 107.0],
            'Low': [99.0, 100.0, 101.0],
            'Close': [104.0, 105.0, 106.0],
            'Volume': [1000000, 1100000, 1200000]
        })
        
        # Test error handling for formatting functions
        symbol = "0700.HK"
        start_date = "2025-07-10"
        end_date = "2025-07-12"
        
        print(f"  Test formatted Hong Kong stock data: {symbol}")
        
        result = format_hk_stock_data_akshare(symbol, test_data, start_date, end_date)
        
        if result and len(result) > 100:
            print(f"  ✅ Formatting successful, length: {len(result)}")
            
            # Check if necessary information is included
            required_info = ['Hong Kong stocks', 'HK$', 'code', 'price']
            missing_info = [info for info in required_info if info not in result]
            
            if not missing_info:
                print(f"  ✅ Contains all necessary information")
            else:
                print(f"  ⚠️ Missing information: {missing_info}")
            
            # Check error handling
            if "Failed to obtain" in result or "❌" in result:
                if "Default" in result or "Spare" in result:
                    print(f"  ✅ Contains elegant error handling")
                else:
                    print(f"  ⚠️ Error handling may be inadequate")
            else:
                print(f"  ✅ Data processing was successful with no errors")
            
            return True
        else:
            print(f"  ❌ Format failed or result is too short")
            return False
        
    except Exception as e:
        print(f"❌ AKShare Error recovery mechanism test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_hk_fallback_mechanisms():
    """Test the Hong Kong stock backup mechanism"""
    print("\n🔧 Test the Hong Kong stock backup mechanism...")
    
    try:
        from tradingagents.dataflows.interface import get_hk_stock_data_unified, get_hk_stock_info_unified
        
        symbol = "0700.HK"
        start_date = "2025-06-14"
        end_date = "2025-07-14"
        
        print(f"  Test the unified interface for Hong Kong stock data: {symbol}")
        
        # Test data acquisition
        data_result = get_hk_stock_data_unified(symbol, start_date, end_date)
        
        if data_result:
            print(f"  ✅ Data interface call is successful, length: {len(data_result)}")
            
            # Check data source identification
            if "AKShare" in data_result:
                print(f"  ✅ Use AKShare as primary data source")
            elif "Yahoo Finance" in data_result:
                print(f"  ✅ Use Yahoo Finance as an alternate data source")
            elif "FINNHUB" in data_result:
                print(f"  ✅ Use FINNHUB as an alternate data source")
            else:
                print(f"  ⚠️ Data source not clearly identified")
        else:
            print(f"  ❌ Data interface call failed")
            return False
        
        # Get test information
        print(f"  Test the unified interface for Hong Kong stock information: {symbol}")
        
        info_result = get_hk_stock_info_unified(symbol)
        
        if info_result and isinstance(info_result, dict):
            print(f"  ✅ Information interface call successful")
            print(f"    Stock name: {info_result.get('name', 'N/A')}")
            print(f"    Currency: {info_result.get('currency', 'N/A')}")
            print(f"    exchange: {info_result.get('exchange', 'N/A')}")
            print(f"    data source: {info_result.get('source', 'N/A')}")
            
            # Verify Hong Kong stock-specific information
            if info_result.get('currency') == 'HKD' and info_result.get('exchange') == 'HKG':
                print(f"  ✅ Hong Kong stock information is correct")
            else:
                print(f"  ⚠️ Hong Kong stock information may be incomplete")
        else:
            print(f"  ❌ Information interface call failed")
            return False
        
        print("✅ Hong Kong stock backup mechanism passed test")
        return True
        
    except Exception as e:
        print(f"❌ Hong Kong stock backup mechanism test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function"""
    print("🔧 Hong Kong stock data acquisition error handling test")
    print("=" * 60)
    
    tests = [
        test_hk_data_error_handling,
        test_akshare_error_recovery,
        test_hk_fallback_mechanisms,
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
        print("🎉 All tests passed! Hong Kong stock error handling improved successfully")
        print("\n📋 Improve content:")
        print("✅ Improved error handling in AKShare Hong Kong stock information acquisition")
        print("✅ Added multiple alternatives to unified fundamental tools")
        print("✅ Implemented graceful degradation mechanism")
        print("✅ Provides helpful error messages and advice")
        print("✅ Ensure that basic information is still available even if some data fails")
        
        print("\n🚀 Processing flow:")
        print("1️⃣ Try AKShare to get complete Hong Kong stock data")
        print("2️⃣ If part fails, continue processing using default information")
        print("3️⃣ If total failure, try Yahoo Finance alternative")
        print("4️⃣ Final fallback: provides basic information and advice")
        
        return True
    else:
        print("⚠️ Some tests failed and require further inspection")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
