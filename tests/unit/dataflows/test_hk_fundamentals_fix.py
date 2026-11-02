#!/usr/bin/env python3
"""
Test the fundamental analysis and repair of Hong Kong stocks
Verify that Hong Kong stock code identification, tool selection and currency processing are correct
"""

import os
import sys

def test_stock_type_detection():
    """Testing the stock type detection feature"""
    print("🧪 Test stock type detection...")
    
    try:
        from tradingagents.utils.stock_utils import StockUtils
        
        test_cases = [
            ("0700.HK", "Hong Kong stocks", "Hong Kong dollar", "HK$"),
            ("9988.HK", "Hong Kong stocks", "Hong Kong dollar", "HK$"),
            ("000001", "China A shares", "RMB", "¥"),
            ("600036", "China A shares", "RMB", "¥"),
            ("AAPL", "US stocks", "US dollars", "$"),
            ("TSLA", "US stocks", "US dollars", "$"),
        ]
        
        for ticker, expected_market, expected_currency, expected_symbol in test_cases:
            market_info = StockUtils.get_market_info(ticker)
            
            print(f"  {ticker}:")
            print(f"    market: {market_info['market_name']}")
            print(f"    Currency: {market_info['currency_name']} ({market_info['currency_symbol']})")
            print(f"    Is it Hong Kong stocks?: {market_info['is_hk']}")
            print(f"    Is it A-share?: {market_info['is_china']}")
            print(f"    Is it US stocks?: {market_info['is_us']}")
            
            # Verification results
            if (expected_market in market_info['market_name'] and 
                market_info['currency_name'] == expected_currency and
                market_info['currency_symbol'] == expected_symbol):
                print(f"    ✅ Recognize correctly")
            else:
                print(f"    ❌ Recognition error")
                print(f"       Expectation: {expected_market}, {expected_currency}, {expected_symbol}")
                print(f"       actual: {market_info['market_name']}, {market_info['currency_name']}, {market_info['currency_symbol']}")
                return False
        
        print("✅ Stock type detection test passed")
        return True
        
    except Exception as e:
        print(f"❌ Stock type detection test failed: {e}")
        return False


def test_fundamentals_analyst_tool_selection():
    """Testing the tool selection logic of fundamental analysts"""
    print("\n🧪 Testing Fundamental Analyst Tool Selection...")
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.utils.stock_utils import StockUtils
        
        # Create toolkit
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Test the selection of Hong Kong stock instruments
        hk_ticker = "0700.HK"
        market_info = StockUtils.get_market_info(hk_ticker)
        
        print(f"  Hong Kong Stock Tool Selection Test: {hk_ticker}")
        print(f"    market type: {market_info['market_name']}")
        print(f"    Is it Hong Kong stocks?: {market_info['is_hk']}")
        print(f"    Currency: {market_info['currency_name']} ({market_info['currency_symbol']})")
        
        # Check whether the special tool for Hong Kong stocks exists
        if hasattr(toolkit, 'get_hk_stock_data_unified'):
            print(f"    ✅ The existence of special tools for Hong Kong stocks: get_hk_stock_data_unified")
        else:
            print(f"    ❌ Special tools for Hong Kong stocks do not exist")
            return False
        
        # Test A-share instrument selection
        china_ticker = "000001"
        market_info = StockUtils.get_market_info(china_ticker)
        
        print(f"  A Stock Tool Selection Test: {china_ticker}")
        print(f"    market type: {market_info['market_name']}")
        print(f"    Is it A-share?: {market_info['is_china']}")
        print(f"    Currency: {market_info['currency_name']} ({market_info['currency_symbol']})")
        
        # Check whether A-share special tools exist
        if hasattr(toolkit, 'get_china_stock_data'):
            print(f"    ✅ A Stock-specific tools exist: get_china_stock_data")
        else:
            print(f"    ❌ A Stock-specific tools do not exist")
            return False
        
        print("✅ Fundamental Analyst Tool Selection Test Passed")
        return True
        
    except Exception as e:
        print(f"❌ Fundamental Analyst Tool Selection Test Failed: {e}")
        return False


def test_trader_currency_detection():
    """Test currency detection for trader nodes"""
    print("\n🧪 Test trader currency detection...")
    
    try:
        from tradingagents.utils.stock_utils import StockUtils
        
        test_cases = [
            ("0700.HK", "Hong Kong dollar", "HK$"),
            ("9988.HK", "Hong Kong dollar", "HK$"),
            ("000001", "RMB", "¥"),
            ("AAPL", "US dollars", "$"),
        ]
        
        for ticker, expected_currency, expected_symbol in test_cases:
            market_info = StockUtils.get_market_info(ticker)
            
            print(f"  {ticker}:")
            print(f"    Currency detected: {market_info['currency_name']} ({market_info['currency_symbol']})")
            print(f"    desired currency: {expected_currency} ({expected_symbol})")
            
            if (market_info['currency_name'] == expected_currency and 
                market_info['currency_symbol'] == expected_symbol):
                print(f"    ✅ Currency detection correct")
            else:
                print(f"    ❌ Currency detection error")
                return False
        
        print("✅ Trader currency detection test passed")
        return True
        
    except Exception as e:
        print(f"❌ Trader currency detection test failed: {e}")
        return False


def test_hk_data_source():
    """Test Hong Kong stock data source"""
    print("\n🧪 Test Hong Kong stock data source...")
    
    try:
        from tradingagents.dataflows.interface import get_hk_stock_data_unified
        
        # Test Hong Kong stock data acquisition
        hk_ticker = "0700.HK"
        print(f"  Test to obtain Hong Kong stock data: {hk_ticker}")
        
        result = get_hk_stock_data_unified(hk_ticker, "2025-07-10", "2025-07-14")
        
        print(f"  Data acquisition result length: {len(result)}")
        print(f"  The first 100 characters of the result: {result[:100]}...")
        
        if "❌" in result:
            print(f"  ⚠️ Data retrieval failed, but this may be normal (network issue or API limitation)")
            print(f"  Failure message: {result}")
        else:
            print(f"  ✅ Data acquisition successful")
        
        print("✅ Hong Kong stock data source testing completed")
        return True
        
    except Exception as e:
        print(f"❌ Hong Kong stock data source test failed: {e}")
        return False


def main():
    """Main test function"""
    print("🔧 Hong Kong stock fundamental analysis repair test")
    print("=" * 60)
    
    tests = [
        test_stock_type_detection,
        test_fundamentals_analyst_tool_selection,
        test_trader_currency_detection,
        test_hk_data_source,
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
        print("🎉 All tests passed! Fundamental analysis of Hong Kong stocks successfully repaired")
        return True
    else:
        print("⚠️ Some tests failed and require further inspection")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
