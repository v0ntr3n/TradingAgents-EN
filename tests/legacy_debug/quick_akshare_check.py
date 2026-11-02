#!/usr/bin/env python3
"""
Quick AKShare feature check
"""

def check_akshare_import():
    """Check AKShare import"""
    try:
        import akshare as ak
        print(f"✅ AKShare Import successful, version: {ak.__version__}")
        return True
    except ImportError as e:
        print(f"❌ AKShare Import failed: {e}")
        print("💡 Please install AKShare: pip install akshare")
        return False

def check_akshare_utils():
    """Check akshare_utils.py"""
    try:
        from tradingagents.dataflows.akshare_utils import get_akshare_provider
        provider = get_akshare_provider()
        print(f"✅ AKShare The tool module is normal and the connection status is: {provider.connected}")
        return True, provider
    except Exception as e:
        print(f"❌ AKShare Tool module exception: {e}")
        return False, None

def check_data_source_manager():
    """Check the data source manager"""
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager
        manager = DataSourceManager()
        
        available = [s.value for s in manager.available_sources]
        if 'akshare' in available:
            print("✅ AKShare in available data sources")
        else:
            print("⚠️ AKShare Not in available data sources")
        
        return True
    except Exception as e:
        print(f"❌ Data source manager check failed: {e}")
        return False

def test_basic_akshare():
    """Test basic AKShare functionality"""
    try:
        import akshare as ak
        
        # Test to get the stock list
        print("📊 Test to get the stock list...")
        stock_list = ak.stock_info_a_code_name()
        print(f"✅ Get{len(stock_list)}only stocks")
        
        # Test to obtain stock data
        print("📈 Test to obtain stock data...")
        data = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20241201", end_date="20241210", adjust="")
        print(f"✅ Get{len(data)}piece of data")
        
        return True
    except Exception as e:
        print(f"❌ AKShare Basic functional test failed: {e}")
        return False

def main():
    """main check function"""
    print("🔍 AKShare Function quick check")
    print("=" * 40)
    
    results = []
    
    # 1. Check import
    results.append(check_akshare_import())
    
    # 2. Check tool module
    success, provider = check_akshare_utils()
    results.append(success)
    
    # 3. Check the data source manager
    results.append(check_data_source_manager())
    
    # 4. Test basic functionality
    if results[0]:  # If the import is successful
        results.append(test_basic_akshare())
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"\n📊 Check results: {passed}/{total} Item passed")
    
    if passed == total:
        print("🎉 AKShare The functionality is fully functional!")
    else:
        print("⚠️ AKShare There is a problem with the functionality")
    
    return passed == total

if __name__ == "__main__":
    main()
