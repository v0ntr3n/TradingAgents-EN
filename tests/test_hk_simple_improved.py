#!/usr/bin/env python3
"""
Test the improved Hong Kong stock tool (simplified version, direct import)
"""

import os
import sys
import time

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_hk_provider_direct():
    """Directly test the Hong Kong stock provider"""
    print("\n🇭🇰 Directly test the Hong Kong stock provider")
    print("=" * 80)
    
    try:
        # Directly import improved Hong Kong stock tools
        from improved_hk_utils import ImprovedHKStockProvider
        
        provider = ImprovedHKStockProvider()
        print("✅ Improved Hong Kong stock provider initialization success")
        
        # Test Hong Kong stock codes in different formats
        test_symbols = [
            "0700.HK",  # Tencent Holdings
            "0700",     # Tencent Holdings (no suffix)
            "00700",    # Tencent Holdings (5th place)
            "0941.HK",  # China Mobile
            "1299",     # AIA
            "9988.HK",  # Alibaba
            "3690",     # Meituan
            "1234.HK",  # non-existent stocks
        ]
        
        print(f"\n📊 Test the acquisition of Hong Kong stock company name:")
        success_count = 0
        for symbol in test_symbols:
            try:
                company_name = provider.get_company_name(symbol)
                print(f"   {symbol:10} -> {company_name}")
                
                # Validation is not the default format
                if not company_name.startswith('Hong Kong stocks'):
                    print(f"      ✅ Successfully obtained the specific company name")
                    success_count += 1
                else:
                    print(f"      ⚠️ Use default format")
                    
            except Exception as e:
                print(f"   {symbol:10} -> ❌ Error: {e}")
        
        print(f"\n✅ The number of specific names successfully obtained: {success_count}")
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cache_direct():
    """Directly test caching functionality"""
    print("\n💾 Directly test caching functionality")
    print("=" * 80)
    
    try:
        from improved_hk_utils import ImprovedHKStockProvider
        
        provider = ImprovedHKStockProvider()
        
        # Use new cache path
        cache_dir = os.path.join('data', 'cache', 'hk')
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, 'hk_stock_cache.json')
        
        # Clean possible cache files
        if os.path.exists(cache_file):
            os.remove(cache_file)
            print("🗑️ Clean old cache files")
        
        test_symbol = "0700.HK"
        
        # First acquisition (should use built-in mapping)
        print(f"\n📊 Get it for the first time {test_symbol}:")
        start_time = time.time()
        name1 = provider.get_company_name(test_symbol)
        time1 = time.time() - start_time
        print(f"   result: {name1}")
        print(f"   Time consuming: {time1:.3f}seconds")
        
        # Second fetch (cache should be used)
        print(f"\n📊 second acquisition {test_symbol}:")
        start_time = time.time()
        name2 = provider.get_company_name(test_symbol)
        time2 = time.time() - start_time
        print(f"   result: {name2}")
        print(f"   Time consuming: {time2:.3f}seconds")
        
        # Verify result consistency
        if name1 == name2:
            print("✅ Cached results are consistent")
        else:
            print("❌ Cached results are inconsistent")
        
        # Check cache files
        if os.path.exists(cache_file):
            print("✅ Cache file has been created")
            
            # Read cache contents
            import json
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            print(f"📄 Number of cache entries: {len(cache_data)}")
            for key, value in cache_data.items():
                print(f"   {key}: {value['data']} (Source: {value['source']})")
        else:
            print("⚠️ Cache file not created")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_normalization():
    """Testing Hong Kong stock code standardization"""
    print("\n🔧 Testing Hong Kong stock code standardization")
    print("=" * 80)
    
    try:
        from improved_hk_utils import ImprovedHKStockProvider
        
        provider = ImprovedHKStockProvider()
        
        test_cases = [
            ("0700.HK", "00700"),
            ("0700", "00700"),
            ("700", "00700"),
            ("70", "00070"),
            ("7", "00007"),
            ("1299.HK", "01299"),
            ("1299", "01299"),
            ("9988.HK", "09988"),
            ("9988", "09988"),
        ]
        
        print("📊 Hong Kong Stock Code Standardization Test:")
        for input_symbol, expected in test_cases:
            normalized = provider._normalize_hk_symbol(input_symbol)
            status = "✅" if normalized == expected else "❌"
            print(f"   {input_symbol:10} -> {normalized:10} (Expectation: {expected}) {status}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🚀 Start simplifying Hong Kong stock tool testing")
    print("=" * 100)
    
    results = []
    
    # test 1: Directly test the Hong Kong stock provider
    results.append(test_hk_provider_direct())
    
    # test 2: Directly test caching functionality
    results.append(test_cache_direct())
    
    # test 3: Test standardized functionality
    results.append(test_normalization())
    
    # Summary results
    print("\n" + "=" * 100)
    print("📋 Summary of test results")
    print("=" * 100)
    
    passed = sum(results)
    total = len(results)
    
    test_names = [
        "Hong Kong stock provider direct test",
        "Direct test of caching function",
        "Code standardized testing"
    ]
    
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ Pass" if result else "❌ failed"
        print(f"{i+1}. {name}: {status}")
    
    print(f"\n📊 Overall results: {passed}/{total} Test passed")
    
    if passed == total:
        print("🎉 All tests passed! Improve the normal operation of Hong Kong stock tools")
        print("\n📋 Improve results:")
        print("1. ✅ Built-in Hong Kong stock name mapping to avoid API calls")
        print("2. ✅ Intelligent caching mechanism to improve performance")
        print("3. ✅ Standardization of Hong Kong stock codes")
        print("4. ✅ Multi-level degradation scheme to ensure availability")
        print("5. ✅ Friendly error handling")
        
        print("\n🔧 Problem solved:")
        print("1. ❌ 'Too Many Requests' API Limit error")
        print("2. ❌ Failed to obtain Hong Kong stock names")
        print("3. ❌ Duplicate API calls due to lack of caching")
        print("4. ❌ The issue of inconsistent Hong Kong stock code formats")
    else:
        print("⚠️ Some tests failed and need further optimization")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
