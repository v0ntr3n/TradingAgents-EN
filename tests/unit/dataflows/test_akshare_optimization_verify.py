#!/usr/bin/env python3
"""
AKShare Optimization point verification test script

Verify content:
1. stock_zh_a_spot_em Fields returned by the batch interface (confirm whether PE/PB/total market capitalization/turnover rate are included)
2. stock_individual_info_em Field comparison of single query
3. find_latest_trade_date Does the asyncio.run bug actually trigger
4. stock_zh_a_hist Return structure of historical data interface

Operation mode:
    cd c:\TradingAgentsCN
    python tests/test_akshare_optimization_verify.py
"""
import asyncio
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def print_header(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_subheader(title: str):
    print(f"\n--- {title} ---")


def test_1_batch_vs_single_basic_data():
    """test 1: Compare the valuation data fields of batch interfaces vs single interfaces"""
    print_header("test 1: stock_zh_a_spot_em Batch interface vs stock_individual_info_em single interface")
    
    try:
        import akshare as ak
    except ImportError:
        print("❌ akshare Not installed, skip testing")
        return
    
    test_codes = ["000002", "600519", "000001"]  # Vanke, Moutai, Ping An Bank
    
    # ========== Bulk interface ==========
    print_subheader("1.1 Call stock_zh_a_spot_em (full market snapshot, 1 call)")
    start_time = time.time()
    try:
        df_batch = ak.stock_zh_a_spot_em()
        batch_elapsed = time.time() - start_time
        print(f"✅ Time consuming: {batch_elapsed:.2f}s, Return {len(df_batch)} only stocks")
        print(f"📋 List: {df_batch.columns.tolist()}")
        
        # Check if key fields are included
        required_fields = {
            "code": ["code", "symbol", "Stock code"],
            "Name": ["Name", "name"],
            "latest price": ["latest price", "Current price", "Latest"],
            "PE": ["Price Earning Ratio - Dynamic", "P/E ratio", "pe"],
            "PB": ["price to book ratio", "pb"],
            "Total market capitalization": ["Total market capitalization", "Total market capitalization(Yuan)"],
            "turnover rate": ["turnover rate", "turnover_rate"],
        }
        
        print_subheader("1.2 Key field matching")
        matched_fields = {}
        for field_name, possible_cols in required_fields.items():
            matched = [c for c in possible_cols if c in df_batch.columns]
            if matched:
                print(f"  ✅ {field_name}: find column '{matched[0]}'")
                matched_fields[field_name] = matched[0]
            else:
                print(f"  ❌ {field_name}: not found (expected column: {possible_cols}) ")
        
        # Print data for test stocks
        print_subheader("1.3 Test batch interface data for stocks")
        code_col = matched_fields.get("code", "code")
        for test_code in test_codes:
            row = df_batch[df_batch[code_col].astype(str).str.contains(test_code, na=False)]
            if not row.empty:
                print(f"\n  📊 {test_code}:")
                for field_name, col_name in matched_fields.items():
                    val = row.iloc[0].get(col_name)
                    print(f"     {field_name}: {val}")
            else:
                print(f"  ⚠️ {test_code} not found")
        
    except Exception as e:
        print(f"❌ stock_zh_a_spot_em call failed: {e}")
        return
    
    # ========== single interface ==========
    print_subheader("1.4 Call stock_individual_info_em (single query, 3 calls)")
    single_total_time = 0
    for test_code in test_codes:
        start_time = time.time()
        try:
            info_df = ak.stock_individual_info_em(symbol=test_code)
            elapsed = time.time() - start_time
            single_total_time += elapsed
            print(f"\n  📊 {test_code} (Time consuming {elapsed:.2f}s):")
            if info_df is not None and not info_df.empty:
                info_dict = dict(zip(info_df['item'], info_df['value']))
                for key in ["stock abbreviation", "Latest", "Total market capitalization", "Circulation market value", "Industry", "time to market"]:
                    if key in info_dict:
                        print(f"     {key}: {info_dict[key]}")
        except Exception as e:
            print(f"  ❌ {test_code} Query failed: {e}")
    
    # ========== Comparison summary ==========
    print_subheader("1.5 Comparison summary")
    print(f"  Bulk interface: 1 calls, Time consuming {batch_elapsed:.2f}s, get {len(df_batch)} only stocks")
    print(f"  single interface: {len(test_codes)} calls, Time consuming {single_total_time:.2f}s, get {len(test_codes)} only stocks")
    print(f"  To get 5000 stocks:")
    print(f"    Bulk interface: 1 calls, ~{batch_elapsed:.0f}s")
    estimated_single = (single_total_time / len(test_codes)) * 5000
    print(f"    single interface: 5000 calls, ~{estimated_single:.0f}s ({estimated_single/60:.1f} minutes)")
    print(f"  Conclusion: Batch interface efficiency is improved by approx. {estimated_single / batch_elapsed:.0f} times")


def test_2_find_latest_trade_date_bug():
    """test 2: Verify that in find_latest_trade_date asyncio.run bug"""
    print_header("test 2: find_latest_trade_date in asyncio.run bug")
    
    print_subheader("2.1 Called in an asynchronous context asyncio.run() behavior")
    
    async def test_asyncio_run_in_async_context():
        """Code to simulate akshare_adapter.py L614"""
        print("  Try calling in an async context asyncio.run()...")
        try:
            # This is exactly how akshare_adapter.py L614 is written
            async def dummy_coro():
                return "ok"
            
            result = asyncio.run(dummy_coro())
            print(f"  ✅ asyncio.run() Return successfully: {result}")
            print(f"  ℹ️ Note: In some Python versions this may not report an error immediately, but it is potentially risky")
            return True
        except RuntimeError as e:
            if "cannot be called from a running event loop" in str(e):
                print(f"  ❌ Confirm Bug: {e}")
                print(f"  This is an expected error —— asyncio.run() cannot be called within a running event loop")
                return False
            else:
                print(f"  ⚠️ Others RuntimeError: {e}")
                return None
        except Exception as e:
            print(f"  ⚠️ Other exceptions: {type(e).__name__}: {e}")
            return None
    
    result = asyncio.run(test_asyncio_run_in_async_context())
    
    print_subheader("2.2 The correct way to write it should be")
    print("  # Wrong writing (current code):")
    print("    asyncio.run(cache_service.set_cached_trade_date('akshare', yesterday))")
    print()
    print("  # correct way to write 1: Use await")
    print("    await cache_service.set_cached_trade_date('akshare', yesterday)")
    print()
    print("  # correct way to write 2: Use synchronous methods (if available)")
    print("    cache_service.set_cached_trade_date_sync('akshare', yesterday)")
    print()
    print("  # Note: akshare_adapter.py L542 Synchronous method has been used set_cached_trade_date_sync")
    print("  # But the back-end branch of L614 uses asyncio.run, which is inconsistent.")


def test_3_historical_data_structure():
    """test 3: Verify the return structure of the stock_zh_a_hist historical data interface"""
    print_header("test 3: stock_zh_a_hist Historical data interface return structure")
    
    try:
        import akshare as ak
    except ImportError:
        print("❌ akshare Not installed, skip testing")
        return
    
    test_code = "000002"  # Vanke A (with data)
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    
    print_subheader(f"3.1 call stock_zh_a_hist({test_code}, daily, {start_date}~{end_date})")
    start_time = time.time()
    try:
        df = ak.stock_zh_a_hist(
            symbol=test_code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq"
        )
        elapsed = time.time() - start_time
        print(f"✅ Time consuming: {elapsed:.2f}s, Return {len(df)} records")
        print(f"📋 List: {df.columns.tolist()}")
        if not df.empty:
            print(f"\n First 3 rows of data:")
            print(df.head(3).to_string(index=False))
    except Exception as e:
        print(f"❌ call failed: {e}")
    
    print_subheader("3.2 Verify: stock_zh_a_hist It is a single query interface and cannot be used in batches.")
    print("  Conclusion: Historical data synchronization must be queried one by one, serially + Delay is the right anti-blocking strategy")
    print("  Optimization direction: The main force of historical synchronization is handed over to Tushare (paid API does not have the risk of IP blocking), and AKShare takes care of it.")


def test_4_summary():
    """test 4: Summary of optimization suggestions"""
    print_header("test 4: Summary of optimization suggestions")
    
    print("""
┌─────────────────────────────────────────────────────────────────────┐
│  Optimization items                          │ risk   │ income   │ Suggestions          │
├─────────────────────────────────────────────────────────────────────┤
│ 1. get_daily_basic Use batch interface instead  │ low     │ high     │ ✅ Prioritize     │
│    stock_zh_a_spot_em 1 calls    │        │        │              │
│    substitute stock_individual_info_em │        │        │              │
│    5000 calls                    │        │        │              │
├─────────────────────────────────────────────────────────────────────┤
│ 2. Repair asyncio.run bug          │ None     │ in     │ ✅ Easy to repair     │
│    L614 Use await or synchronized methods instead    │        │        │              │
├─────────────────────────────────────────────────────────────────────┤
│ 3. Historical synchronization remains serial               │ -      │ -      │ ⚠️ Don t be concurrent   │
│    AKShare A single query will be blocked IP      │        │        │              │
│    The main force is handed over to Tushare              │        │        │              │
└─────────────────────────────────────────────────────────────────────┘
""")


def main():
    print_header("AKShare Optimization point verification test")
    print(f"Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python: {sys.version.split()[0]}")
    
    try:
        import akshare as ak
        print(f"AKShare version: {ak.__version__}")
    except ImportError:
        print("❌ akshare Not installed")
        return
    except AttributeError:
        print("AKShare Installed (version number unknown)")
    
    # Execute tests
    test_1_batch_vs_single_basic_data()
    test_2_find_latest_trade_date_bug()
    test_3_historical_data_structure()
    test_4_summary()
    
    print_header("Test completed")


if __name__ == "__main__":
    main()
