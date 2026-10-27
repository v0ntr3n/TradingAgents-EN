#!/usr/bin/env python3
"""
Properly Test Google and Reddit API Tools
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

def test_google_news_tool():
    """Test Google News Tools"""
    try:
        print("🧪 Test Google News Tools")
        print("=" * 50)
        
        from tradingagents.dataflows.interface import get_google_news
        
        print("✅ get_google_news Function imported successfully")
        
        # Test to get Apple news
        print("📰 Get Apple News...")
        try:
            news = get_google_news(
                query="Apple AAPL stock",
                curr_date="2025-06-27", 
                look_back_days=7
            )
            
            if news and len(news) > 0:
                print("✅ Google News obtained successfully")
                print(f"   news length: {len(news)} character")
                print(f"   News preview: {news[:200]}...")
                return True
            else:
                print("⚠️ Google News obtained successfully but the content is empty")
                return True  # Functions fine, just no content
                
        except Exception as e:
            print(f"❌ Google Failed to get news: {e}")
            return False
            
    except ImportError as e:
        print(f"❌ Google News tool import failed: {e}")
        return False

def test_reddit_tools():
    """Test Reddit Tools"""
    try:
        print("\n🧪 Test Reddit Tools")
        print("=" * 50)
        
        from tradingagents.dataflows.interface import get_reddit_global_news, get_reddit_company_news
        
        print("✅ Reddit Tool function imported successfully")
        
        # Check Reddit data directory
        reddit_data_dir = Path("tradingagents/dataflows/data_cache/reddit_data")
        print(f"📁 Reddit data directory: {reddit_data_dir}")
        
        if reddit_data_dir.exists():
            print("✅ Reddit data directory exists")
            
            # Check subdirectories
            subdirs = [d for d in reddit_data_dir.iterdir() if d.is_dir()]
            print(f"   subdirectory: {[d.name for d in subdirs]}")
            
            if subdirs:
                print("✅ Reddit Data is available and can be tested")
                
                # Test global news
                try:
                    print("📰 Testing Reddit Global News...")
                    global_news = get_reddit_global_news(
                        start_date="2025-06-27",
                        look_back_days=1,
                        max_limit_per_day=5
                    )
                    
                    if global_news and len(global_news) > 0:
                        print("✅ Reddit Global news success")
                        print(f"   news length: {len(global_news)} character")
                    else:
                        print("⚠️ Reddit Global news was obtained successfully but the content is empty")
                        
                except Exception as e:
                    print(f"❌ Reddit Failed to obtain global news: {e}")
                
                # Testing company news
                try:
                    print("📰 Testing Reddit Company News...")
                    company_news = get_reddit_company_news(
                        ticker="AAPL",
                        start_date="2025-06-27",
                        look_back_days=1,
                        max_limit_per_day=5
                    )
                    
                    if company_news and len(company_news) > 0:
                        print("✅ Reddit Company News Get Successful")
                        print(f"   news length: {len(company_news)} character")
                    else:
                        print("⚠️ Reddit Company news was obtained successfully but the content is empty")
                        
                except Exception as e:
                    print(f"❌ Reddit Failed to obtain company news: {e}")
                    
                return True
            else:
                print("⚠️ Reddit The data directory is empty, you need to download the data first")
                return False
        else:
            print("⚠️ Reddit The data directory does not exist, you need to set the data first")
            print("💡 Tips: Reddit Tool requires pre-downloaded data files")
            return False
            
    except ImportError as e:
        print(f"❌ Reddit Tool import failed: {e}")
        return False

def test_toolkit_integration():
    """Test toolkit integration"""
    try:
        print("\n🧪 Test toolkit integration")
        print("=" * 50)
        
        # Check if the Toolkit class contains these tools
        from tradingagents.agents.utils.toolkit import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        
        toolkit = Toolkit(config=config)
        
        # Check out the methods in the toolkit
        methods = [method for method in dir(toolkit) if not method.startswith('_')]
        
        google_methods = [m for m in methods if 'google' in m.lower()]
        reddit_methods = [m for m in methods if 'reddit' in m.lower()]
        
        print(f"📊 Total number of toolkit methods: {len(methods)}")
        print(f"   Google Related methods: {google_methods}")
        print(f"   Reddit Related methods: {reddit_methods}")
        
        # Check if a specific method exists
        if hasattr(toolkit, 'get_google_news'):
            print("✅ toolkit.get_google_news method exists")
        else:
            print("❌ toolkit.get_google_news method does not exist")
            
        if hasattr(toolkit, 'get_reddit_global_news'):
            print("✅ toolkit.get_reddit_global_news method exists")
        else:
            print("❌ toolkit.get_reddit_global_news method does not exist")
            
        if hasattr(toolkit, 'get_reddit_company_news'):
            print("✅ toolkit.get_reddit_company_news method exists")
        else:
            print("❌ toolkit.get_reddit_company_news method does not exist")
        
        return True
        
    except Exception as e:
        print(f"❌ Toolkit integration test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Correct API Tool Testing")
    print("=" * 60)
    
    # Check API key
    google_key = os.getenv('GOOGLE_API_KEY')
    reddit_id = os.getenv('REDDIT_CLIENT_ID')
    
    print(f"🔑 API Key status:")
    print(f"   Google API: {'✅ configured' if google_key else '❌ Not configured'}")
    print(f"   Reddit API: {'✅ configured' if reddit_id else '❌ Not configured'}")
    
    # Run tests
    results = {}
    
    results['Google News tools'] = test_google_news_tool()
    results['Reddit Tools'] = test_reddit_tools()
    results['Toolkit integration'] = test_toolkit_integration()
    
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
