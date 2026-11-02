"""
Fix for testing async event loop in thread pool

Problem: Calling in thread pool asyncio.get_event_loop() will throw RuntimeError
Solution: use asyncio.new_event_loop() Create a new event loop
"""

import asyncio
import pytest
from concurrent.futures import ThreadPoolExecutor
from tradingagents.dataflows.data_source_manager import DataSourceManager


def test_asyncio_in_thread_pool():
    """Testing the use of asynchronous methods in a thread pool"""
    
    def run_in_thread():
        """Functions running in the thread pool"""
        # This should not throw RuntimeError
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            # There is no event loop in the thread pool, create a new
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Test running a simple asynchronous function
        async def simple_async():
            await asyncio.sleep(0.01)
            return "success"
        
        result = loop.run_until_complete(simple_async())
        return result
    
    # Execute in thread pool
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(run_in_thread)
        result = future.result(timeout=5)
        assert result == "success"


def test_data_source_manager_in_thread_pool():
    """Test the use of DataSourceManager in the thread pool"""
    
    def get_stock_data():
        """Get stock data in thread pool"""
        manager = DataSourceManager()
        # This should not throw RuntimeError
        # NOTE: Actual data retrieval may fail (if no API key is configured), but this should not be an event loop error
        try:
            result = manager.get_stock_data(
                symbol="000001",
                start_date="2025-01-01",
                end_date="2025-01-10",
                period="daily"
            )
            return result
        except Exception as e:
            # If it is an event loop error, the test fails
            if "There is no current event loop" in str(e):
                raise AssertionError(f"Event loop bug not fixed: {e}")
            # Other errors (such as API configuration issues) are acceptable
            return f"Other errors (acceptable): {type(e).__name__}"
    
    # Execute in thread pool
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(get_stock_data)
        result = future.result(timeout=30)
        
        # Verify it's not an event loop error
        assert "There is no current event loop" not in str(result)
        print(f"✅ Test passed, result: {result[:200] if isinstance(result, str) else result}")


def test_multiple_threads():
    """Test multiple threads using asynchronous methods simultaneously"""
    
    def run_async_task(task_id):
        """Run asynchronous tasks in threads"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        async def task():
            await asyncio.sleep(0.01)
            return f"Task {task_id} completed"
        
        return loop.run_until_complete(task())
    
    # Execute simultaneously in multiple threads
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_async_task, i) for i in range(5)]
        results = [f.result(timeout=5) for f in futures]
        
        # Verify that all tasks are completed successfully
        assert len(results) == 5
        for i, result in enumerate(results):
            assert result == f"Task {i} completed"


if __name__ == "__main__":
    print("🧪 test 1: Asynchronous methods in thread pool")
    test_asyncio_in_thread_pool()
    print("✅ Test 1 passed\n")
    
    print("🧪 test 2: DataSourceManager in thread pool")
    test_data_source_manager_in_thread_pool()
    print("✅ Test 2 passed\n")
    
    print("🧪 test 3: Multi-thread concurrency")
    test_multiple_threads()
    print("✅ Test 3 passed\n")
    
    print("🎉 All tests passed!")

