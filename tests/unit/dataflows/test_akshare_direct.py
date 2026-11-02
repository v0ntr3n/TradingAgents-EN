#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Directly test the AKShare financial data acquisition function
"""

import akshare as ak
import pandas as pd

def test_akshare_financial_apis():
    """Test AKShare financial data API"""
    print("=" * 60)
    print("🧪 Test AKShare financial data directly API")
    print("=" * 60)
    
    symbol = '000001'
    print(f"🔍 test stocks: {symbol}")
    
    # Test balance sheet
    try:
        print("\n📊 Test balance sheet...")
        balance_sheet = ak.stock_balance_sheet_by_report_em(symbol=symbol)
        if not balance_sheet.empty:
            print(f"✅ The balance sheet was successful, with a total of{len(balance_sheet)}records")
            print(f"📅 Latest reporting period: {balance_sheet.iloc[0]['reporting period']}")
        else:
            print("❌ Balance sheet is empty")
    except Exception as e:
        print(f"❌ Failed to obtain balance sheet: {e}")
    
    # Test the income statement
    try:
        print("\n📊 Test the income statement...")
        income_statement = ak.stock_profit_sheet_by_report_em(symbol=symbol)
        if not income_statement.empty:
            print(f"✅ The income statement was successful, with a total of{len(income_statement)}records")
            print(f"📅 Latest reporting period: {income_statement.iloc[0]['reporting period']}")
        else:
            print("❌ Income statement is empty")
    except Exception as e:
        print(f"❌ Failed to obtain income statement: {e}")
    
    # Test Cash Flow Statement
    try:
        print("\n📊 Test Cash Flow Statement...")
        cash_flow = ak.stock_cash_flow_sheet_by_report_em(symbol=symbol)
        if not cash_flow.empty:
            print(f"✅ The cash flow statement was successfully obtained, with a total of{len(cash_flow)}records")
            print(f"📅 Latest reporting period: {cash_flow.iloc[0]['reporting period']}")
        else:
            print("❌ Cash flow statement is empty")
    except Exception as e:
        print(f"❌ Failed to obtain cash flow statement: {e}")
    
    # Test key financial indicators
    try:
        print("\n📊 Test key financial indicators...")
        main_indicators = ak.stock_financial_abstract_ths(symbol=symbol)
        if not main_indicators.empty:
            print(f"✅ The main financial indicators were successful, with a total of{len(main_indicators)}records")
            print("📈 Main indicators:")
            for col in main_indicators.columns[:5]:  # Show first 5 columns
                print(f"   {col}: {main_indicators.iloc[0][col]}")
        else:
            print("❌ Key financial indicators are empty")
    except Exception as e:
        print(f"❌ Failed to obtain major financial indicators: {e}")

def test_akshare_stock_info():
    """Test AKShare stock basic information"""
    print("\n" + "=" * 60)
    print("📋 Test AKShare stock basic information")
    print("=" * 60)
    
    symbol = '000001'
    print(f"🔍 test stocks: {symbol}")
    
    try:
        stock_info = ak.stock_individual_info_em(symbol=symbol)
        if not stock_info.empty:
            print(f"✅ Stock information obtained successfully")
            print("📋 Basic information:")
            for _, row in stock_info.head(10).iterrows():  # Show first 10 items
                print(f"   {row['item']}: {row['value']}")
        else:
            print("❌ Stock information is empty")
    except Exception as e:
        print(f"❌ Failed to obtain stock information: {e}")

def main():
    """Main test function"""
    print("🚀 Start testing AKShare financial data directly API")
    print()
    
    test_akshare_financial_apis()
    test_akshare_stock_info()
    
    print("\n" + "=" * 60)
    print("✅ Test completed")
    print("=" * 60)

if __name__ == "__main__":
    main()