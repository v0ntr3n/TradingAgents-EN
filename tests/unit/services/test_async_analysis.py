#!/usr/bin/env python3
"""
Test new asynchronous analysis implementation
Verify BackgroundTasks + Memory state management + WebSocket The complete process
"""

import asyncio
import aiohttp
import websockets
import json
import time
from datetime import datetime

async def test_async_analysis():
    """Testing asynchronous analysis capabilities"""
    
    base_url = "http://localhost:8000"
    ws_url = "ws://localhost:8000"
    
    print("🧪 Start testing the new asynchronous analysis implementation")
    print("=" * 50)
    
    # 1. Log in to get token
    print("🔐 logging in...")
    async with aiohttp.ClientSession() as session:
        login_response = await session.post(f"{base_url}/api/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        
        if login_response.status != 200:
            print(f"❌ Login failed: {login_response.status}")
            return
        
        login_data = await login_response.json()
        token = login_data["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("✅ Login successful")
        
        # 2. Submit analysis task (should return immediately)
        print("\n📊 Submit analysis task...")
        submit_start = time.time()
        
        analysis_response = await session.post(f"{base_url}/api/analysis/single", 
                                             json={
                                                 "stock_code": "000001",
                                                 "parameters": {
                                                     "research_depth": 1,  # Quick analysis
                                                     "selected_analysts": ["market"]
                                                 }
                                             }, 
                                             headers=headers)
        
        submit_time = time.time() - submit_start
        print(f"⏱️ Task submission time: {submit_time:.2f}seconds")
        
        if analysis_response.status != 200:
            print(f"❌ Task submission failed: {analysis_response.status}")
            response_text = await analysis_response.text()
            print(f"error message: {response_text}")
            return
        
        analysis_data = await analysis_response.json()
        task_id = analysis_data["data"]["task_id"]
        print(f"✅ Task submitted successfully: {task_id}")
        
        # Verify API response speed
        if submit_time < 2.0:
            print("🎉 API The response is fast and the non-blocking implementation is successful!")
        else:
            print("⚠️ API Slow response, may still have blocking issues")
        
        # 3. Test other APIs now (verify non-blocking)
        print("\n🔍 Test other API responsiveness...")
        
        # health check
        health_start = time.time()
        health_response = await session.get(f"{base_url}/api/health")
        health_time = time.time() - health_start
        print(f"🏥 health check: {health_response.status} - {health_time:.2f}seconds")
        
        # Task status query
        status_start = time.time()
        status_response = await session.get(f"{base_url}/api/analysis/task/{task_id}", 
                                          headers=headers)
        status_time = time.time() - status_start
        print(f"📋 Task status query: {status_response.status} - {status_time:.2f}seconds")
        
        if status_response.status == 200:
            status_data = await status_response.json()
            print(f"📊 Current status: {status_data['data']['status']} ({status_data['data']['progress']}%)")
        
        # 4. Test WebSocket real-time progress
        print(f"\n🔌 Test WebSocket real-time progress...")
        try:
            await test_websocket_progress(task_id, ws_url)
        except Exception as e:
            print(f"⚠️ WebSocket test failed: {e}")
        
        # 5. Poll task status until completion
        print(f"\n⏳ Wait for task to complete...")
        max_wait_time = 300  # Wait up to 5 minutes
        start_wait = time.time()
        
        while time.time() - start_wait < max_wait_time:
            status_response = await session.get(f"{base_url}/api/analysis/task/{task_id}", 
                                              headers=headers)
            
            if status_response.status == 200:
                status_data = await status_response.json()
                task_status = status_data['data']['status']
                progress = status_data['data']['progress']
                message = status_data['data'].get('message', '')
                
                print(f"📊 Status: {task_status} ({progress}%) - {message}")
                
                if task_status in ['completed', 'failed', 'cancelled']:
                    break
            
            await asyncio.sleep(5)  # Query every 5 seconds
        
        # 6. Get final result
        final_response = await session.get(f"{base_url}/api/analysis/task/{task_id}", 
                                         headers=headers)
        
        if final_response.status == 200:
            final_data = await final_response.json()
            task_data = final_data['data']
            
            print(f"\n📈 final result:")
            print(f"  Status: {task_data['status']}")
            print(f"  Progress: {task_data['progress']}%")
            print(f"  Execution time: {task_data.get('execution_time', 'N/A')}seconds")
            
            if task_data['status'] == 'completed' and task_data.get('result_data'):
                result = task_data['result_data']
                print(f"  Stock code: {result.get('stock_code', 'N/A')}")
                print(f"  Recommended: {result.get('recommendation', 'N/A')}")
                print(f"  Confidence: {result.get('confidence_score', 'N/A')}")
        
        # 7. Test task list
        print(f"\n📋 Test task list...")
        tasks_response = await session.get(f"{base_url}/api/analysis/tasks", 
                                         headers=headers)
        
        if tasks_response.status == 200:
            tasks_data = await tasks_response.json()
            tasks = tasks_data['data']['tasks']
            print(f"✅ Get {len(tasks)} tasks")
            for task in tasks[:3]:  # Show first 3 tasks
                print(f"  - {task['task_id'][:8]}... : {task['status']} ({task['progress']}%)")

async def test_websocket_progress(task_id: str, ws_url: str):
    """Test WebSocket real-time progress"""
    try:
        uri = f"{ws_url}/api/analysis/ws/task/{task_id}"
        print(f"🔌 connect WebSocket: {uri}")
        
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket Connection successful")
            
            # Receive message, wait up to 30 seconds
            timeout = 30
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(message)
                    
                    if data.get("type") == "connection_established":
                        print("🔗 WebSocket Connection confirmation")
                    elif data.get("type") == "progress_update":
                        print(f"📡 Real-time progress: {data.get('status')} ({data.get('progress')}%) - {data.get('message')}")
                    
                    # If the task is completed, exit
                    if data.get("status") in ["completed", "failed", "cancelled"]:
                        break
                        
                except asyncio.TimeoutError:
                    # Send heartbeat
                    await websocket.send("ping")
                    continue
                except Exception as e:
                    print(f"⚠️ WebSocket Message processing error: {e}")
                    break
            
            print("🔌 WebSocket Test completed")
            
    except Exception as e:
        print(f"❌ WebSocket Connection failed: {e}")

async def test_concurrent_requests():
    """Test concurrent request capabilities"""
    print("\n🔄 Test concurrent request capabilities...")
    
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
    max_time = max(duration for _, duration in results)
    
    print(f"📊 Performance statistics:")
    print(f"  average response time: {avg_time:.3f}seconds")
    print(f"  Maximum response time: {max_time:.3f}seconds")
    
    if max_time < 1.0:
        print("🎉 Concurrency performance is good!")
    else:
        print("⚠️ Concurrency performance needs to be optimized")

if __name__ == "__main__":
    print(f"🚀 Start test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    asyncio.run(test_async_analysis())
    asyncio.run(test_concurrent_requests())
    
    print(f"\n✅ Test completion time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
