#!/usr/bin/env python3
"""
Test the three functions of synchronization control: start synchronization, refresh status, and clear cache
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

async def test_sync_control_functions():
    """Test the three core functions of synchronization control"""
    print("=" * 60)
    print("🧪 Test synchronization control function")
    print("=" * 60)
    
    try:
        from app.services.multi_source_basics_sync_service import get_multi_source_sync_service
        from app.core.database import init_db, get_mongo_db
        
        # Initialize database
        await init_db()
        service = get_multi_source_sync_service()
        db = get_mongo_db()
        
        print("✅ Service initialization successful")
        
        # 1. Test to get synchronization status
        print("\n1. 📊 Test to get synchronization status...")
        try:
            status = await service.get_status()
            print(f"   ✅ Current status: {status.get('status', 'unknown')}")
            print(f"   📈 Statistics: total={status.get('total', 0)}, New={status.get('inserted', 0)}, update={status.get('updated', 0)}")
            if status.get('data_sources_used'):
                print(f"   🔗 Data source used: {status.get('data_sources_used')}")
        except Exception as e:
            print(f"   ❌ Failed to get status: {e}")
        
        # 2. Test clear cache
        print("\n2. 🗑️ Test clear cache...")
        try:
            # First check if there is cached data
            cache_count_before = await db.sync_status.count_documents({"job": "stock_basics_multi_source"})
            print(f"   📊 Number of cached records before clearing: {cache_count_before}")
            
            # Logic for clearing the cache (simulating API calls)
            result = await db.sync_status.delete_many({"job": "stock_basics_multi_source"})
            service._running = False
            
            cache_count_after = await db.sync_status.count_documents({"job": "stock_basics_multi_source"})
            print(f"   ✅ Clear cache successfully: deleted{result.deleted_count}records")
            print(f"   📊 Number of cached records after clearing: {cache_count_after}")
            
        except Exception as e:
            print(f"   ❌ Failed to clear cache: {e}")
        
        # 3. Test start synchronization (small-scale testing)
        print("\n3. 🚀 Test starts synchronization...")
        try:
            # Check data source availability
            from app.services.data_source_adapters import DataSourceManager
            manager = DataSourceManager()
            available_adapters = manager.get_available_adapters()
            
            if not available_adapters:
                print("   ⚠️ No data source available, skip sync test")
            else:
                print(f"   📡 Available data sources: {[adapter.name for adapter in available_adapters]}")
                
                # Start synchronization (non-blocking)
                print("   🔄 Start synchronization task...")
                
                # Create a simple sync task to test
                sync_task = asyncio.create_task(service.run_full_sync(force=True))
                
                # Wait a short time for sync to begin
                await asyncio.sleep(2)
                
                # Check sync status
                status = await service.get_status()
                print(f"   📊 Sync status: {status.get('status', 'unknown')}")
                
                if status.get('status') == 'running':
                    print("   ✅ Synchronization task started successfully")
                    print("   ⏳ Wait for sync to complete...")
                    
                    # Wait for sync to complete or timeout
                    try:
                        await asyncio.wait_for(sync_task, timeout=30)
                        final_status = await service.get_status()
                        print(f"   🎯 Synchronization completed: {final_status.get('status')}")
                        print(f"   📈 final tally: total={final_status.get('total', 0)}, New={final_status.get('inserted', 0)}, update={final_status.get('updated', 0)}")
                    except asyncio.TimeoutError:
                        print("   ⏰ Sync timed out but task is still running in the background")
                        sync_task.cancel()
                else:
                    print(f"   ⚠️ Abnormal synchronization status: {status.get('status')}")
                    if status.get('message'):
                        print(f"   💬 news: {status.get('message')}")
                
        except Exception as e:
            print(f"   ❌ Sync test failed: {e}")
            import traceback
            traceback.print_exc()
        
        # 4. final status check
        print("\n4. 📋 final status check...")
        try:
            final_status = await service.get_status()
            print(f"   📊 final state: {final_status.get('status', 'unknown')}")
            print(f"   🕐 start time: {final_status.get('started_at', 'N/A')}")
            print(f"   🕑 end time: {final_status.get('finished_at', 'N/A')}")
            
            if final_status.get('data_sources_used'):
                print(f"   🔗 Data source used: {', '.join(final_status.get('data_sources_used'))}")
            
        except Exception as e:
            print(f"   ❌ Final status check failed: {e}")
        
        print(f"\n🎉 Synchronous control function test completed")
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()

async def test_api_endpoints():
    """Test API endpoints (simulate HTTP calls)"""
    print("\n" + "=" * 60)
    print("🌐 Test API endpoints")
    print("=" * 60)
    
    try:
        # Here you can add HTTP client testing
        # But to simplify, we call the routing function directly
        from app.routers.multi_source_sync import get_sync_status, clear_sync_cache, run_stock_basics_sync
        
        print("1. 📊 Test to get synchronization status API...")
        try:
            response = await get_sync_status()
            print(f"   ✅ API Response successful: {response.success}")
            print(f"   📊 Status: {response.data.get('status', 'unknown')}")
        except Exception as e:
            print(f"   ❌ API call failed: {e}")
        
        print("\n2. 🗑️ Test clear cache API...")
        try:
            response = await clear_sync_cache()
            print(f"   ✅ API Response successful: {response.success}")
            print(f"   💬 news: {response.message}")
            print(f"   📊 Clear the number of items: {response.data.get('items_cleared', 0)}")
        except Exception as e:
            print(f"   ❌ API call failed: {e}")
        
        print("\n3. 🚀 Test starts synchronization API...")
        try:
            # Test startup synchronization (without waiting for completion)
            response = await run_stock_basics_sync(force=True)
            print(f"   ✅ API Response successful: {response.success}")
            print(f"   💬 news: {response.message}")
            print(f"   📊 Sync status: {response.data.get('status', 'unknown')}")
        except Exception as e:
            print(f"   ❌ API call failed: {e}")
        
        print(f"\n🎉 API Endpoint testing completed")
        
    except Exception as e:
        print(f"❌ API test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_sync_control_functions())
    asyncio.run(test_api_endpoints())
