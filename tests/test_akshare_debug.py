#!/usr/bin/env python3
"""
AKShare Financial data acquisition debugging script
"""

import sys
import os
import logging

# Set the log level to DEBUG to view detailed information
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s')

# Add project path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.dataflows.akshare_utils import AKShareProvider

def test_akshare_financial_data():
    """Test AKShare financial data acquisition"""
    print("=" * 60)
    print("🔍 AKShare Financial data acquisition debugging test")
    print("=" * 60)
    
    # 1. Get AKShare provider
    print("\n1. Get AKShare provider...")
    provider = AKShareProvider()
    print(f"   connection status: {provider.connected}")
    
    if not provider.connected:
        print("❌ AKShare Not connected, unable to continue testing")
        return
    
    # 2. Directly call the get_financial_data method
    print("\n2. Directly call the get_financial_data method...")
    symbol = "600519"
    
    try:
        financial_data = provider.get_financial_data(symbol)
        print(f"   Return result type: {type(financial_data)}")
        print(f"   Return results: {financial_data}")
        
        if financial_data:
            print("✅ Successfully obtained financial data")
            for key, value in financial_data.items():
                if hasattr(value, '__len__'):
                    print(f"   - {key}: {len(value)}records")
                else:
                    print(f"   - {key}: {type(value)}")
        else:
            print("❌ No financial data was obtained")
            
    except Exception as e:
        print(f"❌ Failed to call get_financial_data: {e}")
        import traceback
        traceback.print_exc()
    
    # 3. Test condition judgment
    print("\n3. Test condition judgment...")
    test_data = {}
    print(f"   empty dictionary any(test_data.values()): {any(test_data.values())}")
    
    test_data = {'main_indicators': None}
    print(f"   contains None any(test_data.values()): {any(test_data.values())}")
    
    test_data = {'main_indicators': {}}
    print(f"   Contains an empty dictionary any(test_data.values()): {any(test_data.values())}")
    
    test_data = {'main_indicators': {'pe': 18.5}}
    print(f"   Contains data any(test_data.values()): {any(test_data.values())}")
    
    print("\n" + "=" * 60)
    print("✅ Debugging test completed")
    print("=" * 60)

if __name__ == "__main__":
    test_akshare_financial_data()