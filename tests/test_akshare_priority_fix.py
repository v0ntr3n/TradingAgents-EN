#!/usr/bin/env python3
"""
Test AKShare data source priority fix
Verify that AKShare has been set as the first priority data source
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_default_data_source():
    """Test default data source settings"""
    print("🔧 Test default data source settings")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager, ChinaDataSource
        
        # Create data source manager
        manager = DataSourceManager()
        
        print(f"📊 Default data source: {manager.default_source.value}")
        print(f"📊 Current data source: {manager.current_source.value}")
        print(f"📊 Available data sources: {[s.value for s in manager.available_sources]}")
        
        # Verify that the default data source is AKShare
        if manager.default_source == ChinaDataSource.AKSHARE:
            print("✅ The default data source is correctly set to AKShare")
            return True
        else:
            print(f"❌ Default data source error: expected akshare, actual{manager.default_source.value}")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_fallback_priority():
    """Test alternative data source priorities"""
    print("\n🔧 Test alternative data source priorities")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager, ChinaDataSource
        
        manager = DataSourceManager()
        
        # Simulate current data source failure and test alternate data source sequence
        print("📊 Simulation data source failed, check backup data source priority...")
        
        # Check the _try_fallback_sources method fallback_order
        # Here we verify by checking the source code
        import inspect
        source_code = inspect.getsource(manager._try_fallback_sources)
        
        if "ChinaDataSource.AKSHARE" in source_code:
            # Check if AKShare is before Tushare
            akshare_pos = source_code.find("ChinaDataSource.AKSHARE")
            tushare_pos = source_code.find("ChinaDataSource.TUSHARE")
            
            if akshare_pos < tushare_pos and akshare_pos != -1:
                print("✅ Alternate data source priority is correct: AKShare > Tushare")
                return True
            else:
                print("❌ Alternate data source priority error: AKShare Should be before Tushare")
                return False
        else:
            print("❌ Alternate data source configuration not found AKShare")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_environment_variable_override():
    """Test environment variable coverage"""
    print("\n🔧 Test environment variable coverage")
    print("=" * 60)
    
    try:
        # Save original environment variables
        original_env = os.getenv('DEFAULT_CHINA_DATA_SOURCE')
        
        # The test is set to tushare
        os.environ['DEFAULT_CHINA_DATA_SOURCE'] = 'tushare'
        
        from tradingagents.dataflows.data_source_manager import DataSourceManager, ChinaDataSource
        
        # Re-import to get new environment variables
        import importlib
        import tradingagents.dataflows.data_source_manager as dsm
        importlib.reload(dsm)
        
        manager = dsm.DataSourceManager()
        
        if manager.default_source == ChinaDataSource.TUSHARE:
            print("✅ Environment variable coverage function is normal")
            result = True
        else:
            print(f"❌ Environment variable override failed: expected tushare, actual{manager.default_source.value}")
            result = False
        
        # Restore original environment variables
        if original_env:
            os.environ['DEFAULT_CHINA_DATA_SOURCE'] = original_env
        else:
            os.environ.pop('DEFAULT_CHINA_DATA_SOURCE', None)
        
        return result
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_akshare_availability():
    """Test AKShare usability"""
    print("\n🔧 Test AKShare usability")
    print("=" * 60)
    
    try:
        import akshare as ak
        print(f"✅ AKShare Library installed: v{ak.__version__}")
        
        # Simple test AKShare function
        print("📊 Test AKShare basic functions...")
        
        # The API is not actually called here, only the import is tested.
        from tradingagents.dataflows.akshare_utils import get_china_stock_data_akshare
        print("✅ AKShare Tool function imported successfully")
        
        return True
        
    except ImportError:
        print("❌ AKShare Library not installed")
        return False
    except Exception as e:
        print(f"❌ AKShare test failed: {e}")
        return False

def test_data_source_switching():
    """Test data source switching function"""
    print("\n🔧 Test data source switching function")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager, ChinaDataSource
        
        manager = DataSourceManager()
        original_source = manager.current_source
        
        print(f"📊 original data source: {original_source.value}")
        
        # Test switching to different data sources
        test_sources = [ChinaDataSource.TUSHARE, ChinaDataSource.BAOSTOCK]
        
        for source in test_sources:
            if source in manager.available_sources:
                success = manager.set_current_source(source)
                if success:
                    print(f"✅ Successfully switched to: {source.value}")
                    current = manager.get_current_source()
                    if current == source:
                        print(f"✅ Confirm current data source: {current.value}")
                    else:
                        print(f"❌ Data source switching verification failed")
                        return False
                else:
                    print(f"❌ switch to{source.value}failed")
                    return False
            else:
                print(f"⚠️ data source{source.value}Not available, skip test")
        
        # Restore original data source
        manager.set_current_source(original_source)
        print(f"📊 Restore original data source: {original_source.value}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🧪 AKShare Data source priority repair verification")
    print("=" * 80)
    
    tests = [
        ("Default data source settings", test_default_data_source),
        ("Alternate data source priority", test_fallback_priority),
        ("Environment variable override", test_environment_variable_override),
        ("AKShare Availability", test_akshare_availability),
        ("Data source switching function", test_data_source_switching),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n🔍 Execute tests: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ test{test_name}Abnormal: {e}")
            results.append((test_name, False))
    
    # Summary results
    print("\n" + "=" * 80)
    print("📊 Summary of test results:")
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall results: {passed}/{total} Test passed")
    
    if passed == total:
        print("🎉 All tests passed! AKShare data source priority repaired successfully!")
        return True
    else:
        print("⚠️ Some tests failed and require further inspection.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
