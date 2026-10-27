#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test the PE calculation of profitable stocks (such as 600036 China Merchants Bank)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.utils.agent_utils import Toolkit
from tradingagents.default_config import DEFAULT_CONFIG

def test_profitable_stock():
    """Testing PE calculations for profitable stocks"""
    print("Testing PE calculations for profitable stocks...")
    
    # Create toolkit
    config = DEFAULT_CONFIG.copy()
    config["online_tools"] = True
    toolkit = Toolkit(config)
    
    # Test 600036 (China Merchants Bank) - Usually profitable
    print("\n=== Test 600036 (China Merchants Bank)===")
    result = toolkit.get_stock_fundamentals_unified.invoke({
        'ticker': '600036',
        'start_date': '2025-06-01',
        'end_date': '2025-07-15',
        'curr_date': '2025-07-15'
    })
    
    # Find valuation metrics
    lines = result.split('\n')
    
    print("\n📊 600036 Basic information:")
    for i, line in enumerate(lines):
        if "Stock name" in line or "Industry" in line:
            print(f"  {line}")
    
    print("\n💰 600036 Valuation indicators:")
    for i, line in enumerate(lines):
        if "Valuation indicators" in line:
            # Print the valuation indicator and the following lines
            for j in range(i, min(len(lines), i+8)):
                if lines[j].strip() and not lines[j].startswith("###"):
                    print(f"  {lines[j]}")
                elif lines[j].startswith("###") and j > i:
                    break
            break
    
    print("\n📈 600036 Profitability:")
    for i, line in enumerate(lines):
        if "profitability indicator" in line:
            # Print the profitability indicator and the following lines
            for j in range(i, min(len(lines), i+8)):
                if lines[j].strip() and not lines[j].startswith("###"):
                    print(f"  {lines[j]}")
                elif lines[j].startswith("###") and j > i:
                    break
            break

if __name__ == "__main__":
    test_profitable_stock()