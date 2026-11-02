#!/usr/bin/env python3
"""
Test model configuration function
Verify saving and reading of model capability fields
"""

import asyncio
import json
import aiohttp
from typing import Dict, Any, Optional

BASE_URL = "http://localhost:8001"

# global access token
access_token: Optional[str] = None

async def login():
    """Log in to get access token"""
    global access_token
    print("🔐 logging in...")
    
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{BASE_URL}/api/auth/login",
                json=login_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("success"):
                        access_token = result["data"]["access_token"]
                        print(f"✅ Log in successfully and obtain access token")
                        return True
                    else:
                        print(f"❌ Login failed: {result.get('message', 'unknown error')}")
                        return False
                else:
                    error_text = await response.text()
                    print(f"❌ Login failed ({response.status}): {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Login request exception: {e}")
            return False

def get_auth_headers():
    """Get authentication header"""
    if access_token:
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    return {"Content-Type": "application/json"}

async def test_add_llm_config():
    """Test adding LLM configuration"""
    print("🧪 Test adding LLM configuration...")
    
    # Test configuration data
    config_data = {
        "provider": "qwen",
        "model_name": "qwen-test-model",
        "model_display_name": "Qwen test model",
        "api_key": "",
        "max_tokens": 4000,
        "temperature": 0.7,
        "enabled": True,
        "description": "Model configuration for testing",
        
        # Model capability fields
        "capability_level": 3,
        "suitable_roles": ["both"],
        "features": ["tool_calling", "reasoning"],
        "recommended_depths": ["Basics", "Standard", "Depth"],
        "performance_metrics": {
            "speed": 4,
            "cost": 3,
            "quality": 4
        }
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            # Add configuration
            async with session.post(
                f"{BASE_URL}/api/config/llm",
                json=config_data,
                headers=get_auth_headers()
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ Added configuration successfully: {result}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Failed to add configuration ({response.status}): {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Request exception: {e}")
            return False

async def test_get_llm_configs():
    """Test to obtain LLM configuration"""
    print("🧪 Test to obtain LLM configuration...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                f"{BASE_URL}/api/config/llm",
                headers=get_auth_headers()
            ) as response:
                if response.status == 200:
                    configs = await response.json()
                    print(f"✅ Obtained configuration successfully, total {len(configs)} configuration")
                    
                    # Find a test model
                    test_model = None
                    for config in configs:
                        if config.get("model_name") == "qwen-test-model":
                            test_model = config
                            break
                    
                    if test_model:
                        print("✅ Find the test model configuration:")
                        print(f"   - Model name: {test_model.get('model_name')}")
                        print(f"   - display name: {test_model.get('model_display_name')}")
                        print(f"   - Ability level: {test_model.get('capability_level')}")
                        print(f"   - Applicable roles: {test_model.get('suitable_roles')}")
                        print(f"   - Features: {test_model.get('features')}")
                        print(f"   - Recommended depth: {test_model.get('recommended_depths')}")
                        print(f"   - Performance indicators: {test_model.get('performance_metrics')}")
                        return True
                    else:
                        print("❌ Test model configuration not found")
                        return False
                else:
                    error_text = await response.text()
                    print(f"❌ Failed to get configuration ({response.status}): {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Request exception: {e}")
            return False

async def test_model_capability_service():
    """Test model capability service"""
    print("🧪 Test model capability service...")
    
    async with aiohttp.ClientSession() as session:
        try:
            # Test recommendation model
            async with session.post(
                f"{BASE_URL}/api/model-capabilities/recommend",
                json={"research_depth": "Standard"},
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ Model recommendation successful:")
                    print(f"   - quick model: {result.get('data', {}).get('quick_model')}")
                    print(f"   - deep model: {result.get('data', {}).get('deep_model')}")
                    print(f"   - Reasons for recommendation: {result.get('data', {}).get('reason')}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Model recommendation failed ({response.status}): {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Request exception: {e}")
            return False

async def test_delete_test_config():
    """Delete test configuration"""
    print("🧪 Clean test configuration...")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.delete(
                f"{BASE_URL}/api/config/llm/qwen/qwen-test-model",
                headers=get_auth_headers()
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ Deletion of test configuration successful: {result}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"⚠️ Deletion of test configuration failed ({response.status}): {error_text}")
                    return False
        except Exception as e:
            print(f"⚠️ Delete request exception: {e}")
            return False

async def main():
    """Main test function"""
    print("🚀 Start testing the model configuration function...")
    print("=" * 50)
    
    # Log in first
    if not await login():
        print("❌ Login failed and cannot continue testing")
        return
    
    # Test steps
    tests = [
        ("Add LLM configuration", test_add_llm_config),
        ("Get LLM configuration", test_get_llm_configs),
        ("Model capability service", test_model_capability_service),
        ("Clean test configuration", test_delete_test_config),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        print("-" * 30)
        success = await test_func()
        results.append((test_name, success))
        print()
    
    # Summary
    print("=" * 50)
    print("📊 Summary of test results:")
    passed = 0
    for test_name, success in results:
        status = "✅ Pass" if success else "❌ failed"
        print(f"   {test_name}: {status}")
        if success:
            passed += 1
    
    print(f"\n🎯 total: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! The configuration function works fine.")
    else:
        print("⚠️ Some tests failed, please check the configuration.")

if __name__ == "__main__":
    asyncio.run(main())