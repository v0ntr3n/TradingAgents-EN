#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test optimized data depth level logic
Validated fundamental analysis no longer obtains unnecessary historical data
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from tradingagents.agents.utils.agent_utils import Toolkit

def test_optimized_data_depth():
    """Test optimized data depth levels"""
    
    # Test ticker
    stock_code = '300750'  # Ningde era
    
    print("=" * 80)
    print("Test optimized data depth level logic")
    print("=" * 80)
    
    # Test different depth levels
    depth_levels = [1, 3, 5]
    depth_names = ["fast", "Standard", "Comprehensive"]
    
    results = {}
    
    for i, depth in enumerate(depth_levels):
        print(f"\n🔍 Test depth level {depth} ({depth_names[i]})...")
        
        # Set research depth
        Toolkit._config['research_depth'] = depth
        
        try:
            # Get fundamental data
            data = Toolkit.get_stock_fundamentals_unified(stock_code)
            
            # Analyze data content
            lines = data.split('\n')
            line_count = len(lines)
            
            # Number of statistical modules (in##line starting with)
            module_count = sum(1 for line in lines if line.strip().startswith('##'))
            
            # Check whether it contains historical data related content
            historical_data_mentions = sum(1 for line in lines if 'history' in line or 'day data' in line or 'days' in line.lower())
            
            results[depth] = {
                'line_count': line_count,
                'module_count': module_count,
                'historical_mentions': historical_data_mentions,
                'data_length': len(data)
            }
            
            print(f"   ✅ Number of data rows: {line_count}")
            print(f"   ✅ Number of modules: {module_count}")
            print(f"   ✅ Historical data mentions: {historical_data_mentions}")
            print(f"   ✅ Total length of data: {len(data)} character")
            
        except Exception as e:
            print(f"   ❌ Failed to get data: {e}")
            results[depth] = None
    
    # Analyze results
    print("\n" + "=" * 80)
    print("Optimization result analysis")
    print("=" * 80)
    
    valid_results = {k: v for k, v in results.items() if v is not None}
    
    if len(valid_results) >= 2:
        print("\n📊 Data depth level comparison:")
        for depth in depth_levels:
            if depth in valid_results:
                result = valid_results[depth]
                depth_name = depth_names[depth_levels.index(depth)]
                print(f"   level {depth} ({depth_name}): {result['module_count']} module, {result['line_count']} OK, {result['data_length']} character")
        
        # Check optimization effect
        print("\n🎯 Optimization effect verification:")
        
        # 1. Check if there is any historical data related content
        total_historical_mentions = sum(r['historical_mentions'] for r in valid_results.values())
        if total_historical_mentions == 0:
            print("   ✅ Successfully removed content related to historical data")
        else:
            print(f"   ⚠️  There are still {total_historical_mentions} Handle historical data related content")
        
        # 2. Check whether the differences at different levels are reasonable
        level_1_modules = valid_results.get(1, {}).get('module_count', 0)
        level_3_modules = valid_results.get(3, {}).get('module_count', 0)
        level_5_modules = valid_results.get(5, {}).get('module_count', 0)
        
        if level_1_modules < level_3_modules <= level_5_modules:
            print("   ✅ Data depth level increments are reasonable")
        else:
            print(f"   ⚠️  Data depth levels may need to be adjusted: L1={level_1_modules}, L3={level_3_modules}, L5={level_5_modules}")
        
        # 3. Performance improvement estimates
        if 1 in valid_results and 5 in valid_results:
            level_1_size = valid_results[1]['data_length']
            level_5_size = valid_results[5]['data_length']
            if level_5_size > level_1_size:
                size_ratio = level_5_size / level_1_size
                print(f"   📈 Level 5 has an increased amount of data compared to level 1: {size_ratio:.1f}times")
            else:
                print("   ✅ High level data volume is well controlled")
    
    print("\n" + "=" * 80)
    print("Test completed")
    print("=" * 80)

if __name__ == "__main__":
    test_optimized_data_depth()