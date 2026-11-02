#!/usr/bin/env python3
"""
Unified test configuration
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

def test_config_unification():
    """Test whether the unified configuration is working properly"""
    print("🔬 Unified test configuration")
    print("=" * 60)
    
    try:
        from tradingagents.config.config_manager import config_manager
        
        print("🔧 Test the global configuration manager...")
        
        # Check configuration directory
        print(f"📁 Configuration directory: {config_manager.config_dir}")
        print(f"📁 Configuration directory absolute path: {config_manager.config_dir.absolute()}")
        print(f"📄 pricing document: {config_manager.pricing_file}")
        print(f"📄 Pricing file exists: {config_manager.pricing_file.exists()}")
        
        # Load pricing configuration
        pricing_configs = config_manager.load_pricing()
        print(f"📊 Number of pricing configurations loaded: {len(pricing_configs)}")
        
        # Find DeepSeek configuration
        deepseek_configs = [p for p in pricing_configs if p.provider == "deepseek"]
        print(f"📊 DeepSeek Configuration quantity: {len(deepseek_configs)}")
        
        if deepseek_configs:
            print("✅ Find DeepSeek configuration:")
            for config in deepseek_configs:
                print(f"   - {config.model_name}: input¥{config.input_price_per_1k}/1K, output¥{config.output_price_per_1k}/1K")
        else:
            print("❌ DeepSeek configuration not found")
        
        # Test cost calculation
        print(f"\n💰 Test cost calculation:")
        deepseek_cost = config_manager.calculate_cost(
            provider="deepseek",
            model_name="deepseek-chat",
            input_tokens=1000,
            output_tokens=500
        )
        print(f"   DeepSeek cost: ¥{deepseek_cost:.6f}")
        
        if deepseek_cost > 0:
            print("✅ DeepSeek Cost calculation is normal")
            return True
        else:
            print("❌ DeepSeek The cost calculation is still 0")
            return False
        
    except Exception as e:
        print(f"❌ Configuration unified test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_web_config_access():
    """Test web interface configuration access"""
    print("\n🌐 Test web interface configuration access")
    print("=" * 60)
    
    try:
        # Simulate the import method of the web interface
        sys.path.insert(0, str(project_root / "web"))
        
        # Import the web configuration management page
        from pages.config_management import config_manager as web_config_manager
        
        print("🔧 Testing the Web Configuration Manager...")
        
        # Check configuration directory
        print(f"📁 Web Configuration directory: {web_config_manager.config_dir}")
        print(f"📁 Web Configuration directory absolute path: {web_config_manager.config_dir.absolute()}")
        
        # Load pricing configuration
        web_pricing_configs = web_config_manager.load_pricing()
        print(f"📊 Web Number of pricing configurations loaded: {len(web_pricing_configs)}")
        
        # Find DeepSeek configuration
        web_deepseek_configs = [p for p in web_pricing_configs if p.provider == "deepseek"]
        print(f"📊 Web DeepSeek Configuration quantity: {len(web_deepseek_configs)}")
        
        if web_deepseek_configs:
            print("✅ Web Find the DeepSeek configuration on the interface")
            return True
        else:
            print("❌ Web DeepSeek configuration not found in the interface")
            return False
        
    except Exception as e:
        print(f"❌ Web Configuration access test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config_consistency():
    """Test configuration consistency"""
    print("\n🔄 Test configuration consistency")
    print("=" * 60)
    
    try:
        from tradingagents.config.config_manager import config_manager
        
        # Importing from different paths should use the same configuration
        sys.path.insert(0, str(project_root / "web"))
        from pages.config_management import config_manager as web_config_manager
        
        # Compare configuration directories
        main_config_dir = config_manager.config_dir.absolute()
        web_config_dir = web_config_manager.config_dir.absolute()
        
        print(f"📁 Main configuration directory: {main_config_dir}")
        print(f"📁 Web Configuration directory: {web_config_dir}")
        
        if main_config_dir == web_config_dir:
            print("✅ The configuration directory is consistent")
            
            # Compare configuration quantities
            main_configs = config_manager.load_pricing()
            web_configs = web_config_manager.load_pricing()
            
            print(f"📊 Number of main configurations: {len(main_configs)}")
            print(f"📊 Web Configuration quantity: {len(web_configs)}")
            
            if len(main_configs) == len(web_configs):
                print("✅ The configuration quantity is the same")
                return True
            else:
                print("❌ The number of configurations is inconsistent")
                return False
        else:
            print("❌ Configuration directory is inconsistent")
            return False
        
    except Exception as e:
        print(f"❌ Configuration consistency test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """main function"""
    print("🔬 Configure unified testing")
    print("=" * 80)
    print("📝 This test will verify whether the configuration unification is successful")
    print("📝 Check that all components use the same configuration file")
    print("=" * 80)
    
    # Unified test configuration
    unification_success = test_config_unification()
    
    # Test web configuration access
    web_access_success = test_web_config_access()
    
    # Test configuration consistency
    consistency_success = test_config_consistency()
    
    # Summary
    print("\n📋 Test summary")
    print("=" * 60)
    
    print(f"Unified configuration: {'✅ success' if unification_success else '❌ failed'}")
    print(f"Web Configure access: {'✅ success' if web_access_success else '❌ failed'}")
    print(f"Configuration consistency: {'✅ success' if consistency_success else '❌ failed'}")
    
    overall_success = unification_success and web_access_success and consistency_success
    
    if overall_success:
        print("\n🎉 Configuration unified successfully!")
        print("   All components now use the unified configuration of the project root directory")
        print("   No more need to maintain multiple sets of configuration files")
    else:
        print("\n❌ Configuration unification failed")
        print("   Need further debugging")
    
    print("\n🎯 Test completed!")
    return overall_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
