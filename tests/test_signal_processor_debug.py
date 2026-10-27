#!/usr/bin/env python3
"""
Debug script for testing signal handlers
"""

import sys
import os
sys.path.append('..')

def test_signal_processor():
    """Test signal processor functionality"""
    print("🔍 Test signal processor...")
    
    try:
        from tradingagents.graph.signal_processing import SignalProcessor
        from tradingagents.llm_adapters import ChatDashScope
        
        # Create LLM instance
        llm = ChatDashScope(
            model="qwen-plus-latest",
            temperature=0.1,
            max_tokens=1000
        )
        
        # Create signal handler
        processor = SignalProcessor(llm)
        print("✅ Signal handler created successfully")
        
        # test signal
        test_signal = """
        Based on a thorough analysis, I recommend a hold strategy on the stock.
        
        Investment advice: Hold
        Confidence:75%
        Target price:¥45.50
        Risk score:40%
        
        Main reasons:
        1. Technicals show an uptrend
        2. Fundamentals are solid
        3. Market sentiment is positive
        """
        
        print(f"\n📊 Test signal content:")
        print(test_signal)
        
        # Process signals
        print(f"\n🔄 Start processing signals...")
        result = processor.process_signal(test_signal, "000001")
        
        print(f"\n✅ Processing results:")
        print(f"Type: {type(result)}")
        print(f"content: {result}")
        
        # Check result structure
        if isinstance(result, dict):
            print(f"\n📋 Result details:")
            for key, value in result.items():
                print(f"  {key}: {value}")
        
        return result
        
    except Exception as e:
        print(f"❌ test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def test_trading_graph():
    """Test the complete trading graph"""
    print("\n" + "="*50)
    print("🔍 Test the complete transaction graph...")
    
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config['llm_provider'] = 'Ali Bailian'
        config['quick_think_llm'] = 'qwen-plus-latest'
        config['deep_think_llm'] = 'qwen-plus-latest'
        
        print(f"📊 Configuration information:")
        print(f"  LLM provider: {config['llm_provider']}")
        print(f"  quick model: {config['quick_think_llm']}")
        print(f"  deep model: {config['deep_think_llm']}")
        
        # Create transaction diagram
        print(f"\n🔄 Create transaction diagram...")
        graph = TradingAgentsGraph(analysts=['market'], config=config, debug=False)
        print("✅ Trading chart created successfully")
        
        # Test signal processor
        print(f"\n🔄 Test signal processor...")
        test_signal = "Recommendation: Buy\n Target price:¥50.00\n Confidence:80%\n Risk score:30%"
        result = graph.process_signal(test_signal, "000001")
        
        print(f"✅ Signal processing results:")
        print(f"Type: {type(result)}")
        print(f"content: {result}")
        
        return result
        
    except Exception as e:
        print(f"❌ test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("🚀 Start signal handler debugging test")
    print("="*50)
    
    # Check API key
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("❌ Please set the DASHSCOPE_API_KEY environment variable")
        sys.exit(1)
    
    print(f"✅ API Key configured: {api_key[:10]}...")
    
    # Test signal processor
    result1 = test_signal_processor()
    
    # Test trading chart
    result2 = test_trading_graph()
    
    print("\n" + "="*50)
    print("🎯 Test summary:")
    print(f"Signal Processor Test: {'✅ success' if result1 else '❌ failed'}")
    print(f"Trading graph test: {'✅ success' if result2 else '❌ failed'}")
