#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test the repair effect of financial indicators
Verify that real financial data is used rather than categorical estimates
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider
import logging

# Set log level
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_financial_metrics():
    """Test financial indicator acquisition"""
    print("🔧 Test the repair effect of financial indicators")
    print("=" * 80)
    
    # Test stock list
    test_symbols = [
        "000001",  # Ping An Bank
        "000002",  # Vanke A
        "300001",  # Tered (GEM)
        "600036",  # China Merchants Bank
        "600519",  # Kweichow Moutai
    ]
    
    provider = OptimizedChinaDataProvider()
    
    for symbol in test_symbols:
        print(f"\n📊 test stocks: {symbol}")
        print("-" * 50)
        
        try:
            # Get fundamental data
            fundamentals = provider.get_fundamentals_data(symbol, force_refresh=True)
            
            # Check whether a data source description is included
            if "✅ **Data description**: Financial indicators are calculated based on Tushare s real financial data" in fundamentals:
                print(f"✅ {symbol}: Use real financial data")
            elif "⚠️ **Data description**: Some financial indicators are estimates." in fundamentals:
                print(f"⚠️ {symbol}: Use estimated financial data")
            else:
                print(f"❓ {symbol}: Data source is unclear")
            
            # Extract key financial indicators
            lines = fundamentals.split('\n')
            pe_line = next((line for line in lines if "P/E ratio(PE)" in line), None)
            pb_line = next((line for line in lines if "price to book ratio(PB)" in line), None)
            roe_line = next((line for line in lines if "ROE(ROE)" in line), None)
            
            if pe_line:
                print(f"  PE: {pe_line.split(':')[1].strip()}")
            if pb_line:
                print(f"  PB: {pb_line.split(':')[1].strip()}")
            if roe_line:
                print(f"  ROE: {roe_line.split(':')[1].strip()}")
                
        except Exception as e:
            print(f"❌ {symbol}: test failed - {e}")

def test_tushare_connection():
    """Test Tushare connection"""
    print("\n🔧 Test Tushare connection")
    print("=" * 80)
    
    try:
        from tradingagents.dataflows.tushare_utils import get_tushare_provider
        
        provider = get_tushare_provider()
        if provider.connected:
            print("✅ Tushare Connection successful")
            
            # Test to obtain financial data
            test_symbol = "000001"
            financial_data = provider.get_financial_data(test_symbol)
            
            if financial_data:
                print(f"✅ successfully obtained{test_symbol}financial data")
                print(f"  balance sheet: {len(financial_data.get('balance_sheet', []))}records")
                print(f"  income statement: {len(financial_data.get('income_statement', []))}records")
                print(f"  cash flow statement: {len(financial_data.get('cash_flow', []))}records")
            else:
                print(f"⚠️ Not obtained{test_symbol}financial data")
        else:
            print("❌ Tushare Connection failed")
            
    except Exception as e:
        print(f"❌ Tushare test failed: {e}")

def main():
    """main function"""
    print("🚀 Start testing the financial indicator repair effect")
    print("=" * 80)
    
    # Test Tushare connection
    test_tushare_connection()
    
    # Test financial metrics
    test_financial_metrics()
    
    print("\n✅ Test completed")
    print("=" * 80)
    print("Description:")
    print("- ✅ Represents the use of real financial data")
    print("- ⚠️ Indicates using estimated data (fallback option if Tushare is unavailable)")
    print("- ❌ Indicates test failure")

if __name__ == "__main__":
    main()