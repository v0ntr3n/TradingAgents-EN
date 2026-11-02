#!/usr/bin/env python3
"""
Test synchronized user feedback functionality
Simulate state changes during synchronization and verify user feedback mechanism
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

async def simulate_sync_with_feedback():
    """Simulate the synchronization process and test user feedback"""
    print("=" * 60)
    print("🎭 Simulating the synchronization process - test user feedback")
    print("=" * 60)
    
    try:
        from app.services.multi_source_basics_sync_service import get_multi_source_sync_service
        from app.core.database import init_db, get_mongo_db
        
        # Initialize database
        await init_db()
        service = get_multi_source_sync_service()
        db = get_mongo_db()
        
        print("✅ Service initialization successful")
        
        # 1. Clear previous status
        print("\n1. 🧹 Clear previous status...")
        await db.sync_status.delete_many({"job": "stock_basics_multi_source"})
        service._running = False
        print("   ✅ Status cleared")
        
        # 2. Check initial state
        print("\n2. 📊 Check initial state...")
        initial_status = await service.get_status()
        print(f"   📋 initial state: {initial_status.get('status', 'unknown')}")
        
        # 3. Start synchronization and monitor status changes
        print("\n3. 🚀 Start synchronization and monitor status changes...")
        
        # Start synchronization task
        sync_task = asyncio.create_task(service.run_full_sync(force=True))
        print("   🔄 Synchronization task started")
        
        # Monitor status changes
        previous_status = None
        previous_progress = 0
        monitor_count = 0
        
        while not sync_task.done() and monitor_count < 30:  # Monitor up to 30 times
            await asyncio.sleep(2)  # Check every 2 seconds
            monitor_count += 1
            
            current_status = await service.get_status()
            status = current_status.get('status', 'unknown')
            total = current_status.get('total', 0)
            processed = current_status.get('inserted', 0) + current_status.get('updated', 0)
            progress = round((processed / total * 100) if total > 0 else 0, 1)
            
            # Check status changes
            if status != previous_status:
                print(f"   📈 status change: {previous_status} -> {status}")
                previous_status = status
            
            # Check progress changes
            if progress != previous_progress and progress > 0:
                print(f"   📊 progress update: {progress}% ({processed}/{total})")
                previous_progress = progress
            
            # If synchronization is completed, exit monitoring
            if status in ['success', 'success_with_errors', 'failed']:
                print(f"   🎯 Synchronization completed: {status}")
                break
        
        # Wait for the sync task to complete
        try:
            await asyncio.wait_for(sync_task, timeout=5)
        except asyncio.TimeoutError:
            print("   ⏰ The synchronization task is still running, continue to wait...")
            await sync_task
        
        # 4. Check final status
        print("\n4. 📋 Check final status...")
        final_status = await service.get_status()
        
        status = final_status.get('status', 'unknown')
        total = final_status.get('total', 0)
        inserted = final_status.get('inserted', 0)
        updated = final_status.get('updated', 0)
        errors = final_status.get('errors', 0)
        sources = final_status.get('data_sources_used', [])
        started_at = final_status.get('started_at', '')
        finished_at = final_status.get('finished_at', '')
        
        print(f"   📊 final state: {status}")
        print(f"   📈 Process statistics: total={total}, New={inserted}, update={updated}, Error={errors}")
        print(f"   🔗 data source: {', '.join(sources) if sources else 'None'}")
        print(f"   🕐 start time: {started_at}")
        print(f"   🕑 end time: {finished_at}")
        
        # 5. Simulate front-end user feedback
        print("\n5. 🎭 Simulate front-end user feedback...")
        
        if status == 'success':
            feedback_message = f"🎉 Synchronization completed! Processed {total} records, new {inserted} article, update {updated} Article"
            feedback_type = "Success notification"
        elif status == 'success_with_errors':
            feedback_message = f"⚠️ Sync completed with errors! Processed {total} records, new {inserted} article, update {updated} bar, error {errors} Article"
            feedback_type = "warning notification"
        elif status == 'failed':
            feedback_message = f"❌ Synchronization failed!{final_status.get('message', 'unknown error')}"
            feedback_type = "Error notification"
        else:
            feedback_message = f"ℹ️ Sync status: {status}"
            feedback_type = "Information notification"
        
        print(f"   📢 {feedback_type}: {feedback_message}")
        
        if sources:
            print(f"   📡 Data source notification: Data source used: {', '.join(sources)}")
        
        # 6. Calculate synchronization time
        if started_at and finished_at:
            try:
                start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(finished_at.replace('Z', '+00:00'))
                duration = (end_time - start_time).total_seconds()
                print(f"   ⏱️ Synchronization takes time: {duration:.1f} seconds")
            except Exception as e:
                print(f"   ⏱️ Unable to calculate time taken: {e}")
        
        print(f"\n🎉 User feedback testing completed")
        
        return {
            'status': status,
            'total': total,
            'inserted': inserted,
            'updated': updated,
            'errors': errors,
            'sources': sources,
            'feedback_message': feedback_message,
            'feedback_type': feedback_type
        }
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

async def test_status_polling_simulation():
    """Simulate frontend status polling"""
    print("\n" + "=" * 60)
    print("🔄 Simulate frontend status polling")
    print("=" * 60)
    
    try:
        from app.services.multi_source_basics_sync_service import get_multi_source_sync_service
        
        service = get_multi_source_sync_service()
        
        print("📊 The simulated frontend polls for status every 5 seconds...")
        
        # Simulate polling 10 times
        for i in range(10):
            status = await service.get_status()
            
            current_status = status.get('status', 'unknown')
            total = status.get('total', 0)
            processed = status.get('inserted', 0) + status.get('updated', 0)
            progress = round((processed / total * 100) if total > 0 else 0, 1)
            
            print(f"   polling #{i+1}: Status={current_status}, Progress={progress}% ({processed}/{total})")
            
            # If it is not running, stop polling
            if current_status != 'running':
                print(f"   🛑 Non-running status detected, stop polling")
                break
            
            await asyncio.sleep(1)  # Analog polling interval
        
        print("🎯 Status polling simulation completed")
        
    except Exception as e:
        print(f"❌ Poll simulation failed: {e}")

if __name__ == "__main__":
    result = asyncio.run(simulate_sync_with_feedback())
    if result:
        print(f"\n📊 Summary of test results:")
        print(f"   Status: {result['status']}")
        print(f"   Process: {result['total']} records")
        print(f"   feedback: {result['feedback_message']}")
    
    asyncio.run(test_status_polling_simulation())
