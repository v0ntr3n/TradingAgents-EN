"""
Test import fix
"""

import sys
import os

# Add project root directory to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_fundamentals_analyst_import():
    """Test fundamental analyst import"""
    print("🧪 Test fundamental analyst import...")
    
    try:
        # Test import fundamental analysts
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        print("  ✅ Fundamental analysts were imported successfully")
        
        # Test is_china_stock function import
        from tradingagents.utils.stock_utils import is_china_stock
        print("  ✅ is_china_stock Function imported successfully")
        
        # Test function call
        result = is_china_stock("000001")
        print(f"  ✅ is_china_stock('000001') = {result}")
        
        result = is_china_stock("0700.HK")
        print(f"  ✅ is_china_stock('0700.HK') = {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ Fundamental analyst import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_stock_utils_functions():
    """Testing stock instrument functions"""
    print("\n🧪 Testing stock instrument functions...")
    
    try:
        from tradingagents.utils.stock_utils import (
            is_china_stock, 
            is_hk_stock, 
            is_us_stock,
            StockUtils
        )
        
        # Test various stock symbols
        test_cases = [
            ("000001", "A shares", True, False, False),
            ("600036", "A shares", True, False, False),
            ("0700.HK", "Hong Kong stocks", False, True, False),
            ("9988.HK", "Hong Kong stocks", False, True, False),
            ("AAPL", "US stocks", False, False, True),
            ("TSLA", "US stocks", False, False, True),
        ]
        
        for ticker, market, expect_china, expect_hk, expect_us in test_cases:
            china_result = is_china_stock(ticker)
            hk_result = is_hk_stock(ticker)
            us_result = is_us_stock(ticker)
            
            print(f"  {ticker} ({market}):")
            print(f"    China A shares: {china_result} {'✅' if china_result == expect_china else '❌'}")
            print(f"    Hong Kong stocks: {hk_result} {'✅' if hk_result == expect_hk else '❌'}")
            print(f"    US stocks: {us_result} {'✅' if us_result == expect_us else '❌'}")
            
            if (china_result != expect_china or 
                hk_result != expect_hk or 
                us_result != expect_us):
                print(f"❌ {ticker} The recognition result is incorrect")
                return False
        
        print("  ✅ All stock instrument function tests passed")
        return True
        
    except Exception as e:
        print(f"❌ Stock instrument function test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_web_analysis_runner():
    """Test the web analytics runner"""
    print("\n🧪 Test the web analytics runner...")
    
    try:
        from web.utils.analysis_runner import validate_analysis_params
        
        # Test Hong Kong stock verification
        is_valid, errors = validate_analysis_params(
            stock_symbol="0700.HK",
            analysis_date="2025-07-14",
            analysts=["market", "fundamentals"],
            research_depth=3,
            market_type="Hong Kong stocks"
        )
        
        print(f"  Hong Kong stock verification results: {'Pass' if is_valid else 'failed'}")
        if not is_valid:
            print(f"  error message: {errors}")
            return False
        
        print("  ✅ Web Analysis runner test passes")
        return True
        
    except Exception as e:
        print(f"❌ Web Analysis runner test fails: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_complete_analysis_flow():
    """Test the complete analysis process (without actually running it)"""
    print("\n🧪 Test the complete analysis process import...")
    
    try:
        # Test all necessary imports
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        
        print("  ✅ Transaction graph imported successfully")
        print("  ✅ Default configuration imported successfully")
        print("  ✅ Fundamental analysts were imported successfully")
        
        # Test configuration creation
        config = DEFAULT_CONFIG.copy()
        print("  ✅ Configuration created successfully")
        
        print("  ✅ The complete analysis process import test passed")
        return True
        
    except Exception as e:
        print(f"❌ Complete analysis process import test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all import tests"""
    print("🔧 Import repair test")
    print("=" * 40)
    
    tests = [
        test_fundamentals_analyst_import,
        test_stock_utils_functions,
        test_web_analysis_runner,
        test_complete_analysis_flow
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ test {test_func.__name__} Abnormal: {e}")
    
    print("\n" + "=" * 40)
    print(f"🔧 Import repair test completed: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 All import tests passed!")
        print("\n Now you can perform normal Hong Kong stock analysis")
        print("It is recommended to restart the web application and test the 0700.HK analysis")
    else:
        print("⚠️ Some import tests failed, please check the failed tests")

if __name__ == "__main__":
    main()
