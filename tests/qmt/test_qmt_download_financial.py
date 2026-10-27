#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Testing the QMT download_financial_data2 method (batch download with callback)
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

def on_progress(data):
    """Download progress callback function"""
    total = data.get('total', 0)
    finished = data.get('finished', 0)
    stockcode = data.get('stockcode', '')
    message = data.get('message', '')
    
    # Calculate progress percentage
    if total > 0:
        percent = (finished / total) * 100
        print(f"  📥 Progress: {finished}/{total} ({percent:.1f}%) - {stockcode} {message}")
    else:
        print(f"  📥 {stockcode} {message}")

def test_download_financial_data2():
    """Test the download_financial_data2 method"""
    print("=" * 60)
    print("🔍 Testing the QMT download_financial_data2 method")
    print("=" * 60)
    
    # Test stock list (small number of stocks to speed up testing)
    stock_list = [
        "000001.SZ",  # Ping An Bank
        "600000.SH",  # Shanghai Pudong Development Bank
        "000002.SZ",  # Vanke A
    ]
    
    # Download only main indicators (reduce download time)
    table_list = [
        'Pershareindex',  # Per Share Indicators (Main Indicators)
        'Income',         # income statement
    ]
    
    print(f"\n📊 test stocks: {', '.join(stock_list)}")
    print(f"📋 Report type: {', '.join(table_list)}")
    print(f"⏰ time range: 2023-01-01 to 2024-12-31")
    
    # Download using download_financial_data2
    print(f"\n⏬ Start downloading financial data...")
    print(f"💡 Tips: This may take some time, please be patient...\n")
    
    try:
        xtdata.download_financial_data2(
            stock_list=stock_list,
            table_list=table_list,
            start_time='20230101',  # Starting time (by disclosure date)
            end_time='20241231',    # End time (by disclosure date)
            callback=on_progress    # Progress callback
        )
        
        print(f"\n✅ Download completed!")
        
        # Verify downloaded data
        print(f"\n📥 Verify downloaded data...")
        for stock_code in stock_list:
            print(f"\n  📊 {stock_code}:")
            
            financial_data = xtdata.get_financial_data(
                stock_list=[stock_code],
                table_list=table_list,
                start_time='20230101',
                end_time='20241231',
                report_type='announce_time'  # Filter by disclosure date
            )
            
            if financial_data and stock_code in financial_data:
                stock_data = financial_data[stock_code]
                
                for table_name, table_data in stock_data.items():
                    if table_data is not None and not table_data.empty:
                        print(f"    ✅ {table_name}: {len(table_data)} records")
                        
                        # Show latest issue
                        if len(table_data) > 0:
                            latest = table_data.iloc[0]
                            
                            if table_name == 'Pershareindex':
                                print(f"       Latest: {latest.get('m_timetag', 'N/A')} "
                                      f"EPS={latest.get('s_fa_eps_basic', 'N/A')} "
                                      f"BPS={latest.get('s_fa_bps', 'N/A')}")
                            elif table_name == 'Income':
                                print(f"       Latest: {latest.get('m_timetag', 'N/A')} "
                                      f"Revenue={latest.get('revenue_inc', 'N/A')} "
                                      f"net profit={latest.get('net_profit_incl_min_int_inc', 'N/A')}")
                    else:
                        print(f"    ❌ {table_name}: No data")
            else:
                print(f"    ❌ No data obtained")
        
    except Exception as e:
        print(f"\n❌ Download failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_download_financial_data2()

