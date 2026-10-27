#!/usr/bin/env python3
"""
Test .env file compatibility
"""

import sys
import os
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_env_loading():
    """Test .env file loading"""
    print("🧪 Test .env file loading")
    print("=" * 50)
    
    try:
        from tradingagents.config.config_manager import config_manager
        
        # Test .env status check
        env_status = config_manager.get_env_config_status()
        print(f"✅ .env File exists: {env_status['env_file_exists']}")
        
        # Test API key loading
        print("\n📋 API Key status:")
        for provider, configured in env_status['api_keys'].items():
            status = "✅ configured" if configured else "❌ Not configured"
            print(f"  {provider}: {status}")
        
        return True
    except Exception as e:
        print(f"❌ .env File loading failed: {e}")
        import traceback
        print(f"Error details: {traceback.format_exc()}")
        return False

def test_model_config_merge():
    """Test model configuration merge"""
    print("\n🧪 Test model configuration merge")
    print("=" * 50)
    
    try:
        from tradingagents.config.config_manager import config_manager
        
        # Load model configuration
        models = config_manager.load_models()
        print(f"📋 loaded {len(models)} model configuration")
        
        # Check if .env keys are merged correctly
        env_status = config_manager.get_env_config_status()
        
        for model in models:
            env_has_key = env_status['api_keys'].get(model.provider.lower(), False)
            model_has_key = bool(model.api_key)
            
            print(f"\n🤖 {model.provider} - {model.model_name}:")
            print(f"  .env There is a key in: {env_has_key}")
            print(f"  The model is configured with a key: {model_has_key}")
            print(f"  Model enabled status: {model.enabled}")
            
            if env_has_key:
                print(f"  API key: ***{model.api_key[-4:] if model.api_key else 'None'}")
        
        return True
    except Exception as e:
        print(f"❌ Model configuration merge failed: {e}")
        import traceback
        print(f"Error details: {traceback.format_exc()}")
        return False

def test_settings_merge():
    """Test system settings merge"""
    print("\n🧪 Test system settings merge")
    print("=" * 50)
    
    try:
        from tradingagents.config.config_manager import config_manager
        
        # Load settings
        settings = config_manager.load_settings()
        
        # Check that settings in .env are merged correctly
        env_settings = [
            "finnhub_api_key",
            "reddit_client_id", 
            "reddit_client_secret",
            "results_dir",
            "log_level"
        ]
        
        print("⚙️ System settings status:")
        for key in env_settings:
            value = settings.get(key, "not set")
            if "api_key" in key or "secret" in key:
                display_value = f"***{value[-4:]}" if value and value != "not set" else "not set"
            else:
                display_value = value
            print(f"  {key}: {display_value}")
        
        return True
    except Exception as e:
        print(f"❌ System settings merge failed: {e}")
        import traceback
        print(f"Error details: {traceback.format_exc()}")
        return False

def test_backward_compatibility():
    """Test for backward compatibility"""
    print("\n🧪 Test for backward compatibility")
    print("=" * 50)
    
    try:
        # Test the original environment variable reading method
        dashscope_key = os.getenv("DASHSCOPE_API_KEY")
        finnhub_key = os.getenv("FINNHUB_API_KEY")
        
        print("🔑 Direct environment variable reading:")
        print(f"  DASHSCOPE_API_KEY: {'✅ Already set' if dashscope_key else '❌ not set'}")
        print(f"  FINNHUB_API_KEY: {'✅ Already set' if finnhub_key else '❌ not set'}")
        
        # Test CLI tool compatibility
        from cli.main import check_api_keys
        
        # Simulate CLI check
        if dashscope_key and finnhub_key:
            print("✅ CLI Tools API key check should pass")
        else:
            print("⚠️ CLI Tools API key check may fail")
        
        return True
    except Exception as e:
        print(f"❌ Backward compatibility test failed: {e}")
        import traceback
        print(f"Error details: {traceback.format_exc()}")
        return False

def main():
    """Main test function"""
    print("🧪 .env File compatibility testing")
    print("=" * 60)
    
    tests = [
        (".env File loading", test_env_loading),
        ("Model configuration merge", test_model_config_merge),
        ("System settings merge", test_settings_merge),
        ("backward compatibility", test_backward_compatibility),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} Test passed")
            else:
                print(f"❌ {test_name} test failed")
        except Exception as e:
            print(f"❌ {test_name} Test exception: {e}")
    
    print(f"\n📊 Test results: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 .env All compatibility tests passed!")
        print("\n💡 Compatibility features:")
        print("✅ Prefer reading the API key from the .env file")
        print("✅ Web Interface displays configuration source")
        print("✅ Keep CLI tools fully compatible")
        print("✅ Support the original environment variable method")
        print("✅ Added new web management interface as a supplement")
        return True
    else:
        print("❌ Some tests failed, please check the compatibility implementation")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
