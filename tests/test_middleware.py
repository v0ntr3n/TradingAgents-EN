#!/usr/bin/env python3
"""
Test operation log middleware
"""

import asyncio
import sys
import os
import httpx

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_middleware():
    """Test whether the middleware is working properly"""
    print("🧪 Test operation log middleware...")
    
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient() as client:
        try:
            # test 1: Login request
            print("\n🔐 test 1: Login request")
            login_data = {
                "username": "admin",
                "password": "admin123"
            }
            
            response = await client.post(f"{base_url}/api/auth/login", json=login_data)
            print(f"Login response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                token = data["data"]["access_token"]
                print("✅ Log in successfully and get token")
                
                # test 2: Use token for authentication request
                print("\n📊 test 2: Get operation log list")
                headers = {"Authorization": f"Bearer {token}"}
                
                logs_response = await client.get(
                    f"{base_url}/api/system/logs/list", 
                    headers=headers
                )
                print(f"Get log response status: {logs_response.status_code}")
                
                if logs_response.status_code == 200:
                    logs_data = logs_response.json()
                    total_logs = logs_data["data"]["total"]
                    print(f"✅ Obtaining logs successfully, total number: {total_logs}")
                    
                    # Show the most recent logs
                    logs = logs_data["data"]["logs"]
                    print("📝 recent logs:")
                    for log in logs[:5]:
                        print(f"  - {log['timestamp']} | {log['username']} | {log['action']} | {'✅' if log['success'] else '❌'}")
                else:
                    print(f"❌ Failed to get log: {logs_response.text}")
                
                # test 3: Logout request
                print("\n🚪 test 3: Logout request")
                logout_response = await client.post(
                    f"{base_url}/api/auth/logout",
                    headers=headers
                )
                print(f"Logout response status: {logout_response.status_code}")
                
                if logout_response.status_code == 200:
                    print("✅ Logout successful")
                else:
                    print(f"❌ Logout failed: {logout_response.text}")
                
            else:
                print(f"❌ Login failed: {response.text}")
                
        except Exception as e:
            print(f"❌ test failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_middleware())
