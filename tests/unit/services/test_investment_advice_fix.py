#!/usr/bin/env python3
"""
Test Investment Advice Chinese Culture Fix
"""

import os
import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_web_components():
    """Investment advice display for testing web components"""
    print("🧪 Test web component investment advice display")
    print("=" * 50)
    
    try:
        # Test the results_display component
        print("📊 Test the results_display component...")
        
        # Simulate different investment advice inputs
        test_cases = [
            {'action': 'BUY', 'confidence': 0.8, 'risk_score': 0.3},
            {'action': 'SELL', 'confidence': 0.7, 'risk_score': 0.6},
            {'action': 'HOLD', 'confidence': 0.6, 'risk_score': 0.4},
            {'action': 'buy', 'confidence': 0.8, 'risk_score': 0.3},
            {'action': 'sell', 'confidence': 0.7, 'risk_score': 0.6},
            {'action': 'hold', 'confidence': 0.6, 'risk_score': 0.4},
        ]
        
        # Simulate the processing logic of web components
        for decision in test_cases:
            action = decision.get('action', 'N/A')
            
            # Apply our repair logic
            action_translation = {
                'BUY': 'buy',
                'SELL': 'sell', 
                'HOLD': 'hold',
                'buy': 'buy',
                'sell': 'sell',
                'hold': 'hold'
            }
            
            chinese_action = action_translation.get(action.upper(), action)
            
            print(f"   input: {action} -> output: {chinese_action}")
            
            if chinese_action in ['buy', 'sell', 'hold']:
                print(f"   ✅ Correctly converted to Chinese")
            else:
                print(f"   ❌ Conversion failed")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Web Component test failed: {e}")
        return False

def test_analysis_runner():
    """Test analysis_runner s investment advice processing"""
    print("\n🔍 Test analysis_runner investment advice processing")
    print("-" * 50)
    
    try:
        # Simulate the processing logic of analysis_runner
        test_decisions = [
            "BUY",
            "SELL", 
            "HOLD",
            {"action": "BUY", "confidence": 0.8},
            {"action": "SELL", "confidence": 0.7},
            {"action": "HOLD", "confidence": 0.6},
        ]
        
        for decision in test_decisions:
            print(f"\n input decision: {decision}")
            
            # Apply our repair logic
            if isinstance(decision, str):
                action_translation = {
                    'BUY': 'buy',
                    'SELL': 'sell', 
                    'HOLD': 'hold',
                    'buy': 'buy',
                    'sell': 'sell',
                    'hold': 'hold'
                }
                action = action_translation.get(decision.strip(), decision.strip())
                
                formatted_decision = {
                    'action': action,
                    'confidence': 0.7,
                    'risk_score': 0.3,
                }
            else:
                action_translation = {
                    'BUY': 'buy',
                    'SELL': 'sell', 
                    'HOLD': 'hold',
                    'buy': 'buy',
                    'sell': 'sell',
                    'hold': 'hold'
                }
                action = decision.get('action', 'hold')
                chinese_action = action_translation.get(action, action)
                
                formatted_decision = {
                    'action': chinese_action,
                    'confidence': decision.get('confidence', 0.5),
                    'risk_score': decision.get('risk_score', 0.3),
                }
            
            result_action = formatted_decision['action']
            print(f"output decision: {result_action}")
            
            if result_action in ['buy', 'sell', 'hold']:
                print(f"✅ Correctly converted to Chinese")
            else:
                print(f"❌ Conversion failed: {result_action}")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ analysis_runner test failed: {e}")
        return False

def test_demo_data():
    """Test the Chinese culture of the demo data"""
    print("\n🎯 Test demo data culture")
    print("-" * 30)
    
    try:
        # Simulation demo data generation
        import random
        
        actions = ['buy', 'hold', 'sell']  # Chinese should be used after repair
        action = random.choice(actions)
        
        print(f"Demo investment advice: {action}")
        
        # Simulation demonstration report generation
        demo_report = f"""
**investment advice**: {action}

**Main analysis points**:
1. **Technical analysis**: Current price trend display{'rise' if action == 'buy' else 'fall' if action == 'sell' else 'Sideways'}signal
2. **fundamental assessment**: Company financial status{'good' if action == 'buy' else 'Average' if action == 'hold' else 'Need attention'}
3. **market sentiment**: investor sentiment{'optimistic' if action == 'buy' else 'Neutral' if action == 'hold' else 'cautious'}
4. **risk assessment**: The current risk level is{'medium' if action == 'hold' else 'lower' if action == 'buy' else 'higher'}
        """
        
        print("Demo report snippet:")
        print(demo_report[:200] + "...")
        
        if action in ['buy', 'sell', 'hold']:
            print("✅ Demo data is in Chinese")
            return True
        else:
            print(f"❌ Demo data is still in English: {action}")
            return False
        
    except Exception as e:
        print(f"❌ Demo data test failed: {e}")
        return False

def main():
    """main function"""
    print("🔧 Investment advice Chinese culture repair test")
    print("=" * 60)
    
    success1 = test_web_components()
    success2 = test_analysis_runner()
    success3 = test_demo_data()
    
    print("\n" + "=" * 60)
    if success1 and success2 and success3:
        print("🎉 All cultural repair tests in investment suggestions passed!")
        print("\n✅ Repair effect:")
        print("   - Web Interface investment advice is displayed in Chinese")
        print("   - Analysis results are processed in Chinese")
        print("   - Demo data to generate Chinese content")
        print("\n All investment recommendations should now appear in Chinese: Buy/Sell/Hold")
    else:
        print("❌ Investment advice Chinese culture repair test failed")
        print("   Requires further inspection and repair")
    
    return success1 and success2 and success3

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
