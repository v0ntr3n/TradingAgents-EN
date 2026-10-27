#!/usr/bin/env python3
"""
Test the command line version
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

def test_cli_imports():
    """Test CLI module import"""
    print("🔬 Test CLI module import")
    print("=" * 60)
    
    try:
        # Test import CLI main module
        from cli.main import app, console
        print("✅ CLI Main module imported successfully")
        
        # Test import analyst type
        from cli.models import AnalystType
        print("✅ Analyst type imported successfully")
        
        # Test import tool function
        from cli.utils import get_user_selections
        print("✅ CLI Tool function imported successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ CLI Module import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cli_config():
    """Test CLI configuration"""
    print("\n🔧 Test CLI configuration")
    print("=" * 60)
    
    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.config.config_manager import config_manager
        
        print("🔧 Test default configuration...")
        print(f"   LLM provider: {DEFAULT_CONFIG.get('llm_provider', 'N/A')}")
        print(f"   deep thinking model: {DEFAULT_CONFIG.get('deep_think_llm', 'N/A')}")
        print(f"   quick thinking model: {DEFAULT_CONFIG.get('quick_think_llm', 'N/A')}")
        
        print("\n🔧 Test Configuration Manager...")
        print(f"   Configuration directory: {config_manager.config_dir}")
        
        # Test pricing configuration
        pricing_configs = config_manager.load_pricing()
        print(f"   Pricing configuration quantity: {len(pricing_configs)}")
        
        # Find DeepSeek configuration
        deepseek_configs = [p for p in pricing_configs if p.provider == "deepseek"]
        print(f"   DeepSeek Configuration quantity: {len(deepseek_configs)}")
        
        if deepseek_configs:
            print("✅ CLI Can access DeepSeek configuration")
            return True
        else:
            print("❌ CLI Unable to access DeepSeek configuration")
            return False
        
    except Exception as e:
        print(f"❌ CLI Configuration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cli_graph_creation():
    """Test CLI diagram creation"""
    print("\n📊 Test CLI diagram creation")
    print("=" * 60)
    
    # Check API key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("⚠️ DEEPSEEK_API_KEY not found, skipping graph creation test")
        return True
    
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        print("🔧 Create test configuration...")
        config = DEFAULT_CONFIG.copy()
        config.update({
            "llm_provider": "deepseek",
            "deep_think_llm": "deepseek-chat",
            "quick_think_llm": "deepseek-chat",
            "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1,
            "online_tools": False,  # Close online tools and reduce complexity
            "memory_enabled": False
        })
        
        print("📊 Create transaction analysis chart...")
        # Create diagrams using the CLI
        graph = TradingAgentsGraph(
            ["market"],  # Only use market analysts
            config=config,
            debug=True
        )
        
        print("✅ CLI Diagram created successfully")
        return True
        
    except Exception as e:
        print(f"❌ CLI Graph creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cli_cost_tracking():
    """Test CLI cost tracking"""
    print("\n💰 Test CLI cost tracking")
    print("=" * 60)
    
    try:
        from tradingagents.config.config_manager import config_manager, token_tracker
        
        print("🔧 Test cost calculation...")
        cost = config_manager.calculate_cost(
            provider="deepseek",
            model_name="deepseek-chat",
            input_tokens=1000,
            output_tokens=500
        )
        print(f"   DeepSeek cost: ¥{cost:.6f}")
        
        if cost > 0:
            print("✅ CLI Cost calculation is normal")
            
            print("\n🔧 Test Token Tracking...")
            usage_record = token_tracker.track_usage(
                provider="deepseek",
                model_name="deepseek-chat",
                input_tokens=100,
                output_tokens=50,
                session_id="cli_test",
                analysis_type="cli_test"
            )
            
            if usage_record and usage_record.cost > 0:
                print(f"   Track costs: ¥{usage_record.cost:.6f}")
                print("✅ CLI Token Tracking OK")
                return True
            else:
                print("❌ CLI Token Tracking failed")
                return False
        else:
            print("❌ CLI The cost is calculated as 0")
            return False
        
    except Exception as e:
        print(f"❌ CLI Cost tracking test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cli_help():
    """Test CLI help functionality"""
    print("\n❓ Test CLI help functionality")
    print("=" * 60)
    
    try:
        from cli.main import app
        
        print("🔧 Test CLI application creation...")
        print(f"   Application name: {app.info.name}")
        print(f"   Application help: {app.info.help[:50]}...")
        
        print("✅ CLI Help function is normal")
        return True
        
    except Exception as e:
        print(f"❌ CLI Help function test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """main function"""
    print("🔬 Command line version test")
    print("=" * 80)
    print("📝 This test will verify that the CLI version is working properly")
    print("📝 Check functionality for module import, configuration access, diagram creation, and more")
    print("=" * 80)
    
    # Run various tests
    tests = [
        ("module import", test_cli_imports),
        ("Configure access", test_cli_config),
        ("Diagram creation", test_cli_graph_creation),
        ("cost tracking", test_cli_cost_tracking),
        ("Help function", test_cli_help),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name}Test exception: {e}")
            results[test_name] = False
    
    # Summary
    print("\n📋 Test summary")
    print("=" * 60)
    
    for test_name, success in results.items():
        status = "✅ success" if success else "❌ failed"
        print(f"{test_name}: {status}")
    
    overall_success = all(results.values())
    
    if overall_success:
        print("\n🎉 CLI All version tests passed!")
        print("   The command line version can be used normally")
        print("   It is recommended to run: python -m cli.main analyze")
    else:
        print("\n❌ CLI Version test has failed items")
        print("   Please check the failed test items")
    
    print("\n🎯 Test completed!")
    return overall_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
