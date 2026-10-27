"""
Simple Hong Kong stock function test
"""

import sys
import os

# Add project root directory to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_basic():
    """basic test"""
    print("🧪 Start basic Hong Kong stock function test...")
    
    try:
        # Test stock tools
        from tradingagents.utils.stock_utils import StockUtils
        
        # Test Hong Kong stock code recognition
        test_cases = [
            "0700.HK",  # Tencent
            "9988.HK",  # Alibaba
            "3690.HK",  # Meituan
            "000001",   # Ping An Bank
            "AAPL"      # apple
        ]
        
        for ticker in test_cases:
            market_info = StockUtils.get_market_info(ticker)
            print(f"  {ticker}: {market_info['market_name']} ({market_info['currency_name']} {market_info['currency_symbol']})")
        
        print("✅ Basic test passed")
        return True
        
    except Exception as e:
        print(f"❌ Basic test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_basic()
