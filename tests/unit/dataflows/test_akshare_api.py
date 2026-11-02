#!/usr/bin/env python3
"""
direct test AKShare API
"""

import akshare as ak
import logging

# Set log level
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-8s | %(message)s')

def test_akshare_apis():
    """Test various financial data of AKShare API"""
    print("=" * 60)
    print("🔍 Test AKShare financial data directly API")
    print("=" * 60)
    
    symbol = "600519"
    
    # 1. Test key financial indicators API
    print(f"\n1. Test key financial indicators API: stock_financial_abstract")
    try:
        data = ak.stock_financial_abstract(symbol=symbol)
        if data is not None and not data.empty:
            print(f"✅ Successfully obtain key financial indicators: {len(data)}records")
            print(f"   List: {list(data.columns)}")
            print(f"   First 3 rows of data:")
            print(data.head(3))
        else:
            print("❌ Key financial indicators are empty")
    except Exception as e:
        print(f"❌ Key Financial Indicators API failed: {e}")
    
    # 2. Test balance sheet API
    print(f"\n2. Test balance sheet API: stock_balance_sheet_by_report_em")
    try:
        data = ak.stock_balance_sheet_by_report_em(symbol=symbol)
        if data is not None and not data.empty:
            print(f"✅ Successfully obtained the balance sheet: {len(data)}records")
            print(f"   List: {list(data.columns)}")
        else:
            print("❌ Balance sheet is empty")
    except Exception as e:
        print(f"❌ Balance Sheet API failed: {e}")
    
    # 3. Test the income statement API
    print(f"\n3. Test the income statement API: stock_profit_sheet_by_report_em")
    try:
        data = ak.stock_profit_sheet_by_report_em(symbol=symbol)
        if data is not None and not data.empty:
            print(f"✅ Successfully obtained income statement: {len(data)}records")
            print(f"   List: {list(data.columns)}")
        else:
            print("❌ Income statement is empty")
    except Exception as e:
        print(f"❌ Income Statement API failed: {e}")
    
    # 4. Test Cash Flow Statement API
    print(f"\n4. Test Cash Flow Statement API: stock_cash_flow_sheet_by_report_em")
    try:
        data = ak.stock_cash_flow_sheet_by_report_em(symbol=symbol)
        if data is not None and not data.empty:
            print(f"✅ Successfully obtained cash flow statement: {len(data)}records")
            print(f"   List: {list(data.columns)}")
        else:
            print("❌ Cash flow statement is empty")
    except Exception as e:
        print(f"❌ Cash flow statement API failed: {e}")
    
    print("\n" + "=" * 60)
    print("✅ API Test completed")
    print("=" * 60)

if __name__ == "__main__":
    test_akshare_apis()