#!/usr/bin/env python3
"""
Test backend non-blocking functionality
After the verification analysis task is submitted, the API server can still respond to other requests
"""

import asyncio
import aiohttp
import time
import json

async def test_non_blocking_analysis():
    """Test non-blocking analysis capabilities"""
    
    base_url = "http://localhost:8000"
    
    # First log in to get token
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    
    async with aiohttp.ClientSession() as session:
        print("🔐 logging in...")
        async with session.post(f"{base_url}/api/auth/login", json=login_data) as resp:
            if resp.status != 200:
                print(f"❌ Login failed: {resp.status}")
                return
            
            login_result = await resp.json()
            token = login_result["data"]["access_token"]
            print("✅ Login successful")
        
        # Set authentication header
        headers = {"Authorization": f"Bearer {token}"}
        
        # Submit analysis task
        analysis_data = {
            "stock_code": "000001",
            "parameters": {
                "market_type": "A shares",
                "research_depth": "Standard",
                "selected_analysts": ["market", "fundamentals"],
                "quick_analysis_model": "qwen-turbo",
                "deep_analysis_model": "qwen-plus"
            }
        }
        
        print("📊 Submit analysis task...")
        start_time = time.time()
        
        async with session.post(f"{base_url}/api/analysis/single", 
                               json=analysis_data, 
                               headers=headers) as resp:
            submit_time = time.time() - start_time
            print(f"⏱️ Task submission time: {submit_time:.2f}seconds")
            
            if resp.status != 200:
                print(f"❌ Task submission failed: {resp.status}")
                text = await resp.text()
                print(f"error message: {text}")
                return
            
            result = await resp.json()
            task_id = result["data"]["task_id"]
            print(f"✅ The task submission was successful, the task ID: {task_id}")
        
        # Now test if other APIs are still responsive
        print("\n🔍 Test other API responsiveness...")
        
        # Test health check
        test_start = time.time()
        async with session.get(f"{base_url}/api/health") as resp:
            health_time = time.time() - test_start
            print(f"🏥 Health check response time: {health_time:.2f}seconds - status: {resp.status}")
        
        # Test user information
        test_start = time.time()
        async with session.get(f"{base_url}/api/auth/me", headers=headers) as resp:
            me_time = time.time() - test_start
            print(f"👤 User information response time: {me_time:.2f}seconds - status: {resp.status}")
        
        # Test task status query
        test_start = time.time()
        async with session.get(f"{base_url}/api/analysis/tasks/{task_id}/status", 
                              headers=headers) as resp:
            status_time = time.time() - test_start
            print(f"📋 Task status response time: {status_time:.2f}seconds - status: {resp.status}")
            
            if resp.status == 200:
                status_result = await resp.json()
                print(f"📊 Task status: {status_result['data']['status']}")
        
        # Wait a few seconds and check the task status again
        print("\n⏳ Wait 5 seconds and check the task status again...")
        await asyncio.sleep(5)
        
        async with session.get(f"{base_url}/api/analysis/tasks/{task_id}/status", 
                              headers=headers) as resp:
            if resp.status == 200:
                status_result = await resp.json()
                print(f"📊 5 Task status after seconds: {status_result['data']['status']}")
                print(f"📈 Task progress: {status_result['data'].get('progress', 0)}%")
            else:
                print(f"❌ Status query failed: {resp.status}")

async def test_concurrent_requests():
    """Test concurrent requests"""
    print("\n🔄 Test concurrent requests...")
    
    base_url = "http://localhost:8000"
    
    async def make_health_check():
        async with aiohttp.ClientSession() as session:
            start_time = time.time()
            async with session.get(f"{base_url}/api/health") as resp:
                duration = time.time() - start_time
                return resp.status, duration
    
    # Send 10 health check requests concurrently
    tasks = [make_health_check() for _ in range(10)]
    results = await asyncio.gather(*tasks)
    
    print("🏥 Concurrent health check results:")
    for i, (status, duration) in enumerate(results):
        print(f"  Request {i+1}: Status {status}, Time consuming {duration:.3f}seconds")
    
    avg_time = sum(duration for _, duration in results) / len(results)
    print(f"📊 average response time: {avg_time:.3f}seconds")

if __name__ == "__main__":
    print("🧪 Start testing backend non-blocking functionality")
    print("=" * 50)
    
    asyncio.run(test_non_blocking_analysis())
    asyncio.run(test_concurrent_requests())
    
    print("\n✅ Test completed")
