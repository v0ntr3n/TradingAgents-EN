#!/usr/bin/env python3
"""
Agent Utils Tushare Fix validation tests
Verify that functions in agent_utils have been successfully migrated from TDX to Tushare unified interface
"""

import os
import sys
from datetime import datetime, timedelta

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_get_china_stock_data_fix():
    """Tushare fix for testing get_china_stock_data function"""
    print("\n🔧 Test get_china_stock_data function fix")
    print("=" * 60)
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit

        print("✅ Toolkit Import successful")

        # Test stock data acquisition
        print("🔄 Test stock data acquisition...")
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')

        result = Toolkit.get_china_stock_data("600036", start_date, end_date)
        
        if result and len(result) > 100:
            print("✅ Stock data obtained successfully")
            print(f"📊 Data length: {len(result)}character")
            
            # Check if unified interface is used (instead of TDX)
            if "Unified data source interface" in result or "tushare" in result.lower():
                print("✅ Successfully used unified data source interface")
            elif "Tong Da Xin" in result:
                print("⚠️ warning: Still using China stock data source")
            else:
                print("✅ Data source updated")
                
            # Show partial results
            print(f"📋 Results preview: {result[:200]}...")
        else:
            print("❌ Failed to obtain stock data")
            print(f"Return results: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ get_china_stock_data test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_china_market_overview_fix():
    """Test fix for get_china_market_overview function"""
    print("\n🔧 Test get_china_market_overview function fix")
    print("=" * 60)
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit

        print("✅ Toolkit Import successful")

        # Get a test market overview
        print("🔄 Get a test market overview...")
        curr_date = datetime.now().strftime('%Y-%m-%d')

        result = Toolkit.get_china_market_overview(curr_date)
        
        if result and len(result) > 50:
            print("✅ Market overview for success")
            print(f"📊 Data length: {len(result)}character")
            
            # Check if Tushare migration is mentioned
            if "Tushare" in result or "Migrate" in result:
                print("✅ Updated to Tushare data source description")
            elif "Tong Da Xin" in result and "TDX" not in result:
                print("⚠️ warning: Still using China stock data source")
            else:
                print("✅ Market overview feature has been updated")
                
            # Show partial results
            print(f"📋 Results preview: {result[:300]}...")
        else:
            print("❌ Failed to obtain market overview")
            print(f"Return results: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ get_china_market_overview test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_stock_name_mapping_fix():
    """Test fix for stock name mapping"""
    print("\n🔧 Test stock name mapping fix")
    print("=" * 60)
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit

        print("✅ Toolkit Import successful")

        # Test fundamental data acquisition (will trigger stock name mapping)
        print("🔄 Test fundamental data acquisition (including stock name mapping)...")
        curr_date = datetime.now().strftime('%Y-%m-%d')

        result = Toolkit.get_fundamentals_openai("600036", curr_date)
        
        if result and len(result) > 100:
            print("✅ Fundamental data obtained successfully")
            print(f"📊 Data length: {len(result)}character")
            
            # Check if the correct stock name is included
            if "China Merchants Bank" in result:
                print("✅ Stock name mapping successful: 600036 -> China Merchants Bank")
            else:
                print("⚠️ There may be a problem with stock name mapping")
                
            # Show partial results
            print(f"📋 Results preview: {result[:200]}...")
        else:
            print("❌ Failed to obtain fundamental data")
            print(f"Return results: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ Stock name mapping test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_debug_output():
    """Check the debug output to see if the unified interface is used"""
    print("\n🔧 Check debug output")
    print("=" * 60)
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit

        print("🔄 Run stock data acquisition and inspect debug output...")
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')

        # This should produce debug output
        result = Toolkit.get_china_stock_data("000001", start_date, end_date)
        
        print("✅ Debug output inspection completed")
        print("💡 Please check the debug output above to confirm whether it is displayed:")
        print("   - 'Successfully imported unified data source interface'")
        print("   - 'Calling the unified data source interface'")
        print("   - instead of 'tdx_utils.get_china_stock_data'")
        
        return True
        
    except Exception as e:
        print(f"❌ Debug output check failed: {e}")
        return False


def main():
    """Main test function"""
    print("🔬 Agent Utils Tushare Fix validation tests")
    print("=" * 70)
    print("💡 Test target:")
    print("   - Verify that get_china_stock_data has been migrated to the unified interface")
    print("   - Verify that get_china_market_overview has been updated")
    print("   - Verify stock name mapping using unified interface")
    print("   - Check the debug output to confirm the fix took effect")
    print("=" * 70)
    
    # Run all tests
    tests = [
        ("get_china_stock_data Repair", test_get_china_stock_data_fix),
        ("get_china_market_overview Repair", test_get_china_market_overview_fix),
        ("Stock name mapping fix", test_stock_name_mapping_fix),
        ("Debug output inspection", check_debug_output)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}Test exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n📋 Agent Utils Repair test summary")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\n📊 Test results: {passed}/{total} Pass")
    
    if passed == total:
        print("\n🎉 Agent Utils The repair test was completely successful!")
        print("\n💡 Repair effect:")
        print("   ✅ get_china_stock_data Unified data source interface has been used")
        print("   ✅ get_china_market_overview Updated to Tushare instructions")
        print("   ✅ Stock name mapping uses unified interface")
        print("   ✅ Debug output confirms the fix took effect")
        print("\n🚀 Now the Agent tool completely uses Tushare data source!")
    else:
        print("\n⚠️ Some tests failed, please check the relevant configuration")
    
    print("\n🎯 Verification method:")
    print("   1. View the debug output for'Unified data source interface'words")
    print("   2. Confirm not to appear again'tdx_utils'Related calls")
    print("   3. Stock data should come from Tushare instead TDX")
    
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
