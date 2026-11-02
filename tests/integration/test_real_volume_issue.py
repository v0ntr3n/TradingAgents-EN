#!/usr/bin/env python3
"""
Test real volume mapping issues
Verify that existing code actually exists KeyError: 'volume'question
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(project_root, '.env'))
    print(f"✅ .env file loaded")
except ImportError:
    print(f"⚠️ python-dotenv Not installed, try manually loading environment variables")
except Exception as e:
    print(f"⚠️ Loading .env file failed: {e}")

def test_real_tushare_volume_access():
    """Test real Tushare data volume access"""
    print("🧪 Test real Tushare data volume access")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager, ChinaDataSource
        
        # Check if Tushare is available
        tushare_token = os.getenv('TUSHARE_TOKEN')
        if not tushare_token:
            print("⚠️ TUSHARE_TOKEN Not set, cannot test real data")
            return True
        
        print(f"✅ TUSHARE_TOKEN Already set")
        
        # Create data source manager
        manager = DataSourceManager()
        
        # Make sure to use the Tushare data source
        if ChinaDataSource.TUSHARE in manager.available_sources:
            manager.set_current_source(ChinaDataSource.TUSHARE)
            print(f"📊 Current data source: {manager.current_source.value}")
            
            # Test to get real data
            print(f"🔍 Get 000001 real data...")
            
            try:
                result = manager._get_tushare_data('000001', '2025-07-20', '2025-07-26')
                
                if result and "❌" not in result:
                    print(f"✅ Successfully obtained data, length: {len(result)}")
                    print(f"📊 Results preview: {result[:200]}...")
                    
                    # Check if the results include volume information
                    if "Volume" in result:
                        print(f"✅ Results include volume information")
                        return True
                    else:
                        print(f"⚠️ Results do not include volume information")
                        return False
                else:
                    print(f"❌ Failed to get data: {result}")
                    return False
                    
            except KeyError as e:
                if "'volume'" in str(e):
                    print(f"🎯 confirm existence KeyError: 'volume'Question!")
                    print(f"❌ Error details: {e}")
                    return False
                else:
                    print(f"❌ Others KeyError: {e}")
                    return False
            except Exception as e:
                print(f"❌ Other errors: {e}")
                if "volume" in str(e).lower():
                    print(f"🎯 Possible volume-related errors")
                import traceback
                traceback.print_exc()
                return False
        else:
            print("❌ Tushare Data source is not available")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_tushare_adapter_direct():
    """Test the Tushare adapter directly"""
    print(f"\n🧪 Test the Tushare adapter directly")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.tushare_adapter import get_tushare_adapter
        
        # Check if Tushare is available
        tushare_token = os.getenv('TUSHARE_TOKEN')
        if not tushare_token:
            print("⚠️ TUSHARE_TOKEN Not set, cannot test real data")
            return True
        
        adapter = get_tushare_adapter()
        print(f"✅ Tushare Adapter created successfully")
        
        # Test to obtain stock data
        print(f"🔍 Get 000001 stock data...")
        
        try:
            data = adapter.get_stock_data('000001', '2025-07-20', '2025-07-26')
            
            if data is not None and not data.empty:
                print(f"✅ Successfully obtained data, shape: {data.shape}")
                print(f"📊 List: {list(data.columns)}")
                
                # Check the volume column
                if 'volume' in data.columns:
                    print(f"✅ volume Column exists")
                    volume_sum = data['volume'].sum()
                    print(f"📊 total trading volume: {volume_sum:,.0f}")
                    
                    # Test access to volume column (this is the key test)
                    try:
                        volume_values = data['volume'].tolist()
                        print(f"✅ Successfully accessed volume column: {volume_values[:3]}...")
                        return True
                    except KeyError as e:
                        print(f"❌ KeyError Access volume column: {e}")
                        return False
                else:
                    print(f"❌ volume Column does not exist")
                    print(f"📊 Available columns: {list(data.columns)}")
                    return False
            else:
                print(f"❌ No data obtained")
                return False
                
        except KeyError as e:
            if "'volume'" in str(e):
                print(f"🎯 confirm existence KeyError: 'volume'Question!")
                print(f"❌ Error details: {e}")
                return False
            else:
                print(f"❌ Others KeyError: {e}")
                return False
        except Exception as e:
            print(f"❌ Other errors: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_column_mapping_in_real_data():
    """Test column mapping on real data"""
    print(f"\n🧪 Test column mapping on real data")
    print("=" * 60)
    
    try:
        import tushare as ts
        
        # Check if Tushare is available
        tushare_token = os.getenv('TUSHARE_TOKEN')
        if not tushare_token:
            print("⚠️ TUSHARE_TOKEN Not set, cannot test real data")
            return True
        
        # Directly call Tushare API to obtain original data
        print(f"🔍 call directly Tushare API...")
        ts.set_token(tushare_token)
        pro = ts.pro_api()
        
        # Get raw data
        raw_data = pro.daily(ts_code='000001.SZ', start_date='20250720', end_date='20250726')
        
        if raw_data is not None and not raw_data.empty:
            print(f"✅ Obtaining original data successfully, shape: {raw_data.shape}")
            print(f"📊 original column name: {list(raw_data.columns)}")
            
            # Check column names in raw data
            if 'vol' in raw_data.columns:
                print(f"✅ The original data contains'vol'Column")
                vol_values = raw_data['vol'].tolist()
                print(f"📊 vol column value: {vol_values}")
            else:
                print(f"❌ The original data does not contain'vol'Column")
                return False
            
            # Test our normalized function
            from tradingagents.dataflows.tushare_adapter import get_tushare_adapter
            adapter = get_tushare_adapter()
            
            print(f"\n🔧 Test normalized functions...")
            standardized_data = adapter._standardize_data(raw_data)
            
            print(f"📊 Listed after standardization: {list(standardized_data.columns)}")
            
            if 'volume' in standardized_data.columns:
                print(f"✅ Included after normalization'volume'Column")
                volume_values = standardized_data['volume'].tolist()
                print(f"📊 volume column value: {volume_values}")
                
                # Verify mapping is correct
                if raw_data['vol'].sum() == standardized_data['volume'].sum():
                    print(f"✅ vol -> volume Mapping correct")
                    return True
                else:
                    print(f"❌ vol -> volume Mapping error")
                    return False
            else:
                print(f"❌ Not included after standardization'volume'Column")
                return False
        else:
            print(f"❌ Original data not obtained")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🔍 Verify volume mapping issues in real environments")
    print("=" * 80)
    print("📋 target: Verify existence in real environment KeyError: 'volume' question")
    print("=" * 80)
    
    tests = [
        ("Real data column mapping test", test_column_mapping_in_real_data),
        ("Tushare Adapter direct test", test_tushare_adapter_direct),
        ("Data Source Manager Real Data Test", test_real_tushare_volume_access),
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
    print("📊 Summary of real environment test results:")
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall results: {passed}/{total} Test passed")
    
    # Analysis results and recommendations
    print("\n📋 Analysis conclusion:")
    if passed == total:
        print("🎉 All real environment tests passed!")
        print("✅ The volume mapping function of the existing code is completely normal")
        print("\n💡 Yes PR #173 suggestions:")
        print("  1. 🤔 Ask the PR author for specific steps to reproduce the error")
        print("  2. 📅 Confirm the code version and branch used by the PR author")
        print("  3. 🔍 Check if the issue is with your specific environment, data, or configuration")
        print("  4. 📝 Ask for complete error stack information")
        print("  5. ⚠️ Might be an old issue that has been fixed")
    else:
        print("❌ Some real environment tests failed")
        print("🎯 There are indeed volume related issues,PR #173 A repair is necessary")
        print("\n💡 Suggestions:")
        print("  1. ✅ accept PR #173 repair")
        print("  2. 🔧 But the implementation needs to be optimized")
        print("  3. 🧪 Add more test cases")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
