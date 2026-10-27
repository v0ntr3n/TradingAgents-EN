"""
Test progress tracking and step status updates
"""
import asyncio
import aiohttp
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"
USERNAME = "admin"
PASSWORD = "admin123"

async def login() -> str:
    """Log in and get token"""
    async with aiohttp.ClientSession() as session:
        login_data = {
            "username": USERNAME,
            "password": PASSWORD
        }
        
        async with session.post(f"{BASE_URL}/api/auth/login", json=login_data) as response:
            if response.status == 200:
                result = await response.json()
                print(f"📋 Login response: {json.dumps(result, indent=2, ensure_ascii=False)}")

                # Try different data structures
                if "data" in result and "token" in result["data"]:
                    token = result["data"]["token"]
                elif "data" in result and "access_token" in result["data"]:
                    token = result["data"]["access_token"]
                elif "token" in result:
                    token = result["token"]
                elif "access_token" in result:
                    token = result["access_token"]
                else:
                    print(f"❌ Unable to extract from response token")
                    return None

                print(f"✅ Login successful,token: {token[:20]}...")
                return token
            else:
                error = await response.text()
                print(f"❌ Login failed: {error}")
                return None

async def start_analysis(token: str) -> str:
    """Initiate analysis task"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    analysis_data = {
        "stock_code": "601398",
        "parameters": {
            "analysts": ["market", "fundamentals"],
            "research_depth": "fast",
            "custom_requirements": "Test step status update"
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE_URL}/api/analysis/single",
            headers=headers,
            json=analysis_data
        ) as response:
            if response.status == 200:
                result = await response.json()
                print(f"📋 Analyze response: {json.dumps(result, indent=2, ensure_ascii=False)}")
                task_id = result["data"]["task_id"]
                print(f"✅ Analysis task has been submitted: {task_id}")
                return task_id
            else:
                error = await response.text()
                print(f"❌ Failed to submit analysis (status code: {response.status}): {error}")
                return None

async def get_task_status(token: str, task_id: str) -> dict:
    """Get task status"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/api/analysis/tasks/{task_id}/status",
            headers=headers
        ) as response:
            if response.status == 200:
                result = await response.json()
                return result["data"]
            else:
                error = await response.text()
                print(f"❌ Failed to get status: {error}")
                return None

def print_progress_info(status_data: dict, iteration: int):
    """Print progress information"""
    print(f"\n{'='*80}")
    print(f"📊 No. {iteration} queries - {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*80}")
    
    # Basic information
    print(f"📋 Task ID: {status_data.get('task_id', 'N/A')}")
    print(f"📈 Status: {status_data.get('status', 'N/A')}")
    print(f"📊 Progress: {status_data.get('progress', 0)}%")
    print(f"💬 news: {status_data.get('message', 'N/A')}")
    
    # Current step information
    current_step = status_data.get('current_step')
    current_step_name = status_data.get('current_step_name', 'N/A')
    current_step_description = status_data.get('current_step_description', 'N/A')
    
    print(f"\n🎯 current step:")
    print(f"   Index: {current_step}")
    print(f"   Name: {current_step_name}")
    print(f"   Description: {current_step_description}")
    
    # time information
    elapsed = status_data.get('elapsed_time', 0)
    remaining = status_data.get('remaining_time', 0)
    estimated = status_data.get('estimated_total_time', 0)
    
    print(f"\n⏱️ time information:")
    print(f"   elapsed time: {elapsed:.1f}seconds")
    print(f"   Estimated remaining: {remaining:.1f}seconds")
    print(f"   Estimated total duration: {estimated:.1f}seconds")
    
    # Step details
    steps = status_data.get('steps', [])
    if steps:
        print(f"\n📝 Step details (total {len(steps)} a):")
        print(f"{'serial number':<6} {'Status':<12} {'Name':<30} {'weight':<8}")
        print(f"{'-'*80}")
        
        for i, step in enumerate(steps):
            status_icon = {
                'pending': '⏳',
                'current': '🔄',
                'completed': '✅',
                'failed': '❌'
            }.get(step.get('status', 'pending'), '❓')
            
            print(f"{i:<6} {status_icon} {step.get('status', 'N/A'):<10} {step.get('name', 'N/A'):<30} {step.get('weight', 0):.2%}")
        
        # Statistical step status
        status_count = {}
        for step in steps:
            s = step.get('status', 'pending')
            status_count[s] = status_count.get(s, 0) + 1
        
        print(f"\n📊 Step status statistics:")
        for status, count in status_count.items():
            print(f"   {status}: {count}")
    else:
        print(f"\n⚠️ No step information")
    
    print(f"{'='*80}\n")

async def monitor_task_progress(token: str, task_id: str, max_iterations: int = 60, interval: int = 3):
    """Monitor task progress"""
    print(f"\n🔄 Start monitoring task progress...")
    print(f"   Task ID: {task_id}")
    print(f"   Maximum number of queries: {max_iterations}")
    print(f"   Query interval: {interval}seconds")
    
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        
        # Get status
        status_data = await get_task_status(token, task_id)
        
        if not status_data:
            print(f"❌ Unable to get task status")
            break
        
        # Print progress information
        print_progress_info(status_data, iteration)
        
        # Check if completed
        status = status_data.get('status')
        if status == 'completed':
            print(f"✅ Mission accomplished!")
            break
        elif status == 'failed':
            print(f"❌ Mission failed!")
            break
        
        # Waiting for next query
        await asyncio.sleep(interval)
    
    if iteration >= max_iterations:
        print(f"⏰ The maximum number of queries is reached and monitoring is stopped.")

async def main():
    """main function"""
    print(f"{'='*80}")
    print(f"🧪 Test progress tracking and step status updates")
    print(f"{'='*80}\n")
    
    # 1. Login
    print(f"1️⃣ Log in to the system...")
    token = await login()
    if not token:
        print(f"❌ Login failed, exit test")
        return
    
    # 2. Initiate analysis
    print(f"\n2️⃣ Initiate analysis task...")
    task_id = await start_analysis(token)
    if not task_id:
        print(f"❌ Failed to initiate analysis and exited the test")
        return
    
    # 3. Monitor progress
    print(f"\n3️⃣ Monitor task progress...")
    await monitor_task_progress(token, task_id, max_iterations=100, interval=3)
    
    print(f"\n{'='*80}")
    print(f"✅ Test completed")
    print(f"{'='*80}")

if __name__ == "__main__":
    asyncio.run(main())

