#!/usr/bin/env python3
"""
Debugging the complete AKShare data acquisition and parsing process
"""

import sys
import os
import logging
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set verbose log level
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider
from tradingagents.dataflows.akshare_utils import get_akshare_provider

def debug_full_flow():
    """Debugging the complete data acquisition and parsing process"""
    symbol = "600519"
    
    print("🔍 Start debugging the complete process...")
    
    # 1. Initialize data provider
    provider = OptimizedChinaDataProvider()
    print(f"✅ Data provider initialization completed")
    
    # 2. Get AKShare financial data
    print(f"\n📊 Get AKShare financial data...")
    akshare_provider = get_akshare_provider()
    financial_data = akshare_provider.get_financial_data(symbol)
    stock_info = akshare_provider.get_stock_info(symbol)
    
    print(f"   financial data key: {list(financial_data.keys()) if financial_data else 'None'}")
    print(f"   stock information: {stock_info}")
    
    # 3. Get simulated stock price
    print(f"\n💰 Get simulated stock price...")
    current_price = "1800.0"  # simulated stock price
    try:
        price_value = float(current_price.replace('¥', '').replace(',', ''))
        print(f"   Analyze stock price: {price_value}")
    except Exception as e:
        print(f"   Stock price analysis failed: {e}")
        price_value = 10.0
    
    # 4. Call parsing function
    print(f"\n🔧 Call parsing function...")
    try:
        metrics = provider._parse_akshare_financial_data(financial_data, stock_info, price_value)
        if metrics:
            print(f"✅ Parsed successfully!")
            print(f"   PE: {metrics.get('pe', 'N/A')}")
            print(f"   PB: {metrics.get('pb', 'N/A')}")
            print(f"   ROE: {metrics.get('roe', 'N/A')}")
            print(f"   Data source: {metrics.get('data_source', 'N/A')}")
        else:
            print(f"❌ Parsing failed, return None")
    except Exception as e:
        print(f"❌ parsing exception: {e}")
        import traceback
        traceback.print_exc()
    
    # 5. Test_get_real_financial_metrics function
    print(f"\n🔍 Test_get_real_financial_metrics function...")
    try:
        print(f"   Call parameters: symbol={symbol}, price_value={price_value}")
        real_metrics = provider._get_real_financial_metrics(symbol, price_value)
        print(f"   Return results: {real_metrics}")
        if real_metrics:
            print(f"✅ Real financial metrics for success!")
            print(f"   PE: {real_metrics.get('pe', 'N/A')}")
            print(f"   PB: {real_metrics.get('pb', 'N/A')}")
            print(f"   ROE: {real_metrics.get('roe', 'N/A')}")
            print(f"   Data source: {real_metrics.get('data_source', 'N/A')}")
        else:
            print(f"❌ Failed to obtain real financial indicators")
    except Exception as e:
        print(f"❌ Abnormal acquisition of real financial indicators: {e}")
        import traceback
        traceback.print_exc()
    
    # 6. Test_estimate_financial_metrics function
    print(f"\n🔍 Test_estimate_financial_metrics function...")
    try:
        print(f"   Call parameters: symbol={symbol}, current_price={current_price}")
        estimated_metrics = provider._estimate_financial_metrics(symbol, current_price)
        print(f"   Return results: {estimated_metrics}")
        if estimated_metrics:
            print(f"✅ Financial indicator estimation successful!")
            print(f"   PE: {estimated_metrics.get('pe', 'N/A')}")
            print(f"   PB: {estimated_metrics.get('pb', 'N/A')}")
            print(f"   ROE: {estimated_metrics.get('roe', 'N/A')}")
            print(f"   Data source: {estimated_metrics.get('data_source', 'N/A')}")
        else:
            print(f"❌ Financial indicator estimation failed")
    except Exception as e:
        print(f"❌ Financial indicator estimation anomalies: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n" + "="*60)
    print(f"✅ Debugging completed")
    print(f"="*60)

if __name__ == "__main__":
    debug_full_flow()