#!/usr/bin/env python3
"""
Specifically view the PE, PB, and ROE indicators in AKShare financial data
"""

import sys
import os
import logging

# Set log level
logging.basicConfig(level=logging.WARNING, format='%(asctime)s | %(levelname)-8s | %(message)s')

# Add project path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.dataflows.akshare_utils import AKShareProvider

def check_key_metrics():
    """Check key financial indicators"""
    print("=" * 60)
    print("🔍 Check AKShare Key Financial Metrics")
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
    
    # Get the latest data column
    latest_col = main_indicators.columns[2]  # Column 3 is the latest data
    print(f"📅 latest data period: {latest_col}")
    
    # Find ROE
    roe_row = main_indicators[main_indicators['indicator'] == 'ROE(ROE)']
    if not roe_row.empty:
        roe_value = roe_row.iloc[0][latest_col]
        print(f"📈 ROE(ROE): {roe_value}")
    else:
        print("❌ ROE indicator not found")
    
    # Find earnings per share (used to calculate PE)
    eps_row = main_indicators[main_indicators['indicator'] == 'earnings per share']
    if not eps_row.empty:
        eps_value = eps_row.iloc[0][latest_col]
        print(f"💰 earnings per share(EPS): {eps_value}")
    else:
        print("❌ Earnings per share metric not found")
    
    # Find net assets per share (used to calculate PB)
    bps_row = main_indicators[main_indicators['indicator'] == 'Net assets per share_latest number of shares']
    if not bps_row.empty:
        bps_value = bps_row.iloc[0][latest_col]
        print(f"📊 Net assets per share(BPS): {bps_value}")
    else:
        print("❌ Net assets per share indicator not found")
    
    # show all contains"per share"indicators
    print(f"\n📋 All per share related indicators:")
    eps_indicators = main_indicators[main_indicators['indicator'].str.contains('per share', na=False)]
    for _, row in eps_indicators.iterrows():
        indicator_name = row['indicator']
        value = row[latest_col]
        print(f"   {indicator_name}: {value}")
    
    # show all contains"Yield"indicators
    print(f"\n📋 All yield related indicators:")
    roe_indicators = main_indicators[main_indicators['indicator'].str.contains('Yield', na=False)]
    for _, row in roe_indicators.iterrows():
        indicator_name = row['indicator']
        value = row[latest_col]
        print(f"   {indicator_name}: {value}")
    
    print("\n" + "=" * 60)
    print("✅ Key indicator check completed")
    print("=" * 60)

if __name__ == "__main__":
    check_key_metrics()