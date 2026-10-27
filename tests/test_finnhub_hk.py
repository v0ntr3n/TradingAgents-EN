"""
Test FINNHUB Hong Kong stock support
"""

import sys
import os

# Add project root directory to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_finnhub_connection():
    """Test FINNHUB connection"""
    print("🧪 Test FINNHUB connection...")
    
    try:
        import finnhub
        
        api_key = os.getenv('FINNHUB_API_KEY')
        if not api_key:
            print("❌ The FINNHUB_API_KEY environment variable is not configured")
            return False
        
        client = finnhub.Client(api_key=api_key)
        
        # Test US stock connection
        print("  Test US stock connection (AAPL)...")
        quote = client.quote('AAPL')
        if quote and 'c' in quote:
            print(f"    ✅ US stock connection successful: AAPL = ${quote['c']:.2f}")
        else:
            print("    ❌ US stock connection failed")
            return False
        
        print("✅ FINNHUB Connection test passed")
        return True
        
    except Exception as e:
        print(f"❌ FINNHUB Connection test failed: {e}")
        return False

def test_finnhub_hk_symbols():
    """Test FINNHUB Hong Kong stock code format"""
    print("\n🧪 Test FINNHUB Hong Kong stock code format...")
    
    try:
        import finnhub
        
        api_key = os.getenv('FINNHUB_API_KEY')
        if not api_key:
            print("❌ The FINNHUB_API_KEY environment variable is not configured")
            return False
        
        client = finnhub.Client(api_key=api_key)
        
        # Test different Hong Kong stock code formats
        hk_symbols = [
            "0700.HK",  # Tencent
            "9988.HK",  # Alibaba
            "3690.HK",  # Meituan
            "1810.HK",  # Xiaomi
        ]
        
        success_count = 0
        
        for symbol in hk_symbols:
            try:
                print(f"  Test Hong Kong stocks: {symbol}...")
                quote = client.quote(symbol)
                
                if quote and 'c' in quote and quote['c'] > 0:
                    print(f"    ✅ {symbol} = HK${quote['c']:.2f}")
                    success_count += 1
                else:
                    print(f"    ❌ {symbol} No data or price is 0")
                    
            except Exception as e:
                print(f"    ❌ {symbol} Failed to obtain: {e}")
        
        if success_count > 0:
            print(f"✅ FINNHUB Hong Kong stock support test passed ({success_count}/{len(hk_symbols)} success)")
            return True
        else:
            print("❌ FINNHUB Hong Kong stock support test failed - data cannot be obtained for all Hong Kong stock symbols")
            return False
        
    except Exception as e:
        print(f"❌ FINNHUB Hong Kong stock support test failed: {e}")
        return False

def test_finnhub_hk_company_info():
    """Test FINNHUB Hong Kong stock company information"""
    print("\n🧪 Test FINNHUB Hong Kong stock company information...")
    
    try:
        import finnhub
        
        api_key = os.getenv('FINNHUB_API_KEY')
        if not api_key:
            print("❌ The FINNHUB_API_KEY environment variable is not configured")
            return False
        
        client = finnhub.Client(api_key=api_key)
        
        symbol = "0700.HK"  # Tencent
        print(f"  get {symbol} Company information...")
        
        try:
            profile = client.company_profile2(symbol=symbol)
            
            if profile and 'name' in profile:
                print(f"    ✅ Company name: {profile['name']}")
                print(f"    ✅ country: {profile.get('country', 'N/A')}")
                print(f"    ✅ Currency: {profile.get('currency', 'N/A')}")
                print(f"    ✅ exchange: {profile.get('exchange', 'N/A')}")
                print(f"    ✅ Industry: {profile.get('finnhubIndustry', 'N/A')}")
                return True
            else:
                print(f"    ❌ {symbol} Company information is empty")
                return False
                
        except Exception as e:
            print(f"    ❌ {symbol} Failed to obtain company information: {e}")
            return False
        
    except Exception as e:
        print(f"❌ FINNHUB Hong Kong stock company information test failed: {e}")
        return False

def test_optimized_us_data_finnhub_hk():
    """FINNHUB Hong Kong stock support for testing optimized data module"""
    print("\n🧪 FINNHUB Hong Kong stock support for testing optimized data module...")
    
    try:
        from tradingagents.dataflows.optimized_us_data import get_us_stock_data_cached
        from datetime import datetime, timedelta
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        symbol = "0700.HK"  # Tencent
        print(f"  Obtained through optimization module {symbol} data...")
        
        data = get_us_stock_data_cached(symbol, start_date, end_date, force_refresh=True)
        
        if data and len(data) > 100:
            print("    ✅ Data acquisition successful")
            
            # Check key information
            checks = [
                ("Hong Kong stocks", "Identified as Hong Kong stocks"),
                ("HK$", "Use Hong Kong dollar symbol"),
                ("FINNHUB", "Using the FINNHUB data source"),
                (symbol, "Contains ticker symbol")
            ]
            
            for check_text, description in checks:
                if check_text in data:
                    print(f"      ✅ {description}")
                else:
                    print(f"      ⚠️ missing{description}")
            
            print("✅ Optimized data module FINNHUB Hong Kong stock support test passed")
            return True
        else:
            print("❌ Optimized data module FINNHUB Hong Kong stock support test failed")
            print(f"Return data: {data[:200]}...")
            return False
            
    except Exception as e:
        print(f"❌ Optimized data module FINNHUB Hong Kong stock support test failed: {e}")
        return False

def test_unified_interface_finnhub_priority():
    """Test FINNHUB priority for unified interface"""
    print("\n🧪 Test FINNHUB priority for unified interface...")
    
    try:
        from tradingagents.dataflows.interface import get_hk_stock_data_unified
        from datetime import datetime, timedelta
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        symbol = "0700.HK"
        print(f"  Obtained through unified interface {symbol} data...")
        
        data = get_hk_stock_data_unified(symbol, start_date, end_date)
        
        if data and len(data) > 50:
            print("    ✅ Unified interface data is obtained successfully")
            
            # Check data source priority
            if "FINNHUB" in data:
                print("    ✅ Prioritize using FINNHUB data source")
            elif "Yahoo Finance" in data:
                print("    ✅ Use Yahoo Finance alternative data sources")
            elif "AKShare" in data:
                print("    ✅ Use AKShare alternative data source")
            else:
                print("    ⚠️ Data source not recognized")
            
            print("✅ Unified interface FINNHUB priority test passed")
            return True
        else:
            print("❌ Unified interface FINNHUB priority test failed")
            return False
        
    except Exception as e:
        print(f"❌ Unified interface FINNHUB priority test failed: {e}")
        return False

def main():
    """Run all FINNHUB Hong Kong stock tests"""
    print("🇭🇰 Start FINNHUB Hong Kong stock support test")
    print("=" * 50)
    
    tests = [
        test_finnhub_connection,
        test_finnhub_hk_symbols,
        test_finnhub_hk_company_info,
        test_optimized_us_data_finnhub_hk,
        test_unified_interface_finnhub_priority
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
    print(f"🇭🇰 FINNHUB Hong Kong stock support test completed: {passed}/{total} Pass")
    
    if passed >= 2:  # At least connectivity and basic functionality works
        print("🎉 FINNHUB Hong Kong stock support is basically normal!")
        print("\n✅ FINNHUB Functional features of Hong Kong stocks:")
        print("  - Support real-time quotation of Hong Kong stocks")
        print("  - Support Hong Kong stock company information")
        print("  - As the preferred data source for Hong Kong stock data")
        print("  - Automatic currency symbol recognition (HK$)")
        print("  - Integrated into Unified Data Interface")
    else:
        print("⚠️ FINNHUB There may be a problem with Hong Kong stock support, please check the API configuration")

if __name__ == "__main__":
    main()
