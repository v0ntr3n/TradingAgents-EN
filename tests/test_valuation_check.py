#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test valuation indicator calculation results
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.utils.agent_utils import Toolkit
from tradingagents.default_config import DEFAULT_CONFIG

def test_valuation_indicators():
    """Test valuation indicator calculation"""
    print("Test 300750 valuation indicator calculation...")
    
    # Create toolkit
    config = DEFAULT_CONFIG.copy()
    config["online_tools"] = True
    toolkit = Toolkit(config)
    
    # Get fundamental data
    result = toolkit.get_stock_fundamentals_unified.invoke({
        'ticker': '300750',
        'start_date': '2025-06-01',
        'end_date': '2025-07-15',
        'curr_date': '2025-07-15'
    })
    
    # Find the Valuation Metrics section
    lines = result.split('\n')
    
    print("\n=== Valuation indicator part ===")
    in_valuation_section = False
    
    for line in lines:
        if "Valuation indicators" in line:
            in_valuation_section = True
            print(line)
        elif in_valuation_section:
            if "P/E ratio" in line or "price to book ratio" in line or "price to sales ratio" in line or "dividend yield" in line:
                print(line)
            elif line.strip() == "" or line.startswith("##"):
                if line.startswith("##"):
                    break
    
    print("\n=== Full results preview ===")
    # Only show first 2000 characters
    print(result[:2000])
    if len(result) > 2000:
        print("...(Result truncated)")

if __name__ == "__main__":
    test_valuation_indicators()