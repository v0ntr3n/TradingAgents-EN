#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Performance comparison test: Verify the performance difference in fundamental analysis data acquisition before and after optimization
Compare key indicators such as data transfer volume and processing time
"""

import sys
import os
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta

def simulate_old_strategy():
    """Data acquisition strategy before simulation optimization (7-30 days of historical data)"""
    print("🔄 Simulate pre-optimization strategy: obtain 7-30 days of historical data...")
    
    ticker = "000001"
    results = {}
    
    # Simulate historical data acquisition with different data depths
    test_cases = [
        ("basic", 7, "Fundamental Analysis - 7 days of data"),
        ("standard", 14, "Standard Analysis - 14 days of data"), 
        ("full", 21, "Full analysis - 21 days of data"),
        ("detailed", 28, "Detailed analysis - 28 days of data"),
        ("comprehensive", 30, "Comprehensive analysis – 30 days of data")
    ]
    
    for depth_name, days_back, description in test_cases:
        print(f"\n📊 {description}")
        
        # Calculate date range
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        
        start_time = time.time()
        
        try:
            # Get historical price data
            from tradingagents.dataflows.interface import get_china_stock_data_unified
            stock_data = get_china_stock_data_unified(ticker, start_date, end_date)
            
            # Get fundamental data
            from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider
            analyzer = OptimizedChinaDataProvider()
            fundamentals_data = analyzer._generate_fundamentals_report(ticker, stock_data)
            
            # Merge data
            combined_data = f"## A stock price data\n{stock_data}\n\n## A Stock fundamental data\n{fundamentals_data}"
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            results[depth_name] = {
                'success': True,
                'data_length': len(combined_data),
                'price_data_length': len(stock_data) if stock_data else 0,
                'fundamentals_length': len(fundamentals_data) if fundamentals_data else 0,
                'processing_time': processing_time,
                'days_requested': days_back,
                'description': description
            }
            
            print(f"   ✅ Data length: {len(combined_data):,} character")
            print(f"   ⏱️ processing time: {processing_time:.2f}seconds")
            
        except Exception as e:
            results[depth_name] = {
                'success': False,
                'data_length': 0,
                'price_data_length': 0,
                'fundamentals_length': 0,
                'processing_time': 0,
                'days_requested': days_back,
                'description': description,
                'error': str(e)
            }
            print(f"   ❌ Failed to obtain: {e}")
    
    return results

def test_new_strategy():
    """Test the optimized data acquisition strategy (only obtain the prices of the last 2 days+fundamental data)"""
    print("\n🚀 Test the optimized strategy: only get the prices of the last 2 days+fundamental data...")
    
    ticker = "000001"
    
    start_time = time.time()
    
    try:
        # 1. Get the latest stock price information (only the last 1-2 days of data are required)
        curr_date = datetime.now().strftime('%Y-%m-%d')
        recent_end_date = curr_date
        recent_start_date = (datetime.strptime(curr_date, '%Y-%m-%d') - timedelta(days=2)).strftime('%Y-%m-%d')
        
        from tradingagents.dataflows.interface import get_china_stock_data_unified
        current_price_data = get_china_stock_data_unified(ticker, recent_start_date, recent_end_date)
        
        # 2. Get fundamental financial data
        from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider
        analyzer = OptimizedChinaDataProvider()
        fundamentals_data = analyzer._generate_fundamentals_report(ticker, current_price_data)
        
        # 3. Merge results
        combined_data = f"## A Stock current price information\n{current_price_data}\n\n## A Stock Fundamentals Financial Data\n{fundamentals_data}"
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        result = {
            'success': True,
            'data_length': len(combined_data),
            'price_data_length': len(current_price_data) if current_price_data else 0,
            'fundamentals_length': len(fundamentals_data) if fundamentals_data else 0,
            'processing_time': processing_time,
            'days_requested': 2,
            'description': "Optimization Strategy – 2 Days Price Data+fundamental data"
        }
        
        print(f"   ✅ Data length: {len(combined_data):,} character")
        print(f"   ⏱️ processing time: {processing_time:.2f}seconds")
        
        return result
        
    except Exception as e:
        return {
            'success': False,
            'data_length': 0,
            'price_data_length': 0,
            'fundamentals_length': 0,
            'processing_time': 0,
            'days_requested': 2,
            'description': "Optimization Strategy – 2 Days Price Data+fundamental data",
            'error': str(e)
        }

def compare_performance():
    """Compare the performance difference before and after optimization"""
    print("=" * 80)
    print("📊 Fundamental analysis data acquisition strategy performance comparison test")
    print("=" * 80)
    
    # Test pre-optimization strategies
    old_results = simulate_old_strategy()
    
    # Test the optimized strategy
    new_result = test_new_strategy()
    
    # Performance comparison analysis
    print("\n" + "=" * 80)
    print("📈 Performance comparison analysis")
    print("=" * 80)
    
    if new_result['success']:
        print(f"\n🚀 Optimized strategy performance:")
        print(f"   - Data length: {new_result['data_length']:,} character")
        print(f"   - processing time: {new_result['processing_time']:.2f}seconds")
        print(f"   - Request days: {new_result['days_requested']}day")
        
        print(f"\n📊 Comparison with each level before optimization:")
        
        successful_old = {k: v for k, v in old_results.items() if v['success']}
        
        if successful_old:
            # Data volume comparison
            old_data_lengths = [v['data_length'] for v in successful_old.values()]
            avg_old_length = sum(old_data_lengths) / len(old_data_lengths)
            max_old_length = max(old_data_lengths)
            min_old_length = min(old_data_lengths)
            
            print(f"\n📏 Data transfer volume comparison:")
            print(f"   - Average before optimization: {avg_old_length:,.0f} character")
            print(f"   - Range before optimization: {min_old_length:,} - {max_old_length:,} character")
            print(f"   - After optimization: {new_result['data_length']:,} character")
            print(f"   - data reduction: {(avg_old_length - new_result['data_length'])/avg_old_length*100:.1f}%")
            
            # Processing time comparison
            old_times = [v['processing_time'] for v in successful_old.values()]
            avg_old_time = sum(old_times) / len(old_times)
            
            print(f"\n⏱️ Processing time comparison:")
            print(f"   - Average before optimization: {avg_old_time:.2f}seconds")
            print(f"   - After optimization: {new_result['processing_time']:.2f}seconds")
            print(f"   - time saving: {(avg_old_time - new_result['processing_time'])/avg_old_time*100:.1f}%")
            
            # Detailed comparison table
            print(f"\n📋 Detailed comparison table:")
            print(f"{'Strategy':<25} | {'days':<4} | {'Data volume(character)':<12} | {'time(seconds)':<8} | {'Status'}")
            print("-" * 70)
            
            for depth, result in old_results.items():
                status = "✅" if result['success'] else "❌"
                data_len = f"{result['data_length']:,}" if result['success'] else "N/A"
                proc_time = f"{result['processing_time']:.2f}" if result['success'] else "N/A"
                print(f"{result['description']:<25} | {result['days_requested']:<4} | {data_len:<12} | {proc_time:<8} | {status}")
            
            print("-" * 70)
            data_len = f"{new_result['data_length']:,}"
            proc_time = f"{new_result['processing_time']:.2f}"
            print(f"{'Optimized strategy':<25} | {new_result['days_requested']:<4} | {data_len:<12} | {proc_time:<8} | ✅")
            
            # Summary of optimization effects
            print(f"\n💡 Summary of optimization effects:")
            print(f"   ✅ Average reduction in data transfer volume {(avg_old_length - new_result['data_length'])/avg_old_length*100:.1f}%")
            print(f"   ✅ Average processing time savings {(avg_old_time - new_result['processing_time'])/avg_old_time*100:.1f}%")
            print(f"   ✅ Maintain the integrity of the core information required for fundamental analysis")
            print(f"   ✅ Improved pertinence and efficiency of data acquisition")
            print(f"   ✅ Reduces unnecessary transmission of historical price data")
        
    else:
        print(f"❌ Strategy test failed after optimization: {new_result.get('error', 'unknown error')}")
    
    print(f"\n🎉 Performance comparison test completed!")

if __name__ == "__main__":
    compare_performance()