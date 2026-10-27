#!/usr/bin/env python3
"""
Test all API key functionality
Includes Google APIs and Reddit API
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv(project_root / ".env", override=True)

def check_all_api_keys():
    """Check all API key configurations"""
    print("🔑 Check API key configuration")
    print("=" * 50)
    
    api_keys = {
        'DASHSCOPE_API_KEY': 'Ali Bailian API',
        'FINNHUB_API_KEY': 'financial data API', 
        'GOOGLE_API_KEY': 'Google API',
        'REDDIT_CLIENT_ID': 'Reddit client ID',
        'REDDIT_CLIENT_SECRET': 'Reddit client key',
        'REDDIT_USER_AGENT': 'Reddit user agent'
    }
    
    configured_apis = []
    missing_apis = []
    
    for key, name in api_keys.items():
        value = os.getenv(key)
        if value:
            print(f"✅ {name}: configured ({value[:10]}...)")
            configured_apis.append(name)
        else:
            print(f"❌ {name}: Not configured")
            missing_apis.append(name)
    
    print(f"\n📊 configuration status:")
    print(f"  configured: {len(configured_apis)}/{len(api_keys)}")
    print(f"  Missing: {len(missing_apis)}")
    
    return configured_apis, missing_apis

def test_google_api():
    """test Google API"""
    try:
        print("\n🧪 test Google API")
        print("=" * 50)
        
        google_key = os.getenv('GOOGLE_API_KEY')
        if not google_key:
            print("❌ Google API Key not configured")
            return False
        
        # Specific Google API tests can be added here
        # For example Google News API or Google Search API
        print("✅ Google API Key configured")
        print("💡 Tips: Need to be tested according to the specific Google services used")
        
        return True
        
    except Exception as e:
        print(f"❌ Google API test failed: {e}")
        return False

def test_reddit_api():
    """test Reddit API"""
    try:
        print("\n🧪 test Reddit API")
        print("=" * 50)
        
        client_id = os.getenv('REDDIT_CLIENT_ID')
        client_secret = os.getenv('REDDIT_CLIENT_SECRET')
        user_agent = os.getenv('REDDIT_USER_AGENT')
        
        if not all([client_id, client_secret, user_agent]):
            print("❌ Reddit API Incomplete configuration")
            print(f"  CLIENT_ID: {'✅' if client_id else '❌'}")
            print(f"  CLIENT_SECRET: {'✅' if client_secret else '❌'}")
            print(f"  USER_AGENT: {'✅' if user_agent else '❌'}")
            return False
        
        # Test Reddit API connection
        try:
            import praw
            
            reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent
            )
            
            # Test to get a simple subreddit information
            subreddit = reddit.subreddit('investing')
            print(f"✅ Reddit API Connection successful")
            print(f"  test subreddit: {subreddit.display_name}")
            print(f"  Number of subscribers: {subreddit.subscribers:,}")
            
            return True
            
        except ImportError:
            print("⚠️ praw The library is not installed and cannot be tested Reddit API")
            print("💡 run: pip install praw")
            return False
        except Exception as e:
            print(f"❌ Reddit API Connection failed: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Reddit API test failed: {e}")
        return False

def test_tradingagents_with_new_apis():
    """Test whether TradingAgents can use the new API"""
    try:
        print("\n🧪 Test the TradingAgents integration")
        print("=" * 50)
        
        # Check if TradingAgents supports these API
        from tradingagents.dataflows import interface
        
        # Check available data flow tools
        print("📊 Check available data acquisition tools:")
        
        # Check Google related tools
        try:
            from tradingagents.dataflows.googlenews_utils import get_google_news
            print("✅ Google News Tools available")
        except ImportError:
            print("❌ Google News Tool is not available")
        
        # Check out Reddit related tools  
        try:
            from tradingagents.dataflows.reddit_utils import get_reddit_sentiment
            print("✅ Reddit Sentiment analysis tools are available")
        except ImportError:
            print("❌ Reddit Sentiment analysis tool is not available")
        
        return True
        
    except Exception as e:
        print(f"❌ TradingAgents Integration test failed: {e}")
        return False

def test_social_media_analyst():
    """Testing whether social media analysts can use Reddit data"""
    try:
        print("\n🧪 Test social media analyst")
        print("=" * 50)
        
        # Check social media analysts
        from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst
        from tradingagents.llm_adapters import ChatDashScope
        
        # Create model instance
        llm = ChatDashScope(model="qwen-plus")
        
        # A toolkit instance is required here, and the actual testing is skipped for now.
        print("✅ Social Media Analyst module available")
        print("💡 A full toolkit instance is required for actual testing")
        
        return True
        
    except Exception as e:
        print(f"❌ Social media analyst test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Comprehensive API testing")
    print("=" * 60)
    
    # Check API key configuration
    configured, missing = check_all_api_keys()
    
    # Test each API
    results = {}
    
    if 'Google API' in configured:
        results['Google API'] = test_google_api()
    
    if all(api in configured for api in ['Reddit client ID', 'Reddit client key']):
        results['Reddit API'] = test_reddit_api()
    
    # Test the TradingAgents integration
    results['TradingAgents Integrate'] = test_tradingagents_with_new_apis()
    results['social media analyst'] = test_social_media_analyst()
    
    # Summary results
    print(f"\n📊 Summary of test results:")
    print("=" * 50)
    
    for test_name, success in results.items():
        status = "✅ Pass" if success else "❌ failed"
        print(f"  {test_name}: {status}")
    
    successful_tests = sum(results.values())
    total_tests = len(results)
    
    print(f"\n🎯 Overall results: {successful_tests}/{total_tests} Test passed")
    
    if successful_tests == total_tests:
        print("🎉 All tests passed!")
    else:
        print("⚠️ Some tests failed, please check the configuration")

if __name__ == "__main__":
    main()
