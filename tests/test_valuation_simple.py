#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simplified Valuation Metric Testing
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.utils.agent_utils import Toolkit
from tradingagents.default_config import DEFAULT_CONFIG

def test_valuation_simple():
    """Simplified Valuation Metric Testing"""
    print("Simplified Testing of the 300750 Valuation Indicator...")
    
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
    
    print("\n=== Find valuation metrics ===")
    for i, line in enumerate(lines):
        if "Valuation indicators" in line:
            print(f"Find the Valuation Metrics section in section{i+1}OK:")
            # Print the valuation indicator and the following lines
            for j in range(max(0, i-1), min(len(lines), i+10)):
                print(f"{j+1:3d}: {lines[j]}")
            break
    else:
        print("Valuation metrics section not found")
        
        # Search for lines containing PE, PB, PS
        print("\n=== Search for PE, PB, PS related lines ===")
        for i, line in enumerate(lines):
            if any(keyword in line for keyword in ["P/E ratio", "price to book ratio", "price to sales ratio", "PE", "PB", "PS"]):
                print(f"{i+1:3d}: {line}")

if __name__ == "__main__":
    test_valuation_simple()