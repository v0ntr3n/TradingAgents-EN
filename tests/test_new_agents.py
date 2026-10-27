"""
Test the newly created Agent
"""

import sys
import os

# Add project root directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_report_generator_v2():
    """Test report generator v2"""
    print("\n" + "="*60)
    print("test ReportGeneratorV2")
    print("="*60)
    
    try:
        from core.agents.post_processors import ReportGeneratorV2
        
        # Create instance
        agent = ReportGeneratorV2()
        
        print(f"✅ Agent ID: {agent.metadata.id}")
        print(f"✅ Agent Name: {agent.metadata.name}")
        print(f"✅ Category: {agent.metadata.category}")
        print(f"✅ Version: {agent.metadata.version}")
        print(f"✅ Icon: {agent.metadata.icon}")
        
        # test execution
        test_state = {
            "ticker": "000001",
            "market_report": "Market analysis report content...",
            "fundamentals_report": "Fundamental analysis report content...",
            "bull_report": "positive evidence view...",
            "bear_report": "cautious evidence view...",
        }
        
        result = agent.execute(test_state)
        
        print(f"\n✅ Executed successfully!")
        print(f"   - Number of extracted reports: {len(result.get('generated_reports', {}))}")
        print(f"   - Number of structured reports: {len(result.get('structured_reports', {}))}")
        print(f"   - summary information: {result.get('report_summary', {})}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_preparer_v2():
    """test data preparer v2"""
    print("\n" + "="*60)
    print("test DataPreparerV2")
    print("="*60)
    
    try:
        from core.agents.post_processors import DataPreparerV2
        
        # Create instance
        agent = DataPreparerV2()
        
        print(f"✅ Agent ID: {agent.metadata.id}")
        print(f"✅ Agent Name: {agent.metadata.name}")
        print(f"✅ Category: {agent.metadata.category}")
        print(f"✅ Version: {agent.metadata.version}")
        print(f"✅ Icon: {agent.metadata.icon}")
        
        # test execution
        test_state = {
            "ticker": "000001",
            "analysis_date": "2026-02-19",
        }
        
        result = agent.execute(test_state)
        
        print(f"\n✅ Executed successfully!")
        print(f"   - Company name: {result.get('company_name', 'N/A')}")
        print(f"   - Industry: {result.get('industry', 'N/A')}")
        print(f"   - current price: {result.get('current_price', 'N/A')}")
        print(f"   - Data preparation status: {result.get('data_prepared', False)}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_agent_registry():
    """Test Agent Registration"""
    print("\n" + "="*60)
    print("Test Agent Registration")
    print("="*60)
    
    try:
        from core.agents.registry import get_registry
        
        registry = get_registry()
        
        # Check if registered
        report_gen = registry.get("report_generator_v2")
        data_prep = registry.get("data_preparer_v2")
        
        if report_gen:
            print(f"✅ ReportGeneratorV2 Registered")
        else:
            print(f"⚠️ ReportGeneratorV2 Not registered")
        
        if data_prep:
            print(f"✅ DataPreparerV2 Registered")
        else:
            print(f"⚠️ DataPreparerV2 Not registered")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n🚀 Start testing the newly created Agent\n")
    
    results = []
    
    # Test report generator
    results.append(("ReportGeneratorV2", test_report_generator_v2()))
    
    # test data preparer
    results.append(("DataPreparerV2", test_data_preparer_v2()))
    
    # Test registration
    results.append(("Agent Registry", test_agent_registry()))
    
    # Summary
    print("\n" + "="*60)
    print("Test summary")
    print("="*60)
    
    for name, success in results:
        status = "✅ Pass" if success else "❌ failed"
        print(f"{status} - {name}")
    
    all_passed = all(success for _, success in results)
    
    if all_passed:
        print("\n🎉 All tests passed!")
    else:
        print("\n⚠️ Some tests failed")
    
    sys.exit(0 if all_passed else 1)

