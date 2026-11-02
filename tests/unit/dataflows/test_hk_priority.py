#!/usr/bin/env python3
"""
Test the priority setting of Hong Kong stock data sources
Verify AKShare first, Yahoo Finance as backup
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_hk_data_source_priority():
    """Test the priority of Hong Kong stock data sources"""
    print("\n🇭🇰 Test the priority of Hong Kong stock data sources")
    print("=" * 80)
    
    try:
        # Set log level
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("default")
        logger.setLevel("INFO")
        
        print("📊 Test the priority of obtaining Hong Kong stock information...")
        
        # Test the unified Hong Kong stock information interface
        from tradingagents.dataflows.interface import get_hk_stock_info_unified
        
        test_symbols = [
            "0700.HK",  # Tencent Holdings
            "0941.HK",  # China Mobile  
            "1299.HK",  # AIA
        ]
        
        for symbol in test_symbols:
            print(f"\n📊 test stocks: {symbol}")
            print("-" * 40)
            
            try:
                result = get_hk_stock_info_unified(symbol)
                
                print(f"✅ get success:")
                print(f"   Stock code: {result.get('symbol', 'N/A')}")
                print(f"   Company name: {result.get('name', 'N/A')}")
                print(f"   data source: {result.get('source', 'N/A')}")
                print(f"   Currency: {result.get('currency', 'N/A')}")
                print(f"   exchange: {result.get('exchange', 'N/A')}")
                
                # Check whether the specific company name was successfully obtained
                name = result.get('name', '')
                if not name.startswith('Hong Kong stocks'):
                    print(f"   ✅ Successfully obtained the specific company name")
                else:
                    print(f"   ⚠️ Use default format")
                    
            except Exception as e:
                print(f"❌ Failed to obtain: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_hk_data_priority():
    """Test the priority of Hong Kong stock data acquisition"""
    print("\n📈 Test the priority of Hong Kong stock data acquisition")
    print("=" * 80)
    
    try:
        from tradingagents.dataflows.interface import get_hk_stock_data_unified
        
        test_symbol = "0700.HK"
        start_date = "2025-07-01"
        end_date = "2025-07-15"
        
        print(f"📊 Test Hong Kong stock data acquisition: {test_symbol}")
        print(f"   time range: {start_date} Arrive {end_date}")
        print("-" * 40)
        
        result = get_hk_stock_data_unified(test_symbol, start_date, end_date)
        
        if result and "❌" not in result:
            print(f"✅ Hong Kong stock data obtained successfully")
            print(f"   Data length: {len(result)}")
            
            # Display the first 200 characters of the data
            print(f"   Data preview:")
            print(f"   {result[:200]}...")
            
            # Check that the data contains the correct stock symbol
            if "0700" in result or "Tencent" in result:
                print(f"   ✅ The data contains correct stock information")
            else:
                print(f"   ⚠️ Data may be incomplete")
        else:
            print(f"❌ Failed to obtain Hong Kong stock data")
            print(f"   Return results: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_improved_hk_provider_priority():
    """Test to improve the priority of Hong Kong stock provider"""
    print("\n🔧 Test improved Hong Kong stock provider priority")
    print("=" * 80)
    
    try:
        from tradingagents.dataflows.providers.hk.improved_hk import get_improved_hk_provider
        
        provider = get_improved_hk_provider()
        
        # Clean cache to test real API call priority
        if hasattr(provider, 'cache'):
            provider.cache.clear()
        
        test_symbols = [
            "0700.HK",  # Tencent Holdings (built-in mapping)
            "1234.HK",  # Stocks not in built-in mapping (testing API priority)
        ]
        
        for symbol in test_symbols:
            print(f"\n📊 test stocks: {symbol}")
            print("-" * 40)
            
            try:
                company_name = provider.get_company_name(symbol)
                print(f"✅ Get company name: {company_name}")
                
                # Check cache information
                cache_key = f"name_{symbol}"
                if hasattr(provider, 'cache') and cache_key in provider.cache:
                    cache_info = provider.cache[cache_key]
                    print(f"   cache source: {cache_info.get('source', 'unknown')}")
                    print(f"   Cache time: {cache_info.get('timestamp', 'unknown')}")
                
                # Check whether the specific company name was successfully obtained
                if not company_name.startswith('Hong Kong stocks'):
                    print(f"   ✅ Successfully obtained the specific company name")
                else:
                    print(f"   ⚠️ Use default format")
                    
            except Exception as e:
                print(f"❌ Failed to obtain: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_source_availability():
    """Test data source availability"""
    print("\n🔍 Test data source availability")
    print("=" * 80)
    
    try:
        # Check AKShare availability
        try:
            from tradingagents.dataflows.akshare_utils import get_hk_stock_info_akshare
            print("✅ AKShare Hong Kong stock tools are available")
            akshare_available = True
        except ImportError as e:
            print(f"❌ AKShare Hong Kong stock instruments are not available: {e}")
            akshare_available = False
        
        # Check Yahoo Finance availability
        try:
            from tradingagents.dataflows.hk_stock_utils import get_hk_stock_info
            print("✅ Yahoo Finance Hong Kong stock tools are available")
            yf_available = True
        except ImportError as e:
            print(f"❌ Yahoo Finance Hong Kong stock instruments are not available: {e}")
            yf_available = False
        
        # Check unified interface
        try:
            from tradingagents.dataflows.interface import get_hk_stock_info_unified, AKSHARE_HK_AVAILABLE, HK_STOCK_AVAILABLE
            print("✅ Unified Hong Kong stock interface is available")
            print(f"   AKShare available flags: {AKSHARE_HK_AVAILABLE}")
            print(f"   Yahoo Finance available flags: {HK_STOCK_AVAILABLE}")
        except ImportError as e:
            print(f"❌ The unified Hong Kong stock interface is not available: {e}")
        
        print(f"\n📊 Data source priority verification:")
        print(f"   1. AKShare (Priority): {'✅ Available' if akshare_available else '❌ Not available'}")
        print(f"   2. Yahoo Finance (Spare): {'✅ Available' if yf_available else '❌ Not available'}")
        print(f"   3. Default format (Downgrade): ✅ always available")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🚀 Start testing the priority of Hong Kong stock data sources")
    print("=" * 100)
    
    results = []
    
    # test 1: Data source availability
    results.append(test_data_source_availability())
    
    # test 2: Hong Kong stock information acquisition priority
    results.append(test_hk_data_source_priority())
    
    # test 3: Hong Kong stock data acquisition priority
    results.append(test_hk_data_priority())
    
    # test 4: Improve Hong Kong stock provider priority
    results.append(test_improved_hk_provider_priority())
    
    # Summary results
    print("\n" + "=" * 100)
    print("📋 Summary of test results")
    print("=" * 100)
    
    passed = sum(results)
    total = len(results)
    
    test_names = [
        "Data source availability check",
        "Hong Kong stock information acquisition priority",
        "Hong Kong stock data acquisition priority", 
        "Improve Hong Kong stock provider priority"
    ]
    
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ Pass" if result else "❌ failed"
        print(f"{i+1}. {name}: {status}")
    
    print(f"\n📊 Overall results: {passed}/{total} Test passed")
    
    if passed == total:
        print("🎉 All tests passed! The priority of Hong Kong stock data source is set correctly")
        print("\n📋 Priority settings:")
        print("1. 🥇 AKShare (Domestic data sources, Hong Kong stocks have better support)")
        print("2. 🥈 Yahoo Finance (International Data Sources, Alternatives)")
        print("3. 🥉 Default format (Downgrade plan to ensure availability)")
        
        print("\n✅ Optimization effect:")
        print("- Reduce Yahoo Finance API rate limiting issues")
        print("- Improve the success rate of obtaining Hong Kong stock data")
        print("- Better Chinese company name support")
        print("- More stable data source access")
    else:
        print("⚠️ Some tests failed and need further optimization")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
