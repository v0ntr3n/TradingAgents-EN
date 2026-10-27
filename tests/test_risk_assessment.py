#!/usr/bin/env python3
"""
Test risk assessment functionality
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv(project_root / ".env", override=True)

def test_risk_assessment_extraction():
    """Test risk assessment data extraction functionality"""
    print("🧪 Test risk assessment data extraction")
    print("=" * 50)
    
    try:
        from web.utils.analysis_runner import extract_risk_assessment
        
        # Simulate and analyze status data
        mock_state = {
            'risk_debate_state': {
                'risky_history': """
As an activist risk analyst, I believe AAPL currently has the following risk characteristics:

1. **market opportunity**: The current market sentiment is positive and technological innovation continues to advance
2. **growth potential**: Strong growth in new product lines and services
3. **Risk controllable**: Despite market volatility, the company s fundamentals are solid

Suggestions: Increase positions appropriately and seize growth opportunities
                """.strip(),
                
                'safe_history': """
As a conservative risk analyst, I am cautious about AAPL:

1. **market risk**: The current valuation is on the high side and there is a risk of a correction
2. **Industry competition**: Smartphone market is highly competitive and growth is slowing
3. **macro environment**: Rising interest rates and economic uncertainty increase risks

Suggestions: Stay cautious and control position size
                """.strip(),
                
                'neutral_history': """
As a neutral risk analyst, my overall assessment is as follows:

1. **balanced perspective**: AAPL There are both growth opportunities and challenges
2. **risk return**: The current risk-benefit ratio is within a reasonable range
3. **Timing**: It is recommended to open positions in batches to reduce timing risks

Suggestions: Adopt a balanced strategy and moderate allocation
                """.strip(),
                
                'judge_decision': """
After full discussion by the Risk Committee, the conclusion of AAPL s risk assessment is as follows:

**Comprehensive risk level**: medium risk
**Main risk factors**: 
- Valuation risk: The current P/E ratio is on the high side
- market risk: Technology stocks are more volatile
- Competing risks: Industry competition intensifies

**Risk control suggestions**:
1. It is recommended that the position be controlled at 5-10%
2. Set stop loss at current price-15%
3. Open positions in batches to reduce timing risks
4. Keep an eye on quarterly earnings and product releases

**Final recommendations**: Cautiously optimistic, moderate allocation
                """.strip()
            }
        }
        
        # Test the extraction function
        risk_assessment = extract_risk_assessment(mock_state)
        
        if risk_assessment:
            print("✅ Risk assessment data extraction successful")
            print("\n📋 Extracted risk assessment report:")
            print("-" * 50)
            print(risk_assessment[:500] + "..." if len(risk_assessment) > 500 else risk_assessment)
            print("-" * 50)
            
            # Verify report content
            required_sections = [
                "Radical Risk Analyst Perspective",
                "Neutral risk analyst view", 
                "Conservative risk analyst view",
                "Final decision of the Risk Management Committee"
            ]
            
            missing_sections = []
            for section in required_sections:
                if section not in risk_assessment:
                    missing_sections.append(section)
            
            if missing_sections:
                print(f"⚠️ The following parts are missing: {', '.join(missing_sections)}")
                return False
            else:
                print("✅ The risk assessment report contains all required sections")
                return True
        else:
            print("❌ Risk assessment data extraction failed")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_web_interface_risk_display():
    """Test web interface risk assessment display"""
    print("\n🧪 Test web interface risk assessment display")
    print("=" * 50)
    
    try:
        from web.utils.analysis_runner import run_stock_analysis
        
        print("📋 Check the web interface analysis runner...")
        
        # Checks whether the function contains risk assessment extraction logic
        import inspect
        source = inspect.getsource(run_stock_analysis)
        
        if 'extract_risk_assessment' in source:
            print("✅ Web The interface has integrated risk assessment extraction function")
        else:
            print("❌ Web Interface lacks risk assessment extraction functionality")
            return False
        
        if 'risk_assessment' in source:
            print("✅ Web Interface supports risk assessment data transfer")
        else:
            print("❌ Web Interface lacks risk assessment data transfer")
            return False
        
        print("✅ Web Interface risk assessment function check passed")
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

def test_risk_assessment_integration():
    """Test risk assessment fully integrated"""
    print("\n🧪 Test risk assessment fully integrated")
    print("=" * 50)
    
    try:
        # Check API key
        dashscope_key = os.getenv('DASHSCOPE_API_KEY')
        google_key = os.getenv('GOOGLE_API_KEY')
        
        if not dashscope_key and not google_key:
            print("⚠️ API key not configured, skipping actual analysis test")
            return True
        
        print("🚀 Perform actual risk assessment testing...")
        
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        if dashscope_key:
            config["llm_provider"] = "dashscope"
            config["deep_think_llm"] = "qwen-plus"
            config["quick_think_llm"] = "qwen-turbo"
        elif google_key:
            config["llm_provider"] = "google"
            config["deep_think_llm"] = "gemini-2.5-flash-lite-preview-06-17"
            config["quick_think_llm"] = "gemini-2.5-flash-lite-preview-06-17"
        
        config["online_tools"] = False  # Avoid API restrictions
        config["memory_enabled"] = True
        config["max_risk_discuss_rounds"] = 1  # Reduce testing time
        
        # repair path
        config["data_dir"] = str(project_root / "data")
        config["results_dir"] = str(project_root / "results")
        config["data_cache_dir"] = str(project_root / "tradingagents" / "dataflows" / "data_cache")
        
        # Create directory
        os.makedirs(config["data_dir"], exist_ok=True)
        os.makedirs(config["results_dir"], exist_ok=True)
        os.makedirs(config["data_cache_dir"], exist_ok=True)
        
        print("✅ Configuration created successfully")
        
        # Create TradingAgentsGraph instance
        print("🚀 Initialize TradingAgents graph...")
        graph = TradingAgentsGraph(["market", "fundamentals"], config=config, debug=False)
        
        print("✅ TradingAgents Graph initialization successful")
        
        # Perform analysis
        print("📊 Start risk assessment testing...")
        state, decision = graph.propagate("AAPL", "2025-06-27")
        
        # Check risk assessment data
        if 'risk_debate_state' in state:
            print("✅ Discover risk assessment data")
            
            risk_debate = state['risk_debate_state']
            components = ['risky_history', 'safe_history', 'neutral_history', 'judge_decision']
            
            for component in components:
                if component in risk_debate and risk_debate[component]:
                    print(f"   ✅ {component}: There is data")
                else:
                    print(f"   ❌ {component}: No data")
            
            # Test the extraction function
            from web.utils.analysis_runner import extract_risk_assessment
            risk_assessment = extract_risk_assessment(state)
            
            if risk_assessment:
                print("✅ Risk assessment report generated successfully")
                print(f"   Report length: {len(risk_assessment)} character")
                return True
            else:
                print("❌ Risk assessment report generation failed")
                return False
        else:
            print("❌ No risk assessment data found")
            return False
            
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def main():
    """Main test function"""
    print("🧪 Risk assessment functional testing")
    print("=" * 70)
    
    # Run tests
    results = {}
    
    results['Data extraction'] = test_risk_assessment_extraction()
    results['Web Interface integration'] = test_web_interface_risk_display()
    results['Full integration'] = test_risk_assessment_integration()
    
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
        print("🎉 The risk assessment function is completely normal!")
        print("\n💡 The web interface should now display risk assessment data correctly")
    else:
        print("⚠️ Some functions require further inspection")

if __name__ == "__main__":
    main()
