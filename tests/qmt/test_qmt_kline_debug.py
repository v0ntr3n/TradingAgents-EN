"""Debugging QMT K-line data acquisition"""
import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timedelta

print("=" * 60)
print("🔍 QMT K Line data acquisition and debugging")
print("=" * 60)

# import xtquant
try:
    import xtquant.xtdata as xt
    print("✅ xtquant Import successful")
except ImportError as e:
    print(f"❌ xtquant Import failed: {e}")
    sys.exit(1)

# test connection
print("\n Check xtdata connection...")
try:
    ticks = xt.get_full_tick([])
    print(f"✅ xtdata Connection successful")
except Exception as e:
    print(f"❌ xtdata Connection failed: {e}")
    sys.exit(1)

# Test to obtain K-line data
print("\n" + "=" * 60)
print("test 1: Use the count parameter to get the last 5 days of data")
print("=" * 60)

stock_code = "000001.SZ"  # Ping An Bank
print(f"Stock code: {stock_code}")

try:
    # method 1: Use count parameter (recommended)
    data1 = xt.get_market_data(
        field_list=["open", "high", "low", "close", "volume", "amount"],
        stock_list=[stock_code],
        period="1d",
        count=5  # Get the last 5 pieces of data
    )
    
    if data1 and stock_code in data1:
        df = data1[stock_code]
        print(f"✅ Successfully retrieved data (using count)")
        print(f"   data type: {type(df)}")
        print(f"   data shape: {df.shape if hasattr(df, 'shape') else 'N/A'}")
        print(f"\n Data content:")
        print(df)
    else:
        print(f"❌ No data obtained")
        print(f"   return value: {data1}")
        
except Exception as e:
    print(f"❌ Failed to obtain: {e}")
    import traceback
    traceback.print_exc()

# Test method 2: Use time range
print("\n" + "=" * 60)
print("test 2: Get data using time range")
print("=" * 60)

try:
    end = datetime.now()
    start = end - timedelta(days=10)
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")
    
    print(f"time range: {start_str} ~ {end_str}")
    
    data2 = xt.get_market_data(
        field_list=["open", "high", "low", "close", "volume", "amount"],
        stock_list=[stock_code],
        period="1d",
        start_time=start_str,
        end_time=end_str
    )
    
    if data2 and stock_code in data2:
        df = data2[stock_code]
        print(f"✅ Data fetched successfully (using time range)")
        print(f"   data type: {type(df)}")
        print(f"   data shape: {df.shape if hasattr(df, 'shape') else 'N/A'}")
        print(f"\n Data content:")
        print(df)
    else:
        print(f"❌ No data obtained")
        print(f"   return value: {data2}")
        
except Exception as e:
    print(f"❌ Failed to obtain: {e}")
    import traceback
    traceback.print_exc()

# Test method 3: Get historical data (use download_history_data)
print("\n" + "=" * 60)
print("test 3: Download historical data")
print("=" * 60)

try:
    print(f"try download {stock_code} historical data...")
    result = xt.download_history_data(
        stock_code=stock_code,
        period="1d",
        start_time="20240101"
    )
    print(f"Download results: {result}")
    
    # Try to get again
    data3 = xt.get_market_data(
        field_list=["open", "high", "low", "close", "volume", "amount"],
        stock_list=[stock_code],
        period="1d",
        count=5
    )
    
    if data3 and stock_code in data3:
        df = data3[stock_code]
        print(f"✅ Successfully obtained data after downloading")
        print(f"\n Data content:")
        print(df)
    else:
        print(f"❌ No data obtained after downloading")
        
except Exception as e:
    print(f"❌ Download failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("✅ Debugging completed")
print("=" * 60)

