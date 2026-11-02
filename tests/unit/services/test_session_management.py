"""
Test session management functionality

Verify:
1. Create after logging in session
2. The session becomes invalid after logging out.
3. After changing the password, all sessions will become invalid.
4. Token Can be revoked after leakage
"""

import asyncio
import sys
import os

# Add project root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import init_database, get_mongo_db
from app.services.auth_service import AuthService
from app.services.session_service import get_session_service
from app.services.user_service import user_service


async def test_session_management():
    """Test session management"""
    
    print("=" * 60)
    print("Test session management functionality")
    print("=" * 60)
    
    # Initialize database
    await init_database()

    # Get session service (no need to pass in db, synchronous connection will be automatically used)
    session_service = get_session_service()
    
    # test user
    test_username = "testuser"
    test_password = "testpass123"
    
    # 1. Create test user if does not exist
    print("\n1️⃣ Create test user...")
    user = await user_service.get_user_by_username(test_username)
    if not user:
        from app.models.user import UserCreate
        user_data = UserCreate(
            username=test_username,
            email="test@example.com",
            password=test_password
        )
        user = await user_service.create_user(user_data)
        print(f"✅ User created successfully: {user.username}")
    else:
        print(f"✅ User already exists: {user.username}")
    
    # 2. Simulate login, create session
    print("\n2️⃣ Simulate login, create session...")
    session_id = session_service.create_session(
        user_id=str(user.id),
        ip_address="127.0.0.1",
        user_agent="Test Client",
        expires_in_seconds=3600
    )
    print(f"✅ Session Created successfully: {session_id[:16]}...")
    
    # 3. Generate token (including session_id)
    print("\n3️⃣ generate JWT Token...")
    token = AuthService.create_access_token(sub=user.username, session_id=session_id)
    print(f"✅ Token Generated successfully: {token[:50]}...")
    
    # 4. Verify token and session
    print("\n4️⃣ Verify Token and Session...")
    token_data = AuthService.verify_token(token)
    if token_data:
        print(f"✅ Token Verification successful: sub={token_data.sub}, session_id={token_data.session_id[:16]}...")
        
        session = session_service.verify_session(token_data.session_id)
        if session:
            print(f"✅ Session Verification successful: user_id={session.user_id}")
        else:
            print("❌ Session Authentication failed")
    else:
        print("❌ Token Authentication failed")
    
    # 5. Test logging out (revoking session)
    print("\n5️⃣ Test logging out (revoking session)...")
    success = session_service.revoke_session(session_id)
    if success:
        print(f"✅ Session Revoked successfully")
        
        # Verify session again (should fail)
        session = session_service.verify_session(session_id)
        if session:
            print("❌ Session Still valid (shouldn t be)")
        else:
            print("✅ Session Expired (correct)")
    else:
        print("❌ Session Undo failed")
    
    # 6. Test password changes and then revoke all session
    print("\n6️⃣ Test password changes and then revoke all session...")
    
    # Create multiple session
    session_ids = []
    for i in range(3):
        sid = session_service.create_session(
            user_id=str(user.id),
            ip_address=f"192.168.1.{i+1}",
            user_agent=f"Device {i+1}",
            expires_in_seconds=3600
        )
        session_ids.append(sid)
        print(f"  Create Session {i+1}: {sid[:16]}...")
    
    # Undo all session
    revoked_count = session_service.revoke_all_user_sessions(str(user.id))
    print(f"✅ revoked {revoked_count} a session")
    
    # Verify that all sessions have expired
    for i, sid in enumerate(session_ids):
        session = session_service.verify_session(sid)
        if session:
            print(f"❌ Session {i+1} Still valid (shouldn t be)")
        else:
            print(f"✅ Session {i+1} Expired (correct)")
    
    # 7. Test to get all activities of the user session
    print("\n7️⃣ Test to get all activities of the user session...")
    
    # create new session
    for i in range(2):
        session_service.create_session(
            user_id=str(user.id),
            ip_address=f"10.0.0.{i+1}",
            user_agent=f"Browser {i+1}",
            expires_in_seconds=3600
        )
    
    sessions = session_service.get_user_sessions(str(user.id))
    print(f"✅ User has {len(sessions)} active session:")
    for i, s in enumerate(sessions):
        print(f"  Session {i+1}: {s.session_id[:16]}..., IP: {s.ip_address}, UA: {s.user_agent}")
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_session_management())

