#!/usr/bin/env python3
"""
Test the BaoStock stock filtering feature
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from datetime import datetime, timedelta

# Setup log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)

def test_baostock_stock_types():
    """Test different types of data returned by BaoStock"""
    print("=" * 60)
    print("🔍 Test different types of data returned by BaoStock")
    print("=" * 60)
    
    try:
        import baostock as bs
        
        # Login BaoStock
        lg = bs.login()
        if lg.error_code != '0':
            print(f"❌ BaoStock Login failed: {lg.error_msg}")
            return
        
        print("✅ BaoStock Login successful")
        
        # Get a list of stocks
        trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"📅 Query date: {trade_date}")
        
        rs = bs.query_all_stock(day=trade_date)
        print(f"return code: {rs.error_code}")
        print(f"return message: {rs.error_msg}")
        print(f"Field list: {rs.fields}")
        
        if rs.error_code == '0':
            # Parse data and classify by type
            type_counts = {}
            stock_samples = {}
            count = 0
            
            while (rs.error_code == '0') & rs.next():
                row = rs.get_row_data()
                count += 1
                
                if len(row) >= 5:
                    code = row[0]
                    name = row[1]
                    stock_type = row[4]
                    
                    # Count the number of various types
                    if stock_type not in type_counts:
                        type_counts[stock_type] = 0
                        stock_samples[stock_type] = []
                    
                    type_counts[stock_type] += 1
                    
                    # Save first 3 samples
                    if len(stock_samples[stock_type]) < 3:
                        stock_samples[stock_type].append((code, name))
                
                if count >= 1000:  # Limit the number of processes
                    break
            
            print(f"\n📊 Data type statistics (before{count}records):")
            type_names = {
                '1': 'stocks',
                '2': 'Index', 
                '3': 'Others',
                '4': 'Convertible bonds',
                '5': 'ETF'
            }
            
            for stock_type, count in type_counts.items():
                type_name = type_names.get(stock_type, f'unknown type({stock_type})')
                print(f"   Type{stock_type} ({type_name}): {count}Article")
                
                # show sample
                if stock_type in stock_samples:
                    print(f"     sample:")
                    for code, name in stock_samples[stock_type]:
                        print(f"       {code} - {name}")
                print()
        
        bs.logout()
        print("✅ BaoStock Logout successful")
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()

def test_baostock_adapter_stock_filter():
    """Testing the fixed BaoStock adapter stock filtering"""
    print("\n" + "=" * 60)
    print("🧪 Testing the fixed BaoStock adapter stock filtering")
    print("=" * 60)
    
    try:
        from app.services.data_source_adapters import BaoStockAdapter
        
        adapter = BaoStockAdapter()
        
        if not adapter.is_available():
            print("❌ BaoStock Adapter not available")
            return
        
        print("✅ BaoStock Adapters available")
        
        # 1. Get test stock list
        print("\n1. Get test stock list...")
        df = adapter.get_stock_list()
        
        if df is not None and not df.empty:
            print(f"✅ Stock list obtained successfully: {len(df)}records")
            print(f"   List: {list(df.columns)}")
            
            # Check if they are all stocks
            print(f"\n   First 10 records:")
            for i, row in df.head(10).iterrows():
                symbol = row.get('symbol', 'N/A')
                name = row.get('name', 'N/A')
                ts_code = row.get('ts_code', 'N/A')
                print(f"     {symbol} - {name} - {ts_code}")
            
            # Check ticker format
            print(f"\n   📊 Stock symbol analysis:")
            if 'symbol' in df.columns:
                # Analyze stock symbol prefixes
                prefixes = df['symbol'].str[:3].value_counts()
                print(f"     Stock code prefix distribution:")
                for prefix, count in prefixes.head(10).items():
                    print(f"       {prefix}xxx: {count}only")
        else:
            print("❌ Failed to obtain stock list")
            return
        
        # 2. Test daily_basic acquisition
        print("\n2. Test daily_basic data acquisition...")
        trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        print(f"   get{trade_date}data...")
        
        basic_df = adapter.get_daily_basic(trade_date)
        
        if basic_df is not None and not basic_df.empty:
            print(f"✅ daily_basic Data acquisition successful: {len(basic_df)}records")
            print(f"   List: {list(basic_df.columns)}")
            
            # Show first few records
            print(f"   First 10 records:")
            for i, row in basic_df.head(10).iterrows():
                ts_code = row.get('ts_code', 'N/A')
                name = row.get('name', 'N/A')
                pe = row.get('pe', 'N/A')
                pb = row.get('pb', 'N/A')
                close = row.get('close', 'N/A')
                print(f"     {ts_code} - {name}")
                print(f"       PE: {pe}, PB: {pb}, closing price: {close}")
            
            # Statistically valid data
            pe_count = basic_df['pe'].notna().sum() if 'pe' in basic_df.columns else 0
            pb_count = basic_df['pb'].notna().sum() if 'pb' in basic_df.columns else 0
            close_count = basic_df['close'].notna().sum() if 'close' in basic_df.columns else 0
            
            # Count non-zero data
            pe_nonzero = (basic_df['pe'] > 0).sum() if 'pe' in basic_df.columns else 0
            pb_nonzero = (basic_df['pb'] > 0).sum() if 'pb' in basic_df.columns else 0
            
            print(f"\n   📈 Statistics:")
            print(f"     Stocks with PE data: {pe_count}only (non-zero: {pe_nonzero}only)")
            print(f"     Stocks with petabytes of data: {pb_count}only (non-zero: {pb_nonzero}only)")
            print(f"     Stocks with closing price data: {close_count}only")
            
        else:
            print("❌ daily_basic Data acquisition failed")
        
    except Exception as e:
        print(f"❌ Adapter test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_baostock_stock_types()
    test_baostock_adapter_stock_filter()
