"""
Test AKShare Hong Kong stock related interface
Verify which interfaces are available, as well as their functionality and return data
"""
import akshare as ak
import pandas as pd
from datetime import datetime

def print_separator(title):
    """Print dividers"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80 + "\n")

def test_api(api_name, api_func, *args, **kwargs):
    """Test a single API interface"""
    print(f"📊 test interface: {api_name}")
    print(f"   parameters: args={args}, kwargs={kwargs}")
    try:
        result = api_func(*args, **kwargs)
        
        if isinstance(result, pd.DataFrame):
            print(f"   ✅ success! Return DataFrame")
            print(f"   📈 Number of data rows: {len(result)}")
            print(f"   📋 List: {list(result.columns)}")
            print(f"\n   First 3 rows of data:")
            print(result.head(3).to_string())
            return True, result
        else:
            print(f"   ✅ success! Return type: {type(result)}")
            print(f"   data: {result}")
            return True, result
            
    except Exception as e:
        print(f"   ❌ failed: {e}")
        return False, None

def main():
    """Main test function"""
    
    # Test ticker
    test_symbol = "00700"  # Tencent Holdings
    
    print_separator("AKShare Hong Kong stock interface test")
    print(f"test stocks: {test_symbol} (Tencent Holdings)")
    print(f"Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # ========================================
    # 1. Real-time market interface
    # ========================================
    print_separator("1. Real-time market interface")
    
    # 1.1 Oriental Fortune - Real-time Hong Kong Stock Quotes
    success, df = test_api(
        "stock_hk_spot_em",
        ak.stock_hk_spot_em
    )
    if success and df is not None:
        # Find Tencent Holdings
        matched = df[df['code'] == test_symbol]
        if not matched.empty:
            print(f"\n   🎯 found {test_symbol}:")
            print(matched.to_string())
    
    # 1.2 Oriental Fortune - Hong Kong stock main board real-time quotes
    success, df = test_api(
        "stock_hk_main_board_spot_em",
        ak.stock_hk_main_board_spot_em
    )
    if success and df is not None:
        matched = df[df['code'] == test_symbol]
        if not matched.empty:
            print(f"\n   🎯 found {test_symbol}:")
            print(matched.to_string())
    
    # 1.3 Sina Finance - Real-time Hong Kong Stock Quotes
    try:
        success, df = test_api(
            "stock_hk_spot",
            ak.stock_hk_spot
        )
        if success and df is not None:
            # The column name of Sina interface is 'code', No 'symbol'
            matched = df[df['code'] == test_symbol]
            if not matched.empty:
                print(f"\n   🎯 found {test_symbol}:")
                print(matched.to_string())
    except AttributeError:
        print(f"   ⚠️ Interface stock_hk_spot does not exist")
    
    # ========================================
    # 2. Historical market interface
    # ========================================
    print_separator("2. Historical market interface")
    
    # 2.1 Sina Finance - Hong Kong Stock Market Historical Quotes
    success, df = test_api(
        "stock_hk_daily",
        ak.stock_hk_daily,
        symbol=test_symbol,
        adjust="qfq"  # Former restoration of rights
    )
    if success and df is not None:
        print(f"\n   📅 Last 5 trading days:")
        print(df.tail(5).to_string())
    
    # ========================================
    # 3. Individual stock information interface
    # ========================================
    print_separator("3. Individual stock information interface")
    
    # 3.1 Snowball - Hong Kong stock information
    try:
        success, result = test_api(
            "stock_individual_basic_info_hk_xq",
            ak.stock_individual_basic_info_hk_xq,
            symbol=test_symbol
        )
    except AttributeError:
        print(f"   ⚠️ Interface stock_individual_basic_info_hk_xq does not exist")
    except Exception as e:
        print(f"   ❌ call failed: {e}")
    
    # ========================================
    # 4. Stock list interface
    # ========================================
    print_separator("4. Stock list interface")
    
    # 4.1 Hong Kong stock list
    try:
        success, df = test_api(
            "stock_hk_list",
            ak.stock_hk_list
        )
    except AttributeError:
        print(f"   ⚠️ Interface stock_hk_list does not exist")
    
    # 4.2 Get a stock list from real-time quotes
    print(f"\n📊 Get the stock list from stock_hk_spot_em:")
    try:
        df = ak.stock_hk_spot_em()
        if df is not None and not df.empty:
            print(f"   ✅ total {len(df)} Only Hong Kong stocks")
            print(f"   📋 List: {list(df.columns)}")
            print(f"\n   Top 10 stocks:")
            print(df.head(10)[['code', 'Name', 'latest price', 'Increase or decrease']].to_string())
    except Exception as e:
        print(f"   ❌ failed: {e}")
    
    # ========================================
    # 5. Other possible interfaces
    # ========================================
    print_separator("5. Other Hong Kong stock related interfaces")
    
    # 5.1 Hong Kong Stock Connect constituent stocks
    try:
        success, df = test_api(
            "stock_hk_ggt_components_em",
            ak.stock_hk_ggt_components_em
        )
    except AttributeError:
        print(f"   ⚠️ Interface stock_hk_ggt_components_em does not exist")
    
    # 5.2 Hong Kong Stock Connect Fund Flow
    try:
        success, df = test_api(
            "stock_hk_ggt_hist_em",
            ak.stock_hk_ggt_hist_em
        )
    except AttributeError:
        print(f"   ⚠️ Interface stock_hk_ggt_hist_em does not exist")
    
    # ========================================
    # Summary
    # ========================================
    print_separator("Test summary")
    
    print("""
    📊 AKShare Summary of Hong Kong Stocks Interface:
    
    ✅ Available interfaces:
    1. stock_hk_spot_em - Oriental Fortune Hong Kong stock real-time quotes (Recommended)
       - contains: Code, name, latest price, increase or decrease, trading volume, etc.
       - Get a list of all Hong Kong stocks
       - The data is more comprehensive
    
    2. stock_hk_main_board_spot_em - Oriental Fortune Hong Kong stock main board real-time quotes
       - Only includes main board stocks
       - The data structure is similar to stock_hk_spot_em
    
    3. stock_hk_daily - Sina Finance Hong Kong stock market historical quotes
       - Stock code needs to be specified
       - Supports restoration of rights before and after restoration
       - contains: Date, opening, closing, highest, lowest, trading volume, etc.
    
    ⚠️ Things to note:
    - Some interfaces may not exist or may be obsolete
    - It is recommended to use stock_hk_spot_em as the main data source
    - Historical data usage stock_hk_daily
    """)

if __name__ == "__main__":
    main()

