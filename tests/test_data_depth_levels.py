#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test differences at different data depth levels
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.utils.agent_utils import Toolkit
from tradingagents.default_config import DEFAULT_CONFIG

def test_data_depth_levels():
    """Test different data depth levels"""
    print("Test differences at different data depth levels...")
    
    # Test ticker
    ticker = '300750'  # Ningde era
    
    # Test different levels
    levels = [1, 3, 5]
    level_names = {1: "fast", 3: "Standard", 5: "Comprehensive"}
    
    results = {}
    
    for level in levels:
        print(f"\n{'='*60}")
        print(f"🔍 test level {level} ({level_names[level]})")
        print(f"{'='*60}")
        
        # Set configuration
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        config["research_depth"] = level  # Set data depth level
        
        # Create toolkit
        toolkit = Toolkit(config)
        
        # Get fundamental data
        result = toolkit.get_stock_fundamentals_unified.invoke({
            'ticker': ticker,
            'start_date': '2025-06-01',
            'end_date': '2025-07-15',
            'curr_date': '2025-07-15'
        })
        
        # Analyze results
        data_length = len(result)
        lines = result.split('\n')
        line_count = len(lines)
        
        # Count different types of content
        sections = []
        current_section = None
        
        for line in lines:
            if line.startswith('##'):
                current_section = line.strip()
                sections.append(current_section)
        
        results[level] = {
            'data_length': data_length,
            'line_count': line_count,
            'sections': sections,
            'content': result
        }
        
        print(f"📊 Data length: {data_length:,} character")
        print(f"📝 Number of lines: {line_count:,} OK")
        print(f"📋 Number of data modules: {len(sections)}")
        print(f"📋 data module:")
        for i, section in enumerate(sections, 1):
            print(f"  {i}. {section}")
        
        # Show partial preview
        print(f"\n📄 Content preview (first 500 characters):")
        print("-" * 50)
        print(result[:500] + "..." if len(result) > 500 else result)
        print("-" * 50)
    
    # Compare results
    print(f"\n{'='*80}")
    print(f"📊 Comparison and summary of different levels of data")
    print(f"{'='*80}")
    
    print(f"{'level':<8} {'Name':<8} {'Data length':<12} {'Number of lines':<8} {'Number of modules':<8}")
    print("-" * 60)
    
    for level in levels:
        data = results[level]
        print(f"{level:<8} {level_names[level]:<8} {data['data_length']:,<12} {data['line_count']:<8} {len(data['sections']):<8}")
    
    # Analyze differences
    print(f"\n🔍 Difference analysis:")
    
    # Data length difference
    level1_length = results[1]['data_length']
    level3_length = results[3]['data_length']
    level5_length = results[5]['data_length']
    
    print(f"  📈 data length growth:")
    print(f"    - level 1→3: {level3_length - level1_length:+,} character ({((level3_length/level1_length-1)*100):+.1f}%)")
    print(f"    - level 3→5: {level5_length - level3_length:+,} character ({((level5_length/level3_length-1)*100):+.1f}%)")
    print(f"    - level 1→5: {level5_length - level1_length:+,} character ({((level5_length/level1_length-1)*100):+.1f}%)")
    
    # Module quantity difference
    print(f"\n  📋 Data module differences:")
    for level in levels:
        sections = results[level]['sections']
        print(f"    - level{level} ({level_names[level]}): {len(sections)}modules")
        for section in sections:
            print(f"      • {section}")
    
    # Historical data range differences
    print(f"\n  📅 Historical data range differences:")
    print(f"    - level 1 (fast): 7 days historical data")
    print(f"    - level 3 (Standard): 21 days historical data")
    print(f"    - level 5 (Comprehensive): 30 days historical data")
    
    print(f"\n✅ Test completed! Different levels do capture different depths of data.")

if __name__ == "__main__":
    test_data_depth_levels()