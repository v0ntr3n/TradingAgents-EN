#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple depth level validation script
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.utils.agent_utils import Toolkit

def test_depth_level(depth):
    """Test specified depth level"""
    print(f"\n{'='*50}")
    print(f"Test depth level: {depth}")
    print(f"{'='*50}")
    
    # Set research depth
    Toolkit._config['research_depth'] = depth
    
    # Call fundamental analysis
    result = Toolkit.get_stock_fundamentals_unified.invoke({
        'ticker': '300750',
        'start_date': "2024-10-10",
        'end_date': "2024-10-11",
        'curr_date': "2024-10-11"
    })
    
    # Analyze results
    lines = result.split('\n')
    char_count = len(result)
    
    # Find data depth level
    depth_level = "unknown"
    for line in lines:
        if "Data depth level" in line:
            depth_level = line.split(":")[-1].strip()
            break
    
    print(f"📊 Result statistics:")
    print(f"   - Data depth level: {depth_level}")
    print(f"   - Total number of rows: {len(lines)}")
    print(f"   - Total characters: {char_count}")
    
    # Show the first few lines of content
    print(f"\n📝 The first 10 lines of content:")
    for i, line in enumerate(lines[:10]):
        if line.strip():
            print(f"   {i+1}: {line[:100]}...")
    
    return {
        'depth_level': depth_level,
        'lines': len(lines),
        'chars': char_count,
        'content': result[:500] + "..." if len(result) > 500 else result
    }

def main():
    """main function"""
    print("🔍 Simple depth level verification test")
    
    # Save original configuration
    original_depth = Toolkit._config.get('research_depth', 3)
    
    results = {}
    
    try:
        # Test different depth levels
        for depth in [1, 3, 5]:
            results[depth] = test_depth_level(depth)
        
        # Compare results
        print(f"\n{'='*60}")
        print("📊 Results comparison")
        print(f"{'='*60}")
        
        for depth in [1, 3, 5]:
            result = results[depth]
            print(f"Depth {depth}: {result['depth_level']} | {result['lines']} OK | {result['chars']} character")
        
        # Check differences
        levels = [results[d]['depth_level'] for d in [1, 3, 5]]
        chars = [results[d]['chars'] for d in [1, 3, 5]]
        
        print(f"\n✅ Verification results:")
        print(f"   - Are the depth levels different?: {len(set(levels)) > 1}")
        print(f"   - Character count changes: {chars[0]} → {chars[1]} → {chars[2]}")
        print(f"   - Data volume growth multiple: {chars[2] / chars[0]:.1f}x")
        
    finally:
        # Restore original configuration
        Toolkit._config['research_depth'] = original_depth
        print(f"\n🔧 Original configuration restored: research_depth = {original_depth}")

if __name__ == "__main__":
    main()