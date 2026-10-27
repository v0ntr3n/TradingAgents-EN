#!/usr/bin/env python3
"""
Test front-end and back-end integration
Verify the complete process of task submission and status query
"""

import requests
import time
import json

def test_frontend_backend_integration():
    """Test front-end and back-end integration"""
    
    base_url = "http://localhost:8000"
    
    print("🧪 Test front-end and back-end integration")
    print("=" * 40)
    
    # 1. Login
    print("🔐 Logging in...")
    try:
        login_response = requests.post(f"{base_url}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        }, timeout=10)
        
        if login_response.status_code != 200:
            print(f"❌ Login failed: {login_response.status_code}")
            print(f"Response content: {login_response.text}")
            return False
        
        login_data = login_response.json()
        token = login_data["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("✅ Login successful")
        
    except Exception as e:
        print(f"❌ Login exception: {e}")
        return False
    
    # 2. Submit analysis task (simulate front-end request)
    print("\n📊 Submit analysis task...")
    
    # Simulate the request format sent by the front end
    analysis_request = {
        "stock_code": "000001",
        "parameters": {
            "market_type": "A shares",
            "analysis_date": "2024-01-15",
            "research_depth": "fast",
            "selected_analysts": ["market"],
            "include_sentiment": True,
            "include_risk": True,
            "language": "zh",
            "quick_analysis_model": "qwen-turbo",
            "deep_analysis_model": "qwen-plus"
        }
    }
    
    try:
        submit_start = time.time()
        submit_response = requests.post(f"{base_url}/api/analysis/single", 
                                      json=analysis_request, 
                                      headers=headers,
                                      timeout=10)
        
        submit_time = time.time() - submit_start
        print(f"⏱️ Task submission time: {submit_time:.2f}seconds")
        
        if submit_response.status_code != 200:
            print(f"❌ Task submission failed: {submit_response.status_code}")
            print(f"Response content: {submit_response.text}")
            return False
        
        submit_data = submit_response.json()
        print(f"✅ Task submitted successfully")
        print(f"📋 response format: {json.dumps(submit_data, indent=2, ensure_ascii=False)}")
        
        # Check whether the response format meets the front-end expectations
        if not submit_data.get("success"):
            print("❌ Success field is missing from response")
            return False
        
        if not submit_data.get("data"):
            print("❌ Data field is missing from response")
            return False
        
        if not submit_data["data"].get("task_id"):
            print("❌ Task_id field is missing from response")
            return False
        
        task_id = submit_data["data"]["task_id"]
        print(f"📝 Get the task ID: {task_id}")
        
    except Exception as e:
        print(f"❌ Exception when submitting task: {e}")
        return False
    
    # 3. Query task status (simulate front-end polling)
    print(f"\n🔍 Query task status...")
    
    try:
        status_response = requests.get(f"{base_url}/api/analysis/tasks/{task_id}/status", 
                                     headers=headers, 
                                     timeout=10)
        
        if status_response.status_code != 200:
            print(f"❌ Status query failed: {status_response.status_code}")
            print(f"Response content: {status_response.text}")
            return False
        
        status_data = status_response.json()
        print(f"✅ Status query successful")
        print(f"📊 status response: {json.dumps(status_data, indent=2, ensure_ascii=False)}")
        
        # Check status response format
        if not status_data.get("success"):
            print("❌ success field missing from status response")
            return False
        
        if not status_data.get("data"):
            print("❌ data field missing from status response")
            return False
        
        task_status = status_data["data"].get("status")
        progress = status_data["data"].get("progress", 0)
        message = status_data["data"].get("message", "")
        
        print(f"📈 Task status: {task_status}")
        print(f"📊 Progress: {progress}%")
        print(f"💬 news: {message}")
        
    except Exception as e:
        print(f"❌ Status query exception: {e}")
        return False
    
    # 4. Test task list
    print(f"\n📋 Test task list...")
    
    try:
        tasks_response = requests.get(f"{base_url}/api/analysis/tasks", 
                                    headers=headers, 
                                    timeout=10)
        
        if tasks_response.status_code != 200:
            print(f"❌ Task list query failed: {tasks_response.status_code}")
            print(f"Response content: {tasks_response.text}")
        else:
            tasks_data = tasks_response.json()
            print(f"✅ Task list query successful")
            tasks = tasks_data.get("data", {}).get("tasks", [])
            print(f"📝 Number of tasks: {len(tasks)}")
            
            if tasks:
                latest_task = tasks[0]
                print(f"📋 Latest tasks: {latest_task.get('task_id', 'N/A')[:8]}... - {latest_task.get('status', 'N/A')}")
        
    except Exception as e:
        print(f"❌ Task list query exception: {e}")
    
    # 5. Summary
    print(f"\n📈 Integration test summary:")
    print(f"  ✅ Login successful")
    print(f"  ✅ Task submitted successfully (Time consuming: {submit_time:.2f}seconds)")
    print(f"  ✅ Status query successful")
    print(f"  ✅ Response format is correct")
    print(f"  📝 Task ID: {task_id}")
    print(f"  📊 Current status: {task_status} ({progress}%)")
    
    if submit_time < 3.0:
        print("🎉 API The response is fast and the asynchronous implementation is successful!")
    else:
        print("⚠️ API Slow response, may need optimization")
    
    return True

if __name__ == "__main__":
    print(f"🚀 Start integration testing: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    success = test_frontend_backend_integration()
    
    print(f"\n✅ Test completed: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if success:
        print("🎊 Front-end and back-end integration testing successful!")
    else:
        print("🔧 Need further debugging")
