#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test stock market identification logic
Verify the identification results of 300750 and 300750.SZ
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.utils.stock_utils import StockUtils

def test_stock_identification():
    """Test stock symbol recognition"""
    test_cases = [
        "300750",      # Pure A-share code
        "300750.SZ",   # A-share code with suffix
        "000001",      # Another A-share code
        "000001.SZ",   # A-share code with suffix
        "600000",      # Shanghai A-share code
        "600000.SH",   # Shanghai A-share code with suffix
        "0700.HK",     # Hong Kong stock code
        "AAPL",        # US stock code
    ]
    
    print("🔍 Stock Market Identification Test")
    print("=" * 50)
    
    for ticker in test_cases:
        market_info = StockUtils.get_market_info(ticker)
        print(f"Stock code: {ticker:12} | market: {market_info['market_name']:8} | Is it A-share?: {market_info['is_china']}")
    
    print("\n" + "=" * 50)
    print("🎯 Focus on testing 300750 related code:")
    
    # Key tests 300750
    for ticker in ["300750", "300750.SZ"]:
        market_info = StockUtils.get_market_info(ticker)
        print(f"\n📊 Stock code: {ticker}")
        print(f"   market type: {market_info['market']}")
        print(f"   Market name: {market_info['market_name']}")
        print(f"   Is it A-share?: {market_info['is_china']}")
        print(f"   data source: {market_info['data_source']}")
        print(f"   Currency: {market_info['currency_name']} ({market_info['currency_symbol']})")

if __name__ == "__main__":
    test_stock_identification()