#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testing the updated unified fundamental analysis functions
Verify that the valuation indicator of 300750 is displayed correctly
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.agent_utils import Toolkit

def test_300750_fundamentals():
    """Fundamental analysis of test 300750"""
    print("🔍 Test 300750 fundamental analysis...")
    
    # Set research depth
    config = DEFAULT_CONFIG.copy()
    config['research_depth'] = 'Standard'
    
    # Create Toolkit instance
    toolkit = Toolkit(config=config)
    
    # Test 300750 (without suffix)
    ticker = "300750"
    print(f"\n📊 Analyze stocks: {ticker}")
    
    try:
        result = toolkit.get_stock_fundamentals_unified(ticker)
        print(f"✅ Successfully obtained fundamental data")
        
        # Check if valuation metrics are included
        if "PE" in result or "P/E ratio" in result:
            print("✅ Discover PE Valuation Metrics")
        else:
            print("❌ No PE valuation indicators found")
            
        if "PB" in result or "price to book ratio" in result:
            print("✅ Discover PB Valuation Metrics")
        else:
            print("❌ No PB valuation indicators found")
            
        # Print complete analysis results
        print(f"\n" + "="*80)
        print(f"📋 Complete analysis results:")
        print("="*80)
        print(result)
        print("="*80)
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_300750_fundamentals()