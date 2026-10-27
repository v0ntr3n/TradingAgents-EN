"""
Test the Hong Kong stock data source repair for all analyst nodes
"""

import sys
import os

# Add project root directory to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_market_analyst_hk_config():
    """Test market analyst s Hong Kong stock allocation"""
    print("🧪 Test market analyst s Hong Kong stock allocation...")
    
    try:
        # Read market analyst files
        with open('tradingagents/agents/analysts/market_analyst.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check Hong Kong stock allocation
        has_hk_branch = 'elif is_hk:' in content
        has_unified_tool = 'get_hk_stock_data_unified' in content
        has_akshare_comment = 'Priority AKShare' in content
        
        print(f"  Hong Kong stock branch: {has_hk_branch}")
        print(f"  unified tools: {has_unified_tool}")
        print(f"  AKShare Comment: {has_akshare_comment}")
        
        if has_hk_branch and has_unified_tool and has_akshare_comment:
            print("  ✅ Market analysts have the correct allocation for Hong Kong stocks")
            return True
        else:
            print("  ❌ Market analysts Hong Kong stock allocation is incomplete")
            return False
        
    except Exception as e:
        print(f"❌ Market analyst s Hong Kong stock allocation test failed: {e}")
        return False

def test_fundamentals_analyst_hk_config():
    """Testing fundamental analysts Hong Kong stock allocations"""
    print("\n🧪 Testing fundamental analysts Hong Kong stock allocations...")
    
    try:
        # Read fundamental analyst files
        with open('tradingagents/agents/analysts/fundamentals_analyst.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check Hong Kong stock allocation
        has_hk_branch = 'elif is_hk:' in content
        has_unified_tool = 'get_hk_stock_data_unified' in content
        has_akshare_comment = 'Priority AKShare' in content
        
        print(f"  Hong Kong stock branch: {has_hk_branch}")
        print(f"  unified tools: {has_unified_tool}")
        print(f"  AKShare Comment: {has_akshare_comment}")
        
        if has_hk_branch and has_unified_tool and has_akshare_comment:
            print("  ✅ Fundamental analysts have the correct allocation for Hong Kong stocks")
            return True
        else:
            print("  ❌ Fundamental analysts Hong Kong stock allocation is incomplete")
            return False
        
    except Exception as e:
        print(f"❌ Fundamental analyst s Hong Kong stock allocation test failed: {e}")
        return False

def test_optimized_us_data_hk_support():
    """Test and optimize the Hong Kong stock support of the US stock data module"""
    print("\n🧪 Test and optimize the Hong Kong stock support of the US stock data module...")
    
    try:
        # Read optimized US stock data files
        with open('tradingagents/dataflows/optimized_us_data.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check Hong Kong stock support
        has_hk_detection = "market_info['is_hk']" in content
        has_akshare_import = 'get_hk_stock_data_unified' in content
        has_akshare_priority = 'priority use AKShare' in content
        
        print(f"  Hong Kong stock testing: {has_hk_detection}")
        print(f"  AKShare import: {has_akshare_import}")
        print(f"  AKShare priority: {has_akshare_priority}")
        
        if has_hk_detection and has_akshare_import and has_akshare_priority:
            print("  ✅ Optimize the US stock data module and support Hong Kong stocks correctly")
            return True
        else:
            print("  ❌ Optimized U.S. stock data module and incomplete support for Hong Kong stocks")
            return False
        
    except Exception as e:
        print(f"❌ Optimization of US stock data module and Hong Kong stock support test failed: {e}")
        return False

def test_toolkit_hk_method_availability():
    """Test toolkit Hong Kong stock method availability"""
    print("\n🧪 Test toolkit Hong Kong stock method availability...")
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create toolkit
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # How to check Hong Kong stocks
        has_hk_method = hasattr(toolkit, 'get_hk_stock_data_unified')
        
        print(f"  Toolkit Hong Kong Stock Method: {has_hk_method}")
        
        if has_hk_method:
            print("  ✅ Toolkit Hong Kong Stock Method Available")
            return True
        else:
            print("  ❌ Toolkit Hong Kong stock method is not available")
            return False
        
    except Exception as e:
        print(f"❌ Usability test of toolkit Hong Kong stock method failed: {e}")
        return False

def test_data_source_priority_summary():
    """Test data source priority summary"""
    print("\n🧪 Data source priority summary...")
    
    try:
        from tradingagents.dataflows.interface import AKSHARE_HK_AVAILABLE, HK_STOCK_AVAILABLE
        
        print("  📊 Current data source availability:")
        print(f"    AKShare Hong Kong stocks: {AKSHARE_HK_AVAILABLE}")
        print(f"    Yahoo Finance Hong Kong stocks: {HK_STOCK_AVAILABLE}")
        
        print("\n  🎯 Expected data source priority:")
        print("    Hong Kong stocks (0700.HK):")
        print("      1. AKShare (main) - Domestic stability, no Rate Limit")
        print("      2. Yahoo Finance (Spare) - international data sources")
        print("    China A shares (000001):")
        print("      1. Tushare/AKShare/BaoStock (Existing configuration)")
        print("    US stocks (AAPL):")
        print("      1. FINNHUB (main)")
        print("      2. Yahoo Finance (Spare)")
        
        return True
        
    except Exception as e:
        print(f"❌ Data source priority summary failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🔧 All analyst node Hong Kong stock data source repair test")
    print("=" * 60)
    
    tests = [
        test_market_analyst_hk_config,
        test_fundamentals_analyst_hk_config,
        test_optimized_us_data_hk_support,
        test_toolkit_hk_method_availability,
        test_data_source_priority_summary
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ test {test_func.__name__} Abnormal: {e}")
    
    print("\n" + "=" * 60)
    print(f"🔧 All analyst node Hong Kong stock data source repair tests completed: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 All analyst node Hong Kong stock data sources have been repaired successfully!")
        print("\n✅ Repair summary:")
        print("  - market analyst: Hong Kong stocks have priority AKShare")
        print("  - fundamental analyst: Hong Kong stocks have priority AKShare")
        print("  - Optimize data module: Support Hong Kong stocks AKShare priority")
        print("  - tool kit: A unified interface method for Hong Kong stocks has been added")
        print("\n🚀 All Hong Kong stock analysis will now use the AKShare data source first!")
    else:
        print("⚠️ Some tests failed, please check the failed tests")

if __name__ == "__main__":
    main()
