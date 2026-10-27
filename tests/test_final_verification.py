#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Final verification script: Test whether the optimized data depth level produces fundamental analysis reports with different levels of detail
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.utils.agent_utils import Toolkit
import time

def test_analysis_depth_differences():
    """Test reporting differences produced by different depth levels"""
    print("=" * 80)
    print("Final verification: Testing the differences in fundamental analysis reporting at different depth levels")
    print("=" * 80)
    
    stock_code = '300750'  # Ningde era
    
    # Test three depth levels
    depth_levels = [1, 3, 5]
    results = {}
    
    for depth in depth_levels:
        print(f"\n🔍 Test depth level {depth}...")
        
        try:
            # Call fundamental analysis
            result = Toolkit.get_stock_fundamentals_unified(
                ticker=stock_code,
                start_date="2024-10-10",
                end_date="2024-10-11",
                curr_date="2024-10-11"
            )
            
            # Analyze results
            lines = result.split('\n')
            char_count = len(result)
            
            # Check report type identifier
            report_type = "unknown"
            if "(Basic version)" in result:
                report_type = "Basic version"
            elif "(full version)" in result:
                report_type = "full version"
            else:
                report_type = "Standard Edition"
            
            # Count the number of key indicators
            pe_mentions = result.count("P/E ratio")
            pb_mentions = result.count("price to book ratio")
            roe_mentions = result.count("ROE")
            industry_mentions = result.count("Industry")
            investment_mentions = result.count("investment")
            
            results[depth] = {
                'lines': len(lines),
                'chars': char_count,
                'type': report_type,
                'pe_count': pe_mentions,
                'pb_count': pb_mentions,
                'roe_count': roe_mentions,
                'industry_count': industry_mentions,
                'investment_count': investment_mentions,
                'content': result[:500] + "..." if len(result) > 500 else result
            }
            
            print(f"   ✅ report type: {report_type}")
            print(f"   ✅ Number of data rows: {len(lines)}")
            print(f"   ✅ Number of characters: {char_count}")
            print(f"   ✅ Key Indicators Mentioned: PE({pe_mentions}) PB({pb_mentions}) ROE({roe_mentions})")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results[depth] = {'error': str(e)}
        
        time.sleep(1)  # Avoid requesting too quickly
    
    # Analyze the difference in results
    print("\n" + "=" * 80)
    print("Report gap analysis")
    print("=" * 80)
    
    print("\n📊 Comparison of reports at each level:")
    for depth in depth_levels:
        if 'error' not in results[depth]:
            r = results[depth]
            print(f"   level {depth}: {r['type']} - {r['lines']}OK, {r['chars']}character")
        else:
            print(f"   level {depth}: Error - {results[depth]['error']}")
    
    # Verify the differential effect
    print("\n🎯 Differentiated verification:")
    
    # Check if there are different report types
    types = set()
    valid_results = []
    for depth in depth_levels:
        if 'error' not in results[depth]:
            types.add(results[depth]['type'])
            valid_results.append((depth, results[depth]))
    
    if len(types) > 1:
        print("   ✅ Success: Different depth levels produced different types of reports")
        for report_type in types:
            depths = [d for d, r in valid_results if r['type'] == report_type]
            print(f"      - {report_type}: depth level {depths}")
    else:
        print("   ⚠️  Warning: All depth levels produced the same type of report")
    
    # Check content length differences
    if len(valid_results) >= 2:
        min_chars = min(r['chars'] for _, r in valid_results)
        max_chars = max(r['chars'] for _, r in valid_results)
        char_ratio = max_chars / min_chars if min_chars > 0 else 1
        
        print(f"   📈 content length difference: {char_ratio:.1f}times ({min_chars} -> {max_chars} character)")
        
        if char_ratio >= 1.5:
            print("   ✅ Excellent: Significant content differences between depth levels")
        elif char_ratio >= 1.2:
            print("   ✅ Good: Moderate content differences between depth levels")
        else:
            print("   ⚠️  Average: Small content differences between depth levels")
    
    # Show sample content
    print("\n📝 Example of report content:")
    for depth in [1, 5]:  # Show only the lowest and highest levels
        if depth in results and 'error' not in results[depth]:
            print(f"\n--- depth level {depth} ({results[depth]['type']}) ---")
            print(results[depth]['content'])
    
    print("\n" + "=" * 80)
    print("Final verification completed")
    print("=" * 80)

if __name__ == "__main__":
    test_analysis_depth_differences()