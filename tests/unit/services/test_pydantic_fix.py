#!/usr/bin/env python3
"""
Testing Pydantic v2 fixes
"""

try:
    from webapi.models.user import PyObjectId, User
    from bson import ObjectId
    
    print("✅ Import successful")
    
    # test PyObjectId
    test_id = ObjectId()
    print(f"✅ ObjectId Created successfully: {test_id}")
    
    # Test the User model
    user_data = {
        "username": "test_user",
        "email": "test@example.com",
        "is_active": True,
        "is_verified": False,
        "is_admin": False
    }
    
    user = User(**user_data)
    print(f"✅ User Model created successfully: {user.username}")
    
    print("🎉 Pydantic v2 Repair verification successful!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
