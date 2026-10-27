#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test the calculation of valuation indicators for 000002 stocks
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.utils.agent_utils import Toolkit
from tradingagents.default_config import DEFAULT_CONFIG

def test_000002_valuation():
    """Testing Valuation Metrics for 000002 Stocks"""
    print("Test 000002 stock valuation indicator calculation...")
    
    # Create toolkit
    config = DEFAULT_CONFIG.copy()
    config["online_tools"] = True
    toolkit = Toolkit(config)
    
    # Get fundamental data
    result = toolkit.get_stock_fundamentals_unified.invoke({
        'ticker': '000002',
        'start_date': '2025-06-01',
        'end_date': '2025-07-15',
        'curr_date': '2025-07-15'
    })
    
    # Find the Valuation Metrics section
    lines = result.split('\n')
    
    print("\n=== 000002 Basic stock information ===")
    for i, line in enumerate(lines):
        if "Stock name" in line or "Industry" in line or "market sector" in line:
            print(line)
    
    print("\n=== 000002 Valuation indicators ===")
    found_valuation = False
    for i, line in enumerate(lines):
        if "Valuation indicators" in line:
            found_valuation = True
            print(f"Find the Valuation Metrics section:")
            # Print the valuation indicator and the following lines
            for j in range(i, min(len(lines), i+8)):
                if lines[j].strip() and not lines[j].startswith("###"):
                    print(f"  {lines[j]}")
                elif lines[j].startswith("###") and j > i:
                    break
            break
    
    if not found_valuation:
        print("Valuation indicator part not found, search related keywords...")
        # Search for lines containing PE, PB, PS
        for i, line in enumerate(lines):
            if any(keyword in line for keyword in ["P/E ratio", "price to book ratio", "price to sales ratio", "PE", "PB", "PS"]):
                print(f"  {line}")
    
    print("\n=== financial health indicators ===")
    for i, line in enumerate(lines):
        if "financial health" in line:
            # Print financial health and the following lines
            for j in range(i, min(len(lines), i+8)):
                if lines[j].strip() and not lines[j].startswith("##"):
                    print(f"  {lines[j]}")
                elif lines[j].startswith("##") and j > i:
                    break
            break

if __name__ == "__main__":
    test_000002_valuation()