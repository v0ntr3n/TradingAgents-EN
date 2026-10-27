#!/usr/bin/env python3
"""
Quickly test the repair effect
"""

import requests
import time
import json

def quick_test():
    """Quickly test the repair effect"""
    print("🔍 Quickly test the repair effect")
    print("=" * 60)
    
    # API Basics URL
    base_url = "http://localhost:8000"
    
    try:
        # 1. Log in to get token
        print("1. Log in to get token...")
        login_data = {
            "username": "admin",
            "password": "admin123"
        }
        
        login_response = requests.post(
            f"{base_url}/api/auth/login",
            json=login_data
        )
        
        if login_response.status_code == 200:
            login_result = login_response.json()
            access_token = login_result["data"]["access_token"]
            print("✅ Log in successfully and get token")
        else:
            print(f"❌ Login failed: {login_response.status_code}")
            return False
        
        # 2. Submit an analysis request
        print("\n2. Submit an analysis request...")
        analysis_request = {
            "stock_code": "000007",  # Use new ticker
            "parameters": {
                "market_type": "A shares",
                "analysis_date": "2025-08-20",
                "research_depth": "fast",
                "selected_analysts": ["market"],  # Select just one analyst for a quick test
                "include_sentiment": False,
                "include_risk": False,
                "language": "zh-CN",
                "quick_analysis_model": "qwen-turbo",
                "deep_analysis_model": "qwen-max"
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        
        response = requests.post(
            f"{base_url}/api/analysis/single",
            json=analysis_request,
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            task_id = result["data"]["task_id"]
            print(f"✅ Analysis task has been submitted: {task_id}")
        else:
            print(f"❌ Failed to submit analysis request: {response.status_code}")
            print(f"   response: {response.text}")
            return False
        
        # 3. Wait for task to complete
        print(f"\n3. Wait for task to complete...")
        for i in range(60):  # Wait up to 5 minutes
            status_response = requests.get(
                f"{base_url}/api/analysis/tasks/{task_id}/status",
                headers=headers
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                status = status_data["data"]["status"]
                progress = status_data["data"].get("progress", 0)
                message = status_data["data"].get("message", "")
                
                print(f"   Status: {status}, Progress: {progress}%, news: {message}")
                
                if status == "completed":
                    print("✅ Analysis task completed!")
                    return True
                elif status == "failed":
                    print(f"❌ Analysis task failed: {message}")
                    return False
            
            time.sleep(5)
        
        print(f"⏰ Task execution timeout")
        return False
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

if __name__ == "__main__":
    success = quick_test()
    if success:
        print("\n🎉 Quick test successful!")
    else:
        print("\n💥 Quick test failed!")
