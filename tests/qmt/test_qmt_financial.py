#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test QMT financial data acquisition
"""
import sys
import os

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

try:
    import xtquant.xtdata as xtdata
except ImportError:
    print("❌ xtquant Not installed")
    sys.exit(1)

def test_financial_data():
    """Test financial data acquisition"""
    print("=" * 60)
    print("🔍 Test QMT financial data acquisition")
    print("=" * 60)
    
    # test stocks
    stock_code = "000001.SZ"  # Ping An Bank
    
    # Supported financial statements
    table_list = [
        'Balance',          # balance sheet
        'Income',           # income statement
        'CashFlow',         # cash flow statement
        'Pershareindex',    # Per Share Indicators (Main Indicators)
        'Capital',          # share capital table
        'Top10holder',      # Top ten shareholders
        'Top10flowholder',  # Top ten tradable shareholders
        'Holdernum',        # Number of shareholders
    ]
    
    print(f"\n📊 test stocks: {stock_code}")
    print(f"📋 Report type: {', '.join(table_list)}")
    
    # Download financial data first
    print(f"\n⏬ Download financial data...")
    try:
        xtdata.download_financial_data([stock_code], table_list)
        print("✅ Download completed")
    except Exception as e:
        print(f"⚠️  Download failed: {e}")
    
    # Get financial data
    print(f"\n📥 Get financial data...")
    try:
        financial_data = xtdata.get_financial_data(
            stock_list=[stock_code],
            table_list=table_list,
            start_time='',  # Empty means earliest
            end_time='',    # Empty means latest
            report_type='report_time'  # Filter by deadline
        )
        
        if financial_data and stock_code in financial_data:
            stock_data = financial_data[stock_code]
            print(f"✅ Successfully obtained financial data")
            print(f"\n📊 Data overview:")
            
            for table_name, table_data in stock_data.items():
                if table_data is not None and not table_data.empty:
                    print(f"\n  📋 {table_name}:")
                    print(f"     Number of records: {len(table_data)}")
                    print(f"     Number of fields: {len(table_data.columns)}")
                    print(f"     Field list: {', '.join(table_data.columns[:10].tolist())}...")
                    
                    # Display some fields of the latest period of data
                    if len(table_data) > 0:
                        latest = table_data.iloc[0]
                        print(f"     Latest issue:")
                        
                        # Display key fields according to different reports
                        if table_name == 'Income':
                            print(f"       Disclosure date: {latest.get('m_anntime', 'N/A')}")
                            print(f"       Deadline: {latest.get('m_timetag', 'N/A')}")
                            print(f"       operating income: {latest.get('revenue_inc', 'N/A')}")
                            print(f"       net profit: {latest.get('net_profit_incl_min_int_inc', 'N/A')}")
                        elif table_name == 'Balance':
                            print(f"       Disclosure date: {latest.get('m_anntime', 'N/A')}")
                            print(f"       Deadline: {latest.get('m_timetag', 'N/A')}")
                            print(f"       total assets: {latest.get('tot_assets', 'N/A')}")
                            print(f"       total liabilities: {latest.get('tot_liab', 'N/A')}")
                        elif table_name == 'Pershareindex':
                            print(f"       Disclosure date: {latest.get('m_anntime', 'N/A')}")
                            print(f"       Deadline: {latest.get('m_timetag', 'N/A')}")
                            print(f"       earnings per share: {latest.get('s_fa_eps_basic', 'N/A')}")
                            print(f"       Net assets per share: {latest.get('s_fa_bps', 'N/A')}")
                            print(f"       ROE: {latest.get('du_return_on_equity', 'N/A')}")
                        elif table_name == 'Capital':
                            print(f"       Report date: {latest.get('m_timetag', 'N/A')}")
                            print(f"       total share capital: {latest.get('total_capital', 'N/A')}")
                            print(f"       circulating capital: {latest.get('circulating_capital', 'N/A')}")
                else:
                    print(f"\n  ❌ {table_name}: No data")
        else:
            print(f"❌ No financial data was obtained")
            
    except Exception as e:
        print(f"❌ Failed to obtain: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_financial_data()

