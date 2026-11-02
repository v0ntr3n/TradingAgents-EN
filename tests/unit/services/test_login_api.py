import asyncio
import aiohttp
import json

async def test_login_api():
    """Test whether the login API is working properly"""
    url = "http://localhost:8001/api/auth/login"
    
    # test data
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=login_data) as response:
                print(f"status code: {response.status}")
                print(f"response header: {dict(response.headers)}")
                
                if response.status == 200:
                    result = await response.json()
                    print(f"Login successful!")
                    print(f"full response: {json.dumps(result, indent=2, ensure_ascii=False)}")
                    print(f"access token: {result.get('access_token', 'N/A')[:50]}...")
                    print(f"refresh token: {result.get('refresh_token', 'N/A')[:50]}...")
                    print(f"Expiration time: {result.get('expires_in', 'N/A')} seconds")
                    print(f"User information: {result.get('user', 'N/A')}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"Login failed: {error_text}")
                    return False
                    
    except Exception as e:
        print(f"Request exception: {e}")
        return False

if __name__ == "__main__":
    print("🔐 Test login API...")
    success = asyncio.run(test_login_api())
    if success:
        print("✅ Login API test successful")
    else:
        print("❌ Login API test failed")