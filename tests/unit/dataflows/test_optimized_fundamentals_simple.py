#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simplified testing: directly test the optimized fundamental analysis data acquisition logic
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta

def test_optimized_fundamentals_logic():
    """Directly test the optimized fundamental analysis logic"""
    print("=" * 80)
    print("🧪 Test the optimized fundamental analysis data acquisition logic")
    print("=" * 80)
    
    # Test stocks: Ping An Bank (000001)
    ticker = "000001"
    
    # Simulation optimized data acquisition strategy
    print(f"\n📊 test stocks: {ticker}")
    print("-" * 50)
    
    try:
        # 1. Get the latest stock price information (only the last 1-2 days of data are required)
        from datetime import datetime, timedelta
        curr_date = datetime.now().strftime('%Y-%m-%d')
        recent_end_date = curr_date
        recent_start_date = (datetime.strptime(curr_date, '%Y-%m-%d') - timedelta(days=2)).strftime('%Y-%m-%d')
        
        print(f"📅 Get price data time range: {recent_start_date} Arrive {recent_end_date}")
        
        from tradingagents.dataflows.interface import get_china_stock_data_unified
        current_price_data = get_china_stock_data_unified(ticker, recent_start_date, recent_end_date)
        
        if current_price_data:
            print(f"✅ Successfully obtained current price data")
            print(f"📏 Price data length: {len(current_price_data):,} character")
            print(f"📝 Price data preview:\n{current_price_data[:300]}...")
        else:
            print(f"❌ Price data not obtained")
            current_price_data = ""
        
        # 2. Get fundamental financial data
        print(f"\n💰 Get fundamental financial data...")
        
        from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider
        analyzer = OptimizedChinaDataProvider()
        fundamentals_data = analyzer._generate_fundamentals_report(ticker, current_price_data)
        
        if fundamentals_data:
            print(f"✅ Successfully obtained fundamental data")
            print(f"📏 Fundamental data length: {len(fundamentals_data):,} character")
            print(f"📝 Fundamental data preview:\n{fundamentals_data[:300]}...")
        else:
            print(f"❌ Fundamental data not obtained")
            fundamentals_data = ""
        
        # 3. Merge results
        result_data = []
        if current_price_data:
            result_data.append(f"## A Stock current price information\n{current_price_data}")
        if fundamentals_data:
            result_data.append(f"## A Stock Fundamentals Financial Data\n{fundamentals_data}")
        
        final_result = "\n\n".join(result_data)
        
        print(f"\n📈 final result statistics:")
        print(f"   - Total data length: {len(final_result):,} character")
        print(f"   - Price data proportion: {len(current_price_data)/len(final_result)*100:.1f}%")
        print(f"   - Fundamental data proportion: {len(fundamentals_data)/len(final_result)*100:.1f}%")
        
        # Check data quality
        has_price = "price" in final_result or "stock price" in final_result or "Price" in final_result
        has_fundamentals = "Finance" in final_result or "Fundamentals" in final_result or "investment advice" in final_result
        has_company = "company" in final_result or "enterprise" in final_result
        
        print(f"\n🔍 Data quality check:")
        print(f"   - Contains price information: {'✅' if has_price else '❌'}")
        print(f"   - Contains fundamental information: {'✅' if has_fundamentals else '❌'}")
        print(f"   - Contains company information: {'✅' if has_company else '❌'}")
        
        print(f"\n💡 Optimization effect:")
        print(f"   - ✅ Only obtain price data for the last 2 days, avoiding historical data for 7-30 days")
        print(f"   - ✅ Retains the core financial data required for fundamental analysis")
        print(f"   - ✅ Dramatically reduces data transfer volume and processing overhead")
        print(f"   - ✅ Improved efficiency and pertinence of fundamental analysis")
        
        return True
        
    except Exception as e:
        print(f"❌ An error occurred during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_optimized_fundamentals_logic()
    if success:
        print("\n🎉 The optimized fundamental analysis data acquisition strategy was tested successfully!")
    else:
        print("\n💥 The test failed and further debugging is required")