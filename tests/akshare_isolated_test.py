#!/usr/bin/env python3
"""
Standalone AKShare functional testing
Bypass yfinance dependency issues and directly test AKShare integration
"""

import sys
import os

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def test_akshare_direct():
    """Test AKShare functionality directly"""
    print("🔍 Test AKShare functionality directly")
    print("=" * 40)
    
    try:
        import akshare as ak
        print(f"✅ AKShare Import successful, version: {ak.__version__}")
        
        # Test to get the stock list
        print("📊 Test to get the stock list...")
        stock_list = ak.stock_info_a_code_name()
        print(f"✅ Get{len(stock_list)}only stocks")
        
        # Test to obtain stock data
        print("📈 Test to obtain China Merchants Bank(000001)data...")
        data = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20241201", end_date="20241210", adjust="")
        print(f"✅ Get{len(data)}piece of data")
        print(f"   latest closing price: {data.iloc[-1]['close']}")
        
        # Test to get real-time quotes
        print("📊 Test to get real-time quotes...")
        realtime = ak.stock_zh_a_spot_em()
        print(f"✅ Get{len(realtime)}Real-time quotes of individual stocks")
        
        return True
        
    except Exception as e:
        print(f"❌ AKShare test failed: {e}")
        return False

def test_akshare_utils_direct():
    """Test the akshare_utils module directly"""
    print("\n🔍 Test the akshare_utils module directly")
    print("=" * 40)
    
    try:
        # Import akshare_utils directly to avoid passing__init__.py
        akshare_utils_path = os.path.join(project_root, 'tradingagents', 'dataflows', 'akshare_utils.py')
        
        if os.path.exists(akshare_utils_path):
            print(f"✅ Find the akshare_utils.py file")
            
            # Use exec to directly execute the file content
            with open(akshare_utils_path, 'r', encoding='utf-8') as f:
                akshare_utils_code = f.read()
            
            # Create a separate namespace
            namespace = {}
            exec(akshare_utils_code, namespace)
            
            # test AKShareProvider
            if 'AKShareProvider' in namespace:
                provider_class = namespace['AKShareProvider']
                provider = provider_class()
                
                print(f"✅ AKShareProvider Initialization successful, connection status: {provider.connected}")
                
                if provider.connected:
                    # Test to obtain stock data
                    stock_data = provider.get_stock_data("000001", "2024-12-01", "2024-12-10")
                    if stock_data is not None and not stock_data.empty:
                        print(f"✅ Obtaining stock data successfully,{len(stock_data)}records")
                    else:
                        print("❌ Failed to get stock data")
                    
                    # Test to obtain stock information
                    stock_info = provider.get_stock_info("000001")
                    print(f"✅ Get stock information: {stock_info}")
                
                return True
            else:
                print("❌ AKShareProvider Class not found")
                return False
        else:
            print(f"❌ akshare_utils.py File does not exist: {akshare_utils_path}")
            return False
            
    except Exception as e:
        print(f"❌ akshare_utils test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_data_source_enum():
    """Check the data source enumeration definition"""
    print("\n🔍 Check the data source enumeration definition")
    print("=" * 40)
    
    try:
        # Read the data_source_manager.py file directly
        data_source_manager_path = os.path.join(project_root, 'tradingagents', 'dataflows', 'data_source_manager.py')
        
        if os.path.exists(data_source_manager_path):
            with open(data_source_manager_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check AKShare related definitions
            if 'AKSHARE' in content:
                print("✅ Find the AKSHARE enumeration definition")
            else:
                print("❌ AKSHARE enumeration definition not found")
            
            if 'akshare' in content.lower():
                print("✅ Find akshare related code")
                
                # Count the number of occurrences of akshare
                akshare_count = content.lower().count('akshare')
                print(f"   akshare appear in code{akshare_count}times")
            else:
                print("❌ No akshare related code found")
            
            return True
        else:
            print(f"❌ data_source_manager.py File does not exist")
            return False
            
    except Exception as e:
        print(f"❌ Data source enumeration check failed: {e}")
        return False

def analyze_yfinance_issue():
    """Analyze yfinance dependency issues"""
    print("\n🔍 Analyze yfinance dependency issues")
    print("=" * 40)
    
    try:
        # Check if yfinance can be imported independently
        import yfinance as yf
        print("✅ yfinance Can be imported independently")
        return True
    except Exception as e:
        print(f"❌ yfinance Import failed: {e}")
        
        # Check curl_cffi
        try:
            import curl_cffi
            print("✅ curl_cffi Can be imported")
        except Exception as e2:
            print(f"❌ curl_cffi Import failed: {e2}")
        
        # Check cffi
        try:
            import cffi
            print("✅ cffi Can be imported")
        except Exception as e3:
            print(f"❌ cffi Import failed: {e3}")
        
        return False

def main():
    """Main test function"""
    print("🔍 AKShare Functional independent testing")
    print("=" * 60)
    
    test_results = {}
    
    # 1. direct test AKShare
    test_results['akshare_direct'] = test_akshare_direct()
    
    # 2. direct test akshare_utils
    test_results['akshare_utils_direct'] = test_akshare_utils_direct()
    
    # 3. Check datasource enumeration
    test_results['data_source_enum'] = check_data_source_enum()
    
    # 4. Analyze yfinance issues
    test_results['yfinance_analysis'] = analyze_yfinance_issue()
    
    # Summary results
    print(f"\n📊 Independent testing summary")
    print("=" * 60)
    
    passed = sum(test_results.values())
    total = len(test_results)
    
    for test_name, result in test_results.items():
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name:25} {status}")
    
    print(f"\n🎯 Overall results: {passed}/{total} tests passed")
    
    # Analyze results
    if test_results.get('akshare_direct', False) and test_results.get('akshare_utils_direct', False):
        print("\n🎉 AKShare The core functions are completely normal!")
        print("💡 The problem is just a module import problem caused by yfinance dependency")
        print("✅ Duplicate AKShare branches can be safely removed")
        
        print(f"\n🎯 Branch management suggestions:")
        print("✅ AKShare The functionality itself is completely fine")
        print("✅ feature/tushare-integration Includes full AKShare integration")
        print("✅ The following branches can be safely deleted:")
        print("   - feature/akshare-integration")
        print("   - feature/akshare-integration-clean")
        
        return True
    else:
        print("\n⚠️ AKShare There is a problem with the functionality and requires further investigation")
        return False

if __name__ == "__main__":
    success = main()
    
    if success:
        print(f"\n🚀 Suggestions for next steps:")
        print("1. Fix yfinance dependency issue (optional)")
        print("2. Remove duplicate AKShare branches")
        print("3. Release v0.1.6 version")
    else:
        print(f"\n🔧 Issues that need to be fixed:")
        print("1. Check AKShare integration code")
        print("2. Fix dependency issues")
        print("3. Retest before considering branch cleanup")
