"""
Test progress time calculation logic
Verify that post-fix time calculations are correct
"""
import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from datetime import datetime, timedelta
from app.services.memory_state_manager import TaskState, TaskStatus


def test_progress_time_calculation_basic():
    """Test basic time calculation logic - use estimated total time"""
    # Create a task, estimated total time is 5 minutes, has been running for 5 seconds, progress 1%
    task = TaskState(
        task_id="test_task_1",
        user_id="test_user",
        stock_code="000001",
        status=TaskStatus.RUNNING,
        progress=1,  # 1%
        start_time=datetime.now() - timedelta(seconds=5),
        estimated_duration=300  # Estimated 5 minutes
    )

    data = task.to_dict()

    # Verification time calculation
    assert data['elapsed_time'] == pytest.approx(5, abs=0.5), "The elapsed time should be about 5 seconds"

    # Estimated total duration = Estimated value (fixed)= 300 seconds (5 minutes)
    assert data['estimated_total_time'] == 300, "The estimated total duration should be the estimated 300 seconds (5 minutes)"

    # Estimated remaining = Estimated total time - elapsed time = 300 - 5 = 295 seconds
    expected_remaining = 300 - 5
    assert data['remaining_time'] == pytest.approx(expected_remaining, abs=1), \
        f"It is expected that the remaining should be approximately{expected_remaining}seconds ({expected_remaining/60:.1f}minutes)"

    print(f"✅ Test passed:")
    print(f"   elapsed time: {data['elapsed_time']:.1f}seconds")
    print(f"   Estimated total duration: {data['estimated_total_time']:.1f}seconds ({data['estimated_total_time']/60:.1f}minutes)")
    print(f"   Estimated remaining: {data['remaining_time']:.1f}seconds ({data['remaining_time']/60:.1f}minutes)")


def test_progress_time_calculation_10_percent():
    """Time calculation for testing 10% progress"""
    # Create a task with an estimated total duration of 5 minutes and has been running for 30 seconds. Progress 10%
    task = TaskState(
        task_id="test_task_2",
        user_id="test_user",
        stock_code="000001",
        status=TaskStatus.RUNNING,
        progress=10,  # 10%
        start_time=datetime.now() - timedelta(seconds=30),
        estimated_duration=300  # Estimated 5 minutes
    )

    data = task.to_dict()

    # Verification time calculation
    assert data['elapsed_time'] == pytest.approx(30, abs=0.5), "The elapsed time should be approximately 30 seconds"

    # Estimated total duration = Estimated value (fixed)= 300 seconds (5 minutes)
    assert data['estimated_total_time'] == 300, "The estimated total duration should be the estimated 300 seconds (5 minutes)"

    # Estimated remaining = Estimated total time - elapsed time = 300 - 30 = 270 seconds (4.5 minutes)
    expected_remaining = 300 - 30
    assert data['remaining_time'] == pytest.approx(expected_remaining, abs=1), \
        f"It is expected that the remaining should be approximately{expected_remaining}seconds ({expected_remaining/60:.1f}minutes)"

    print(f"✅ Test passed:")
    print(f"   elapsed time: {data['elapsed_time']:.1f}seconds")
    print(f"   Estimated total duration: {data['estimated_total_time']:.1f}seconds ({data['estimated_total_time']/60:.1f}minutes)")
    print(f"   Estimated remaining: {data['remaining_time']:.1f}seconds ({data['remaining_time']/60:.1f}minutes)")


def test_progress_time_calculation_50_percent():
    """Time calculation for testing 50% progress"""
    # Create a task with an estimated total duration of 5 minutes and has been running for 150 seconds. Progress 50%
    task = TaskState(
        task_id="test_task_3",
        user_id="test_user",
        stock_code="000001",
        status=TaskStatus.RUNNING,
        progress=50,  # 50%
        start_time=datetime.now() - timedelta(seconds=150),
        estimated_duration=300  # Estimated 5 minutes
    )

    data = task.to_dict()

    # Verification time calculation
    assert data['elapsed_time'] == pytest.approx(150, abs=0.5), "The elapsed time should be approximately 150 seconds"

    # Estimated total duration = Estimated value (fixed)= 300 seconds (5 minutes)
    assert data['estimated_total_time'] == 300, "The estimated total duration should be the estimated 300 seconds (5 minutes)"

    # Estimated remaining = Estimated total time - elapsed time = 300 - 150 = 150 seconds (2.5 minutes)
    expected_remaining = 300 - 150
    assert data['remaining_time'] == pytest.approx(expected_remaining, abs=1), \
        f"It is expected that the remaining should be approximately{expected_remaining}seconds ({expected_remaining/60:.1f}minutes)"

    print(f"✅ Test passed:")
    print(f"   elapsed time: {data['elapsed_time']:.1f}seconds")
    print(f"   Estimated total duration: {data['estimated_total_time']:.1f}seconds ({data['estimated_total_time']/60:.1f}minutes)")
    print(f"   Estimated remaining: {data['remaining_time']:.1f}seconds ({data['remaining_time']/60:.1f}minutes)")


def test_progress_time_calculation_zero_progress():
    """Time calculation for testing 0% progress (using default estimate)"""
    # Create a task, has been running for 5 seconds, progress 0%
    task = TaskState(
        task_id="test_task_4",
        user_id="test_user",
        stock_code="000001",
        status=TaskStatus.RUNNING,
        progress=0,  # 0%
        start_time=datetime.now() - timedelta(seconds=5)
    )

    data = task.to_dict()

    # Verification time calculation
    assert data['elapsed_time'] == pytest.approx(5, abs=0.5), "The elapsed time should be about 5 seconds"

    # When the progress is 0, the default estimated time (5 minutes) is used
    assert data['estimated_total_time'] == 300, "The estimated total duration should be the default 300 seconds (5 minutes)"
    # Estimated remaining = Estimated total time - elapsed time = 300 - 5 = 295 seconds
    expected_remaining = 300 - 5
    assert data['remaining_time'] == pytest.approx(expected_remaining, abs=1), \
        f"It is expected that the remaining should be approximately{expected_remaining}seconds ({expected_remaining/60:.1f}minutes)"

    print(f"✅ Test passed:")
    print(f"   elapsed time: {data['elapsed_time']:.1f}seconds")
    print(f"   Estimated total duration: {data['estimated_total_time']:.1f}seconds ({data['estimated_total_time']/60:.1f}minutes)")
    print(f"   Estimated remaining: {data['remaining_time']:.1f}seconds ({data['remaining_time']/60:.1f}minutes)")


def test_progress_time_calculation_completed():
    """Calculation of time to test 100% progress"""
    start_time = datetime.now() - timedelta(seconds=300)
    end_time = datetime.now()
    
    task = TaskState(
        task_id="test_task_5",
        user_id="test_user",
        stock_code="000001",
        status=TaskStatus.COMPLETED,
        progress=100,  # 100%
        start_time=start_time,
        end_time=end_time,
        execution_time=300
    )
    
    data = task.to_dict()
    
    # Verification time calculation
    assert data['elapsed_time'] == 300, "The elapsed time should be 300 seconds"
    assert data['estimated_total_time'] == 300, "Estimated total time should equal elapsed time"
    assert data['remaining_time'] == 0, "The expected remainder should be 0"
    
    print(f"✅ Test passed:")
    print(f"   elapsed time: {data['elapsed_time']:.1f}seconds")
    print(f"   Estimated total duration: {data['estimated_total_time']:.1f}seconds ({data['estimated_total_time']/60:.1f}minutes)")
    print(f"   Estimated remaining: {data['remaining_time']:.1f}seconds")


if __name__ == "__main__":
    print("=" * 60)
    print("Test progress time calculation logic")
    print("=" * 60)
    
    print("\n1. Test 1% progress (running for 5 seconds)")
    print("-" * 60)
    test_progress_time_calculation_basic()
    
    print("\n2. Test 10% progress (running for 30 seconds)")
    print("-" * 60)
    test_progress_time_calculation_10_percent()
    
    print("\n3. Test 50% progress (running for 150 seconds)")
    print("-" * 60)
    test_progress_time_calculation_50_percent()
    
    print("\n4. Test 0% progress (running for 5 seconds)")
    print("-" * 60)
    test_progress_time_calculation_zero_progress()
    
    print("\n5. Test 100% progress (completed)")
    print("-" * 60)
    test_progress_time_calculation_completed()
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)

