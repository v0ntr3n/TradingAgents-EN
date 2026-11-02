#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Raw data display test script
Directly call the underlying data interface to display original financial data
"""

import sys
import os
import json
from datetime import datetime, timedelta

# Add project root directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_raw_data_display():
    """Test and display raw fundamental data"""
    
    print("=" * 80)
    print("📊 Raw fundamental data display test")
    print("=" * 80)
    
    # Test parameters
    ticker = "000001"  # Ping An Bank
    curr_date = datetime.now()
    start_date = curr_date - timedelta(days=2)  # After optimization, only 2 days of data are obtained
    end_date = curr_date
    
    print(f"🎯 test stocks: {ticker}")
    print(f"📅 data range: {start_date.strftime('%Y-%m-%d')} Arrive {end_date.strftime('%Y-%m-%d')}")
    print(f"⏰ current time: {curr_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    try:
        # Directly call the underlying data interface
        from tradingagents.dataflows.interface import get_china_stock_data_unified
        
        print("🔄 Retrieving raw stock data...")
        print("-" * 60)
        
        # Call the underlying data interface
        raw_data = get_china_stock_data_unified(
            ticker,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )
        
        print("✅ Original data obtained successfully!")
        print()
        
        # Display basic information of raw data
        print("📋 Basic information of original data:")
        print(f"   - data type: {type(raw_data)}")
        print(f"   - Data length: {len(str(raw_data))} character")
        print()
        
        # Full display of original data content
        print("📄 Complete raw data content:")
        print("=" * 80)
        
        if isinstance(raw_data, str):
            print("🔤 String format raw data:")
            print(raw_data)
        elif isinstance(raw_data, dict):
            print("📚 Dictionary format raw data:")
            print(json.dumps(raw_data, ensure_ascii=False, indent=2))
        elif isinstance(raw_data, list):
            print("📝 Raw data in list format:")
            for i, item in enumerate(raw_data):
                print(f"📌 Project {i+1}:")
                if isinstance(item, (dict, list)):
                    print(json.dumps(item, ensure_ascii=False, indent=2))
                else:
                    print(f"   {item}")
                print("-" * 40)
        else:
            print("🔍 Raw data in other formats:")
            print(repr(raw_data))
        
        print("=" * 80)
        
        # Data statistics
        print("\n📊 Raw data statistics:")
        print(f"   - Total characters: {len(str(raw_data))}")
        
        # If it is a string, display detailed information
        if isinstance(raw_data, str):
            lines = raw_data.split('\n')
            print(f"   - Total number of rows: {len(lines)}")
            print(f"   - First line: {lines[0]}")
            if len(lines) > 1:
                print(f"   - last line: {lines[-1]}")
            
            # Find key information
            if "Stock code" in raw_data:
                print("   ✅ Contains stock code information")
            if "Stock name" in raw_data:
                print("   ✅ Contains stock name information")
            if "current price" in raw_data:
                print("   ✅ Contains current price information")
            if "financial indicators" in raw_data:
                print("   ✅ Contains financial indicator information")
            if "historical price" in raw_data:
                print("   ✅ Contains historical price information")
        
        print("\n🎉 Raw data display completed!")
        
        # Test to obtain financial data
        print("\n" + "=" * 80)
        print("📊 Test to obtain financial fundamental data")
        print("=" * 80)
        
        try:
            from tradingagents.dataflows.interface import get_china_stock_fundamentals_tushare
            
            print("🔄 Retrieving financial fundamentals data...")
            
            fundamentals_data = get_china_stock_fundamentals_tushare(ticker)
            
            print("✅ Financial fundamental data was obtained successfully!")
            print()
            
            print("📋 Basic information on financial fundamentals:")
            print(f"   - data type: {type(fundamentals_data)}")
            print(f"   - Data length: {len(str(fundamentals_data))} character")
            print()
            
            print("📄 Complete financial fundamental data content:")
            print("=" * 80)
            
            if isinstance(fundamentals_data, str):
                print("🔤 Financial data in string format:")
                print(fundamentals_data)
            elif isinstance(fundamentals_data, dict):
                print("📚 Dictionary format financial data:")
                print(json.dumps(fundamentals_data, ensure_ascii=False, indent=2))
            else:
                print("🔍 Financial data in other formats:")
                print(repr(fundamentals_data))
            
            print("=" * 80)
            
        except Exception as e:
            print(f"❌ Failed to obtain financial fundamental data: {str(e)}")
            import traceback
            print("🔍 Detailed error message:")
            traceback.print_exc()
        
    except Exception as e:
        print(f"❌ test failed: {str(e)}")
        import traceback
        print("🔍 Detailed error message:")
        traceback.print_exc()

if __name__ == "__main__":
    test_raw_data_display()