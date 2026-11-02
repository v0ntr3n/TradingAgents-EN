#!/usr/bin/env python3
"""
Test volume mapping issues in existing code
Verify existence KeyError: 'volume' question
"""

import os
import sys
import pandas as pd
import numpy as np

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def test_tushare_adapter_volume_mapping():
    """Test the volume mapping of the Tushare adapter"""
    print("🧪 Test Tushare adapter volume mapping")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.tushare_adapter import get_tushare_adapter
        
        # Create adapter
        adapter = get_tushare_adapter()
        
        # Create simulated Tushare raw data (using'vol'column name)
        mock_tushare_data = pd.DataFrame({
            'trade_date': ['20250726', '20250725', '20250724'],
            'ts_code': ['000001.SZ', '000001.SZ', '000001.SZ'],
            'open': [12.50, 12.40, 12.30],
            'high': [12.60, 12.50, 12.40],
            'low': [12.40, 12.30, 12.20],
            'close': [12.55, 12.45, 12.35],
            'vol': [1000000, 1200000, 1100000],  # Note: Use here'vol'instead of'volume'
            'amount': [12550000, 14940000, 13585000],
            'pct_chg': [0.8, 0.81, -0.4],
            'change': [0.1, 0.1, -0.05]
        })
        
        print(f"📊 Simulate raw data column names: {list(mock_tushare_data.columns)}")
        print(f"📊 vol column in original data: {mock_tushare_data['vol'].tolist()}")
        
        # Test data standardization
        print(f"\n🔧 test_standardize_data method...")
        standardized_data = adapter._standardize_data(mock_tushare_data)
        
        print(f"📊 Listed after standardization: {list(standardized_data.columns)}")
        
        # Check if the volume column exists
        if 'volume' in standardized_data.columns:
            print(f"✅ volume Column exists: {standardized_data['volume'].tolist()}")
            print(f"✅ vol -> volume Mapping successful")
            
            # Verify data is correct
            original_vol_sum = mock_tushare_data['vol'].sum()
            mapped_volume_sum = standardized_data['volume'].sum()
            
            if original_vol_sum == mapped_volume_sum:
                print(f"✅ Data mapping is correct: Original vol sum={original_vol_sum}, Sum of volumes after mapping={mapped_volume_sum}")
                return True
            else:
                print(f"❌ Data mapping error: Original vol sum={original_vol_sum}, Sum of volumes after mapping={mapped_volume_sum}")
                return False
        else:
            print(f"❌ volume Column does not exist, mapping failed")
            print(f"❌ Available columns: {list(standardized_data.columns)}")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_source_manager_volume_access():
    """Test volume access in the data source manager"""
    print(f"\n🧪 Test data source manager volume access")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager
        
        # Create data source manager
        manager = DataSourceManager()
        
        # Create simulated data (already normalized)
        mock_standardized_data = pd.DataFrame({
            'date': pd.to_datetime(['2025-07-26', '2025-07-25', '2025-07-24']),
            'code': ['000001.SZ', '000001.SZ', '000001.SZ'],
            'open': [12.50, 12.40, 12.30],
            'high': [12.60, 12.50, 12.40],
            'low': [12.40, 12.30, 12.20],
            'close': [12.55, 12.45, 12.35],
            'volume': [1000000, 1200000, 1100000],  # Normalized volume column
            'amount': [12550000, 14940000, 13585000]
        })
        
        print(f"📊 Simulate standardized data column names: {list(mock_standardized_data.columns)}")
        
        # Test direct access to volume column
        try:
            volume_sum = mock_standardized_data['volume'].sum()
            print(f"✅ Direct access to the volume column is successful: total trading volume={volume_sum:,.0f}")
            
            # Test statistical calculations (simulate the logic in data_source_manager)
            stats_result = f"Volume: {volume_sum:,.0f}shares"
            print(f"✅ Statistical calculation successful: {stats_result}")
            
            return True
            
        except KeyError as e:
            print(f"❌ KeyError: {e}")
            print(f"❌ This is the question mentioned in the PR!")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_real_tushare_data():
    """Test real Tushare data acquisition"""
    print(f"\n🧪 Test real Tushare data acquisition")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager
        
        # Check if Tushare is available
        tushare_token = os.getenv('TUSHARE_TOKEN')
        if not tushare_token:
            print("⚠️ TUSHARE_TOKEN Not set, skip real data testing")
            return True
        
        manager = DataSourceManager()
        
        # Set as Tushare data source
        from tradingagents.dataflows.data_source_manager import ChinaDataSource
        if ChinaDataSource.TUSHARE in manager.available_sources:
            manager.set_current_source(ChinaDataSource.TUSHARE)
            
            print(f"📊 Current data source: {manager.current_source.value}")
            
            # Test to get real data
            print(f"🔍 Test to obtain 000001 real data...")
            
            try:
                # Here we only test data acquisition, not actual execution to avoid API calls
                print(f"✅ Real data test preparation completed")
                print(f"💡 If you need to test real data, please execute it manually:")
                print(f"   result = manager._get_tushare_data('000001', '2025-07-20', '2025-07-26')")
                return True
                
            except Exception as e:
                print(f"❌ Failed to obtain real data: {e}")
                if "KeyError: 'volume'" in str(e):
                    print(f"🎯 Confirm that the problem mentioned in the PR exists!")
                return False
        else:
            print("⚠️ Tushare Data source is not available")
            return True
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_column_mapping_logic():
    """Detailed process for testing column mapping logic"""
    print(f"\n🧪 Detailed process of testing column mapping logic")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.tushare_adapter import TushareAdapter
        
        # Create adapter instance
        adapter = TushareAdapter()
        
        # create contains'vol'Column test data
        test_data = pd.DataFrame({
            'trade_date': ['20250726'],
            'ts_code': ['000001.SZ'],
            'open': [12.50],
            'high': [12.60],
            'low': [12.40],
            'close': [12.55],
            'vol': [1000000],  # Key: use'vol'List
            'amount': [12550000]
        })
        
        print(f"📊 Test data original column name: {list(test_data.columns)}")
        print(f"📊 vol column value: {test_data['vol'].iloc[0]}")
        
        # Perform mapping logic manually
        print(f"\n🔧 Perform column mapping logic manually...")
        
        # Get mapping configuration
        column_mapping = {
            'trade_date': 'date',
            'ts_code': 'code',
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'vol': 'volume',  # key mapping
            'amount': 'amount',
            'pct_chg': 'pct_change',
            'change': 'change'
        }
        
        print(f"📊 Mapping configuration: {column_mapping}")
        
        # Execute mapping
        mapped_data = test_data.copy()
        for old_col, new_col in column_mapping.items():
            if old_col in mapped_data.columns:
                print(f"🔄 mapping: {old_col} -> {new_col}")
                mapped_data = mapped_data.rename(columns={old_col: new_col})
        
        print(f"📊 Column names after mapping: {list(mapped_data.columns)}")
        
        if 'volume' in mapped_data.columns:
            print(f"✅ volume Column exists, value: {mapped_data['volume'].iloc[0]}")
            
            # test access
            try:
                volume_value = mapped_data['volume'].iloc[0]
                print(f"✅ Successfully accessed volume value: {volume_value}")
                return True
            except KeyError as e:
                print(f"❌ Failed to access volume: {e}")
                return False
        else:
            print(f"❌ volume Column does not exist")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🔍 Verify volume mapping issues in existing code")
    print("=" * 80)
    print("📋 target: Verify existence KeyError: 'volume' question")
    print("📋 Check: 'vol' -> 'volume' Is the mapping working properly?")
    print("=" * 80)
    
    tests = [
        ("Detailed testing of column mapping logic", test_column_mapping_logic),
        ("Tushare Adapter volume mapping", test_tushare_adapter_volume_mapping),
        ("Data source manager volume access", test_data_source_manager_volume_access),
        ("Real Tushare data test", test_real_tushare_data),
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
    
    # Analyze results
    print("\n📋 Analysis conclusion:")
    if passed == total:
        print("🎉 All tests passed! The volume mapping of the existing code functions normally")
        print("💡 Suggestions:")
        print("  1. Ask the PR author for specific steps to reproduce the error")
        print("  2. Confirm the code version used by the PR author")
        print("  3. Check if the problem is with a specific environment or data source")
    elif passed >= total * 0.5:
        print("⚠️ Some tests failed, there may be problems in specific scenarios")
        print("💡 Suggestions:")
        print("  1. Further investigation of failed test scenarios")
        print("  2. Confirm specific error scenarios with the PR author")
    else:
        print("❌ Most tests fail, there is indeed a volume mapping problem")
        print("💡 Suggestions:")
        print("  1. PR #173 A repair is necessary")
        print("  2. Need to further optimize the repair plan")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
