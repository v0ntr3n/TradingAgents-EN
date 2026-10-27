#!/usr/bin/env python3
"""
Test operation log function
"""

import asyncio
import sys
import os

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import init_db, get_mongo_db
from app.services.operation_log_service import log_operation, get_operation_log_service
from app.models.operation_log import ActionType

async def test_operation_logs():
    """Test operation log function"""
    print("🧪 Start testing the operation log function...")
    
    try:
        # Initialize database
        await init_db()
        print("✅ Database initialization successful")
        
        # Get service instance
        service = get_operation_log_service()
        print("✅ Operation log service is obtained successfully")
        
        # test 1: Create operation log
        print("\n📝 test 1: Create operation log")
        log_id = await log_operation(
            user_id="admin",
            username="admin",
            action_type=ActionType.USER_LOGIN,
            action="Test user login",
            details={"test": True, "ip": "127.0.0.1"},
            success=True,
            duration_ms=100,
            ip_address="127.0.0.1",
            user_agent="Test Agent"
        )
        print(f"✅ Log created successfully,ID: {log_id}")
        
        # test 2: Create more test logs
        print("\n📝 test 2: Create more test logs")
        test_logs = [
            {
                "action_type": ActionType.STOCK_ANALYSIS,
                "action": "Analyze stocks 000001",
                "details": {"stock_code": "000001", "analysis_type": "comprehensive"},
                "success": True,
                "duration_ms": 1500
            },
            {
                "action_type": ActionType.CONFIG_MANAGEMENT,
                "action": "Update large model configuration",
                "details": {"provider": "openai", "model": "gpt-4"},
                "success": False,
                "error_message": "API Key verification failed",
                "duration_ms": 500
            },
            {
                "action_type": ActionType.DATABASE_OPERATION,
                "action": "Database backup",
                "details": {"backup_type": "full", "size_mb": 150},
                "success": True,
                "duration_ms": 3000
            }
        ]
        
        for i, log_data in enumerate(test_logs):
            log_id = await log_operation(
                user_id="admin",
                username="admin",
                **log_data,
                ip_address="127.0.0.1",
                user_agent="Test Agent"
            )
            print(f"✅ Create test log {i+1} success,ID: {log_id}")
        
        # test 3: Query operation log
        print("\n📋 test 3: Query operation log")
        from app.models.operation_log import OperationLogQuery
        
        query = OperationLogQuery(page=1, page_size=10)
        logs, total = await service.get_logs(query)
        print(f"✅ Query successful, total number: {total}, Return: {len(logs)} Article")
        
        for log in logs[:3]:  # Show first 3 items
            print(f"  - {log.timestamp} | {log.username} | {log.action} | {'✅' if log.success else '❌'}")
        
        # test 4: Get statistics
        print("\n📊 test 4: Get statistics")
        stats = await service.get_stats(days=30)
        print(f"✅ Statistics obtained successfully:")
        print(f"  - Total number of logs: {stats.total_logs}")
        print(f"  - success log: {stats.success_logs}")
        print(f"  - Failure log: {stats.failed_logs}")
        print(f"  - success rate: {stats.success_rate}%")
        print(f"  - Operation type distribution: {stats.action_type_distribution}")
        
        # test 5: Check records in database
        print("\n🔍 test 5: Check database records")
        db = get_mongo_db()
        count = await db.operation_logs.count_documents({})
        print(f"✅ There are total in the database {count} Operation log records")
        
        # Show the latest records
        cursor = db.operation_logs.find().sort("timestamp", -1).limit(3)
        recent_logs = await cursor.to_list(length=3)
        print("📝 The latest 3 records:")
        for log in recent_logs:
            print(f"  - {log.get('timestamp')} | {log.get('username')} | {log.get('action')} | {log.get('success')}")
        
        print("\n🎉 All tests completed! The operation log function works normally.")
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_operation_logs())
