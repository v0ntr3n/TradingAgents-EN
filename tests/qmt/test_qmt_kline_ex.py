#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test QMT K-line data acquisition (use get_market_data_ex)
"""
import sys
import os

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from app.services.data_sources.qmt_adapter import QMTAdapter

def test_kline_with_ex():
    """Test using get_market_data_ex to obtain K-line data"""
    print("=" * 60)
    print("🔍 Test QMT K-line data acquisition (get_market_data_ex)")
    print("=" * 60)
    
    adapter = QMTAdapter()
    
    if not adapter.is_available():
        print("❌ QMT Not available")
        return
    
    print("✅ QMT Available")
    
    # Test stock list
    test_stocks = [
        ("000001", "Ping An Bank"),
        ("600000", "Shanghai Pudong Development Bank"),
        ("000002", "Vanke A"),
    ]
    
    for code, name in test_stocks:
        print(f"\n{'=' * 60}")
        print(f"📊 test stocks: {code} ({name})")
        print(f"{'=' * 60}")
        
        # Get daily data
        kline = adapter.get_kline(code, period="day", limit=5)
        
        if kline:
            print(f"✅ successfully obtained {len(kline)} K-line data")
            print("\n Last 5 pieces of data:")
            for i, item in enumerate(kline[-5:], 1):
                print(f"  {i}. Date: {item['date']}")
                print(f"     Open: {item['open']:.2f}, highest: {item['high']:.2f}")
                print(f"     lowest: {item['low']:.2f}, close: {item['close']:.2f}")
                print(f"     Volume: {item['volume']:.0f}, Turnover: {item['amount']:.2f}")
        else:
            print(f"❌ K-line data not obtained")
            print(f"💡 Tip: You may need to manually download historical data in MiniQMT")

if __name__ == "__main__":
    test_kline_with_ex()

