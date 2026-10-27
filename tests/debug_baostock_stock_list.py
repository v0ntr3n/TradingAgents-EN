#!/usr/bin/env python3
"""
Debugging BaoStock stock list retrieval issue
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import pandas as pd

# Setup log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)

def debug_baostock_query_all_stock():
    """Debugging BaoStock s query_all_stock interface"""
    print("=" * 60)
    print("🔍 Debugging BaoStock s query_all_stock interface")
    print("=" * 60)
    
    try:
        import baostock as bs
        
        # Login BaoStock
        lg = bs.login()
        if lg.error_code != '0':
            print(f"❌ BaoStock Login failed: {lg.error_msg}")
            return
        
        print("✅ BaoStock Login successful")
        
        try:
            # Get basic stock information
            print("📊 call bs.query_all_stock()...")
            rs = bs.query_all_stock()
            
            print(f"   return code: {rs.error_code}")
            print(f"   return message: {rs.error_msg}")
            print(f"   Field list: {rs.fields}")
            
            if rs.error_code != '0':
                print(f"❌ Query failed: {rs.error_msg}")
                return
            
            # Parse data
            data_list = []
            count = 0
            while (rs.error_code == '0') & rs.next():
                row = rs.get_row_data()
                data_list.append(row)
                count += 1
                if count <= 10:  # Only show the first 10 items
                    print(f"   No.{count}Article: {row}")
                if count >= 100:  # Limit the total number to avoid excessive output
                    break
            
            print(f"\n📈 Obtained in total {len(data_list)} records")
            
            if data_list:
                # Convert to DataFrame
                df = pd.DataFrame(data_list, columns=rs.fields)
                print(f"   DataFrame shape: {df.shape}")
                print(f"   List: {list(df.columns)}")
                
                # Check A-share stocks
                if 'code' in df.columns:
                    print(f"\n🔍 Analyze stock symbol format:")
                    code_samples = df['code'].head(20).tolist()
                    print(f"   first 20 codes: {code_samples}")
                    
                    # Check A-share filters
                    a_stock_pattern = r'^(sh|sz)\.[0-9]{6}$'
                    a_stocks = df[df['code'].str.contains(a_stock_pattern, na=False)]
                    print(f"   The number of stocks matching the A-share pattern: {len(a_stocks)}")
                    
                    if len(a_stocks) > 0:
                        print(f"   A stock sample:")
                        for i, row in a_stocks.head(5).iterrows():
                            print(f"     {row['code']} - {row.get('code_name', 'N/A')}")
                    else:
                        print(f"   ❌ No stocks matching the A-share pattern were found!")
                        print(f"   All code format samples:")
                        unique_patterns = df['code'].str.extract(r'^([a-z]+)\.').iloc[:, 0].value_counts()
                        print(f"     {unique_patterns}")
                else:
                    print(f"   ❌ not found'code'Column")
            else:
                print(f"   ❌ No data was obtained")
                
        finally:
            bs.logout()
            print("✅ BaoStock Logout successful")
        
    except ImportError:
        print("❌ BaoStock Not installed")
    except Exception as e:
        print(f"❌ Debugging failed: {e}")
        import traceback
        traceback.print_exc()

def debug_baostock_stock_basic():
    """Debugging BaoStock s query_stock_basic interface"""
    print("\n" + "=" * 60)
    print("🔍 Debugging BaoStock s query_stock_basic interface")
    print("=" * 60)
    
    try:
        import baostock as bs
        
        # Login BaoStock
        lg = bs.login()
        if lg.error_code != '0':
            print(f"❌ BaoStock Login failed: {lg.error_msg}")
            return
        
        print("✅ BaoStock Login successful")
        
        # Test several known stock symbols
        test_codes = ['sh.600000', 'sz.000001', 'sh.600519']
        
        for code in test_codes:
            print(f"\n📊 test stocks: {code}")
            try:
                rs = bs.query_stock_basic(code=code)
                print(f"   return code: {rs.error_code}")
                print(f"   return message: {rs.error_msg}")
                
                if rs.error_code == '0':
                    data_list = []
                    while (rs.error_code == '0') & rs.next():
                        data_list.append(rs.get_row_data())
                    
                    if data_list:
                        print(f"   ✅ get success: {data_list[0]}")
                    else:
                        print(f"   ⚠️ No data returned")
                else:
                    print(f"   ❌ Query failed: {rs.error_msg}")
                    
            except Exception as e:
                print(f"   ❌ Abnormal: {e}")
        
        bs.logout()
        print("\n✅ BaoStock Logout successful")
        
    except Exception as e:
        print(f"❌ Debugging failed: {e}")

def test_baostock_adapter_stock_list():
    """Test the stock list acquisition of BaoStock adapter"""
    print("\n" + "=" * 60)
    print("🔍 Test the stock list acquisition of BaoStock adapter")
    print("=" * 60)
    
    try:
        from app.services.data_source_adapters import BaoStockAdapter
        
        adapter = BaoStockAdapter()
        
        if not adapter.is_available():
            print("❌ BaoStock Adapter not available")
            return
        
        print("✅ BaoStock Adapters available")
        
        # Get a list of stocks
        print("📊 call adapter.get_stock_list()...")
        df = adapter.get_stock_list()
        
        if df is not None and not df.empty:
            print(f"✅ Stock list obtained successfully: {len(df)}records")
            print(f"   List: {list(df.columns)}")
            print(f"   First 5 records:")
            for i, row in df.head().iterrows():
                print(f"     {row.get('symbol', 'N/A')} - {row.get('name', 'N/A')} - {row.get('ts_code', 'N/A')}")
        else:
            print("❌ Failed to obtain stock list")
        
    except Exception as e:
        print(f"❌ Adapter test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_baostock_query_all_stock()
    debug_baostock_stock_basic()
    test_baostock_adapter_stock_list()
