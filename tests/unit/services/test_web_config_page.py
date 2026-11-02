#!/usr/bin/env python3
"""
Test the Web configuration management page
"""

import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_config_page_import():
    """Test configuration page import"""
    print("🧪 Test configuration management page import")
    print("=" * 50)
    
    try:
        from web.pages.config_management import render_config_management
        print("✅ Configuration management page imported successfully")
        return True
    except Exception as e:
        print(f"❌ Configuration management page import failed: {e}")
        import traceback
        print(f"Error details: {traceback.format_exc()}")
        return False

def test_config_manager_import():
    """Test Configuration Manager Import"""
    print("\n🧪 Test Configuration Manager Import")
    print("=" * 50)
    
    try:
        from tradingagents.config.config_manager import config_manager, token_tracker
        print("✅ Configuration manager imported successfully")
        
        # Test basic functionality
        models = config_manager.load_models()
        print(f"📋 loaded {len(models)} model configuration")
        
        pricing = config_manager.load_pricing()
        print(f"💰 loaded {len(pricing)} pricing configuration")
        
        settings = config_manager.load_settings()
        print(f"⚙️ loaded {len(settings)} system settings")
        
        return True
    except Exception as e:
        print(f"❌ Configuration manager import failed: {e}")
        import traceback
        print(f"Error details: {traceback.format_exc()}")
        return False

def test_streamlit_components():
    """Test the Streamlit component"""
    print("\n🧪 Test the Streamlit component")
    print("=" * 50)
    
    try:
        import streamlit as st
        import pandas as pd
        import plotly.express as px
        import plotly.graph_objects as go
        
        print("✅ Streamlit Import successful")
        print("✅ Pandas Import successful")
        print("✅ Plotly Import successful")
        
        return True
    except Exception as e:
        print(f"❌ Streamlit Component import failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Web Configuration management page test")
    print("=" * 60)
    
    tests = [
        ("Streamlit components", test_streamlit_components),
        ("configuration manager", test_config_manager_import),
        ("Configuration page", test_config_page_import),
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
        print("🎉 All tests passed! The configuration management page can be used normally")
        print("\n💡 How to use:")
        print("1. Start web application: python -m streamlit run web/app.py")
        print("2. Select in the sidebar '⚙️ Configuration management'")
        print("3. Configure API keys, model parameters and rate settings")
        print("4. View usage statistics and cost analysis")
        return True
    else:
        print("❌ Some tests failed, please check the configuration")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
