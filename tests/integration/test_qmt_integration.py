"""
QMT Data source integration testing

Test prerequisites:
1. xtquant library installed
2. MiniQMT Client has started
3. Only supports Windows systems

Test content:
1. QMT Adapter availability check
2. Get a list of stocks
3. Get real-time quotes
4. Get K-line data
5. QMT Sync service testing
"""
import sys
import os
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import logging
from datetime import datetime

# Configuration log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_qmt_adapter():
    """Test QMT adapter basic functionality"""
    print("\n" + "="*60)
    print("🧪 test 1: QMT Adapter availability check")
    print("="*60)
    
    try:
        from app.services.data_sources.qmt_adapter import QMTAdapter
        
        adapter = QMTAdapter()
        is_available = adapter.is_available()
        
        if is_available:
            print("✅ QMT Adapters available")
            print("   - xtquant Library installed")
            print("   - MiniQMT Client is connected")
        else:
            print("❌ QMT Adapter not available")
            print("   Please check:")
            print("   1. Whether the xtquant library has been installed")
            print("   2. MiniQMT Whether the client is started and logged in")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False
    
    return True


async def test_get_stock_list():
    """Test to get the stock list"""
    print("\n" + "="*60)
    print("🧪 test 2: Get a list of stocks")
    print("="*60)
    
    try:
        from app.services.data_sources.qmt_adapter import QMTAdapter
        
        adapter = QMTAdapter()
        df = adapter.get_stock_list()
        
        if df is not None and not df.empty:
            print(f"✅ successfully obtained {len(df)} only stocks")
            print(f"\n Top 5 stocks:")
            print(df.head().to_string())
            return True
        else:
            print("❌ No stock list obtained")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_get_realtime_quotes():
    """Test to get real-time quotes"""
    print("\n" + "="*60)
    print("🧪 test 3: Get real-time quotes")
    print("="*60)

    try:
        from app.services.data_sources.qmt_adapter import QMTAdapter

        adapter = QMTAdapter()
        quotes = adapter.get_realtime_quotes()

        if quotes:
            print(f"✅ successfully obtained {len(quotes)} Real-time quotes of individual stocks")
            # Showing top 5
            count = 0
            for code, quote in quotes.items():
                if count >= 5:
                    break
                print(f"\n{code}:")
                print(f"  latest price: {quote.get('close')}")
                print(f"  Increase or decrease: {quote.get('pct_chg')}%")
                print(f"  Turnover: {quote.get('amount')}")
                count += 1
            return True
        else:
            print("⚠️  No real-time quotes were obtained")
            print("   Possible reasons:")
            print("   1. Current non-trading hours")
            print("   2. MiniQMT Not connected to the market server")
            print("   3. Need to test during trading hours")
            return False

    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_get_kline():
    """Test to obtain K-line data"""
    print("\n" + "="*60)
    print("🧪 test 4: Get K-line data")
    print("="*60)
    
    try:
        from app.services.data_sources.qmt_adapter import QMTAdapter
        
        adapter = QMTAdapter()
        # Test to obtain the daily data of Ping An Bank (000001)
        kline = adapter.get_kline("000001", period="day", limit=5)
        
        if kline:
            print(f"✅ successfully obtained {len(kline)} K-line data (000001 Ping An Bank)")
            print("\n Last 5 trading days:")
            for item in kline:
                print(f"  {item.get('date')}: open{item.get('open')} high{item.get('high')} "
                      f"low{item.get('low')} receive{item.get('close')} quantity{item.get('volume')}")
            return True
        else:
            print("❌ K-line data not obtained")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("\n" + "🚀 " + "="*58)
    print("🚀 QMT Data source integration testing")
    print("🚀 " + "="*58)
    print(f"⏰ Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # test 1: Availability check
    if not await test_qmt_adapter():
        print("\n❌ QMT Not available, skip subsequent tests")
        return
    
    # test 2: Get a list of stocks
    await test_get_stock_list()
    
    # test 3: Get real-time quotes
    await test_get_realtime_quotes()
    
    # test 4: Get K-line data
    await test_get_kline()
    
    print("\n" + "="*60)
    print("✅ All tests completed")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())

