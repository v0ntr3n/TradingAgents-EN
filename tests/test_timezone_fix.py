#!/usr/bin/env python3
"""
Test time zone fix
"""

import asyncio
import sys
import os
import datetime

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import init_db, get_mongo_db
from app.services.operation_log_service import log_operation
from app.models.operation_log import ActionType

async def test_timezone_fix():
    """Test time zone fix"""
    print("🕐 Test time zone fix...")
    
    try:
        # Initialize database
        await init_db()
        print("✅ Database initialization successful")
        
        # Display current time information
        now_local = datetime.datetime.now()
        now_utc = datetime.datetime.utcnow()
        print(f"📅 current local time: {now_local}")
        print(f"📅 Current UTC time: {now_utc}")
        print(f"📅 time difference: {now_local - now_utc}")
        
        # Create a test log
        print("\n📝 Create test log...")
        log_id = await log_operation(
            user_id="admin",
            username="admin",
            action_type=ActionType.SYSTEM_SETTINGS,
            action="time zone test",
            details={
                "test_type": "timezone_fix",
                "local_time": now_local.isoformat(),
                "utc_time": now_utc.isoformat()
            },
            success=True,
            duration_ms=100,
            ip_address="127.0.0.1",
            user_agent="Timezone Test"
        )
        print(f"✅ Log created successfully,ID: {log_id}")
        
        # Query this record directly from the database
        print("\n🔍 Query records from database...")
        db = get_mongo_db()
        from bson import ObjectId
        
        doc = await db.operation_logs.find_one({"_id": ObjectId(log_id)})
        if doc:
            print(f"📄 time stored in database:")
            print(f"  timestamp: {doc['timestamp']}")
            print(f"  created_at: {doc['created_at']}")
            print(f"  action: {doc['action']}")
            
            # compare time
            stored_time = doc['timestamp']
            print(f"\n⏰ time comparison:")
            print(f"  storage time: {stored_time}")
            print(f"  local time: {now_local}")
            print(f"  UTC time: {now_utc}")
            
            # Determine what time is stored
            if abs((stored_time - now_local).total_seconds()) < 60:
                print("✅ Stored is local time")
            elif abs((stored_time - now_utc).total_seconds()) < 60:
                print("⚠️ The UTC time is stored")
            else:
                print("❓ Storage time is unclear")
        else:
            print("❌ No record found")
        
        # Test the time format returned by the API
        print("\n🌐 Test API return format...")
        from app.services.operation_log_service import get_operation_log_service
        from app.models.operation_log import OperationLogQuery
        
        service = get_operation_log_service()
        query = OperationLogQuery(page=1, page_size=1)
        logs, total = await service.get_logs(query)
        
        if logs:
            log = logs[0]
            print(f"📋 API return time: {log.timestamp}")
            print(f"📋 time type: {type(log.timestamp)}")
            
            # If it is a string, try to parse
            if isinstance(log.timestamp, str):
                try:
                    parsed_time = datetime.datetime.fromisoformat(log.timestamp.replace('Z', ''))
                    print(f"📋 time after parsing: {parsed_time}")
                except:
                    print("❌ Time string parsing failed")
        
        print("\n🎉 Time zone test completed!")
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_timezone_fix())
