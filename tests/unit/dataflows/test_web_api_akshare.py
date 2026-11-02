#!/usr/bin/env python3
"""
Testing AKShare functionality in Web API
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import time
from datetime import datetime, timedelta

# Setup log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)

def test_akshare_web_api():
    """Testing AKShare s performance in Web API"""
    print("=" * 60)
    print("🌐 Test AKShare Web API compatibility")
    print("=" * 60)
    
    try:
        from app.services.data_source_adapters import AKShareAdapter
        
        adapter = AKShareAdapter()
        
        if not adapter.is_available():
            print("❌ AKShare Adapter not available")
            return
        
        print("✅ AKShare Adapters available")
        
        # Simulate the testing process of Web API
        results = {}
        total_start = time.time()
        
        # 1. Stock List Test
        print("\n1. 📊 Stock List Test...")
        start = time.time()
        try:
            stock_df = adapter.get_stock_list()
            duration = time.time() - start
            
            if stock_df is not None and not stock_df.empty:
                results['stock_list'] = {
                    'status': 'success',
                    'count': len(stock_df),
                    'duration': duration,
                    'message': f'Successfully fetched {len(stock_df)} stocks'
                }
                print(f"   ✅ success: {len(stock_df)}records, time consuming: {duration:.1f}seconds")
            else:
                results['stock_list'] = {
                    'status': 'failed',
                    'count': 0,
                    'duration': duration,
                    'message': 'No stock data returned'
                }
                print(f"   ❌ failed: No data returned, time consuming: {duration:.1f}seconds")
        except Exception as e:
            duration = time.time() - start
            results['stock_list'] = {
                'status': 'error',
                'count': 0,
                'duration': duration,
                'message': f'Error: {str(e)}'
            }
            print(f"   ❌ Error: {e}, Time consuming: {duration:.1f}seconds")
        
        # 2. Transaction date test
        print("\n2. 📅 Transaction date test...")
        start = time.time()
        try:
            latest_date = adapter.find_latest_trade_date()
            duration = time.time() - start
            
            if latest_date:
                results['trade_date'] = {
                    'status': 'success',
                    'date': latest_date,
                    'duration': duration,
                    'message': f'Found latest trade date: {latest_date}'
                }
                print(f"   ✅ success: {latest_date}, Time consuming: {duration:.1f}seconds")
            else:
                results['trade_date'] = {
                    'status': 'failed',
                    'date': None,
                    'duration': duration,
                    'message': 'No trade date found'
                }
                print(f"   ❌ failed: No transaction date, time consuming: {duration:.1f}seconds")
        except Exception as e:
            duration = time.time() - start
            results['trade_date'] = {
                'status': 'error',
                'date': None,
                'duration': duration,
                'message': f'Error: {str(e)}'
            }
            print(f"   ❌ Error: {e}, Time consuming: {duration:.1f}seconds")
        
        # 3. Financial data testing
        print("\n3. 💰 Financial data testing...")
        start = time.time()
        try:
            trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            basic_df = adapter.get_daily_basic(trade_date)
            duration = time.time() - start
            
            if basic_df is not None and not basic_df.empty:
                results['daily_basic'] = {
                    'status': 'success',
                    'count': len(basic_df),
                    'duration': duration,
                    'message': f'Successfully fetched basic data for {trade_date}, {len(basic_df)} records'
                }
                print(f"   ✅ success: {len(basic_df)}records, time consuming: {duration:.1f}seconds")
            else:
                results['daily_basic'] = {
                    'status': 'failed',
                    'count': 0,
                    'duration': duration,
                    'message': 'No daily basic data available or not supported'
                }
                print(f"   ❌ failed: No financial data, time consuming: {duration:.1f}seconds")
        except Exception as e:
            duration = time.time() - start
            results['daily_basic'] = {
                'status': 'error',
                'count': 0,
                'duration': duration,
                'message': f'Error: {str(e)}'
            }
            print(f"   ❌ Error: {e}, Time consuming: {duration:.1f}seconds")
        
        total_duration = time.time() - total_start
        
        # Output results in Web API format
        print(f"\n📊 Web API Test results:")
        print(f"   Total time spent: {total_duration:.1f}seconds")
        
        web_result = {
            'name': 'akshare',
            'priority': 2,
            'description': 'Open source financial database, providing basic stock information',
            'available': True,
            'tests': {
                'stock_list': results.get('stock_list', {}),
                'trade_date': results.get('trade_date', {}),
                'daily_basic': results.get('daily_basic', {})
            },
            'total_duration': total_duration
        }
        
        print(f"\n🔍 Detailed results:")
        for test_name, test_result in web_result['tests'].items():
            status = test_result.get('status', 'unknown')
            duration = test_result.get('duration', 0)
            message = test_result.get('message', 'No message')
            
            status_icon = "✅" if status == 'success' else "❌"
            print(f"   {status_icon} {test_name}: {message} ({duration:.1f}s)")
        
        # Web Timeout evaluation
        print(f"\n🌐 Web Compatibility assessment:")
        if total_duration < 30:
            print(f"   🎯 Excellent: Total time spent {total_duration:.1f}seconds < 30 seconds")
        elif total_duration < 60:
            print(f"   ⚠️ acceptable: Total time spent {total_duration:.1f}seconds < 60 seconds")
        else:
            print(f"   ❌ Timeout risk: Total time spent {total_duration:.1f}seconds > 60 seconds")
        
        return web_result
        
    except Exception as e:
        print(f"❌ Web API test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = test_akshare_web_api()
    if result:
        print(f"\n✅ Testing completed, AKShare Web API compatibility: {'good' if result['total_duration'] < 60 else 'Need optimization'}")
    else:
        print(f"\n❌ test failed")
