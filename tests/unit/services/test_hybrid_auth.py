"""
Testing Hybrid Authentication Schemes

Verify:
1. JWT Token Authentication (API calls)
2. Session Cookie Authentication (web front-end)
3. Both methods fail when logging out.
4. Both methods are invalid when changing the password.
"""

import asyncio
import httpx
import sys
import os

# Add project root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


async def test_hybrid_auth():
    """Test hybrid certification"""
    
    print("=" * 60)
    print("Testing Hybrid Authentication Schemes")
    print("=" * 60)
    
    base_url = "http://localhost:8000"
    
    # test user
    test_username = "admin"
    test_password = "admin123"
    
    async with httpx.AsyncClient(base_url=base_url, follow_redirects=True) as client:
        
        # 1. Test login (get JWT Token and Session Cookie)
        print("\n1️⃣ Test login...")
        login_response = await client.post(
            "/api/auth/login",
            json={"username": test_username, "password": test_password}
        )
        
        if login_response.status_code == 200:
            login_data = login_response.json()
            access_token = login_data["data"]["access_token"]
            print(f"✅ Login successful")
            print(f"   JWT Token: {access_token[:50]}...")
            print(f"   Cookies: {client.cookies}")
        else:
            print(f"❌ Login failed: {login_response.text}")
            return
        
        # 2. Test JWT Token authentication
        print("\n2️⃣ Test JWT Token authentication (API call)...")
        me_response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if me_response.status_code == 200:
            user_data = me_response.json()
            print(f"✅ JWT Token Authentication successful: {user_data['data']['username']}")
        else:
            print(f"❌ JWT Token Authentication failed: {me_response.text}")
        
        # 3. Test Session Cookie authentication (without Authorization header)
        print("\n3️⃣ Testing Session Cookie Authentication (Web Front End)...")
        me_response_cookie = await client.get("/api/auth/me")
        
        if me_response_cookie.status_code == 200:
            user_data = me_response_cookie.json()
            print(f"✅ Session Cookie Authentication successful: {user_data['data']['username']}")
        else:
            print(f"❌ Session Cookie Authentication failed: {me_response_cookie.text}")
        
        # 4. Test logging out (clearing session cookies)
        print("\n4️⃣ Test logging out (without Authorization header)...")
        logout_response = await client.post("/api/auth/logout")
        
        if logout_response.status_code == 200:
            print(f"✅ Log out successfully")
            
            # Verify that the session cookie has expired
            me_response_after_logout = await client.get("/api/auth/me")
            if me_response_after_logout.status_code == 401:
                print(f"✅ Session Cookie Expired (correct)")
            else:
                print(f"❌ Session Cookie Still valid (shouldn t be)")
        else:
            print(f"❌ Logout failed: {logout_response.text}")
        
        # 5. Test whether the JWT Token is still valid (it should be invalid)
        print("\n5️⃣ Test whether the JWT Token is invalid...")
        me_response_jwt = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if me_response_jwt.status_code == 401:
            print(f"✅ JWT Token Expired (correct)")
        else:
            print(f"❌ JWT Token Still valid (shouldn t be)")
        
        # 6. Log in again to test changing password
        print("\n6️⃣ Log in again to test changing password...")
        login_response2 = await client.post(
            "/api/auth/login",
            json={"username": test_username, "password": test_password}
        )
        
        if login_response2.status_code == 200:
            login_data2 = login_response2.json()
            access_token2 = login_data2["data"]["access_token"]
            print(f"✅ Re-login successfully")
            
            # Change password (change to the same password)
            print("\n7️⃣ Test password change...")
            change_pwd_response = await client.post(
                "/api/auth/change-password",
                json={
                    "old_password": test_password,
                    "new_password": test_password  # Change to the same password
                }
            )
            
            if change_pwd_response.status_code == 200:
                print(f"✅ Password changed successfully")
                
                # Verify that the session cookie has expired
                me_response_after_pwd = await client.get("/api/auth/me")
                if me_response_after_pwd.status_code == 401:
                    print(f"✅ Session Cookie Expired (correct)")
                else:
                    print(f"❌ Session Cookie Still valid (shouldn t be)")
                
                # Verify that the JWT Token has expired
                me_response_jwt2 = await client.get(
                    "/api/auth/me",
                    headers={"Authorization": f"Bearer {access_token2}"}
                )
                if me_response_jwt2.status_code == 401:
                    print(f"✅ JWT Token Expired (correct)")
                else:
                    print(f"❌ JWT Token Still valid (shouldn t be)")
            else:
                print(f"❌ Password change failed: {change_pwd_response.text}")
        else:
            print(f"❌ Re-login failed: {login_response2.text}")
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_hybrid_auth())

