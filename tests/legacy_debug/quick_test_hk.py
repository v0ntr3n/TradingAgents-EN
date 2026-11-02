"""
Quickly test the Hong Kong stock function
"""

import sys
import os

# Add project root directory to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_stock_recognition():
    """Test stock recognition"""
    print("🧪 Test stock recognition...")
    
    try:
        from tradingagents.utils.stock_utils import StockUtils
        
        test_cases = [
            "0700.HK",  # Tencent Hong Kong stocks
            "000001",   # Ping An Bank A shares
            "AAPL"      # Apple US stocks
        ]
        
        for ticker in test_cases:
            info = StockUtils.get_market_info(ticker)
            print(f"  {ticker}: {info['market_name']} ({info['currency_symbol']})")
        
        print("✅ Stock identification test completed")
        return True
        
    except Exception as e:
        print(f"❌ Stock recognition test failed: {e}")
        return False

def test_akshare_basic():
    """Test AKShare basic functions"""
    print("\n🧪 Test AKShare basic functions...")
    
    try:
        from tradingagents.dataflows.akshare_utils import get_akshare_provider
        
        provider = get_akshare_provider()
        
        if provider.connected:
            print("  ✅ AKShare Connection successful")
            
            # Testing Hong Kong stock code standardization
            test_symbol = "0700.HK"
            normalized = provider._normalize_hk_symbol_for_akshare(test_symbol)
            print(f"  Hong Kong stock code standardization: {test_symbol} -> {normalized}")
            
            return True
        else:
            print("  ⚠️ AKShare Not connected")
            return False
        
    except Exception as e:
        print(f"❌ AKShare Basic functional test failed: {e}")
        return False

def test_unified_interface():
    """Test unified interface"""
    print("\n🧪 Test unified interface...")
    
    try:
        from tradingagents.dataflows.interface import get_hk_stock_info_unified
        
        symbol = "0700.HK"
        print(f"  get {symbol} information...")
        
        info = get_hk_stock_info_unified(symbol)
        
        if info and 'symbol' in info:
            print(f"    code: {info['symbol']}")
            print(f"    Name: {info['name']}")
            print(f"    Currency: {info['currency']}")
            print(f"    data source: {info['source']}")
            print("  ✅ Unified interface test successful")
            return True
        else:
            print("  ❌ Unified interface test failed")
            return False
        
    except Exception as e:
        print(f"❌ Unified interface test failed: {e}")
        return False

def main():
    """Run a quick test"""
    print("🇭🇰 Quick test of Hong Kong stock function")
    print("=" * 30)
    
    tests = [
        test_stock_recognition,
        test_akshare_basic,
        test_unified_interface
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ Test exception: {e}")
    
    print("\n" + "=" * 30)
    print(f"🇭🇰 Test completed: {passed}/{total} Pass")
    
    if passed >= 2:
        print("🎉 The functions of Hong Kong stocks are basically normal!")
    else:
        print("⚠️ There may be a problem with the Hong Kong stock function")

if __name__ == "__main__":
    main()
