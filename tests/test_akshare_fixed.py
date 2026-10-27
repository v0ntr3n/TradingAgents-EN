#!/usr/bin/env python3
"""
Test the repaired AKShare functionality
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

def test_akshare_adapter_fixed():
    """Test the repaired AKShare adapter"""
    print("=" * 60)
    print("🧪 Test the repaired AKShare adapter")
    print("=" * 60)
    
    try:
        from app.services.data_source_adapters import AKShareAdapter
        
        adapter = AKShareAdapter()
        
        if not adapter.is_available():
            print("❌ AKShare Adapter not available")
            return
        
        print("✅ AKShare Adapters available")
        
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
            print(f"   First 10 records:")
            for i, row in basic_df.head(10).iterrows():
                ts_code = row.get('ts_code', 'N/A')
                name = row.get('name', 'N/A')
                close = row.get('close', 'N/A')
                total_mv = row.get('total_mv', 'N/A')
                turnover_rate = row.get('turnover_rate', 'N/A')
                print(f"     {ts_code} - {name}")
                print(f"       closing price: {close}, Total market capitalization: {total_mv}, turnover rate: {turnover_rate}")
            
            # Statistically valid data
            close_count = basic_df['close'].notna().sum() if 'close' in basic_df.columns else 0
            mv_count = basic_df['total_mv'].notna().sum() if 'total_mv' in basic_df.columns else 0
            turnover_count = basic_df['turnover_rate'].notna().sum() if 'turnover_rate' in basic_df.columns else 0
            
            # Count non-zero data
            close_nonzero = (basic_df['close'] > 0).sum() if 'close' in basic_df.columns else 0
            mv_nonzero = (basic_df['total_mv'] > 0).sum() if 'total_mv' in basic_df.columns else 0
            
            print(f"\n   📈 Statistics:")
            print(f"     Stocks with closing price data: {close_count}only (non-zero: {close_nonzero}only)")
            print(f"     Stocks with total market capitalization data: {mv_count}only (non-zero: {mv_nonzero}only)")
            print(f"     Stocks with turnover data: {turnover_count}only")
            
        else:
            print("❌ daily_basic Data acquisition failed")
        
    except Exception as e:
        print(f"❌ Adapter test failed: {e}")
        import traceback
        traceback.print_exc()

def test_data_source_manager_akshare():
    """Test the data source manager AKShare"""
    print("\n" + "=" * 60)
    print("🧪 Test the data source manager AKShare")
    print("=" * 60)
    
    try:
        from app.services.data_source_adapters import DataSourceManager
        
        manager = DataSourceManager()
        available_adapters = manager.get_available_adapters()
        
        print(f"✅ Available data sources: {[adapter.name for adapter in available_adapters]}")
        
        # Find AKShare adapter
        akshare_adapter = None
        for adapter in available_adapters:
            if adapter.name == 'akshare':
                akshare_adapter = adapter
                break
        
        if akshare_adapter:
            print(f"✅ Find AKShare adapter, priority: {akshare_adapter.priority}")
            
            # Test fallback mechanism
            trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            print(f"📅 Test fallback mechanism acquisition{trade_date}data...")
            
            df, source = manager.get_daily_basic_with_fallback(trade_date)
            
            if df is not None and not df.empty:
                print(f"✅ Fallback get success: {len(df)}record, source: {source}")
                
                if source == 'akshare':
                    print(f"🎯 Used AKShare data source!")
                    # Check AKShare-specific data
                    if 'total_mv' in df.columns:
                        mv_count = df['total_mv'].notna().sum()
                        print(f"   Total market capitalization data: {mv_count}only stocks")
                    if 'turnover_rate' in df.columns:
                        turnover_count = df['turnover_rate'].notna().sum()
                        print(f"   Turnover data: {turnover_count}only stocks")
                else:
                    print(f"ℹ️ Other data sources used: {source}")
            else:
                print(f"❌ Fallback Failed to obtain")
        else:
            print(f"❌ AKShare adapter not found")
        
    except Exception as e:
        print(f"❌ Data source manager test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_akshare_adapter_fixed()
    test_data_source_manager_akshare()
