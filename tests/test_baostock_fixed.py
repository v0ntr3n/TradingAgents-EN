#!/usr/bin/env python3
"""
Test the repaired BaoStock functionality
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

def test_baostock_query_all_stock_with_date():
    """Test with date parameter query_all_stock"""
    print("=" * 60)
    print("🧪 Test with date parameter BaoStock query_all_stock")
    print("=" * 60)
    
    try:
        import baostock as bs
        
        # Login BaoStock
        lg = bs.login()
        if lg.error_code != '0':
            print(f"❌ BaoStock Login failed: {lg.error_msg}")
            return
        
        print("✅ BaoStock Login successful")
        
        # Test different dates
        test_dates = [
            (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),  # yesterday
            (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),  # the day before yesterday
            "2024-12-31",  # fixed date
        ]
        
        for test_date in test_dates:
            print(f"\n📅 Test date: {test_date}")
            try:
                rs = bs.query_all_stock(day=test_date)
                print(f"   return code: {rs.error_code}")
                print(f"   return message: {rs.error_msg}")
                
                if rs.error_code == '0':
                    # Parse data
                    data_list = []
                    count = 0
                    while (rs.error_code == '0') & rs.next():
                        row = rs.get_row_data()
                        data_list.append(row)
                        count += 1
                        if count <= 5:  # Only show the first 5 items
                            print(f"     No.{count}Article: {row}")
                        if count >= 50:  # total limit
                            break
                    
                    print(f"   ✅ Get {len(data_list)} records")
                    
                    # Analyze A-share stocks
                    a_stocks = [row for row in data_list if row[0].startswith(('sh.', 'sz.')) and len(row[0]) == 9]
                    print(f"   📊 A number of shares: {len(a_stocks)}")
                    
                    if len(a_stocks) > 0:
                        print(f"   A stock sample:")
                        for i, row in enumerate(a_stocks[:3]):
                            print(f"     {row[0]} - {row[2]}")
                        break  # Exit when valid data is found
                else:
                    print(f"   ❌ Query failed: {rs.error_msg}")
                    
            except Exception as e:
                print(f"   ❌ Abnormal: {e}")
        
        bs.logout()
        print("\n✅ BaoStock Logout successful")
        
    except Exception as e:
        print(f"❌ test failed: {e}")

def test_baostock_adapter_fixed():
    """Test the repaired BaoStock adapter"""
    print("\n" + "=" * 60)
    print("🧪 Test the repaired BaoStock adapter")
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
            print(f"   First 5 records:")
            for i, row in df.head().iterrows():
                print(f"     {row.get('symbol', 'N/A')} - {row.get('name', 'N/A')} - {row.get('ts_code', 'N/A')}")
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
            print(f"   First 5 records:")
            for i, row in basic_df.head().iterrows():
                print(f"     {row.get('ts_code', 'N/A')} - {row.get('name', 'N/A')}")
                print(f"       PE: {row.get('pe', 'N/A')}, PB: {row.get('pb', 'N/A')}")
                print(f"       closing price: {row.get('close', 'N/A')}")
            
            # Statistically valid data
            pe_count = basic_df['pe'].notna().sum() if 'pe' in basic_df.columns else 0
            pb_count = basic_df['pb'].notna().sum() if 'pb' in basic_df.columns else 0
            close_count = basic_df['close'].notna().sum() if 'close' in basic_df.columns else 0
            
            print(f"\n   📈 Statistics:")
            print(f"     Stocks with PE data: {pe_count}only")
            print(f"     Stocks with petabytes of data: {pb_count}only")
            print(f"     Stocks with closing price data: {close_count}only")
            
        else:
            print("❌ daily_basic Data acquisition failed")
        
    except Exception as e:
        print(f"❌ Adapter test failed: {e}")
        import traceback
        traceback.print_exc()

def test_data_source_manager_baostock():
    """Test the data source manager BaoStock"""
    print("\n" + "=" * 60)
    print("🧪 Test the data source manager BaoStock")
    print("=" * 60)
    
    try:
        from app.services.data_source_adapters import DataSourceManager
        
        manager = DataSourceManager()
        available_adapters = manager.get_available_adapters()
        
        print(f"✅ Available data sources: {[adapter.name for adapter in available_adapters]}")
        
        # Find BaoStock adapter
        baostock_adapter = None
        for adapter in available_adapters:
            if adapter.name == 'baostock':
                baostock_adapter = adapter
                break
        
        if baostock_adapter:
            print(f"✅ Find BaoStock adapter, priority: {baostock_adapter.priority}")
            
            # Get test stock list
            print("\n📊 Get test stock list...")
            stock_df, source = manager.get_stock_list_with_fallback()
            
            if stock_df is not None and not stock_df.empty:
                print(f"✅ Stock list obtained successfully: {len(stock_df)}record, source: {source}")
                
                if source == 'baostock':
                    print(f"🎯 Used BaoStock data source!")
                else:
                    print(f"ℹ️ Other data sources used: {source}")
            else:
                print(f"❌ Failed to obtain stock list")
            
            # Test daily_basic acquisition
            print("\n📊 Test daily_basic acquisition...")
            trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            
            basic_df, source = manager.get_daily_basic_with_fallback(trade_date)
            
            if basic_df is not None and not basic_df.empty:
                print(f"✅ daily_basic get success: {len(basic_df)}record, source: {source}")
                
                if source == 'baostock':
                    print(f"🎯 Used BaoStock data source!")
                    # Check out BaoStock-specific valuation metrics
                    if 'ps' in basic_df.columns:
                        ps_count = basic_df['ps'].notna().sum()
                        print(f"   price to sales ratio(PS)data: {ps_count}only stocks")
                    if 'pcf' in basic_df.columns:
                        pcf_count = basic_df['pcf'].notna().sum()
                        print(f"   price to cash ratio(PCF)data: {pcf_count}only stocks")
                else:
                    print(f"ℹ️ Other data sources used: {source}")
            else:
                print(f"❌ daily_basic Failed to obtain")
        else:
            print(f"❌ BaoStock adapter not found")
        
    except Exception as e:
        print(f"❌ Data source manager test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_baostock_query_all_stock_with_date()
    test_baostock_adapter_fixed()
    test_data_source_manager_baostock()
