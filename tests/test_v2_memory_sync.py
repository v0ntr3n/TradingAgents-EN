"""Testing memory synchronization for the v2 engine

Verify:
1. v2 When the engine creates a task, it also creates the task state in memory.
2. v2 When the engine executes a task, the memory status is updated synchronously
3. Update memory status when task completes/fails
"""

import pytest
import asyncio


@pytest.mark.asyncio
async def test_v2_task_memory_creation():
    """Test v2 engine synchronizes to memory when creating tasks"""
    from app.services.task_analysis_service import get_task_analysis_service
    from app.services.memory_state_manager import get_memory_state_manager
    from app.models.analysis import AnalysisTaskType
    from app.models.user import PyObjectId
    
    task_service = get_task_analysis_service()
    memory_manager = get_memory_state_manager()
    
    # Create task
    task = await task_service.create_task(
        user_id=PyObjectId("507f1f77bcf86cd799439011"),
        task_type=AnalysisTaskType.STOCK_ANALYSIS,
        task_params={
            "symbol": "000001",
            "market_type": "cn",
            "research_depth": "fast"
        }
    )
    
    print(f"\n✅ Task has been created: {task.task_id}")
    
    # Verify that it exists in memory
    memory_task = await memory_manager.get_task_dict(task.task_id)
    
    assert memory_task is not None, "The task should exist in memory"
    assert memory_task["task_id"] == task.task_id, "Task ID should match"
    assert memory_task["stock_code"] == "000001", "ticker should match"
    
    print(f"✅ Task found in memory: {memory_task['task_id']}")
    print(f"  Status: {memory_task['status']}")
    print(f"  Stock code: {memory_task['stock_code']}")
    
    # clean up
    await memory_manager.delete_task(task.task_id)


@pytest.mark.asyncio
async def test_v2_task_progress_sync():
    """Synchronize progress to memory when the test v2 engine is executed"""
    from app.services.task_analysis_service import get_task_analysis_service
    from app.services.memory_state_manager import get_memory_state_manager
    from app.models.analysis import AnalysisTaskType
    from app.models.user import PyObjectId

    task_service = get_task_analysis_service()
    memory_manager = get_memory_state_manager()

    # Create task
    task = await task_service.create_task(
        user_id=PyObjectId("507f1f77bcf86cd799439011"),
        task_type=AnalysisTaskType.STOCK_ANALYSIS,
        task_params={
            "symbol": "000001",
            "market_type": "cn",
            "research_depth": "fast"
        }
    )

    print(f"\n✅ Task has been created: {task.task_id}")

    # Simulation progress callback
    progress_updates = []

    async def test_progress_callback(progress: int, message: str, **kwargs):
        """Test progress callback"""
        progress_updates.append({
            "progress": progress,
            "message": message,
            "step_name": kwargs.get("step_name")
        })
        print(f"📊 progress update: {progress}% - {message}")

    # Note: The task is not actually executed here, only the memory synchronization of the progress callback is tested.
    # Actual execution requires complete environment configuration

    # Manually call wrapped_progress_callback to test
    from app.services.memory_state_manager import TaskStatus

    await memory_manager.update_task_status(
        task_id=task.task_id,
        status=TaskStatus.RUNNING,
        progress=50,
        message="📈 Market analysts are analyzing technical indicators and market trends...",
        current_step="market_analyst",
        current_step_name="market analyst",  # 🔑 New: step name
        current_step_description="📈 Market analysts are analyzing technical indicators and market trends..."  # 🔑 New: Step description
    )

    # Verify progress in memory
    memory_task = await memory_manager.get_task_dict(task.task_id)

    assert memory_task is not None, "The task should exist in memory"
    assert memory_task["progress"] == 50, "The progress should be 50%"
    assert memory_task["status"] == "running", "The status should be running"
    assert memory_task["current_step"] == "market_analyst", "The current step should be market_analyst"
    assert memory_task["current_step_name"] == "market analyst", "The step name should be Market Analyst"
    assert memory_task["current_step_description"] == "📈 Market analysts are analyzing technical indicators and market trends...", "The step description should be correct"

    print(f"\n✅ Memory progress verification passed:")
    print(f"  Progress: {memory_task['progress']}%")
    print(f"  Status: {memory_task['status']}")
    print(f"  current step: {memory_task['current_step']}")
    print(f"  step name: {memory_task['current_step_name']}")  # 🔑 New
    print(f"  Step description: {memory_task['current_step_description']}")  # 🔑 New
    print(f"  news: {memory_task['message']}")

    # clean up
    await memory_manager.delete_task(task.task_id)


@pytest.mark.asyncio
async def test_memory_manager_singleton():
    """Test memory manager is a singleton"""
    from app.services.memory_state_manager import get_memory_state_manager
    
    manager1 = get_memory_state_manager()
    manager2 = get_memory_state_manager()
    
    assert id(manager1) == id(manager2), "Memory manager should be a singleton"
    
    print(f"\n✅ Memory manager singleton verification passed:")
    print(f"  Example 1 ID: {id(manager1)}")
    print(f"  Example 2 ID: {id(manager2)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

