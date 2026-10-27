#!/usr/bin/env python3
"""
Stock symbol tracking test script
Specifically used to debug stock code misjudgments in fundamental analysis
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_stock_code_tracking():
    """Test the passage of stock symbols throughout the process"""
    print("\n🔍 Stock symbol tracking test")
    print("=" * 80)
    
    # Test Focus Media 002027
    test_ticker = "002027"
    print(f"📊 Test ticker: {test_ticker} (focus media)")
    
    try:
        # Import necessary modules
        from tradingagents.agents.utils.agent_utils import AgentUtils
        from tradingagents.utils.logging_init import get_logger
        
        # Set the log level to INFO to display trace logs
        logger = get_logger("default")
        logger.setLevel("INFO")
        
        print(f"\n🔧 Start calling the unified fundamental analysis tool...")
        
        # Call the Unified Fundamental Analysis Tool
        result = AgentUtils.get_stock_fundamentals_unified(
            ticker=test_ticker,
            start_date='2025-06-01',
            end_date='2025-07-15',
            curr_date='2025-07-15'
        )
        
        print(f"\n✅ Unified fundamental analysis tool call completed")
        print(f"📊 Return result length: {len(result) if result else 0}")
        
        # Check if the correct stock symbol is included in the results
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

def test_individual_components():
    """Test ticker handling for individual components"""
    print("\n🔧 Test ticker handling for individual components")
    print("=" * 80)
    
    test_ticker = "002027"
    
    try:
        # 1. Test stock market recognition
        print(f"\n1️⃣ Test stock market recognition...")
        from tradingagents.utils.stock_utils import StockUtils
        market_info = StockUtils.get_market_info(test_ticker)
        print(f"   market information: {market_info}")
        
        # 2. Test Tushare code standardization
        print(f"\n2️⃣ Test Tushare code standardization...")
        from tradingagents.dataflows.tushare_utils import get_tushare_provider
        provider = get_tushare_provider()
        if provider:
            normalized = provider._normalize_symbol(test_ticker)
            print(f"   Standardized results: {test_ticker} -> {normalized}")
        
        # 3. Test data source manager
        print(f"\n3️⃣ Test data source manager...")
        from tradingagents.dataflows.data_source_manager import get_china_stock_data_unified
        data_result = get_china_stock_data_unified(test_ticker, "2025-07-01", "2025-07-15")
        print(f"   Data acquisition result length: {len(data_result) if data_result else 0}")
        
        return True
        
    except Exception as e:
        print(f"❌ Component test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Start ticker tracking test")
    
    # test 1: Complete process tracking
    success1 = test_stock_code_tracking()
    
    # test 2: Testing of individual components
    success2 = test_individual_components()
    
    if success1 and success2:
        print("\n✅ All tests passed")
    else:
        print("\n❌ Some tests failed")
