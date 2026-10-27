"""
Test the stock code standardization and historical data import functions of the market warehousing service
"""
import asyncio
import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.quotes_ingestion_service import QuotesIngestionService
from app.core.database import get_mongo_db, init_db, close_db
from datetime import datetime


async def test_normalize_stock_code():
    """Testing the ticker standardization feature"""
    print("\n" + "="*60)
    print("test 1: Stock code normalization function")
    print("="*60)
    
    test_cases = [
        ("sz000001", "000001", "Shenzhen Ping An Bank"),
        ("sh600036", "600036", "Shanghai China Merchants Bank"),
        ("000001", "000001", "Standard 6-digit code"),
        ("1", "000001", "single number"),
        ("600036", "600036", "Already 6 digits"),
        ("sz002594", "002594", "Shenzhen BYD"),
        ("", "", "empty string"),
        ("abc123", "000123", "contains letters"),
        ("sz000000", "000000", "All 0 code"),
    ]
    
    service = QuotesIngestionService()
    
    passed = 0
    failed = 0
    
    for input_code, expected, description in test_cases:
        result = service._normalize_stock_code(input_code)
        status = "✅" if result == expected else "❌"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} {description:20s} | input: {input_code:12s} | Expectation: {expected:8s} | actual: {result:8s}")
    
    print(f"\n total: {len(test_cases)} test cases, Pass: {passed}, failed: {failed}")
    
    return failed == 0


async def test_market_quotes_status():
    """Test the market_quotes collection state"""
    print("\n" + "="*60)
    print("test 2: market_quotes Collection status check")
    print("="*60)
    
    await init_db()
    db = get_mongo_db()
    service = QuotesIngestionService()
    
    # Check if the collection is empty
    is_empty = await service._collection_empty()
    count = await db.market_quotes.estimated_document_count()
    
    print(f"📊 market_quotes Collection status:")
    print(f"   - Is it empty: {is_empty}")
    print(f"   - Number of documents: {count}")
    
    if count > 0:
        # Get some sample data
        sample_docs = await db.market_quotes.find().limit(5).to_list(length=5)
        print(f"\n📋 sample data (Top 5):")
        for i, doc in enumerate(sample_docs, 1):
            code = doc.get('code') or doc.get('symbol')
            close = doc.get('close')
            trade_date = doc.get('trade_date')
            updated_at = doc.get('updated_at')
            print(f"   {i}. code: {code}, closing price: {close}, trading day: {trade_date}, Update time: {updated_at}")
        
        # Check if there are prefixed codes
        print(f"\n🔍 Check if there is an exception code (length is not 6 digits):")
        pipeline = [
            {
                "$project": {
                    "code": 1,
                    "code_length": {"$strLenCP": {"$toString": "$code"}}
                }
            },
            {
                "$match": {
                    "code_length": {"$ne": 6}
                }
            },
            {"$limit": 10}
        ]
        
        abnormal_docs = await db.market_quotes.aggregate(pipeline).to_list(length=10)
        
        if abnormal_docs:
            print(f"   ⚠️ discover {len(abnormal_docs)} exception code:")
            for doc in abnormal_docs:
                print(f"      - code: {doc.get('code')}, length: {doc.get('code_length')}")
        else:
            print(f"   ✅ All codes are in standard 6-bit format")
    
    await close_db()
    return True


async def test_historical_data_import():
    """Test the function of importing historical data"""
    print("\n" + "="*60)
    print("test 3: Import from historical data to market_quotes")
    print("="*60)
    
    await init_db()
    db = get_mongo_db()
    service = QuotesIngestionService()
    
    # Check the stock_daily_quotes collection status
    daily_count = await db.stock_daily_quotes.estimated_document_count()
    print(f"📊 stock_daily_quotes Collection status:")
    print(f"   - Number of documents: {daily_count}")
    
    if daily_count == 0:
        print(f"   ⚠️ The historical data collection is empty and the import function cannot be tested.")
        await close_db()
        return False
    
    # Get the latest trading day
    latest_doc = await db.stock_daily_quotes.find(
        {"period": "daily"}
    ).sort("trade_date", -1).limit(1).to_list(length=1)
    
    if latest_doc:
        latest_trade_date = latest_doc[0].get('trade_date')
        print(f"   - Latest trading day: {latest_trade_date}")
        
        # Count the data volume of this trading day
        date_count = await db.stock_daily_quotes.count_documents({
            "trade_date": latest_trade_date,
            "period": "daily"
        })
        print(f"   - The amount of data on the day: {date_count}")
    else:
        print(f"   ⚠️ Unable to get latest trading day")
        await close_db()
        return False
    
    # Check current status of market_quotes
    market_count_before = await db.market_quotes.estimated_document_count()
    print(f"\n📊 market_quotes State before import:")
    print(f"   - Number of documents: {market_count_before}")
    
    # Ask the user if they want to clear market_quotes for testing
    print(f"\n⚠️  Do you want to clear the market_quotes collection to test the import functionality?")
    print(f"   input 'yes' Clear and test, enter other to skip testing")
    
    # Since it is an automated test, we do not clear it, but only simulate the check.
    print(f"   [Automatically skip the clearing operation and only check the import logic]")
    
    # Testing the backfill_from_historical_data method
    print(f"\n🔄 Test historical data import logic...")
    
    try:
        # If the collection is not empty, the method will automatically skip
        await service.backfill_from_historical_data()
        
        market_count_after = await db.market_quotes.estimated_document_count()
        print(f"\n📊 market_quotes Post-import status:")
        print(f"   - Number of documents: {market_count_after}")
        
        if market_count_after > market_count_before:
            print(f"   ✅ Imported successfully {market_count_after - market_count_before} piece of data")
        elif market_count_before > 0:
            print(f"   ℹ️  Collection is not empty, import skipped (as expected)")
        else:
            print(f"   ⚠️ The collection is empty but no data has been imported. There may be insufficient historical data.")
        
    except Exception as e:
        print(f"   ❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        await close_db()
        return False
    
    await close_db()
    return True


async def test_akshare_realtime_quotes():
    """Test AKShare real-time market quotation acquisition (check code standardization)"""
    print("\n" + "="*60)
    print("test 4: AKShare Real-time market code standardization")
    print("="*60)
    
    try:
        from app.services.data_sources.akshare_adapter import AKShareAdapter
        
        adapter = AKShareAdapter()
        
        if not adapter.is_available():
            print("   ⚠️ AKShare Not available, skip test")
            return True
        
        print("   📡 Obtaining real-time market information (Sina interface)...")
        quotes_map = adapter.get_realtime_quotes(source="sina")
        
        if not quotes_map:
            print("   ⚠️ No real-time market data was obtained")
            return False
        
        print(f"   ✅ Get {len(quotes_map)} Real-time quotes of individual stocks")
        
        # Check code format
        print(f"\n🔍 Check code format (top 10):")
        abnormal_codes = []
        
        for i, (code, data) in enumerate(list(quotes_map.items())[:10], 1):
            code_len = len(code)
            is_digit = code.isdigit()
            status = "✅" if code_len == 6 and is_digit else "❌"
            
            if code_len != 6 or not is_digit:
                abnormal_codes.append(code)
            
            print(f"   {status} {i:2d}. code: {code:8s} | length: {code_len} | pure numbers: {is_digit} | closing price: {data.get('close')}")
        
        if abnormal_codes:
            print(f"\n   ⚠️ discover {len(abnormal_codes)} exception code")
            return False
        else:
            print(f"\n   ✅ All codes are in standard 6-digit format")
            return True
        
    except Exception as e:
        print(f"   ❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main test function"""
    print("\n" + "="*60)
    print("🧪 Market warehousing service test program")
    print("="*60)
    print(f"Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    
    # test 1: Stock code standardization
    result1 = await test_normalize_stock_code()
    results.append(("Stock code standardization", result1))
    
    # test 2: market_quotes Collection status
    result2 = await test_market_quotes_status()
    results.append(("market_quotes status check", result2))
    
    # test 3: Historical data import
    result3 = await test_historical_data_import()
    results.append(("Historical data import", result3))
    
    # test 4: AKShare Real-time quotes
    result4 = await test_akshare_realtime_quotes()
    results.append(("AKShare Real-time quotes", result4))
    
    # Summary results
    print("\n" + "="*60)
    print("📊 Summary of test results")
    print("="*60)
    
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{status:8s} | {test_name}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\n total: {total} tests, Pass: {passed}, failed: {total - passed}")
    
    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  Yes {total - passed} tests failed, please check the logs")


if __name__ == "__main__":
    asyncio.run(main())

