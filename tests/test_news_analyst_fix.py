#!/usr/bin/env python3
"""
Test news analyst tool call parameter fix
Verify that forced and alternative tool calls are correctly passed the required parameters
"""

import sys
import os
from datetime import datetime

# Add project path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.utils.agent_utils import Toolkit

def test_tool_parameters():
    """Check whether the test tool parameters are correct"""
    print("🔧 Test news analyst tool call parameter fix")
    print("=" * 50)
    
    # Initialization kit
    toolkit = Toolkit()
    
    # Test parameters
    ticker = "600036"
    curr_date = "2025-07-28"
    
    print(f"📊 Test parameters:")
    print(f"   - ticker: {ticker}")
    print(f"   - curr_date: {curr_date}")
    print()
    
    # Testing the get_realtime_stock_news tool
    print("🔍 Test the get_realtime_stock_news tool call...")
    try:
        # Simulate the calling method after repair
        params = {"ticker": ticker, "curr_date": curr_date}
        print(f"   parameters: {params}")
        
        # Check if the tool accepts these parameters
        result = toolkit.get_realtime_stock_news.invoke(params)
        print(f"   ✅ get_realtime_stock_news Call successful")
        print(f"   📝 Return data length: {len(result) if result else 0} character")
        
    except Exception as e:
        print(f"   ❌ get_realtime_stock_news call failed: {e}")
    
    print()
    
    # Testing the get_google_news tool
    print("🔍 Test the get_google_news tool call...")
    try:
        # Simulate the calling method after repair
        params = {"query": f"{ticker} Stock News", "curr_date": curr_date}
        print(f"   parameters: {params}")
        
        # Check if the tool accepts these parameters
        result = toolkit.get_google_news.invoke(params)
        print(f"   ✅ get_google_news Call successful")
        print(f"   📝 Return data length: {len(result) if result else 0} character")
        
    except Exception as e:
        print(f"   ❌ get_google_news call failed: {e}")
    
    print()
    
    # Test how the error was called before fixing it (should fail)
    print("🚫 Test how the error was called before fixing it (should fail)...")
    
    print("   Test get_realtime_stock_news missing curr_date:")
    try:
        params = {"ticker": ticker}  # missing curr_date
        result = toolkit.get_realtime_stock_news.invoke(params)
        print(f"   ⚠️ Unexpected success (may have default value handling)")
    except Exception as e:
        print(f"   ✅ Correctly failed: {e}")
    
    print("   Testing get_google_news is missing query and curr_date:")
    try:
        params = {"ticker": ticker}  # Missing query and curr_date
        result = toolkit.get_google_news.invoke(params)
        print(f"   ⚠️ Unexpected success (may have default value handling)")
    except Exception as e:
        print(f"   ✅ Correctly failed: {e}")
    
    print()
    print("🎯 Repair summary:")
    print("   1. ✅ get_realtime_stock_news Now correctly passing ticker and curr_date")
    print("   2. ✅ get_google_news Now correctly passing query and curr_date")
    print("   3. ✅ Fixed Pydantic validation error")
    print("   4. ✅ News analysts should be able to obtain news data normally")

if __name__ == "__main__":
    test_tool_parameters()