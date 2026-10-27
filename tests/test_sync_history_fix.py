#!/usr/bin/env python3
"""
Test sync history fix
Verify:
1. Each sync creates a new history record
2. Time zone is displayed correctly
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

async def test_multiple_sync_records():
    """Test multiple synchronizations to create multiple records"""
    print("=" * 60)
    print("🔄 Test multiple synchronizations to create multiple historical records")
    print("=" * 60)
    
    try:
        from app.core.database import init_db, get_mongo_db
        from app.services.multi_source_basics_sync_service import get_multi_source_sync_service
        
        # Initialize database
        await init_db()
        db = get_mongo_db()
        service = get_multi_source_sync_service()
        
        print("✅ Service initialization successful")
        
        # 1. Clear existing history (for testing)
        print("\n1. 🧹 Clear existing history...")
        result = await db.sync_status.delete_many({"job": "stock_basics_multi_source"})
        print(f"   deleted {result.deleted_count} records")
        
        # 2. Run the first sync
        print("\n2. 🚀 Run the first sync...")
        start_time_1 = datetime.now()
        print(f"   start time: {start_time_1.strftime('%Y-%m-%d %H:%M:%S')}")
        
        result1 = await service.run_full_sync(force=True)
        print(f"   ✅ First synchronization completed: {result1.get('status')}")
        
        # Wait one second to make sure the timestamps are different
        await asyncio.sleep(2)
        
        # 3. Run a second sync
        print("\n3. 🚀 Run a second sync...")
        start_time_2 = datetime.now()
        print(f"   start time: {start_time_2.strftime('%Y-%m-%d %H:%M:%S')}")
        
        result2 = await service.run_full_sync(force=True)
        print(f"   ✅ Second synchronization completed: {result2.get('status')}")
        
        # Wait one second to make sure the timestamps are different
        await asyncio.sleep(2)
        
        # 4. Run the third sync
        print("\n4. 🚀 Run the third sync...")
        start_time_3 = datetime.now()
        print(f"   start time: {start_time_3.strftime('%Y-%m-%d %H:%M:%S')}")
        
        result3 = await service.run_full_sync(force=True)
        print(f"   ✅ The third synchronization is completed: {result3.get('status')}")
        
        # 5. Check history number
        print("\n5. 📊 Check history...")
        total_records = await db.sync_status.count_documents({"job": "stock_basics_multi_source"})
        print(f"   📈 Total number of historical records: {total_records}")
        
        if total_records >= 3:
            print("   ✅ Success! New records are created with every sync")
        else:
            print("   ❌ Failure! Incorrect number of records")
        
        # 6. Check timestamp
        print("\n6. 🕐 Check timestamp...")
        records = await db.sync_status.find(
            {"job": "stock_basics_multi_source"}
        ).sort("started_at", -1).to_list(length=5)
        
        print("   Recent sync history:")
        for i, record in enumerate(records):
            started_at = record.get('started_at', '')
            finished_at = record.get('finished_at', '')
            status = record.get('status', '')
            
            # parse timestamp
            if started_at:
                try:
                    start_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                    start_local = start_dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    start_local = started_at
            else:
                start_local = "unknown"
                
            if finished_at:
                try:
                    finish_dt = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
                    finish_local = finish_dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    finish_local = finished_at
            else:
                finish_local = "Not completed"
            
            print(f"   {i+1}. Status: {status}")
            print(f"      start: {start_local}")
            print(f"      Complete: {finish_local}")
            print(f"      total: {record.get('total', 0)}")
            print()
        
        # 7. Verify time zone
        print("7. 🌍 Verify time zone...")
        if records:
            latest_record = records[0]
            started_at = latest_record.get('started_at', '')
            
            if started_at:
                try:
                    # parse timestamp
                    record_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                    current_dt = datetime.now()
                    
                    # Calculate the time difference (should be very small, because it was just synchronized)
                    time_diff = abs((current_dt - record_dt).total_seconds())
                    
                    print(f"   Record time: {record_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"   current time: {current_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"   time difference: {time_diff:.1f} seconds")
                    
                    if time_diff < 300:  # 5 within minutes
                        print("   ✅ The time zone is correct!")
                    else:
                        print("   ❌ There may be a problem with the time zone")
                        
                except Exception as e:
                    print(f"   ❌ Time parsing failed: {e}")
        
        return {
            'total_records': total_records,
            'records_created': total_records >= 3,
            'timezone_correct': time_diff < 300 if 'time_diff' in locals() else False
        }
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

async def test_api_response():
    """Test API response"""
    print("\n" + "=" * 60)
    print("🌐 Test API response")
    print("=" * 60)
    
    try:
        from app.routers.multi_source_sync import get_sync_history
        
        # Test to get history
        print("📡 call history API...")
        response = await get_sync_history(page=1, page_size=5)
        
        if response.success:
            records = response.data['records']
            print(f"✅ API The call was successful and the {len(records)} records")
            
            if records:
                latest = records[0]
                print(f"📊 latest record:")
                print(f"   Status: {latest.get('status')}")
                print(f"   start time: {latest.get('started_at')}")
                print(f"   completion time: {latest.get('finished_at')}")
                print(f"   total: {latest.get('total')}")
                print(f"   data source: {latest.get('data_sources_used', [])}")
        else:
            print(f"❌ API call failed: {response.message}")
            
    except Exception as e:
        print(f"❌ API test failed: {e}")

if __name__ == "__main__":
    print("🧪 Start synchronizing history repair test")
    print("=" * 60)
    
    result = asyncio.run(test_multiple_sync_records())
    
    if result:
        print(f"\n📊 Summary of test results:")
        print(f"   Total number of historical records: {result['total_records']}")
        print(f"   Record created correctly: {'✅' if result['records_created'] else '❌'}")
        print(f"   Time zone is displayed correctly: {'✅' if result['timezone_correct'] else '❌'}")
        
        if result['records_created'] and result['timezone_correct']:
            print(f"\n🎉 All tests passed! Repair successful!")
        else:
            print(f"\n⚠️ Some tests failed and require further inspection")
    
    # test API
    asyncio.run(test_api_response())
    
    print(f"\n📝 Now you can test on the frontend:")
    print(f"   1. multiple clicks'force resync'")
    print(f"   2. Refresh history after each sync")
    print(f"   3. You should be able to see multiple historical records")
    print(f"   4. The time display should be the correct local time")
