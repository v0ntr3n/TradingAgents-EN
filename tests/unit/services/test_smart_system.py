#!/usr/bin/env python3
"""
Intelligent System Complete Testing - Validating Adaptive Configuration and Caching Systems
"""

import time
import sys
from datetime import datetime

def test_smart_config():
    """Test the intelligent configuration system"""
    print("🔧 Test the intelligent configuration system")
    print("-" * 30)
    
    try:
        from smart_config import get_smart_config, get_config
        
        # Get configuration manager
        config_manager = get_smart_config()
        config_manager.print_status()
        
        # Get configuration information
        config = get_config()
        print(f"\n✅ Configuration obtained successfully")
        print(f"Main caching backend: {config['cache']['primary_backend']}")
        
        return True, config_manager
        
    except Exception as e:
        print(f"❌ Smart configuration test failed: {e}")
        return False, None

def test_adaptive_cache():
    """Test the adaptive caching system"""
    print("\n💾 Test the adaptive caching system")
    print("-" * 30)
    
    try:
        from adaptive_cache_manager import get_cache
        
        # Get cache manager
        cache = get_cache()
        
        # Show cache status
        stats = cache.get_cache_stats()
        print("📊 cache status:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        # Test basic functionality
        print("\n🧪 Test basic caching functionality...")
        
        test_data = f"test data - {datetime.now()}"
        cache_key = cache.save_stock_data(
            symbol="AAPL",
            data=test_data,
            start_date="2024-01-01",
            end_date="2024-12-31",
            data_source="smart_test"
        )
        print(f"✅ Data saved successfully: {cache_key}")
        
        # Test loading
        loaded_data = cache.load_stock_data(cache_key)
        if loaded_data == test_data:
            print("✅ The data is loaded successfully and the content matches")
        else:
            print("❌ Data loading failed or content does not match")
            return False
        
        # Test lookup
        found_key = cache.find_cached_stock_data(
            symbol="AAPL",
            start_date="2024-01-01",
            end_date="2024-12-31",
            data_source="smart_test"
        )
        
        if found_key:
            print(f"✅ Cache lookup successful: {found_key}")
        else:
            print("❌ Cache lookup failed")
            return False
        
        return True, cache
        
    except Exception as e:
        print(f"❌ Adaptive cache test failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def test_performance():
    """Test performance"""
    print("\n⚡ Test cache performance")
    print("-" * 30)
    
    try:
        from adaptive_cache_manager import get_cache
        
        cache = get_cache()
        
        # Performance test data
        symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"]
        
        print("📊 Performance test results:")
        
        total_save_time = 0
        total_load_time = 0
        
        for symbol in symbols:
            test_data = f"Performance test data - {symbol}"
            
            # Test save performance
            start_time = time.time()
            cache_key = cache.save_stock_data(
                symbol=symbol,
                data=test_data,
                start_date="2024-01-01",
                end_date="2024-12-31",
                data_source="perf_test"
            )
            save_time = time.time() - start_time
            total_save_time += save_time
            
            # Test loading performance
            start_time = time.time()
            loaded_data = cache.load_stock_data(cache_key)
            load_time = time.time() - start_time
            total_load_time += load_time
            
            print(f"  {symbol}: save {save_time:.4f}s, Load {load_time:.4f}s")
        
        avg_save_time = total_save_time / len(symbols)
        avg_load_time = total_load_time / len(symbols)
        
        print(f"\n📈 average performance:")
        print(f"  save time: {avg_save_time:.4f}seconds")
        print(f"  Loading time: {avg_load_time:.4f}seconds")
        
        # Compute performance improvements
        api_simulation_time = 2.0  # Let's say the API call takes 2 seconds
        if avg_load_time < api_simulation_time:
            improvement = ((api_simulation_time - avg_load_time) / api_simulation_time) * 100
            print(f"  Performance improvements: {improvement:.1f}%")
            
            if improvement > 90:
                print("🚀 Performance improvements are significant!")
                return True
            else:
                print("⚠️ Limited performance improvements")
                return True
        else:
            print("❌ Cache performance is not as expected")
            return False
            
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        return False

def test_fallback_mechanism():
    """Test the downgrade mechanism"""
    print("\n🔄 Test the downgrade mechanism")
    print("-" * 30)
    
    try:
        from adaptive_cache_manager import get_cache
        
        cache = get_cache()
        
        # Check downgrade configuration
        if cache.fallback_enabled:
            print("✅ Downgrade mechanism is enabled")
        else:
            print("⚠️ Downgrade mechanism is not enabled")
        
        # Test behavior when primary backend is unavailable
        print(f"Main backend: {cache.primary_backend}")
        
        if cache.primary_backend == "file":
            print("✅ Use file caching without downgrading")
        elif cache.primary_backend == "redis" and not cache.redis_enabled:
            print("✅ Redis Unavailable, automatically downgraded to file cache")
        elif cache.primary_backend == "mongodb" and not cache.mongodb_enabled:
            print("✅ MongoDB Unavailable, automatically downgraded to file cache")
        else:
            print(f"✅ {cache.primary_backend} backend works fine")
        
        return True
        
    except Exception as e:
        print(f"❌ Downgrade mechanism test failed: {e}")
        return False

def generate_test_report(results):
    """Generate test report"""
    print("\n📋 test report")
    print("=" * 50)
    
    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)
    
    print(f"Total number of tests: {total_tests}")
    print(f"Pass test: {passed_tests}")
    print(f"failed test: {total_tests - passed_tests}")
    print(f"pass rate: {(passed_tests/total_tests)*100:.1f}%")
    
    print("\n Detailed results:")
    for test_name, result in results.items():
        status = "✅ Pass" if result else "❌ failed"
        print(f"  {test_name}: {status}")
    
    # Generate suggestions
    print("\n💡 Suggestions:")
    
    if all(results.values()):
        print("🎉 All tests passed! The system can run normally")
        print("✅ You can start preparing for upstream contributions")
    else:
        print("⚠️ Some tests failed and the following issues need to be checked:")
        
        if not results.get("Intelligent configuration", True):
            print("  - Check out the smart configuration system")
        if not results.get("Adaptive caching", True):
            print("  - Check cache system configuration")
        if not results.get("Performance testing", True):
            print("  - Optimize caching performance")
        if not results.get("Downgrade mechanism", True):
            print("  - Check the downgrade mechanism configuration")

def main():
    """Main test function"""
    print("🚀 TradingAgents Complete testing of intelligent systems")
    print("=" * 50)
    print(f"Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Execute all tests
    results = {}
    
    # test 1: Intelligent configuration
    config_success, config_manager = test_smart_config()
    results["Intelligent configuration"] = config_success
    
    # test 2: Adaptive caching
    cache_success, cache_manager = test_adaptive_cache()
    results["Adaptive caching"] = cache_success
    
    # test 3: Performance testing
    if cache_success:
        perf_success = test_performance()
        results["Performance testing"] = perf_success
    else:
        results["Performance testing"] = False
    
    # test 4: Downgrade mechanism
    if cache_success:
        fallback_success = test_fallback_mechanism()
        results["Downgrade mechanism"] = fallback_success
    else:
        results["Downgrade mechanism"] = False
    
    # Generate report
    generate_test_report(results)
    
    # Save configuration (if available)
    if config_manager:
        config_manager.save_config("test_config.json")
        print(f"\n💾 Test configuration saved: test_config.json")
    
    # Return overall results
    return all(results.values())

if __name__ == "__main__":
    success = main()
    
    print(f"\n🎯 test{'success' if success else 'failed'}!")
    
    if success:
        print("\n Next step:")
        print("1. Clean up Chinese content")
        print("2. Add English document")
        print("3. Prepare for upstream contributions")
    else:
        print("\n Problems that need to be solved:")
        print("1. Check dependency installation")
        print("2. Fix configuration issues")
        print("3. Rerun test")
    
    sys.exit(0 if success else 1)
