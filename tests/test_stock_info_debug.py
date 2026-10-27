#!/usr/bin/env python3
"""
Stock information acquisition debugging test
Specialized in diagnosing why certain stocks are showing"Unknown company"
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_stock_code_normalization():
    """Test ticker standardization"""
    print("\n🔧 Test ticker standardization")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.tushare_utils import get_tushare_provider
        
        provider = get_tushare_provider()
        
        test_codes = ["000858", "600036", "000001", "300001"]
        
        for code in test_codes:
            normalized = provider._normalize_symbol(code)
            print(f"📊 {code} -> {normalized}")
        
        return True
        
    except Exception as e:
        print(f"❌ Stock symbol standardized test failed: {e}")
        return False


def test_tushare_api_direct():
    """direct test Tushare API"""
    print("\n🔧 direct test Tushare API")
    print("=" * 60)
    
    try:
        import tushare as ts
        import os
        
        token = os.getenv('TUSHARE_TOKEN')
        if not token:
            print("❌ TUSHARE_TOKEN not set")
            return False
        
        ts.set_token(token)
        pro = ts.pro_api()
        
        # Test to obtain the information of 000858
        print("🔄 Test to obtain the basic information of 000858.SZ...")
        
        try:
            basic_info = pro.stock_basic(
                ts_code='000858.SZ',
                fields='ts_code,symbol,name,area,industry,market,list_date'
            )
            
            if not basic_info.empty:
                info = basic_info.iloc[0]
                print(f"✅ Find stock information:")
                print(f"   code: {info['ts_code']}")
                print(f"   Name: {info['name']}")
                print(f"   Industry: {info.get('industry', 'N/A')}")
                print(f"   area: {info.get('area', 'N/A')}")
                return True
            else:
                print("❌ No information found for 000858.SZ")
                
                # Try searching for all stocks containing 858
                print("🔄 Search all stocks containing 858...")
                all_stocks = pro.stock_basic(
                    exchange='',
                    list_status='L',
                    fields='ts_code,symbol,name,area,industry,market,list_date'
                )
                
                matches = all_stocks[all_stocks['symbol'].str.contains('858', na=False)]
                if not matches.empty:
                    print(f"✅ found{len(matches)}Contains only 858 stocks:")
                    for idx, row in matches.iterrows():
                        print(f"   {row['ts_code']} - {row['name']}")
                else:
                    print("❌ No stocks containing 858 found")
                
                return False
                
        except Exception as e:
            print(f"❌ API call failed: {e}")
            return False
        
    except Exception as e:
        print(f"❌ Tushare API test failed: {e}")
        return False


def test_stock_list_search():
    """Test stock list search"""
    print("\n🔧 Test stock list search")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.tushare_utils import get_tushare_provider
        
        provider = get_tushare_provider()
        
        if not provider.connected:
            print("❌ Tushare Not connected")
            return False
        
        # Get a list of stocks
        print("🔄 Get the full stock list...")
        stock_list = provider.get_stock_list()
        
        if stock_list.empty:
            print("❌ Stock list is empty")
            return False
        
        print(f"✅ Get{len(stock_list)}only stocks")
        
        # Search 000858
        print("🔄 Search 000858...")
        matches = stock_list[stock_list['symbol'] == '000858']
        
        if not matches.empty:
            print("✅ found 000858:")
            for idx, row in matches.iterrows():
                print(f"   {row['ts_code']} - {row['name']} - {row.get('industry', 'N/A')}")
        else:
            print("❌ Not found in stock list 000858")
            
            # Search for stocks containing 858
            partial_matches = stock_list[stock_list['symbol'].str.contains('858', na=False)]
            if not partial_matches.empty:
                print(f"✅ found{len(partial_matches)}Contains only 858 stocks:")
                for idx, row in partial_matches.head(5).iterrows():
                    print(f"   {row['ts_code']} - {row['name']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Stock list search failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_alternative_stock_codes():
    """Test other stock symbols"""
    print("\n🔧 Test other stock symbols")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.tushare_adapter import get_tushare_adapter
        
        adapter = get_tushare_adapter()
        
        # Test several known stock symbols
        test_codes = [
            ("000001", "Ping An Bank"),
            ("600036", "China Merchants Bank"),
            ("000002", "Vanke A"),
            ("600519", "Kweichow Moutai"),
            ("000858", "Wuliangye")  # This may be the problem code
        ]
        
        for code, expected_name in test_codes:
            print(f"🔄 test {code} (Expectation: {expected_name})...")
            
            info = adapter.get_stock_info(code)
            
            if info and info.get('name') and info['name'] != f'stocks{code}':
                print(f"✅ {code}: {info['name']}")
                if expected_name in info['name']:
                    print(f"   ✅ name match")
                else:
                    print(f"   ⚠️ Name does not match, expected: {expected_name}")
            else:
                print(f"❌ {code}: Failed to obtain or returned unknown")
        
        return True
        
    except Exception as e:
        print(f"❌ Other stock symbol tests failed: {e}")
        return False


def main():
    """Main test function"""
    print("🔍 Stock information acquisition debugging test")
    print("=" * 70)
    print("💡 debug target:")
    print("   - Diagnose why 000858 is displayed'Unknown company'")
    print("   - Check stock symbol standardization")
    print("   - Verify Tushare API response")
    print("   - Test stock list search")
    print("=" * 70)
    
    # Run all tests
    tests = [
        ("Stock code standardization", test_stock_code_normalization),
        ("Tushare API direct test", test_tushare_api_direct),
        ("Stock list search", test_stock_list_search),
        ("Other stock symbol tests", test_alternative_stock_codes)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}Test exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n📋 Stock information debugging test summary")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\n📊 Test results: {passed}/{total} Pass")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        print("💡 If 000858 still shows unknown, it may be:")
        print("   1. The stock code does not exist in Tushare")
        print("   2. The stock has been delisted or suspended from trading")
        print("   3. Need to use different query methods")
    else:
        print("\n⚠️ Some tests failed, please check for specific issues")
    
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
