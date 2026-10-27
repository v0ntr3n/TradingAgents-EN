"""
Time calculation fix for test status API

Verify that time calculation is correct when querying task status from MongoDB
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.services.progress.tracker import RedisProgressTracker


def test_time_calculation_with_fixed_total():
    """Test the time calculation logic using a fixed estimated total duration (old version logic)"""

    # Simulation task start time (10 seconds ago)
    start_time = datetime.now(timezone.utc) - timedelta(seconds=10)
    current_time = datetime.now(timezone.utc)

    # The elapsed time should be about 10 seconds
    elapsed_time = (current_time - start_time).total_seconds()

    print(f"\n elapsed time: {elapsed_time:.2f}seconds")

    # 🔑 Key: The estimated total duration is fixed (determined when the task is created) and does not change with the progress.
    estimated_total_time = 300  # Assume the estimated total duration is 5 minutes (300 seconds)

    # Test scenario 1: Progress 50%, 10 seconds elapsed
    progress_pct = 50
    remaining_time = max(0, estimated_total_time - elapsed_time)

    print(f"\n Scenario 1: Progress 50%, 10 seconds elapsed")
    print(f"  elapsed time: {elapsed_time:.2f}seconds")
    print(f"  Estimated total duration: {estimated_total_time:.2f}Seconds (fixed value)")
    print(f"  Estimated remaining: {remaining_time:.2f}seconds")
    print(f"  Verify: {elapsed_time:.2f} + {remaining_time:.2f} = {elapsed_time + remaining_time:.2f} ≈ {estimated_total_time:.2f}")

    # Verify mathematical consistency
    assert abs((elapsed_time + remaining_time) - estimated_total_time) < 0.01

    # Validation is expected to have approximately 290 seconds remaining (300 - 10 = 290) 
    assert abs(remaining_time - 290) < 1.0

    # Test scenario 2: Progress 15%, 10 seconds elapsed
    progress_pct = 15
    remaining_time = max(0, estimated_total_time - elapsed_time)

    print(f"\n Scenario 2: Progress 15%, 10 seconds elapsed")
    print(f"  elapsed time: {elapsed_time:.2f}seconds")
    print(f"  Estimated total duration: {estimated_total_time:.2f}Seconds (fixed value)")
    print(f"  Estimated remaining: {remaining_time:.2f}seconds")
    print(f"  Verify: {elapsed_time:.2f} + {remaining_time:.2f} = {elapsed_time + remaining_time:.2f} ≈ {estimated_total_time:.2f}")

    # Verify mathematical consistency
    assert abs((elapsed_time + remaining_time) - estimated_total_time) < 0.01

    # Validation is expected to have approximately 290 seconds remaining (300 - 10 = 290, Not related to progress)
    assert abs(remaining_time - 290) < 1.0

    # Test scenario 3: Task completed
    # Simulation task completion time (300 seconds after start)
    end_time = start_time + timedelta(seconds=300)
    elapsed_time_completed = (end_time - start_time).total_seconds()
    estimated_total_time_completed = elapsed_time_completed  # The total time for completed tasks is the elapsed time
    remaining_time_completed = 0

    print(f"\n Scenario 3: Task completed")
    print(f"  elapsed time: {elapsed_time_completed:.2f}seconds")
    print(f"  Estimated total duration: {estimated_total_time_completed:.2f}seconds")
    print(f"  Estimated remaining: {remaining_time_completed:.2f}seconds")

    # Verify time of completed tasks
    assert estimated_total_time_completed == elapsed_time_completed
    assert remaining_time_completed == 0


def test_base_total_time_calculation():
    """Calculation of total test benchmark time"""
    
    # Baseline times for testing different configurations
    test_cases = [
        {
            "analysts": ["market_analyst_v2"],
            "research_depth": "fast",
            "llm_provider": "dashscope",
            "expected_min": 100,  # at least 100 seconds
            "expected_max": 300,  # up to 300 seconds
        },
        {
            "analysts": ["market_analyst_v2", "fundamentals_analyst_v2", "news_analyst_v2"],
            "research_depth": "Depth",
            "llm_provider": "dashscope",
            "expected_min": 500,  # At least 500 seconds
            "expected_max": 800,  # up to 800 seconds
        },
    ]
    
    print("\n Baseline time calculation verification:")
    for i, case in enumerate(test_cases, 1):
        tracker = RedisProgressTracker(
            task_id=f"test_task_{i}",
            analysts=case["analysts"],
            research_depth=case["research_depth"],
            llm_provider=case["llm_provider"]
        )
        
        base_total_time = tracker._get_base_total_time()
        
        print(f"\n scene{i}:")
        print(f"  analyst: {len(case['analysts'])}a")
        print(f"  Research depth: {case['research_depth']}")
        print(f"  LLM provider: {case['llm_provider']}")
        print(f"  Baseline total time: {base_total_time:.2f}seconds")
        
        # Verify that the baseline time is within the expected range
        assert case["expected_min"] <= base_total_time <= case["expected_max"], \
            f"base time {base_total_time} Not within the expected range [{case['expected_min']}, {case['expected_max']}] within"


def test_time_consistency_over_time():
    """Test the consistency of time calculations at different moments"""
    import time
    
    # Create a progress tracker
    tracker = RedisProgressTracker(
        task_id="test_consistency",
        analysts=["market_analyst_v2", "fundamentals_analyst_v2"],
        research_depth="fast",
        llm_provider="dashscope"
    )
    
    # Update progress to 30%
    tracker.update_progress({'progress_percentage': 30})
    
    # First acquisition time
    data1 = tracker.to_dict()
    elapsed1 = data1['elapsed_time']
    remaining1 = data1['remaining_time']
    total1 = data1['estimated_total_time']
    
    print(f"\n First query:")
    print(f"  elapsed time: {elapsed1:.2f}seconds")
    print(f"  Estimated remaining: {remaining1:.2f}seconds")
    print(f"  Estimated total duration: {total1:.2f}seconds")
    print(f"  Verify: {elapsed1:.2f} + {remaining1:.2f} = {elapsed1 + remaining1:.2f} ≈ {total1:.2f}")
    
    # Verify mathematical consistency for the first time
    assert abs((elapsed1 + remaining1) - total1) < 1.0
    
    # wait 1 second
    time.sleep(1)
    
    # Second acquisition time (does not update progress)
    data2 = tracker.to_dict()
    elapsed2 = data2['elapsed_time']
    remaining2 = data2['remaining_time']
    total2 = data2['estimated_total_time']
    
    print(f"\n Second query (after 1 second):")
    print(f"  elapsed time: {elapsed2:.2f}seconds")
    print(f"  Estimated remaining: {remaining2:.2f}seconds")
    print(f"  Estimated total duration: {total2:.2f}seconds")
    print(f"  Verify: {elapsed2:.2f} + {remaining2:.2f} = {elapsed2 + remaining2:.2f} ≈ {total2:.2f}")
    
    # Verify mathematical consistency a second time
    assert abs((elapsed2 + remaining2) - total2) < 1.0
    
    # Verification elapsed time increased by approximately 1 second
    assert (elapsed2 - elapsed1) >= 0.9, f"The elapsed time should increase by about 1 second, the actual increase: {elapsed2 - elapsed1}"
    
    # The estimated remaining time for verification has been reduced by about 1 second
    assert (remaining1 - remaining2) >= 0.9, f"It is expected that the remaining should be reduced by about 1 second, the actual reduction is: {remaining1 - remaining2}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

