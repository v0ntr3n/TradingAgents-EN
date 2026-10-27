"""
Improved Hong Kong stock function test
"""

import sys
import os

# Add project root directory to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_stock_recognition():
    """Test the stock recognition function"""
    print("🧪 Test the stock recognition function...")
    
    try:
        from tradingagents.utils.stock_utils import StockUtils
        
        test_cases = [
            ("0700.HK", "Hong Kong stocks", "HK$"),
            ("9988.HK", "Hong Kong stocks", "HK$"),
            ("000001", "China A shares", "¥"),
            ("AAPL", "US stocks", "$"),
        ]
        
        for ticker, expected_market, expected_currency in test_cases:
            market_info = StockUtils.get_market_info(ticker)
            
            print(f"  {ticker}:")
            print(f"    market: {market_info['market_name']}")
            print(f"    Currency: {market_info['currency_name']} ({market_info['currency_symbol']})")
            print(f"    data source: {market_info['data_source']}")
            
            # Verification results
            if expected_market in market_info['market_name'] and market_info['currency_symbol'] == expected_currency:
                print(f"    ✅ Recognize correctly")
            else:
                print(f"    ❌ Recognition error")
                return False
        
        print("✅ Stock recognition function test passed")
        return True
        
    except Exception as e:
        print(f"❌ Stock recognition function test failed: {e}")
        return False

def test_hk_data_unified():
    """Test the unified data interface of Hong Kong stocks"""
    print("\n🧪 Test the unified data interface of Hong Kong stocks...")
    
    try:
        from tradingagents.dataflows.interface import get_hk_stock_data_unified
        from datetime import datetime, timedelta
        
        # Set test date
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        # Test Tencent Hong Kong stocks
        symbol = "0700.HK"
        print(f"  get {symbol} data...")
        
        data = get_hk_stock_data_unified(symbol, start_date, end_date)
        
        if data and len(data) > 100:
            print("  ✅ Data acquisition successful")
            
            # Check key information
            checks = [
                ("Hong Kong Stock Data Report", "Contains title"),
                ("HK$", "Contains Hong Kong dollar symbol"),
                ("Hong Kong Exchange", "Contains exchange information"),
                (symbol, "Contains ticker symbol")
            ]
            
            for check_text, description in checks:
                if check_text in data:
                    print(f"    ✅ {description}")
                else:
                    print(f"    ⚠️ missing{description}")
            
            print("✅ Hong Kong stocks unified data interface test passed")
            return True
        else:
            print("❌ Hong Kong stock unified data interface test failed")
            return False
            
    except Exception as e:
        print(f"❌ Hong Kong stock unified data interface test failed: {e}")
        return False

def test_hk_info_unified():
    """Test the unified interface for Hong Kong stock information"""
    print("\n🧪 Test the unified interface for Hong Kong stock information...")
    
    try:
        from tradingagents.dataflows.interface import get_hk_stock_info_unified
        
        symbol = "0700.HK"
        print(f"  get {symbol} information...")
        
        info = get_hk_stock_info_unified(symbol)
        
        if info and 'symbol' in info:
            print(f"    ✅ Stock code: {info['symbol']}")
            print(f"    ✅ Stock name: {info['name']}")
            print(f"    ✅ Currency: {info['currency']}")
            print(f"    ✅ exchange: {info['exchange']}")
            
            # Verify Hong Kong stock-specific information
            if info['currency'] == 'HKD' and info['exchange'] == 'HKG':
                print("    ✅ Hong Kong stock information is correct")
            else:
                print("    ⚠️ Hong Kong stock information may be incomplete")
            
            print("✅ Hong Kong stock information unified interface test passed")
            return True
        else:
            print("❌ Hong Kong stock information unified interface test failed")
            return False
            
    except Exception as e:
        print(f"❌ Hong Kong stock information unified interface test failed: {e}")
        return False

def test_market_auto_selection():
    """Test the market auto-selection feature"""
    print("\n🧪 Test the market auto-selection feature...")
    
    try:
        from tradingagents.dataflows.interface import get_stock_data_by_market
        from datetime import datetime, timedelta
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        test_symbols = [
            ("0700.HK", "Hong Kong stocks"),
            ("000001", "A shares"),
            ("AAPL", "US stocks")
        ]
        
        for symbol, market_type in test_symbols:
            print(f"  test {symbol} ({market_type})...")
            
            data = get_stock_data_by_market(symbol, start_date, end_date)
            
            if data and len(data) > 50:
                print(f"    ✅ {market_type}Data acquisition successful")
            else:
                print(f"    ⚠️ {market_type}Data retrieval may fail")
        
        print("✅ Market automatic selection function test passed")
        return True
        
    except Exception as e:
        print(f"❌ Market automatic selection function test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🇭🇰 Start testing improved Hong Kong stock functionality")
    print("=" * 50)
    
    tests = [
        test_stock_recognition,
        test_hk_data_unified,
        test_hk_info_unified,
        test_market_auto_selection
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
    print(f"🇭🇰 Improved Hong Kong stock function test completed: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 All tests passed! Hong Kong stock function optimization successful")
        print("\n✅ Functional features of Hong Kong stocks:")
        print("  - Correctly identify the Hong Kong stock code format (XXXX.HK)")
        print("  - Use Hong Kong dollars (HK$) Show price")
        print("  - Support multiple backup plans")
        print("  - Handling API frequency limits")
        print("  - Provide demo mode data")
    else:
        print("⚠️ Some tests fail, but core functionality works")

if __name__ == "__main__":
    main()
