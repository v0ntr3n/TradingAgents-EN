"""
Test turnover unit fix
Verify that the turnover unit conversion of Tushare data is correct
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from app.database import get_mongo_db
from tradingagents.dataflows.providers.china.tushare import get_tushare_provider

async def test_amount_fix():
    """Test turnover unit fix"""
    print("=" * 80)
    print("Test turnover unit fix")
    print("=" * 80)
    
    # Test stock: 300750 CATL
    test_code = "300750"
    
    print(f"\n1️⃣ Test Tushare Provider Standardization")
    print(f"   Stock code: {test_code}")
    
    provider = get_tushare_provider()
    if not provider.is_available():
        print("   ❌ Tushare Not available, please check TUSHARE_TOKEN configuration")
        return
    
    # Get historical data (last day)
    from datetime import datetime, timedelta
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5)
    
    print(f"\n2️⃣ Get historical data")
    print(f"   date range: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
    
    df = await provider.get_historical_data(
        symbol=test_code,
        start_date=start_date,
        end_date=end_date,
        period="daily"
    )
    
    if df is None or df.empty:
        print("   ❌ No data obtained")
        return
    
    print(f"   ✅ Get {len(df)} records")
    
    # Show the latest data
    latest = df.iloc[-1]
    print(f"\n3️⃣ Latest data (normalized)")
    print(f"   Date: {latest.name}")
    print(f"   closing price: {latest.get('close')}")
    print(f"   Volume: {latest.get('volume')}")
    print(f"   Turnover(Yuan): {latest.get('amount'):,.0f}")
    print(f"   Turnover(billion): {latest.get('amount') / 1e8:.2f}")
    print(f"   Turnover(Ten thousand yuan): {latest.get('amount') / 1e4:.2f}")
    
    # Check the data in the database
    print(f"\n4️⃣ Check the database stock_daily_quotes collection")
    db = get_mongo_db()
    coll = db["stock_daily_quotes"]
    
    doc = coll.find_one(
        {"symbol": test_code, "period": "daily", "data_source": "tushare"},
        sort=[("trade_date", -1)]
    )
    
    if doc:
        print(f"   ✅ Find database record")
        print(f"   transaction date: {doc.get('trade_date')}")
        print(f"   closing price: {doc.get('close')}")
        print(f"   Turnover(Yuan): {doc.get('amount'):,.0f}")
        print(f"   Turnover(billion): {doc.get('amount') / 1e8:.2f}")
        print(f"   Turnover(Ten thousand yuan): {doc.get('amount') / 1e4:.2f}")
    else:
        print(f"   ⚠️ No record found in database")
    
    # Check the market_quotes collection
    print(f"\n5️⃣ Check the database market_quotes collection")
    quotes_coll = db["market_quotes"]
    
    quote_doc = quotes_coll.find_one({"code": test_code})
    
    if quote_doc:
        print(f"   ✅ Find the market record")
        print(f"   transaction date: {quote_doc.get('trade_date')}")
        print(f"   closing price: {quote_doc.get('close')}")
        print(f"   Turnover(Yuan): {quote_doc.get('amount'):,.0f}")
        print(f"   Turnover(billion): {quote_doc.get('amount') / 1e8:.2f}")
        print(f"   Turnover(Ten thousand yuan): {quote_doc.get('amount') / 1e4:.2f}")
    else:
        print(f"   ⚠️ market_quotes No record found in")
    
    print("\n" + "=" * 80)
    print("✅ Test completed")
    print("=" * 80)
    print("\n💡 Verification standards:")
    print("   - If the transaction volume is shown to be around 9.092 billion, it means the repair is successful. ✅")
    print("   - If the transaction volume is displayed as 9.0918 million or 000.91 million, it means there is still a problem ❌")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_amount_fix())

