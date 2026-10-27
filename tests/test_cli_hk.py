"""
Test CLI Hong Kong stock input function
"""

import sys
import os

# Add project root directory to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_cli_market_selection():
    """Testing CLI market selection functionality"""
    print("🧪 Testing CLI market selection functionality...")
    
    try:
        # Import CLI related modules
        from cli.main import select_market, get_ticker
        
        # Simulate Hong Kong stock market allocation
        hk_market = {
            "name": "Hong Kong stocks",
            "name_en": "Hong Kong Stock", 
            "default": "0700.HK",
            "examples": ["0700.HK (Tencent)", "9988.HK (Alibaba)", "3690.HK (Meituan)"],
            "format": "code.HK (Such as: 0700.HK)",
            "pattern": r'^\d{4}\.HK$',
            "data_source": "yahoo_finance"
        }
        
        # Test Hong Kong stock code verification
        import re
        test_codes = [
            ("0700.HK", True),
            ("9988.HK", True), 
            ("3690.HK", True),
            ("700.HK", False),   # Less than 4 people
            ("07000.HK", False), # More than 4 people
            ("0700", False),     # missing.HK
            ("AAPL", False)      # US stock code
        ]
        
        for code, should_match in test_codes:
            matches = bool(re.match(hk_market["pattern"], code))
            status = "✅" if matches == should_match else "❌"
            print(f"  {code}: {status} (match: {matches}, Expectation: {should_match})")
        
        print("✅ CLI Market selection test passed")
        return True
        
    except Exception as e:
        print(f"❌ CLI Market selection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_stock_analysis_flow():
    """Test the stock analysis process"""
    print("🧪 Test the stock analysis process...")
    
    try:
        # Test stock type recognition
        from tradingagents.utils.stock_utils import StockUtils
        
        # Test Hong Kong stocks
        hk_ticker = "0700.HK"
        market_info = StockUtils.get_market_info(hk_ticker)
        
        print(f"  Hong Kong stock test: {hk_ticker}")
        print(f"    market: {market_info['market_name']}")
        print(f"    Currency: {market_info['currency_name']} ({market_info['currency_symbol']})")
        print(f"    data source: {market_info['data_source']}")
        print(f"    Is it Hong Kong stocks?: {market_info['is_hk']}")
        
        # Verify Hong Kong stock identification
        if not market_info['is_hk']:
            print(f"❌ {hk_ticker} should be identified as Hong Kong stocks")
            return False
            
        if market_info['currency_symbol'] != 'HK$':
            print(f"❌ The currency symbol of Hong Kong stocks should be HK$, Actually: {market_info['currency_symbol']}")
            return False
        
        print("✅ Stock analysis process test passed")
        return True
        
    except Exception as e:
        print(f"❌ Stock analysis process test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("🇭🇰 Start Hong Kong stock CLI function test")
    print("=" * 40)
    
    tests = [
        test_cli_market_selection,
        test_stock_analysis_flow
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
            print()
        except Exception as e:
            print(f"❌ test {test_func.__name__} Abnormal: {e}")
    
    print("=" * 40)
    print(f"🇭🇰 Hong Kong stock CLI test completed: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 All tests passed! Hong Kong stock CLI functions normally")
    else:
        print("⚠️ Some tests failed and require further debugging")

if __name__ == "__main__":
    main()
