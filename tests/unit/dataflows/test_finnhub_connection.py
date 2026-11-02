#!/usr/bin/env python3
"""
Test FINNHUB API connection
"""

import sys
import os
sys.path.append('..')

def test_finnhub_api():
    """Test FINNHUB API connection"""
    print("🔍 Test FINNHUB API connection...")
    
    # Check API key
    finnhub_key = os.getenv("FINNHUB_API_KEY")
    if not finnhub_key:
        print("❌ Please set the FINNHUB_API_KEY environment variable")
        return False
    
    print(f"✅ FINNHUB API Key configured: {finnhub_key[:10]}...")
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config['online_tools'] = True
        
        # Create toolkit
        toolkit = Toolkit()
        toolkit.update_config(config)
        
        # Test FINNHUB News API
        print(f"\n📰 Test FINNHUB News API...")
        try:
            news_result = toolkit.get_finnhub_news.invoke({
                'ticker': 'AAPL',
                'start_date': '2025-06-25',
                'end_date': '2025-06-29'
            })
            print(f"✅ FINNHUB News API call successful")
            print(f"News data length: {len(news_result) if news_result else 0}")
            if news_result and len(news_result) > 100:
                print(f"First 200 characters of news content:")
                print(news_result[:200])
            else:
                print(f"News content: {news_result}")
        except Exception as e:
            print(f"❌ FINNHUB News API call failed: {e}")
        
        # Testing Yahoo Finance data API
        print(f"\n📊 Testing Yahoo Finance data API...")
        try:
            stock_result = toolkit.get_YFin_data_online.invoke({
                'symbol': 'AAPL',
                'start_date': '2025-06-25',
                'end_date': '2025-06-29'
            })
            print(f"✅ Yahoo Finance API Call successful")
            print(f"Stock data length: {len(stock_result) if stock_result else 0}")
            if stock_result and len(stock_result) > 100:
                print(f"The first 200 characters of stock data:")
                print(stock_result[:200])
            else:
                print(f"stock data: {stock_result}")
        except Exception as e:
            print(f"❌ Yahoo Finance API call failed: {e}")
        
        # Testing OpenAI Fundamentals API
        print(f"\n💼 Testing OpenAI Fundamentals API...")
        try:
            fundamentals_result = toolkit.get_fundamentals_openai.invoke({
                'ticker': 'AAPL',
                'curr_date': '2025-06-29'
            })
            print(f"✅ OpenAI Fundamentals API call successful")
            print(f"Fundamental data length: {len(fundamentals_result) if fundamentals_result else 0}")
            if fundamentals_result and len(fundamentals_result) > 100:
                print(f"The first 200 characters of fundamental data:")
                print(fundamentals_result[:200])
            else:
                print(f"fundamental data: {fundamentals_result}")
        except Exception as e:
            print(f"❌ OpenAI Fundamentals API call failed: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_china_stock_api():
    """Test China Stock API connection"""
    print("\n" + "="*50)
    print("🔍 Test China Stock API connection...")
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config['online_tools'] = True
        
        # Create toolkit
        toolkit = Toolkit()
        toolkit.update_config(config)
        
        # Test China stock data API
        print(f"\n📊 Test China stock data API...")
        try:
            china_result = toolkit.get_china_stock_data.invoke({
                'stock_code': '000001',
                'start_date': '2025-06-25',
                'end_date': '2025-06-29'
            })
            print(f"✅ China stock data API call successful")
            print(f"Stock data length: {len(china_result) if china_result else 0}")
            if china_result and len(china_result) > 100:
                print(f"The first 200 characters of stock data:")
                print(china_result[:200])
            else:
                print(f"stock data: {china_result}")
        except Exception as e:
            print(f"❌ China stock data API call failed: {e}")
        
        # Testing China Stock Fundamentals API
        print(f"\n💼 Testing China Stock Fundamentals API...")
        try:
            china_fundamentals_result = toolkit.get_china_fundamentals.invoke({
                'ticker': '000001',
                'curr_date': '2025-06-29'
            })
            print(f"✅ China stock fundamentals API call successful")
            print(f"Fundamental data length: {len(china_fundamentals_result) if china_fundamentals_result else 0}")
            if china_fundamentals_result and len(china_fundamentals_result) > 100:
                print(f"The first 200 characters of fundamental data:")
                print(china_fundamentals_result[:200])
            else:
                print(f"fundamental data: {china_fundamentals_result}")
        except Exception as e:
            print(f"❌ China Stock Fundamentals API call failed: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Start API connection test")
    print("="*50)
    
    # Test US stocks API
    result1 = test_finnhub_api()
    
    # Testing Chinese stocks API
    result2 = test_china_stock_api()
    
    print("\n" + "="*50)
    print("🎯 Test summary:")
    print(f"US Stock API Test: {'✅ success' if result1 else '❌ failed'}")
    print(f"China Stock API Test: {'✅ success' if result2 else '❌ failed'}")
    
    if result1 and result2:
        print("🎉 All API connections are normal and stock analysis can be performed!")
    else:
        print("⚠️ There is a problem with some API connections, please check the configuration and network connection.")
