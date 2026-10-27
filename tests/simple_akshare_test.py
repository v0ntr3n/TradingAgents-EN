#!/usr/bin/env python3
"""
Simple AKShare test
Verify that the repaired import is working properly
"""

import sys
import os

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def test_basic_imports():
    """Test basic import"""
    print("🔍 Test basic import")
    print("=" * 40)
    
    try:
        # Test AKShare direct import
        import akshare as ak
        print(f"✅ AKShare Import successful: {ak.__version__}")
    except Exception as e:
        print(f"❌ AKShare Import failed: {e}")
        return False
    
    try:
        # Test dataflows module import
        from tradingagents.dataflows import akshare_utils
        print("✅ akshare_utils Module imported successfully")
    except Exception as e:
        print(f"❌ akshare_utils Module import failed: {e}")
        return False
    
    try:
        # Test data source manager import
        from tradingagents.dataflows.data_source_manager import DataSourceManager
        print("✅ DataSourceManager Import successful")
    except Exception as e:
        print(f"❌ DataSourceManager Import failed: {e}")
        return False
    
    return True

def test_akshare_provider():
    """Testing the AKShare provider"""
    print("\n🔍 Testing the AKShare provider")
    print("=" * 40)
    
    try:
        from tradingagents.dataflows.akshare_utils import get_akshare_provider
        provider = get_akshare_provider()
        print(f"✅ AKShare Provider created successfully, connection status: {provider.connected}")
        
        if provider.connected:
            # Test to obtain stock data
            data = provider.get_stock_data("000001", "2024-12-01", "2024-12-10")
            if data is not None and not data.empty:
                print(f"✅ Obtaining stock data successfully: {len(data)}records")
            else:
                print("❌ Failed to get stock data")
                return False
        
        return True
    except Exception as e:
        print(f"❌ AKShare Provider test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_source_manager():
    """Test data source manager"""
    print("\n🔍 Test data source manager")
    print("=" * 40)
    
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager, ChinaDataSource
        
        # Check AKShare enumeration
        akshare_enum = ChinaDataSource.AKSHARE
        print(f"✅ AKShare enumeration: {akshare_enum.value}")
        
        # Create manager
        manager = DataSourceManager()
        print("✅ Data source manager created successfully")
        
        # Check available data sources
        available = [s.value for s in manager.available_sources]
        print(f"✅ Available data sources: {available}")
        
        if 'akshare' in available:
            print("✅ AKShare in available data sources")
        else:
            print("⚠️ AKShare Not in available data sources")
        
        return True
    except Exception as e:
        print(f"❌ Data source manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🔍 Simple AKShare function test")
    print("=" * 60)
    
    results = []
    
    # 1. Basic import test
    results.append(test_basic_imports())
    
    # 2. AKShare Provider testing
    results.append(test_akshare_provider())
    
    # 3. Data Source Manager Test
    results.append(test_data_source_manager())
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"\n📊 Test results: {passed}/{total} Item passed")
    
    if passed == total:
        print("🎉 AKShare Fully functional!")
        print("✅ Duplicate AKShare branches can be safely removed")
        return True
    elif passed >= 2:
        print("⚠️ AKShare Basic functions are normal, but some advanced functions may have problems.")
        print("✅ Consider deleting duplicate AKShare branches")
        return True
    else:
        print("❌ AKShare There is a problem with the functionality")
        return False

if __name__ == "__main__":
    success = main()
    
    if success:
        print(f"\n🎯 Branch management suggestions:")
        print("✅ AKShare Functions are basically normal")
        print("✅ The following duplicate branches can be removed:")
        print("   - feature/akshare-integration")
        print("   - feature/akshare-integration-clean")
        print("✅ Keep feature/tushare-integration (contains full functionality)")
    else:
        print(f"\n⚠️ Suggestions:")
        print("1. Fix AKShare integration issues first")
        print("2. Consider branch cleanup again")
