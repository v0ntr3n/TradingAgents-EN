#!/usr/bin/env python3
"""
Test the BaoStock valuation indicator function
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

def test_baostock_valuation_direct():
    """Directly test BaoStock valuation indicators API"""
    print("=" * 60)
    print("🧪 Directly test BaoStock valuation indicators API")
    print("=" * 60)
    
    try:
        import baostock as bs
        
        # Login BaoStock
        lg = bs.login()
        if lg.error_code != '0':
            print(f"❌ BaoStock Login failed: {lg.error_msg}")
            return
        
        print("✅ BaoStock Login successful")
        
        # Test ticker
        test_codes = ['sh.600000', 'sz.000001', 'sh.600519']
        trade_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        print(f"📅 Test date: {trade_date}")
        
        for code in test_codes:
            print(f"\n📊 test stocks: {code}")
            print("-" * 30)
            
            try:
                # Get valuation metrics
                rs = bs.query_history_k_data_plus(
                    code,
                    "date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM",
                    start_date=trade_date,
                    end_date=trade_date,
                    frequency="d",
                    adjustflag="3"
                )
                
                if rs.error_code == '0':
                    result_list = []
                    while (rs.error_code == '0') & rs.next():
                        result_list.append(rs.get_row_data())
                    
                    if result_list:
                        row = result_list[0]
                        print(f"✅ Valuation data obtained successfully:")
                        print(f"   Date: {row[0]}")
                        print(f"   code: {row[1]}")
                        print(f"   closing price: {row[2]}")
                        print(f"   rolling price to earnings ratio(peTTM): {row[3]}")
                        print(f"   price to book ratio(pbMRQ): {row[4]}")
                        print(f"   rolling price-to-sales ratio(psTTM): {row[5]}")
                        print(f"   rolling price to cash ratio(pcfNcfTTM): {row[6]}")
                    else:
                        print(f"⚠️ No data returned")
                else:
                    print(f"❌ Query failed: {rs.error_msg}")
                    
            except Exception as e:
                print(f"❌ test failed: {e}")
        
        # Log out
        bs.logout()
        print(f"\n✅ BaoStock Direct API testing completed")
        
    except ImportError:
        print("❌ BaoStock Not installed")
    except Exception as e:
        print(f"❌ test failed: {e}")

def test_baostock_provider_valuation():
    """Test the valuation function of BaoStock Provider"""
    print("\n" + "=" * 60)
    print("🧪 Test BaoStock Provider valuation function")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.baostock_utils import get_baostock_provider
        
        provider = get_baostock_provider()
        
        # Test ticker
        test_symbols = ['600000', '000001', '600519']
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        print(f"📅 Test date range: {start_date} Arrive {end_date}")
        
        for symbol in test_symbols:
            print(f"\n📊 test stocks: {symbol}")
            print("-" * 30)
            
            try:
                # Test valuation data acquisition
                valuation_df = provider.get_valuation_data(symbol, start_date, end_date)
                
                if not valuation_df.empty:
                    print(f"✅ Valuation data obtained successfully: {len(valuation_df)}records")
                    print(f"   List: {list(valuation_df.columns)}")
                    
                    # Show latest data
                    if len(valuation_df) > 0:
                        latest = valuation_df.iloc[-1]
                        print(f"   latest data:")
                        print(f"     Date: {latest.get('date', 'N/A')}")
                        print(f"     closing price: {latest.get('close', 'N/A')}")
                        print(f"     PE(TTM): {latest.get('peTTM', 'N/A')}")
                        print(f"     PB(MRQ): {latest.get('pbMRQ', 'N/A')}")
                        print(f"     PS(TTM): {latest.get('psTTM', 'N/A')}")
                        print(f"     PCF(TTM): {latest.get('pcfNcfTTM', 'N/A')}")
                else:
                    print(f"⚠️ No valuation data obtained")
                    
            except Exception as e:
                print(f"❌ test failed: {e}")
        
        print(f"\n✅ BaoStock Provider Valuation test completed")
        
    except Exception as e:
        print(f"❌ Provider test failed: {e}")
        import traceback
        traceback.print_exc()

def test_baostock_adapter_daily_basic():
    """Test the daily_basic function of the BaoStock adapter"""
    print("\n" + "=" * 60)
    print("🧪 Test BaoStock adapter daily_basic function")
    print("=" * 60)
    
    try:
        from app.services.data_source_adapters import BaoStockAdapter
        
        adapter = BaoStockAdapter()
        
        if not adapter.is_available():
            print("❌ BaoStock Adapter not available")
            return
        
        print("✅ BaoStock Adapters available")
        
        # Test to obtain daily_basic data
        trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        print(f"📅 get{trade_date}daily_basic data...")
        
        df = adapter.get_daily_basic(trade_date)
        
        if df is not None and not df.empty:
            print(f"✅ daily_basic Data acquisition successful: {len(df)}records")
            print(f"   List: {list(df.columns)}")
            
            # Show first few records
            print(f"\n📊 First 5 records:")
            for i, row in df.head().iterrows():
                print(f"   {i+1}. {row.get('ts_code', 'N/A')} - {row.get('name', 'N/A')}")
                print(f"      PE: {row.get('pe', 'N/A')}, PB: {row.get('pb', 'N/A')}")
                print(f"      closing price: {row.get('close', 'N/A')}")
            
            # Statistically valid data
            pe_count = df['pe'].notna().sum() if 'pe' in df.columns else 0
            pb_count = df['pb'].notna().sum() if 'pb' in df.columns else 0
            
            print(f"\n📈 Statistics:")
            print(f"   Stocks with PE data: {pe_count}only")
            print(f"   Stocks with petabytes of data: {pb_count}only")
            
        else:
            print(f"❌ daily_basic data not obtained")
        
        print(f"\n✅ BaoStock Adapter test completed")
        
    except Exception as e:
        print(f"❌ Adapter test failed: {e}")
        import traceback
        traceback.print_exc()

def test_data_source_manager_with_baostock():
    """Testing the BaoStock functionality in the Data Source Manager"""
    print("\n" + "=" * 60)
    print("🧪 Testing the BaoStock functionality in the Data Source Manager")
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
            
            # Test fallback mechanism
            trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            print(f"📅 Test fallback mechanism acquisition{trade_date}data...")
            
            df, source = manager.get_daily_basic_with_fallback(trade_date)
            
            if df is not None and not df.empty:
                print(f"✅ Fallback get success: {len(df)}record, source: {source}")
                
                if source == 'baostock':
                    print(f"🎯 Used BaoStock data source!")
                    # Check out BaoStock-specific valuation metrics
                    if 'ps' in df.columns:
                        ps_count = df['ps'].notna().sum()
                        print(f"   price to sales ratio(PS)data: {ps_count}only stocks")
                    if 'pcf' in df.columns:
                        pcf_count = df['pcf'].notna().sum()
                        print(f"   price to cash ratio(PCF)data: {pcf_count}only stocks")
                else:
                    print(f"ℹ️ Other data sources used: {source}")
            else:
                print(f"❌ Fallback Failed to obtain")
        else:
            print(f"❌ BaoStock adapter not found")
        
        print(f"\n✅ Data source manager testing completed")
        
    except Exception as e:
        print(f"❌ Data source manager test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_baostock_valuation_direct()
    test_baostock_provider_valuation()
    test_baostock_adapter_daily_basic()
    test_data_source_manager_with_baostock()
