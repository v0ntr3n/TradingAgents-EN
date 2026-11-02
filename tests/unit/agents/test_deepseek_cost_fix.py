#!/usr/bin/env python3
"""
Verify DeepSeek cost calculation fix
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

def test_deepseek_cost_calculation():
    """Testing DeepSeek Cost Calculation"""
    print("🧪 Testing DeepSeek costing fixes")
    print("=" * 50)
    
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if not deepseek_key:
        print("⚠️ DEEPSEEK_API_KEY not found, test skipped")
        return False
    
    try:
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
        from tradingagents.config.config_manager import config_manager
        
        # Get initial statistics
        initial_stats = config_manager.get_usage_statistics(1)
        initial_cost = initial_stats.get("total_cost", 0)
        
        print(f"📊 initial cost: ¥{initial_cost:.6f}")
        
        # Create DeepSeek instance
        llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.1,
            max_tokens=100
        )
        
        # Test multiple calls
        test_cases = [
            "What are stocks?",
            "Please briefly explain the meaning of P/E ratio.",
            "Analyze the investment risks."
        ]
        
        total_expected_cost = 0
        
        for i, prompt in enumerate(test_cases, 1):
            print(f"\n🔍 test {i}: {prompt}")
            
            response = llm.invoke(
                prompt,
                session_id=f"test_cost_{i}",
                analysis_type="cost_test"
            )
            
            print(f"   response length: {len(response.content)}")
        
        # Waiting for statistics update
        import time
        time.sleep(1)
        
        # Check final statistics
        final_stats = config_manager.get_usage_statistics(1)
        final_cost = final_stats.get("total_cost", 0)
        
        cost_increase = final_cost - initial_cost
        
        print(f"\n📊 final tally:")
        print(f"   initial cost: ¥{initial_cost:.6f}")
        print(f"   final cost: ¥{final_cost:.6f}")
        print(f"   cost increase: ¥{cost_increase:.6f}")
        
        # Check DeepSeek Statistics
        provider_stats = final_stats.get("provider_stats", {})
        deepseek_stats = provider_stats.get("deepseek", {})
        
        if deepseek_stats:
            print(f"   DeepSeek cost: ¥{deepseek_stats.get('cost', 0):.6f}")
            print(f"   DeepSeek Request: {deepseek_stats.get('requests', 0)}")
            print(f"   DeepSeek Token: {deepseek_stats.get('tokens', 0)}")
        
        # Verify that costs are reasonable
        if cost_increase > 0:
            print(f"\n✅ Cost calculation repair successful!")
            print(f"   average cost per call: ¥{cost_increase/len(test_cases):.6f}")
            return True
        else:
            print(f"\n❌ Cost calculations still have problems")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cost_precision():
    """Test cost accuracy display"""
    print("\n🔍 Test cost accuracy display")
    print("-" * 30)
    
    from tradingagents.config.config_manager import ConfigManager
    
    config_manager = ConfigManager()
    
    # Test small cost calculations
    test_cases = [
        (10, 5),    # Very small number of tokens
        (100, 50),  # Small number of tokens
        (1000, 500), # Medium number of tokens
        (2000, 1000) # Larger number of tokens
    ]
    
    for input_tokens, output_tokens in test_cases:
        cost = config_manager.calculate_cost("deepseek", "deepseek-chat", input_tokens, output_tokens)
        print(f"   {input_tokens:4d}+{output_tokens:4d} tokens = ¥{cost:.6f}")

def main():
    """main function"""
    success1 = test_deepseek_cost_calculation()
    test_cost_precision()
    
    print("\n" + "=" * 50)
    if success1:
        print("🎉 DeepSeek Cost calculation repair verification successful!")
    else:
        print("❌ DeepSeek Costing still needs fixing")
    
    return success1

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
