#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Detailed data display test script
Completely displays all data content obtained by fundamental analysis
"""

import sys
import os
import json
from datetime import datetime, timedelta

# Add project root directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.utils.agent_utils import Toolkit

def test_detailed_data_display():
    """Test and fully display the data obtained by fundamental analysis"""
    
    print("=" * 80)
    print("📊 Fundamental analysis data detailed display test")
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
        # Create tool instance
        toolkit = Toolkit()
        
        print("🔄 Getting fundamental analysis data...")
        print("-" * 60)
        
        # Call the optimized fundamental data acquisition function
        result = toolkit.get_stock_fundamentals_unified.invoke({
            'ticker': ticker,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'curr_date': curr_date.strftime('%Y-%m-%d')
        })
        
        print("✅ Data acquisition successful!")
        print()
        
        # Show basic information about original results
        print("📋 Basic information of original results:")
        print(f"   - data type: {type(result)}")
        print(f"   - Data length: {len(str(result))} character")
        print()
        
        # Show results in full
        print("📄 Complete data content:")
        print("=" * 80)
        
        if isinstance(result, str):
            print("🔤 string format data:")
            print(result)
        elif isinstance(result, dict):
            print("📚 Dictionary format data:")
            for key, value in result.items():
                print(f"🔑 {key}:")
                if isinstance(value, (dict, list)):
                    print(json.dumps(value, ensure_ascii=False, indent=2))
                else:
                    print(f"   {value}")
                print("-" * 40)
        elif isinstance(result, list):
            print("📝 List format data:")
            for i, item in enumerate(result):
                print(f"📌 Project {i+1}:")
                if isinstance(item, (dict, list)):
                    print(json.dumps(item, ensure_ascii=False, indent=2))
                else:
                    print(f"   {item}")
                print("-" * 40)
        else:
            print("🔍 Data in other formats:")
            print(repr(result))
        
        print("=" * 80)
        
        # Data statistics
        print("\n📊 Statistics:")
        print(f"   - Total characters: {len(str(result))}")
        print(f"   - Total number of rows: {str(result).count(chr(10)) + 1}")
        
        # If it is a string, display the before and after parts of the content
        if isinstance(result, str):
            lines = result.split('\n')
            print(f"   - Total number of rows: {len(lines)}")
            print(f"   - First line: {lines[0][:100]}..." if len(lines[0]) > 100 else f"   - First line: {lines[0]}")
            if len(lines) > 1:
                print(f"   - last line: {lines[-1][:100]}..." if len(lines[-1]) > 100 else f"   - last line: {lines[-1]}")
        
        print("\n🎉 Data display completed!")
        
    except Exception as e:
        print(f"❌ test failed: {str(e)}")
        import traceback
        print("🔍 Detailed error message:")
        traceback.print_exc()

if __name__ == "__main__":
    test_detailed_data_display()