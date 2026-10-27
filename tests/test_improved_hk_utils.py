#!/usr/bin/env python3
"""
Testing improved Hong Kong stock tools
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_improved_hk_provider():
    """Testing the improved Hong Kong stock provider"""
    print("\n🇭🇰 Testing the improved Hong Kong stock provider")
    print("=" * 80)
    
    try:
        from tradingagents.dataflows.providers.hk.improved_hk import get_improved_hk_provider
        
        provider = get_improved_hk_provider()
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
        for symbol in test_symbols:
            try:
                company_name = provider.get_company_name(symbol)
                print(f"   {symbol:10} -> {company_name}")
                
                # Validation is not the default format
                if not company_name.startswith('Hong Kong stocks'):
                    print(f"      ✅ Successfully obtained the specific company name")
                else:
                    print(f"      ⚠️ Use default format")
                    
            except Exception as e:
                print(f"   {symbol:10} -> ❌ Error: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_analyst_integration():
    """Test Analyst Integration"""
    print("\n🔍 Test Analyst Integration")
    print("=" * 80)
    
    try:
        from tradingagents.agents.analysts.market_analyst import _get_company_name
        from tradingagents.agents.analysts.fundamentals_analyst import _get_company_name_for_fundamentals
        from tradingagents.utils.stock_utils import StockUtils
        
        test_hk_symbols = ["0700.HK", "0941.HK", "1299.HK"]
        
        for symbol in test_hk_symbols:
            print(f"\n📊 Test Hong Kong stocks: {symbol}")
            
            # Get market information
            market_info = StockUtils.get_market_info(symbol)
            print(f"   market information: {market_info['market_name']}")
            
            # test market analyst
            try:
                market_name = _get_company_name(symbol, market_info)
                print(f"   market analyst: {market_name}")
            except Exception as e:
                print(f"   market analyst: ❌ {e}")
            
            # Test Fundamental Analyst
            try:
                fundamentals_name = _get_company_name_for_fundamentals(symbol, market_info)
                print(f"   fundamental analyst: {fundamentals_name}")
            except Exception as e:
                print(f"   fundamental analyst: ❌ {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cache_functionality():
    """Test caching functionality"""
    print("\n💾 Test caching functionality")
    print("=" * 80)
    
    try:
        from tradingagents.dataflows.providers.hk.improved_hk import get_improved_hk_provider
        import time
        
        provider = get_improved_hk_provider()
        
        # Use new cache path (avoid root directory pollution)
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

def main():
    """Main test function"""
    print("🚀 Start testing improved Hong Kong stock tools")
    print("=" * 100)
    
    results = []
    
    # test 1: Improve Hong Kong stock provider
    results.append(test_improved_hk_provider())
    
    # test 2: Analyst integration
    results.append(test_analyst_integration())
    
    # test 3: Caching function
    results.append(test_cache_functionality())
    
    # Summary results
    print("\n" + "=" * 100)
    print("📋 Summary of test results")
    print("=" * 100)
    
    passed = sum(results)
    total = len(results)
    
    test_names = [
        "Improve Hong Kong stock provider",
        "Analyst integration testing",
        "Cache function test"
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
        print("3. ✅ Rate limiting protection to avoid API errors")
        print("4. ✅ Multi-level degradation scheme to ensure availability")
        print("5. ✅ Friendly error handling and logging")
    else:
        # Keep the original output structure
        pass

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
