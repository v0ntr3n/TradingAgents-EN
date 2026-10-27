#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test the financial data functionality of the QMT adapter
"""
import sys
import os

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from app.services.data_sources.qmt_adapter import QMTAdapter

def on_progress(data):
    """Download progress callback function"""
    total = data.get('total', 0)
    finished = data.get('finished', 0)
    stockcode = data.get('stockcode', '')
    
    if total > 0:
        percent = (finished / total) * 100
        print(f"  📥 Progress: {finished}/{total} ({percent:.1f}%) - {stockcode}")

def test_qmt_adapter_financial():
    """Test the financial data functionality of the QMT adapter"""
    print("=" * 60)
    print("🔍 Test QMT Adapter - Financial Data Functionality")
    print("=" * 60)
    
    # Create a QMT adapter instance
    adapter = QMTAdapter()
    
    # Check availability
    print("\n1️⃣ Check QMT adapter availability...")
    if not adapter.is_available():
        print("❌ QMT Adapter not available")
        return
    print("✅ QMT Adapters available")
    
    # Test stock list
    test_stocks = ["000001", "600000"]
    
    # Test downloading financial data
    print(f"\n2️⃣ Test downloading financial data - {', '.join(test_stocks)}...")
    success = adapter.download_financial_data(
        stock_list=test_stocks,
        table_list=['Pershareindex', 'Income'],
        start_time='20230101',
        end_time='20241231',
        callback=on_progress
    )
    
    if success:
        print("✅ Financial data download successful")
    else:
        print("❌ Financial data download failed")
        return
    
    # Test to obtain financial data
    print(f"\n3️⃣ Test to obtain financial data...")
    for code in test_stocks:
        print(f"\n  📊 {code}:")
        
        financial_data = adapter.get_financial_data(
            code=code,
            table_list=['Pershareindex', 'Income'],
            start_time='20230101',
            end_time='20241231',
            report_type='announce_time'
        )
        
        if financial_data:
            for table_name, df in financial_data.items():
                print(f"    ✅ {table_name}: {len(df)} records")
                
                # Show the latest data
                if len(df) > 0:
                    latest = df.iloc[0]
                    
                    if table_name == 'Pershareindex':
                        print(f"       Latest: {latest.get('m_timetag', 'N/A')} "
                              f"EPS={latest.get('s_fa_eps_basic', 'N/A')} "
                              f"BPS={latest.get('s_fa_bps', 'N/A')}")
                    elif table_name == 'Income':
                        print(f"       Latest: {latest.get('m_timetag', 'N/A')} "
                              f"Revenue={latest.get('revenue_inc', 'N/A')} "
                              f"net profit={latest.get('net_profit_incl_min_int_inc', 'N/A')}")
        else:
            print(f"    ❌ No financial data was obtained")
    
    print("\n" + "=" * 60)
    print("✅ QMT Adapter financial data function test completed")
    print("=" * 60)

if __name__ == "__main__":
    test_qmt_adapter_financial()

