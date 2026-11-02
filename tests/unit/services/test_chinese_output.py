#!/usr/bin/env python3
"""
Test Chinese output function
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

def test_dashscope_chinese():
    """Test the Chinese output of Alibaba Bailian model"""
    try:
        from tradingagents.llm_adapters import ChatDashScope
        
        print("🧪 Test the Chinese output of Alibaba Bailian model")
        print("=" * 50)
        
        # Create model instance
        llm = ChatDashScope(
            model="qwen-plus",
            temperature=0.1,
            max_tokens=500
        )
        
        # Test Chinese Prompt Words
        test_prompt = """You are a professional stock analyst. Please analyze Apple in Chinese(AAPL)investment prospects.
        
Please focus on:
1. The company s competitive advantage
2. Market prospects
3. investment advice

Please make sure to answer in Chinese."""
        
        print("Send test prompt word...")
        response = llm.invoke(test_prompt)
        
        print("✅ The model responded successfully")
        print(f"Response content: {response.content[:200]}...")
        
        # Check if it contains Chinese
        chinese_chars = sum(1 for char in response.content if '\u4e00' <= char <= '\u9fff')
        total_chars = len(response.content)
        chinese_ratio = chinese_chars / total_chars if total_chars > 0 else 0
        
        print(f"Chinese character ratio: {chinese_ratio:.2%}")
        
        if chinese_ratio > 0.3:
            print("✅ The model correctly outputs Chinese content")
            return True
        else:
            print("❌ The proportion of Chinese output in the model is low")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_signal_processor_chinese():
    """Test the Chinese output of the signal processor"""
    try:
        from tradingagents.graph.signal_processing import SignalProcessor
        from tradingagents.llm_adapters import ChatDashScope
        
        print("\n🧪 Test signal processor Chinese output")
        print("=" * 50)
        
        # Create model instance
        llm = ChatDashScope(
            model="qwen-plus",
            temperature=0.1,
            max_tokens=100
        )
        
        # Create signal handler
        processor = SignalProcessor(llm)
        
        # test signal
        test_signal = """Based on technical and fundamental analysis, Apple shows strong growth potential.
        It is recommended to buy the stock with a target price of $200."""
        
        print("Process test signals...")
        decision = processor.process_signal(test_signal, "AAPL")
        
        print(f"✅ Signal processing successful")
        print(f"decision result: {decision}")
        
        # Check if the decision is in Chinese
        if any(word in decision for word in ['buy', 'sell', 'hold']):
            print("✅ Signal processor outputs Chinese decision-making")
            return True
        elif any(word in decision.upper() for word in ['BUY', 'SELL', 'HOLD']):
            print("⚠️ Signal processor output English decision")
            return False
        else:
            print(f"❓ Unrecognized decision format: {decision}")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def main():
    """Main test function"""
    print("🧪 Chinese output function test")
    print("=" * 60)
    
    # Check environment variables
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("❌ DASHSCOPE_API_KEY Environment variable not set")
        return
    
    # Test basic Chinese output
    success1 = test_dashscope_chinese()
    
    # Test signal processor
    success2 = test_signal_processor_chinese()
    
    print(f"\n📊 Test results:")
    print(f"  Basic Chinese output: {'✅ Pass' if success1 else '❌ failed'}")
    print(f"  signal processor: {'✅ Pass' if success2 else '❌ failed'}")
    
    if success1 and success2:
        print("\n🎉 All tests passed! Chinese output function is normal")
    else:
        print("\n⚠️ Some tests failed and may require further adjustments")

if __name__ == "__main__":
    main()
