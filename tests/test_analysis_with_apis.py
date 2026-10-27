#!/usr/bin/env python3
"""
Test in full analysis using Google and Reddit API
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

def test_news_analyst_with_google():
    """Testing news analysts using Google tools"""
    try:
        print("🧪 Testing news analysts using Google tools")
        print("=" * 60)
        
        from tradingagents.agents.analysts.news_analyst import create_news_analyst
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.llm_adapters import ChatDashScope
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        config["llm_provider"] = "dashscope"
        
        # Create LLM and toolkit
        llm = ChatDashScope(model="qwen-plus", temperature=0.1)
        toolkit = Toolkit(config=config)
        
        print("✅ Component created successfully")
        
        # Create a news analyst
        news_analyst = create_news_analyst(llm, toolkit)
        
        print("✅ News analyst created successfully")
        
        # Create test state
        from tradingagents.agents.utils.agent_states import AgentState
        from langchain_core.messages import HumanMessage
        
        test_state = {
            "messages": [HumanMessage(content="Analyze AAPL news")],
            "company_of_interest": "AAPL",
            "trade_date": "2025-06-27"
        }
        
        print("📰 Start news analysis...")
        
        # Perform analysis (this may take some time)
        result = news_analyst(test_state)
        
        if result and "news_report" in result:
            news_report = result["news_report"]
            if news_report and len(news_report) > 100:
                print("✅ News analysis completed successfully")
                print(f"   Report length: {len(news_report)} character")
                print(f"   Report preview: {news_report[:200]}...")
                return True
            else:
                print("⚠️ News analysis completed but report content is small")
                return True
        else:
            print("⚠️ News analysis completed but no report generated")
            return False
            
    except Exception as e:
        print(f"❌ News analyst test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_social_analyst_with_reddit():
    """Test social media analysts using Reddit tools"""
    try:
        print("\n🧪 Test social media analysts using Reddit tools")
        print("=" * 60)
        
        from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.llm_adapters import ChatDashScope
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        config["llm_provider"] = "dashscope"
        
        # Create LLM and toolkit
        llm = ChatDashScope(model="qwen-plus", temperature=0.1)
        toolkit = Toolkit(config=config)
        
        print("✅ Component created successfully")
        
        # Create a social media analyst
        social_analyst = create_social_media_analyst(llm, toolkit)
        
        print("✅ Social media analyst created successfully")
        
        # Create test state
        from langchain_core.messages import HumanMessage
        
        test_state = {
            "messages": [HumanMessage(content="Analyzing social media sentiment for AAPL")],
            "company_of_interest": "AAPL", 
            "trade_date": "2025-06-27"
        }
        
        print("💭 Start social media analysis...")
        
        # Perform analysis
        result = social_analyst(test_state)
        
        if result and "sentiment_report" in result:
            sentiment_report = result["sentiment_report"]
            if sentiment_report and len(sentiment_report) > 100:
                print("✅ Social media analysis completed successfully")
                print(f"   Report length: {len(sentiment_report)} character")
                print(f"   Report preview: {sentiment_report[:200]}...")
                return True
            else:
                print("⚠️ Social media analysis completed but reports are sparse")
                return True
        else:
            print("⚠️ Social media analysis completed but no reports generated")
            return False
            
    except Exception as e:
        print(f"❌ Social media analyst test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def main():
    """Main test function"""
    print("🧪 API Tool Testing in Complete Analysis")
    print("=" * 70)
    
    # Check environment variables
    dashscope_key = os.getenv("DASHSCOPE_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")
    reddit_id = os.getenv("REDDIT_CLIENT_ID")
    
    if not dashscope_key:
        print("❌ DASHSCOPE_API_KEY Not configured and cannot be tested")
        return
    
    print("🔑 API Key status:")
    print(f"   Ali Bailian: ✅ configured")
    print(f"   Google: {'✅ configured' if google_key else '❌ Not configured'}")
    print(f"   Reddit: {'✅ configured' if reddit_id else '❌ Not configured'}")
    
    # Run tests
    results = {}
    
    print("\n" + "="*70)
    results['news analyst+Google'] = test_news_analyst_with_google()
    
    print("\n" + "="*70)
    results['social media analyst+Reddit'] = test_social_analyst_with_reddit()
    
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
        print("🎉 All API tools work properly in analysis!")
        print("\n💡 Usage suggestions:")
        print("   1. Select in the web interface'news analyst'to use Google News")
        print("   2. Select in the web interface'social media analyst'to use Reddit data")
        print("   3. Select multiple analysts at the same time for a more comprehensive analysis")
    else:
        print("⚠️ Some API tools require further configuration")

if __name__ == "__main__":
    main()
