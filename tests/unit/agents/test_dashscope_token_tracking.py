#!/usr/bin/env python3
"""
Test the token statistics function of DashScope adapter
"""

import os
import sys
import time
from datetime import datetime

# Add project root directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tradingagents.llm_adapters.dashscope_adapter import ChatDashScope
from tradingagents.config.config_manager import config_manager, token_tracker
from langchain_core.messages import HumanMessage


def test_dashscope_token_tracking():
    """Test the token statistics function of DashScope adapter"""
    print("🧪 Start testing DashScope Token statistics function...")
    
    # Check API key
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("❌ DASHSCOPE_API_KEY environment variable not found")
        print("Please set it in the .env file DASHSCOPE_API_KEY")
        return False
    
    try:
        # Initialize the DashScope adapter
        print("📝 Initialize the DashScope adapter...")
        llm = ChatDashScope(
            model="qwen-turbo",
            api_key=api_key,
            temperature=0.7,
            max_tokens=500
        )
        
        # Get initial statistics
        initial_stats = config_manager.get_usage_statistics(1)
        initial_cost = initial_stats.get("total_cost", 0)
        initial_requests = initial_stats.get("total_requests", 0)
        
        print(f"📊 Initial Statistics - Cost: ¥{initial_cost:.4f}, Number of requests: {initial_requests}")
        
        # test message
        test_messages = [
            HumanMessage(content="Please briefly introduce the basic concepts of stock investment, no more than 100 words.")
        ]
        
        # Generate session ID
        session_id = f"test_session_{int(time.time())}"
        
        print(f"🚀 Send test request (session ID: {session_id})...")
        
        # Call LLM (pass in session_id and analysis_type)
        response = llm.invoke(
            test_messages,
            session_id=session_id,
            analysis_type="test_analysis"
        )
        
        print(f"✅ response received: {response.content[:100]}...")
        
        # Wait to make sure the record is saved
        time.sleep(1)
        
        # Get updated statistics
        updated_stats = config_manager.get_usage_statistics(1)
        updated_cost = updated_stats.get("total_cost", 0)
        updated_requests = updated_stats.get("total_requests", 0)
        
        print(f"📊 Updated Statistics - Costs: ¥{updated_cost:.4f}, Number of requests: {updated_requests}")
        
        # Check if there are new records
        cost_increase = updated_cost - initial_cost
        requests_increase = updated_requests - initial_requests
        
        print(f"📈 Change - cost increase: ¥{cost_increase:.4f}, Request to add: {requests_increase}")
        
        # Verification results
        if requests_increase > 0:
            print("✅ Token Statistics function works fine!")
            
            # Show supplier statistics
            provider_stats = updated_stats.get("provider_stats", {})
            dashscope_stats = provider_stats.get("dashscope", {})
            
            if dashscope_stats:
                print(f"📊 DashScope statistics:")
                print(f"   - cost: ¥{dashscope_stats.get('cost', 0):.4f}")
                print(f"   - input tokens: {dashscope_stats.get('input_tokens', 0)}")
                print(f"   - output tokens: {dashscope_stats.get('output_tokens', 0)}")
                print(f"   - Number of requests: {dashscope_stats.get('requests', 0)}")
            
            # Test session cost query
            session_cost = token_tracker.get_session_cost(session_id)
            print(f"💰 session cost: ¥{session_cost:.4f}")
            
            return True
        else:
            print("❌ Token Statistics function is not working properly")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mongodb_storage():
    """Test MongoDB storage capabilities"""
    print("\n🧪 Test MongoDB storage capabilities...")
    
    # Check if enabled MongoDB
    use_mongodb = os.getenv("USE_MONGODB_STORAGE", "false").lower() == "true"
    
    if not use_mongodb:
        print("ℹ️ MongoDB Storage not enabled, skipping MongoDB test")
        print("To enable MongoDB storage, set in the .env file USE_MONGODB_STORAGE=true")
        return True
    
    # Check MongoDB connection
    if config_manager.mongodb_storage and config_manager.mongodb_storage.is_connected():
        print("✅ MongoDB The connection is normal")
        
        # Test cleaning function (clean test records older than 1 day)
        try:
            deleted_count = config_manager.mongodb_storage.cleanup_old_records(1)
            print(f"🧹 Cleaned up {deleted_count} old test records")
        except Exception as e:
            print(f"⚠️ Cleaning old records failed: {e}")
        
        return True
    else:
        print("❌ MongoDB Connection failed")
        print("Please check MongoDB configuration and connection string")
        return False


def main():
    """Main test function"""
    print("🔬 DashScope Token Statistics and MongoDB storage testing")
    print("=" * 50)
    
    # Show configuration status
    env_status = config_manager.get_env_config_status()
    print(f"📋 configuration status:")
    print(f"   - .env File exists: {env_status['env_file_exists']}")
    print(f"   - DashScope API: {env_status['api_keys']['dashscope']}")
    
    # Check MongoDB configuration
    use_mongodb = os.getenv("USE_MONGODB_STORAGE", "false").lower() == "true"
    print(f"   - MongoDB storage: {use_mongodb}")
    
    if use_mongodb:
        mongodb_conn = os.getenv("MONGODB_CONNECTION_STRING", "Not configured")
        mongodb_db = os.getenv("MONGODB_DATABASE_NAME", "tradingagents")
        print(f"   - MongoDB connect: {mongodb_conn}")
        print(f"   - MongoDB database: {mongodb_db}")
    
    print("\n" + "=" * 50)
    
    # Run tests
    success = True
    
    # Test DashScope token statistics
    if not test_dashscope_token_tracking():
        success = False
    
    # Test MongoDB storage
    if not test_mongodb_storage():
        success = False
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 All tests passed!")
    else:
        print("❌ Some tests failed")
    
    return success


if __name__ == "__main__":
    main()