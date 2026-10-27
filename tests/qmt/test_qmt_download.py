"""Test QMT data download function"""
import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("🔍 QMT Data download test")
print("=" * 60)

# import xtquant
try:
    import xtquant.xtdata as xt
    print("✅ xtquant Import successful")
except ImportError as e:
    print(f"❌ xtquant Import failed: {e}")
    sys.exit(1)

# Test downloading single stock data
print("\n" + "=" * 60)
print("test 1: Download historical data for a single stock")
print("=" * 60)

stock_code = "000001.SZ"  # Ping An Bank
print(f"Stock code: {stock_code}")
print(f"cycle: daily line (1d)")
print(f"start time: 20240101")

try:
    print("\n Start downloading...")
    result = xt.download_history_data(
        stock_code=stock_code,
        period="1d",
        start_time="20240101"
    )
    print(f"Download results: {result}")
    
    # Try to get data
    print("\n Try to get the downloaded data...")
    data = xt.get_market_data(
        field_list=["open", "high", "low", "close", "volume", "amount"],
        stock_list=[stock_code],
        period="1d",
        count=5
    )
    
    if data and stock_code in data:
        df = data[stock_code]
        if not df.empty:
            print(f"✅ Data obtained successfully")
            print(f"   data shape: {df.shape}")
            print(f"\n Data for the last 5 days:")
            print(df)
        else:
            print(f"❌ Data is empty")
    else:
        print(f"❌ No data obtained")
        
except Exception as e:
    print(f"❌ failed: {e}")
    import traceback
    traceback.print_exc()

# Test batch download
print("\n" + "=" * 60)
print("test 2: Download stock data in batches")
print("=" * 60)

stock_list = ["000001.SZ", "600000.SH", "000002.SZ"]
print(f"stock list: {stock_list}")

try:
    print("\n Start batch download...")
    for stock in stock_list:
        print(f"  Download {stock}...")
        result = xt.download_history_data(
            stock_code=stock,
            period="1d",
            start_time="20240101"
        )
        print(f"    result: {result}")
    
    print("\n Try to get batch data...")
    data = xt.get_market_data(
        field_list=["close"],
        stock_list=stock_list,
        period="1d",
        count=1
    )
    
    if data:
        print(f"✅ Successfully obtained batch data")
        for stock in stock_list:
            if stock in data:
                df = data[stock]
                if not df.empty:
                    print(f"  {stock}: {df['close'].iloc[-1] if 'close' in df.columns else 'N/A'}")
                else:
                    print(f"  {stock}: Data is empty")
    else:
        print(f"❌ Batch data not obtained")
        
except Exception as e:
    print(f"❌ failed: {e}")
    import traceback
    traceback.print_exc()

# Test to obtain local existing data
print("\n" + "=" * 60)
print("test 3: Check local data path")
print("=" * 60)

try:
    # Get data path
    import os
    data_path = "D:\\gjzq\\bin.x64\\..\\userdata_mini\\datadir"
    print(f"data path: {data_path}")
    
    if os.path.exists(data_path):
        print(f"✅ data path exists")
        # List some files
        files = os.listdir(data_path)
        print(f"   Number of files: {len(files)}")
        if files:
            print(f"   first 5 files: {files[:5]}")
    else:
        print(f"❌ Data path does not exist")
        
except Exception as e:
    print(f"❌ Check failed: {e}")

print("\n" + "=" * 60)
print("✅ Test completed")
print("=" * 60)
print("\n💡 Tips:")
print("1. If the download fails, please check if MiniQMT is logged in")
print("2. Some brokerage versions may require manual downloading of data in the MiniQMT interface.")
print("3. Data management functions can be viewed in MiniQMT")

