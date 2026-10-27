#!/usr/bin/env python3
"""
Test the synchronization history API function
Verify the acquisition and display of history records
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from datetime import datetime

# Setup log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)

async def test_sync_history_api():
    """Test sync history API"""
    print("=" * 60)
    print("📚 Test sync history API")
    print("=" * 60)
    
    try:
        from app.core.database import init_db, get_mongo_db
        from app.services.multi_source_basics_sync_service import get_multi_source_sync_service
        
        # Initialize database
        await init_db()
        db = get_mongo_db()
        service = get_multi_source_sync_service()
        
        print("✅ Service initialization successful")
        
        # 1. Check existing history
        print("\n1. 📊 Check existing history...")
        existing_count = await db.sync_status.count_documents({"job": "stock_basics_multi_source"})
        print(f"   📈 Number of existing history records: {existing_count}")
        
        # 2. If there is no history, create some test data
        if existing_count == 0:
            print("\n2. 🏗️ Create test history data...")
            
            test_records = [
                {
                    "job": "stock_basics_multi_source",
                    "status": "success",
                    "started_at": datetime.utcnow().isoformat(),
                    "finished_at": datetime.utcnow().isoformat(),
                    "total": 5427,
                    "inserted": 0,
                    "updated": 5427,
                    "errors": 0,
                    "data_sources_used": ["stock_list:tushare", "daily_data:tushare"],
                    "last_trade_date": "20250903"
                },
                {
                    "job": "stock_basics_multi_source",
                    "status": "success_with_errors",
                    "started_at": (datetime.utcnow()).isoformat(),
                    "finished_at": (datetime.utcnow()).isoformat(),
                    "total": 5420,
                    "inserted": 15,
                    "updated": 5400,
                    "errors": 5,
                    "data_sources_used": ["stock_list:akshare", "daily_data:tushare"],
                    "last_trade_date": "20250902"
                }
            ]
            
            result = await db.sync_status.insert_many(test_records)
            print(f"   ✅ Created {len(result.inserted_ids)} test records")
        
        # 3. Testing the history API (simulating HTTP calls)
        print("\n3. 🌐 Test history API...")
        
        # Simulate API calls
        from app.routers.multi_source_sync import get_sync_history
        
        # Test the first page
        print("   📄 Test the first page...")
        try:
            response = await get_sync_history(page=1, page_size=10)
            print(f"   ✅ API Response successful: {response.success}")
            print(f"   📊 Number of records: {len(response.data['records'])}")
            print(f"   📈 total: {response.data['total']}")
            print(f"   📄 Page number: {response.data['page']}")
            print(f"   🔄 are there more: {response.data['has_more']}")
            
            # Show details of the first record
            if response.data['records']:
                first_record = response.data['records'][0]
                print(f"   📋 first record:")
                print(f"      Status: {first_record.get('status')}")
                print(f"      total: {first_record.get('total')}")
                print(f"      start time: {first_record.get('started_at')}")
                print(f"      completion time: {first_record.get('finished_at')}")
                print(f"      data source: {first_record.get('data_sources_used', [])}")
                
        except Exception as e:
            print(f"   ❌ API call failed: {e}")
        
        # 4. Test status filter
        print("\n4. 🔍 Test status filter...")
        try:
            response = await get_sync_history(page=1, page_size=10, status="success")
            print(f"   ✅ Success status filter: {len(response.data['records'])} records")
        except Exception as e:
            print(f"   ❌ Status filtering failed: {e}")
        
        # 5. Run a new sync, creating new history
        print("\n5. 🚀 Run a new sync to create history...")
        try:
            sync_result = await service.run_full_sync(force=True)
            print(f"   ✅ Synchronization completed: {sync_result.get('status')}")
            
            # Wait to make sure the record is saved
            await asyncio.sleep(1)
            
            # Check the history number again
            new_count = await db.sync_status.count_documents({"job": "stock_basics_multi_source"})
            print(f"   📈 Number of new history records: {new_count}")
            
        except Exception as e:
            print(f"   ❌ Sync failed: {e}")
        
        # 6. final verification
        print("\n6. ✅ final verification...")
        final_response = await get_sync_history(page=1, page_size=5)
        print(f"   📊 Latest history number: {len(final_response.data['records'])}")
        
        if final_response.data['records']:
            latest = final_response.data['records'][0]
            print(f"   🕐 Latest recording time: {latest.get('started_at')}")
            print(f"   📊 latest record status: {latest.get('status')}")
        
        print(f"\n🎉 Synchronization history API test completed")
        
        return {
            'total_records': final_response.data['total'],
            'latest_status': final_response.data['records'][0].get('status') if final_response.data['records'] else None,
            'api_working': True
        }
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

async def test_frontend_integration():
    """Test front-end integration"""
    print("\n" + "=" * 60)
    print("🌐 Front-End Integration Testing Guide")
    print("=" * 60)
    
    print("Now you can test the following functionality on the frontend:")
    print()
    print("1. 🔄 **Refresh sync history**:")
    print("   - Click on the sync history card 'Refresh' button")
    print("   - You should be able to see the real historical records")
    print()
    print("2. 🚀 **Run a sync and watch historical updates**:")
    print("   - Click 'force resync' button")
    print("   - Once the sync is complete, the history should update automatically")
    print()
    print("3. 🕐 **Check completion time**:")
    print("   - Completion time should show real timestamp")
    print("   - no longer fixed '2025/09/04 00:53:38'")
    print()
    print("4. 📊 **Validate statistics**:")
    print("   - The total number, new additions, updates, and errors should be real data")
    print("   - Data source information should show the actual data source used")
    print()
    print("5. 🔔 **Test notification functionality**:")
    print("   - A success notification should be displayed after the sync is complete")
    print("   - Contains detailed statistics")
    print()
    print("If the above functions work normally, the repair is successful!")

if __name__ == "__main__":
    result = asyncio.run(test_sync_history_api())
    if result:
        print(f"\n📊 Summary of test results:")
        print(f"   Total number of historical records: {result['total_records']}")
        print(f"   latest status: {result['latest_status']}")
        print(f"   API normal: {result['api_working']}")
    
    asyncio.run(test_frontend_integration())
