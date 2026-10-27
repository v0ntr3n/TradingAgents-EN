#!/usr/bin/env python3
"""
Cache optimization function test
Test the caching strategy and performance of US stock and A-share data
"""

import os
import sys
import time
from datetime import datetime, timedelta

# Add project root directory to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

def test_cache_manager():
    """Test the basic functionality of the cache manager"""
    print("🧪 Test cache manager...")
    
    try:
        from tradingagents.dataflows.cache_manager import get_cache
        
        cache = get_cache()
        print(f"✅ Cache manager initialization successful")
        print(f"📁 cache directory: {cache.cache_dir}")
        
        # Test cache configuration
        if hasattr(cache, 'cache_config'):
            print(f"⚙️ Cache configuration:")
            for config_name, config_data in cache.cache_config.items():
                print(f"  - {config_name}: TTL={config_data.get('ttl_hours')}h, Description={config_data.get('description')}")
        
        # Test cache statistics
        stats = cache.get_cache_stats()
        print(f"📊 cache statistics: {stats}")
        
        return True
        
    except Exception as e:
        print(f"❌ Cache manager test failed: {e}")
        return False


def test_us_stock_cache():
    """Test US stock data cache"""
    print("\n🇺🇸 Test US stock data cache...")
    
    try:
        from tradingagents.dataflows.optimized_us_data import get_optimized_us_data_provider
        
        provider = get_optimized_us_data_provider()
        symbol = "AAPL"
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        print(f"📈 test stocks: {symbol} ({start_date} Arrive {end_date})")
        
        # First call (should be obtained from API)
        print("🌐 First call (obtained from API)...")
        start_time = time.time()
        result1 = provider.get_stock_data(symbol, start_date, end_date)
        time1 = time.time() - start_time
        print(f"⏱️ The first call takes time: {time1:.2f}seconds")
        
        # Second call (should get it from cache)
        print("⚡ Second call (get from cache)...")
        start_time = time.time()
        result2 = provider.get_stock_data(symbol, start_date, end_date)
        time2 = time.time() - start_time
        print(f"⏱️ The second call takes time: {time2:.2f}seconds")
        
        # Verify result consistency
        if result1 == result2:
            print("✅ Cache data consistency verification passed")
        else:
            print("⚠️ Cache data is inconsistent")
        
        # Performance improvements
        if time2 < time1:
            improvement = ((time1 - time2) / time1) * 100
            print(f"🚀 Cache performance improvements: {improvement:.1f}%")
        
        return True
        
    except Exception as e:
        print(f"❌ US stock cache test failed: {e}")
        return False


def test_china_stock_cache():
    """Test A-share data cache"""
    print("\n🇨🇳 Test A-share data cache...")
    
    try:
        from tradingagents.dataflows.optimized_china_data import get_optimized_china_data_provider
        
        provider = get_optimized_china_data_provider()
        symbol = "000001"
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        print(f"📈 test stocks: {symbol} ({start_date} Arrive {end_date})")
        
        # First call (should be obtained from API)
        print("🌐 First call (obtained from Tushare data interface)...")
        start_time = time.time()
        result1 = provider.get_stock_data(symbol, start_date, end_date)
        time1 = time.time() - start_time
        print(f"⏱️ The first call takes time: {time1:.2f}seconds")
        
        # Second call (should get it from cache)
        print("⚡ Second call (get from cache)...")
        start_time = time.time()
        result2 = provider.get_stock_data(symbol, start_date, end_date)
        time2 = time.time() - start_time
        print(f"⏱️ The second call takes time: {time2:.2f}seconds")
        
        # Verify result consistency
        if result1 == result2:
            print("✅ Cache data consistency verification passed")
        else:
            print("⚠️ Cache data is inconsistent")
        
        # Performance improvements
        if time2 < time1:
            improvement = ((time1 - time2) / time1) * 100
            print(f"🚀 Cache performance improvements: {improvement:.1f}%")
        
        # Test fundamental data cache
        print("\n📊 Test A-share fundamental data cache...")
        start_time = time.time()
        fundamentals1 = provider.get_fundamentals_data(symbol)
        time1 = time.time() - start_time
        print(f"⏱️ The first call of fundamental data takes time: {time1:.2f}seconds")
        
        start_time = time.time()
        fundamentals2 = provider.get_fundamentals_data(symbol)
        time2 = time.time() - start_time
        print(f"⏱️ The second call of fundamental data takes time: {time2:.2f}seconds")
        
        if fundamentals1 == fundamentals2:
            print("✅ Fundamental data cache consistency verification passed")
        
        return True
        
    except Exception as e:
        print(f"❌ A Share cache test failed: {e}")
        return False


def test_cache_ttl():
    """Test cache TTL functionality"""
    print("\n⏰ Test cache TTL functionality...")
    
    try:
        from tradingagents.dataflows.cache_manager import get_cache
        
        cache = get_cache()
        
        # Test US stock cache TTL
        us_cache_key = cache.find_cached_stock_data(
            symbol="AAPL",
            start_date=(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
            end_date=datetime.now().strftime('%Y-%m-%d'),
            data_source="yfinance"
        )
        
        if us_cache_key:
            is_valid = cache.is_cache_valid(us_cache_key, symbol="AAPL", data_type="stock_data")
            print(f"📈 U.S. stock cache effectiveness: {'✅ valid' if is_valid else '❌ Expired'}")
        
        # Test A-share cache TTL
        china_cache_key = cache.find_cached_stock_data(
            symbol="000001",
            start_date=(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
            end_date=datetime.now().strftime('%Y-%m-%d'),
            data_source="tdx"
        )
        
        if china_cache_key:
            is_valid = cache.is_cache_valid(china_cache_key, symbol="000001", data_type="stock_data")
            print(f"📈 A Share cache validity: {'✅ valid' if is_valid else '❌ Expired'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Cache TTL test failed: {e}")
        return False


def test_cache_cleanup():
    """Test cache cleaning functionality"""
    print("\n🧹 Test cache cleaning functionality...")
    
    try:
        from tradingagents.dataflows.cache_manager import get_cache
        
        cache = get_cache()
        
        # Get statistics before cleaning
        stats_before = cache.get_cache_stats()
        print(f"📊 Statistics before cleaning: {stats_before}")
        
        # Perform a cleanup (clean cache from 7 days ago)
        print("🧹 Perform cache cleaning...")
        cache.clear_old_cache(max_age_days=7)
        
        # Get cleaned statistics
        stats_after = cache.get_cache_stats()
        print(f"📊 Statistics after cleaning: {stats_after}")
        
        # Calculate cleaning effect
        files_removed = stats_before['total_files'] - stats_after['total_files']
        size_freed = stats_before['total_size_mb'] - stats_after['total_size_mb']
        
        print(f"🗑️ Clean results: Delete {files_removed} files, release {size_freed:.2f} MB space")
        
        return True
        
    except Exception as e:
        print(f"❌ Cache cleaning test failed: {e}")
        return False


def main():
    """Main test function"""
    print("🚀 Start cache optimization function test")
    print("=" * 50)
    
    test_results = []
    
    # Test cache manager
    test_results.append(("cache manager", test_cache_manager()))
    
    # Test US stock cache
    test_results.append(("US stock data cache", test_us_stock_cache()))
    
    # Test A-share cache
    test_results.append(("A Stock data cache", test_china_stock_cache()))
    
    # test cache TTL
    test_results.append(("cache TTL", test_cache_ttl()))
    
    # Test cache cleanup
    test_results.append(("Cache cleaning", test_cache_cleanup()))
    
    # Output test results
    print("\n" + "=" * 50)
    print("📋 Summary of test results:")
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall results: {passed}/{total} Test passed")
    
    if passed == total:
        print("🎉 All cache optimization function tests passed!")
    else:
        print("⚠️ Some tests failed, please check the system configuration")


if __name__ == "__main__":
    main()
