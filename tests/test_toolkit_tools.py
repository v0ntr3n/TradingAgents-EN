#!/usr/bin/env python3
"""
Google and Reddit tools in the testing toolkit
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

def test_toolkit_tools():
    """Tools in the testing toolkit"""
    try:
        print("🧪 Google and Reddit tools in the testing toolkit")
        print("=" * 60)
        
        # Import correctly Toolkit
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        
        # Create toolkit instance
        toolkit = Toolkit(config=config)
        
        print("✅ Toolkit Instance created successfully")
        
        # Check all available methods
        all_methods = [method for method in dir(toolkit) if not method.startswith('_')]
        print(f"📊 Total number of methods in the toolkit: {len(all_methods)}")
        
        # Find related methods on Google
        google_methods = [m for m in all_methods if 'google' in m.lower()]
        print(f"🔍 Google Related methods: {google_methods}")
        
        # Find related methods on Reddit
        reddit_methods = [m for m in all_methods if 'reddit' in m.lower()]
        print(f"🔍 Reddit Related methods: {reddit_methods}")
        
        # How to find news related
        news_methods = [m for m in all_methods if 'news' in m.lower()]
        print(f"📰 News related methods: {news_methods}")
        
        # Test specific Google tools
        if hasattr(toolkit, 'get_google_news'):
            print("\n✅ get_google_news method exists")
            try:
                # test call
                print("📰 Test Google News Fetch...")
                news = toolkit.get_google_news(
                    query="Apple AAPL",
                    curr_date="2025-06-27",
                    look_back_days=3
                )
                if news and len(news) > 100:
                    print(f"✅ Google News obtained successfully ({len(news)} character)")
                else:
                    print("⚠️ Google News acquisition is successful but the content is less")
            except Exception as e:
                print(f"❌ Google News test failed: {e}")
        else:
            print("❌ get_google_news method does not exist")
        
        # Test Reddit Tools
        reddit_tools = ['get_reddit_global_news', 'get_reddit_company_news', 'get_reddit_stock_info', 'get_reddit_news']
        
        for tool_name in reddit_tools:
            if hasattr(toolkit, tool_name):
                print(f"✅ {tool_name} method exists")
            else:
                print(f"❌ {tool_name} method does not exist")
        
        # Show all methods (for debugging)
        print(f"\n📋 All available methods:")
        for i, method in enumerate(sorted(all_methods), 1):
            print(f"  {i:2d}. {method}")
        
        return True
        
    except Exception as e:
        print(f"❌ Kit test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_social_news_analysts():
    """Test whether social media and news analysts can use these tools"""
    try:
        print("\n🧪 Test Analyst Tool Integration")
        print("=" * 60)
        
        # Check social media analysts
        try:
            from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst
            print("✅ Social Media Analyst module available")
        except ImportError as e:
            print(f"❌ Social media analyst import failed: {e}")
        
        # Check News Analysts
        try:
            from tradingagents.agents.analysts.news_analyst import create_news_analyst
            print("✅ News Analyst module available")
        except ImportError as e:
            print(f"❌ News analyst import failed: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Analyst test failed: {e}")
        return False

def check_data_requirements():
    """Check data requirements"""
    print("\n🧪 Check data requirements")
    print("=" * 60)
    
    # Check Reddit data directory
    reddit_data_paths = [
        "tradingagents/dataflows/data_cache/reddit_data",
        "data/reddit_data",
        "reddit_data"
    ]
    
    reddit_data_found = False
    for path in reddit_data_paths:
        reddit_path = Path(path)
        if reddit_path.exists():
            print(f"✅ Reddit Data directory found: {reddit_path}")
            subdirs = [d.name for d in reddit_path.iterdir() if d.is_dir()]
            if subdirs:
                print(f"   subdirectory: {subdirs}")
                reddit_data_found = True
            else:
                print("   Directory is empty")
            break
    
    if not reddit_data_found:
        print("⚠️ Reddit Data directory not found")
        print("💡 Reddit Tool requires pre-downloaded data files")
        print("   possible solutions:")
        print("   1. Download the Reddit dataset")
        print("   2. Configure the correct data path")
        print("   3. Use the online Reddit API (if supported)")
    
    # Check Google API requirements
    google_key = os.getenv('GOOGLE_API_KEY')
    if google_key:
        print("✅ Google API Key configured")
        print("💡 Google News tool uses web scraping, no API key required")
    else:
        print("⚠️ Google API Key not configured")
        print("💡 But Google News tools may still work (using web scraping)")

def main():
    """Main test function"""
    print("🧪 Toolkit Google and Reddit Tool Testing")
    print("=" * 70)
    
    # Check API key status
    print("🔑 API Key status:")
    google_key = os.getenv('GOOGLE_API_KEY')
    reddit_id = os.getenv('REDDIT_CLIENT_ID')
    print(f"   Google API: {'✅ configured' if google_key else '❌ Not configured'}")
    print(f"   Reddit API: {'✅ configured' if reddit_id else '❌ Not configured'}")
    
    # Run tests
    results = {}
    
    results['toolkit tools'] = test_toolkit_tools()
    results['Analyst integration'] = test_social_news_analysts()
    
    # Check data requirements
    check_data_requirements()
    
    # Summary results
    print(f"\n📊 Summary of test results:")
    print("=" * 50)
    
    for test_name, success in results.items():
        status = "✅ Pass" if success else "❌ failed"
        print(f"  {test_name}: {status}")
    
    successful_tests = sum(results.values())
    total_tests = len(results)
    
    print(f"\n🎯 Overall results: {successful_tests}/{total_tests} Test passed")

if __name__ == "__main__":
    main()
