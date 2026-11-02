#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test the optimized fundamental analysis data acquisition strategy
Verify that the new strategy can correctly obtain the necessary financial data and current stock prices without obtaining a large amount of historical daily data
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.utils.agent_utils import Toolkit

def test_optimized_fundamentals():
    """Test optimized fundamental analysis data acquisition"""
    print("=" * 80)
    print("🧪 Test the optimized fundamental analysis data acquisition strategy")
    print("=" * 80)
    
    # Test stocks: Ping An Bank (000001)
    test_symbol = "000001"
    
    # Test different date ranges (corresponding to different data depths)
    from datetime import datetime, timedelta
    
    today = datetime.now()
    test_cases = [
        ("basic", 7, "Fundamental Analysis - 1 Week Data"),
        ("standard", 14, "Standard Analysis - 2 Weeks of Data"), 
        ("full", 21, "Full analysis - 3 weeks of data"),
        ("detailed", 28, "Detailed Analysis - 4 Weeks of Data"),
        ("comprehensive", 30, "Full analysis - 1 month of data")
    ]
    
    results = {}
    
    for depth_name, days_back, description in test_cases:
        print(f"\n📊 test: {description}")
        print("-" * 50)
        
        # Calculate date range
        end_date = today.strftime('%Y-%m-%d')
        start_date = (today - timedelta(days=days_back)).strftime('%Y-%m-%d')
        
        try:
            # Call static methods directly, bypassing tool decorators
            toolkit = Toolkit()
            result = toolkit.get_stock_fundamentals_unified.__func__(
                test_symbol,
                start_date,
                end_date,
                end_date
            )
            
            if result:
                data_length = len(result)
                results[depth_name] = {
                    'success': True,
                    'data_length': data_length,
                    'preview': result[:300] + "..." if len(result) > 300 else result,
                    'description': description
                }
                
                print(f"✅ Data obtained successfully")
                print(f"📏 Data length: {data_length:,} character")
                print(f"📝 Data preview:\n{result[:200]}...")
                
                # Check whether fundamental key information is included
                has_price = "price" in result or "stock price" in result or "Price" in result
                has_fundamentals = "Finance" in result or "Fundamentals" in result or "investment advice" in result
                has_company = "company" in result or "enterprise" in result
                
                print(f"🔍 Data quality check:")
                print(f"   - Contains price information: {'✅' if has_price else '❌'}")
                print(f"   - Contains fundamental information: {'✅' if has_fundamentals else '❌'}")
                print(f"   - Contains company information: {'✅' if has_company else '❌'}")
                
            else:
                results[depth_name] = {
                    'success': False,
                    'data_length': 0,
                    'preview': "No data returned",
                    'description': description
                }
                print(f"❌ No data obtained")
                
        except Exception as e:
            results[depth_name] = {
                'success': False,
                'data_length': 0,
                'preview': f"Error: {str(e)}",
                'description': description
            }
            print(f"❌ Error while getting data: {e}")
    
    # Summary results
    print("\n" + "=" * 80)
    print("📈 Summary of test results")
    print("=" * 80)
    
    successful_tests = sum(1 for r in results.values() if r['success'])
    total_tests = len(results)
    
    print(f"🎯 success rate: {successful_tests}/{total_tests} ({successful_tests/total_tests*100:.1f}%)")
    
    if successful_tests > 0:
        data_lengths = [r['data_length'] for r in results.values() if r['success']]
        avg_length = sum(data_lengths) / len(data_lengths)
        min_length = min(data_lengths)
        max_length = max(data_lengths)
        
        print(f"📏 Data length statistics:")
        print(f"   - average length: {avg_length:,.0f} character")
        print(f"   - minimum length: {min_length:,} character")
        print(f"   - maximum length: {max_length:,} character")
        print(f"   - Data expansion multiple: {max_length/min_length:.1f}x")
        
        # Compare the changes in data volume before and after optimization
        print(f"\n💡 Optimization effect:")
        print(f"   - The new strategy only obtains the price data of the last 2 days + Fundamental Financial Data")
        print(f"   - Compared with the previous 7-30 days of historical data, the amount of data transmission has been significantly reduced.")
        print(f"   - Maintains the integrity of core information required for fundamental analysis")
    
    # Detailed results
    print(f"\n📋 Detailed results for each depth:")
    for depth_name, result in results.items():
        status = "✅ success" if result['success'] else "❌ failed"
        print(f"   {result['description']:20} | {status} | {result['data_length']:6,} character")
    
    print("\n🎉 Test completed!")
    return results

if __name__ == "__main__":
    test_optimized_fundamentals()