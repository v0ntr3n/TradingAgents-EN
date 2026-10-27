#!/usr/bin/env python3
"""
Test DeepSeek cost calculation detailed debugging
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

def test_deepseek_cost_debug():
    """Test DeepSeek cost calculation and observe detailed logs"""
    print("🔬 DeepSeek Cost calculation detailed debugging")
    print("=" * 60)
    
    # Check API key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ DEEPSEEK_API_KEY not found, unable to test")
        return False
    
    try:
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
        
        print("🔧 Create DeepSeek instance...")
        
        # Create DeepSeek instance
        deepseek_llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.1,
            max_tokens=50  # Limit the number of tokens and reduce output
        )
        
        print(f"📊 Model name: {deepseek_llm.model_name}")
        print("\n" + "="*80)
        print("Start calling DeepSeek and observe the detailed cost calculation log:")
        print("="*80)
        
        # test call
        result = deepseek_llm.invoke("hello")
        
        print("="*80)
        print("Call completed!")
        print("="*80)
        
        print(f"📊 Response content: {result.content}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """main function"""
    print("🔬 DeepSeek Detailed commissioning and testing of cost calculations")
    print("=" * 80)
    print("📝 This test will show each step of the cost calculation")
    print("=" * 80)
    
    success = test_deepseek_cost_debug()
    
    if success:
        print("\n🎉 Test completed!")
        print("Please check the detailed log above to find out why the cost calculation is 0.")
    else:
        print("\n❌ test failed")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
