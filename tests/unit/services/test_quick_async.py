#!/usr/bin/env python3
"""
Quickly test asynchronous analysis implementation
Verify that the API is no longer blocking
"""

import requests
import time
import json

def test_api_non_blocking():
    """Test API non-blocking functionality"""
    
    base_url = "http://localhost:8000"
    
    print("🧪 Quickly test API non-blocking functionality")
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
            return False
        
        token = login_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("✅ Login successful")
        
    except Exception as e:
        print(f"❌ Login exception: {e}")
        return False
    
    # 2. Submit analysis task (critical test: should return immediately)
    print("\n📊 Submit analysis task...")
    start_time = time.time()
    
    try:
        analysis_response = requests.post(f"{base_url}/api/analysis/single", 
                                        json={
                                            "stock_code": "000001",
                                            "parameters": {
                                                "research_depth": 1,  # Quick analysis
                                                "selected_analysts": ["market"]
                                            }
                                        }, 
                                        headers=headers,
                                        timeout=10)  # 10 seconds timeout
        
        submit_time = time.time() - start_time
        print(f"⏱️ Task submission time: {submit_time:.2f}seconds")
        
        if analysis_response.status_code == 200:
            task_data = analysis_response.json()
            task_id = task_data["data"]["task_id"]
            print(f"✅ Task submitted successfully: {task_id}")
            
            # Key judgment: If the submission time is very short, it means that the API is not blocked
            if submit_time < 3.0:
                print("🎉 API The response is fast and the non-blocking implementation is successful!")
                success = True
            else:
                print("⚠️ API Slow response, may still have blocking issues")
                success = False
                
        else:
            print(f"❌ Task submission failed: {analysis_response.status_code}")
            print(f"error message: {analysis_response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out! API may still block")
        return False
    except Exception as e:
        print(f"❌ Exception when submitting task: {e}")
        return False
    
    # 3. Test other APIs now (verify the server is not blocked)
    print("\n🔍 Test other API responsiveness...")
    
    # health check
    try:
        health_start = time.time()
        health_response = requests.get(f"{base_url}/api/health", timeout=5)
        health_time = time.time() - health_start
        print(f"🏥 health check: {health_response.status_code} - {health_time:.2f}seconds")
        
        if health_time > 2.0:
            print("⚠️ Health check response is slow and the server may be blocked")
            success = False
            
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        success = False
    
    # Task status query
    try:
        status_start = time.time()
        status_response = requests.get(f"{base_url}/api/analysis/task/{task_id}", 
                                     headers=headers, timeout=5)
        status_time = time.time() - status_start
        print(f"📋 Task status query: {status_response.status_code} - {status_time:.2f}seconds")
        
        if status_response.status_code == 200:
            status_data = status_response.json()
            task_status = status_data['data']['status']
            progress = status_data['data']['progress']
            print(f"📊 Current status: {task_status} ({progress}%)")
            
        if status_time > 2.0:
            print("⚠️ Status query response is slow")
            success = False
            
    except Exception as e:
        print(f"❌ Status query failed: {e}")
        success = False
    
    # 4. Summary
    print(f"\n📈 Test summary:")
    print(f"  - Task submission time: {submit_time:.2f}seconds")
    print(f"  - Health check time: {health_time:.2f}seconds")
    print(f"  - Status query time: {status_time:.2f}seconds")
    
    if success:
        print("🎉 Asynchronous implementation successful! API no longer blocks")
    else:
        print("❌ There are still blocking problems and need further optimization")
    
    return success

def test_multiple_concurrent_requests():
    """Test multiple concurrent requests"""
    print("\n🔄 Test concurrent requests...")
    
    base_url = "http://localhost:8000"
    
    import threading
    import queue
    
    results = queue.Queue()
    
    def make_health_request():
        try:
            start = time.time()
            response = requests.get(f"{base_url}/api/health", timeout=5)
            duration = time.time() - start
            results.put((response.status_code, duration))
        except Exception as e:
            results.put((0, 999))
    
    # Start 5 concurrent requests
    threads = []
    for i in range(5):
        thread = threading.Thread(target=make_health_request)
        threads.append(thread)
        thread.start()
    
    # Wait for all requests to complete
    for thread in threads:
        thread.join()
    
    # Collect results
    response_times = []
    while not results.empty():
        status, duration = results.get()
        response_times.append(duration)
        print(f"  Concurrent requests: Status {status}, Time consuming {duration:.3f}seconds")
    
    if response_times:
        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)
        print(f"📊 Concurrency performance: average {avg_time:.3f}seconds, maximum {max_time:.3f}seconds")
        
        if max_time < 1.0:
            print("🎉 Good concurrency performance")
        else:
            print("⚠️ Concurrency performance needs to be optimized")

if __name__ == "__main__":
    print(f"🚀 Start testing: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    success = test_api_non_blocking()
    test_multiple_concurrent_requests()
    
    print(f"\n✅ Test completed: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if success:
        print("🎊 Congratulations! Asynchronous analysis was implemented successfully")
    else:
        print("🔧 Needs further debugging and optimization")
