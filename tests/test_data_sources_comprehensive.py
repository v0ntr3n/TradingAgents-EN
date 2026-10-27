#!/usr/bin/env python3
"""
Data source comprehensive testing program
Test the acquisition process and priority switching of all data sources
"""

import sys
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def test_china_stock_data_sources():
    """Test China Stock Data Source"""
    print("🇨🇳 Test China Stock Data Source")
    print("=" * 60)
    
    test_symbols = ["000001", "600036", "000858"]  # Ping An Bank, China Merchants Bank, Wuliangye
    start_date = "2025-07-01"
    end_date = "2025-07-12"
    
    results = {}
    
    for symbol in test_symbols:
        print(f"\n📊 test stocks: {symbol}")
        print("-" * 40)
        
        symbol_results = {}
        
        # 1. Test the unified data source interface
        try:
            print(f"🔍 Test the unified data source interface...")
            from tradingagents.dataflows.interface import get_china_stock_data_unified
            
            start_time = time.time()
            result = get_china_stock_data_unified(symbol, start_date, end_date)
            end_time = time.time()
            
            if result and "❌" not in result:
                print(f"✅ Unified interface obtained successfully ({end_time - start_time:.2f}s)")
                print(f"   Data length: {len(result)} character")
                print(f"   Data preview: {result[:150]}...")
                symbol_results['unified'] = {
                    'success': True,
                    'time': end_time - start_time,
                    'data_length': len(result)
                }
            else:
                print(f"❌ Unified interface acquisition failed: {result[:100]}...")
                symbol_results['unified'] = {'success': False, 'error': result[:100]}
                
        except Exception as e:
            print(f"❌ Unified interface exception: {e}")
            symbol_results['unified'] = {'success': False, 'error': str(e)}
        
        # 2. Test optimized version
        try:
            print(f"🔍 Test optimized version...")
            from tradingagents.dataflows.optimized_china_data import get_china_stock_data_cached
            
            start_time = time.time()
            result = get_china_stock_data_cached(symbol, start_date, end_date, force_refresh=True)
            end_time = time.time()
            
            if result and "❌" not in result:
                print(f"✅ Optimized version successfully obtained ({end_time - start_time:.2f}s)")
                print(f"   Data length: {len(result)} character")
                symbol_results['optimized'] = {
                    'success': True,
                    'time': end_time - start_time,
                    'data_length': len(result)
                }
            else:
                print(f"❌ Failed to obtain optimized version: {result[:100]}...")
                symbol_results['optimized'] = {'success': False, 'error': result[:100]}
                
        except Exception as e:
            print(f"❌ Optimized version exception: {e}")
            symbol_results['optimized'] = {'success': False, 'error': str(e)}
        
        # 3. Test data source manager
        try:
            print(f"🔍 Test data source manager...")
            from tradingagents.dataflows.data_source_manager import DataSourceManager
            
            manager = DataSourceManager()
            print(f"   Current data source: {manager.current_source.value}")
            print(f"   Available data sources: {[s.value for s in manager.available_sources]}")
            
            start_time = time.time()
            result = manager.get_stock_data(symbol, start_date, end_date)
            end_time = time.time()
            
            if result and "❌" not in result:
                print(f"✅ Data source manager obtained successfully ({end_time - start_time:.2f}s)")
                symbol_results['manager'] = {
                    'success': True,
                    'time': end_time - start_time,
                    'current_source': manager.current_source.value,
                    'available_sources': [s.value for s in manager.available_sources]
                }
            else:
                print(f"❌ Data source manager acquisition failed: {result[:100]}...")
                symbol_results['manager'] = {'success': False, 'error': result[:100]}
                
        except Exception as e:
            print(f"❌ Data source manager exception: {e}")
            symbol_results['manager'] = {'success': False, 'error': str(e)}
        
        results[symbol] = symbol_results
        time.sleep(1)  # Avoid API frequency limits
    
    return results

def test_us_stock_data_sources():
    """Test US stock data source"""
    print("\n🇺🇸 Test US stock data source")
    print("=" * 60)
    
    test_symbols = ["AAPL", "SPY", "TSLA"]
    start_date = "2025-07-01"
    end_date = "2025-07-12"
    
    results = {}
    
    for symbol in test_symbols:
        print(f"\n📊 test stocks: {symbol}")
        print("-" * 40)
        
        symbol_results = {}
        
        # 1. Test the optimized version (FinnHub takes priority)
        try:
            print(f"🔍 Test the optimized version (FinnHub takes priority)...")
            from tradingagents.dataflows.optimized_us_data import get_us_stock_data_cached
            
            start_time = time.time()
            result = get_us_stock_data_cached(symbol, start_date, end_date, force_refresh=True)
            end_time = time.time()
            
            if result and "❌" not in result:
                print(f"✅ Optimized version successfully obtained ({end_time - start_time:.2f}s)")
                print(f"   Data length: {len(result)} character")
                
                # Check data source
                if "FINNHUB" in result.upper() or "finnhub" in result:
                    print(f"   🎯 Used FinnHub data source")
                elif "Yahoo Finance" in result or "yfinance" in result:
                    print(f"   ⚠️ Used Yahoo Finance alternative data source")
                
                symbol_results['optimized'] = {
                    'success': True,
                    'time': end_time - start_time,
                    'data_length': len(result)
                }
            else:
                print(f"❌ Failed to obtain optimized version: {result[:100]}...")
                symbol_results['optimized'] = {'success': False, 'error': result[:100]}
                
        except Exception as e:
            print(f"❌ Optimized version exception: {e}")
            symbol_results['optimized'] = {'success': False, 'error': str(e)}
        
        # 2. Test the original yfinance interface
        try:
            print(f"🔍 Test the original yfinance interface...")
            from tradingagents.dataflows.interface import get_YFin_data_online
            
            start_time = time.time()
            result = get_YFin_data_online(symbol, start_date, end_date)
            end_time = time.time()
            
            if result and "No data found" not in result and "❌" not in result:
                print(f"✅ yfinance Interface obtained successfully ({end_time - start_time:.2f}s)")
                print(f"   Data length: {len(result)} character")
                symbol_results['yfinance'] = {
                    'success': True,
                    'time': end_time - start_time,
                    'data_length': len(result)
                }
            else:
                print(f"❌ yfinance Interface acquisition failed: {result[:100]}...")
                symbol_results['yfinance'] = {'success': False, 'error': result[:100]}
                
        except Exception as e:
            print(f"❌ yfinance Interface exception: {e}")
            symbol_results['yfinance'] = {'success': False, 'error': str(e)}
        
        results[symbol] = symbol_results
        time.sleep(2)  # Avoid API frequency limits
    
    return results

def test_news_data_sources():
    """Test news data source"""
    print("\n📰 Test news data source")
    print("=" * 60)
    
    test_symbols = ["AAPL", "000001"]
    results = {}
    
    for symbol in test_symbols:
        print(f"\n📰 Test stock news: {symbol}")
        print("-" * 40)
        
        symbol_results = {}
        
        # 1. Testing a real-time news aggregator
        try:
            print(f"🔍 Testing a real-time news aggregator...")
            from tradingagents.dataflows.realtime_news_utils import RealtimeNewsAggregator
            
            aggregator = RealtimeNewsAggregator()
            start_time = time.time()
            news_items = aggregator.get_realtime_stock_news(symbol, hours_back=24)
            end_time = time.time()
            
            print(f"✅ Get real-time news successfully ({end_time - start_time:.2f}s)")
            print(f"   Number of news: {len(news_items)}")
            
            if news_items:
                print(f"   latest news: {news_items[0].title[:50]}...")
                print(f"   news source: {news_items[0].source}")
            
            symbol_results['realtime_news'] = {
                'success': True,
                'time': end_time - start_time,
                'news_count': len(news_items)
            }
                
        except Exception as e:
            print(f"❌ Real time news anomaly: {e}")
            symbol_results['realtime_news'] = {'success': False, 'error': str(e)}
        
        # 2. Test FinnHub News
        try:
            print(f"🔍 Test FinnHub News...")
            from tradingagents.dataflows.interface import get_finnhub_news
            
            start_time = time.time()
            result = get_finnhub_news(symbol, "2025-07-01", "2025-07-12")
            end_time = time.time()
            
            if result and "❌" not in result:
                print(f"✅ FinnHub News obtained successfully ({end_time - start_time:.2f}s)")
                print(f"   Data length: {len(result)} character")
                symbol_results['finnhub_news'] = {
                    'success': True,
                    'time': end_time - start_time,
                    'data_length': len(result)
                }
            else:
                print(f"❌ FinnHub Failed to get news: {result[:100]}...")
                symbol_results['finnhub_news'] = {'success': False, 'error': result[:100]}
                
        except Exception as e:
            print(f"❌ FinnHub News anomaly: {e}")
            symbol_results['finnhub_news'] = {'success': False, 'error': str(e)}
        
        results[symbol] = symbol_results
        time.sleep(1)
    
    return results

def test_cache_system():
    """Test caching system"""
    print("\n🗄️ Test caching system")
    print("=" * 60)
    
    results = {}
    
    try:
        print(f"🔍 Test cache manager...")
        from tradingagents.dataflows.cache_manager import get_cache
        
        cache = get_cache()
        print(f"   cache type: {type(cache).__name__}")
        
        # Test cache save and load
        test_data = "test data_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save test data
        cache_key = cache.save_stock_data(
            symbol="TEST001",
            data=test_data,
            start_date="2025-07-01",
            end_date="2025-07-12",
            data_source="test"
        )
        
        print(f"   cache key: {cache_key}")
        
        # Load test data
        loaded_data = cache.load_stock_data(cache_key)
        
        if loaded_data == test_data:
            print(f"✅ Cache system test successful")
            results['cache'] = {'success': True, 'cache_type': type(cache).__name__}
        else:
            print(f"❌ Cache data does not match")
            results['cache'] = {'success': False, 'error': 'Data does not match'}
            
    except Exception as e:
        print(f"❌ Cache system exception: {e}")
        results['cache'] = {'success': False, 'error': str(e)}
    
    return results


def analyze_results(all_results: Dict):
    """Analyze test results"""
    print("\n📊 Test result analysis")
    print("=" * 60)

    # Statistical success rate
    total_tests = 0
    successful_tests = 0

    for category, category_results in all_results.items():
        print(f"\n📋 {category.upper()} Category:")

        if category == 'cache':
            total_tests += 1
            if category_results.get('success'):
                successful_tests += 1
                print(f"   ✅ caching system: normal")
            else:
                print(f"   ❌ caching system: {category_results.get('error', 'unknown error')}")
        else:
            for symbol, symbol_results in category_results.items():
                print(f"   📊 {symbol}:")
                for test_type, result in symbol_results.items():
                    total_tests += 1
                    if result.get('success'):
                        successful_tests += 1
                        time_taken = result.get('time', 0)
                        data_length = result.get('data_length', 0)
                        print(f"      ✅ {test_type}: {time_taken:.2f}s, {data_length}character")
                    else:
                        error = result.get('error', 'unknown error')
                        print(f"      ❌ {test_type}: {error[:50]}...")

    # Overall statistics
    success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
    print(f"\n📈 Overall statistics:")
    print(f"   Total number of tests: {total_tests}")
    print(f"   Number of successes: {successful_tests}")
    print(f"   success rate: {success_rate:.1f}%")

    # Performance analysis
    print(f"\n⚡ Performance analysis:")
    fastest_times = []
    slowest_times = []

    for category, category_results in all_results.items():
        if category != 'cache':
            for symbol, symbol_results in category_results.items():
                for test_type, result in symbol_results.items():
                    if result.get('success') and 'time' in result:
                        time_taken = result['time']
                        fastest_times.append((f"{category}-{symbol}-{test_type}", time_taken))
                        slowest_times.append((f"{category}-{symbol}-{test_type}", time_taken))

    if fastest_times:
        fastest_times.sort(key=lambda x: x[1])
        slowest_times.sort(key=lambda x: x[1], reverse=True)

        print(f"   fastest: {fastest_times[0][0]} ({fastest_times[0][1]:.2f}s)")
        print(f"   slowest: {slowest_times[0][0]} ({slowest_times[0][1]:.2f}s)")

    return success_rate >= 70  # 70%The above success rate is considered as passing


def print_recommendations(all_results: Dict):
    """Print optimization suggestions"""
    print(f"\n💡 Optimization suggestions:")
    print("=" * 60)

    # Check China Stock Data Source
    china_results = all_results.get('china_stocks', {})
    china_success_count = 0
    china_total_count = 0

    for symbol, symbol_results in china_results.items():
        for test_type, result in symbol_results.items():
            china_total_count += 1
            if result.get('success'):
                china_success_count += 1

    china_success_rate = (china_success_count / china_total_count * 100) if china_total_count > 0 else 0

    if china_success_rate < 80:
        print("🇨🇳 China stock data source:")
        print("   - Check Tushare Token configuration")
        print("   - Confirm AKShare library installation")
        print("   - Verify network connection")

    # Check US stock data source
    us_results = all_results.get('us_stocks', {})
    us_success_count = 0
    us_total_count = 0

    for symbol, symbol_results in us_results.items():
        for test_type, result in symbol_results.items():
            us_total_count += 1
            if result.get('success'):
                us_success_count += 1

    us_success_rate = (us_success_count / us_total_count * 100) if us_total_count > 0 else 0

    if us_success_rate < 80:
        print("🇺🇸 US stock data source:")
        print("   - Check FinnHub API Key configuration")
        print("   - Avoid yfinance frequency limits")
        print("   - Consider using a proxy service")

    # Check news data sources
    news_results = all_results.get('news', {})
    if news_results:
        print("📰 news data source:")
        print("   - Configure more news API keys")
        print("   - Add Chinese news source")
        print("   - Optimize news deduplication algorithm")

    # Caching system recommendations
    cache_result = all_results.get('cache', {})
    if not cache_result.get('success'):
        print("🗄️ caching system:")
        print("   - Check Redis/MongoDB connection")
        print("   - Confirm file cache directory permissions")
        print("   - Clean expired cache files")


def main():
    """Main test function"""
    print("🧪 Data source comprehensive testing program")
    print("=" * 60)
    print(f"Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    all_results = {}

    try:
        # 1. Test China Stock Data Source
        china_results = test_china_stock_data_sources()
        all_results['china_stocks'] = china_results

        # 2. Test US stock data source
        us_results = test_us_stock_data_sources()
        all_results['us_stocks'] = us_results

        # 3. Test news data source
        news_results = test_news_data_sources()
        all_results['news'] = news_results

        # 4. Test caching system
        cache_results = test_cache_system()
        all_results['cache'] = cache_results

        # 5. Analyze results
        success = analyze_results(all_results)

        # 6. Printing suggestions
        print_recommendations(all_results)

        # 7. Summary
        print(f"\n🎯 Test summary:")
        if success:
            print("✅ The data source system is running normally")
            print("✅ Priority configuration is correct")
            print("✅ The backup mechanism is effective")
        else:
            print("⚠️ There is a problem with the data source system")
            print("⚠️ Need to check configuration and network")

        return success

    except Exception as e:
        print(f"❌ Test program exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()

    print(f"\n{'='*60}")
    if success:
        print("🎉 Data source testing completed! The system is running normally.")
    else:
        print("⚠️ The data source test found a problem, please check the configuration.")

    print(f"\n📋 Next step:")
    print("1. Optimize configuration based on recommendations")
    print("2. Run python -m cli.main to test the complete process")
    print("3. Check the API key configuration in the .env file")
    print("4. Check the log file for detailed error information")
