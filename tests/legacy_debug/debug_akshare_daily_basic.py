#!/usr/bin/env python3
"""
Debugging AKShare s daily_basic function
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

def test_akshare_spot_data():
    """Test AKShare s real-time market data"""
    print("=" * 60)
    print("🧪 Test AKShare s real-time market data")
    print("=" * 60)
    
    try:
        import akshare as ak
        
        print("✅ AKShare Import successful")
        
        # Get real-time market data of A shares
        print("📊 call ak.stock_zh_a_spot_em()...")
        spot_data = ak.stock_zh_a_spot_em()
        
        if spot_data is not None and not spot_data.empty:
            print(f"✅ Real-time market data obtained successfully: {len(spot_data)}records")
            print(f"   List: {list(spot_data.columns)}")
            
            # Check if the required column exists
            required_cols = ['code', 'Name', 'Price Earning Ratio - Dynamic', 'price to book ratio', 'Total market capitalization']
            print(f"\n🔍 Check required columns:")
            for col in required_cols:
                exists = col in spot_data.columns
                print(f"   {col}: {'✅ exist' if exists else '❌ does not exist'}")
            
            # Show actual column names (subject to change)
            print(f"\n📋 Actual column names (top 20):")
            for i, col in enumerate(spot_data.columns[:20]):
                print(f"   {i+1:2d}. {col}")
            
            # Show the first few data
            print(f"\n📊 First 5 pieces of data:")
            print(spot_data.head())
            
            # Find possible PE, PB related columns
            print(f"\n🔍 Find PE and PB related columns:")
            pe_cols = [col for col in spot_data.columns if 'P/E ratio' in col or 'PE' in col or 'pe' in col]
            pb_cols = [col for col in spot_data.columns if 'price to book ratio' in col or 'PB' in col or 'pb' in col]
            mv_cols = [col for col in spot_data.columns if 'Market value' in col or 'Total market capitalization' in col]
            
            print(f"   PE Related columns: {pe_cols}")
            print(f"   PB Related columns: {pb_cols}")
            print(f"   Market capitalization related columns: {mv_cols}")
            
        else:
            print("❌ Failed to obtain real-time market data or is empty")
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()

def test_akshare_adapter():
    """Test the AKShare adapter"""
    print("\n" + "=" * 60)
    print("🧪 Test the AKShare adapter")
    print("=" * 60)
    
    try:
        from app.services.data_source_adapters import AKShareAdapter
        
        adapter = AKShareAdapter()
        
        if not adapter.is_available():
            print("❌ AKShare Adapter not available")
            return
        
        print("✅ AKShare Adapters available")
        
        # Test daily_basic acquisition
        trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        print(f"\n📅 Test acquisition{trade_date}daily_basic data...")
        
        df = adapter.get_daily_basic(trade_date)
        
        if df is not None and not df.empty:
            print(f"✅ daily_basic Data acquisition successful: {len(df)}records")
            print(f"   List: {list(df.columns)}")
            
            # Show first few records
            print(f"   First 5 records:")
            for i, row in df.head().iterrows():
                ts_code = row.get('ts_code', 'N/A')
                name = row.get('name', 'N/A')
                pe = row.get('pe', 'N/A')
                pb = row.get('pb', 'N/A')
                total_mv = row.get('total_mv', 'N/A')
                print(f"     {ts_code} - {name}")
                print(f"       PE: {pe}, PB: {pb}, Total market capitalization: {total_mv}")
            
            # Statistically valid data
            pe_count = df['pe'].notna().sum() if 'pe' in df.columns else 0
            pb_count = df['pb'].notna().sum() if 'pb' in df.columns else 0
            mv_count = df['total_mv'].notna().sum() if 'total_mv' in df.columns else 0
            
            print(f"\n   📈 Statistics:")
            print(f"     Stocks with PE data: {pe_count}only")
            print(f"     Stocks with petabytes of data: {pb_count}only")
            print(f"     Stocks with total market capitalization data: {mv_count}only")
            
        else:
            print("❌ daily_basic Data acquisition failed")
        
    except Exception as e:
        print(f"❌ Adapter test failed: {e}")
        import traceback
        traceback.print_exc()

def test_akshare_alternative_apis():
    """Test other financial data from AKShare API"""
    print("\n" + "=" * 60)
    print("🧪 Test other financial data from AKShare API")
    print("=" * 60)
    
    try:
        import akshare as ak
        
        # test different API
        apis_to_test = [
            ('stock_zh_a_spot_em', 'Oriental Fortune-Shanghai, Shenzhen and Beijing A-shares-real-time quotes'),
            ('stock_zh_a_hist_min_em', 'Oriental Fortune-Shanghai, Shenzhen and Beijing A shares-Historical minute quotes'),
            ('stock_individual_info_em', 'Oriental Fortune-Individual Stock Information'),
        ]
        
        for api_name, description in apis_to_test:
            print(f"\n📊 test {api_name} ({description}):")
            try:
                if api_name == 'stock_zh_a_spot_em':
                    data = ak.stock_zh_a_spot_em()
                elif api_name == 'stock_individual_info_em':
                    # Test individual stocks
                    data = ak.stock_individual_info_em(symbol="000001")
                else:
                    print(f"   ⏭️ Skip complex API testing")
                    continue
                
                if data is not None and not data.empty:
                    print(f"   ✅ success: {len(data)}records")
                    print(f"   List: {list(data.columns)[:10]}...")  # Only show the first 10 column names
                else:
                    print(f"   ❌ No data")
                    
            except Exception as e:
                print(f"   ❌ failed: {e}")
        
    except Exception as e:
        print(f"❌ test failed: {e}")

if __name__ == "__main__":
    test_akshare_spot_data()
    test_akshare_adapter()
    test_akshare_alternative_apis()
