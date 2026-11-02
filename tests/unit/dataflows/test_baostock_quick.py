#!/usr/bin/env python3
"""
Quickly test the BaoStock data source
"""

import sys
import os

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def test_baostock_import():
    """Test BaoStock import"""
    print("🔍 Test BaoStock import...")
    try:
        import baostock as bs
        print(f"✅ BaoStock Import successful")
        print(f"   version: {bs.__version__}")
        return True
    except ImportError as e:
        print(f"❌ BaoStock Import failed: {e}")
        return False

def test_baostock_connection():
    """Test BaoStock connection"""
    print("\n🔍 Test BaoStock connection...")
    try:
        import baostock as bs
        
        # Log in to the system
        lg = bs.login()
        if lg.error_code != '0':
            print(f"❌ BaoStock Login failed: {lg.error_msg}")
            return False
        
        print(f"✅ BaoStock Login successful")
        
        # Test to get data
        rs = bs.query_history_k_data_plus(
            "sz.000001",  # Ping An Bank
            "date,code,open,high,low,close,volume",
            start_date='2025-07-01',
            end_date='2025-07-12',
            frequency="d"
        )
        
        if rs.error_code != '0':
            print(f"❌ BaoStock Data acquisition failed: {rs.error_msg}")
            bs.logout()
            return False
        
        # Get data
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        
        print(f"✅ BaoStock Data acquisition successful")
        print(f"   Number of data items: {len(data_list)}")
        if data_list:
            print(f"   latest data: {data_list[-1]}")
        
        # Log out of the system
        bs.logout()
        return True
        
    except Exception as e:
        print(f"❌ BaoStock Connection abnormality: {e}")
        try:
            import baostock as bs
            bs.logout()
        except:
            pass
        return False

def test_data_source_manager():
    """Test the data source manager BaoStock"""
    print("\n🔍 Test the data source manager BaoStock...")
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager
        
        manager = DataSourceManager()
        print(f"✅ Data source manager initialized successfully")
        print(f"   Current data source: {manager.current_source.value}")
        print(f"   Available data sources: {[s.value for s in manager.available_sources]}")
        
        # Check if BaoStock is in available data source
        available_sources = [s.value for s in manager.available_sources]
        if 'baostock' in available_sources:
            print(f"✅ BaoStock Identified as an available data source")
            return True
        else:
            print(f"❌ BaoStock Not recognized as a valid data source")
            return False
            
    except Exception as e:
        print(f"❌ Data source manager test exception: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 BaoStock quick test")
    print("=" * 40)
    
    results = []
    
    # 1. Test import
    import_result = test_baostock_import()
    results.append(('BaoStock import', import_result))
    
    # 2. Test the connection (test only if the import is successful)
    if import_result:
        connection_result = test_baostock_connection()
        results.append(('BaoStock connect', connection_result))
        
        # 3. Test data source manager
        manager_result = test_data_source_manager()
        results.append(('Data source manager', manager_result))
    
    # Statistical results
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\n📊 Test results:")
    print("=" * 40)
    
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name}: {status}")
    
    print(f"\n📈 Overall results: {passed}/{total}")
    
    if passed == total:
        print(f"🎉 BaoStock Configuration completed!")
        print(f"✅ China stock data sources now include:")
        print(f"   1. Tushare (main)")
        print(f"   2. AKShare (Spare)")
        print(f"   3. BaoStock (Historical data backup)")
        print(f"   4. TDX (will be eliminated)")
    else:
        print(f"⚠️ BaoStock There is a problem with the configuration")
        print(f"❌ Please check network connection and library installation")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    
    if success:
        print(f"\n🎯 Next step:")
        print("1. Rerun the full data source test")
        print("2. python tests/test_data_sources_comprehensive.py")
    else:
        print(f"\n🔧 Troubleshooting:")
        print("1. Check network connection")
        print("2. Reinstall: pip install baostock")
        print("3. View BaoStock official documentation")
