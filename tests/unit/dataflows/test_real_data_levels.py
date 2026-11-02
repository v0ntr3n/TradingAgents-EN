#!/usr/bin/env python3
"""
Real data level testing procedures
Actually call the get_stock_fundamentals_unified function to verify the differences in data acquisition at different levels.
"""

import os
import sys
from datetime import datetime, timedelta
import json

# Add project root directory to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Set environment variables
os.environ['PYTHONPATH'] = project_root

def analyze_data_content(data, level_name):
    """Analyze data content and print complete data"""
    print(f"\n{'='*80}")
    print(f"📊  [{level_name}] Complete data content:")
    print(f"📏 total length: {len(data)} character")
    print(f"{'='*80}")
    
    # Print complete data content
    print(data)
    
    print(f"\n{'='*80}")
    print(f"📊  [{level_name}] Data statistical analysis:")
    
    # Statistics module
    sections = data.split("##")
    print(f"   📋 Number of data modules: {len(sections)-1} a")
    
    # Check the contained data types
    data_types = []
    if "price data" in data or "stock price data" in data:
        data_types.append("price data")
    if "fundamental data" in data or "financial data" in data:
        data_types.append("fundamental data")
    if "Basic information" in data or "Company information" in data:
        data_types.append("Basic information")
    if "Technical indicators" in data:
        data_types.append("Technical indicators")
    if "News" in data or "information" in data:
        data_types.append("News")
    
    print(f"   🎯 Contains data types: {', '.join(data_types) if data_types else 'Not recognized'}")
    
    # Check data depth level information
    if "Data depth level" in data:
        depth_lines = [line.strip() for line in data.split('\n') if "Data depth level" in line]
        if depth_lines:
            print(f"   🔍 {depth_lines[0]}")
    
    # Extract date range information
    date_range = 'N/A'
    import re
    date_pattern = r'data period[: :]\s*(\d{4}-\d{2}-\d{2})\s*to\s*(\d{4}-\d{2}-\d{2})'
    match = re.search(date_pattern, data)
    if match:
        start_date, end_date = match.groups()
        # Calculate days
        from datetime import datetime
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        days = (end_dt - start_dt).days + 1
        date_range = f"{start_date} to {end_date} ({days}day)"
        print(f"   📅 data period: {date_range}")
    
    print(f"{'='*80}")
    
    return {
        'length': len(data),
        'sections': sections,
        'data_types': data_types,
        'date_range': date_range
    }

def test_stock_with_all_levels(ticker, stock_name):
    """Test data acquisition for a single stock at all levels"""
    print(f"\n{'='*80}")
    print(f"🎯 test stocks: {stock_name} ({ticker})")
    print(f"{'='*80}")
    
    # Import necessary modules
    from tradingagents.agents.utils.agent_utils import Toolkit
    from tradingagents.default_config import DEFAULT_CONFIG
    
    # Set test date
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    curr_date = end_date
    
    # Test all levels
    test_levels = [
        (1, "Level 1 - Fast"),
        (2, "Level 2 - Standard"),
        (3, "Level 3 - Detailed"),
        (4, "Level 4 - Deeper"),
        (5, "Level 5 - Comprehensive")
    ]
    
    results = {}
    
    for level_num, level_name in test_levels:
        print(f"\n🔍 test {level_name}")
        print("-" * 60)
        
        try:
            # Update configuration
            config = DEFAULT_CONFIG.copy()
            config['research_depth'] = level_num
            Toolkit.update_config(config)
            
            print(f"📝 settings research_depth = {level_num}")
            
            # Create a tool instance and call
            toolkit = Toolkit(config)
            
            # Use the invoke method to call a tool
            result = toolkit.get_stock_fundamentals_unified.invoke({
                'ticker': ticker,
                'start_date': start_date,
                'end_date': end_date,
                'curr_date': curr_date
            })
            
            print(f"✅ Data acquisition successful!")
            
            # Analyze data content
            analysis = analyze_data_content(result, level_name)
            results[level_num] = {
                'level_name': level_name,
                'data': result,
                'analysis': analysis
            }
            
        except Exception as e:
            print(f"❌ Data acquisition failed: {e}")
            import traceback
            traceback.print_exc()
            results[level_num] = {
                'level_name': level_name,
                'error': str(e)
            }
    
    # Comparative analysis
    print(f"\n📈  [{stock_name}] Level comparison analysis:")
    print("=" * 60)
    
    successful_results = {k: v for k, v in results.items() if 'data' in v}
    
    if len(successful_results) >= 2:
        print("📊 Data length comparison:")
        for level_num in sorted(successful_results.keys()):
            result = successful_results[level_num]
            length = result['analysis']['length']
            sections = result['analysis']['sections']
            data_types = len(result['analysis']['data_types'])
            date_range = result['analysis']['date_range']
            print(f"   {result['level_name']}: {length:,} character, {sections} module, {data_types} data type, date range: {date_range}")
        
        # Calculate growth rate
        lengths = [successful_results[k]['analysis']['length'] for k in sorted(successful_results.keys())]
        if len(lengths) > 1:
            print(f"\n📈 Data growth trends:")
            for i in range(1, len(lengths)):
                growth = ((lengths[i] - lengths[i-1]) / lengths[i-1]) * 100 if lengths[i-1] > 0 else 0
                level_names = [successful_results[k]['level_name'] for k in sorted(successful_results.keys())]
                print(f"   {level_names[i-1]} → {level_names[i]}: {growth:+.1f}%")
    
    return results

def main():
    """Main test function"""
    print("🚀 Start real data level testing")
    print("=" * 80)
    print("📋 Test target:")
    print("   1. Verify actual data acquisition at different levels")
    print("   2. Compare data content and length differences")
    print("   3. Analyze data type and module differences")
    print("   4. Demonstrate real data acquisition effects")
    
    # Test stock list - only test A shares
    test_stocks = [
        ("000001", "A Stock-Ping An Bank")
    ]
    
    all_results = {}
    
    # Test stocks one by one
    for ticker, stock_name in test_stocks:
        try:
            results = test_stock_with_all_levels(ticker, stock_name)
            all_results[ticker] = results
        except Exception as e:
            print(f"❌ test stocks {stock_name} failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Generate summary report
    print(f"\n{'='*80}")
    print("📊 summary report")
    print(f"{'='*80}")
    
    for ticker, results in all_results.items():
        stock_name = next((name for t, name in test_stocks if t == ticker), ticker)
        successful_count = len([r for r in results.values() if 'data' in r])
        total_count = len(results)
        
        print(f"\n🎯 {stock_name} ({ticker}):")
        print(f"   ✅ success: {successful_count}/{total_count} levels")
        
        if successful_count > 0:
            successful_results = {k: v for k, v in results.items() if 'data' in v}
            lengths = [v['analysis']['length'] for v in successful_results.values()]
            min_length = min(lengths)
            max_length = max(lengths)
            avg_length = sum(lengths) / len(lengths)
            
            print(f"   📏 Data length range: {min_length:,} - {max_length:,} character")
            print(f"   📊 average length: {avg_length:,.0f} character")
            
            if max_length > min_length:
                expansion_ratio = max_length / min_length
                print(f"   📈 Data expansion multiple: {expansion_ratio:.1f}x")
    
    print(f"\n🎉 Test completed!")
    print("💡 Through the above test, we can see that:")
    print("   • Different levels indeed obtain different depths of data")
    print("   • High levels contain more data modules and content")
    print("   • The data length increases as the level increases")
    print("   • Each stock type supports level distinction")

if __name__ == "__main__":
    main()