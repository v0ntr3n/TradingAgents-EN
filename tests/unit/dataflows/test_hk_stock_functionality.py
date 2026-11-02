"""
Test the Hong Kong stock function
Verify Hong Kong stock code identification, data acquisition and processing functions
"""

import sys
import os
import traceback

# Add project root directory to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_stock_utils():
    """Test stock tools"""
    print("\n🧪 Test stock tools...")
    
    try:
        from tradingagents.utils.stock_utils import StockUtils
        
        # Test Hong Kong stock code recognition
        test_cases = [
            ("0700.HK", "Hong Kong stocks"),
            ("9988.HK", "Hong Kong stocks"),
            ("3690.HK", "Hong Kong stocks"),
            ("000001", "China A shares"),
            ("600036", "China A shares"),
            ("AAPL", "US stocks"),
            ("TSLA", "US stocks"),
            ("invalid", "unknown market")
        ]
        
        for ticker, expected in test_cases:
            market_info = StockUtils.get_market_info(ticker)
            print(f"  {ticker}: {market_info['market_name']} ({market_info['currency_name']}) - {'✅' if expected in market_info['market_name'] else '❌'}")
            
            if expected == "Hong Kong stocks" and not market_info['is_hk']:
                print(f"❌ {ticker} should be identified as Hong Kong stocks")
                return False
            elif expected == "China A shares" and not market_info['is_china']:
                print(f"❌ {ticker} Should be identified as China A-shares")
                return False
            elif expected == "US stocks" and not market_info['is_us']:
                print(f"❌ {ticker} Should be identified as US stocks")
                return False
        
        print("✅ Passed the stock instrument test")
        return True
        
    except Exception as e:
        print(f"❌ Stock instrument class test failed: {e}")
        traceback.print_exc()
        return False


def test_hk_stock_provider():
    """Test Hong Kong stock data provider"""
    print("\n🧪 Test Hong Kong stock data provider...")
    
    try:
        from tradingagents.dataflows.hk_stock_utils import get_hk_stock_provider
        
        provider = get_hk_stock_provider()
        
        # Testing Hong Kong stock code standardization
        test_symbols = [
            ("0700", "0700.HK"),
            ("0700.HK", "0700.HK"),
            ("9988", "9988.HK"),
            ("3690.HK", "3690.HK")
        ]
        
        for input_symbol, expected in test_symbols:
            normalized = provider._normalize_hk_symbol(input_symbol)
            print(f"  Standardization: {input_symbol} -> {normalized} {'✅' if normalized == expected else '❌'}")
            
            if normalized != expected:
                print(f"❌ Hong Kong stock code standardization fails: {input_symbol} -> {normalized}, Expectation: {expected}")
                return False
        
        print("✅ Hong Kong stock data provider test passed")
        return True
        
    except Exception as e:
        print(f"❌ Hong Kong stock data provider test failed: {e}")
        traceback.print_exc()
        return False


def test_hk_stock_info():
    """Test the acquisition of Hong Kong stock information"""
    print("\n🧪 Test the acquisition of Hong Kong stock information...")
    
    try:
        from tradingagents.dataflows.hk_stock_utils import get_hk_stock_info
        
        # Test Tencent Hong Kong stock information
        hk_symbol = "0700.HK"
        print(f"  get {hk_symbol} information...")
        
        info = get_hk_stock_info(hk_symbol)
        
        if info and 'symbol' in info:
            print(f"  ✅ Stock code: {info['symbol']}")
            print(f"  ✅ Stock name: {info['name']}")
            print(f"  ✅ Currency: {info['currency']}")
            print(f"  ✅ exchange: {info['exchange']}")
            print(f"  ✅ data source: {info['source']}")
            
            # Validate basic fields
            if info['currency'] != 'HKD':
                print(f"⚠️ The currency of Hong Kong stocks should be HKD, but it is actually: {info['currency']}")
            
            if info['exchange'] != 'HKG':
                print(f"⚠️ The Hong Kong Stock Exchange should be HKG, but it is actually: {info['exchange']}")
            
            print("✅ Hong Kong stock information acquisition test passed")
            return True
        else:
            print("❌ Failed to obtain Hong Kong stock information")
            return False
            
    except Exception as e:
        print(f"❌ Hong Kong stock information acquisition test failed: {e}")
        traceback.print_exc()
        return False


def test_hk_stock_data():
    """Test the acquisition of Hong Kong stock data (simple test)"""
    print("\n🧪 Test Hong Kong stock data acquisition...")
    
    try:
        from tradingagents.dataflows.hk_stock_utils import get_hk_stock_data
        from datetime import datetime, timedelta
        
        # Set test date range (last 30 days)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        # Test Tencent Hong Kong stock data
        hk_symbol = "0700.HK"
        print(f"  get {hk_symbol} data ({start_date} Arrive {end_date})...")
        
        data_text = get_hk_stock_data(hk_symbol, start_date, end_date)
        
        if data_text and "Hong Kong Stock Data Report" in data_text:
            print("  ✅ Hong Kong stock data format is correct")
            print(f"  ✅ Data length: {len(data_text)}character")
            
            # Check key information
            if "HK$" in data_text:
                print("  ✅ Contains Hong Kong dollar price information")
            else:
                print("  ⚠️ Missing Hong Kong dollar price information")
            
            if "Hong Kong Exchange" in data_text:
                print("  ✅ Contains exchange information")
            
            print("✅ Hong Kong stock data acquisition test passed")
            return True
        else:
            print("❌ Failed to obtain Hong Kong stock data or format error")
            print(f"Return data: {data_text[:200]}...")
            return False
            
    except Exception as e:
        print(f"❌ Hong Kong stock data acquisition test failed: {e}")
        traceback.print_exc()
        return False


def test_optimized_us_data_hk_support():
    """Test and optimize the Hong Kong stock support of the US stock data module"""
    print("\n🧪 Test optimization data module Hong Kong stock support...")
    
    try:
        from tradingagents.dataflows.optimized_us_data import get_us_stock_data_cached
        from datetime import datetime, timedelta
        
        # Set test date range
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        # Test Hong Kong stock data acquisition
        hk_symbol = "0700.HK"
        print(f"  Obtained through optimization module {hk_symbol} data...")
        
        data_text = get_us_stock_data_cached(
            symbol=hk_symbol,
            start_date=start_date,
            end_date=end_date,
            force_refresh=True
        )
        
        if data_text and "data analysis" in data_text:
            print("  ✅ Data acquisition successful")
            
            # Check Hong Kong stock specific information
            if "Hong Kong stocks" in data_text:
                print("  ✅ Correctly identified as Hong Kong stocks")
            
            if "HK$" in data_text:
                print("  ✅ Use Hong Kong dollar symbol")
            else:
                print("  ⚠️ Hong Kong dollar symbol not used")
            
            print("✅ Optimized data module Hong Kong stocks support test passed")
            return True
        else:
            print("❌ Optimized data module Hong Kong stock support test failed")
            return False
            
    except Exception as e:
        print(f"❌ Optimized data module Hong Kong stock support test failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all Hong Kong stock functional tests"""
    print("🇭🇰 Start Hong Kong stock function test")
    print("=" * 50)
    
    tests = [
        test_stock_utils,
        test_hk_stock_provider,
        test_hk_stock_info,
        test_hk_stock_data,
        test_optimized_us_data_hk_support
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ test {test_func.__name__} Abnormal: {e}")
    
    print("\n" + "=" * 50)
    print(f"🇭🇰 Hong Kong stock function test completed: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 All tests passed! Hong Kong stocks function normally")
        return True
    else:
        print("⚠️ Some tests failed and require further debugging")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
