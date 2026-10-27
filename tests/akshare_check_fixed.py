#!/usr/bin/env python3
"""
Repair version AKShare function check
Add path settings to resolve module import issues
"""

import sys
import os

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def check_akshare_import():
    """Check AKShare import"""
    try:
        import akshare as ak
        print(f"✅ AKShare Import successful, version: {ak.__version__}")
        return True
    except ImportError as e:
        print(f"❌ AKShare Import failed: {e}")
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
        import traceback
        traceback.print_exc()
        return False, None

def check_data_source_manager():
    """Check the data source manager"""
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager, ChinaDataSource
        
        # Check AKShare enumeration
        akshare_enum = ChinaDataSource.AKSHARE
        print(f"✅ AKShare enumeration: {akshare_enum.value}")
        
        # Initialization manager
        manager = DataSourceManager()
        
        # Check available data sources
        available = [s.value for s in manager.available_sources]
        if 'akshare' in available:
            print("✅ AKShare in available data sources")
        else:
            print("⚠️ AKShare Not in available data sources")
        
        return True, manager
    except Exception as e:
        print(f"❌ Data source manager check failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def test_akshare_adapter():
    """Test the AKShare adapter"""
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager
        
        manager = DataSourceManager()
        
        # Get the AKShare adapter
        akshare_adapter = manager._get_akshare_adapter()
        
        if akshare_adapter is not None:
            print("✅ AKShare Adapter obtained successfully")
            
            # Test to obtain stock data
            test_data = akshare_adapter.get_stock_data("000001", "2024-12-01", "2024-12-10")
            if test_data is not None and not test_data.empty:
                print(f"✅ AKShare The adapter data was obtained successfully,{len(test_data)}records")
                return True
            else:
                print("❌ AKShare Adapter data acquisition failed")
                return False
        else:
            print("❌ AKShare Adapter acquisition failed")
            return False
            
    except Exception as e:
        print(f"❌ AKShare Adapter test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_source_switching():
    """Test data source switching"""
    try:
        from tradingagents.dataflows.interface import switch_china_data_source
        
        # switch to AKShare
        result = switch_china_data_source("akshare")
        print(f"Data source switching results: {result}")
        
        if "success" in result or "✅" in result or "akshare" in result.lower():
            print("✅ Data source switched to AKShare successfully")
            return True
        else:
            print("❌ Failed to switch data source to AKShare")
            return False
            
    except Exception as e:
        print(f"❌ Data source switching test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_unified_interface():
    """Test unified data interface"""
    try:
        from tradingagents.dataflows.interface import get_china_stock_data_unified, switch_china_data_source
        
        # First switch to AKShare
        switch_china_data_source("akshare")
        
        # Test to get data
        data = get_china_stock_data_unified("000001", "2024-12-01", "2024-12-10")
        
        if data and len(data) > 100:  # Assume that the data returned is string format
            print("✅ Unified data interface test successful")
            print(f"   Data length: {len(data)} character")
            return True
        else:
            print("❌ Unified data interface test failed")
            print(f"   Return data: {data}")
            return False
            
    except Exception as e:
        print(f"❌ Unified data interface test failed: {e}")
        import traceback
        traceback.print_exc()
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
    print("🔍 AKShare Functional integrity check (repaired version)")
    print("=" * 50)
    print(f"Project root directory: {project_root}")
    print(f"Python path: {sys.path[0]}")
    print("=" * 50)
    
    test_results = {}
    
    # 1. Basic AKShare functionality
    print("\n1️⃣ Basic AKShare functional testing")
    test_results['basic_akshare'] = test_basic_akshare()
    
    # 2. AKShare tool module
    print("\n2️⃣ AKShare Tool module testing")
    success, provider = check_akshare_utils()
    test_results['akshare_utils'] = success
    
    # 3. Data source manager
    print("\n3️⃣ Data Source Manager Test")
    success, manager = check_data_source_manager()
    test_results['data_source_manager'] = success
    
    # 4. AKShare adapter
    print("\n4️⃣ AKShare Adapter test")
    test_results['akshare_adapter'] = test_akshare_adapter()
    
    # 5. Data source switching
    print("\n5️⃣ Data source switching test")
    test_results['data_source_switching'] = test_data_source_switching()
    
    # 6. unified data interface
    print("\n6️⃣ Unified data interface testing")
    test_results['unified_interface'] = test_unified_interface()
    
    # Summary results
    print(f"\n📊 AKShare Functional check summary")
    print("=" * 50)
    
    passed = sum(test_results.values())
    total = len(test_results)
    
    for test_name, result in test_results.items():
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name:25} {status}")
    
    print(f"\n🎯 Overall results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 AKShare The functionality is fully functional!")
        print("💡 Duplicate AKShare branches can be safely removed")
    elif passed >= total * 0.7:
        print("⚠️ AKShare The functionality is basically usable, but there are some issues")
        print("💡 It is recommended to fix the problem before deleting the duplicate branch.")
    else:
        print("❌ AKShare Serious problem with functionality")
        print("💡 It is not recommended to delete the AKShare branch, the problem needs to be fixed first")
    
    return passed >= total * 0.7

if __name__ == "__main__":
    success = main()
    
    print(f"\n🎯 Branch management suggestions:")
    if success:
        print("✅ AKShare The function is basically normal. You can consider deleting duplicate branches.")
        print("   - feature/akshare-integration")
        print("   - feature/akshare-integration-clean")
        print("   - Keep feature/tushare-integration (contains full functionality)")
    else:
        print("⚠️ It is recommended to fix the AKShare function problem first, and then consider branch cleaning.")
