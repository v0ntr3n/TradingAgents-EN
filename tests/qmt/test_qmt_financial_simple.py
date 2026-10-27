#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test QMT financial data acquisition (simplified version)
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

def test_financial_data_simple():
    """Test financial data acquisition (no downloading, only local query)"""
    print("=" * 60)
    print("🔍 Test QMT financial data acquisition (query local data)")
    print("=" * 60)
    
    # test stocks
    stock_code = "000001.SZ"  # Ping An Bank
    
    # Only test main indicators
    table_list = ['Pershareindex']  # Per Share Indicators (Main Indicators)
    
    print(f"\n📊 test stocks: {stock_code}")
    print(f"📋 Report type: {', '.join(table_list)}")
    
    # Get financial data directly (no downloading)
    print(f"\n📥 Get local financial data...")
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
            
            for table_name, table_data in stock_data.items():
                if table_data is not None and not table_data.empty:
                    print(f"\n  📋 {table_name}:")
                    print(f"     Number of records: {len(table_data)}")
                    print(f"     Number of fields: {len(table_data.columns)}")
                    
                    # Show the latest data
                    if len(table_data) > 0:
                        latest = table_data.iloc[0]
                        print(f"\n     The latest data:")
                        print(f"       Disclosure date: {latest.get('m_anntime', 'N/A')}")
                        print(f"       Deadline: {latest.get('m_timetag', 'N/A')}")
                        print(f"       earnings per share: {latest.get('s_fa_eps_basic', 'N/A')}")
                        print(f"       Net assets per share: {latest.get('s_fa_bps', 'N/A')}")
                        print(f"       ROE: {latest.get('du_return_on_equity', 'N/A')}")
                        print(f"       operating cash flow per share: {latest.get('s_fa_ocfps', 'N/A')}")
                else:
                    print(f"\n  ❌ {table_name}: No data locally")
                    print(f"  💡 Tips: You need to download financial data in MiniQMT first")
        else:
            print(f"❌ No financial data was obtained")
            print(f"💡 Tips: Financial data for this stock may not be available locally")
            print(f"   This can be downloaded manually in MiniQMT, or using download_financial_data() Download")
            
    except Exception as e:
        print(f"❌ Failed to obtain: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_financial_data_simple()

