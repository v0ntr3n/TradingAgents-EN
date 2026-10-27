"""
Testing AKShare Volume Units
Check whether the transaction volume data unit returned by AKShare is correct
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from tradingagents.dataflows.providers.china.akshare import get_akshare_provider

async def test_akshare_amount():
    """Testing AKShare Volume Units"""
    print("=" * 80)
    print("Testing AKShare Volume Units")
    print("=" * 80)
    
    # Test stock: 300750 CATL
    test_code = "300750"
    
    print(f"\n1️⃣ test stocks: {test_code} (Ningde era)")
    
    provider = get_akshare_provider()
    if not provider.is_available():
        print("   ❌ AKShare Not available")
        return
    
    print(f"\n2️⃣ Get real-time quotes")
    
    # Get real-time quotes
    quotes = await provider.get_stock_quotes(test_code)
    
    if quotes:
        print(f"   ✅ get success")
        print(f"   latest price: {quotes.get('close')}")
        print(f"   Original value of turnover: {quotes.get('amount')}")
        if quotes.get('amount'):
            amount = quotes.get('amount')
            print(f"   Turnover(Yuan): {amount:,.0f}")
            print(f"   Turnover(billion): {amount / 1e8:.2f}")
            print(f"   Turnover(Ten thousand yuan): {amount / 1e4:.2f}")
    else:
        print(f"   ❌ Failed to obtain")
    
    print(f"\n3️⃣ Get historical data")
    
    # Get historical data (last 5 days)
    from datetime import datetime, timedelta
    end_date = datetime.now()
    start_date = end_date - timedelta(days=5)
    
    hist_df = await provider.get_historical_data(
        symbol=test_code,
        start_date=start_date,
        end_date=end_date,
        period="daily"
    )
    
    if hist_df is not None and not hist_df.empty:
        print(f"   ✅ Get {len(hist_df)} records")
        
        # Show the latest data
        latest = hist_df.iloc[-1]
        print(f"\n   latest data:")
        print(f"   Date: {latest.name if hasattr(latest, 'name') else latest.get('date')}")
        print(f"   closing price: {latest.get('close')}")
        print(f"   Original value of turnover: {latest.get('amount')}")
        if latest.get('amount'):
            amount = latest.get('amount')
            print(f"   Turnover(Yuan): {amount:,.0f}")
            print(f"   Turnover(billion): {amount / 1e8:.2f}")
            print(f"   Turnover(Ten thousand yuan): {amount / 1e4:.2f}")
    else:
        print(f"   ❌ Failed to obtain")
    
    print("\n" + "=" * 80)
    print("💡 AKShare Official documentation:")
    print("   - stock_zh_a_spot_em(): The unit of transaction volume is yuan")
    print("   - stock_zh_a_hist(): The unit of transaction volume is yuan")
    print("=" * 80)
    print("\n✅ Conclusion:")
    print("   If the transaction volume is shown to be around 9.092 billion, it means that the AKShare unit is correct (yuan)✅")
    print("   If the transaction volume is displayed as 9.0918 million or 009.1 million, there is a problem ❌")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_akshare_amount())

