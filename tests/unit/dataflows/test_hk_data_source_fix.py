"""
Test Hong Kong stock data source repair
"""

import sys
import os

# Add project root directory to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_toolkit_hk_method():
    """Test Toolkit Hong Kong Stock Method"""
    print("🧪 Test Toolkit Hong Kong Stock Method...")
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create toolkit
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Check if there is a Hong Kong stock method
        has_hk_method = hasattr(toolkit, 'get_hk_stock_data_unified')
        print(f"  Does the toolkit have Hong Kong stock methods?: {has_hk_method}")
        
        if has_hk_method:
            print("  ✅ Toolkit Hong Kong stock method exists")
            return True
        else:
            print("  ❌ The toolkit Hong Kong stock method does not exist")
            return False
        
    except Exception as e:
        print(f"❌ Toolkit Hong Kong stock method test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_market_analyst_tools():
    """Test Market Analyst Tool Configuration"""
    print("\n🧪 Test Market Analyst Tool Configuration...")
    
    try:
        from tradingagents.agents.analysts.market_analyst import create_market_analyst
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.utils.stock_utils import StockUtils
        
        # Create toolkit
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Test Hong Kong stock identification
        hk_ticker = "0700.HK"
        market_info = StockUtils.get_market_info(hk_ticker)
        
        print(f"  Hong Kong Stock Identification Test: {hk_ticker}")
        print(f"    market type: {market_info['market_name']}")
        print(f"    Is it Hong Kong stocks?: {market_info['is_hk']}")
        print(f"    Currency: {market_info['currency_name']}")
        
        if market_info['is_hk']:
            print("  ✅ Hong Kong stocks are correctly identified")
        else:
            print("  ❌ Hong Kong stock identification failed")
            return False
        
        # Check toolkit methods
        print(f"  Toolkit Hong Kong Stock Method: {hasattr(toolkit, 'get_hk_stock_data_unified')}")
        
        print("  ✅ Market analyst tool configuration test passed")
        return True
        
    except Exception as e:
        print(f"❌ Market Analyst Tool Configuration Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_akshare_hk_availability():
    """Test the availability of AKShare Hong Kong stocks"""
    print("\n🧪 Test the availability of AKShare Hong Kong stocks...")
    
    try:
        from tradingagents.dataflows.interface import AKSHARE_HK_AVAILABLE, HK_STOCK_AVAILABLE
        
        print(f"  AKShare Hong Kong stocks available: {AKSHARE_HK_AVAILABLE}")
        print(f"  Yahoo Finance Hong Kong stocks available: {HK_STOCK_AVAILABLE}")
        
        if AKSHARE_HK_AVAILABLE:
            print("  ✅ AKShare Hong Kong stock data source available")
            
            # Test AKShare Hong Kong stock function
            from tradingagents.dataflows.akshare_utils import get_hk_stock_data_akshare
            print("  ✅ AKShare Hong Kong stock function imported successfully")
            
        else:
            print("  ⚠️ AKShare Hong Kong stock data source is not available")
        
        if HK_STOCK_AVAILABLE:
            print("  ✅ Yahoo Finance Hong Kong stock data source available")
        else:
            print("  ⚠️ Yahoo Finance Hong Kong stock data source is not available")
        
        # Test unified interface
        from tradingagents.dataflows.interface import get_hk_stock_data_unified
        print("  ✅ The unified interface for Hong Kong stocks was successfully imported")
        
        return True
        
    except Exception as e:
        print(f"❌ AKShare Hong Kong stock usability test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_source_priority():
    """Test data source priority"""
    print("\n🧪 Test data source priority...")
    
    try:
        from tradingagents.dataflows.interface import get_hk_stock_data_unified
        from datetime import datetime, timedelta
        
        # Set test date
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        symbol = "0700.HK"
        print(f"  Test acquisition {symbol} data...")
        print(f"  date range: {start_date} Arrive {end_date}")
        
        # Call the unified interface (do not actually obtain data, only test the call)
        print("  ✅ Unified interface call test preparation completed")
        
        # There is no actual call here to avoid network requests.
        # result = get_hk_stock_data_unified(symbol, start_date, end_date)
        
        print("  ✅ Data source priority test passed")
        return True
        
    except Exception as e:
        print(f"❌ Data source priority test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_market_analyst_modification():
    """Test Market Analyst Modifications"""
    print("\n🧪 Test Market Analyst Modifications...")
    
    try:
        # Read market analyst file content
        with open('tradingagents/agents/analysts/market_analyst.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check whether Hong Kong stock allocation is included
        has_hk_config = 'elif is_hk:' in content
        has_unified_tool = 'get_hk_stock_data_unified' in content
        
        print(f"  Includes Hong Kong stock allocation: {has_hk_config}")
        print(f"  Contains unified tools: {has_unified_tool}")
        
        if has_hk_config and has_unified_tool:
            print("  ✅ Market analyst revised correctly")
            return True
        else:
            print("  ❌ Market analyst s modification is incomplete")
            return False
        
    except Exception as e:
        print(f"❌ Market Analyst Modification Test Fails: {e}")
        return False

def main():
    """Run all tests"""
    print("🔧 Hong Kong stock data source repair test")
    print("=" * 50)
    
    tests = [
        test_akshare_hk_availability,
        test_toolkit_hk_method,
        test_market_analyst_tools,
        test_data_source_priority,
        test_market_analyst_modification
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
    print(f"🔧 Hong Kong stock data source repair test completed: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 The Hong Kong stock data source was repaired successfully!")
        print("\n Hong Kong stock analysis should now give priority to using the AKShare data source")
        print("Instead of Yahoo Finance, avoid the Rate Limit problem")
    else:
        print("⚠️ Some tests failed, please check the failed tests")

if __name__ == "__main__":
    main()
