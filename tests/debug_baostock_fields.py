#!/usr/bin/env python3
"""
Debugging the field structure returned by BaoStock
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import pandas as pd
from datetime import datetime, timedelta

# Setup log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)

def debug_baostock_fields():
    """Debugging the field structure returned by BaoStock"""
    print("=" * 60)
    print("🔍 Debugging the field structure returned by BaoStock")
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
            # Parse data
            data_list = []
            count = 0
            while (rs.error_code == '0') & rs.next():
                row = rs.get_row_data()
                data_list.append(row)
                count += 1
                if count <= 10:  # Show the first 10 items
                    print(f"No.{count}Article: {row}")
                if count >= 100:  # total limit
                    break
            
            print(f"\n📊 Obtained in total {len(data_list)} records")
            
            if data_list:
                # Convert to DataFrame
                df = pd.DataFrame(data_list, columns=rs.fields)
                print(f"DataFrame shape: {df.shape}")
                print(f"List: {list(df.columns)}")
                print(f"First 5 rows of data:")
                print(df.head())
                
                # Analyze A-share stocks
                print(f"\n🔍 Analyze A-share stocks:")
                a_stock_pattern = r'^(sh|sz)\.[0-9]{6}$'
                a_stocks = df[df['code'].str.contains(a_stock_pattern, na=False)]
                print(f"The number of stocks matching the A-share pattern: {len(a_stocks)}")
                
                if len(a_stocks) > 0:
                    print(f"A stock sample:")
                    print(a_stocks.head())
                    
                    # Check field mapping
                    print(f"\n📋 Field mapping analysis:")
                    print(f"code -> symbol: {a_stocks['code'].head(3).tolist()}")
                    if 'code_name' in a_stocks.columns:
                        print(f"code_name -> name: {a_stocks['code_name'].head(3).tolist()}")
                    if 'tradeStatus' in a_stocks.columns:
                        print(f"tradeStatus: {a_stocks['tradeStatus'].head(3).tolist()}")
        
        bs.logout()
        print("\n✅ BaoStock Logout successful")
        
    except Exception as e:
        print(f"❌ Debugging failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_baostock_fields()
