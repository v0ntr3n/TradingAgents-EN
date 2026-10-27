"""
Test task cancellation function

Verification tasks can be canceled during execution
"""

import asyncio
from app.core.database import init_database, get_mongo_db
from app.services.task_analysis_service import get_task_analysis_service
from app.models.analysis import AnalysisTaskType
from app.models.user import PyObjectId


async def test_task_cancellation():
    """Test task canceled"""
    print("=" * 60)
    print("🧪 Test task cancellation function")
    print("=" * 60)
    
    # Initialize database
    await init_database()
    
    # Get services
    task_service = get_task_analysis_service()
    
    # Create test tasks
    print("\n1️⃣ Create test tasks...")
    task = await task_service.create_task(
        user_id=PyObjectId("507f1f77bcf86cd799439011"),  # test user ID
        task_type=AnalysisTaskType.STOCK_ANALYSIS,
        task_params={
            "symbol": "000001",
            "market_type": "cn",
            "research_depth": "Standard"
        },
        engine_type="workflow",
        preference_type="neutral"
    )
    
    print(f"✅ Task has been created: {task.task_id}")
    print(f"   Status: {task.status}")
    
    # Execute tasks asynchronously (without waiting for completion)
    print("\n2️⃣ Start task...")
    task_future = asyncio.create_task(task_service.execute_task(task))
    
    # Wait 3 seconds before canceling the task
    print("\n3️⃣ Wait 3 seconds before canceling the task...")
    await asyncio.sleep(3)
    
    print("\n4️⃣ Cancel task...")
    success = await task_service.cancel_task(task.task_id)
    
    if success:
        print(f"✅ Task cancellation request sent")
    else:
        print(f"❌ Task cancellation failed (may have been completed)")
    
    # Wait for task execution to complete (TaskCancelledException should be thrown)
    print("\n5️⃣ Wait for task execution to complete...")
    try:
        result_task = await task_future
        print(f"📊 task final status: {result_task.status}")
        print(f"   error message: {result_task.error_message}")
    except Exception as e:
        print(f"⚠️ Task execution exception: {e}")
    
    # Query task status
    print("\n6️⃣ Query the final status of the task...")
    final_task = await task_service.get_task(task.task_id)
    if final_task:
        print(f"📊 final state: {final_task.status}")
        print(f"   Progress: {final_task.progress}%")
        print(f"   error message: {final_task.error_message}")
        print(f"   Execution time: {final_task.execution_time:.2f}s")
    
    print("\n" + "=" * 60)
    print("✅ Test completed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_task_cancellation())

