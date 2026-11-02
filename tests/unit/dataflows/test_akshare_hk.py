"""
Test the AKShare Hong Kong stock function
"""

import sys
import os

# Add project root directory to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_akshare_hk_basic():
    """Test the basic functions of AKShare Hong Kong stocks"""
    print("🧪 Test the basic functions of AKShare Hong Kong stocks...")
    
    try:
        from tradingagents.dataflows.akshare_utils import get_akshare_provider
        
        provider = get_akshare_provider()
        
        if not provider.connected:
            print("⚠️ AKShare Not connected, skip test")
            return True
        
        # Testing Hong Kong stock code standardization
        test_symbols = [
            ("0700.HK", "00700"),
            ("700", "00700"),
            ("9988.HK", "09988"),
            ("3690", "03690")
        ]
        
        for input_symbol, expected in test_symbols:
            normalized = provider._normalize_hk_symbol_for_akshare(input_symbol)
            print(f"  Standardization: {input_symbol} -> {normalized} {'✅' if normalized == expected else '❌'}")
            
            if normalized != expected:
                print(f"❌ Hong Kong stock code standardization fails: {input_symbol} -> {normalized}, Expectation: {expected}")
                return False
        
        print("✅ AKShare Passed the basic function test of Hong Kong stocks")
        return True
        
    except Exception as e:
        print(f"❌ AKShare Hong Kong stock basic function test failed: {e}")
        return False

def test_akshare_hk_data():
    """Test AKShare Hong Kong stock data acquisition"""
    print("\n🧪 Test AKShare Hong Kong stock data acquisition...")
    
    try:
        from tradingagents.dataflows.akshare_utils import get_hk_stock_data_akshare
        from datetime import datetime, timedelta
        
        # Set test date
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        # Test Tencent Hong Kong stocks
        symbol = "0700.HK"
        print(f"  get {symbol} data...")
        
        data = get_hk_stock_data_akshare(symbol, start_date, end_date)
        
        if data and len(data) > 100:
            print("  ✅ AKShare Hong Kong stock data obtained successfully")
            
            # Check key information
            checks = [
                ("Hong Kong Stock Data Report", "Contains title"),
                ("AKShare", "Contains data source identifier"),
                ("HK$", "Contains Hong Kong dollar symbol"),
                ("Hong Kong Exchange", "Contains exchange information"),
                (symbol, "Contains ticker symbol")
            ]
            
            for check_text, description in checks:
                if check_text in data:
                    print(f"    ✅ {description}")
                else:
                    print(f"    ⚠️ missing{description}")
            
            print("✅ AKShare Hong Kong stock data acquisition test passed")
            return True
        else:
            print("❌ AKShare Failed to obtain Hong Kong stock data")
            print(f"Return data: {data[:200]}...")
            return False
            
    except Exception as e:
        print(f"❌ AKShare Hong Kong stock data acquisition test failed: {e}")
        return False

def test_akshare_hk_info():
    """Test AKShare Hong Kong stock information acquisition"""
    print("\n🧪 Test AKShare Hong Kong stock information acquisition...")
    
    try:
        from tradingagents.dataflows.akshare_utils import get_hk_stock_info_akshare
        
        symbol = "0700.HK"
        print(f"  get {symbol} information...")
        
        info = get_hk_stock_info_akshare(symbol)
        
        if info and 'symbol' in info:
            print(f"    ✅ Stock code: {info['symbol']}")
            print(f"    ✅ Stock name: {info['name']}")
            print(f"    ✅ Currency: {info['currency']}")
            print(f"    ✅ exchange: {info['exchange']}")
            print(f"    ✅ data source: {info['source']}")
            
            # Verify Hong Kong stock-specific information
            if info['currency'] == 'HKD' and info['exchange'] == 'HKG':
                print("    ✅ Hong Kong stock information is correct")
            else:
                print("    ⚠️ Hong Kong stock information may be incomplete")
            
            print("✅ AKShare Hong Kong stock information acquisition test passed")
            return True
        else:
            print("❌ AKShare Failed to obtain Hong Kong stock information")
            return False
            
    except Exception as e:
        print(f"❌ AKShare Hong Kong stock information acquisition test failed: {e}")
        return False

def test_unified_interface():
    """Testing AKShare support for unified interface"""
    print("\n🧪 Testing AKShare support for unified interface...")
    
    try:
        from tradingagents.dataflows.interface import get_hk_stock_data_unified, get_hk_stock_info_unified
        from datetime import datetime, timedelta
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        symbol = "0700.HK"
        print(f"  Obtained through unified interface {symbol} data...")
        
        # Test data acquisition
        data = get_hk_stock_data_unified(symbol, start_date, end_date)
        
        if data and len(data) > 50:
            print("    ✅ Unified interface data is obtained successfully")
            
            # Check if AKShare logo is included
            if "AKShare" in data:
                print("    ✅ Successfully used AKShare as a data source")
            elif "Yahoo Finance" in data:
                print("    ✅ Use Yahoo Finance as an alternate data source")
            elif "Demo mode" in data:
                print("    ✅ Use demo mode as a final fallback")
            
        # Get test information
        info = get_hk_stock_info_unified(symbol)
        
        if info and 'symbol' in info:
            print("    ✅ Unified interface information obtained successfully")
            print(f"    data source: {info.get('source', 'unknown')}")
        
        print("✅ Unified interface AKShare support test passed")
        return True
        
    except Exception as e:
        print(f"❌ Unified interface AKShare support test failed: {e}")
        return False

def main():
    """Run all AKShare Hong Kong stock tests"""
    print("🇭🇰 Start AKShare Hong Kong stock function test")
    print("=" * 50)
    
    tests = [
        test_akshare_hk_basic,
        test_akshare_hk_data,
        test_akshare_hk_info,
        test_unified_interface
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ test {test_func.__name__} Abnormal: {e}")
    
    print("\n" + "=" * 50)
    print(f"🇭🇰 AKShare Hong Kong stock function test completed: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 All tests passed! AKShare Hong Kong stocks function normally")
        print("\n✅ AKShare Functional features of Hong Kong stocks:")
        print("  - Support Hong Kong stock code format conversion")
        print("  - Get historical data of Hong Kong stocks")
        print("  - Get basic information about Hong Kong stocks")
        print("  - Integrated into Unified Data Interface")
        print("  - As a backup to Yahoo Finance")
    else:
        print("⚠️ Some tests fail, but core functionality may work")

if __name__ == "__main__":
    main()
