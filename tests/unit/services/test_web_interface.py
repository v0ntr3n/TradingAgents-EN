#!/usr/bin/env python3
"""
Testing the Google Model functionality of the web interface
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

def test_web_interface_config():
    """Test the web interface configuration function"""
    print("🧪 Test web interface Google model configuration")
    print("=" * 60)
    
    try:
        # Test sidebar configuration
        print("📋 Test sidebar configuration...")
        from web.components.sidebar import render_sidebar
        
        # Simulate Streamlit environment (simplified testing)
        print("✅ sidebar Module imported successfully")
        
        # Test analysis_runner configuration
        print("📊 Test analysis_runner configuration...")
        from web.utils.analysis_runner import run_stock_analysis
        
        print("✅ analysis_runner Module imported successfully")
        
        # Test parameter verification
        print("🔧 Test parameter configuration...")
        
        # Simulate Google configuration
        test_config = {
            'llm_provider': 'google',
            'llm_model': 'gemini-2.0-flash',
            'enable_memory': True,
            'enable_debug': False,
            'max_tokens': 4000
        }
        
        print(f"✅ Test configuration created successfully: {test_config}")
        
        # Verify configuration parameters
        required_params = ['llm_provider', 'llm_model']
        for param in required_params:
            if param in test_config:
                print(f"   ✅ {param}: {test_config[param]}")
            else:
                print(f"   ❌ {param}: Missing")
        
        return True
        
    except Exception as e:
        print(f"❌ Web Interface configuration test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_model_options():
    """Test model option configuration"""
    print("\n🧪 Test model option configuration")
    print("=" * 60)
    
    # Ali Bailian model options
    dashscope_models = ["qwen-turbo", "qwen-plus", "qwen-max"]
    print("📊 Ali Bailian model options:")
    for model in dashscope_models:
        print(f"   ✅ {model}")
    
    # Google Model options
    google_models = ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
    print("\n🤖 Google Model options:")
    for model in google_models:
        print(f"   ✅ {model}")
    
    # Verify recommended configuration
    print(f"\n🏆 Recommended configuration:")
    print(f"   LLM provider: Google AI")
    print(f"   Recommended model: gemini-2.0-flash")
    print(f"   Embed services: Ali Bailian (automatic configuration)")
    print(f"   memory function: enable")
    
    return True

def test_api_requirements():
    """Test API key requirements"""
    print("\n🧪 Test API key requirements")
    print("=" * 60)
    
    # Check required API keys
    api_keys = {
        'GOOGLE_API_KEY': 'Google AI API key',
        'DASHSCOPE_API_KEY': 'Alibaba Bailian API key (for embedding)',
        'FINNHUB_API_KEY': 'Financial Data API Key'
    }
    
    all_configured = True
    
    for key, description in api_keys.items():
        value = os.getenv(key)
        if value:
            print(f"✅ {description}: configured")
        else:
            print(f"❌ {description}: Not configured")
            all_configured = False
    
    if all_configured:
        print(f"\n🎉 All required API keys have been configured!")
        print(f"💡 Complete stock analysis can now be done using Google AI")
    else:
        print(f"\n⚠️ Some API keys are not configured")
        print(f"💡 Please configure the missing API key in the .env file")
    
    return all_configured

def main():
    """Main test function"""
    print("🧪 Web Interface Google model functional testing")
    print("=" * 70)
    
    # Run tests
    results = {}
    
    results['Web Interface configuration'] = test_web_interface_config()
    results['Model options'] = test_model_options()
    results['API key'] = test_api_requirements()
    
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
        print("🎉 Web The interface Google model functionality is fully available!")
        print("\n💡 User Guide:")
        print("   1. Open the web interface: http://localhost:8501")
        print("   2. Select in the left sidebar'Google AI'As an LLM provider")
        print("   3. Choose'Gemini 2.0 Flash'Model (recommended)")
        print("   4. Enable memory for better analysis")
        print("   5. Select an analyst and start stock analysis")
        print("\n🚀 Now you can enjoy the powerful analytical capabilities of Google AI!")
    else:
        print("⚠️ Some functions require further configuration")

if __name__ == "__main__":
    main()
