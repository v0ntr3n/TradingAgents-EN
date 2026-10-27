#!/usr/bin/env python3
"""
Test fundamental data caching function
Verify the caching mechanism of OpenAI and Finnhub fundamental data
"""

import os
import sys
import time
from datetime import datetime

# Add project root directory to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

def test_cache_manager_fundamentals():
    """Testing the cache manager s fundamental data functionality"""
    print("🧪 Test Fundamentals Data Cache Manager...")
    
    try:
        from tradingagents.dataflows.cache_manager import get_cache
        
        cache = get_cache()
        print(f"✅ Cache manager initialization successful")
        print(f"📁 cache directory: {cache.cache_dir}")
        
        # Test saving fundamental data
        test_symbol = "AAPL"
        test_data = f"""
# {test_symbol} Fundamental analysis report (test data)

**Data acquisition time**: {datetime.now().strftime('%Y-%m-%d')}
**Data source**: test data

## Company Profile
- **Company name**: Apple Inc.
- **Industry**: Technology
- **Market value**: 3000000 million dollars

## key financial indicators
| indicator | numerical value |
|------|------|
| P/E ratio (PE) | 25.50 |
| price to sales ratio (PS) | 7.20 |
| ROE (ROE) | 15.30% |

## Data description
- This is test data to verify caching functionality
"""
        
        # Save test to cache
        print(f"\n💾 Test saving fundamental data to cache...")
        cache_key = cache.save_fundamentals_data(test_symbol, test_data, data_source="test")
        print(f"✅ Data saved, cache key: {cache_key}")
        
        # Test loading from cache
        print(f"\n📖 Test loading fundamental data from cache...")
        loaded_data = cache.load_fundamentals_data(cache_key)
        if loaded_data:
            print(f"✅ Data loaded successfully, length: {len(loaded_data)}")
            print(f"📄 Data preview: {loaded_data[:200]}...")
        else:
            print(f"❌ Data loading failed")
        
        # Test lookup cache
        print(f"\n🔍 Test to find fundamental cache data...")
        found_key = cache.find_cached_fundamentals_data(test_symbol, data_source="test")
        if found_key:
            print(f"✅ Find cache data, cache key: {found_key}")
        else:
            print(f"❌ Cache data not found")
        
        # Test cache statistics
        print(f"\n📊 Test cache statistics...")
        stats = cache.get_cache_stats()
        print(f"cache statistics: {stats}")
        
        return True
        
    except Exception as e:
        print(f"❌ Cache manager test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_fundamentals_with_cache():
    """Test the caching function of the fundamental data acquisition function"""
    print(f"\n🧪 Test the caching function of the fundamental data acquisition function...")
    
    try:
        from tradingagents.dataflows.interface import get_fundamentals_openai, get_fundamentals_finnhub
        
        test_symbol = "MSFT"
        curr_date = datetime.now().strftime('%Y-%m-%d')
        
        print(f"\n📊 Get it for the first time {test_symbol} Fundamental data (should be obtained from API)...")
        start_time = time.time()
        result1 = get_fundamentals_finnhub(test_symbol, curr_date)
        first_time = time.time() - start_time
        print(f"⏱️ First acquisition time: {first_time:.2f}seconds")
        print(f"📄 Data length: {len(result1)}")
        
        print(f"\n📊 second acquisition {test_symbol} Fundamental data (should be obtained from cache)...")
        start_time = time.time()
        result2 = get_fundamentals_finnhub(test_symbol, curr_date)
        second_time = time.time() - start_time
        print(f"⏱️ The second acquisition time: {second_time:.2f}seconds")
        print(f"📄 Data length: {len(result2)}")
        
        # Verify caching effect
        if second_time < first_time:
            print(f"✅ Caching takes effect! The second acquisition speed has been improved {((first_time - second_time) / first_time * 100):.1f}%")
        else:
            print(f"⚠️ The cache may not be effective, or the data source may have changed.")
        
        # Verify data consistency
        if result1 == result2:
            print(f"✅ The data obtained twice are exactly the same")
        else:
            print(f"⚠️ The data obtained twice is inconsistent, which may be a caching issue.")
        
        return True
        
    except Exception as e:
        print(f"❌ Fundamental data cache test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_cache_ttl():
    """Test cache TTL (time to live) functionality"""
    print(f"\n🧪 Test cache TTL functionality...")
    
    try:
        from tradingagents.dataflows.cache_manager import get_cache
        
        cache = get_cache()
        
        # Check cache configuration
        print(f"📋 Cache configuration:")
        for cache_type, config in cache.cache_config.items():
            if 'fundamentals' in cache_type:
                print(f"  - {cache_type}: TTL={config['ttl_hours']}hours, Description={config['description']}")
        
        # Test different TTL settings for US stocks and A-shares
        us_symbol = "GOOGL"
        china_symbol = "000001"  # Ping An Bank
        
        print(f"\n🇺🇸 Testing US Stock Fundamental Cache ({us_symbol})...")
        us_key = cache.find_cached_fundamentals_data(us_symbol, data_source="test")
        if us_key:
            print(f"Find US stock cache: {us_key}")
        else:
            print(f"US stock cache not found")
        
        print(f"\n🇨🇳 Test A-share fundamental cache ({china_symbol})...")
        china_key = cache.find_cached_fundamentals_data(china_symbol, data_source="test")
        if china_key:
            print(f"Find A-share cache: {china_key}")
        else:
            print(f"A-share cache not found")
        
        return True
        
    except Exception as e:
        print(f"❌ Cache TTL test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🚀 Start fundamental data caching function test")
    print("=" * 50)
    
    # Check environment
    print(f"📍 current working directory: {os.getcwd()}")
    print(f"📍 Python path: {sys.path[0]}")
    
    # Run tests
    tests = [
        ("Cache manager basic functions", test_cache_manager_fundamentals),
        ("Fundamental data caching function", test_fundamentals_with_cache),
        ("Cache TTL functionality", test_cache_ttl),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ test '{test_name}' Execution failed: {str(e)}")
            results.append((test_name, False))
    
    # Output test results
    print(f"\n{'='*20} Summary of test results {'='*20}")
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{status} {test_name}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    print(f"\n📊 Test completed: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Fundamental data caching functionality is working properly.")
    else:
        print("⚠️ Some tests failed, please check related functions.")

if __name__ == "__main__":
    main()