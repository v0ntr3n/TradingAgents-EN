#!/usr/bin/env python3
"""
Test Finnhub fundamental data acquisition function, OpenAI fallback mechanism and caching function
"""

import os
import sys
import time
from datetime import datetime

# Add project root directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_finnhub_api_key():
    """Test Finnhub API key configuration"""
    print("🔑 Check Finnhub API key...")
    
    api_key = os.getenv('FINNHUB_API_KEY')
    if api_key:
        print(f"✅ Finnhub API Key configured: {api_key[:8]}...")
        return True
    else:
        print("❌ The FINNHUB_API_KEY environment variable is not configured")
        return False

def test_finnhub_fundamentals_with_cache():
    """Test Finnhub fundamental data acquisition and caching functions"""
    print("\n📊 Test Finnhub fundamental data acquisition and caching functions...")
    
    try:
        from tradingagents.dataflows.interface import get_fundamentals_finnhub
        from tradingagents.dataflows.cache_manager import get_cache
        
        # Clean possible caches
        cache = get_cache()
        test_ticker = "AAPL"
        curr_date = datetime.now().strftime('%Y-%m-%d')
        
        print(f"\n🔍 Get it for the first time {test_ticker} Fundamental data (obtained from API)...")
        start_time = time.time()
        result1 = get_fundamentals_finnhub(test_ticker, curr_date)
        first_time = time.time() - start_time
        
        if result1 and len(result1) > 100:
            print(f"✅ {test_ticker} Fundamental data is obtained successfully, length: {len(result1)}")
            print(f"⏱️ First acquisition time: {first_time:.2f}seconds")
            print(f"📄 Data preview: {result1[:200]}...")
            
            # The second time you get it, it should be read from the cache
            print(f"\n🔍 second acquisition {test_ticker} Fundamental data (obtained from cache)...")
            start_time = time.time()
            result2 = get_fundamentals_finnhub(test_ticker, curr_date)
            second_time = time.time() - start_time
            
            print(f"⏱️ The second acquisition time: {second_time:.2f}seconds")
            
            # Verify caching effect
            if second_time < first_time and result1 == result2:
                print(f"✅ The cache function is normal! Speed increased {((first_time - second_time) / first_time * 100):.1f}%")
                return True
            else:
                print(f"⚠️ Caching may not be effective")
                return False
        else:
            print(f"❌ {test_ticker} Failed to obtain fundamental data or the data is too short")
            print(f"📄 Return content: {result1}")
            return False
        
    except Exception as e:
        print(f"❌ Finnhub Fundamental data test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_openai_fallback_with_cache():
    """Test the OpenAI fallback mechanism and caching function"""
    print("\n🔄 Test the OpenAI fallback mechanism and caching function...")
    
    try:
        from tradingagents.dataflows.interface import get_fundamentals_openai
        
        # Temporarily remove OpenAI configuration for testing fallback
        original_backend_url = os.environ.get('BACKEND_URL')
        original_quick_think_llm = os.environ.get('QUICK_THINK_LLM')
        
        # Clear OpenAI configuration
        if 'BACKEND_URL' in os.environ:
            del os.environ['BACKEND_URL']
        if 'QUICK_THINK_LLM' in os.environ:
            del os.environ['QUICK_THINK_LLM']
        
        print("🚫 The OpenAI configuration has been temporarily removed and the test fallback is Finnhub...")
        
        curr_date = datetime.now().strftime('%Y-%m-%d')
        test_ticker = "MSFT"
        
        print(f"\n🔍 Obtained for the first time through the OpenAI interface {test_ticker} Data (should fallback to Finnhub)...")
        start_time = time.time()
        result1 = get_fundamentals_openai(test_ticker, curr_date)
        first_time = time.time() - start_time
        
        if result1 and "Finnhub" in result1:
            print("✅ OpenAI fallback The mechanism works normally and successfully falls back to Finnhub API")
            print(f"📄 Data length: {len(result1)}")
            print(f"⏱️ First acquisition time: {first_time:.2f}seconds")
            
            # The second time you get it, it should be read from the cache
            print(f"\n🔍 Obtained through the OpenAI interface for the second time {test_ticker} Data (should be obtained from cache)...")
            start_time = time.time()
            result2 = get_fundamentals_openai(test_ticker, curr_date)
            second_time = time.time() - start_time
            
            print(f"⏱️ The second acquisition time: {second_time:.2f}seconds")
            
            # Verify caching effect
            if second_time < first_time and result1 == result2:
                print(f"✅ fallback + The cache function is normal! Speed increased {((first_time - second_time) / first_time * 100):.1f}%")
                success = True
            else:
                print(f"⚠️ Caching may not be effective")
                success = False
        else:
            print("❌ OpenAI fallback There may be something wrong with the mechanism")
            print(f"📄 Return content: {result1[:500]}...")
            success = False
        
        # Restore original configuration
        if original_backend_url:
            os.environ['BACKEND_URL'] = original_backend_url
        if original_quick_think_llm:
            os.environ['QUICK_THINK_LLM'] = original_quick_think_llm
        
        return success
        
    except Exception as e:
        print(f"❌ OpenAI fallback test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_cache_management():
    """Test cache management functionality"""
    print("\n💾 Test cache management functionality...")
    
    try:
        from tradingagents.dataflows.cache_manager import get_cache
        
        cache = get_cache()
        
        # Get cache statistics
        stats = cache.get_cache_stats()
        print(f"📊 Current cache statistics: {stats}")
        
        # Check cache configuration
        print(f"\n⚙️ Fundamental data cache configuration:")
        for cache_type, config in cache.cache_config.items():
            if 'fundamentals' in cache_type:
                print(f"  - {cache_type}: TTL={config['ttl_hours']}hours, Maximum number of files={config['max_files']}, Description={config['description']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Cache management test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🚀 Start Finnhub fundamental data functionality and cache testing")
    print("=" * 60)
    
    # Check environment
    print(f"📍 current working directory: {os.getcwd()}")
    print(f"📍 Python path: {sys.path[0]}")
    
    # Run tests
    tests = [
        ("Finnhub API Key check", test_finnhub_api_key),
        ("Finnhub Fundamental data acquisition and caching", test_finnhub_fundamentals_with_cache),
        ("OpenAI fallback Mechanisms and caching", test_openai_fallback_with_cache),
        ("Cache management function", test_cache_management),
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
        print("🎉 All tests passed! Finnhub fundamental data functionality and caching system are working properly.")
        print("\n💡 Features:")
        print("1. ✅ When the OpenAI configuration is unavailable, the system automatically uses Finnhub API")
        print("2. ✅ Finnhub Provide official financial data, including key indicators such as PE, PS, ROE, etc.")
        print("3. ✅ The data comes from company financial reports and SEC documents and has high reliability.")
        print("4. ✅ Supports intelligent caching mechanism, caching US stock fundamental data for 24 hours and A-shares for 12 hours")
        print("5. ✅ The cache is stored according to market types to improve search efficiency.")
        print("6. ✅ Automatically detect cache validity and expired data will be retrieved again")
    else:
        print("⚠️ Some tests failed, please check the relevant configuration.")

if __name__ == "__main__":
    main()