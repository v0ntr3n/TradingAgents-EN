#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test the repair effect of AKShare data source priority and financial indicators
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.dataflows.optimized_china_data import get_optimized_china_data_provider
from tradingagents.dataflows.akshare_utils import get_akshare_provider
from tradingagents.dataflows.tushare_utils import get_tushare_provider

def test_data_source_connection():
    """Test data source connection status"""
    print("=" * 60)
    print("📡 Test data source connection status")
    print("=" * 60)
    
    # Test AKShare connection
    try:
        akshare_provider = get_akshare_provider()
        print(f"🔗 AKShare connection status: {'✅ Connected' if akshare_provider.connected else '❌ Not connected'}")
    except Exception as e:
        print(f"❌ AKShare Connection failed: {e}")
    
    # Test Tushare connection
    try:
        tushare_provider = get_tushare_provider()
        print(f"🔗 Tushare connection status: {'✅ Connected' if tushare_provider.connected else '❌ Not connected'}")
    except Exception as e:
        print(f"❌ Tushare Connection failed: {e}")
    
    print()

def test_akshare_financial_data():
    """Test AKShare financial data acquisition"""
    print("=" * 60)
    print("📊 Test AKShare financial data acquisition")
    print("=" * 60)
    
    test_symbols = ['000001', '000002', '600519']
    
    try:
        akshare_provider = get_akshare_provider()
        if not akshare_provider.connected:
            print("❌ AKShare Not connected, skip test")
            return
        
        for symbol in test_symbols:
            print(f"\n🔍 test stocks: {symbol}")
            try:
                financial_data = akshare_provider.get_financial_data(symbol)
                if financial_data:
                    print(f"✅ {symbol}: AKShare Financial data obtained successfully")
                    
                    # Check key financial indicators
                    main_indicators = financial_data.get('main_indicators', {})
                    if main_indicators:
                        pe = main_indicators.get('P/E ratio', main_indicators.get('PE', 'N/A'))
                        pb = main_indicators.get('price to book ratio', main_indicators.get('PB', 'N/A'))
                        roe = main_indicators.get('ROE', main_indicators.get('ROE', 'N/A'))
                        print(f"   📈 PE: {pe}, PB: {pb}, ROE: {roe}")
                    else:
                        print(f"   ⚠️ Key financial indicators are empty")
                else:
                    print(f"❌ {symbol}: AKShare Failed to obtain financial data")
            except Exception as e:
                print(f"❌ {symbol}: AKShare Abnormal acquisition of financial data: {e}")
    
    except Exception as e:
        print(f"❌ AKShare Financial data test failed: {e}")
    
    print()

def test_financial_metrics_with_data_source():
    """Test financial metric calculations and data source identification"""
    print("=" * 60)
    print("🧮 Test financial metric calculations and data source identification")
    print("=" * 60)
    
    test_symbols = ['000001', '000002', '600519']
    
    provider = get_optimized_china_data_provider()
    
    for symbol in test_symbols:
        print(f"\n🔍 test stocks: {symbol}")
        try:
            # Get fundamental data
            fundamentals = provider.get_fundamentals_data(symbol, force_refresh=True)
            
            # Check data source identification
            if "AKShare" in fundamentals:
                data_source = "AKShare"
            elif "Tushare" in fundamentals:
                data_source = "Tushare"
            else:
                data_source = "unknown"
            
            print(f"📊 Data source: {data_source}")
            
            # Extract PE, PB, ROE information
            lines = fundamentals.split('\n')
            pe_line = next((line for line in lines if 'P/E ratio(PE)' in line), None)
            pb_line = next((line for line in lines if 'price to book ratio(PB)' in line), None)
            roe_line = next((line for line in lines if 'ROE(ROE)' in line), None)
            
            if pe_line:
                pe_value = pe_line.split('**')[2].strip() if '**' in pe_line else pe_line.split(':')[1].strip()
                print(f"📈 PE: {pe_value}")
            
            if pb_line:
                pb_value = pb_line.split('**')[2].strip() if '**' in pb_line else pb_line.split(':')[1].strip()
                print(f"📈 PB: {pb_value}")
            
            if roe_line:
                roe_value = roe_line.split('**')[2].strip() if '**' in roe_line else roe_line.split(':')[1].strip()
                print(f"📈 ROE: {roe_value}")
            
            # Check if there is an outlier of 0 times
            if pe_line and ('0.0 times' in pe_line or '0 times' in pe_line):
                print(f"⚠️ PE outliers found: {pe_value}")
            
            if pb_line and ('0.00 times' in pb_line or '0 times' in pb_line):
                print(f"⚠️ PB outliers found: {pb_value}")
                
        except Exception as e:
            print(f"❌ {symbol}: Financial indicator test failed: {e}")
    
    print()

def test_data_source_priority():
    """Test data source priority"""
    print("=" * 60)
    print("🔄 Test data source priority")
    print("=" * 60)
    
    provider = get_optimized_china_data_provider()
    
    # Test the process of obtaining financial indicators for a stock
    symbol = '000001'
    print(f"🔍 test stocks: {symbol}")
    
    try:
        # Directly call internal method test
        real_metrics = provider._get_real_financial_metrics(symbol, 10.0)
        
        if real_metrics:
            data_source = real_metrics.get('data_source', 'unknown')
            print(f"✅ Financial data obtained successfully")
            print(f"📊 Data source: {data_source}")
            print(f"📈 PE: {real_metrics.get('pe', 'N/A')}")
            print(f"📈 PB: {real_metrics.get('pb', 'N/A')}")
            print(f"📈 ROE: {real_metrics.get('roe', 'N/A')}")
            
            if data_source == 'AKShare':
                print("✅ Prioritize using AKShare data source successfully")
            elif data_source == 'Tushare':
                print("⚠️ Use Tushare alternative data source")
            else:
                print("❓ Data source is unclear")
        else:
            print("❌ Failed to obtain financial data")
            
    except Exception as e:
        print(f"❌ Data source priority test failed: {e}")
    
    print()

def main():
    """Main test function"""
    print("🚀 Start AKShare data source priority and financial indicator repair testing")
    print()
    
    # 1. Test data source connection
    test_data_source_connection()
    
    # 2. Test AKShare financial data acquisition
    test_akshare_financial_data()
    
    # 3. Test data source priority
    test_data_source_priority()
    
    # 4. Test financial metrics and data source identification
    test_financial_metrics_with_data_source()
    
    print("=" * 60)
    print("✅ Test completed")
    print("=" * 60)

if __name__ == "__main__":
    main()