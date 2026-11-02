#!/usr/bin/env python3
"""
Test AKShare performance optimization
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import time
from datetime import datetime, timedelta

# Setup log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)

def test_akshare_performance():
    """Test AKShare performance"""
    print("=" * 60)
    print("🚀 Test AKShare performance optimization")
    print("=" * 60)
    
    try:
        from app.services.data_source_adapters import AKShareAdapter
        
        adapter = AKShareAdapter()
        
        if not adapter.is_available():
            print("❌ AKShare Adapter not available")
            return
        
        print("✅ AKShare Adapters available")
        
        # Test daily_basic to get performance
        trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        print(f"📅 Test acquisition{trade_date}data...")
        
        start_time = time.time()
        df = adapter.get_daily_basic(trade_date)
        end_time = time.time()
        
        duration = end_time - start_time
        
        if df is not None and not df.empty:
            print(f"✅ daily_basic Data acquisition successful:")
            print(f"   📊 Record quantity: {len(df)}Article")
            print(f"   ⏱️ Time consuming: {duration:.1f}seconds")
            print(f"   🚀 average speed: {len(df)/duration:.1f}bars/second")
            
            # Check data quality
            close_count = df['close'].notna().sum() if 'close' in df.columns else 0
            mv_count = df['total_mv'].notna().sum() if 'total_mv' in df.columns else 0
            
            print(f"   📈 Data quality:")
            print(f"     There is closing price data: {close_count}only ({close_count/len(df)*100:.1f}%)")
            print(f"     There is total market capitalization data: {mv_count}only ({mv_count/len(df)*100:.1f}%)")
            
            # Show sample data
            print(f"   📋 sample data:")
            for i, row in df.head(3).iterrows():
                ts_code = row.get('ts_code', 'N/A')
                name = row.get('name', 'N/A')
                close = row.get('close', 'N/A')
                total_mv = row.get('total_mv', 'N/A')
                print(f"     {ts_code} - {name}: price={close}, Market value={total_mv}")
            
            # Performance evaluation
            if duration < 30:
                print(f"   🎯 Performance evaluation: Excellent (< 30 seconds)")
            elif duration < 60:
                print(f"   ⚠️ Performance evaluation: acceptable (< 60 seconds)")
            else:
                print(f"   ❌ Performance evaluation: Need optimization (> 60 seconds)")
                
        else:
            print(f"❌ daily_basic Data acquisition failed, time consuming: {duration:.1f}seconds")
        
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        import traceback
        traceback.print_exc()

def test_web_api_simulation():
    """Simulate Web API calls"""
    print("\n" + "=" * 60)
    print("🌐 Simulate Web API call testing")
    print("=" * 60)
    
    try:
        from app.services.data_source_adapters import DataSourceManager
        
        manager = DataSourceManager()
        
        # Simulate the test logic of Web API
        print("📊 Simulate test AKShare data source...")
        
        start_time = time.time()
        
        # 1. Test stock list
        print("   1. Get test stock list...")
        stock_start = time.time()
        
        # Find the AKShare adapter
        akshare_adapter = None
        for adapter in manager.get_available_adapters():
            if adapter.name == 'akshare':
                akshare_adapter = adapter
                break
        
        if not akshare_adapter:
            print("   ❌ AKShare adapter not found")
            return
        
        stock_df = akshare_adapter.get_stock_list()
        stock_time = time.time() - stock_start
        
        if stock_df is not None and not stock_df.empty:
            print(f"   ✅ stock list: {len(stock_df)}records, time consuming: {stock_time:.1f}seconds")
        else:
            print(f"   ❌ Failed to obtain stock list")
            return
        
        # 2. Test transaction date
        print("   2. Test transaction date acquisition...")
        date_start = time.time()
        latest_date = akshare_adapter.get_latest_trade_date()
        date_time = time.time() - date_start
        print(f"   ✅ Latest transaction date: {latest_date}, Time consuming: {date_time:.1f}seconds")
        
        # 3. Test financial data
        print("   3. Test financial data acquisition...")
        basic_start = time.time()
        basic_df = akshare_adapter.get_daily_basic(latest_date)
        basic_time = time.time() - basic_start
        
        if basic_df is not None and not basic_df.empty:
            print(f"   ✅ financial data: {len(basic_df)}records, time consuming: {basic_time:.1f}seconds")
        else:
            print(f"   ❌ Failed to obtain financial data, time consuming: {basic_time:.1f}seconds")
        
        total_time = time.time() - start_time
        print(f"\n📊 Overall test results:")
        print(f"   Total time spent: {total_time:.1f}seconds")
        print(f"   stock list: {stock_time:.1f}seconds")
        print(f"   transaction date: {date_time:.1f}seconds")
        print(f"   financial data: {basic_time:.1f}seconds")
        
        # Web Timeout evaluation
        if total_time < 30:
            print(f"   🎯 Web Compatibility: Excellent (< 30 seconds)")
        elif total_time < 60:
            print(f"   ⚠️ Web Compatibility: acceptable (< 60 seconds)")
        else:
            print(f"   ❌ Web Compatibility: Timeout risk (> 60 seconds)")
        
    except Exception as e:
        print(f"❌ Web API Mock test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_akshare_performance()
    test_web_api_simulation()
