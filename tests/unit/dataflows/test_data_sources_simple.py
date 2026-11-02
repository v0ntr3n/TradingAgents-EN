#!/usr/bin/env python3
"""
Simplified version of data source testing program
Quickly test the availability of primary data sources
"""

import sys
import os
import time
from datetime import datetime

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def test_china_data_source():
    """Test China Stock Data Source"""
    print("🇨🇳 Test China Stock Data Source")
    print("-" * 40)
    
    try:
        # Test data source manager
        from tradingagents.dataflows.data_source_manager import DataSourceManager
        
        manager = DataSourceManager()
        print(f"✅ Data source manager initialized successfully")
        print(f"   Current data source: {manager.current_source.value}")
        print(f"   Available data sources: {[s.value for s in manager.available_sources]}")
        
        # Test to get data
        print(f"\n📊 Test to obtain Ping An Bank(000001)data...")
        start_time = time.time()
        result = manager.get_stock_data("000001", "2025-07-01", "2025-07-12")
        end_time = time.time()
        
        if result and "❌" not in result:
            print(f"✅ Data acquisition successful ({end_time - start_time:.2f}s)")
            print(f"   Data length: {len(result)} character")
            print(f"   Data preview: {result[:100]}...")
            return True
        else:
            print(f"❌ Data acquisition failed: {result[:100]}...")
            return False
            
    except Exception as e:
        print(f"❌ China stock data source test failed: {e}")
        return False

def test_us_data_source():
    """Test US stock data source"""
    print("\n🇺🇸 Test US stock data source")
    print("-" * 40)
    
    try:
        # Test optimized version
        from tradingagents.dataflows.optimized_us_data import get_us_stock_data_cached
        
        print(f"📊 Test to get apples(AAPL)data...")
        start_time = time.time()
        result = get_us_stock_data_cached("AAPL", "2025-07-01", "2025-07-12", force_refresh=True)
        end_time = time.time()
        
        if result and "❌" not in result:
            print(f"✅ Data acquisition successful ({end_time - start_time:.2f}s)")
            print(f"   Data length: {len(result)} character")
            
            # Check data source
            if "FINNHUB" in result.upper() or "finnhub" in result:
                print(f"   🎯 Used FinnHub data source")
            elif "Yahoo Finance" in result or "yfinance" in result:
                print(f"   ⚠️ Used Yahoo Finance alternative data source")
            
            print(f"   Data preview: {result[:100]}...")
            return True
        else:
            print(f"❌ Data acquisition failed: {result[:100]}...")
            return False
            
    except Exception as e:
        print(f"❌ US stock data source test failed: {e}")
        return False

def test_cache_system():
    """Test caching system"""
    print("\n🗄️ Test caching system")
    print("-" * 40)
    
    try:
        from tradingagents.dataflows.cache_manager import get_cache
        
        cache = get_cache()
        print(f"✅ Cache manager initialization successful")
        print(f"   cache type: {type(cache).__name__}")
        
        # Test caching operations
        test_data = f"test data_{datetime.now().strftime('%H%M%S')}"
        
        # Save test data
        cache_key = cache.save_stock_data(
            symbol="TEST001",
            data=test_data,
            start_date="2025-07-01",
            end_date="2025-07-12",
            data_source="test"
        )
        
        # Load test data
        loaded_data = cache.load_stock_data(cache_key)
        
        if loaded_data == test_data:
            print(f"✅ Cache read and write test successful")
            print(f"   cache key: {cache_key}")
            return True
        else:
            print(f"❌ Cache data does not match")
            return False
            
    except Exception as e:
        print(f"❌ Cache system test failed: {e}")
        return False

def test_api_keys():
    """Test API key configuration"""
    print("\n🔑 Test API key configuration")
    print("-" * 40)
    
    api_keys = {
        'TUSHARE_TOKEN': os.getenv('TUSHARE_TOKEN'),
        'FINNHUB_API_KEY': os.getenv('FINNHUB_API_KEY'),
        'DASHSCOPE_API_KEY': os.getenv('DASHSCOPE_API_KEY'),
        'DEEPSEEK_API_KEY': os.getenv('DEEPSEEK_API_KEY'),
    }
    
    configured_count = 0
    total_count = len(api_keys)
    
    for key_name, key_value in api_keys.items():
        if key_value:
            print(f"✅ {key_name}: configured")
            configured_count += 1
        else:
            print(f"❌ {key_name}: Not configured")
    
    print(f"\n📊 API Key configuration rate: {configured_count}/{total_count} ({configured_count/total_count*100:.1f}%)")
    
    return configured_count >= 2  # At least 2 API keys are required

def main():
    """Main test function"""
    print("🧪 Data sources simplify testing procedures")
    print("=" * 50)
    print(f"Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    
    # 1. Test API key configuration
    api_result = test_api_keys()
    results.append(('API Key configuration', api_result))
    
    # 2. Test caching system
    cache_result = test_cache_system()
    results.append(('caching system', cache_result))
    
    # 3. Test China Stock Data Source
    china_result = test_china_data_source()
    results.append(('China stock data source', china_result))
    
    # 4. Test US stock data source
    us_result = test_us_data_source()
    results.append(('US stock data source', us_result))
    
    # Statistical results
    passed = sum(1 for _, result in results if result)
    total = len(results)
    success_rate = (passed / total * 100) if total > 0 else 0
    
    print(f"\n📊 Summary of test results")
    print("=" * 50)
    
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name}: {status}")
    
    print(f"\n📈 Overall results:")
    print(f"   Pass: {passed}/{total}")
    print(f"   success rate: {success_rate:.1f}%")
    
    if success_rate >= 75:
        print(f"\n🎉 The data source system is working great!")
        print(f"✅ Main functions are normal")
        print(f"✅ You can start using the system")
    else:
        print(f"\n⚠️ Data source system needs to be optimized")
        print(f"❌ Please check the failed component")
        print(f"❌ Refer to the error message for repairs")
    
    print(f"\n💡 Suggestions:")
    if not api_result:
        print("- Configure more API keys to increase data source availability")
    if not cache_result:
        print("- Check cache system configuration and permissions")
    if not china_result:
        print("- Check Tushare Token or AKShare installation")
    if not us_result:
        print("- Check FinnHub API Key or network connection")
    
    return success_rate >= 75

if __name__ == "__main__":
    try:
        success = main()
        
        print(f"\n{'='*50}")
        if success:
            print("🎯 Test completed! The complete analysis process can be run.")
            print("   Next step: python -m cli.main")
        else:
            print("🔧 Need to fix the configuration and test again.")
            print("   Retest: python tests/test_data_sources_simple.py")
            
    except Exception as e:
        print(f"❌ Test program exception: {e}")
        import traceback
        traceback.print_exc()
