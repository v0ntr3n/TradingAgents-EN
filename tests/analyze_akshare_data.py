#!/usr/bin/env python3
"""
Check AKShare financial data structure
"""

import sys
import os
import logging

# Set log level
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-8s | %(message)s')

# Add project path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.dataflows.akshare_utils import AKShareProvider

def analyze_akshare_data():
    """Analyze AKShare financial data structure"""
    print("=" * 60)
    print("🔍 Analyze AKShare financial data structure")
    print("=" * 60)
    
    provider = AKShareProvider()
    if not provider.connected:
        print("❌ AKShare Not connected")
        return
    
    symbol = "600519"
    financial_data = provider.get_financial_data(symbol)
    
    if not financial_data:
        print("❌ No financial data was obtained")
        return
    
    main_indicators = financial_data.get('main_indicators')
    if main_indicators is None:
        print("❌ No major financial indicators were obtained")
        return
    
    print(f"\n📊 Analysis of data structure of main financial indicators:")
    print(f"   data type: {type(main_indicators)}")
    print(f"   data shape: {main_indicators.shape}")
    print(f"   List: {list(main_indicators.columns)}")
    
    print(f"\n📋 First 5 rows of data:")
    print(main_indicators.head())
    
    print(f"\n🔍 Find PE, PB, ROE related indicators:")
    
    # Find rows containing keywords
    pe_rows = main_indicators[main_indicators['indicator'].str.contains('P/E ratio|PE', na=False, case=False)]
    pb_rows = main_indicators[main_indicators['indicator'].str.contains('price to book ratio|PB', na=False, case=False)]
    roe_rows = main_indicators[main_indicators['indicator'].str.contains('ROE|ROE', na=False, case=False)]
    
    # Get the latest data column (column 3, index 2)
    latest_col = main_indicators.columns[2] if len(main_indicators.columns) > 2 else None
    print(f"   latest data column: {latest_col}")
    
    print(f"\n📈 PE Related indicators ({len(pe_rows)}Article):")
    if not pe_rows.empty:
        for _, row in pe_rows.iterrows():
            latest_value = row[latest_col] if latest_col else 'N/A'
            print(f"   {row['indicator']}: {latest_value}")
    else:
        print("   No PE related indicators found")
    
    print(f"\n📈 PB Related indicators ({len(pb_rows)}Article):")
    if not pb_rows.empty:
        for _, row in pb_rows.iterrows():
            latest_value = row[latest_col] if latest_col else 'N/A'
            print(f"   {row['indicator']}: {latest_value}")
    else:
        print("   No PB related indicators found")
    
    print(f"\n📈 ROE Related indicators ({len(roe_rows)}Article):")
    if not roe_rows.empty:
        for _, row in roe_rows.iterrows():
            latest_value = row[latest_col] if latest_col else 'N/A'
            print(f"   {row['indicator']}: {latest_value}")
    else:
        print("   No ROE related indicators found")
    
    # Specifically look for the ROE indicator
    roe_exact = main_indicators[main_indicators['indicator'] == 'ROE(ROE)']
    if not roe_exact.empty:
        roe_value = roe_exact.iloc[0][latest_col] if latest_col else 'N/A'
        print(f"\n🎯 Exact Match - ROE(ROE): {roe_value}")
        
        # Display historical data of ROE (previous 5 quarters)
        print(f"   historical data:")
        for i in range(2, min(7, len(main_indicators.columns))):
            col_name = main_indicators.columns[i]
            value = roe_exact.iloc[0][col_name]
            print(f"     {col_name}: {value}")
    
    # Find possible alternative indicators of PE and PB
    print(f"\n🔍 Find possible alternative indicators of PE and PB:")
    
    # Find relevant indicators per share
    eps_rows = main_indicators[main_indicators['indicator'].str.contains('earnings per share|net profit per share', na=False, case=False)]
    print(f"\n📈 Earnings per share related indicators ({len(eps_rows)}Article):")
    for _, row in eps_rows.iterrows():
        latest_value = row[latest_col] if latest_col else 'N/A'
        print(f"   {row['indicator']}: {latest_value}")
    
    # Find indicators related to net assets per share
    bps_rows = main_indicators[main_indicators['indicator'].str.contains('Net assets per share', na=False, case=False)]
    print(f"\n📈 Net assets per share related indicators ({len(bps_rows)}Article):")
    for _, row in bps_rows.iterrows():
        latest_value = row[latest_col] if latest_col else 'N/A'
        print(f"   {row['indicator']}: {latest_value}")
    
    # Show all indicator names
    print(f"\n📋 All indicator names:")
    for i, indicator in enumerate(main_indicators['indicator']):
        print(f"   {i:2d}. {indicator}")
    
    print("\n" + "=" * 60)
    print("✅ Data structure analysis completed")
    print("=" * 60)

if __name__ == "__main__":
    analyze_akshare_data()