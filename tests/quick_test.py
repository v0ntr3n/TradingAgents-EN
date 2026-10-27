#!/usr/bin/env python3
"""
Quick integration test - verify copied files work properly
"""

import os
import sys
import traceback
from datetime import datetime

print("🚀 TradingAgents Integration testing")
print("=" * 40)

# Test 1: Check if the file exists
print("\n📁 Check copied files...")
files_to_check = [
    'tradingagents/dataflows/cache_manager.py',
    'tradingagents/dataflows/optimized_us_data.py',
    'tradingagents/dataflows/config.py'
]

for file_path in files_to_check:
    if os.path.exists(file_path):
        size = os.path.getsize(file_path)
        print(f"✅ {file_path} (size: {size:,} Bytes)")
    else:
        print(f"❌ {file_path} (File does not exist)")

# Test 2: Check Python syntax
print("\n🐍 Check Python syntax...")
for file_path in files_to_check:
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                compile(f.read(), file_path, 'exec')
            print(f"✅ {file_path} Grammatically correct")
        except SyntaxError as e:
            print(f"❌ {file_path} syntax error: {e}")
        except Exception as e:
            print(f"⚠️ {file_path} Check failed: {e}")

# Test 3: Trying to import the module
print("\n📦 Test module import...")

# Test cache manager
try:
    from tradingagents.dataflows.cache_manager import get_cache, StockDataCache
    print("✅ cache_manager Import successful")
    
    # Create cache instance
    cache = get_cache()
    print(f"✅ Cache instance created successfully: {type(cache).__name__}")
    
    # Check cache directory
    if hasattr(cache, 'cache_dir'):
        print(f"📁 cache directory: {cache.cache_dir}")
        if cache.cache_dir.exists():
            print("✅ Cache directory has been created")
        else:
            print("⚠️ Cache directory does not exist")
    
except Exception as e:
    print(f"❌ cache_manager Import failed: {e}")
    traceback.print_exc()

# Test and optimize US stock data
try:
    from tradingagents.dataflows.optimized_us_data import get_optimized_us_data_provider
    print("✅ optimized_us_data Import successful")
    
    # Create data provider
    provider = get_optimized_us_data_provider()
    print(f"✅ Data provider created successfully: {type(provider).__name__}")
    
except Exception as e:
    print(f"❌ optimized_us_data Import failed: {e}")
    traceback.print_exc()

# Test configuration module
try:
    from tradingagents.dataflows.config import get_config
    print("✅ config Import successful")
    
    # Get configuration
    config = get_config()
    print(f"✅ Configuration obtained successfully: {type(config).__name__}")
    
except Exception as e:
    print(f"❌ config Import failed: {e}")
    traceback.print_exc()

# Test 4: Basic functional test
print("\n💾 Test basic cache functions...")
try:
    cache = get_cache()
    
    # Test data storage
    test_data = f"test data - {datetime.now()}"
    cache_key = cache.save_stock_data(
        symbol="TEST",
        data=test_data,
        start_date="2024-01-01",
        end_date="2024-12-31",
        data_source="integration_test"
    )
    print(f"✅ Data saved successfully: {cache_key}")
    
    # Test data loading
    loaded_data = cache.load_stock_data(cache_key)
    if loaded_data == test_data:
        print("✅ The data is loaded successfully and the content matches")
    else:
        print(f"❌ Data does not match")
        print(f"  Expectation: {test_data}")
        print(f"  actual: {loaded_data}")
    
    # Test cache lookup
    found_key = cache.find_cached_stock_data(
        symbol="TEST",
        start_date="2024-01-01",
        end_date="2024-12-31",
        data_source="integration_test"
    )
    
    if found_key:
        print(f"✅ Cache lookup successful: {found_key}")
    else:
        print("❌ Cache lookup failed")
    
except Exception as e:
    print(f"❌ Cache functionality test failed: {e}")
    traceback.print_exc()

# Test 5: Performance Test
print("\n⚡ Simple performance test...")
try:
    import time
    
    cache = get_cache()
    
    # save test
    start_time = time.time()
    cache_key = cache.save_stock_data(
        symbol="PERF",
        data="Performance test data",
        start_date="2024-01-01",
        end_date="2024-12-31",
        data_source="perf_test"
    )
    save_time = time.time() - start_time
    
    # load test
    start_time = time.time()
    data = cache.load_stock_data(cache_key)
    load_time = time.time() - start_time
    
    print(f"📊 save time: {save_time:.4f}seconds")
    print(f"⚡ Loading time: {load_time:.4f}seconds")
    
    if load_time < 0.1:
        print("✅ Good caching performance (<0.1 seconds)")
    else:
        print("⚠️ Cache performance needs to be optimized")
    
except Exception as e:
    print(f"❌ Performance test failed: {e}")

# Test 6: Cache Statistics
print("\n📊 cache statistics...")
try:
    cache = get_cache()
    stats = cache.get_cache_stats()
    
    print("cache statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
except Exception as e:
    print(f"❌ Cache statistics failed: {e}")

print("\n" + "=" * 40)
print("🎉 Integration testing completed!")
print(f"Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Generate test report
print("\n📋 Test summary:")
print("1. File copy: Check if files are copied correctly")
print("2. Grammar check: Verify Python syntax correctness")
print("3. module import: Test whether the module can be imported normally")
print("4. Functional testing: Verify basic cache functionality")
print("5. Performance testing: Check caching performance")
print("6. Statistics: Get cache usage statistics")

print("\n🎯 Next step:")
print("1. If the test passes, you can start cleaning up Chinese content")
print("2. Add English documentation and comments")
print("3. Create complete test cases")
print("4. Prepare performance benchmark report")
print("5. Contact the upstream project maintainer")
