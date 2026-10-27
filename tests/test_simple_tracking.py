#!/usr/bin/env python3
"""
Simple ticker tracking test
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_data_flow():
    """Testing ticker symbol processing in data streams"""
    print("\n🔍 Dataflow ticker tracking test")
    print("=" * 80)
    
    # Test Focus Media 002027
    test_ticker = "002027"
    print(f"📊 Test ticker: {test_ticker} (focus media)")
    
    try:
        # Set log level
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("default")
        logger.setLevel("INFO")
        
        print(f"\n🔧 Test data source manager...")
        
        # Test data source manager
        from tradingagents.dataflows.data_source_manager import get_china_stock_data_unified
        
        result = get_china_stock_data_unified(test_ticker, "2025-07-01", "2025-07-15")
        
        print(f"\n✅ Data source manager call completed")
        print(f"📊 Return result length: {len(result) if result else 0}")
        
        # Check the stock symbol in the results
        if result:
            print(f"\n🔍 Check the stock symbol in the results...")
            if "002027" in result:
                print("✅ The results contain the correct ticker symbol 002027")
            else:
                print("❌ Results do not contain the correct stock symbol 002027")
                
            if "002021" in result:
                print("⚠️ Results contain wrong stock symbol 002021")
            else:
                print("✅ Results do not contain incorrect stock symbols 002021")
                
            # Display the first 500 characters of the result
            print(f"\n📄 The first 500 characters of the result:")
            print("-" * 60)
            print(result[:500])
            print("-" * 60)
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_tushare_direct():
    """Directly test the Tushare interface"""
    print("\n🔧 Directly test the Tushare interface")
    print("=" * 80)
    
    test_ticker = "002027"
    
    try:
        # Set log level
        from tradingagents.utils.logging_init import get_logger
        logger.setLevel("INFO")
        
        print(f"\n🔧 Test Tushare interface...")
        
        # Test Tushare interface
        from tradingagents.dataflows.interface import get_china_stock_data_tushare
        
        result = get_china_stock_data_tushare(test_ticker, "2025-07-01", "2025-07-15")
        
        print(f"\n✅ Tushare Interface call completed")
        print(f"📊 Return result length: {len(result) if result else 0}")
        
        # Check the stock symbol in the results
        if result:
            print(f"\n🔍 Check the stock symbol in the results...")
            if "002027" in result:
                print("✅ The results contain the correct ticker symbol 002027")
            else:
                print("❌ Results do not contain the correct stock symbol 002027")
                
            if "002021" in result:
                print("⚠️ Results contain wrong stock symbol 002021")
            else:
                print("✅ Results do not contain incorrect stock symbols 002021")
                
            # Display the first 500 characters of the result
            print(f"\n📄 The first 500 characters of the result:")
            print("-" * 60)
            print(result[:500])
            print("-" * 60)
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_tushare_provider():
    """Test the Tushare provider"""
    print("\n🔧 Test the Tushare provider")
    print("=" * 80)
    
    test_ticker = "002027"
    
    try:
        # Set log level
        from tradingagents.utils.logging_init import get_logger
        logger.setLevel("INFO")
        
        print(f"\n🔧 Test the Tushare provider...")
        
        # Test the Tushare provider
        from tradingagents.dataflows.tushare_utils import get_tushare_provider
        
        provider = get_tushare_provider()
        
        if provider and provider.connected:
            print("✅ Tushare Provider connection successful")
            
            # Test stock information acquisition
            stock_info = provider.get_stock_info(test_ticker)
            print(f"📊 stock information: {stock_info}")
            
            # Test stock data acquisition
            stock_data = provider.get_stock_daily(test_ticker, "2025-07-01", "2025-07-15")
            print(f"📊 Stock data shape: {stock_data.shape if stock_data is not None and hasattr(stock_data, 'shape') else 'None'}")
            
            if stock_data is not None and not stock_data.empty:
                print(f"📊 Stock data column: {list(stock_data.columns)}")
                if 'ts_code' in stock_data.columns:
                    unique_codes = stock_data['ts_code'].unique()
                    print(f"📊 in data ts_code: {unique_codes}")
        else:
            print("❌ Tushare Provider connection failed")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Start a simple ticker tracking test")
    
    # test 1: Tushare provider
    success1 = test_tushare_provider()
    
    # test 2: Tushare interface
    success2 = test_tushare_direct()
    
    # test 3: Data source manager
    success3 = test_data_flow()
    
    if success1 and success2 and success3:
        print("\n✅ All tests passed")
    else:
        print("\n❌ Some tests failed")
